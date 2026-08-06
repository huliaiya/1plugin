"""WebUI 仪表盘快照渲染器

用 Pillow 把数据库统计数据渲染成一张与 WebUI 风格一致的 PNG，
供 /msg_record snapshot 指令直接发到聊天。

视觉对齐 pages/recorder 的 Liquid Glass UI：
1. 浅色渐变背景 + 柔和光斑（饱和度克制）
2. 玻璃卡片：半透白 0.55 + 模糊背景 + 投影 + 内部彩色光斑
3. stat-value 蓝色渐变文字
4. 2x 超采样 + LANCZOS 降采样保证清晰
5. NotoSansCJK 矢量字体 + NotoColorEmoji 彩色 emoji
"""

import io
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .models import MessageStats


# ========== 渲染尺度（2x 超采样绘制，最后降到目标宽度）==========

_SCALE = 2
_W = 1080
_W_FULL = _W * _SCALE
_PX = lambda v: int(v * _SCALE)

# ========== 布局常量 ==========

_PADDING = 34
_CARD_RADIUS = 22
_CARD_GAP = 18

# ========== 色彩（对齐 WebUI :root 变量）==========

_BG_TOP = (240, 247, 255)
_BG_BOTTOM = (252, 228, 236)

_PRIMARY = (79, 195, 247)
_PRIMARY_DARK = (2, 136, 209)
_SUCCESS = (16, 185, 129)
_WARNING = (245, 158, 11)
_DANGER = (239, 68, 68)
_PURPLE = (139, 92, 246)

_TEXT = (30, 41, 59)
_TEXT_LIGHT = (100, 116, 139)
_TEXT_WHITE = (255, 255, 255)

# 玻璃材质（对齐 --glass-bg: rgba(255,255,255,0.55)）
_GLASS_FILL = (255, 255, 255, 140)
_GLASS_BORDER = (255, 255, 255, 115)
_GLASS_HIGHLIGHT = (255, 255, 255, 90)
_TRACK = (226, 232, 240, 210)
_SHADOW = (0, 0, 0, 18)

# stat-value 蓝色渐变（对齐 .rainbow-text）
_GRADIENT_BLUE = [
    (79, 195, 247),
    (41, 182, 246),
    (3, 169, 244),
    (100, 181, 246),
    (129, 212, 250),
    (179, 229, 252),
    (77, 208, 225),
]

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

_STAT_CARDS = [
    ("总消息数", _PRIMARY),
    ("群聊消息", _SUCCESS),
    ("私聊消息", _PURPLE),
    ("频道消息", _WARNING),
    ("平台数", _PRIMARY_DARK),
    ("数据表数量", (77, 208, 225)),
]


# ========== 字体 ==========

_FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
_FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

_FONT_FALLBACK = [
    _FONT_REG,
    _FONT_BOLD,
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
_emoji_font: Optional[ImageFont.FreeTypeFont] = None
_emoji_font_inited = False


def _resolve_font(bold: bool) -> Optional[str]:
    target = _FONT_BOLD if bold else _FONT_REG
    if Path(target).exists():
        return target
    for c in _FONT_FALLBACK:
        if Path(c).exists():
            return c
    return None


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = ("bold" if bold else "reg", size)
    cached = _font_cache.get(key)
    if cached:
        return cached
    path = _resolve_font(bold)
    if path is None:
        f = ImageFont.load_default()
        _font_cache[key] = f
        return f
    for index in (2, 0):
        try:
            f = ImageFont.truetype(path, size, index=index)
            _font_cache[key] = f
            return f
        except Exception:
            continue
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


def _get_emoji_font() -> Optional[ImageFont.FreeTypeFont]:
    global _emoji_font, _emoji_font_inited
    if _emoji_font_inited:
        return _emoji_font
    _emoji_font_inited = True
    if not Path(_EMOJI_FONT).exists():
        _emoji_font = None
        return None
    try:
        _emoji_font = ImageFont.truetype(_EMOJI_FONT, 109)
    except Exception:
        _emoji_font = None
    return _emoji_font


# ========== emoji 识别与绘制 ==========


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    if 0x1F300 <= cp <= 0x1FAFF:
        return True
    if 0x2300 <= cp <= 0x23FF:
        return True
    if 0x2600 <= cp <= 0x27BF:
        return True
    if 0x200D <= cp <= 0x200D:
        return True
    if 0xFE00 <= cp <= 0xFE0F:
        return True
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return True
    return False


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    return draw.textbbox((0, 0), text, font=font)[2]


def _text_width(draw, text: str, font) -> int:
    return _measure_text(draw, text, font)


def _paste_emoji(canvas: Image.Image, xy, ch: str, ref_font, draw):
    """渲染单个 emoji：以 109px 原尺寸绘制后 LANCZOS 下采样到目标大小，保证清晰。"""
    emoji_font = _get_emoji_font()
    if emoji_font is None:
        draw.text(xy, ch, font=ref_font, fill=(120, 120, 120))
        return
    # 目标尺寸：稍大于字体大小，保证视觉平衡
    target = int(ref_font.size * 1.15)
    # 以 109px 原尺寸渲染到独立图层
    raw_size = 109
    layer = Image.new("RGBA", (raw_size + 8, raw_size + 8), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    try:
        ld.text((4, 4), ch, font=emoji_font, embedded_color=True)
    except TypeError:
        ld.text((4, 4), ch, font=emoji_font)
    # LANCZOS 高质量下采样到目标尺寸
    layer = layer.resize((target, target), Image.LANCZOS)
    x, y = xy
    # 垂直微调，让 emoji 与文字基线对齐
    y_off = int(ref_font.size * 0.02)
    canvas.paste(layer, (int(x), int(y - y_off)), layer)


def _draw_text(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, canvas: Image.Image):
    """绘制文本，遇 emoji 用彩色字体单独贴图。"""
    x, y = xy
    if not text:
        return
    emoji_font = _get_emoji_font()
    buf = ""
    cx = x
    for ch in text:
        if _is_emoji(ch) and emoji_font is not None:
            if buf:
                draw.text((cx, y), buf, font=font, fill=fill)
                cx += _measure_text(draw, buf, font)
                buf = ""
            _paste_emoji(canvas, (cx, y), ch, font, draw)
            cx += int(font.size * 1.0)
        else:
            buf += ch
    if buf:
        draw.text((cx, y), buf, font=font, fill=fill)


# ========== 基础图形工具 ==========


def _truncate(draw, text: str, font, max_width: int) -> str:
    if not text or _text_width(draw, text, font) <= max_width:
        return text or ""
    ellipsis = "…"
    ew = _text_width(draw, ellipsis, font)
    for i in range(len(text) - 1, 0, -1):
        if _text_width(draw, text[:i], font) + ew <= max_width:
            return text[:i] + ellipsis
    return ellipsis


def _round_rect(draw, xy, radius, fill=None, outline=None, width=1):
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


def _draw_gradient_text(draw, xy, text, font, colors, canvas):
    """绘制水平渐变文字（模拟 -webkit-background-clip: text）。"""
    x, y = xy
    if not text:
        return
    w = _text_width(draw, text, font)
    if w <= 0:
        return
    # 逐像素列采样渐变色
    seg = max(w // len(colors), 1)
    cx = x
    for i, ch in enumerate(text):
        cw = _measure_text(draw, ch, font)
        t = (cx - x) / max(w, 1)
        idx = int(t * (len(colors) - 1))
        color = colors[min(idx, len(colors) - 1)]
        draw.text((cx, y), ch, font=font, fill=color)
        cx += cw


# ========== 背景（对齐 WebUI body 背景）==========


def _make_background(size) -> Image.Image:
    """浅色渐变 + 柔和光斑背景（对齐 WebUI body）。"""
    w, h = size
    small = Image.new("RGB", (max(w, 1), 2))
    small.paste(_BG_TOP, (0, 0, max(w, 1), 1))
    small.paste(_BG_BOTTOM, (0, 1, max(w, 1), 2))
    bg = small.resize((w, h), Image.BILINEAR).convert("RGBA")

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    blobs = [
        (int(w * 0.15), int(h * 0.05), int(w * 0.26), (79, 195, 247, 32)),
        (int(w * 0.85), int(h * 0.95), int(w * 0.24), (41, 182, 246, 28)),
        (int(w * 0.50), int(h * 0.50), int(w * 0.20), (255, 183, 77, 18)),
        (int(w * 0.70), int(h * 0.30), int(w * 0.18), (129, 199, 132, 16)),
    ]
    for cx, cy, r, color in blobs:
        od.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(_PX(80)))
    bg.alpha_composite(overlay)
    return bg


# ========== 毛玻璃卡片（对齐 WebUI .card / .stat-card）==========


def _draw_glass_card(img: Image.Image, blurred_bg: Image.Image, xy, title: Optional[str] = None, accent: Optional[Tuple] = None):
    """绘制毛玻璃卡片，返回内容区 (x0, y0, x1, y1)。

    对齐 WebUI：
    - backdrop-filter blur(14px) saturate(150%)：预模糊背景 + 提亮
    - box-shadow：投影
    - border 1px rgba(255,255,255,0.45)
    - 顶部内高光 inset 0 1px 0 rgba(255,255,255,0.6)
    - 内部彩色光斑 ::after radial-gradient
    """
    x0, y0, x1, y1 = xy
    cw, ch = x1 - x0, y1 - y0
    pad = _PX(8)

    # 投影（对齐 box-shadow 0 8px 32px rgba(0,0,0,0.08)）
    shadow = Image.new("RGBA", (cw + _PX(20), ch + _PX(20)), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [_PX(10), _PX(10), cw + _PX(10), ch + _PX(10)],
        radius=_CARD_RADIUS, fill=(0, 0, 0, 22),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(_PX(10)))
    img.paste(shadow, (x0 - _PX(10), y0 - _PX(4)), shadow)

    # 毛玻璃本体：预模糊背景取区 + 半透白提亮
    region = blurred_bg.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    bright = Image.new("RGBA", region.size, _GLASS_FILL)
    region.alpha_composite(bright)
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [pad, pad, region.width - pad, region.height - pad],
        radius=_CARD_RADIUS, fill=255,
    )
    img.paste(region, (x0 - pad, y0 - pad), mask)

    # 装饰层：顶部高光 + 内描边 + 内部彩色光斑（一次 paste）
    deco = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)

    # 内部彩色光斑（对齐 .stat-card::after）
    if accent:
        spot = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spot)
        sd.ellipse([int(cw * 0.1), int(ch * 0.1), int(cw * 0.7), int(ch * 0.7)],
                   fill=accent + (22,))
        spot = spot.filter(ImageFilter.GaussianBlur(_PX(30)))
        deco.alpha_composite(spot)

    # 顶部高光渐变（对齐 inset 0 1px 0 rgba(255,255,255,0.6)）
    hl_h = int(ch * 0.4)
    for yy in range(hl_h):
        t = yy / max(hl_h - 1, 1)
        a = int(_GLASS_HIGHLIGHT[3] * (1 - t) ** 1.2)
        dd.line([(0, yy), (cw, yy)], fill=(255, 255, 255, a))

    # 内描边（对齐 border 1px rgba(255,255,255,0.45)）
    _round_rect(dd, (0, 0, cw, ch), _CARD_RADIUS, outline=_GLASS_BORDER, width=_PX(1))

    img.paste(deco, (x0, y0), deco)

    if title:
        draw = ImageDraw.Draw(img)
        f = _get_font(_PX(22), bold=True)
        _draw_text(draw, (x0 + _PX(20), y0 + _PX(16)), title, f, _TEXT, img)
        line = Image.new("RGBA", (x1 - x0 - _PX(40), 1), (0, 0, 0, 24))
        img.paste(line, (x0 + _PX(20), y0 + _PX(54)))
        return (x0 + _PX(20), y0 + _PX(66), x1 - _PX(20), y1 - _PX(16))
    return (x0 + _PX(20), y0 + _PX(16), x1 - _PX(20), y1 - _PX(16))


# ========== 区块绘制 ==========


def _draw_header(img, y, stats: MessageStats, generated_at: float):
    draw = ImageDraw.Draw(img)
    f_title = _get_font(_PX(34), bold=True)
    f_sub = _get_font(_PX(17))
    x = _PADDING * _SCALE
    _paste_emoji(img, (x, y), "🦊", f_title, draw)
    x += int(f_title.size * 1.3)
    _draw_text(draw, (x, y), "狐狸插件 · 仪表盘快照", f_title, _TEXT, img)

    sub = time.strftime("生成时间 %Y-%m-%d %H:%M:%S", time.localtime(generated_at))
    if stats.newest_timestamp:
        latest = time.strftime("最新消息 %m-%d %H:%M", time.localtime(stats.newest_timestamp / 1000))
        sub = sub + "  ·  " + latest
    _draw_text(draw, (_PADDING * _SCALE, y + _PX(46)), sub, f_sub, _TEXT_LIGHT, img)
    return y + _PX(80)


def _draw_stat_cards(img, blurred_bg, y, stats: MessageStats, db_table_count: int):
    values = [
        stats.total_count,
        stats.group_message_count,
        stats.private_message_count,
        stats.channel_message_count,
        len(stats.platform_stats),
        db_table_count,
    ]
    gap = _PX(_CARD_GAP)
    card_w = (_W_FULL - _PX(_PADDING) * 2 - gap * 2) // 3
    card_h = _PX(104)
    draw = ImageDraw.Draw(img)
    for idx in range(6):
        col = idx % 3
        row = idx // 3
        cx = _PX(_PADDING) + col * (card_w + gap)
        cy = y + row * (card_h + gap)
        label, color = _STAT_CARDS[idx]
        _draw_glass_card(img, blurred_bg, (cx, cy, cx + card_w, cy + card_h), accent=color)

        f_val = _get_font(_PX(38), bold=True)
        f_lbl = _get_font(_PX(16))
        val_str = f"{values[idx]:,}" if isinstance(values[idx], int) else str(values[idx])
        # stat-value 蓝色渐变文字（对齐 .stat-value）
        vw = _text_width(draw, val_str, f_val)
        vx = cx + (card_w - vw) // 2
        _draw_gradient_text(draw, (vx, cy + _PX(18)), val_str, f_val, _GRADIENT_BLUE, img)
        # 标签居中
        lw = _text_width(draw, label, f_lbl)
        _draw_text(draw, (cx + (card_w - lw) // 2, cy + _PX(68)), label, f_lbl, _TEXT_LIGHT, img)
    return y + 2 * card_h + gap + _PX(10)


def _draw_timeline(img, xy, timeline: List[Dict]):
    """多系列时间趋势折线图（对齐 WebUI：总/群/私/频道四色线）。

    数据点结构：{"date","count","group_count","private_count","channel_count"}
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if not timeline:
        _draw_text(draw, (x0 + inner_w // 2 - _PX(60), y0 + inner_h // 2), "暂无时间趋势数据", _get_font(_PX(16)), _TEXT_LIGHT, img)
        return

    # 系列定义（对齐 WebUI timelineChart 配色）
    series_defs = [
        ("总消息", "count", (79, 195, 247)),
        ("群聊", "group_count", (102, 187, 106)),
        ("私聊", "private_count", (255, 167, 38)),
        ("频道", "channel_count", (239, 83, 80)),
    ]

    n = len(timeline)
    step_x = inner_w / max(n - 1, 1) if n > 1 else inner_w

    # 计算每系列数据点（纵坐标以全系列最大值为基准，统一刻度）
    series_points = []
    max_c = 1
    for label, key, color in series_defs:
        pts = []
        for i, p in enumerate(timeline):
            v = p.get(key, 0) or 0
            if v > max_c:
                max_c = v
            pts.append(v)
        series_points.append((label, key, color, pts))
    max_c = max(max_c, 1)

    # 图表区局部图层（网格、面积、折线、点一次性绘制）
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    for g in range(4):
        gy = y0 + _PX(12) + g * (inner_h - _PX(24)) / 3
        ld.line([(x0, gy), (x1, gy)], fill=(0, 0, 0, 16), width=_PX(1))

    def to_points(vals):
        pts = []
        for i, v in enumerate(vals):
            px = x0 + (i * step_x if n > 1 else inner_w / 2)
            py = y1 - _PX(10) - (v / max_c) * (inner_h - _PX(36))
            pts.append((px, py))
        return pts

    # 先画"总消息"区域填充，再画全部折线（总最粗且在最上）
    for idx, (label, key, color, vals) in enumerate(series_points):
        pts = to_points(vals)
        if idx == 0 and len(pts) >= 2:
            fill_pts = pts + [(pts[-1][0], y1 - _PX(8)), (pts[0][0], y1 - _PX(8))]
            ld.polygon(fill_pts, fill=color + (40,))

    for idx, (label, key, color, vals) in enumerate(series_points):
        pts = to_points(vals)
        if len(pts) < 2:
            continue
        width = _PX(4) if idx == 0 else _PX(2)
        ld.line(pts, fill=color + (255,), width=width, joint="curve")
        r = _PX(4) if idx == 0 else _PX(3)
        for px, py in pts:
            ld.ellipse([px - r, py - r, px + r, py + r], fill=_TEXT_WHITE, outline=color, width=_PX(2))

    img.alpha_composite(layer)

    # 图例（左上角，对齐 WebUI legend 四色）
    f_legend = _get_font(_PX(12))
    lx = x0
    ly = y0 - _PX(2)
    for label, key, color in series_defs:
        lw = _text_width(draw, label, f_legend)
        dot = Image.new("RGBA", (int(lw + _PX(16)), _PX(12)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot)
        dd.ellipse([0, _PX(3), _PX(9), _PX(3) + _PX(9)], fill=color + (255,))
        img.paste(dot, (int(lx), int(ly)), dot)
        _draw_text(draw, (lx + _PX(14), ly), label, f_legend, _TEXT, img)
        lx += _PX(14) + lw + _PX(18)

    # X 轴标签
    f_lbl = _get_font(_PX(13))
    label_indices = list(range(n)) if n <= 6 else [0, n // 2, n - 1]
    for i in label_indices:
        if 0 <= i < n:
            label = str(timeline[i].get("date", ""))[-5:]
            tw = _text_width(draw, label, f_lbl)
            px = x0 + (i * step_x if n > 1 else inner_w / 2)
            lpx = px - tw / 2
            lpx = max(x0, min(lpx, x1 - tw))
            _draw_text(draw, (lpx, y1 - _PX(2)), label, f_lbl, _TEXT_LIGHT, img)

    _draw_text(draw, (x0, y0 + _PX(18)), f"峰值 {max_c:,}", _get_font(_PX(12)), _TEXT_LIGHT, img)


def _draw_ranking(img, xy, items: List[Dict], name_key: str, count_key: str, color):
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    draw = ImageDraw.Draw(img)
    if not items:
        _draw_text(draw, (x0 + _PX(10), y0 + _PX(10)), "暂无数据", _get_font(_PX(15)), _TEXT_LIGHT, img)
        return

    f_name = _get_font(_PX(16))
    f_count = _get_font(_PX(15))
    f_rank = _get_font(_PX(14), bold=True)
    max_c = max((it.get(count_key, 0) for it in items), default=1) or 1
    row_h = _PX(40)
    top3 = [_WARNING, (192, 192, 192), (205, 127, 50)]
    for i, it in enumerate(items[:8]):
        ry = y0 + i * row_h
        if ry + row_h > y1:
            break
        name = str(it.get(name_key) or it.get("sender_id") or it.get("group_id") or "未知")
        name = _truncate(draw, name, f_name, inner_w - _PX(140))
        count = it.get(count_key, 0)
        count_str = f"{count:,}"

        rank_color = top3[i] if i < 3 else _TEXT_LIGHT
        badge = Image.new("RGBA", (inner_w, row_h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge)
        rr = _PX(11)
        bd.ellipse([0, _PX(4), rr * 2, _PX(4) + rr * 2], fill=rank_color + (235,))
        img.paste(badge, (x0, ry), badge)
        rank_txt = str(i + 1)
        rw = _text_width(draw, rank_txt, f_rank)
        _draw_text(draw, (x0 + rr - rw / 2, ry + _PX(2)), rank_txt, f_rank, _TEXT_WHITE, img)

        _draw_text(draw, (x0 + _PX(30), ry + _PX(2)), name, f_name, _TEXT, img)

        bar_y = ry + _PX(26)
        bar_w = inner_w - _PX(140)
        bar = Image.new("RGBA", (bar_w, _PX(7)), (0, 0, 0, 0))
        bd2 = ImageDraw.Draw(bar)
        _round_rect(bd2, (0, 0, bar_w, _PX(7)), _PX(4), fill=_TRACK)
        fill_w = int(bar_w * (count / max_c))
        if fill_w > 0:
            _round_rect(bd2, (0, 0, fill_w, _PX(7)), _PX(4), fill=color + (255,))
        img.paste(bar, (x0 + _PX(30), bar_y), bar)

        cw = _text_width(draw, count_str, f_count)
        _draw_text(draw, (x1 - cw, ry + _PX(3)), count_str, f_count, _TEXT, img)


_PLATFORM_LABELS = {
    "telegram": "Telegram",
    "discord": "Discord",
    "qq_official": "QQ 官方",
    "qq_private": "QQ 私有",
    "wechat": "微信",
}


def _draw_platform_donut(img, xy, platform_stats: Dict[str, int]):
    """平台分布圆环图（对齐 WebUI platformChart：饼图 + 右侧图例）。

    platform_stats: {platform_key: count}
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if not platform_stats:
        _draw_text(draw, (x0 + inner_w // 2 - _PX(50), y0 + inner_h // 2), "暂无平台数据", _get_font(_PX(15)), _TEXT_LIGHT, img)
        return

    items = sorted(platform_stats.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1

    # 圆环布局：左侧圆环，右侧图例（对齐 WebUI center 40% / legend right 5%）
    donut_d = min(inner_h, inner_w * 0.5)
    donut_r_out = donut_d / 2
    donut_r_in = donut_r_out * 0.55
    cx = x0 + donut_r_out + _PX(8)
    cy = y0 + inner_h / 2

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    start = -90.0
    for idx, (plat, val) in enumerate(items):
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
        ld.pieslice(
            [cx - donut_r_out, cy - donut_r_out, cx + donut_r_out, cy + donut_r_out],
            start, start + sweep, fill=color + (255,),
        )
        start += sweep

    # 中心镂空：用 alpha 0 擦除内圆区域，形成真正的圆环
    mask = Image.new("L", layer.size, 255)
    ImageDraw.Draw(mask).ellipse(
        [cx - donut_r_in, cy - donut_r_in, cx + donut_r_in, cy + donut_r_in],
        fill=0,
    )
    layer.putalpha(mask)
    img.alpha_composite(layer)

    # 中心总量文字
    f_total = _get_font(_PX(26), bold=True)
    f_total_lbl = _get_font(_PX(13))
    total_str = f"{total:,}"
    tw = _text_width(draw, total_str, f_total)
    _draw_gradient_text(draw, (cx - tw / 2, cy - _PX(22)), total_str, f_total, _GRADIENT_BLUE, img)
    lw = _text_width(draw, "总消息", f_total_lbl)
    _draw_text(draw, (cx - lw / 2, cy + _PX(12)), "总消息", f_total_lbl, _TEXT_LIGHT, img)

    # 右侧图例
    f_name = _get_font(_PX(16))
    f_count = _get_font(_PX(15))
    row_h = _PX(38)
    legend_x = x0 + donut_d + _PX(40)
    legend_w = x1 - legend_x
    max_rows = max(1, int(inner_h // row_h))
    for idx, (plat, val) in enumerate(items[:max_rows]):
        ry = y0 + idx * row_h
        if ry + row_h > y1:
            break
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        label = _PLATFORM_LABELS.get(plat, plat or "未知")
        pct = val * 100 / total

        dot = Image.new("RGBA", (inner_w, row_h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot)
        dd.ellipse([0, _PX(6), _PX(16), _PX(6) + _PX(16)], fill=color + (255,))
        img.paste(dot, (legend_x, ry), dot)
        _draw_text(draw, (legend_x + _PX(24), ry + _PX(2)), label, f_name, _TEXT, img)

        bar_x = legend_x + _PX(24)
        bar_y = ry + _PX(26)
        bar_w = legend_w - _PX(24)
        bar = Image.new("RGBA", (bar_w, _PX(7)), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar)
        _round_rect(bd, (0, 0, bar_w, _PX(7)), _PX(4), fill=_TRACK)
        fill_w = int(bar_w * (val / total))
        if fill_w > 0:
            _round_rect(bd, (0, 0, fill_w, _PX(7)), _PX(4), fill=color + (255,))
        img.paste(bar, (bar_x, bar_y), bar)

        txt = f"{val:,} ({pct:.1f}%)"
        tw2 = _text_width(draw, txt, f_count)
        _draw_text(draw, (x1 - tw2, ry + _PX(3)), txt, f_count, _TEXT_LIGHT, img)


def _draw_content_types(img, xy, content_types: List[Dict]):
    """绘制内容类型分布饼图，对齐 WebUI 的 contentTypeChart。
    
    Args:
        img: PIL Image 对象
        xy: 绘制区域 (x0, y0, x1, y1)
        content_types: 内容类型统计 [{"type","label","count"}]
    """
    x0, y0, x1, y1 = xy
    draw = ImageDraw.Draw(img)
    
    if not content_types:
        _draw_text(draw, (x0 + _PX(20), y0 + _PX(20)), "暂无内容类型数据", _get_font(_PX(14)), _TEXT_LIGHT, img)
        return

    # 计算总数和各类型占比
    total = sum(ct.get('count', 0) for ct in content_types)
    if total == 0:
        _draw_text(draw, (x0 + _PX(20), y0 + _PX(20)), "暂无内容类型数据", _get_font(_PX(14)), _TEXT_LIGHT, img)
        return

    # 饼图参数（对齐 WebUI）
    chart_center_x = x0 + int((x1 - x0) * 0.35)  # 35% 位置
    chart_center_y = y0 + int((y1 - y0) * 0.5)   # 垂直居中
    outer_radius = int((y1 - y0) * 0.28)         # 外径 28%
    inner_radius = int(outer_radius * 0.5)        # 内径 50%（甜甜圈）
    
    # 颜色（对齐 WebUI 的 colors 数组）
    colors = ['#4fc3f7', '#29b6f6', '#03a9f4', '#64b5f6', '#81d4fa', '#b3e5fc', '#4dd0e1', '#0288d1', '#039be5', '#80deea', '#26c6da', '#4fc3f7', '#29b6f6', '#64b5f6', '#81d4fa', '#4dd0e1']
    
    # 计算角度并绘制饼图
    current_angle = 0
    
    for i, ct in enumerate(content_types[:8]):  # 最多显示8种类型
        count = ct.get('count', 0)
        if count == 0:
            continue
            
        percentage = count / total
        angle = int(percentage * 360)
        
        if angle > 0:
            color = colors[i % len(colors)]
            
            # 绘制扇形（带圆角）
            start_angle = current_angle
            end_angle = current_angle + angle
            
            # 创建扇形路径
            points = []
            
            # 外圆弧
            for a in range(start_angle, end_angle + 1, 2):
                x = chart_center_x + outer_radius * math.cos(math.radians(a - 90))
                y = chart_center_y + outer_radius * math.sin(math.radians(a - 90))
                points.append((x, y))
            
            # 内圆弧（反向）
            for a in range(end_angle, start_angle - 1, -2):
                x = chart_center_x + inner_radius * math.cos(math.radians(a - 90))
                y = chart_center_y + inner_radius * math.sin(math.radians(a - 90))
                points.append((x, y))
            
            if len(points) >= 3:
                draw.polygon(points, fill=color)
            
            current_angle += angle
    
    # 绘制中心文字（总数量）
    total_text = f"{total}"
    label_text = "总消息"
    
    # 总数量
    _draw_text(draw, (chart_center_x, chart_center_y - _PX(10)), total_text, _get_font(_PX(20)), _TEXT_DARK, img)
    
    # 标签
    _draw_text(draw, (chart_center_x, chart_center_y + _PX(10)), label_text, _get_font(_PX(12)), _TEXT_LIGHT, img)
    
    # 绘制图例
    legend_x = x1 - _PX(180)  # 右侧图例
    legend_y = y0 + _PX(20)
    legend_item_height = _PX(30)
    
    for i, ct in enumerate(content_types[:8]):  # 最多显示8种类型
        count = ct.get('count', 0)
        if count == 0:
            continue
            
        percentage = (count / total) * 100
        color = colors[i % len(colors)]
        label = ct.get('label', ct.get('type', f'类型{i+1}'))
        
        # 颜色圆点
        draw.ellipse([legend_x, legend_y, legend_x + _PX(12), legend_y + _PX(12)], fill=color)
        
        # 类型名称
        _draw_text(draw, (legend_x + _PX(20), legend_y + _PX(4)), label, _get_font(_PX(12)), _TEXT_DARK, img)
        
        # 进度条背景
        progress_x = legend_x + _PX(100)
        progress_y = legend_y + _PX(8)
        progress_w = _PX(60)
        progress_h = _PX(4)
        
        draw.rectangle([progress_x, progress_y, progress_x + progress_w, progress_y + progress_h], fill=_GLASS_BG)
        
        # 进度条
        progress_fill_w = int(progress_w * percentage / 100)
        if progress_fill_w > 0:
            draw.rectangle([progress_x, progress_y, progress_x + progress_fill_w, progress_y + progress_h], fill=color)
        
        # 百分比数字
        _draw_text(draw, (progress_x + progress_w + _PX(8), legend_y + _PX(2)), f"{percentage:.1f}%", _get_font(_PX(11)), _TEXT_DARK, img)
        
        legend_y += legend_item_height


def _draw_platform_detail(img, xy, platforms: List[Dict]):
    """平台消息详情堆叠柱状图（对齐 WebUI platformDetailChart：各平台群聊/私聊/频道堆叠柱）。

    platforms: [{"platform","platform_name","total","group_count","private_count","channel_count",...}]
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if not platforms:
        _draw_text(draw, (x0 + inner_w // 2 - _PX(50), y0 + inner_h // 2), "暂无平台数据", _get_font(_PX(15)), _TEXT_LIGHT, img)
        return

    # 系列定义（对齐 WebUI platformDetailChart 配色，自下而上堆叠）
    series_defs = [
        ("群聊", "group_count", (79, 195, 247)),
        ("私聊", "private_count", (41, 182, 246)),
        ("频道", "channel_count", (129, 212, 250)),
    ]

    legend_h = _PX(20)
    label_h = _PX(26)
    chart_top = y0 + legend_h + _PX(8)
    chart_bottom = y1 - label_h
    chart_h = chart_bottom - chart_top

    def seg_total(p: Dict) -> int:
        return sum(p.get(k, 0) or 0 for _, k, _ in series_defs)

    max_total = max((seg_total(p) for p in platforms), default=1) or 1

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    for g in range(4):
        gy = chart_top + g * chart_h / 3
        ld.line([(x0, gy), (x1, gy)], fill=(0, 0, 0, 16), width=_PX(1))

    n = len(platforms)
    slot_w = inner_w / n
    bar_w = min(slot_w * 0.55, _PX(60))

    f_val = _get_font(_PX(12))
    for i, p in enumerate(platforms):
        cx_bar = x0 + slot_w * i + (slot_w - bar_w) / 2
        total = seg_total(p)
        if total <= 0:
            continue
        h_total = chart_h * total / max_total
        seg_bottom = chart_bottom
        for idx, (label, key, color) in enumerate(series_defs):
            v = p.get(key, 0) or 0
            if v <= 0:
                continue
            h = h_total * v / total
            seg_top = seg_bottom - h
            ld.rectangle([cx_bar, seg_top, cx_bar + bar_w, seg_bottom], fill=color + (255,))
            seg_bottom = seg_top

        # 顶部段圆角（对齐 WebUI 柱状图圆角质感）
        top_v = next((p.get(k, 0) for lbl, k, c in reversed(series_defs) if (p.get(k, 0) or 0) > 0), 0)
        top_h = h_total * top_v / total
        top_y = chart_bottom - h_total
        r = min(_PX(5), bar_w / 2, top_h / 2)
        if r > 1:
            top_color = next(c for lbl, k, c in reversed(series_defs) if (p.get(k, 0) or 0) > 0)
            ld.rounded_rectangle([cx_bar, top_y, cx_bar + bar_w, top_y + top_h], radius=r, fill=top_color + (255,))
            if top_h > r:
                ld.rectangle([cx_bar, top_y + top_h - r, cx_bar + bar_w, top_y + top_h], fill=top_color + (255,))

        # 柱顶总量
        total_str = f"{total:,}"
        tw = _text_width(draw, total_str, f_val)
        _draw_text(draw, (cx_bar + bar_w / 2 - tw / 2, top_y - _PX(18)), total_str, f_val, _TEXT_LIGHT, img)

    img.alpha_composite(layer)

    # 图例（左上角，对齐 WebUI legend 三色）
    f_legend = _get_font(_PX(12))
    lx = x0
    ly = y0 - _PX(2)
    for label, key, color in series_defs:
        lw = _text_width(draw, label, f_legend)
        dot = Image.new("RGBA", (int(lw + _PX(16)), _PX(12)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot)
        dd.ellipse([0, _PX(3), _PX(9), _PX(3) + _PX(9)], fill=color + (255,))
        img.paste(dot, (int(lx), int(ly)), dot)
        _draw_text(draw, (lx + _PX(14), ly), label, f_legend, _TEXT, img)
        lx += _PX(14) + lw + _PX(18)

    # X 轴平台名标签
    f_lbl = _get_font(_PX(13))
    for i, p in enumerate(platforms):
        label = _truncate(draw, str(p.get("platform_name") or p.get("platform") or "未知"), f_lbl, int(slot_w - _PX(6)))
        lw = _text_width(draw, label, f_lbl)
        lx = x0 + slot_w * i + (slot_w - lw) / 2
        _draw_text(draw, (lx, chart_bottom + _PX(8)), label, f_lbl, _TEXT_LIGHT, img)

    _draw_text(draw, (x0, y0 + _PX(18)), f"峰值 {max_total:,}", _get_font(_PX(12)), _TEXT_LIGHT, img)


# ========== 主入口 ==========


def render_snapshot(
    stats: MessageStats,
    db_table_count: int,
    timeline: List[Dict],
    sender_ranking: List[Dict],
    group_ranking: List[Dict],
    content_types: List[Dict],
    platform_stats: Optional[Dict[str, int]] = None,
    platform_detail: Optional[List[Dict]] = None,
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
        platform_stats: 平台分布统计 {platform: count}，默认取 stats.platform_stats
        platform_detail: 平台消息详情统计 [{"platform","platform_name","total","group_count","private_count","channel_count",...}]，默认取数据库查询结果
        generated_at: 生成时间戳，默认当前
    """
    if generated_at is None:
        generated_at = time.time()
    if platform_stats is None:
        platform_stats = stats.platform_stats or {}

    canvas_h = _PX(2800)
    img = _make_background((_W_FULL, canvas_h))
    # 预模糊背景一次，供所有毛玻璃卡片复用（对齐 backdrop-filter blur(14px)）
    blurred_bg = img.filter(ImageFilter.GaussianBlur(_PX(14)))

    y = _PX(_PADDING)
    y = _draw_header(img, y, stats, generated_at)
    y += _PX(14)
    y = _draw_stat_cards(img, blurred_bg, y, stats, db_table_count)
    y += _PX(18)

    # 时间趋势卡片
    chart_h = _PX(240)
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + chart_h + _PX(48)), title="消息时间趋势", accent=_PRIMARY)
    _draw_timeline(
        img,
        (_PX(_PADDING) + _PX(20), y + _PX(66), _W_FULL - _PX(_PADDING) - _PX(20), y + chart_h + _PX(34)),
        timeline,
    )
    y += chart_h + _PX(48) + _PX(18)

    # 平台分布卡片（对齐 WebUI platformChart 圆环图）
    plat_h = _PX(280)
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + plat_h), title="平台分布", accent=_PRIMARY_DARK)
    _draw_platform_donut(
        img,
        (_PX(_PADDING) + _PX(20), y + _PX(66), _W_FULL - _PX(_PADDING) - _PX(20), y + plat_h - _PX(16)),
        platform_stats,
    )
    y += plat_h + _PX(18)

    # 发送者 + 群组排行
    gap = _PX(_CARD_GAP)
    half_w = (_W_FULL - 2 * _PX(_PADDING) - gap) // 2
    rank_h = _PX(360)
    left_xy = (_PX(_PADDING), y, _PX(_PADDING) + half_w, y + rank_h)
    right_xy = (_PX(_PADDING) + half_w + gap, y, _W_FULL - _PX(_PADDING), y + rank_h)
    _draw_glass_card(img, blurred_bg, left_xy, title="发送者排行 Top 8", accent=_PRIMARY_DARK)
    _draw_glass_card(img, blurred_bg, right_xy, title="群组活跃度排行 Top 8", accent=_SUCCESS)

    for g in group_ranking:
        gid = str(g.get("group_id") or "")
        plat = str(g.get("platform") or "")
        g["display_name"] = f"{gid} ({plat})" if gid and plat else (gid or plat or "未知")

    _draw_ranking(
        img,
        (left_xy[0] + _PX(20), left_xy[1] + _PX(66), left_xy[2] - _PX(20), left_xy[3] - _PX(16)),
        sender_ranking, "sender_name", "count", _PRIMARY_DARK,
    )
    _draw_ranking(
        img,
        (right_xy[0] + _PX(20), right_xy[1] + _PX(66), right_xy[2] - _PX(20), right_xy[3] - _PX(16)),
        group_ranking, "display_name", "count", _SUCCESS,
    )
    y += rank_h + _PX(18)

    # 平台消息详情卡片（对齐 WebUI platformDetailChart）
    pd_h = _PX(300)
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + pd_h), title="平台消息详情", accent=_PRIMARY)
    _draw_platform_detail(
        img,
        (_PX(_PADDING) + _PX(20), y + _PX(66), _W_FULL - _PX(_PADDING) - _PX(20), y + pd_h - _PX(16)),
        platform_detail or [],
    )
    y += pd_h + _PX(18)

    # 内容类型分布
    ct_h = _PX(330)
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + ct_h), title="消息内容类型分布", accent=_PURPLE)
    _draw_content_types(
        img,
        (_PX(_PADDING) + _PX(20), y + _PX(66), _W_FULL - _PX(_PADDING) - _PX(20), y + ct_h - _PX(16)),
        content_types,
    )
    y += ct_h + _PX(18)

    # 底部水印
    draw = ImageDraw.Draw(img)
    _draw_text(draw, (_PX(_PADDING), y), "由狐狸插件 /msg_record snapshot 生成 · Liquid Glass 风格", _get_font(_PX(13)), _TEXT_LIGHT, img)

    final_h = y + _PX(34)
    img = img.crop((0, 0, _W_FULL, final_h))
    img = img.resize((_W, int(final_h / _SCALE)), Image.LANCZOS)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
