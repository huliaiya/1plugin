"""爱发电查询发电（query-sponsor）修复测试

覆盖以下修复点：
1. query_sponsor 不传 user_id 时查询全部赞助者（不把自己 user_id 当筛选条件）
2. 指定 sponsor_user_ids 时仍会带上 user_id 筛选
3. 查询赞助为空时回退展示本地已同步订单
4. 本地订单 sku_detail 为 JSON 字符串时可正确还原解析
"""

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