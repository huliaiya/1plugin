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


def test_platform_donut_legend_no_overlap():
    """平台分布图例：高占比平台的进度条不得延伸到右侧数值文字区域。"""
    import astrbot_plugin_fox_toolbox.fox_toolbox.snapshot_renderer as sr
    from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageStats

    platform_stats = {"qq_official": 2724, "telegram": 195, "webchat": 52,
                      "weixin_oc": 25, "kook": 10}

    stats = MessageStats(total_count=3006, group_message_count=2800,
                         private_message_count=200, channel_message_count=6)
    sr.render_snapshot(
        stats, 6,
        timeline=[{"date": "01", "count": 10}],
        sender_ranking=[{"sender_id": "u1", "sender_name": "A", "platform": "tg", "count": 50}],
        group_ranking=[{"group_id": "g1", "platform": "tg", "count": 40, "sender_count": 5}],
        content_types=[{"type": "text", "label": "文本", "count": 80}],
        platform_stats=platform_stats,
        platform_detail=[],
    )

    # 复现 _draw_platform_donut 图例几何，校验进度条右端不越过数值文字左端
    img = sr.Image.new("RGBA", (100, 100))
    draw = sr.ImageDraw.Draw(img)
    x0 = sr._PX(34) + sr._PX(24)
    x1 = sr._W_FULL - sr._PX(34) - sr._PX(24)
    inner_w = x1 - x0
    inner_h = sr._PX(280) - sr._PX(24) * 2
    donut_d = min(inner_h, inner_w * 0.5)
    legend_x = x0 + donut_d + sr._PX(40)
    legend_w = inner_w - donut_d - sr._PX(60)
    f_count = sr._get_font(sr._PX(15))

    total = sum(platform_stats.values())
    items = sorted(platform_stats.items(), key=lambda kv: kv[1], reverse=True)
    max_val_w = max(
        sr._text_width(draw, f"{v:,} ({v * 100 / total:.1f}%)", f_count)
        for _, v in items[:5]
    )
    bar_w = max(legend_w - sr._PX(100) - max_val_w - sr._PX(16), sr._PX(20))
    bar_right = legend_x + sr._PX(100) + bar_w

    for _, val in items[:5]:
        tw = sr._text_width(draw, f"{val:,} ({val * 100 / total:.1f}%)", f_count)
        val_left = x1 - tw - sr._PX(8)
        assert bar_right <= val_left, (
            f"进度条末端({bar_right}) 遮挡数值文字起点({val_left})"
        )