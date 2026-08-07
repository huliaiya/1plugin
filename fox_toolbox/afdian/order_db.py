"""爱发电订单存储。

功能复刻自 astrbot_plugin_afdian/core/order_db.py（作者 Zhalslar），
存储后端适配狐狸插件的 MySQL 连接池：优先写入主库 MySQL 的
`afdian_orders` 表；MySQL 不可用时自动回退到 SQLite 兜底，保证
订单数据不丢失。
"""

import asyncio
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Optional

from astrbot.api import logger


class OrderDB:
    """爱发电订单存储。

    :param sqlite_path: SQLite 兜底数据库路径（MySQL 不可用时使用）
    """

    _MYSQL_DDL = """
        CREATE TABLE IF NOT EXISTS afdian_orders (
            out_trade_no VARCHAR(128) PRIMARY KEY,
            user_id VARCHAR(128) DEFAULT NULL,
            user_name VARCHAR(256) DEFAULT NULL,
            user_private_id VARCHAR(128) DEFAULT NULL,
            plan_id VARCHAR(128) DEFAULT NULL,
            plan_title VARCHAR(256) DEFAULT NULL,
            month INT DEFAULT 0,
            total_amount DOUBLE DEFAULT 0,
            show_amount DOUBLE DEFAULT 0,
            status INT DEFAULT 0,
            product_type INT DEFAULT 0,
            discount DOUBLE DEFAULT 0,
            remark VARCHAR(512) DEFAULT NULL,
            redeem_id VARCHAR(128) DEFAULT NULL,
            sku_detail MEDIUMTEXT,
            address_person VARCHAR(128) DEFAULT NULL,
            address_phone VARCHAR(128) DEFAULT NULL,
            address_address VARCHAR(512) DEFAULT NULL,
            create_time BIGINT DEFAULT 0,
            KEY idx_user_id (user_id),
            KEY idx_create_time (create_time),
            KEY idx_remark (remark(191))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """

    _SQLITE_DDL = """
        CREATE TABLE IF NOT EXISTS afdian_orders (
            out_trade_no TEXT PRIMARY KEY,
            user_id TEXT,
            user_name TEXT,
            user_private_id TEXT,
            plan_id TEXT,
            plan_title TEXT,
            month INTEGER,
            total_amount REAL,
            show_amount REAL,
            status INTEGER,
            product_type INTEGER,
            discount REAL,
            remark TEXT,
            redeem_id TEXT,
            sku_detail TEXT,
            address_person TEXT,
            address_phone TEXT,
            address_address TEXT,
            create_time INTEGER
        )
    """

    def __init__(self, sqlite_path: Optional[str | Path] = None):
        self._pool = None  # aiomysql.Pool
        self._sqlite_path = str(sqlite_path) if sqlite_path else None
        self._mysql_ready = False
        if self._sqlite_path:
            Path(self._sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()

    @property
    def using_mysql(self) -> bool:
        return self._mysql_ready

    # ---- 初始化 ----

    def _init_sqlite(self):
        with sqlite3.connect(self._sqlite_path) as conn:
            conn.execute(self._SQLITE_DDL)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_id ON afdian_orders(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_create_time ON afdian_orders(create_time)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_remark ON afdian_orders(remark)"
            )
            conn.commit()

    def _pool_is_closed(self) -> bool:
        """检测 aiomysql 连接池是否已被关闭。"""
        if not self._pool:
            return True
        # aiomysql.Pool 关闭后 _closing/_closed 为 True
        if getattr(self._pool, "_closing", False) or getattr(self._pool, "_closed", False):
            return True
        return False

    async def bind_mysql_pool(self, pool) -> bool:
        """绑定主插件的 MySQL 连接池，并确保 afdian_orders 表存在。"""
        if pool is None:
            return False
        if getattr(pool, "_closing", False) or getattr(pool, "_closed", False):
            logger.warning("[Afdian] MySQL 连接池已关闭，回退 SQLite 存储")
            return False
        self._pool = pool
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(self._MYSQL_DDL)
                    await conn.commit()
            self._mysql_ready = True
            logger.info("[Afdian] 订单存储已绑定 MySQL 连接池（afdian_orders 表）")
            return True
        except Exception as e:
            self._mysql_ready = False
            logger.warning(
                f"[Afdian] 绑定 MySQL 连接池失败，回退 SQLite 存储: {e}"
            )
            return False

    def _degrade_to_sqlite(self, reason: str) -> None:
        """MySQL 保存失败时永久降级到 SQLite，避免后续每次保存都重复尝试已失效的池。"""
        if not self._mysql_ready:
            return
        self._mysql_ready = False
        self._pool = None
        logger.warning(f"[Afdian] MySQL 保存订单失败，永久降级 SQLite 存储: {reason}")

    # ---- 写入 ----

    async def save_order(self, order) -> None:
        if self._mysql_ready and self._pool:
            await self._save_mysql(order)
        elif self._sqlite_path:
            await asyncio.to_thread(self._save_sqlite, order)
        else:
            logger.error("[Afdian] 无可用存储后端，订单未保存")

    async def save_order_if_new(self, order) -> bool:
        """原子地保存订单，仅当订单原本不存在时返回 True。

        使用 INSERT IGNORE / INSERT OR IGNORE 避免并发下"先查再存"
        的 TOCTOU 竞态（Webhook 与轮询可能同时处理同一订单）。
        """
        if self._mysql_ready and self._pool:
            return await self._save_mysql_if_new(order)
        if self._sqlite_path:
            return await asyncio.to_thread(self._save_sqlite_if_new, order)
        return False

    async def _save_mysql_if_new(self, order) -> bool:
        fields = self._build_fields(order)
        sql = """
            INSERT IGNORE INTO afdian_orders (
                out_trade_no, user_id, user_name, user_private_id, plan_id,
                plan_title, month, total_amount, show_amount, status,
                product_type, discount, remark, redeem_id, sku_detail,
                address_person, address_phone, address_address, create_time
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, tuple(fields.values()))
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            self._degrade_to_sqlite(str(e))
            if self._sqlite_path:
                return await asyncio.to_thread(self._save_sqlite_if_new, order)
            return False

    def _save_sqlite_if_new(self, order) -> bool:
        fields = self._build_fields(order)
        columns = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        with sqlite3.connect(self._sqlite_path) as conn:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO afdian_orders "
                f"({columns}) VALUES ({placeholders})",
                tuple(fields.values()),
            )
            conn.commit()
            return cur.rowcount > 0

    async def _save_mysql(self, order) -> None:
        fields = self._build_fields(order)
        sql = """
            REPLACE INTO afdian_orders (
                out_trade_no, user_id, user_name, user_private_id, plan_id,
                plan_title, month, total_amount, show_amount, status,
                product_type, discount, remark, redeem_id, sku_detail,
                address_person, address_phone, address_address, create_time
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, tuple(fields.values()))
                    await conn.commit()
        except Exception as e:
            self._degrade_to_sqlite(str(e))
            if self._sqlite_path:
                await asyncio.to_thread(self._save_sqlite, order)

    def _save_sqlite(self, order) -> None:
        fields = self._build_fields(order)
        columns = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        with sqlite3.connect(self._sqlite_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO afdian_orders "
                f"({columns}) VALUES ({placeholders})",
                tuple(fields.values()),
            )
            conn.commit()

    def _build_fields(self, order) -> dict:
        return {
            "out_trade_no": order.get("out_trade_no") or "",
            "user_id": order.get("user_id") or "",
            "user_name": order.get("user_name") or "",
            "user_private_id": order.get("user_private_id") or "",
            "plan_id": order.get("plan_id") or "",
            "plan_title": order.get("plan_title") or "",
            "month": order.get("month") or 0,
            "total_amount": self._safe_float(order.get("total_amount")),
            "show_amount": self._safe_float(order.get("show_amount")),
            "status": order.get("status") or 0,
            "product_type": order.get("product_type") or 0,
            "discount": self._safe_float(order.get("discount")),
            "remark": order.get("remark") or "",
            "redeem_id": order.get("redeem_id") or "",
            "sku_detail": json.dumps(order.get("sku_detail") or [], ensure_ascii=False),
            "address_person": order.get("address_person") or "",
            "address_phone": order.get("address_phone") or "",
            "address_address": order.get("address_address") or "",
            "create_time": int(order.get("create_time") or 0),
        }

    # ---- 查询 ----

    async def get_all_orders(self) -> list:
        if self._mysql_ready and self._pool and not self._pool_is_closed():
            return await self._query_mysql("SELECT * FROM afdian_orders ORDER BY create_time DESC")
        if self._sqlite_path:
            return await asyncio.to_thread(self._query_sqlite, "SELECT * FROM afdian_orders ORDER BY create_time DESC")
        return []

    async def get_order_by_id(self, out_trade_no: str):
        if self._mysql_ready and self._pool and not self._pool_is_closed():
            rows = await self._query_mysql(
                "SELECT * FROM afdian_orders WHERE out_trade_no = %s",
                (out_trade_no,),
            )
            return rows[0] if rows else None
        if self._sqlite_path:
            rows = await asyncio.to_thread(
                self._query_sqlite,
                "SELECT * FROM afdian_orders WHERE out_trade_no = ?",
                (out_trade_no,),
            )
            return rows[0] if rows else None
        return None

    async def get_orders_by_user(self, user_id: str) -> list:
        if self._mysql_ready and self._pool and not self._pool_is_closed():
            return await self._query_mysql(
                "SELECT * FROM afdian_orders WHERE user_id = %s ORDER BY create_time DESC",
                (user_id,),
            )
        if self._sqlite_path:
            return await asyncio.to_thread(
                self._query_sqlite,
                "SELECT * FROM afdian_orders WHERE user_id = ? ORDER BY create_time DESC",
                (user_id,),
            )
        return []

    async def get_orders_by_status(self, status: int) -> list:
        if self._mysql_ready and self._pool and not self._pool_is_closed():
            return await self._query_mysql(
                "SELECT * FROM afdian_orders WHERE status = %s ORDER BY create_time DESC",
                (status,),
            )
        if self._sqlite_path:
            return await asyncio.to_thread(
                self._query_sqlite,
                "SELECT * FROM afdian_orders WHERE status = ? ORDER BY create_time DESC",
                (status,),
            )
        return []

    async def _query_mysql(self, sql: str, params: tuple = ()) -> list:
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    rows = await cur.fetchall()
                    columns = [d[0] for d in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            self._degrade_to_sqlite(str(e))
            return []

    def _query_sqlite(self, sql: str, params: tuple = ()) -> list:
        with sqlite3.connect(self._sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _safe_float(value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0