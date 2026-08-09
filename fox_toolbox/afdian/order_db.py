"""爱发电订单存储。

功能复刻自 astrbot_plugin_afdian/core/order_db.py（作者 Zhalslar），
存储后端适配狐狸插件的 MySQL 连接池：优先写入主库 MySQL 的
`afdian_orders` 表；MySQL 不可用时自动回退到 SQLite 兜底，保证
订单数据不丢失。
"""

import asyncio
import json
import sqlite3
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
        self._pool_provider = None  # async 可调用：返回宿主主库当前连接池
        self._recovery_task: Optional[asyncio.Task] = None
        self._recovery_interval = 30.0
        if self._sqlite_path:
            Path(self._sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()

    # ---- 恢复机制 ----

    def set_pool_provider(self, provider) -> None:
        """注册宿主主库连接池提供者（async 可调用，返回当前 aiomysql.Pool 或 None）。"""
        self._pool_provider = provider

    def start_recovery_loop(self, interval: float = 30.0) -> None:
        """启动周期恢复检测：MySQL 恢复后自动重新绑定并回写 SQLite 积累的订单。"""
        self._recovery_interval = interval
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._recovery_loop())

    def stop_recovery_loop(self) -> None:
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
        self._recovery_task = None

    async def _recovery_loop(self) -> None:
        while True:
            await asyncio.sleep(self._recovery_interval)
            try:
                if self._mysql_ready and not self._pool_is_closed():
                    continue
                if not self._pool_provider:
                    continue
                pool = await self._pool_provider()
                if pool is None:
                    continue
                if await self.bind_mysql_pool(pool):
                    logger.info("[Afdian] MySQL 已恢复，重新绑定订单存储并回写降级期订单")
                    await self._backfill_sqlite_to_mysql()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"[Afdian] 订单存储恢复检测异常: {e}")

    async def _backfill_sqlite_to_mysql(self) -> int:
        """把 SQLite 中积累的订单回写 MySQL（INSERT IGNORE 幂等），返回回写条数。"""
        if not self._mysql_ready:
            return 0
        try:
            orders = await asyncio.to_thread(
                self._query_sqlite, "SELECT * FROM afdian_orders"
            )
        except Exception:
            return 0
        count = 0
        for order in orders:
            try:
                if await self._save_mysql_if_new(order):
                    count += 1
            except Exception as e:
                logger.warning(f"[Afdian] 回写订单到 MySQL 失败: {e}")
                break
        return count

    # ---- 初始化 ----

    def _sqlite_connect(self) -> sqlite3.Connection:
        """建立带 WAL 与忙等待超时的 SQLite 连接，降低并发写锁失败概率。"""
        conn = sqlite3.connect(self._sqlite_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_sqlite(self):
        with self._sqlite_connect() as conn:
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
        try:
            with self._sqlite_connect() as conn:
                cur = conn.execute(
                    f"INSERT OR IGNORE INTO afdian_orders "
                    f"({columns}) VALUES ({placeholders})",
                    tuple(fields.values()),
                )
                conn.commit()
                return cur.rowcount > 0
        except sqlite3.OperationalError as e:
            logger.warning(f"[Afdian] SQLite 写入订单失败（存储已锁定或损坏）: {e}")
            return False

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
            return await self._query_mysql(
                "SELECT * FROM afdian_orders ORDER BY create_time DESC",
                sqlite_sql="SELECT * FROM afdian_orders ORDER BY create_time DESC",
            )
        if self._sqlite_path:
            return await asyncio.to_thread(self._query_sqlite, "SELECT * FROM afdian_orders ORDER BY create_time DESC")
        return []

    async def _query_mysql(self, sql: str, params: tuple = (), sqlite_sql: str = None) -> list:
        """执行 MySQL 查询；故障时降级到 SQLite 兜底查询（需提供 SQLite 版 SQL）。

        :param sql: MySQL SQL（%s 占位符）
        :param params: 查询参数
        :param sqlite_sql: SQLite 版 SQL（? 占位符），为空时仅记录降级并返回 []
        """
        if not self._pool:
            if sqlite_sql and self._sqlite_path:
                return await asyncio.to_thread(self._query_sqlite, sqlite_sql, params)
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
            if sqlite_sql and self._sqlite_path:
                return await asyncio.to_thread(self._query_sqlite, sqlite_sql, params)
            return []

    def _query_sqlite(self, sql: str, params: tuple = ()) -> list:
        try:
            with self._sqlite_connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            logger.warning(f"[Afdian] SQLite 查询订单失败: {e}")
            return []

    @staticmethod
    def _safe_float(value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0