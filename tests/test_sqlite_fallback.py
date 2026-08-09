"""SQLite 兜底存储测试 - 本地文件后端 + MySQL 降级/恢复补写"""

import asyncio
import time
import uuid

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database
from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord, QueryFilter
from astrbot_plugin_fox_toolbox.fox_toolbox.sqlite_store import SQLiteStore


def _make_record(**overrides) -> MessageRecord:
    _uid = uuid.uuid4().hex[:8]
    defaults = dict(
        platform="telegram",
        message_id=f"msg_{_uid}",
        session_id="sess_001",
        group_id="grp_001",
        channel_id=None,
        sender_id="user_001",
        sender_name="Alice",
        message_type="group",
        message_str=f"Hello fallback {_uid}",
        message_chain=None,
        raw_message=None,
        reply_to_id=None,
        timestamp=time.time_ns() // 1_000_000,
    )
    defaults.update(overrides)
    return MessageRecord(**defaults)


class TestSQLiteStore:
    @pytest.mark.asyncio
    async def test_save_and_query_roundtrip(self, tmp_path):
        store = SQLiteStore(tmp_path / "fallback.db")
        assert await store.ping() is True

        rec = _make_record()
        rid = await store.save_message(rec)
        assert rid is not None and rid > 0

        qf = QueryFilter()
        rows = await store.query_messages(qf)
        assert len(rows) == 1
        assert rows[0].message_str == rec.message_str
        assert rows[0].id == rid

        # 幂等：相同 content_hash 不重复插入
        rid2 = await store.save_message(_make_record(
            content_hash=rec.content_hash, message_str=rec.message_str,
            timestamp=rec.timestamp,
        ))
        assert rid2 == -1
        assert await store.count_messages(qf) == 1

    @pytest.mark.asyncio
    async def test_batch_save_backfills_ids(self, tmp_path):
        store = SQLiteStore(tmp_path / "fallback.db")
        records = [_make_record() for _ in range(5)]
        saved, skipped = await store.save_messages_batch(records)
        assert saved == 5 and skipped == 0
        for r in records:
            assert r.id is not None and r.id > 0

    @pytest.mark.asyncio
    async def test_unsynced_lifecycle(self, tmp_path):
        store = SQLiteStore(tmp_path / "fallback.db")
        records = [_make_record() for _ in range(3)]
        await store.save_messages_batch(records)
        assert await store.get_unsynced_count() == 3

        ids = await store.get_unsynced_ids(2)
        assert len(ids) == 2
        got = await store.get_records_by_ids(ids)
        assert {r.id for r in got} == set(ids)

        await store.mark_synced(ids)
        assert await store.get_unsynced_count() == 1

    @pytest.mark.asyncio
    async def test_cleanup_synced_by_retention(self, tmp_path):
        store = SQLiteStore(tmp_path / "fallback.db")
        old_created = int(time.time() * 1000) - 100 * 86400 * 1000
        records = [
            _make_record(created_at=old_created),  # 已同步的旧消息
            _make_record(),                        # 未同步的新消息
        ]
        await store.save_messages_batch(records)
        # 模拟第一条已同步
        ids = await store.get_unsynced_ids(10)
        await store.mark_synced([records[0].id])
        assert await store.get_unsynced_count() == 1

        deleted = await store.cleanup_synced(30)
        assert deleted == 1
        assert await store.count_messages(QueryFilter()) == 1

    @pytest.mark.asyncio
    async def test_cleanup_skips_unsynced(self, tmp_path):
        """清理只删除已同步记录，未同步消息保留待补写（防数据丢失）。"""
        store = SQLiteStore(tmp_path / "fallback.db")
        old_ts = int(time.time() * 1000) - 100 * 86400 * 1000
        await store.save_messages_batch([
            _make_record(timestamp=old_ts),   # 旧未同步
            _make_record(),                      # 新未同步
        ])
        ids = await store.get_unsynced_ids(10)
        assert len(ids) == 2

        # 均未同步：即使旧消息也不可删
        deleted, _ = await store.cleanup_by_age(30)
        assert deleted == 0

        # 标记旧消息同步后，它可被清理，未同步的新消息仍保留
        await store.mark_synced([ids[0]])
        deleted, _ = await store.cleanup_by_age(30)
        assert deleted == 1
        assert await store.count_messages(QueryFilter()) == 1
        assert await store.get_unsynced_count() == 1

    @pytest.mark.asyncio
    async def test_stats_and_ranking(self, tmp_path):
        store = SQLiteStore(tmp_path / "fallback.db")
        now = time.time_ns() // 1_000_000
        await store.save_messages_batch([
            _make_record(platform="telegram", sender_id="u1", group_id="g1", timestamp=now - 1000),
            _make_record(platform="telegram", sender_id="u2", group_id="g1", timestamp=now - 900),
            _make_record(platform="telegram", sender_id="u1", group_id="g2", timestamp=now - 800),
        ])
        stats = await store.get_stats()
        assert stats.total_count == 3
        assert stats.group_message_count == 3

        ranking = await store.get_sender_ranking()
        assert ranking[0]["sender_id"] == "u1"
        assert ranking[0]["count"] == 2

        platforms = await store.get_distinct_platforms()
        assert set(platforms) == {"telegram"}

    @pytest.mark.asyncio
    async def test_media_paths(self, tmp_path):
        store = SQLiteStore(tmp_path / "fallback.db")
        await store.save_messages_batch([
            _make_record(message_chain=json_chain("a.jpg"), timestamp=int(time.time() * 1000) - 5000),
            _make_record(message_chain=json_chain("b.png"), timestamp=int(time.time() * 1000) - 2000),
        ])
        paths = await store.get_media_paths_before(int(time.time() * 1000) - 1000)
        assert "a.jpg" in paths and "b.png" in paths

        over = await store.get_media_paths_over_limit(0)
        assert set(over) == {"a.jpg", "b.png"}

        referenced = await store.get_unreferenced_media_paths(["a.jpg", "b.png", "c.txt"])
        assert referenced == ["c.txt"]


def json_chain(media: str) -> str:
    """构造包含媒体路径的消息链 JSON。"""
    import json
    return json.dumps([{"local_path": media}])


class TestDatabaseDegradedMode:
    @pytest.mark.asyncio
    async def test_init_failure_falls_back_to_sqlite(self, tmp_path, monkeypatch):
        """MySQL 不可用时自动降级 SQLite，保存/查询仍可用。"""
        from astrbot_plugin_fox_toolbox.fox_toolbox import database as db_mod

        async def _fail_create_pool(*a, **k):
            raise ConnectionError("mysql down")

        monkeypatch.setattr(db_mod.aiomysql, "create_pool", _fail_create_pool)
        # 避免污染真实数据目录
        monkeypatch.setattr(
            db_mod,
            "get_astrbot_plugin_data_path",
            lambda: str(tmp_path / "data"),
        )

        db = Database("test_plugin", {"host": "127.0.0.1"})
        await db.init()

        assert db.using_fallback is True
        assert db.ping is not None

        rec = _make_record()
        rid = await db.save_message(rec)
        assert rid is not None and rid > 0
        assert rec.id == rid

        rows = await db.query_messages(QueryFilter())
        assert len(rows) == 1

        stats = await db.get_stats()
        assert stats.total_count == 1

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_backfills_unsynced(self, tmp_path, monkeypatch):
        """MySQL 恢复后自动切回并补写降级期间的消息。"""
        from astrbot_plugin_fox_toolbox.fox_toolbox import database as db_mod
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

        pool_ref = {}
        fail = {"flag": True}

        async def _flaky_create_pool(*a, **k):
            if fail["flag"]:
                raise ConnectionError("mysql down")
            return await db_mod.aiomysql.create_pool(*a, **k)

        monkeypatch.setattr(db_mod.aiomysql, "create_pool", _flaky_create_pool)
        monkeypatch.setattr(
            db_mod,
            "get_astrbot_plugin_data_path",
            lambda: str(tmp_path / "data"),
        )

        db = Database("test_plugin", {"host": "127.0.0.1", "port": 3306})
        await db.init()
        assert db.using_fallback is True

        # 降级期间写入 2 条
        await db.save_message(_make_record())
        await db.save_message(_make_record())

        # 模拟 MySQL 恢复：把 _save_messages_batch_mysql 替换为记录调用
        backfilled = []

        async def _fake_batch_mysql(records):
            backfilled.extend(records)
            return len(records), 0

        monkeypatch.setattr(db, "_save_messages_batch_mysql", _fake_batch_mysql)
        db._mysql_ready = True
        db._degraded = False
        db._pool = object()  # 模拟恢复后已建立 MySQL 连接池

        # 手动触发补写逻辑
        await db._backfill_unsynced()
        assert len(backfilled) == 2

        # 补写后 unsynced 清空
        assert await db.get_unsynced_count() == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_init_failure_without_fallback_raises(self, monkeypatch):
        """关闭兜底时 MySQL 初始化失败应抛异常。"""
        from astrbot_plugin_fox_toolbox.fox_toolbox import database as db_mod

        async def _fail_create_pool(*a, **k):
            raise ConnectionError("mysql down")

        monkeypatch.setattr(db_mod.aiomysql, "create_pool", _fail_create_pool)

        db = Database("test_plugin", {"host": "127.0.0.1"}, fallback_enabled=False)
        with pytest.raises(ConnectionError):
            await db.init()
        assert db.using_fallback is False

    @pytest.mark.asyncio
    async def test_try_reconnect_failure_keeps_degraded(self, tmp_path, monkeypatch):
        """恢复重连仍失败时保持降级状态，不误判为已恢复。"""
        from astrbot_plugin_fox_toolbox.fox_toolbox import database as db_mod
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

        calls = {"n": 0}

        async def _fail_create_pool(*a, **k):
            calls["n"] += 1
            raise ConnectionError("still down")

        monkeypatch.setattr(db_mod.aiomysql, "create_pool", _fail_create_pool)
        monkeypatch.setattr(
            db_mod,
            "get_astrbot_plugin_data_path",
            lambda: str(tmp_path / "data"),
        )

        db = Database("test_plugin", {"host": "127.0.0.1"}, recovery_check_interval=5)
        await db.init()
        assert db.using_fallback is True

        ok = await db._try_reconnect_mysql()
        assert ok is False
        assert db.using_fallback is True
        assert db._mysql_ready is False
        assert db._pool is None
        assert calls["n"] == 2  # init 1 次 + 重连 1 次

        await db.close()

    @pytest.mark.asyncio
    async def test_try_reconnect_success(self, tmp_path, monkeypatch):
        """重连成功后置回就绪状态并建立连接池。"""
        from astrbot_plugin_fox_toolbox.fox_toolbox import database as db_mod
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

        fake_pool = object()
        fail = {"flag": True}

        async def _flaky_create_pool(*a, **k):
            if fail["flag"]:
                raise ConnectionError("down")
            return fake_pool

        monkeypatch.setattr(db_mod.aiomysql, "create_pool", _flaky_create_pool)
        monkeypatch.setattr(
            db_mod,
            "get_astrbot_plugin_data_path",
            lambda: str(tmp_path / "data"),
        )
        # 避免重建池后再跑建表/迁移（无真实 MySQL）
        async def _noop_tables(self):
            return None
        monkeypatch.setattr(Database, "_create_tables", _noop_tables)
        monkeypatch.setattr(Database, "_ensure_schema_version", _noop_tables)
        monkeypatch.setattr(Database, "_cleanup_deprecated_tables", _noop_tables)

        db = Database("test_plugin", {"host": "127.0.0.1"})
        await db.init()
        assert db.using_fallback is True

        fail["flag"] = False
        ok = await db._try_reconnect_mysql()
        assert ok is True
        assert db._pool is fake_pool

        # 调用方（恢复循环）负责复位就绪标志
        db._mysql_ready = True
        db._degraded = False
        assert db.using_fallback is False

        await db.close()
