"""redis_cache.py 单元测试 - 使用 mock 模拟 redis.asyncio"""

import asyncio
import sys
import time
import types

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.redis_cache import (
    RedisCache,
)


class _FakeRedisClient:
    """内存版 fake redis.asyncio client"""

    def __init__(self):
        self._data = {}

    async def ping(self):
        return True

    async def aclose(self):
        pass

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, value, ex=None):
        self._data[key] = value
        return True

    async def lpush(self, key, value):
        self._data.setdefault(key, [])
        self._data[key].insert(0, value)
        return len(self._data[key])

    async def ltrim(self, key, start, stop):
        items = self._data.get(key, [])
        self._data[key] = items[start : stop + 1]
        return True

    async def lrange(self, key, start, stop):
        items = self._data.get(key, [])
        if start < 0 and stop < 0:
            return items[start : stop + 1] if stop != -1 else items[start:]
        return items[start : stop + 1]

    async def rpop(self, key):
        items = self._data.get(key, [])
        if not items:
            return None
        return items.pop()

    async def delete(self, key):
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    async def info(self, section=None):
        if section == "memory":
            return {"used_memory_human": "1.2M"}
        return {"redis_version": "7.2.4"}

    async def dbsize(self):
        return 42


class _FakePingFailClient(_FakeRedisClient):
    async def ping(self):
        raise ConnectionError("connection refused")


class _FakeVersionlessClient(_FakeRedisClient):
    async def info(self, section=None):
        raise RuntimeError("no info")


def _install_fake_aioredis(client_factory=None):
    """注入 fake redis.asyncio 模块并标记依赖可用"""
    fake = types.ModuleType("redis")
    fake_asyncio = types.ModuleType("redis.asyncio")
    sys.modules["redis"] = fake
    sys.modules["redis.asyncio"] = fake_asyncio
    fake.asyncio = fake_asyncio
    fake_asyncio.from_url = lambda *args, **kwargs: client_factory() if client_factory else _FakeRedisClient()
    import astrbot_plugin_fox_toolbox.fox_toolbox.redis_cache as rc

    rc._REDIS_AVAILABLE = True
    rc.aioredis = fake_asyncio
    return rc


def _uninstall_fake_aioredis():
    sys.modules.pop("redis", None)
    sys.modules.pop("redis.asyncio", None)
    import astrbot_plugin_fox_toolbox.fox_toolbox.redis_cache as rc

    rc._REDIS_AVAILABLE = False
    rc.aioredis = None


class TestRedisCacheConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(host="127.0.0.1", port=6379, ttl=60)
            ok = await cache.connect()
            assert ok is True
            assert cache.available is True
            await cache.close()
            assert cache.available is False
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_connect_failure_degrades_gracefully(self):
        _install_fake_aioredis(client_factory=_FakePingFailClient)
        try:
            cache = RedisCache(host="127.0.0.1", port=6379, ttl=60)
            ok = await cache.connect()
            assert ok is False
            assert cache.available is False
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_dependency_missing_disables(self):
        cache = RedisCache(host="127.0.0.1", port=6379)
        # 依赖不可用
        import astrbot_plugin_fox_toolbox.fox_toolbox.redis_cache as rc

        rc._REDIS_AVAILABLE = False
        ok = await cache.connect()
        assert ok is False
        assert cache.available is False


class TestRedisCacheStatus:
    @pytest.mark.asyncio
    async def test_status_includes_server_version(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(host="127.0.0.1", port=6379, db=0, ttl=60)
            ok = await cache.connect()
            assert ok is True
            status = await cache.status()
            assert status["version"] == "7.2.4"
            assert status["key_count"] == 42
            assert status["memory_human"] == "1.2M"
            assert status["host"] == "127.0.0.1"
            assert status["db"] == 0
            await cache.close()
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_status_version_none_when_info_fails(self):
        _install_fake_aioredis(client_factory=_FakeVersionlessClient)
        try:
            cache = RedisCache(host="127.0.0.1", port=6379, ttl=60)
            ok = await cache.connect()
            assert ok is True
            status = await cache.status()
            assert status["version"] is None
            await cache.close()
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_status_version_none_when_disconnected(self):
        _install_fake_aioredis(client_factory=_FakePingFailClient)
        try:
            cache = RedisCache(host="127.0.0.1", port=6379, ttl=60)
            ok = await cache.connect()
            assert ok is False
            status = await cache.status()
            assert status["available"] is False
            assert status["version"] is None
        finally:
            _uninstall_fake_aioredis()


class TestRedisCacheStats:
    @pytest.mark.asyncio
    async def test_stats_roundtrip(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            assert await cache.get_stats() is None
            stats = {"total_count": 100, "platform_stats": {"telegram": 60}}
            await cache.set_stats(stats)
            assert await cache.get_stats() == stats
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_stats_ops_noop_when_disabled(self):
        cache = RedisCache(ttl=60)  # 未连接
        assert cache.available is False
        assert await cache.get_stats() is None
        await cache.set_stats({"total_count": 1})  # 不应抛异常
        assert await cache.apply_stats_deltas([{"count": 1}]) is False


class TestRedisCacheApplyStatsDeltas:
    @pytest.mark.asyncio
    async def test_delta_updates_and_slides_ttl(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            await cache.set_stats(
                {
                    "total_count": 100,
                    "group_message_count": 70,
                    "private_message_count": 20,
                    "channel_message_count": 10,
                    "platform_stats": {"telegram": 60, "qq": 40},
                    "oldest_timestamp": 1000,
                    "newest_timestamp": 9000,
                    "first_record_time": 1000,
                    "last_record_time": 9000,
                }
            )
            ok = await cache.apply_stats_deltas(
                [
                    {
                        "count": 1,
                        "platform": "telegram",
                        "bucket": "group",
                        "timestamp": 9500,
                        "created_at": 9500,
                    },
                    {
                        "count": 1,
                        "platform": "qq",
                        "bucket": "private",
                        "timestamp": 9501,
                        "created_at": 9501,
                    },
                ]
            )
            assert ok is True
            stats = await cache.get_stats()
            assert stats["total_count"] == 102
            assert stats["group_message_count"] == 71
            assert stats["private_message_count"] == 21
            assert stats["channel_message_count"] == 10
            assert stats["platform_stats"] == {"telegram": 61, "qq": 41}
            assert stats["newest_timestamp"] == 9501
            assert stats["last_record_time"] == 9501
            assert stats["oldest_timestamp"] == 1000
            assert stats["first_record_time"] == 1000
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_apply_returns_false_when_cache_missing(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            assert await cache.get_stats() is None
            assert await cache.apply_stats_deltas([{"count": 1, "platform": "qq"}]) is False
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_apply_noop_when_disabled(self):
        cache = RedisCache(ttl=60)  # 未连接
        assert await cache.apply_stats_deltas([{"count": 1}]) is False


class TestRedisReconnectLoop:
    """运行中断连后自动重连，连续失败达上限后停止。"""

    @pytest.mark.asyncio
    async def test_reconnects_after_disconnect(self, monkeypatch):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60, max_retries=5)
            await cache.connect()
            assert cache.available is True
            assert cache._client is not None

            # 缩短检测间隔并启动重连循环
            await cache.start_reconnect_loop(interval=0.05)
            assert cache._reconnect_interval == 0.05

            # 模拟运行中断连：清空 client 并强制 available=False
            cache._client = None
            cache._available = False

            # 等循环重连（from_url 恒成功）
            await asyncio.sleep(0.2)
            assert cache.available is True
            assert cache._client is not None

            await cache.close()
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_reconnect_loop_stops_after_max_retries(self, monkeypatch):
        _install_fake_aioredis(client_factory=_FakePingFailClient)
        try:
            cache = RedisCache(ttl=60, max_retries=3)
            await cache.connect()
            assert cache.available is False

            await cache.start_reconnect_loop(interval=0.05)

            # 初次连接失败（_client=None），循环重试；3 次失败后停止
            await asyncio.sleep(0.5)
            assert cache._reconnect_task is not None
            assert cache._reconnect_task.done()
            assert cache.available is False

            await cache.close()
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_reconnect_loop_resets_after_recovery(self, monkeypatch):
        """循环检测到断开后自动重连成功并继续运行。"""
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60, max_retries=3)
            await cache.connect()
            await cache.start_reconnect_loop(interval=0.05)

            # 模拟断连后恢复：先断开，再让 from_url 继续成功
            cache._client = None
            cache._available = False
            await asyncio.sleep(0.2)

            assert cache.available is True
            assert not cache._reconnect_task.done()  # 成功后循环继续

            await cache.close()
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_close_stops_reconnect_loop(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60, max_retries=3)
            await cache.connect()
            await cache.start_reconnect_loop(interval=0.05)
            assert cache._reconnect_task is not None
            await cache.close()
            assert cache._reconnect_task is None
            assert cache.available is False
        finally:
            _uninstall_fake_aioredis()


class TestRecordCachePayload:
    def test_payload_shape(self):
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database
        from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord

        record = MessageRecord(
            id=7,
            platform="telegram",
            sender_id="u1",
            sender_name="Alice",
            message_type="group",
            message_str="hello",
            timestamp=123456,
            created_at=123457,
        )
        payload = Database._record_cache_payload(record)
        assert payload["id"] == 7
        assert payload["platform"] == "telegram"
        assert payload["message_str"] == "hello"
        assert payload["timestamp"] == 123456
        assert payload["created_at"] == 123457

    @pytest.mark.asyncio
    async def test_cache_hooks_noop_without_redis(self):
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database
        from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord

        db = Database("test", {})  # redis_cache=None
        record = MessageRecord(platform="telegram", message_str="hi")
        # 未配置 Redis 时应无副作用地返回
        await db._cache_recent_message(record)
        await db._cache_recent_messages([record])
        assert db.redis_cache is None

    @pytest.mark.asyncio
    async def test_cache_hooks_degrade_on_failure(self):
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database
        from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord

        db = Database("test", {})
        # 挂一个未连接(available=False)的 RedisCache
        db.redis_cache = RedisCache(ttl=60)
        record = MessageRecord(platform="telegram", message_str="hi")
        await db._cache_recent_message(record)
        await db._cache_recent_messages([record])
        assert db.redis_cache.available is False


class TestRecentMessageWindow:
    """最近消息缓存：近 30 分钟窗口裁剪 + 批量重建。"""

    @pytest.mark.asyncio
    async def test_push_trims_out_of_window(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            now = int(time.time() * 1000)
            # 先推旧消息（40 分钟前，超出 30 分钟窗口），再推新消息（窗口内）
            await cache.push_recent_message(
                {"id": 2, "message_str": "stale", "created_at": now - 40 * 60 * 1000}
            )
            await cache.push_recent_message(
                {"id": 1, "message_str": "fresh", "created_at": now}
            )
            recent = await cache.get_recent_messages(limit=50)
            assert len(recent) == 1
            assert recent[0]["id"] == 1
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_push_keeps_within_window(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            now = int(time.time() * 1000)
            # 按时间顺序推送三条，均在 30 分钟内
            for i in range(3):
                await cache.push_recent_message(
                    {
                        "id": i,
                        "message_str": f"m{i}",
                        "created_at": now - (2 - i) * 60 * 1000,
                    }
                )
            recent = await cache.get_recent_messages(limit=50)
            # 3 条都在 30 分钟窗口内
            assert len(recent) == 3
            # 最新的在前面
            assert recent[0]["id"] == 2
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_rebuild_filters_by_window(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            now = int(time.time() * 1000)
            records = [
                {"id": 1, "created_at": now},
                {"id": 2, "created_at": now - 29 * 60 * 1000},
                {"id": 3, "created_at": now - 45 * 60 * 1000},
            ]
            await cache.rebuild_recent_messages(records)
            recent = await cache.get_recent_messages(limit=50)
            ids = [r["id"] for r in recent]
            # 窗口内两条保留，且最新在前
            assert ids == [1, 2]
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_rebuild_empty_clears(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            now = int(time.time() * 1000)
            await cache.push_recent_message({"id": 1, "created_at": now})
            await cache.rebuild_recent_messages([])
            assert await cache.get_recent_messages() == []
        finally:
            _uninstall_fake_aioredis()


class TestRecentCacheRefreshLoop:
    """Database 层周期缓存刷新：重建最近消息缓存并强制对齐统计缓存。"""

    @pytest.mark.asyncio
    async def test_refresh_rebuilds_recent_and_stats(self):
        _install_fake_aioredis()
        try:
            from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

            cache = RedisCache(ttl=60)
            await cache.connect()
            db = Database("test", {}, redis_cache=cache, recent_window_seconds=1800)
            now = int(time.time() * 1000)

            # 记录 query_messages 接收到的过滤器
            captured = {}

            async def fake_query(qf):
                captured["filter"] = qf
                return [
                    type(
                        "R",
                        (),
                        {
                            "id": 1,
                            "platform": "telegram",
                            "sender_id": "u",
                            "sender_name": "A",
                            "message_type": "group",
                            "message_str": "hi",
                            "timestamp": now,
                            "created_at": now,
                        },
                    )(),
                ]

            db.query_messages = fake_query

            # 强制重建统计缓存（验证调用）
            stats_updated = []

            async def fake_stats_refresh():
                stats_updated.append(1)
                return None

            db.get_stats_refresh = fake_stats_refresh
            await db._refresh_redis_caches()
            recent = await cache.get_recent_messages(limit=10)
            assert len(recent) == 1
            assert recent[0]["id"] == 1
            # 统计缓存确实被强制刷新
            assert len(stats_updated) == 1
            # 查询过滤器携带了正确的时间窗口
            qf = captured.get("filter")
            assert qf is not None
            assert qf.start_time == now - 1800 * 1000
            assert qf.end_time == now
            assert qf.limit == 200
            assert qf.order == "desc"
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_refresh_noop_without_redis(self):
        from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

        db = Database("test", {})  # redis_cache=None
        await db._refresh_redis_caches()  # 不应抛异常

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_cache_refresh_loop_stops_on_close(self):
        _install_fake_aioredis()
        try:
            from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

            cache = RedisCache(ttl=60)
            await cache.connect()
            db = Database("test", {}, redis_cache=cache, cache_refresh_interval=60)
            await db._start_cache_refresh_loop()
            assert db._cache_refresh_task is not None
            assert not db._cache_refresh_task.done()
            await db.close()
            assert db._cache_refresh_task is None
        finally:
            _uninstall_fake_aioredis()

