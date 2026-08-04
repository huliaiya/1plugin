"""models.py 单元测试"""

import json
import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.models import (
    MessageRecord,
    QueryFilter,
    MessageStats,
    PLUGIN_DIR_NAME,
    SCHEMA_VERSION,
    VALID_MESSAGE_TYPES,
)


class TestMessageRecord:
    def test_default_values(self):
        r = MessageRecord()
        assert r.id is None
        assert r.platform == ""
        assert r.message_id == ""
        assert r.session_id == ""
        assert r.group_id is None
        assert r.channel_id is None
        assert r.sender_id == ""
        assert r.sender_name is None
        assert r.message_type == ""
        assert r.message_str is None
        assert r.message_chain is None
        assert r.raw_message is None
        assert r.reply_to_id is None
        assert r.content_hash is None
        assert r.timestamp == 0
        assert r.created_at == 0

    def test_to_dict(self):
        r = MessageRecord(
            id=1,
            platform="telegram",
            message_id="123",
            sender_id="user1",
            sender_name="Alice",
            message_type="group",
            message_str="hello",
            timestamp=1700000000000,
        )
        d = r.to_dict()
        assert d["id"] == 1
        assert d["platform"] == "telegram"
        assert d["message_id"] == "123"
        assert d["sender_id"] == "user1"
        assert d["sender_name"] == "Alice"
        assert d["message_type"] == "group"
        assert d["message_str"] == "hello"
        assert d["timestamp"] == 1700000000000
        assert d["group_id"] is None
        assert d["channel_id"] is None

    def test_get_message_chain_list_valid(self):
        chain = [{"type": "Plain", "text": "hi"}, {"type": "Image", "url": "http://x"}]
        r = MessageRecord(message_chain=json.dumps(chain))
        result = r.get_message_chain_list()
        assert len(result) == 2
        assert result[0]["type"] == "Plain"
        assert result[1]["type"] == "Image"

    def test_get_message_chain_list_empty(self):
        r = MessageRecord()
        assert r.get_message_chain_list() == []

    def test_get_message_chain_list_invalid_json(self):
        r = MessageRecord(message_chain="not json")
        assert r.get_message_chain_list() == []

    def test_get_message_chain_list_null(self):
        r = MessageRecord(message_chain=None)
        assert r.get_message_chain_list() == []

    def test_get_raw_message_dict_valid(self):
        raw = {"key": "value", "nested": {"a": 1}}
        r = MessageRecord(raw_message=json.dumps(raw))
        result = r.get_raw_message_dict()
        assert result["key"] == "value"
        assert result["nested"]["a"] == 1

    def test_get_raw_message_dict_invalid(self):
        r = MessageRecord(raw_message="bad json")
        assert r.get_raw_message_dict() is None

    def test_get_raw_message_dict_none(self):
        r = MessageRecord()
        assert r.get_raw_message_dict() is None


class TestQueryFilter:
    def test_default_values(self):
        f = QueryFilter()
        assert f.platform is None
        assert f.limit == 100
        assert f.offset == 0
        assert f.order == "desc"

    def test_get_sender_ids_single(self):
        f = QueryFilter(sender_id="u1")
        assert f.get_sender_ids() == ["u1"]

    def test_get_sender_ids_multiple(self):
        f = QueryFilter(sender_ids=["u1", "u2"])
        assert f.get_sender_ids() == ["u1", "u2"]

    def test_get_sender_ids_combined(self):
        f = QueryFilter(sender_id="u1", sender_ids=["u2", "u3"])
        assert f.get_sender_ids() == ["u1", "u2", "u3"]

    def test_get_sender_ids_empty(self):
        f = QueryFilter()
        assert f.get_sender_ids() == []

    def test_get_group_ids(self):
        f = QueryFilter(group_id="g1", group_ids=["g2"])
        assert f.get_group_ids() == ["g1", "g2"]

    def test_get_session_ids(self):
        f = QueryFilter(session_id="s1", session_ids=["s2"])
        assert f.get_session_ids() == ["s1", "s2"]

    def test_get_platforms(self):
        f = QueryFilter(platform="telegram", platforms=["discord"])
        assert f.get_platforms() == ["telegram", "discord"]

    def test_is_desc_order(self):
        assert QueryFilter(order="desc").is_desc_order() is True
        assert QueryFilter(order="DESC").is_desc_order() is True
        assert QueryFilter(order="asc").is_desc_order() is False
        assert QueryFilter(order="ASC").is_desc_order() is False


class TestMessageStats:
    def test_default_values(self):
        s = MessageStats()
        assert s.total_count == 0
        assert s.group_message_count == 0
        assert s.private_message_count == 0
        assert s.channel_message_count == 0
        assert s.platform_stats == {}
        assert s.oldest_timestamp is None
        assert s.newest_timestamp is None


class TestConstants:
    def test_plugin_dir_name(self):
        assert PLUGIN_DIR_NAME == "astrbot_plugin_fox_toolbox"

    def test_schema_version(self):
        assert SCHEMA_VERSION == 2

    def test_valid_message_types(self):
        assert "group" in VALID_MESSAGE_TYPES
        assert "private" in VALID_MESSAGE_TYPES
        assert "channel" in VALID_MESSAGE_TYPES
        assert "forum" in VALID_MESSAGE_TYPES
