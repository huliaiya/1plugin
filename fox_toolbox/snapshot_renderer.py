"""WebUI 仪表盘快照渲染器 - 现代优雅版

用 Pillow 把数据库统计数据渲染成一张与 WebUI 风格一致的 PNG，
供 /huli_record snapshot 指令直接发到聊天。

视觉设计：
1. 渐变背景 - 淡蓝到淡紫的优雅渐变
2. 现代玻璃卡片 - 半透明白色背景 + 柔和阴影 + 细腻边框
3. 优雅的文字层次 - 清晰的对比度和层次感
4. 精美的图表 - 简洁而不失优雅的设计
5. 2x 超采样 + LANCZOS 降采样保证清晰
6. NotoSansCJK 矢量字体 + NotoColorEmoji 彩色 emoji
"""

import io
import math
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


def _to_int(value, default=0):
    """将任意类型的值安全转换为整数；无法转换时返回 default。

    兼容 MySQL 驱动可能返回的 Decimal、字符串数字、None 等类型，
    杜绝 'dict' object cannot be interpreted as an integer 之类报错。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (ValueError, TypeError):
            return default
    return default


# ========== 布局常量 ==========

_PADDING = 34
_CARD_RADIUS = 16
_CARD_GAP = 20


# ========== 色彩配置 ==========

# 渐变背景
_BG_GRADIENT_START = (240, 248, 255)  # 淡蓝色
_BG_GRADIENT_END = (248, 240, 255)    # 淡紫色
_BG_WHITE = (255, 255, 255)           # 纯白色

# 主色调
_PRIMARY = (59, 130, 246)      # 蓝色
_SUCCESS = (34, 197, 94)       # 绿色
_WARNING = (251, 191, 36)     # 黄色
_DANGER = (239, 68, 68)        # 红色
_PURPLE = (147, 51, 234)       # 紫色
_INDIGO = (99, 102, 241)       # 靛蓝色

# 文字颜色
_TEXT_DARK = (17, 24, 39)      # 深色文字
_TEXT_MEDIUM = (55, 65, 81)    # 中等灰色文字
_TEXT_LIGHT = (107, 114, 128)  # 浅灰色文字

# 现代玻璃效果
_GLASS_FILL = (255, 255, 255, 220)    # 85% 透明白色
_GLASS_BORDER = (229, 231, 235, 180) # 70% 透明边框
_GLASS_SHADOW = (0, 0, 0, 40)         # 柔和阴影

# 图表颜色
_CHART_COLORS = [
    (59, 130, 246),   # 蓝色
    (34, 197, 94),    # 绿色
    (251, 191, 36),   # 黄色
    (239, 68, 68),    # 红色
    (147, 51, 234),   # 紫色
    (99, 102, 241),   # 靛蓝色
    (236, 72, 153),   # 粉色
    (20, 184, 166),   # 青色
]

# 统计卡片配置
_STAT_CARDS = [
    ("总消息数", _PRIMARY),
    ("群聊消息", _SUCCESS),
    ("私聊消息", _PURPLE),
    ("频道消息", _WARNING),
    ("平台数", _INDIGO),
    ("数据表数量", (20, 184, 166)),
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


# ========== 文本处理 ==========

def _truncate(draw, text: str, font, max_width: int) -> str:
    if not text or _text_width(draw, text, font) <= max_width:
        return text or ""
    ellipsis = "…"
    ew = _text_width(draw, ellipsis, font)
    for i in range(len(text) - 1, 0, -1):
        if _text_width(draw, text[:i], font) + ew <= max_width:
            return text[:i] + ellipsis
    return ellipsis


def _truncate_middle(draw, text: str, font, max_width: int) -> str:
    """从中间省略长文本，保留首尾片段（对群 ID 等长串更友好）。"""
    if not text or _text_width(draw, text, font) <= max_width:
        return text or ""
    ellipsis = "…"
    ew = _text_width(draw, ellipsis, font)
    max_n = len(text) // 2
    n = 0
    for i in range(1, max_n + 1):
        if _text_width(draw, text[:i] + ellipsis + text[len(text) - i:], font) <= max_width:
            n = i
        else:
            break
    if n <= 0:
        return _truncate(draw, text, font, max_width)
    return text[:n] + ellipsis + text[len(text) - n:]


# ========== 基础图形 ==========

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


# ========== 背景 ==========

def _make_background(size) -> Image.Image:
    """优雅渐变背景。"""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 创建从左上到右下的渐变
    w, h = size
    for i in range(h):
        # 计算当前行的颜色
        ratio = i / h
        r = int(_BG_GRADIENT_START[0] * (1 - ratio) + _BG_GRADIENT_END[0] * ratio)
        g = int(_BG_GRADIENT_START[1] * (1 - ratio) + _BG_GRADIENT_END[1] * ratio)
        b = int(_BG_GRADIENT_START[2] * (1 - ratio) + _BG_GRADIENT_END[2] * ratio)
        draw.line([(0, i), (w, i)], fill=(r, g, b, 255))
    
    # 添加一些装饰性的光点
    import random
    random.seed(42)  # 固定种子，确保每次生成的光点位置相同
    for _ in range(20):
        x = random.randint(0, w)
        y = random.randint(0, h)
        radius = random.randint(50, 150)
        color = random.choice([(255, 255, 255, 30), (240, 248, 255, 20)])
        for i in range(radius):
            alpha = int(30 * (1 - i / radius))
            if alpha > 0:
                draw.ellipse([x - i, y - i, x + i, y + i], fill=(color[0], color[1], color[2], alpha))
    
    return img


# ========== 液态玻璃卡片 ==========

def _draw_glass_card(img: Image.Image, xy, title: Optional[str] = None, accent: Optional[Tuple] = None):
    """绘制现代玻璃卡片，返回内容区 (x0, y0, x1, y1)。
    
    现代优雅的玻璃效果：
    - 高透明白色背景
    - 柔和阴影
    - 细腻边框
    - 可选标题
    """
    x0, y0, x1, y1 = xy
    cw, ch = x1 - x0, y1 - y0
    pad = _PX(16)

    # 绘制阴影
    shadow_offset = _PX(6)
    shadow = Image.new("RGBA", (cw + shadow_offset * 2, ch + shadow_offset * 2), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    _round_rect(shadow_draw, (shadow_offset, shadow_offset, cw + shadow_offset, ch + shadow_offset), 
                _CARD_RADIUS, fill=_GLASS_SHADOW)
    shadow = shadow.filter(ImageFilter.GaussianBlur(_PX(12)))
    img.paste(shadow, (x0 - shadow_offset, y0 - shadow_offset), shadow)

    # 绘制玻璃主体
    glass = Image.new("RGBA", (cw, ch), _GLASS_FILL)
    glass_draw = ImageDraw.Draw(glass)
    
    # 添加顶部高光效果
    highlight = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    for i in range(_PX(40)):
        alpha = int(40 * (1 - i / _PX(40)))
        highlight_draw.rectangle([0, i, cw, i + 1], fill=(255, 255, 255, alpha))
    glass.alpha_composite(highlight)
    
    # 如果有强调色，添加轻微的彩色光晕
    if accent:
        glow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        # 底部轻微彩色光晕
        for i in range(ch // 4):
            alpha = int(25 * (1 - i / (ch // 4)))
            glow_draw.rectangle([0, ch - i - 1, cw, ch - i], fill=accent + (alpha,))
        glow = glow.filter(ImageFilter.GaussianBlur(_PX(25)))
        glass.alpha_composite(glow)
    
    # 应用圆角遮罩
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, cw, ch], radius=_CARD_RADIUS, fill=255
    )
    img.paste(glass, (x0, y0), mask)
    
    # 绘制标题
    if title:
        draw = ImageDraw.Draw(img)
        f_title = _get_font(_PX(18), bold=True)
        title_color = accent if accent else _TEXT_DARK
        _draw_text(draw, (x0 + _PX(24), y0 + _PX(20)), title, f_title, title_color, img)
    
    return (x0 + _PX(24), y0 + _PX(60) if title else y0 + _PX(24), x1 - _PX(24), y1 - _PX(24))

    # 绘制边框
    border = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    _round_rect(border_draw, (0, 0, cw, ch), _CARD_RADIUS, outline=_GLASS_BORDER, width=_PX(1))
    img.paste(border, (x0, y0), border)

    # 标题区域处理
    if title:
        draw = ImageDraw.Draw(img)
        f = _get_font(_PX(24), bold=True)
        _draw_text(draw, (x0 + _PX(20), y0 + _PX(16)), title, f, _TEXT_DARK, img)
        
        # 标题下划线
        line_y = y0 + _PX(50)
        draw.line([(x0 + _PX(20), line_y), (x1 - _PX(20), line_y)], 
                 fill=_GLASS_BORDER, width=_PX(1))
        
        return (x0 + _PX(20), y0 + _PX(60), x1 - _PX(20), y1 - _PX(16))
    return (x0 + _PX(20), y0 + _PX(16), x1 - _PX(20), y1 - _PX(16))


# ========== 绘制函数 ==========

def _draw_header(img, y, stats: MessageStats, generated_at: float):
    """绘制头部信息。"""
    draw = ImageDraw.Draw(img)
    f_title = _get_font(_PX(36), bold=True)
    f_sub = _get_font(_PX(16))
    x = _PADDING * _SCALE
    _paste_emoji(img, (x, y), "🦊", f_title, draw)
    x += int(f_title.size * 1.3)
    _draw_text(draw, (x, y), "狐狸插件 · 仪表盘快照", f_title, _TEXT_DARK, img)

    sub = time.strftime("生成时间 %Y-%m-%d %H:%M:%S", time.localtime(generated_at))
    newest_ts = _to_int(stats.newest_timestamp, default=0)
    if newest_ts > 0:
        latest = time.strftime("最新消息 %m-%d %H:%M", time.localtime(newest_ts / 1000))
        sub = sub + "  ·  " + latest
    _draw_text(draw, (_PADDING * _SCALE, y + _PX(48)), sub, f_sub, _TEXT_MEDIUM, img)
    return y + _PX(80)


def _draw_stat_cards(img, y, stats: MessageStats, db_table_count: int):
    """绘制统计卡片。"""
    values = [
        _to_int(stats.total_count),
        _to_int(stats.group_message_count),
        _to_int(stats.private_message_count),
        _to_int(stats.channel_message_count),
        _to_int(len(stats.platform_stats or {})),
        _to_int(db_table_count),
    ]
    gap = _PX(_CARD_GAP)
    card_w = (_W_FULL - _PX(_PADDING) * 2 - gap * 2) // 3
    card_h = _PX(120)
    draw = ImageDraw.Draw(img)
    
    for idx in range(6):
        col = idx % 3
        row = idx // 3
        cx = _PX(_PADDING) + col * (card_w + gap)
        cy = y + row * (card_h + gap)
        label, color = _STAT_CARDS[idx]
        
        # 绘制卡片
        card_content = _draw_glass_card(img, (cx, cy, cx + card_w, cy + card_h), accent=color)
        
        # 绘制图标
        icon_size = _PX(24)
        icon_x = cx + _PX(16)
        icon_y = cy + _PX(16)
        icon_symbols = ["📊", "💬", "👤", "📡", "🌐", "🗄️"]
        _paste_emoji(img, (icon_x, icon_y), icon_symbols[idx], _get_font(icon_size), draw)
        
        f_val = _get_font(_PX(36), bold=True)
        f_lbl = _get_font(_PX(14))
        val_str = f"{values[idx]:,}" if isinstance(values[idx], int) else str(values[idx])
        
        # 数值文字
        vw = _text_width(draw, val_str, f_val)
        vx = cx + card_w - vw - _PX(16)
        _draw_text(draw, (vx, cy + _PX(16)), val_str, f_val, _TEXT_DARK, img)
        
        # 标签文字
        lw = _text_width(draw, label, f_lbl)
        lx = cx + card_w - lw - _PX(16)
        _draw_text(draw, (lx, cy + _PX(64)), label, f_lbl, _TEXT_MEDIUM, img)
        
        # 装饰线条
        line_y = cy + card_h - _PX(8)
        draw.line([(cx + _PX(8), line_y), (cx + _PX(32), line_y)], fill=color, width=_PX(2))
    
    return y + 2 * card_h + gap + _PX(20)


def _draw_timeline(img, xy, timeline: List[Dict]):
    """绘制时间趋势图。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    
    if not timeline:
        # 空状态
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无时间趋势数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return

    # 系列定义
    series_defs = [
        ("总消息", "count", _CHART_COLORS[0]),
        ("群聊", "group_count", _CHART_COLORS[1]),
        ("私聊", "private_count", _CHART_COLORS[2]),
        ("频道", "channel_count", _CHART_COLORS[3]),
    ]

    n = len(timeline)
    step_x = inner_w / max(n - 1, 1) if n > 1 else inner_w

    # 计算数据点
    series_points = []
    max_c = 1
    for label, key, color in series_defs:
        pts = []
        for i, p in enumerate(timeline):
            v = _to_int(p.get(key, 0))
            if v > max_c:
                max_c = v
            pts.append(v)
        series_points.append((label, key, color, pts))
    
    max_c = max(max_c, 1)

    # 绘制网格线
    for g in range(5):
        gy = y0 + _PX(8) + g * (inner_h - _PX(16)) / 4
        alpha = 30 if g == 0 or g == 4 else 15
        draw.line([(x0, gy), (x1, gy)], fill=(0, 0, 0, alpha), width=_PX(1))

    # 绘制Y轴标签
    f_axis = _get_font(_PX(12))
    for g in range(5):
        gy = y0 + _PX(8) + g * (inner_h - _PX(16)) / 4
        value = int(max_c * (1 - g / 4))
        label = f"{value:,}"
        tw = _text_width(draw, label, f_axis)
        _draw_text(draw, (x0 - tw - _PX(8), gy - _PX(6)), label, f_axis, _TEXT_MEDIUM, img)

    def to_points(vals):
        pts = []
        for i, v in enumerate(vals):
            px = x0 + (i * step_x if n > 1 else inner_w / 2)
            py = y1 - _PX(8) - (v / max_c) * (inner_h - _PX(16))
            pts.append((px, py))
        return pts

    # 绘制折线（从后往前，避免覆盖）
    for idx, (label, key, color, vals) in enumerate(reversed(series_points)):
        pts = to_points(vals)
        if len(pts) < 2:
            continue
        
        # 绘制线条
        draw.line(pts, fill=color, width=_PX(3))
        
        # 绘制数据点
        for px, py in pts:
            draw.ellipse([px - _PX(3), py - _PX(3), px + _PX(3), py + _PX(3)], 
                       fill=_BG_WHITE, outline=color, width=_PX(2))

    # 绘制图例
    f_legend = _get_font(_PX(12))
    lx = x0 + _PX(16)
    ly = y0 - _PX(20)
    
    for label, key, color in series_defs:
        # 图例线条
        draw.line([(lx, ly + _PX(4)), (lx + _PX(16), ly + _PX(4))], fill=color, width=_PX(3))
        # 图例标签
        lw = _text_width(draw, label, f_legend)
        _draw_text(draw, (lx + _PX(20), ly), label, f_legend, _TEXT_DARK, img)
        lx += _PX(36) + lw + _PX(16)

    # 绘制X轴标签
    f_lbl = _get_font(_PX(12))
    label_indices = list(range(n)) if n <= 8 else [0, n // 4, n // 2, 3 * n // 4, n - 1]
    
    for i in label_indices:
        if 0 <= i < n:
            label = str(timeline[i].get("date", ""))[-5:]
            tw = _text_width(draw, label, f_lbl)
            px = x0 + (i * step_x if n > 1 else inner_w / 2)
            lpx = px - tw / 2
            lpx = max(x0, min(lpx, x1 - tw))
            _draw_text(draw, (lpx, y1 - _PX(6)), label, f_lbl, _TEXT_MEDIUM, img)


def _draw_ranking(img, xy, items: List[Dict], name_key: str, count_key: str, color):
    """绘制排行榜。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    
    if not items:
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return

    f_name = _get_font(_PX(14))
    f_count = _get_font(_PX(14), bold=True)
    f_rank = _get_font(_PX(14), bold=True)
    max_c = max((_to_int(it.get(count_key, 0)) for it in items), default=1) or 1
    row_h = _PX(36)
    
    # 排名颜色配置
    rank_colors = [
        (255, 215, 0),    # 金色 #1
        (192, 192, 192),  # 银色 #2
        (205, 127, 50),   # 铜色 #3
    ]
    
    for i, it in enumerate(items[:8]):
        ry = y0 + _PX(8) + i * row_h
        if ry + row_h > y1:
            break
            
        name = str(it.get(name_key) or it.get("sender_id") or it.get("group_id") or "未知")
        name = _truncate_middle(draw, name, f_name, inner_w - _PX(140))
        count = _to_int(it.get(count_key, 0))
        count_str = f"{count:,}"

        # 排名徽章
        badge_size = _PX(20)
        if i < len(rank_colors):
            rank_color = rank_colors[i]
            draw.ellipse([x0 + _PX(8), ry + _PX(8), x0 + badge_size + _PX(8), ry + badge_size + _PX(8)], 
                       fill=rank_color)
            rank_color_text = _BG_WHITE
        else:
            draw.ellipse([x0 + _PX(8), ry + _PX(8), x0 + badge_size + _PX(8), ry + badge_size + _PX(8)], 
                       fill=_TEXT_MEDIUM)
            rank_color_text = _BG_WHITE
        
        # 排名文字
        rank_txt = str(i + 1)
        rw = _text_width(draw, rank_txt, f_rank)
        _draw_text(draw, (x0 + badge_size // 2 + _PX(8) - rw // 2, ry + _PX(8)), rank_txt, f_rank, rank_color_text, img)

        # 名称
        _draw_text(draw, (x0 + _PX(40), ry + _PX(8)), name, f_name, _TEXT_DARK, img)

        # 进度条
        bar_y = ry + _PX(24)
        bar_w = inner_w - _PX(160)
        bar_bg = Image.new("RGBA", (bar_w, _PX(6)), (0, 0, 0, 0))
        bar_bg_draw = ImageDraw.Draw(bar_bg)
        _round_rect(bar_bg_draw, (0, 0, bar_w, _PX(6)), _PX(3), fill=(229, 231, 235, 100))
        img.paste(bar_bg, (x0 + _PX(40), bar_y), bar_bg)

        # 进度条填充
        fill_w = int(bar_w * (count / max_c))
        if fill_w > 0:
            bar_fill = Image.new("RGBA", (fill_w, _PX(6)), (0, 0, 0, 0))
            bar_fill_draw = ImageDraw.Draw(bar_fill)
            _round_rect(bar_fill_draw, (0, 0, fill_w, _PX(6)), _PX(3), fill=color + (255,))
            img.paste(bar_fill, (x0 + _PX(40), bar_y), bar_fill)

        # 数值
        _draw_text(draw, (x1 - _PX(50), ry + _PX(8)), count_str, f_count, _TEXT_DARK, img)


_PLATFORM_LABELS = {
    "telegram": "Telegram",
    "discord": "Discord",
    "qq_official": "QQ 官方",
    "qq_private": "QQ 私有",
    "wechat": "微信",
}


def _draw_platform_donut(img, xy, platform_stats: Dict[str, int]):
    """绘制平台分布圆环图。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    
    if not platform_stats:
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无平台数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return

    items = sorted(((k, _to_int(v)) for k, v in platform_stats.items()), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1

    # 圆环布局
    donut_d = min(inner_h, inner_w * 0.5)
    donut_r_out = donut_d / 2
    donut_r_in = donut_r_out * 0.6
    cx = x0 + donut_r_out + _PX(20)
    cy = y0 + inner_h / 2

    # 绘制圆环
    start = -90.0
    for idx, (plat, val) in enumerate(items):
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
        
        # 绘制扇形
        draw.pieslice(
            [cx - donut_r_out, cy - donut_r_out, cx + donut_r_out, cy + donut_r_out],
            start, start + sweep, fill=color
        )
        start += sweep

    # 中心镂空
    draw.ellipse(
        [cx - donut_r_in, cy - donut_r_in, cx + donut_r_in, cy + donut_r_in],
        fill=_BG_WHITE,
    )

    # 中心文字
    f_total = _get_font(_PX(28), bold=True)
    f_total_lbl = _get_font(_PX(14))
    total_str = f"{total:,}"
    tw = _text_width(draw, total_str, f_total)
    _draw_text(draw, (cx - tw / 2, cy - _PX(20)), total_str, f_total, _TEXT_DARK, img)
    
    # 总消息标签
    lw = _text_width(draw, "总消息", f_total_lbl)
    _draw_text(draw, (cx - lw / 2, cy + _PX(12)), "总消息", f_total_lbl, _TEXT_MEDIUM, img)

    # 图例
    legend_x = x0 + donut_d + _PX(40)
    legend_w = inner_w - donut_d - _PX(60)
    f_name = _get_font(_PX(14))
    f_count = _get_font(_PX(14))
    
    for idx, (plat, val) in enumerate(items):
        if idx >= 5:  # 最多显示5个
            break
            
        ry = y0 + _PX(20) + idx * _PX(32)
        if ry + _PX(32) > y1 - _PX(20):
            break
            
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        label = _PLATFORM_LABELS.get(plat, plat or "未知")
        pct = val * 100 / total

        # 颜色标识
        draw.ellipse([legend_x, ry + _PX(8), legend_x + _PX(12), ry + _PX(20)], fill=color)
        
        # 平台名称
        _draw_text(draw, (legend_x + _PX(20), ry + _PX(8)), label, f_name, _TEXT_DARK, img)

        # 进度条
        bar_x = legend_x + _PX(100)
        bar_y = ry + _PX(12)
        bar_w = legend_w - _PX(100)
        bar_bg = Image.new("RGBA", (bar_w, _PX(4)), (0, 0, 0, 0))
        bar_bg_draw = ImageDraw.Draw(bar_bg)
        _round_rect(bar_bg_draw, (0, 0, bar_w, _PX(4)), _PX(2), fill=(229, 231, 235, 100))
        img.paste(bar_bg, (bar_x, bar_y), bar_bg)

        # 进度条填充
        fill_w = int(bar_w * (val / total))
        if fill_w > 0:
            bar_fill = Image.new("RGBA", (fill_w, _PX(4)), (0, 0, 0, 0))
            bar_fill_draw = ImageDraw.Draw(bar_fill)
            _round_rect(bar_fill_draw, (0, 0, fill_w, _PX(4)), _PX(2), fill=color)
            img.paste(bar_fill, (bar_x, bar_y), bar_fill)

        # 数值和百分比
        txt = f"{val:,} ({pct:.1f}%)"
        tw2 = _text_width(draw, txt, f_count)
        _draw_text(draw, (x1 - tw2 - _PX(8), ry + _PX(8)), txt, f_count, _TEXT_MEDIUM, img)


def _draw_content_types(img, xy, content_types: List[Dict]):
    """绘制内容类型分布圆环图。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)

    if isinstance(content_types, dict):
        content_types = [
            {"type": k, "label": k, "count": v} for k, v in content_types.items()
        ]

    if not content_types:
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无内容类型数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return

    items = [
        (ct.get("label") or ct.get("type") or "未知", _to_int(ct.get("count", 0)))
        for ct in content_types
    ]
    items = [(lbl, v) for lbl, v in items if v > 0]
    if not items:
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无内容类型数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return

    items.sort(key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1

    # 简化的饼图布局
    pie_d = min(inner_h, inner_w * 0.6)
    pie_r = pie_d / 2
    cx = x0 + pie_r + _PX(20)
    cy = y0 + inner_h / 2

    # 绘制饼图
    start = -90.0
    for idx, (lbl, val) in enumerate(items):
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
        
        # 绘制扇形
        draw.pieslice(
            [cx - pie_r, cy - pie_r, cx + pie_r, cy + pie_r],
            start, start + sweep, fill=color
        )
        start += sweep

    # 图例
    legend_x = x0 + pie_d + _PX(40)
    legend_w = inner_w - pie_d - _PX(60)
    f_name = _get_font(_PX(14))
    f_count = _get_font(_PX(14))
    
    for idx, (lbl, val) in enumerate(items):
        if idx >= 6:  # 最多显示6个
            break
            
        ry = y0 + _PX(20) + idx * _PX(30)
        if ry + _PX(30) > y1 - _PX(20):
            break
            
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        pct = val * 100 / total

        # 颜色标识
        draw.ellipse([legend_x, ry + _PX(8), legend_x + _PX(12), ry + _PX(20)], fill=color)
        
        # 类型名称
        _draw_text(draw, (legend_x + _PX(20), ry + _PX(8)), lbl, f_name, _TEXT_DARK, img)

        # 数值和百分比
        txt = f"{val:,} ({pct:.1f}%)"
        tw2 = _text_width(draw, txt, f_count)
        _draw_text(draw, (x1 - tw2 - _PX(8), ry + _PX(8)), txt, f_count, _TEXT_MEDIUM, img)


def _draw_platform_detail(img, xy, platforms: List[Dict]):
    """绘制平台消息详情堆叠柱状图。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    
    if isinstance(platforms, dict):
        platforms = [{"platform": k, "total": v} for k, v in platforms.items()]
    if not platforms:
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无平台数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return

    # 系列定义
    series_defs = [
        ("群聊", "group_count", _CHART_COLORS[0]),
        ("私聊", "private_count", _CHART_COLORS[1]),
        ("频道", "channel_count", _CHART_COLORS[2]),
    ]

    chart_top = y0 + _PX(30)
    chart_bottom = y1 - _PX(30)
    chart_h = chart_bottom - chart_top

    def seg_total(p: Dict) -> int:
        return sum(_to_int(p.get(k, 0)) for _, k, _ in series_defs)

    max_total = max((seg_total(p) for p in platforms), default=1) or 1

    n = len(platforms)
    slot_w = inner_w / n
    bar_w = min(slot_w * 0.6, _PX(50))

    f_val = _get_font(_PX(12))
    for i, p in enumerate(platforms):
        cx_bar = x0 + slot_w * i + (slot_w - bar_w) / 2
        total = seg_total(p)
        if total <= 0:
            continue
        h_total = chart_h * total / max_total
        seg_bottom = chart_bottom
        for idx, (label, key, color) in enumerate(series_defs):
            v = _to_int(p.get(key, 0))
            if v <= 0:
                continue
            h = h_total * v / total
            seg_top = seg_bottom - h
            draw.rectangle([cx_bar, seg_top, cx_bar + bar_w, seg_bottom], fill=color)
            seg_bottom = seg_top

        # 柱顶总量
        total_str = f"{total:,}"
        tw = _text_width(draw, total_str, f_val)
        _draw_text(draw, (cx_bar + bar_w / 2 - tw / 2, chart_bottom - _PX(20)), total_str, f_val, _TEXT_MEDIUM, img)

    # X轴平台名标签
    f_lbl = _get_font(_PX(12))
    for i, p in enumerate(platforms):
        label = _truncate(draw, str(p.get("platform_name") or p.get("platform") or "未知"), f_lbl, int(slot_w - _PX(8)))
        lw = _text_width(draw, label, f_lbl)
        lx = x0 + slot_w * i + (slot_w - lw) / 2
        _draw_text(draw, (lx, chart_bottom + _PX(8)), label, f_lbl, _TEXT_MEDIUM, img)

    # 峰值标注
    peak_text = f"峰值 {max_total:,}"
    _draw_text(draw, (x0, y0 + _PX(8)), peak_text, _get_font(_PX(12), bold=True), _TEXT_MEDIUM, img)


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
    """渲染简洁现代的仪表盘快照 PNG。

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

    # 画布高度
    canvas_h = _PX(2800)
    img = _make_background((_W_FULL, canvas_h))

    y = _PX(_PADDING)
    
    # 1. 绘制头部
    y = _draw_header(img, y, stats, generated_at)
    y += _PX(20)
    
    # 2. 绘制统计卡片
    y = _draw_stat_cards(img, y, stats, db_table_count)
    y += _PX(30)

    # 3. 时间趋势卡片
    chart_h = _PX(240)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + chart_h), 
                     title="消息时间趋势", accent=_CHART_COLORS[0])
    _draw_timeline(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(60), _W_FULL - _PX(_PADDING) - _PX(24), y + chart_h - _PX(24)),
        timeline,
    )
    y += chart_h + _PX(30)

    # 4. 平台分布卡片
    plat_h = _PX(280)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + plat_h), 
                     title="平台分布", accent=_CHART_COLORS[0])
    _draw_platform_donut(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(60), _W_FULL - _PX(_PADDING) - _PX(24), y + plat_h - _PX(24)),
        platform_stats,
    )
    y += plat_h + _PX(30)

    # 5. 发送者 + 群组排行
    gap = _PX(_CARD_GAP)
    half_w = (_W_FULL - 2 * _PX(_PADDING) - gap) // 2
    rank_h = _PX(340)
    left_xy = (_PX(_PADDING), y, _PX(_PADDING) + half_w, y + rank_h)
    right_xy = (_PX(_PADDING) + half_w + gap, y, _W_FULL - _PX(_PADDING), y + rank_h)
    _draw_glass_card(img, left_xy, title="发送者排行 Top 8", accent=_CHART_COLORS[0])
    _draw_glass_card(img, right_xy, title="群组活跃度排行 Top 8", accent=_CHART_COLORS[1])

    for g in group_ranking:
        gid = str(g.get("group_id") or "")
        plat = str(g.get("platform") or "")
        g["display_name"] = f"{gid} ({plat})" if gid and plat else (gid or plat or "未知")

    _draw_ranking(
        img,
        (left_xy[0] + _PX(24), left_xy[1] + _PX(60), left_xy[2] - _PX(24), left_xy[3] - _PX(24)),
        sender_ranking, "sender_name", "count", _CHART_COLORS[0],
    )
    _draw_ranking(
        img,
        (right_xy[0] + _PX(24), right_xy[1] + _PX(60), right_xy[2] - _PX(24), right_xy[3] - _PX(24)),
        group_ranking, "display_name", "count", _CHART_COLORS[1],
    )
    y += rank_h + _PX(30)

    # 6. 平台消息详情卡片
    pd_h = _PX(300)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + pd_h), 
                     title="平台消息详情", accent=_CHART_COLORS[2])
    _draw_platform_detail(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(60), _W_FULL - _PX(_PADDING) - _PX(24), y + pd_h - _PX(24)),
        platform_detail or [],
    )
    y += pd_h + _PX(30)

    # 7. 内容类型分布卡片
    ct_h = _PX(320)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + ct_h), 
                     title="消息内容类型分布", accent=_CHART_COLORS[3])
    _draw_content_types(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(60), _W_FULL - _PX(_PADDING) - _PX(24), y + ct_h - _PX(24)),
        content_types,
    )
    y += ct_h + _PX(30)

    # 8. 底部水印
    draw = ImageDraw.Draw(img)
    watermark_text = "由狐狸插件 /huli_record snapshot 生成 · 现代优雅风格 v2.1"
    f_watermark = _get_font(_PX(12))
    _draw_text(draw, (_PX(24), y + _PX(12)), watermark_text, f_watermark, _TEXT_MEDIUM, img)

    # 9. 最终处理
    final_h = y + _PX(40)
    img = img.crop((0, 0, _W_FULL, final_h))
    
    # 使用高质量降采样
    img = img.resize((_W, int(final_h / _SCALE)), Image.LANCZOS)

    # 保存为优化的PNG
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True, quality=95)
    return buf.getvalue()