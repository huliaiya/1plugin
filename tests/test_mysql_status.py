"""MySQL 连接状态展示测试

覆盖：
1. Database.get_mysql_version 版本获取（正常/降级/失败）
2. web_api._build_db_status_payload 的 mysql_version / mysql_connected 字段
3. 快照渲染 _draw_mysql_card 各状态（运行中/降级/未连接）不抛异常
4. render_snapshot 传入 mysql_status 正常出图
"""

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.snapshot_renderer import (
    _draw_mysql_card,
    render_snapshot,
)
from astrbot_plugin_fox_toolbox.fox_toolbox.web_api import _build_db_status_payload


class _FakeDb:
    """带可配置行为的 Database mock。"""

    def __init__(self, table_count=5, fallback=False, version="8.0.36", unsynced=3, mysql_ready=True):
        self._table_count = table_count
        self._fallback = fallback
        self._version = version
        self._unsynced = unsynced
        self._mysql_ready = mysql_ready

    @property
    def using_fallback(self):
        return self._fallback

    @property
    def mysql_ready(self):
        return self._mysql_ready

    async def get_table_count(self):
        return self._table_count

    async def get_unsynced_count(self):
        return self._unsynced

    async def get_mysql_version(self):
        return self._version


async def test_payload_mysql_connected_with_version():
    db = _FakeDb(table_count=6, fallback=False, version="8.0.36")
    payload = await _build_db_status_payload(db)
    assert payload["running"] is True
    assert payload["mysql_connected"] is True
    assert payload["mysql_version"] == "8.0.36"
    assert payload["fallback_active"] is False
    assert payload["unsynced_count"] == 0


async def test_payload_fallback_sqlite():
    db = _FakeDb(
        table_count=5,
        fallback=True,
        version=None,
        unsynced=12,
        mysql_ready=False,
    )
    payload = await _build_db_status_payload(db)
    assert payload["running"] is True
    assert payload["mysql_connected"] is False
    assert payload["mysql_version"] is None
    assert payload["fallback_active"] is True
    assert payload["unsynced_count"] == 12
    assert payload["storage_backend"] == "sqlite"


async def test_payload_no_db():
    payload = await _build_db_status_payload(None, "数据库未初始化")
    assert payload["running"] is False
    assert payload["mysql_connected"] is False
    assert payload["mysql_version"] is None


async def test_payload_mysql_down_without_fallback():
    """MySQL 未就绪且未启用兜底时，连接状态应为未连接而非误报运行。"""
    db = _FakeDb(
        table_count=-1,
        fallback=False,
        version=None,
        mysql_ready=False,
    )
    payload = await _build_db_status_payload(db)
    assert payload["mysql_connected"] is False
    assert payload["mysql_version"] is None
    assert payload["fallback_active"] is False


def test_draw_mysql_card_connected():
    from PIL import Image

    img = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    y = _draw_mysql_card(
        img, 10, {"connected": True, "fallback_active": False, "version": "8.0.36"}
    )
    assert y > 10


def test_draw_mysql_card_fallback():
    from PIL import Image

    img = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    y = _draw_mysql_card(
        img, 10, {"connected": False, "fallback_active": True, "unsynced_count": 5}
    )
    assert y > 10


def test_draw_mysql_card_disconnected():
    from PIL import Image

    img = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    y = _draw_mysql_card(img, 10, {"connected": False, "fallback_active": False})
    assert y > 10


@pytest.mark.parametrize(
    "mysql_status",
    [
        {"connected": True, "fallback_active": False, "version": "8.0.36"},
        {"connected": False, "fallback_active": True, "unsynced_count": 5},
        {"connected": False, "fallback_active": False},
        None,
    ],
)
def test_render_snapshot_with_mysql_status(mysql_status):
    """render_snapshot 在各 MySQL 状态下均可正常出图。"""
    from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageStats

    stats = MessageStats(
        total_count=100,
        group_message_count=60,
        private_message_count=30,
        channel_message_count=10,
    )
    png = render_snapshot(
        stats,
        db_table_count=6,
        timeline=[{"date": "01-01", "count": 10, "group_count": 6, "private_count": 3, "channel_count": 1}],
        sender_ranking=[{"sender_id": "u1", "sender_name": "A", "platform": "tg", "count": 50}],
        group_ranking=[{"group_id": "g1", "platform": "tg", "count": 40, "sender_count": 5}],
        content_types=[{"type": "text", "label": "文本", "count": 80}],
        platform_stats={"telegram": 70, "discord": 30},
        platform_detail=[{"platform": "telegram", "platform_name": "Telegram", "total": 70}],
        redis_status={"configured": True, "available": True, "enabled": True},
        mysql_status=mysql_status,
    )
    assert isinstance(png, bytes)
    assert len(png) > 0
