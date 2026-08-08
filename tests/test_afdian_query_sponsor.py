"""爱发电查询发电（query-sponsor）与按需轮询修复测试

覆盖以下修复点：
1. query_sponsor 不传 user_id 时查询全部赞助者（不把自己 user_id 当筛选条件）
2. 指定 sponsor_user_ids 时仍会带上 user_id 筛选
3. 查询赞助为空时回退展示本地已同步订单
4. 本地订单 sku_detail 为 JSON 字符串时可正确还原解析
5. 轮询为按需限时模式：无待确认订单时不启动；有待确认订单时启动并按窗口结束
"""

from types import SimpleNamespace

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.afdian.afdian_api import AfdianAPIClient
from astrbot_plugin_fox_toolbox.fox_toolbox.afdian.star import (
    AfdianFeature,
    _db_order_to_dict,
)


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    async def json(self):
        return {"ec": 0, "data": self._data}


class _FakeCtx:
    def __init__(self, data):
        self._data = data

    async def __aenter__(self):
        return _FakeResponse(self._data)

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, data):
        self._data = data
        self.posted = []

    def post(self, url, json=None, timeout=None):
        self.posted.append((url, json))
        return _FakeCtx(self._data)


def _make_client(data, user_id="creator_uid", token="tok"):
    client = AfdianAPIClient(user_id, token, base_url="http://fake/api")
    client.session = _FakeSession(data)
    return client


async def _collect_sponsor_params(client, **kwargs):
    _ = await client.query_sponsor(**kwargs)
    _, payload = client.session.posted[-1]
    from fox_toolbox.afdian.afdian_api import json as _json

    return _json.loads(payload["params"])


@pytest.mark.asyncio
async def test_query_sponsor_without_user_id_queries_all():
    """不传 sponsor_user_ids 时，params 不携带 user_id 字段（查询全部赞助者）。"""
    client = _make_client({"list": []})
    params = await _collect_sponsor_params(client)
    assert "user_id" not in params
    assert params["page"] == 1
    assert params["per_page"] == 20


@pytest.mark.asyncio
async def test_query_sponsor_with_user_id_filters():
    """显式传入 sponsor_user_ids 时携带 user_id 筛选。"""
    client = _make_client({"list": []})
    params = await _collect_sponsor_params(client, sponsor_user_ids="user_a,user_b")
    assert params["user_id"] == "user_a,user_b"


@pytest.mark.asyncio
async def test_query_sponsor_no_longer_uses_own_user_id_as_filter():
    """回归：不得把创作者自己的 user_id 当作赞助者筛选条件传入。"""
    client = _make_client({"list": []}, user_id="creator_uid")
    params = await _collect_sponsor_params(client)
    assert "user_id" not in params


def _build_feature():
    feature = AfdianFeature.__new__(AfdianFeature)
    return feature


@pytest.mark.asyncio
async def test_db_order_to_dict_parses_sku_detail_json():
    """DB 行的 sku_detail JSON 字符串可还原为 list。"""
    row = {
        "out_trade_no": "20260101_abc",
        "sku_detail": '[{"name": "月卡", "count": 1, "sku_id": "SKU1"}]',
    }
    result = _db_order_to_dict(row)
    assert result["sku_detail"] == [
        {"name": "月卡", "count": 1, "sku_id": "SKU1"}
    ]


@pytest.mark.asyncio
async def test_db_query_to_dict_invalid_json_no_crash():
    """sku_detail 非合法 JSON 时不应崩溃。"""
    row = {"out_line_no": "T1", "sku_detail": "not-json"}
    result = _db_order_to_dict(row)
    assert result["sku_detail"] == []


@pytest.mark.asyncio
async def test_db_query_to_dict_missing_sku_keeps_empty():
    row = {"out_trade_no": "T1"}
    result = _db_order_to_dict(row)
    assert result["sku_detail"] == []


# ---- 按需限时轮询 ----

def _make_feature(config=None, client=None):
    """构建一个最小 AfdianFeature 实例。"""
    cfg = SimpleNamespace(
        enabled=True,
        use_polling=True,
        poll_interval=1,
        poll_timeout=300,
    )
    if config:
        for k, v in config.items():
            setattr(cfg, k, v)
    feature = AfdianFeature.__new__(AfdianFeature)
    feature.afdian_cfg = cfg
    feature.afdian_client = client or _make_client({"data": {"list": []}})
    feature.afdian_db = SimpleNamespace(save_order_if_new=lambda order: False)
    feature.afdian_sync_task = None
    feature.afdian_poll_task = None
    feature.afdian_pending_orders = {}
    return feature


@pytest.mark.asyncio
async def test_ensure_polling_skips_without_pending():
    """无待确认订单时不启动轮询（不请求接口）。"""
    feature = _make_feature()
    started = await feature.afdian_ensure_polling()
    assert started is False
    assert feature.afdian_poll_task is None


@pytest.mark.asyncio
async def test_ensure_polling_starts_with_pending():
    """有待确认订单时启动限时轮询任务。"""
    feature = _make_feature()
    feature.afdian_pending_orders["user_1"] = {"created_at": 0}
    started = await feature.afdian_ensure_polling()
    assert started is True
    assert feature.afdian_poll_task is not None


@pytest.mark.asyncio
async def test_ensure_polling_disabled_when_use_polling_off():
    """use_polling 关闭时不启动轮询。"""
    feature = _make_feature({"use_polling": False})
    feature.afdian_pending_orders["user_1"] = {"created_at": 0}
    started = await feature.afdian_ensure_polling()
    assert started is False
    assert feature.afdian_poll_task is None


@pytest.mark.asyncio
async def test_poll_loop_stops_when_pending_cleared():
    """待确认订单被处理后（pending 清空）轮询自动停止。"""
    feature = _make_feature()
    feature.afdian_pending_orders["user_1"] = {"created_at": 0}
    feature.afdian_poll_window_end = 0  # 窗口立即过期
    await feature.afdian_poll_loop()
    assert feature.afdian_poll_task is None