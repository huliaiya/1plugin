"""广告助手（DsggFeature）单元测试"""

import asyncio
import sys
import types

import pytest

import astrbot_plugin_fox_toolbox.fox_toolbox.dsgg.star as dsgg_star
from astrbot_plugin_fox_toolbox.fox_toolbox.dsgg.star import DsggFeature


def _install_components_stub(monkeypatch):
    """注入 astrbot.core.message(.components) 存根，供消息链重建测试使用。"""
    import astrbot.core as astrbot_core

    class _Plain:
        def __init__(self, text):
            self.text = text
            self.type = "Plain"

    class _Image:
        def __init__(self, file=None):
            self.file = file
            self.type = "Image"

        @classmethod
        def fromFileSystem(cls, path):
            return cls(file=path)

    class _At:
        def __init__(self, qq):
            self.qq = qq

    class _AtAll:
        pass

    msg_mod = types.ModuleType("astrbot.core.message")
    comp_mod = types.ModuleType("astrbot.core.message.components")
    comp_mod.ComponentTypes = {
        "plain": _Plain,
        "image": _Image,
        "at": _At,
        "atall": _AtAll,
    }
    comp_mod.AtAll = _AtAll
    if not hasattr(astrbot_core, "__path__"):
        astrbot_core.__path__ = []
    setattr(astrbot_core, "message", msg_mod)
    monkeypatch.setitem(sys.modules, "astrbot.core.message", msg_mod)
    monkeypatch.setitem(sys.modules, "astrbot.core.message.components", comp_mod)
    return {"_Plain": _Plain, "_Image": _Image, "_AtAll": _AtAll}


class _FakeConfig(dict):
    def save_config(self):
        self._saved = True


class _FakeContext:
    def __init__(self):
        self.sent = []

    async def send_message(self, umo, chain):
        self.sent.append((umo, chain))


class _FakeMsgObj:
    def __init__(self, group_id=None, message=None):
        self.group_id = group_id
        self.message = message
        self.sender = None


class _FakeEvent:
    def __init__(self, platform="aiocqhttp", group_id="10001",
                 umo=None, is_admin=True, message_str=""):
        self._platform = platform
        self._is_admin = is_admin
        self.message_str = message_str
        self.message_obj = _FakeMsgObj(group_id)
        self.unified_msg_origin = umo or f"{platform}:GroupMessage:{group_id}/1"

    def get_platform_name(self):
        return self._platform

    def is_admin(self):
        return self._is_admin


def _make_feature(tmp_path, config=None, platform="aiocqhttp", group_id="10001"):
    cfg = _FakeConfig({
        "dsgg_enabled": True,
        "dsgg_platforms": [],
        "dsgg_exclude_platforms": [],
        "disable_gids": [],
        "dsgg_send_interval": 0,
    })
    if config:
        cfg.update(config)
    feature = DsggFeature.__new__(DsggFeature)
    feature.config = cfg
    feature.context = _FakeContext()
    feature.data_dir = tmp_path
    feature._init_dsgg()
    return feature


@pytest.mark.asyncio
async def test_init_creates_empty_state(tmp_path):
    feature = _make_feature(tmp_path)
    assert feature.dsgg_ads == []
    assert feature.dsgg_scheduled_times == []
    assert feature.dsgg_known_groups == {}
    assert (tmp_path / "dsgg").exists()


@pytest.mark.asyncio
async def test_record_group_and_persist(tmp_path):
    feature = _make_feature(tmp_path)
    feature._dsgg_record_group("aiocqhttp", "10001", "aiocqhttp:GroupMessage:10001/1", "group")
    feature._dsgg_record_group("aiocqhttp", "10001", "aiocqhttp:GroupMessage:10001/2", "group")
    feature._dsgg_record_group("telegram", "20001", "telegram:GroupMessage:20001/3", "group")
    feature._dsgg_record_group("aiocqhttp", "10001", "aiocqhttp:GroupMessage:10001/4", "private")
    await feature._dsgg_flush_groups()
    assert len(feature.dsgg_known_groups) == 2
    # 同一群更新 umo，私聊不记录
    assert feature.dsgg_known_groups["aiocqhttp:10001"]["umo"] == "aiocqhttp:GroupMessage:10001/2"
    assert "aiocqhttp:10001/4" not in feature.dsgg_known_groups


@pytest.mark.asyncio
async def test_platform_filter_whitelist(tmp_path):
    feature = _make_feature(tmp_path, config={"dsgg_platforms": ["aiocqhttp"]})
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_record_group("telegram", "2", "t:GroupMessage:2/1", "group")
    targets = feature._dsgg_get_targets()
    assert len(targets) == 1
    assert targets[0][0] == "aiocqhttp"


@pytest.mark.asyncio
async def test_platform_filter_blacklist(tmp_path):
    feature = _make_feature(tmp_path, config={"dsgg_exclude_platforms": ["telegram"]})
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_record_group("telegram", "2", "t:GroupMessage:2/1", "group")
    targets = feature._dsgg_get_targets()
    assert len(targets) == 1
    assert targets[0][0] == "aiocqhttp"


@pytest.mark.asyncio
async def test_disable_gids_both_formats(tmp_path):
    feature = _make_feature(tmp_path, config={"disable_gids": ["2", "telegram:3"]})
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_record_group("aiocqhttp", "2", "a:GroupMessage:2/1", "group")
    feature._dsgg_record_group("telegram", "2", "t:GroupMessage:2/1", "group")
    feature._dsgg_record_group("telegram", "3", "t:GroupMessage:3/1", "group")
    targets = feature._dsgg_get_targets()
    gids = {(p, g) for p, g, _ in targets}
    # 纯 ID "2" 屏蔽所有平台；telegram:3 仅屏蔽 telegram 的 3
    assert ("aiocqhttp", "1") in gids
    assert ("telegram", "2") not in gids
    assert ("aiocqhttp", "2") not in gids
    assert ("telegram", "3") not in gids


@pytest.mark.asyncio
async def test_add_remove_list_ad(tmp_path):
    feature = _make_feature(tmp_path)
    ad_id = feature._dsgg_add_ad([{"type": "Plain", "text": "广告"}], "广告文本")
    assert ad_id == 1
    assert feature.dsgg_list_ads().startswith("广告列表")
    assert feature.dsgg_get_ad(1)["text"] == "广告文本"
    assert "已删除广告 ID: 1" == feature.dsgg_remove_ad(1)
    assert feature.dsgg_get_ad(1) is None
    assert "未找到广告 ID" in feature.dsgg_remove_ad(99)


@pytest.mark.asyncio
async def test_ads_persist_across_reload(tmp_path):
    feature = _make_feature(tmp_path)
    feature._dsgg_add_ad([{"type": "Plain", "text": "x"}], "x")
    feature2 = DsggFeature.__new__(DsggFeature)
    feature2.config = _FakeConfig({})
    feature2.context = _FakeContext()
    feature2.data_dir = tmp_path
    feature2._init_dsgg()
    assert len(feature2.dsgg_ads) == 1
    assert feature2.dsgg_ads[0]["text"] == "x"


@pytest.mark.asyncio
async def test_schedule_parse_and_invalid(tmp_path):
    feature = _make_feature(tmp_path)
    msg = feature.dsgg_schedule("09:00,14:30,09:00")
    assert "09:00, 14:30" in msg
    assert feature.dsgg_scheduled_times == ["09:00", "14:30"]
    feature.dsgg_broadcast_task.cancel()
    await asyncio.gather(feature.dsgg_broadcast_task, return_exceptions=True)
    feature.dsgg_broadcast_task = None
    bad = feature.dsgg_schedule("25:00")
    assert "时间格式错误" in bad
    no_arg = feature.dsgg_schedule("")
    assert "当前定时广告时间" in no_arg
    feature.dsgg_schedule("09:00")
    await asyncio.sleep(0)
    assert "已停止定时广告发送" in feature.dsgg_stop_schedule()
    await asyncio.sleep(0)
    assert feature.dsgg_scheduled_times == []


@pytest.mark.asyncio
async def test_enable_disable_ad_via_config(tmp_path):
    feature = _make_feature(tmp_path)
    event = _FakeEvent(platform="aiocqhttp", group_id="10001")
    msg = await feature.dsgg_disable_ad(event)
    assert "不再接收广告消息" in msg
    assert feature.config["disable_gids"] == ["aiocqhttp:10001"]
    assert feature.config._saved
    msg2 = await feature.dsgg_enable_ad(event)
    assert "可以接收广告消息了" in msg2
    assert feature.config["disable_gids"] == []
    msg3 = await feature.dsgg_enable_ad(event)
    assert "无需重复开启" in msg3


@pytest.mark.asyncio
async def test_enable_disable_from_non_group(tmp_path):
    feature = _make_feature(tmp_path)
    event = _FakeEvent(platform="aiocqhttp", group_id="")
    msg = await feature.dsgg_disable_ad(event)
    assert "不是群聊" in msg


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_targets(tmp_path):
    feature = _make_feature(tmp_path)
    feature._dsgg_add_ad([{"type": "Plain", "text": "打折啦"}], "打折啦")
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_record_group("telegram", "2", "t:GroupMessage:2/1", "group")
    await feature._dsgg_broadcast()
    sent = feature.context.sent
    assert len(sent) == 2
    umos = {u for u, _ in sent}
    assert umos == {"a:GroupMessage:1/1", "t:GroupMessage:2/1"}


@pytest.mark.asyncio
async def test_broadcast_skips_disabled_and_no_ads(tmp_path):
    feature = _make_feature(tmp_path, config={"disable_gids": ["1"]})
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_add_ad([{"type": "Plain", "text": "x"}], "x")
    await feature._dsgg_broadcast()
    assert feature.context.sent == []
    feature.dsgg_ads.clear()
    feature._dsgg_record_group("aiocqhttp", "2", "a:GroupMessage:2/1", "group")
    await feature._dsgg_broadcast()
    assert feature.context.sent == []


@pytest.mark.asyncio
async def test_broadcast_continues_on_send_failure(tmp_path):
    feature = _make_feature(tmp_path)
    feature._dsgg_add_ad([{"type": "Plain", "text": "x"}], "x")
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_record_group("telegram", "2", "t:GroupMessage:2/1", "group")

    async def _boom(umo, chain):
        if umo.startswith("t:"):
            raise RuntimeError("send failed")
        feature.context.sent.append((umo, chain))

    feature.context.send_message = _boom
    await feature._dsgg_broadcast()
    assert len(feature.context.sent) == 1
    assert feature.context.sent[0][0] == "a:GroupMessage:1/1"


@pytest.mark.asyncio
async def test_event_group_helpers(tmp_path):
    feature = _make_feature(tmp_path)
    event = _FakeEvent(platform="telegram", group_id="888")
    assert feature._dsgg_event_platform(event) == "telegram"
    assert feature._dsgg_event_group_id(event) == "888"
    platform, gid = feature._dsgg_event_group(event)
    assert platform == "telegram" and gid == "888"


@pytest.mark.asyncio
async def test_group_list_output(tmp_path):
    feature = _make_feature(tmp_path, config={"disable_gids": ["1"]})
    feature._dsgg_record_group("aiocqhttp", "1", "a:GroupMessage:1/1", "group")
    feature._dsgg_record_group("aiocqhttp", "2", "a:GroupMessage:2/1", "group")
    text = feature.dsgg_group_list()
    assert "广告群列表" in text
    assert "关闭" in text
    assert "启用" in text
    assert "暂无已接入的群聊" in _make_feature(tmp_path).dsgg_group_list()


@pytest.mark.asyncio
async def test_build_chain_and_fallback(tmp_path, monkeypatch):
    stubs = _install_components_stub(monkeypatch)
    _AtAll = stubs["_AtAll"]

    class _MC:
        def __init__(self, chain=None):
            self.chain = list(chain) if chain else []

        def message(self, text):
            self.chain.append(text)
            return self

    monkeypatch.setattr(dsgg_star, "MessageChain", _MC)

    feature = _make_feature(tmp_path)
    chain = feature._dsgg_build_chain([
        {"type": "Plain", "text": "hi"},
        {"type": "Image", "url": "https://example.com/a.png"},
        {"type": "At", "qq": "123"},
        {"type": "AtAll"},
        {"type": "Face", "id": 1},
    ])
    texts = [c.text for c in chain.chain if hasattr(c, "text") and c.type == "Plain"]
    assert texts == ["hi"]
    img = chain.chain[1]
    assert img.file == "https://example.com/a.png"
    assert chain.chain[2].qq == "123"
    assert isinstance(chain.chain[3], _AtAll)
    # 图片本地文件走 fromFileSystem
    local = tmp_path / "x.png"
    local.write_bytes(b"abc")
    chain2 = feature._dsgg_build_chain([{"type": "Image", "path": str(local)}])
    assert chain2.chain[0].file == str(local)
    # 未知组件跳过
    chain3 = feature._dsgg_build_chain([{"type": "UnknownFoo", "x": 1}])
    assert len(chain3.chain) == 0


@pytest.mark.asyncio
async def test_send_to_uses_chain(tmp_path, monkeypatch):
    _install_components_stub(monkeypatch)

    class _MC:
        def __init__(self, chain=None):
            self.chain = list(chain) if chain else []

        def message(self, text):
            self.chain.append(text)
            return self

    monkeypatch.setattr(dsgg_star, "MessageChain", _MC)

    feature = _make_feature(tmp_path)
    ad = {"content": [{"type": "Plain", "text": "hello"}], "text": "hello"}
    await feature._dsgg_send_to("umo:GroupMessage:1/1", ad)
    sent = feature.context.sent[0]
    assert sent[0] == "umo:GroupMessage:1/1"
    assert sent[1].chain[0].text == "hello"


@pytest.mark.asyncio
async def test_send_to_fallback_plain_text(tmp_path, monkeypatch):
    class _MC:
        def __init__(self, chain=None):
            self.chain = list(chain) if chain else []

        def message(self, text):
            self.chain.append(text)
            return self

    monkeypatch.setattr(dsgg_star, "MessageChain", _MC)

    feature = _make_feature(tmp_path)
    ad = {"content": None, "text": "纯文本降级"}
    await feature._dsgg_send_to("umo:GroupMessage:1/1", ad)
    assert feature.context.sent[0][1].chain == ["纯文本降级"]


@pytest.mark.asyncio
async def test_schedule_persist(tmp_path):
    feature = _make_feature(tmp_path)
    feature.dsgg_schedule("08:00")
    assert feature.dsgg_broadcast_task is not None
    feature.dsgg_broadcast_task.cancel()
    await asyncio.gather(feature.dsgg_broadcast_task, return_exceptions=True)
    feature.dsgg_broadcast_task = None
    feature2 = DsggFeature.__new__(DsggFeature)
    feature2.config = _FakeConfig({})
    feature2.context = _FakeContext()
    feature2.data_dir = tmp_path
    feature2._init_dsgg()
    assert feature2.dsgg_scheduled_times == ["08:00"]
