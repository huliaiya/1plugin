"""api.py 集成测试"""

import json
import time
import uuid

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.api import MessageRecorderAPI
from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord, SCHEMA_VERSION


@pytest.fixture
async def db_and_api(mysql_db):
    api = MessageRecorderAPI(mysql_db)
    yield mysql_db, api


def _make_record(**overrides) -> MessageRecord:
    _uid = uuid.uuid4().hex[:8]
    defaults = dict(
        platform="telegram",
        message_id=f"api_msg_{_uid}",
        session_id="sess_001",
        group_id="grp_001",
        sender_id="user_001",
        sender_name="Alice",
        message_type="group",
        message_str=f"Hello from API test {_uid}",
        timestamp=time.time_ns() // 1_000_000,
    )
    defaults.update(overrides)
    return MessageRecord(**defaults)


class TestMessageRecorderAPIQuery:
    @pytest.mark.asyncio
    async def test_query_basic(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record())
        results = await api.query(limit=10)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_platform(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord", message_id="api_m2"))
        results = await api.query(platform="telegram")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_group(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(group_id="g1"))
        await db.save_message(_make_record(group_id="g2", message_id="api_m2"))
        results = await api.query(group_id="g1")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_channel(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(channel_id="ch1"))
        results = await api.query(channel_id="ch1")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_keyword(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(message_str="unique keyword test"))
        results = await api.search("unique keyword")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_multiple_platforms(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord", message_id="m2"))
        await db.save_message(_make_record(platform="wechat", message_id="m3"))
        results = await api.query(platforms=["telegram", "discord"])
        assert len(results) == 2


class TestMessageRecorderAPICount:
    @pytest.mark.asyncio
    async def test_count_all(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record())
        await db.save_message(_make_record(message_id="c2"))
        count = await api.count()
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_with_filter(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord", message_id="c2"))
        count = await api.count(platform="telegram")
        assert count == 1


class TestMessageRecorderAPIShortcuts:
    @pytest.mark.asyncio
    async def test_get_today(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record())
        results = await api.get_today()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_yesterday(self, db_and_api):
        db, api = db_and_api
        results = await api.get_yesterday()
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_recent(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record())
        results = await api.get_recent(hours=1)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_recent_days(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record())
        results = await api.get_recent_days(days=7)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(message_str="searchable content"))
        results = await api.search("searchable")
        assert len(results) == 1


class TestMessageRecorderAPIGetById:
    @pytest.mark.asyncio
    async def test_get_by_id(self, db_and_api):
        db, api = db_and_api
        rid = await db.save_message(_make_record())
        result = await api.get_by_id(rid)
        assert result is not None
        assert result.id == rid

    @pytest.mark.asyncio
    async def test_get_by_platform_message_id(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(platform="telegram", message_id="pm_100"))
        result = await api.get_by_platform_message_id("pm_100", platform="telegram")
        assert result is not None
        assert result.message_id == "pm_100"


class TestMessageRecorderAPIReplies:
    @pytest.mark.asyncio
    async def test_get_replies(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(message_id="orig_1"))
        await db.save_message(
            _make_record(message_id="reply_1", reply_to_id="orig_1")
        )
        results = await api.get_replies("orig_1")
        assert len(results) == 1
        assert results[0].reply_to_id == "orig_1"


class TestMessageRecorderAPIContext:
    @pytest.mark.asyncio
    async def test_get_context(self, db_and_api):
        db, api = db_and_api
        ts_base = 1700000000000
        for i in range(5):
            await db.save_message(
                _make_record(
                    message_id=f"ctx_{i}",
                    group_id="grp_ctx",
                    message_type="group",
                    timestamp=ts_base + i * 1000,
                )
            )
        target = await db.get_message_by_platform_id("ctx_2")
        context = await api.get_context(target.id, before=1, after=1)
        assert "before" in context
        assert "after" in context


class TestMessageRecorderAPIStats:
    @pytest.mark.asyncio
    async def test_get_stats(self, db_and_api):
        db, api = db_and_api
        await db.save_message(_make_record(message_type="group"))
        stats = await api.get_stats()
        assert stats.total_count >= 1


class TestMessageRecorderAPIMedia:
    def test_get_media_url(self, db_and_api):
        _, api = db_and_api
        url = api.get_media_url("images/2026/abc.jpg")
        assert url.startswith("/astrbot_plugin_fox_toolbox/media?path=")
        assert "images" in url and "abc.jpg" in url

    def test_get_media_url_empty(self, db_and_api):
        _, api = db_and_api
        assert api.get_media_url("") == ""

    def test_extract_media_paths(self, db_and_api):
        _, api = db_and_api
        chain = json.dumps([{"type": "Image", "local_path": "images/test.jpg"}])
        record = MessageRecord(message_chain=chain)
        paths = api.extract_media_paths(record)
        assert "images/test.jpg" in paths

    def test_get_schema_version(self, db_and_api):
        _, api = db_and_api
        assert api.get_schema_version() == SCHEMA_VERSION
