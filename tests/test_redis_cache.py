"""redis_cache.py 单元测试 - 使用 mock 模拟 redis.asyncio"""

import sys
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
        return items[start : stop + 1]


class _FakePingFailClient(_FakeRedisClient):
    async def ping(self):
        raise ConnectionError("connection refused")


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


class TestRedisCacheRecentMessages:
    @pytest.mark.asyncio
    async def test_push_and_read(self):
        _install_fake_aioredis()
        try:
            cache = RedisCache(ttl=60)
            await cache.connect()
            await cache.push_recent_message({"id": 1, "platform": "telegram"})
            await cache.push_recent_message({"id": 2, "platform": "qq"})
            items = await cache.get_recent_messages(limit=5)
            assert items == [{"id": 2, "platform": "qq"}, {"id": 1, "platform": "telegram"}]
        finally:
            _uninstall_fake_aioredis()

    @pytest.mark.asyncio
    async def test_push_and_read_noop_when_disabled(self):
        cache = RedisCache(ttl=60)
        assert cache.available is False
        await cache.push_recent_message({"id": 1})
        assert await cache.get_recent_messages() == []


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

