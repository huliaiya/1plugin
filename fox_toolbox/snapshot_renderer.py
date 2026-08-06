"""WebUI 仪表盘快照渲染器

用 Pillow 把数据库统计数据渲染成一张与 WebUI 视觉风格相近的 PNG，
供 /msg_record snapshot 指令直接发到聊天。零新增重依赖，仅依赖已有的 Pillow。
"""

import io
import math
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from PIL import Image, ImageDraw, ImageFont

from .models import MessageStats


# ========== 视觉常量（对齐 WebUI Liquid Glass 风格） ==========

_W = 1080
_PADDING = 36
_CARD_RADIUS = 18
_CARD_GAP = 18

# 背景渐变（对齐 style.css body 的浅色渐变）
_BG_TOP = (240, 247, 255)
_BG_BOTTOM = (252, 228, 236)

# 主色系（对齐 :root --primary-color 等）
_PRIMARY = (79, 195, 247)
_PRIMARY_DARK = (2, 136, 209)
_SUCCESS = (16, 185, 129)
_WARNING = (245, 158, 11)
_DANGER = (239, 68, 68)
_PURPLE = (139, 92, 246)

_TEXT = (30, 41, 59)
_TEXT_LIGHT = (100, 116, 139)
_TEXT_WHITE = (255, 255, 255)

# 玻璃卡片：半透明白底
_GLASS_BG = (255, 255, 255, 235)
_GLASS_BORDER = (255, 255, 255, 180)

# 图表配色（折线/柱状/饼图系列）
_CHART_COLORS = [
    (79, 195, 247),
    (16, 185, 129),
    (245, 158, 11),
    (139, 92, 246),
    (239, 68, 68),
    (255, 183, 77),
    (77, 208, 225),
    (129, 199, 132),
    (240, 98, 146),
    (149, 117, 205),
]

# 统计卡片配色（数值色 + 图标色）
_STAT_CARDS = [
    ("总消息数", _PRIMARY),
    ("群聊消息", _SUCCESS),
    ("私聊消息", _PURPLE),
    ("频道消息", _WARNING),
    ("平台数", _PRIMARY_DARK),
    ("数据表数量", (77, 208, 225)),
]

# 中文字体候选路径（跨平台）
_FONT_CANDIDATES = [
    # Linux 常见
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

_font_cache: Dict[int, ImageFont.FreeTypeFont] = {}
_default_font: Optional[ImageFont.FreeTypeFont] = None
_font_searched = False


def _find_font() -> Optional[ImageFont.FreeTypeFont]:
    """跨平台查找一个可用字体，优先支持中文。"""
    global _default_font, _font_searched
    if _font_searched:
        return _default_font
    _font_searched = True
    for candidate in _FONT_CANDIDATES:
        try:
            if Path(candidate).exists():
                _default_font = ImageFont.truetype(candidate, 20)
                return _default_font
        except Exception:
            continue
    try:
        _default_font = ImageFont.load_default()
    except Exception:
        _default_font = None
    return _default_font


def _font(size: int) -> ImageFont.FreeTypeFont:
    """获取指定大小的字体。"""
    if size in _font_cache:
        return _font_cache[size]
    base = _find_font()
    if base is None or not hasattr(base, "path"):
        font = base if base is not None else ImageFont.load_default()
    else:
        try:
            font = ImageFont.truetype(base.path, size)
        except Exception:
            font = base
    _font_cache[size] = font
    return font


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _truncate(draw, text: str, font, max_width: int) -> str:
    """按像素宽度截断文本，超宽加省略号。"""
    if not text:
        return ""
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    ew = _text_width(draw, ellipsis, font)
    for i in range(len(text) - 1, 0, -1):
        if _text_width(draw, text[:i], font) + ew <= max_width:
            return text[:i] + ellipsis
    return ellipsis


def _round_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """画圆角矩形（兼容 Pillow 各版本）。"""
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except AttributeError:
        x0, y0, x1, y1 = xy
        r = radius
        draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
        draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
        draw.pieslice([x0, y0, x0 + 2 * r, y0 + 2 * r], 180, 270, fill=fill)
        draw.pieslice([x1 - 2 * r, y0, x1, y0 + 2 * r], 270, 360, fill=fill)
        draw.pieslice([x0, y1 - 2 * r, x0 + 2 * r, y1], 90, 180, fill=fill)
        draw.pieslice([x1 - 2 * r, y1 - 2 * r, x1, y1], 0, 90, fill=fill)


def _gradient_bg(size) -> Image.Image:
    """纵向渐变背景，对齐 WebUI body 浅色渐变。用窄条放缩加速。"""
    w, h = size
    small = Image.new("RGB", (1, h))
    sp = small.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(_BG_TOP[0] + (_BG_BOTTOM[0] - _BG_TOP[0]) * t)
        g = int(_BG_TOP[1] + (_BG_BOTTOM[1] - _BG_TOP[1]) * t)
        b = int(_BG_TOP[2] + (_BG_BOTTOM[2] - _BG_TOP[2]) * t)
        sp[0, y] = (r, g, b)
    return small.resize((w, h), Image.BILINEAR)


def _draw_glass_card(img, xy, title: Optional[str] = None):
    """画一张半透明玻璃卡片，可选标题。返回内容区 (x0, y0, x1, y1)。"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    _round_rect(od, xy, _CARD_RADIUS, fill=_GLASS_BG, outline=_GLASS_BORDER, width=1)
    img.alpha_composite(overlay)
    x0, y0, x1, y1 = xy
    if title:
        draw = ImageDraw.Draw(img)
        f = _font(20)
        draw.text((x0 + 18, y0 + 14), title, font=f, fill=_TEXT)
        return (x0 + 18, y0 + 48, x1 - 18, y1 - 14)
    return (x0 + 18, y0 + 14, x1 - 18, y1 - 14)


def _draw_header(img, y, stats: MessageStats, db_table_count: int, generated_at: float):
    """绘制顶部标题栏。"""
    draw = ImageDraw.Draw(img)
    f_title = _font(30)
    f_sub = _font(16)
    title = "🦊 狐狸插件 · 仪表盘快照"
    draw.text((_PADDING, y), title, font=f_title, fill=_TEXT)
    sub = time.strftime("生成时间 %Y-%m-%d %H:%M:%S", time.localtime(generated_at))
    if stats.newest_timestamp:
        latest = time.strftime("最新消息 %Y-%m-%d %H:%M", time.localtime(stats.newest_timestamp / 1000))
        sub = sub + "  |  " + latest
    draw.text((_PADDING, y + 40), sub, font=f_sub, fill=_TEXT_LIGHT)
    return y + 70


def _draw_stat_cards(img, y, stats: MessageStats, db_table_count: int):
    """绘制统计卡片网格（2 行 × 3 列）。返回底部 y。"""
    values = [
        stats.total_count,
        stats.group_message_count,
        stats.private_message_count,
        stats.channel_message_count,
        len(stats.platform_stats),
        db_table_count,
    ]
    card_w = (_W - 2 * _PADDING - 2 * _CARD_GAP) // 3
    card_h = 92
    for idx in range(6):
        col = idx % 3
        row = idx // 3
        cx = _PADDING + col * (card_w + _CARD_GAP)
        cy = y + row * (card_h + _CARD_GAP)
        label, color = _STAT_CARDS[idx]
        _draw_glass_card(img, (cx, cy, cx + card_w, cy + card_h))

        draw = ImageDraw.Draw(img)
        # 左侧色条
        bar = Image.new("RGBA", (6, card_h - 24), color + (255,))
        img.paste(bar, (cx + 12, cy + 12), bar)

        f_val = _font(34)
        f_lbl = _font(15)
        val_str = f"{values[idx]:,}" if isinstance(values[idx], int) else str(values[idx])
        draw.text((cx + 30, cy + 16), val_str, font=f_val, fill=color)
        draw.text((cx + 30, cy + 60), label, font=f_lbl, fill=_TEXT_LIGHT)
    return y + 2 * card_h + _CARD_GAP + 10


def _draw_timeline(img, xy, timeline: List[Dict], width_px: int):
    """绘制消息时间趋势折线图 + 填充。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    if not timeline:
        draw = ImageDraw.Draw(img)
        draw.text((x0 + inner_w // 2 - 60, y0 + inner_h // 2), "暂无时间趋势数据", font=_font(16), fill=_TEXT_LIGHT)
        return

    counts = [p.get("count", 0) for p in timeline]
    max_c = max(counts) if counts else 1
    if max_c <= 0:
        max_c = 1
    n = len(timeline)
    step_x = inner_w / max(n - 1, 1) if n > 1 else inner_w

    # 计算点位
    points = []
    for i, c in enumerate(counts):
        px = x0 + (i * step_x if n > 1 else inner_w / 2)
        py = y1 - 8 - (c / max_c) * (inner_h - 30)
        points.append((px, py))

    draw = ImageDraw.Draw(img)

    # 横向网格线（半透明，用 overlay 合成）
    grid_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    god = ImageDraw.Draw(grid_overlay)
    for g in range(4):
        gy = y0 + 10 + g * (inner_h - 20) / 3
        god.line([(x0, gy), (x1, gy)], fill=(0, 0, 0, 18), width=1)
    img.alpha_composite(grid_overlay)

    # 填充区域
    if len(points) >= 2:
        fill_pts = points + [(points[-1][0], y1 - 8), (points[0][0], y1 - 8)]
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.polygon(fill_pts, fill=_PRIMARY + (60,))
        img.alpha_composite(overlay)

    # 折线
    if len(points) >= 2:
        draw.line(points, fill=_PRIMARY_DARK, width=3, joint="curve")
    # 数据点
    for px, py in points:
        draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=_PRIMARY_DARK, outline=_TEXT_WHITE, width=1)

    # X 轴标签（首/中/尾）
    f_lbl = _font(13)
    label_indices = []
    if n <= 6:
        label_indices = list(range(n))
    else:
        label_indices = [0, n // 2, n - 1]
    for i in label_indices:
        if 0 <= i < n:
            label = timeline[i].get("date", "")
            tw = _text_width(draw, label, f_lbl)
            lx = points[i][0] - tw / 2
            lx = max(x0, min(lx, x1 - tw))
            draw.text((lx, y1 - 4), label, font=f_lbl, fill=_TEXT_LIGHT)

    # Y 轴最大值标注
    draw.text((x0, y0 - 2), f"峰值 {max_c}", font=_font(13), fill=_TEXT_LIGHT)


def _draw_ranking(img, xy, title: str, items: List[Dict], name_key: str, count_key: str, color):
    """绘制排行榜列表（带横向进度条）。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    if not items:
        draw = ImageDraw.Draw(img)
        draw.text((x0 + 10, y0 + 10), "暂无数据", font=_font(15), fill=_TEXT_LIGHT)
        return

    draw = ImageDraw.Draw(img)
    f_name = _font(16)
    f_count = _font(15)
    f_rank = _font(14)
    max_c = max((it.get(count_key, 0) for it in items), default=1) or 1
    row_h = 38
    for i, it in enumerate(items[:8]):
        ry = y0 + i * row_h
        if ry + row_h > y1:
            break
        name = str(it.get(name_key) or it.get("sender_id") or it.get("group_id") or "未知")
        name = _truncate(draw, name, f_name, inner_w - 130)
        count = it.get(count_key, 0)
        count_str = f"{count:,}"
        # 排名
        rank_color = _WARNING if i == 0 else (_TEXT_LIGHT if i > 2 else color)
        draw.text((x0, ry), f"{i + 1}", font=f_rank, fill=rank_color)
        draw.text((x0 + 24, ry), name, font=f_name, fill=_TEXT)
        # 进度条
        bar_y = ry + 24
        bar_w = inner_w - 130
        _round_rect(draw, (x0 + 24, bar_y, x0 + 24 + bar_w, bar_y + 6), 3, fill=(226, 232, 240))
        fill_w = int(bar_w * (count / max_c))
        if fill_w > 0:
            _round_rect(draw, (x0 + 24, bar_y, x0 + 24 + fill_w, bar_y + 6), 3, fill=color)
        # 数值
        cw = _text_width(draw, count_str, f_count)
        draw.text((x1 - cw, ry + 2), count_str, font=f_count, fill=_TEXT)


def _draw_content_types(img, xy, content_types: List[Dict]):
    """绘制内容类型分布（横向条形图）。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    if not content_types:
        draw = ImageDraw.Draw(img)
        draw.text((x0 + 10, y0 + 10), "暂无数据", font=_font(15), fill=_TEXT_LIGHT)
        return

    draw = ImageDraw.Draw(img)
    f_label = _font(15)
    f_count = _font(14)
    items = content_types[:8]
    max_c = max((it.get("count", 0) for it in items), default=1) or 1
    total = sum((it.get("count", 0) for it in content_types), 0) or 1
    row_h = 34
    for i, it in enumerate(items):
        ry = y0 + i * row_h
        if ry + row_h > y1:
            break
        label = str(it.get("label", it.get("type", "")))
        count = it.get("count", 0)
        pct = count * 100 / total
        color = _CHART_COLORS[i % len(_CHART_COLORS)]
        # 色块
        draw.ellipse([x0, ry + 4, x0 + 12, ry + 16], fill=color)
        draw.text((x0 + 20, ry), label, font=f_label, fill=_TEXT)
        # 条形
        bar_x = x0 + 130
        bar_w = inner_w - 230
        _round_rect(draw, (bar_x, ry + 6, bar_x + bar_w, ry + 14), 4, fill=(226, 232, 240))
        fill_w = int(bar_w * (count / max_c))
        if fill_w > 0:
            _round_rect(draw, (bar_x, ry + 6, bar_x + fill_w, ry + 14), 4, fill=color)
        # 数值 + 百分比
        txt = f"{count:,} ({pct:.1f}%)"
        tw = _text_width(draw, txt, f_count)
        draw.text((x1 - tw, ry + 1), txt, font=f_count, fill=_TEXT_LIGHT)


def render_snapshot(
    stats: MessageStats,
    db_table_count: int,
    timeline: List[Dict],
    sender_ranking: List[Dict],
    group_ranking: List[Dict],
    content_types: List[Dict],
    generated_at: Optional[float] = None,
) -> bytes:
    """渲染仪表盘快照 PNG，返回 PNG 字节数据。

    Args:
        stats: MessageStats 统计对象
        db_table_count: 数据库业务表数量
        timeline: 时间趋势数据 [{"date","count",...}]
        sender_ranking: 发送者排行 [{"sender_id","sender_name","platform","count"}]
        group_ranking: 群组排行 [{"group_id","platform","count","sender_count"}]
        content_types: 内容类型统计 [{"type","label","count"}]
        generated_at: 生成时间戳，默认当前
    """
    if generated_at is None:
        generated_at = time.time()

    img = Image.new("RGBA", (_W, 1800), (255, 255, 255, 255))
    # 背景
    bg = _gradient_bg((_W, 1800)).convert("RGBA")
    img.alpha_composite(bg)

    y = _PADDING
    y = _draw_header(img, y, stats, db_table_count, generated_at)
    y += 14
    y = _draw_stat_cards(img, y, stats, db_table_count)
    y += 18

    # 时间趋势卡片（全宽）
    chart_h = 240
    _draw_glass_card(img, (_PADDING, y, _W - _PADDING, y + chart_h + 44), title="消息时间趋势")
    _draw_timeline(img, (_PADDING + 18, y + 52, _W - _PADDING - 18, y + chart_h + 30), timeline, _W - 2 * _PADDING - 36)
    y += chart_h + 44 + 18

    # 发送者排行 + 群组排行（左右各半）
    half_w = (_W - 2 * _PADDING - _CARD_GAP) // 2
    rank_h = 340
    left_xy = (_PADDING, y, _PADDING + half_w, y + rank_h)
    right_xy = (_PADDING + half_w + _CARD_GAP, y, _W - _PADDING, y + rank_h)
    _draw_glass_card(img, left_xy, title="发送者排行 Top 8")
    _draw_glass_card(img, right_xy, title="群组活跃度排行 Top 8")

    # 群组名补充平台信息
    for g in group_ranking:
        gid = str(g.get("group_id") or "")
        plat = str(g.get("platform") or "")
        if gid and plat:
            g["display_name"] = f"{gid} ({plat})"
        else:
            g["display_name"] = gid or plat or "未知"

    _draw_ranking(
        img,
        (left_xy[0] + 18, left_xy[1] + 52, left_xy[2] - 18, left_xy[3] - 14),
        "发送者排行", sender_ranking, "sender_name", "count", _PRIMARY_DARK,
    )
    _draw_ranking(
        img,
        (right_xy[0] + 18, right_xy[1] + 52, right_xy[2] - 18, right_xy[3] - 14),
        "群组排行", group_ranking, "display_name", "count", _SUCCESS,
    )
    y += rank_h + 18

    # 内容类型分布（全宽）
    ct_h = 320
    _draw_glass_card(img, (_PADDING, y, _W - _PADDING, y + ct_h), title="消息内容类型分布")
    _draw_content_types(img, (_PADDING + 18, y + 52, _W - _PADDING - 18, y + ct_h - 14), content_types)
    y += ct_h + 18

    # 底部水印
    draw = ImageDraw.Draw(img)
    f_foot = _font(13)
    foot = "由狐狸插件 /msg_record snapshot 生成 · Liquid Glass 风格"
    draw.text((_PADDING, y), foot, font=f_foot, fill=_TEXT_LIGHT)

    # 裁剪到实际高度
    final_h = y + 30
    img = img.crop((0, 0, _W, final_h))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
