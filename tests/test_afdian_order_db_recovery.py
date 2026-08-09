"""爱发电订单存储 MySQL 恢复机制测试

覆盖以下能力：
1. SQLite 写入具备 WAL / busy_timeout，写锁异常被捕获而非上抛
2. 降级期间订单正确落在 SQLite
3. 恢复循环：MySQL 恢复后自动重新绑定并回写 SQLite 积累的订单
4. 回写为幂等（INSERT IGNORE），重复回写不产生重复数据
5. 恢复循环可正常停止
"""

import asyncio
import sqlite3
from types import SimpleNamespace

from astrbot_plugin_fox_toolbox.fox_toolbox.afdian.order_db import OrderDB


class _FakePool:
    """极简 aiomysql.Pool 替身：acquire 提供游标执行 INSERT IGNORE 语义。"""

    def __init__(self):
        self._closing = False
        self._closed = False
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS afdian_orders ("
            "out_trade_no TEXT PRIMARY KEY, user_id TEXT, user_name TEXT,"
            "user_private_id TEXT, plan_id TEXT, plan_title TEXT, month INTEGER,"
            "total_amount REAL, show_amount REAL, status INTEGER, product_type INTEGER,"
            "discount REAL, remark TEXT, redeem_id TEXT, sku_detail TEXT,"
            "address_person TEXT, address_phone TEXT, address_address TEXT,"
            "create_time INTEGER)"
        )
        self._conn.commit()

    def acquire(self):
        return _FakeConn(self)

    async def close(self):
        self._closing = True
        self._closed = True
        self._conn.close()


class _FakeConn:
    """aiomysql 连接替身：async with 上下文。"""

    def __init__(self, pool):
        self._pool = pool

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def cursor(self):
        return _FakeCursor(self._pool)

    async def commit(self):
        self._pool._conn.commit()


class _FakeCursor:
    """aiomysql 游标替身：async with 上下文，execute 为 INSERT IGNORE 语义。"""

    def __init__(self, pool):
        self._pool = pool
        self.rowcount = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        if "ENGINE=InnoDB" in sql:
            # MySQL 专属 DDL 在 SQLite 模拟库中静默通过（表已预建）
            self.rowcount = 0
            return self
        sql = sql.replace("%s", "?")
        sql = sql.replace("INSERT IGNORE INTO", "INSERT OR IGNORE INTO")
        try:
            cur = self._pool._conn.execute(sql, params or ())
            self.rowcount = cur.rowcount
        except sqlite3.IntegrityError:
            self.rowcount = 0
        except sqlite3.OperationalError as e:
            # 降级测试期望：MySQL 不可用时 bind 应失败回退
            raise
        return self

    async def fetchall(self):
        cur = self._pool._conn.execute("SELECT * FROM afdian_orders")
        return cur.fetchall()

    @property
    def description(self):
        return [d[0] for d in self._pool._conn.execute("SELECT * FROM afdian_orders").description]


class _ClosedPool(_FakePool):
    """已关闭的连接池：模拟 MySQL 故障状态。"""

    def __init__(self):
        super().__init__()
        self._closing = True
        self._closed = True


def _order(out_trade_no, user_id="u1", amount=6.0):
    return {
        "out_trade_no": out_trade_no,
        "user_id": user_id,
        "user_name": "tester",
        "user_private_id": "",
        "plan_id": "plan_1",
        "plan_title": "支持",
        "month": 1,
        "total_amount": amount,
        "show_amount": amount,
        "status": 1,
        "product_type": 1,
        "discount": 0.0,
        "remark": "",
        "redeem_id": "",
        "sku_detail": [],
        "address_person": "",
        "address_phone": "",
        "address_address": "",
        "create_time": 1700000000,
    }


async def _make_degraded_db(tmp_path):
    """构造一个已降级到 SQLite 的 OrderDB（绑定已关闭的池）。"""
    db = OrderDB(tmp_path / "orders.db")
    await db.bind_mysql_pool(_ClosedPool())
    await db.save_order_if_new(_order("ORD_DEGRADED_1"))
    await db.save_order_if_new(_order("ORD_DEGRADED_2"))
    assert db._mysql_ready is False
    return db


async def test_sqlite_write_after_unsync_raises_no_exception(tmp_path):
    """降级后写入 SQLite 正常返回，不抛异常。"""
    db = OrderDB(tmp_path / "orders.db")
    db._pool = None
    db._mysql_ready = False
    ok = await db.save_order_if_new(_order("ORD_1"))
    assert ok is True
    rows = db._query_sqlite("SELECT * FROM afdian_orders")
    assert len(rows) == 1
    assert rows[0]["out_trade_no"] == "ORD_1"


async def test_recovery_loop_rebinds_and_backfills(tmp_path):
    """MySQL 恢复后：重新绑定 + SQLite 积累订单回写。"""
    db = await _make_degraded_db(tmp_path)
    fake_pool = _FakePool()
    async def _provider():
        return fake_pool

    db.set_pool_provider(_provider)
    db.start_recovery_loop(interval=0.05)
    await asyncio.sleep(0.3)
    db.stop_recovery_loop()

    assert db._mysql_ready is True
    rows = db._query_sqlite("SELECT * FROM afdian_orders")
    assert len(rows) == 2
    # 回写后 SQLite 数据仍在，MySQL 侧已含全部订单
    from fox_toolbox.afdian.afdian_api import json as _json

    cur = fake_pool._conn.execute("SELECT out_trade_no FROM afdian_orders")
    mysql_rows = [r[0] for r in cur.fetchall()]
    assert sorted(mysql_rows) == ["ORD_DEGRADED_1", "ORD_DEGRADED_2"]


async def test_backfill_is_idempotent(tmp_path):
    """回写幂等：重复回写不产生重复订单。"""
    db = await _make_degraded_db(tmp_path)
    fake_pool = _FakePool()

    async def _provider():
        return fake_pool

    db.set_pool_provider(_provider)
    await db.bind_mysql_pool(fake_pool)
    first = await db._backfill_sqlite_to_mysql()
    second = await db._backfill_sqlite_to_mysql()
    assert first == 2
    assert second == 0
    cur = fake_pool._conn.execute("SELECT COUNT(*) FROM afdian_orders")
    assert cur.fetchone()[0] == 2


async def test_recovery_loop_skips_when_mysql_already_ready(tmp_path):
    """MySQL 正常时恢复循环不重绑。"""
    db = OrderDB(tmp_path / "orders.db")
    fake_pool = _FakePool()
    await db.bind_mysql_pool(fake_pool)
    calls = []

    async def _provider():
        calls.append(1)
        return fake_pool

    db.set_pool_provider(_provider)
    db.start_recovery_loop(interval=0.02)
    await asyncio.sleep(0.1)
    db.stop_recovery_loop()
    assert db._mysql_ready is True
    assert calls == []


async def test_recovery_loop_keeps_degraded_when_pool_still_down(tmp_path):
    """MySQL 未恢复时保持降级，不异常退出。"""
    db = await _make_degraded_db(tmp_path)

    async def _provider():
        return None

    db.set_pool_provider(_provider)
    db.start_recovery_loop(interval=0.02)
    await asyncio.sleep(0.1)
    db.stop_recovery_loop()
    assert db._mysql_ready is False


async def test_sqlite_operational_error_is_caught(tmp_path):
    """SQLite 写入锁定/路径异常被捕获，不向调用方传播。"""
    db = OrderDB(tmp_path / "orders.db")
    # 指向不存在的父目录，写入时触发 OperationalError
    db._sqlite_path = str(tmp_path / "no_such_dir" / "orders.db")
    ok = await db.save_order_if_new(_order("ORD_X"))
    assert ok is False


async def test_stop_recovery_loop_cancels_task(tmp_path):
    """stop_recovery_loop 后任务被取消。"""
    db = OrderDB(tmp_path / "orders.db")
    db.set_pool_provider(lambda: None)
    db.start_recovery_loop(interval=0.01)
    task = db._recovery_task
    assert task is not None and not task.done()
    db.stop_recovery_loop()
    assert db._recovery_task is None
