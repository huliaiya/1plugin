"""platform_adapter.py 单元测试"""

import pytest

from astrbot.core.platform.message_type import MessageType

from astrbot_plugin_fox_toolbox.fox_toolbox.platform_adapter import (
    PlatformAdapter,
    TelegramAdapter,
    ChannelBasedAdapter,
    get_adapter,
    register_adapter,
    _ADAPTER_REGISTRY,
    _adapter_cache,
)


class MockMessageObj:
    def __init__(self, **kwargs):
        self.type = kwargs.pop("type", None)
        self.group_id = kwargs.pop("group_id", None)
        self.__dict__.update(kwargs)


class TestPlatformAdapter:
    def setup_method(self):
        self.adapter = PlatformAdapter()

    def test_normalize_sender_id(self):
        assert self.adapter.normalize_sender_id("  123  ") == "123"
        assert self.adapter.normalize_sender_id("") == ""
        assert self.adapter.normalize_sender_id("abc") == "abc"

    def test_normalize_sender_name(self):
        assert self.adapter.normalize_sender_name("  Alice  ") == "Alice"
        assert self.adapter.normalize_sender_name(None) is None
        assert self.adapter.normalize_sender_name("") is None

    def test_normalize_sender_name_truncation(self):
        long_name = "A" * 300
        result = self.adapter.normalize_sender_name(long_name)
        assert len(result) == 256

    def test_normalize_group_id(self):
        assert self.adapter.normalize_group_id("  grp1  ") == "grp1"
        assert self.adapter.normalize_group_id(None) is None
        assert self.adapter.normalize_group_id("") is None

    def test_normalize_group_id_truncation(self):
        long_id = "G" * 200
        result = self.adapter.normalize_group_id(long_id)
        assert len(result) == 128

    def test_extract_channel_id_default(self):
        assert self.adapter.extract_channel_id(MockMessageObj()) is None

    def test_normalize_channel_id(self):
        assert self.adapter.normalize_channel_id("  ch1  ") == "ch1"
        assert self.adapter.normalize_channel_id(None) is None
        assert self.adapter.normalize_channel_id("") is None

    def test_normalize_channel_id_truncation(self):
        long_id = "C" * 200
        result = self.adapter.normalize_channel_id(long_id)
        assert len(result) == 128

    def test_normalize_message_id(self):
        assert self.adapter.normalize_message_id("  msg1  ") == "msg1"
        assert self.adapter.normalize_message_id("") == ""
        assert self.adapter.normalize_message_id(None) == ""

    def test_normalize_message_id_truncation(self):
        long_id = "M" * 200
        result = self.adapter.normalize_message_id(long_id)
        assert len(result) == 128

    def test_determine_message_type_group(self):
        msg = MockMessageObj(type=MessageType.GROUP_MESSAGE, group_id="grp1")
        assert self.adapter.determine_message_type(msg) == "group"

    def test_determine_message_type_private(self):
        msg = MockMessageObj(type=MessageType.FRIEND_MESSAGE)
        assert self.adapter.determine_message_type(msg) == "private"

    def test_determine_message_type_other(self):
        msg = MockMessageObj(type=MessageType.OTHER_MESSAGE)
        assert self.adapter.determine_message_type(msg) == "private"

    def test_determine_message_type_fallback(self):
        msg = MockMessageObj()
        assert self.adapter.determine_message_type(msg) == "private"

    def test_determine_message_type_fallback_group_context(self):
        msg = MockMessageObj(type=MessageType.OTHER_MESSAGE, group_id="grp1")
        assert self.adapter.determine_message_type(msg) == "group"

    def test_extract_reply_to_id(self):
        comp = object()
        data = {"type": "Reply", "message_id": "123"}
        assert self.adapter.extract_reply_to_id(comp, data) == "123"

    def test_extract_reply_to_id_fallback(self):
        data = {"type": "Reply", "id": "456"}
        assert self.adapter.extract_reply_to_id(object(), data) == "456"

    def test_extract_reply_to_id_not_reply(self):
        data = {"type": "Plain", "text": "hi"}
        assert self.adapter.extract_reply_to_id(object(), data) is None


class TestTelegramAdapter:
    def setup_method(self):
        self.adapter = TelegramAdapter()

    def test_platform_name(self):
        assert self.adapter.PLATFORM_NAME == "telegram"

    def test_normalize_message_id_numeric(self):
        assert self.adapter.normalize_message_id("123") == "123"
        assert self.adapter.normalize_message_id("  456  ") == "456"

    def test_normalize_message_id_non_numeric(self):
        assert self.adapter.normalize_message_id("abc") == "abc"

    def test_normalize_message_id_empty(self):
        assert self.adapter.normalize_message_id("") == ""
        assert self.adapter.normalize_message_id(None) == ""


class TestChannelBasedAdapter:
    def setup_method(self):
        self.adapter = ChannelBasedAdapter()

    def test_determine_message_type_channel(self):
        msg = MockMessageObj(type=MessageType.GROUP_MESSAGE, group_id="123456")
        assert self.adapter.determine_message_type(msg) == "channel"

    def test_determine_message_type_private(self):
        msg = MockMessageObj(type=MessageType.FRIEND_MESSAGE)
        assert self.adapter.determine_message_type(msg) == "private"

    def test_determine_message_type_other(self):
        msg = MockMessageObj(type=MessageType.OTHER_MESSAGE)
        assert self.adapter.determine_message_type(msg) == "private"

    def test_determine_message_type_other_with_group_context(self):
        msg = MockMessageObj(type=MessageType.OTHER_MESSAGE, group_id="987654")
        assert self.adapter.determine_message_type(msg) == "channel"

    def test_extract_channel_id(self):
        msg = MockMessageObj(type=MessageType.GROUP_MESSAGE, group_id="987654")
        assert self.adapter.extract_channel_id(msg) == "987654"

    def test_extract_channel_id_no_group(self):
        msg = MockMessageObj(type=MessageType.FRIEND_MESSAGE)
        assert self.adapter.extract_channel_id(msg) is None

    def test_extract_channel_id_empty_group(self):
        msg = MockMessageObj(type=MessageType.GROUP_MESSAGE, group_id="")
        assert self.adapter.extract_channel_id(msg) is None


class TestGetAdapter:
    def setup_method(self):
        _adapter_cache.clear()

    def test_known_platform(self):
        adapter = get_adapter("telegram")
        assert isinstance(adapter, TelegramAdapter)

    def test_channel_based_platform(self):
        adapter = get_adapter("discord")
        assert isinstance(adapter, ChannelBasedAdapter)

    def test_standard_platform(self):
        adapter = get_adapter("aiocqhttp")
        assert isinstance(adapter, PlatformAdapter)
        assert not isinstance(adapter, (TelegramAdapter, ChannelBasedAdapter))

    def test_all_registered_platforms(self):
        for name in _ADAPTER_REGISTRY:
            adapter = get_adapter(name)
            assert adapter is not None

    def test_unknown_platform(self):
        adapter = get_adapter("unknown_platform")
        assert isinstance(adapter, PlatformAdapter)

    def test_empty_platform(self):
        adapter = get_adapter("")
        assert isinstance(adapter, PlatformAdapter)

    def test_none_platform(self):
        adapter = get_adapter(None)
        assert isinstance(adapter, PlatformAdapter)

    def test_caching(self):
        a1 = get_adapter("telegram")
        a2 = get_adapter("telegram")
        assert a1 is a2


class TestRegisterAdapter:
    def setup_method(self):
        _adapter_cache.clear()

    def test_register_custom(self):
        class CustomAdapter(PlatformAdapter):
            PLATFORM_NAME = "custom"

        register_adapter("custom", CustomAdapter)
        adapter = get_adapter("custom")
        assert isinstance(adapter, CustomAdapter)

    def test_register_overwrites_cache(self):
        get_adapter("telegram")
        assert "telegram" in _adapter_cache

        class FakeTelegram(PlatformAdapter):
            PLATFORM_NAME = "telegram"

        register_adapter("telegram", FakeTelegram)
        assert "telegram" not in _adapter_cache

        adapter = get_adapter("telegram")
        assert isinstance(adapter, FakeTelegram)
