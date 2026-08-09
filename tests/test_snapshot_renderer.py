"""snapshot_renderer.py 内部辅助函数单元测试"""

from decimal import Decimal

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.snapshot_renderer import (
    _to_int,
    render_snapshot,
)


class TestToInt:
    def test_none_returns_default(self):
        assert _to_int(None) == 0
        assert _to_int(None, 7) == 7

    def test_int_and_float(self):
        assert _to_int(42) == 42
        assert _to_int(-3) == -3
        assert _to_int(3.9) == 3

    def test_bool(self):
        assert _to_int(True) == 1
        assert _to_int(False) == 0

    def test_decimal(self):
        # 兼容 MySQL 驱动返回的 Decimal 聚合值
        assert _to_int(Decimal("42")) == 42
        assert _to_int(Decimal("3.99")) == 3
        assert _to_int(Decimal("0")) == 0

    def test_numeric_string(self):
        assert _to_int("42") == 42
        assert _to_int("3.7") == 3

    def test_unsupported_type(self):
        assert _to_int({"a": 1}) == 0
        assert _to_int([1, 2]) == 0
        assert _to_int("abc") == 0


@pytest.mark.parametrize(
    "redis_status",
    [
        {
            "configured": True,
            "available": True,
            "enabled": True,
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
            "ttl": 300,
            "version": "7.2.4",
            "key_count": 42,
            "memory_human": "1.2M",
            "keys": {"stats": 1, "recent_messages": 10},
        },
        {
            "configured": True,
            "available": False,
            "enabled": True,
            "version": None,
        },
        None,
    ],
)
def test_render_snapshot_with_redis_status(redis_status):
    """render_snapshot 在各 Redis 状态下均可正常出图（含版本字段）。"""
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
        timeline=[
            {"date": "01-01", "count": 10, "group_count": 6, "private_count": 3, "channel_count": 1}
        ],
        sender_ranking=[{"sender_id": "u1", "sender_name": "A", "platform": "tg", "count": 50}],
        group_ranking=[{"group_id": "g1", "platform": "tg", "count": 40, "sender_count": 5}],
        content_types=[{"type": "text", "label": "文本", "count": 80}],
        platform_stats={"telegram": 70, "discord": 30},
        platform_detail=[{"platform": "telegram", "platform_name": "Telegram", "total": 70}],
        redis_status=redis_status,
    )
    assert isinstance(png, bytes)
    assert len(png) > 0


def test_snapshot_card_order():
    """快照卡片绘制顺序：时间趋势 → 平台分布 → 平台消息详情 → 内容类型 → 排行。"""
    import astrbot_plugin_fox_toolbox.fox_toolbox.snapshot_renderer as sr
    from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageStats

    calls = []
    orig = sr._draw_glass_card

    def spy(img, xy, title=None, accent=None):
        calls.append((title, xy[1]))
        return orig(img, xy, title=title, accent=accent)

    sr._draw_glass_card = spy
    try:
        stats = MessageStats(total_count=100, group_message_count=60,
                             private_message_count=30, channel_message_count=10)
        sr.render_snapshot(
            stats, 6,
            timeline=[{"date": "01", "count": 10}],
            sender_ranking=[{"sender_id": "u1", "sender_name": "A", "platform": "tg", "count": 50}],
            group_ranking=[{"group_id": "g1", "platform": "tg", "count": 40, "sender_count": 5}],
            content_types=[{"type": "text", "label": "文本", "count": 80}],
            platform_stats={"telegram": 70, "discord": 30},
            platform_detail=[{"platform": "telegram", "platform_name": "Telegram",
                              "total": 70, "group_count": 50, "private_count": 20}],
        )
    finally:
        sr._draw_glass_card = orig

    ordered = [t for t, _ in calls if t]
    assert "消息时间趋势" in ordered
    assert "平台分布" in ordered
    assert "平台消息详情" in ordered
    assert "消息内容类型分布" in ordered
    assert "发送者排行 Top 8" in ordered
    assert "群组活跃度排行 Top 8" in ordered

    assert ordered.index("平台分布") < ordered.index("平台消息详情")
    assert ordered.index("平台消息详情") < ordered.index("消息内容类型分布")
    assert ordered.index("消息内容类型分布") < ordered.index("发送者排行 Top 8")