"""WebUI 仪表盘快照渲染器

用 Pillow 把数据库统计数据渲染成一张与 WebUI 风格一致的 PNG，
供 /huli_record snapshot 指令直接发到聊天。

视觉对齐 pages/recorder 的 Liquid Glass UI：
1. 浅色渐变背景 + 柔和光斑（饱和度克制）
2. 玻璃卡片：半透白 0.55 + 模糊背景 + 投影 + 内部彩色光斑
3. stat-value 蓝色渐变文字
4. 2x 超采样 + LANCZOS 降采样保证清晰
5. NotoSansCJK 矢量字体 + NotoColorEmoji 彩色 emoji
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
_CARD_RADIUS = 22
_CARD_GAP = 18

# ========== 色彩（对齐 WebUI :root 变量）==========

# 背景色彩（基于现代玻璃态设计理论）
_BG_TOP = (248, 250, 252)      # 更柔和的顶部色调
_BG_BOTTOM = (241, 245, 249)   # 更柔和的底部色调
_BG_GRADIENT_POINTS = [
    (0.0, (248, 250, 252)),     # 顶部
    (0.3, (246, 248, 250)),     # 中上
    (0.6, (244, 246, 248)),     # 中下
    (1.0, (241, 245, 249))      # 底部
]

_PRIMARY = (79, 195, 247)
_PRIMARY_DARK = (2, 136, 209)
_SUCCESS = (16, 185, 129)
_WARNING = (245, 158, 11)
_DANGER = (239, 68, 68)
_PURPLE = (139, 92, 246)

_TEXT = (30, 41, 59)
_TEXT_LIGHT = (71, 85, 105)
_TEXT_WHITE = (255, 255, 255)

# 玻璃材质（基于2024年玻璃态UI最佳实践）
_GLASS_FILL = (255, 255, 255, 88)     # 15% 透明度，现代玻璃态标准
_GLASS_BORDER = (255, 255, 255, 102)  # 30% 透明度边框
_GLASS_HIGHLIGHT = (255, 255, 255, 102)  # 30% 透明度高光
_GLASS_INNER_GLOW = (255, 255, 255, 64)   # 内部发光效果
_TRACK = (203, 213, 225, 200)     # 60% 透明度轨道（加深提升可见性）
_SHADOW = (0, 0, 0, 24)              # 更柔和的阴影
_SHADOW_SOFT = (0, 0, 0, 16)         # 超软阴影

# stat-value 现代蓝色渐变（基于2024年UI设计趋势）
_GRADIENT_BLUE = [
    (79, 195, 247),    # 主色调
    (41, 182, 246),   # 深蓝过渡
    (3, 169, 244),    # 核心色
    (100, 181, 246),  # 中间色
    (129, 212, 250),  # 浅蓝过渡
    (179, 229, 252),  # 很浅蓝
    (77, 208, 225),   # 青色点缀
]

# 扩展渐变色板（用于图表和装饰）
_GRADIENT_FULL = [
    (79, 195, 247),    # 蓝色
    (16, 185, 129),   # 绿色
    (245, 158, 11),   # 橙色
    (139, 92, 246),   # 紫色
    (239, 68, 68),    # 红色
    (255, 183, 77),   # 黄色
    (77, 208, 225),   # 青色
    (129, 199, 132),  # 薄荷绿
    (240, 98, 146),   # 粉色
    (149, 117, 205),  # 淡紫
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


def _draw_empty_state(img, xy, text: str):
    """绘制居中的玻璃态空状态（圆角框 + 空圆环图标 + 提示文字）。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    f = _get_font(_PX(15))
    text_w = _text_width(draw, text, f)
    box_w = max(text_w + _PX(72), _PX(200))
    box_h = _PX(116)
    bx0 = x0 + (inner_w - box_w) // 2
    by0 = y0 + (inner_h - box_h) // 2

    box = Image.new("RGBA", (box_w, box_h), (255, 255, 255, 20))
    box = box.filter(ImageFilter.GaussianBlur(_PX(10)))
    img.paste(box, (bx0, by0), box)

    border = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(border)
    bd.rounded_rectangle(
        [bx0, by0, bx0 + box_w, by0 + box_h],
        radius=_PX(16), outline=(100, 116, 139, 90), width=_PX(2),
    )
    img.alpha_composite(border)

    icon_r = _PX(15)
    icx = x0 + inner_w // 2
    icy = by0 + _PX(34)
    icon = Image.new("RGBA", img.size, (0, 0, 0, 0))
    idraw = ImageDraw.Draw(icon)
    idraw.ellipse(
        [icx - icon_r, icy - icon_r, icx + icon_r, icy + icon_r],
        outline=(148, 163, 184, 140), width=_PX(2),
    )
    idraw.ellipse(
        [icx - icon_r // 3, icy - icon_r // 3, icx + icon_r // 3, icy + icon_r // 3],
        outline=(148, 163, 184, 140), width=_PX(2),
    )
    img.alpha_composite(icon)

    _draw_text(draw, (x0 + inner_w // 2 - text_w // 2, by0 + _PX(66)), text, f, _TEXT_LIGHT, img)


def _draw_donut_separators(ld, cx, cy, r_in, r_out, items, total):
    """在圆环分段交界处绘制细白分隔线，增强小分段的可辨识度。"""
    start = -90.0
    for idx, (_, val) in enumerate(items):
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
        end = start + sweep
        if idx > 0:
            a_rad = math.radians(start - 90)
            px1 = cx + r_out * math.cos(a_rad)
            py1 = cy + r_out * math.sin(a_rad)
            px2 = cx + r_in * math.cos(a_rad)
            py2 = cy + r_in * math.sin(a_rad)
            ld.line([(px1, py1), (px2, py2)], fill=(255, 255, 255, 235), width=_PX(3))
        start = end


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
    """绘制高级水平渐变文字（支持动态色彩过渡和发光效果）。"""
    x, y = xy
    if not text:
        return
    w = _text_width(draw, text, font)
    if w <= 0:
        return
    
    # 计算渐变分段
    total_chars = len(text)
    char_width = w / max(total_chars, 1)
    
    cx = x
    for i, ch in enumerate(text):
        cw = _measure_text(draw, ch, font)
        if cw <= 0:
            continue
            
        # 计算当前字符在渐变中的位置
        t = i / max(total_chars - 1, 1)
        
        # 使用平滑插值计算颜色
        color = _interpolate_gradient_color(colors, t)
        
        # 绘制主文字
        draw.text((cx, y), ch, font=font, fill=color)
        
        # 为主要字符添加微妙的发光效果
        if i % 2 == 0 and cw > _PX(8):  # 为偶数位置字符添加发光
            glow_color = tuple(min(255, c + 30) for c in color) + (40,)
            # 创建发光效果
            glow_text = Image.new("RGBA", (cw + _PX(4), int(font.size * 1.2)), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_text)
            glow_draw.text((_PX(2), _PX(2)), ch, font=font, fill=glow_color)
            glow_text = glow_text.filter(ImageFilter.GaussianBlur(_PX(2)))
            canvas.paste(glow_text, (int(cx - _PX(2)), int(y - _PX(1))), glow_text)
        
        cx += cw


def _interpolate_gradient_color(colors, t):
    """在渐变色板中平滑插值计算颜色。"""
    if t <= 0:
        return colors[0]
    if t >= 1:
        return colors[-1]
    
    # 计算在哪个颜色区间
    segment_count = len(colors) - 1
    segment_index = int(t * segment_count)
    segment_t = (t * segment_count) - segment_index
    
    if segment_index >= segment_count:
        return colors[-1]
    
    # 在当前区间内插值
    color1 = colors[segment_index]
    color2 = colors[segment_index + 1]
    
    return tuple(
        int(c1 + (c2 - c1) * segment_t)
        for c1, c2 in zip(color1, color2)
    )


# ========== 背景（对齐 WebUI body 背景）==========


def _make_background(size) -> Image.Image:
    """现代玻璃态背景：多层次渐变 + 动态光斑效果。"""
    w, h = size
    
    # 创建高级渐变背景
    bg = Image.new("RGBA", size, (0, 0, 0, 0))
    
    # 基础渐变层：1px 色条纵向插值后放大（保证 alpha 完整）
    strip_h = 32
    strip = Image.new("RGBA", (1, strip_h), (0, 0, 0, 0))
    for yy in range(strip_h):
        t = yy / max(strip_h - 1, 1)
        color = _interpolate_gradient(_BG_GRADIENT_POINTS, t)
        strip.putpixel((0, yy), color + (255,))
    bg = strip.resize((w, h), Image.BILINEAR)
    
    # 光斑层 - 更丰富的动态效果
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    
    # 主要光斑
    blobs = [
        # 主光斑 - 更柔和
        (int(w * 0.12), int(h * 0.08), int(w * 0.35), (79, 195, 247, 24)),
        (int(w * 0.88), int(h * 0.92), int(w * 0.30), (41, 182, 246, 20)),
        # 次要光斑 - 增加层次感
        (int(w * 0.45), int(h * 0.15), int(w * 0.25), (255, 183, 77, 16)),
        (int(w * 0.65), int(h * 0.75), int(w * 0.20), (129, 199, 132, 12)),
        # 细节光斑 - 增加深度
        (int(w * 0.25), int(h * 0.60), int(w * 0.15), (77, 208, 225, 10)),
        (int(w * 0.80), int(h * 0.35), int(w * 0.18), (139, 92, 246, 8)),
    ]
    
    for cx, cy, r, color in blobs:
        # 创建径向渐变光斑
        for i in range(3):
            factor = 1 - (i * 0.3)
            r_scaled = int(r * factor)
            alpha = int(color[3] * (1 - i * 0.4))
            if r_scaled > 0 and alpha > 0:
                blob_color = color[:3] + (alpha,)
                od.ellipse([cx - r_scaled, cy - r_scaled, cx + r_scaled, cy + r_scaled], 
                          fill=blob_color)
    
    # 应用高斯模糊创造景深效果
    overlay = overlay.filter(ImageFilter.GaussianBlur(_PX(60)))
    bg.alpha_composite(overlay)
    
    return bg


def _interpolate_gradient(points, t):
    """在渐变点之间插值计算颜色。"""
    if t <= 0:
        return points[0][1]
    if t >= 1:
        return points[-1][1]
    
    # 找到对应的区间
    for i in range(len(points) - 1):
        t0, color0 = points[i]
        t1, color1 = points[i + 1]
        
        if t0 <= t <= t1:
            # 在区间内线性插值
            local_t = (t - t0) / (t1 - t0)
            return _interpolate_color(color0, color1, local_t)
    
    return points[-1][1]


def _interpolate_color(color1, color2, t):
    """在两种颜色之间插值。"""
    return tuple(
        int(c1 + (c2 - c1) * t)
        for c1, c2 in zip(color1, color2)
    )


# ========== 毛玻璃卡片（对齐 WebUI .card / .stat-card）==========


def _draw_glass_card(img: Image.Image, blurred_bg: Image.Image, xy, title: Optional[str] = None, accent: Optional[Tuple] = None):
    """绘制现代玻璃态卡片，返回内容区 (x0, y0, x1, y1)。

    基于2024年玻璃态UI最佳实践：
    - 多层玻璃效果：基础层 + 高光层 + 反射层
    - 柔和投影：多层阴影创造景深
    - 动态边框：边缘高光模拟玻璃折射
    - 内部发光：彩色光斑增加视觉层次
    """
    x0, y0, x1, y1 = xy
    cw, ch = x1 - x0, y1 - y0
    pad = _PX(12)

    # 多层投影效果（创造景深）
    shadows = []
    
    # 底层阴影（最柔和）
    shadow1 = Image.new("RGBA", (cw + _PX(24), ch + _PX(24)), (0, 0, 0, 0))
    sd1 = ImageDraw.Draw(shadow1)
    sd1.rounded_rectangle(
        [_PX(12), _PX(12), cw + _PX(12), ch + _PX(12)],
        radius=_CARD_RADIUS, fill=_SHADOW_SOFT,
    )
    shadow1 = shadow1.filter(ImageFilter.GaussianBlur(_PX(16)))
    shadows.append((shadow1, x0 - _PX(12), y0 - _PX(8)))
    
    # 中层阴影（标准柔和）
    shadow2 = Image.new("RGBA", (cw + _PX(20), ch + _PX(20)), (0, 0, 0, 0))
    sd2 = ImageDraw.Draw(shadow2)
    sd2.rounded_rectangle(
        [_PX(10), _PX(10), cw + _PX(10), ch + _PX(10)],
        radius=_CARD_RADIUS, fill=_SHADOW,
    )
    shadow2 = shadow2.filter(ImageFilter.GaussianBlur(_PX(10)))
    shadows.append((shadow2, x0 - _PX(10), y0 - _PX(6)))
    
    # 顶层阴影（最清晰）
    shadow3 = Image.new("RGBA", (cw + _PX(16), ch + _PX(16)), (0, 0, 0, 0))
    sd3 = ImageDraw.Draw(shadow3)
    sd3.rounded_rectangle(
        [_PX(8), _PX(8), cw + _PX(8), ch + _PX(8)],
        radius=_CARD_RADIUS, fill=(0, 0, 0, 20),
    )
    shadow3 = shadow3.filter(ImageFilter.GaussianBlur(_PX(6)))
    shadows.append((shadow3, x0 - _PX(8), y0 - _PX(4)))
    
    # 应用所有阴影层（从底到上）
    for shadow, sx, sy in shadows:
        img.paste(shadow, (sx, sy), shadow)

    # 毛玻璃主体层（现代玻璃态标准）
    region = blurred_bg.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    
    # 基础玻璃层
    glass_base = Image.new("RGBA", region.size, _GLASS_FILL)
    region.alpha_composite(glass_base)
    
    # 内部发光层（增加深度）
    if accent:
        inner_glow = Image.new("RGBA", region.size, (0, 0, 0, 0))
        igd = ImageDraw.Draw(inner_glow)
        # 居中多层椭圆，逐层缩小模拟径向渐变发光
        for i in range(3):
            alpha = _GLASS_INNER_GLOW[3] // (i + 1)
            scale = 0.5 - i * 0.1  # 0.5, 0.4, 0.3
            igd.ellipse([
                int(region.width * (0.5 - scale)),
                int(region.height * (0.5 - scale)),
                int(region.width * (0.5 + scale)),
                int(region.height * (0.5 + scale)),
            ], fill=accent + (alpha,))
        inner_glow = inner_glow.filter(ImageFilter.GaussianBlur(_PX(20)))
        region.alpha_composite(inner_glow)
    
    # 创建遮罩并应用
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [pad, pad, region.width - pad, region.height - pad],
        radius=_CARD_RADIUS, fill=255,
    )
    img.paste(region, (x0 - pad, y0 - pad), mask)

    # 装饰层：多层光影效果
    deco = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)

    # 1. 顶部边缘高光（模拟玻璃折射）
    edge_highlight = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ehd = ImageDraw.Draw(edge_highlight)
    
    # 顶部高光渐变
    hl_h = int(ch * 0.35)
    for yy in range(hl_h):
        t = yy / max(hl_h - 1, 1)
        # 使用指数衰减创造更自然的高光效果
        a = int(_GLASS_HIGHLIGHT[3] * (1 - t) ** 1.5)
        ehd.line([(0, yy), (cw, yy)], fill=(255, 255, 255, a))
    
    # 左上角额外高光点
    corner_r = _PX(8)
    ehd.ellipse([0, 0, corner_r * 2, corner_r * 2], fill=(255, 255, 255, 40))
    
    deco.alpha_composite(edge_highlight)

    # 2. 边框强化（双层边框模拟玻璃厚度）
    # 外层边框（更柔和）
    _round_rect(dd, (0, 0, cw, ch), _CARD_RADIUS, outline=_GLASS_BORDER, width=_PX(1))
    
    # 内层边框（更清晰）
    inner_border = Image.new("RGBA", (cw - _PX(2), ch - _PX(2)), (0, 0, 0, 0))
    ibd = ImageDraw.Draw(inner_border)
    _round_rect(ibd, (_PX(1), _PX(1), cw - _PX(3), ch - _PX(3)), 
                _CARD_RADIUS - _PX(1), outline=(255, 255, 255, 60), width=_PX(1))
    deco.paste(inner_border, (_PX(1), _PX(1)), inner_border)

    # 3. 底部反光效果（模拟玻璃表面反射）
    if ch > _PX(60):
        reflection = Image.new("RGBA", (cw, _PX(20)), (0, 0, 0, 0))
        rfd = ImageDraw.Draw(reflection)
        # 渐变反光线
        for i in range(_PX(20)):
            alpha = int(30 * (1 - i / 20) ** 2)
            rfd.line([(0, i), (cw, i)], fill=(255, 255, 255, alpha))
        deco.paste(reflection, (0, ch - _PX(20)), reflection)

    img.paste(deco, (x0, y0), deco)

    # 标题区域处理
    if title:
        draw = ImageDraw.Draw(img)
        f = _get_font(_PX(26), bold=True)
        _draw_text(draw, (x0 + _PX(20), y0 + _PX(14)), title, f, _TEXT, img)
        
        # 标题下划线（更精致）
        line_deco = Image.new("RGBA", (x1 - x0 - _PX(40), _PX(1)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(line_deco)
        # 渐变下划线
        for i in range(_PX(1)):
            alpha = int(40 * (1 - i / 1))
            ld.line([(0, i), (x1 - x0 - _PX(40), i)], fill=(0, 0, 0, alpha))
        img.paste(line_deco, (x0 + _PX(20), y0 + _PX(58)), line_deco)
        
        return (x0 + _PX(20), y0 + _PX(70), x1 - _PX(20), y1 - _PX(16))
    return (x0 + _PX(20), y0 + _PX(16), x1 - _PX(20), y1 - _PX(16))


# ========== 区块绘制 ==========


def _draw_header(img, y, stats: MessageStats, generated_at: float):
    draw = ImageDraw.Draw(img)
    f_title = _get_font(_PX(40), bold=True)
    f_sub = _get_font(_PX(19))
    x = _PADDING * _SCALE
    _paste_emoji(img, (x, y), "🦊", f_title, draw)
    x += int(f_title.size * 1.3)
    _draw_text(draw, (x, y), "狐狸插件 · 仪表盘快照", f_title, _TEXT, img)

    sub = time.strftime("生成时间 %Y-%m-%d %H:%M:%S", time.localtime(generated_at))
    newest_ts = _to_int(stats.newest_timestamp, default=0)
    if newest_ts > 0:
        latest = time.strftime("最新消息 %m-%d %H:%M", time.localtime(newest_ts / 1000))
        sub = sub + "  ·  " + latest
    _draw_text(draw, (_PADDING * _SCALE, y + _PX(52)), sub, f_sub, _TEXT_LIGHT, img)
    return y + _PX(92)


def _draw_stat_cards(img, blurred_bg, y, stats: MessageStats, db_table_count: int):
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
    card_h = _PX(110)
    draw = ImageDraw.Draw(img)
    for idx in range(6):
        col = idx % 3
        row = idx // 3
        cx = _PX(_PADDING) + col * (card_w + gap)
        cy = y + row * (card_h + gap)
        label, color = _STAT_CARDS[idx]
        _draw_glass_card(img, blurred_bg, (cx, cy, cx + card_w, cy + card_h), accent=color)

        f_val = _get_font(_PX(46), bold=True)
        f_lbl = _get_font(_PX(18))
        val_str = f"{values[idx]:,}" if isinstance(values[idx], int) else str(values[idx])
        # stat-value 蓝色渐变文字（对齐 .stat-value）
        vw = _text_width(draw, val_str, f_val)
        vx = cx + (card_w - vw) // 2
        _draw_gradient_text(draw, (vx, cy + _PX(14)), val_str, f_val, _GRADIENT_BLUE, img)
        # 标签居中
        lw = _text_width(draw, label, f_lbl)
        _draw_text(draw, (cx + (card_w - lw) // 2, cy + _PX(74)), label, f_lbl, _TEXT_LIGHT, img)
    return y + 2 * card_h + gap + _PX(10)


def _draw_timeline(img, xy, timeline: List[Dict]):
    """高级多系列时间趋势折线图（现代玻璃态设计 + 动态视觉效果）。"""
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if not timeline:
        _draw_empty_state(img, xy, "暂无时间趋势数据")
        return

    # 系列定义（基于现代UI设计趋势）
    series_defs = [
        ("总消息", "count", _GRADIENT_BLUE[0], True),   # 主系列，更粗
        ("群聊", "group_count", _GRADIENT_FULL[1], False),
        ("私聊", "private_count", _GRADIENT_FULL[4], False),
        ("频道", "channel_count", _GRADIENT_FULL[8], False),
    ]

    n = len(timeline)
    step_x = inner_w / max(n - 1, 1) if n > 1 else inner_w

    # 计算每系列数据点
    series_points = []
    max_c = 1
    for label, key, color, is_main in series_defs:
        pts = []
        for i, p in enumerate(timeline):
            v = _to_int(p.get(key, 0))
            if v > max_c:
                max_c = v
            pts.append(v)
        series_points.append((label, key, color, is_main, pts))
    max_c = max(max_c, 1)

    # 创建图表图层
    chart_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(chart_layer)

    # 1. 绘制网格（更精致的网格线）
    for g in range(5):  # 增加网格密度
        gy = y0 + _PX(8) + g * (inner_h - _PX(16)) / 4
        alpha = 20 if g == 0 or g == 4 else 12  # 边界线更明显
        ld.line([(x0, gy), (x1, gy)], fill=(0, 0, 0, alpha), width=_PX(1))

    # 2. 绘制Y轴刻度标签
    f_axis = _get_font(_PX(14))
    for g in range(5):
        gy = y0 + _PX(8) + g * (inner_h - _PX(16)) / 4
        value = int(max_c * (1 - g / 4))
        label = f"{value:,}"
        tw = _text_width(draw, label, f_axis)
        _draw_text(draw, (x0 - tw - _PX(8), gy - _PX(6)), label, f_axis, _TEXT_LIGHT, img)

    def to_points(vals):
        pts = []
        for i, v in enumerate(vals):
            px = x0 + (i * step_x if n > 1 else inner_w / 2)
            py = y1 - _PX(12) - (v / max_c) * (inner_h - _PX(24))
            pts.append((px, py))
        return pts

    # 3. 绘制面积填充（从后往前，避免覆盖）
    for idx, (label, key, color, is_main, vals) in enumerate(reversed(series_points)):
        pts = to_points(vals)
        if len(pts) >= 2:
            # 创建渐变填充
            fill_pts = pts + [(pts[-1][0], y1 - _PX(8)), (pts[0][0], y1 - _PX(8))]
            
            # 主系列使用更强的填充
            alpha = 60 if is_main else 30
            ld.polygon(fill_pts, fill=color + (alpha,))

    # 4. 绘制折线（从前往后，主系列最后绘制）
    for idx, (label, key, color, is_main, vals) in enumerate(series_points):
        pts = to_points(vals)
        if len(pts) < 2:
            continue
            
        # 线条粗细和样式
        width = _PX(5) if is_main else _PX(2)
        stroke_color = color + (255,)
        
        # 绘制主线
        ld.line(pts, fill=stroke_color, width=width, joint="curve")
        
        # 添加发光效果（仅主系列）
        if is_main:
            glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            glow_draw.line(pts, fill=color + (120,), width=width + _PX(4), joint="curve")
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(_PX(3)))
            img.alpha_composite(glow_layer)

        # 绘制数据点
        point_radius = _PX(5) if is_main else _PX(3)
        for px, py in pts:
            # 外圈
            ld.ellipse([px - point_radius, py - point_radius, px + point_radius, py + point_radius], 
                      fill=_TEXT_WHITE, outline=color, width=_PX(2))
            # 内圈
            inner_radius = point_radius - _PX(2)
            if inner_radius > 0:
                ld.ellipse([px - inner_radius, py - inner_radius, px + inner_radius, py + inner_radius], 
                          fill=color)

    img.alpha_composite(chart_layer)

    # 5. 绘制图例（玻璃态图例框）
    legend_bg = Image.new("RGBA", (inner_w, _PX(40)), (255, 255, 255, 25))
    legend_bg = legend_bg.filter(ImageFilter.GaussianBlur(_PX(8)))
    img.paste(legend_bg, (x0, y0 - _PX(35)), legend_bg)
    
    f_legend = _get_font(_PX(14))
    lx = x0 + _PX(16)
    ly = y0 - _PX(28)
    
    for label, key, color, is_main in series_defs:
        # 绘制图例线条
        line_length = _PX(20)
        line_y = ly + _PX(6)
        line_width = _PX(4) if is_main else _PX(2)
        
        # 线条
        draw.line([(lx, line_y), (lx + line_length, line_y)], fill=color, width=line_width)
        
        # 线条端点圆圈
        draw.ellipse([lx - _PX(3), line_y - _PX(3), lx + _PX(3), line_y + _PX(3)], 
                    fill=_TEXT_WHITE, outline=color, width=_PX(1))
        
        # 标签
        lw = _text_width(draw, label, f_legend)
        _draw_text(draw, (lx + line_length + _PX(8), ly), label, f_legend, _TEXT, img)
        
        lx += line_length + _PX(8) + lw + _PX(16)

    # 6. 绘制X轴标签
    f_lbl = _get_font(_PX(14))
    label_indices = list(range(n)) if n <= 8 else [0, n // 4, n // 2, 3 * n // 4, n - 1]
    
    for i in label_indices:
        if 0 <= i < n:
            label = str(timeline[i].get("date", ""))[-5:]
            tw = _text_width(draw, label, f_lbl)
            px = x0 + (i * step_x if n > 1 else inner_w / 2)
            lpx = px - tw / 2
            lpx = max(x0, min(lpx, x1 - tw))
            _draw_text(draw, (lpx, y1 - _PX(6)), label, f_lbl, _TEXT_LIGHT, img)

    # 7. 峰值标注
    peak_text = f"峰值 {max_c:,}"
    f_peak = _get_font(_PX(14), bold=True)
    peak_tw = _text_width(draw, peak_text, f_peak)
    _draw_gradient_text(draw, (x0, y0 + _PX(8)), peak_text, f_peak, _GRADIENT_BLUE, img)


def _draw_ranking(img, xy, items: List[Dict], name_key: str, count_key: str, color):
    """高级排行榜（现代玻璃态设计 + 动态视觉效果）。
    
    包含：
    - 玻璃态背景和边框
    - 渐变排名徽章
    - 动态进度条
    - 发光效果
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if not items:
        _draw_empty_state(img, xy, "暂无数据")
        return

    # 创建玻璃态背景
    bg_h = min(len(items) * _PX(45) + _PX(20), y1 - y0)
    bg = Image.new("RGBA", (inner_w, bg_h), (255, 255, 255, 22))
    bg = bg.filter(ImageFilter.GaussianBlur(_PX(12)))
    img.paste(bg, (x0, y0), bg)
    
    # 背景边框
    border = Image.new("RGBA", (inner_w, bg_h), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    _round_rect(border_draw, (0, 0, inner_w, bg_h), _PX(12), outline=(255, 255, 255, 35), width=_PX(1))
    img.paste(border, (x0, y0), border)

    f_name = _get_font(_PX(17))
    f_count = _get_font(_PX(16), bold=True)
    f_rank = _get_font(_PX(14), bold=True)
    max_c = max((_to_int(it.get(count_key, 0)) for it in items), default=1) or 1
    row_h = _PX(42)
    
    # 排名颜色配置
    rank_colors = [
        (255, 215, 0),    # 金色 #1
        (192, 192, 192),  # 银色 #2
        (205, 127, 50),   # 铜色 #3
        (100, 181, 246),  # 蓝色 #4
        (129, 199, 132),  # 绿色 #5
    ]
    
    for i, it in enumerate(items[:8]):
        ry = y0 + _PX(10) + i * row_h
        if ry + row_h > y1:
            break
            
        name = str(it.get(name_key) or it.get("sender_id") or it.get("group_id") or "未知")
        name = _truncate_middle(draw, name, f_name, inner_w - _PX(160))
        count = _to_int(it.get(count_key, 0))
        count_str = f"{count:,}"

        # 排名徽章（玻璃态效果）
        badge_size = _PX(24)
        badge_bg = Image.new("RGBA", (badge_size + _PX(8), row_h), (0, 0, 0, 0))
        badge_draw = ImageDraw.Draw(badge_bg)
        
        # 选择排名颜色
        if i < len(rank_colors):
            rank_color = rank_colors[i]
            # 外圈发光
            badge_draw.ellipse([_PX(2), _PX(9), badge_size + _PX(6), _PX(9) + badge_size], 
                              fill=rank_color + (60,))
            # 内圈
            badge_draw.ellipse([_PX(4), _PX(11), badge_size + _PX(4), _PX(11) + badge_size], 
                              fill=rank_color + (200,))
        else:
            # 普通排名
            badge_draw.ellipse([_PX(4), _PX(11), badge_size + _PX(4), _PX(11) + badge_size], 
                              fill=_TEXT_LIGHT + (180,))
        
        img.paste(badge_bg, (x0, ry), badge_bg)
        
        # 排名文字
        rank_txt = str(i + 1)
        rw = _text_width(draw, rank_txt, f_rank)
        rank_color_text = _TEXT_WHITE if i < 3 else _TEXT
        _draw_text(draw, (x0 + badge_size // 2 - rw // 2, ry + _PX(8)), rank_txt, f_rank, rank_color_text, img)

        # 名称（带发光效果）
        name_glow = Image.new("RGBA", (inner_w - _PX(80), row_h), (0, 0, 0, 0))
        name_glow_draw = ImageDraw.Draw(name_glow)
        name_glow_draw.text((_PX(30), _PX(8)), name, font=f_name, fill=color + (40,))
        name_glow = name_glow.filter(ImageFilter.GaussianBlur(_PX(2)))
        img.paste(name_glow, (x0 + _PX(80), ry), name_glow)
        
        _draw_text(draw, (x0 + _PX(30), ry + _PX(8)), name, f_name, _TEXT, img)

        # 进度条区域
        bar_y = ry + _PX(26)
        bar_w = inner_w - _PX(180)
        bar_bg = Image.new("RGBA", (bar_w, _PX(9)), (0, 0, 0, 0))
        bar_bg_draw = ImageDraw.Draw(bar_bg)
        _round_rect(bar_bg_draw, (0, 0, bar_w, _PX(9)), _PX(5), fill=_TRACK)
        img.paste(bar_bg, (x0 + _PX(80), bar_y), bar_bg)

        # 进度条（渐变效果）
        fill_w = int(bar_w * (count / max_c))
        if fill_w > 0:
            # 创建渐变进度条
            bar_fill = Image.new("RGBA", (fill_w, _PX(9)), (0, 0, 0, 0))
            bar_fill_draw = ImageDraw.Draw(bar_fill)
            
            # 基础填充
            _round_rect(bar_fill_draw, (0, 0, fill_w, _PX(9)), _PX(5), fill=color + (255,))
            
            # 添加高光效果
            highlight = Image.new("RGBA", (fill_w, _PX(4)), (0, 0, 0, 0))
            highlight_draw = ImageDraw.Draw(highlight)
            highlight_draw.rectangle([0, 0, fill_w, _PX(4)], fill=(255, 255, 255, 60))
            bar_fill.alpha_composite(highlight)
            
            img.paste(bar_fill, (x0 + _PX(80), bar_y), bar_fill)

        # 数值显示（带渐变效果）
        if i < 3:  # 前三名使用渐变文字
            _draw_gradient_text(draw, (x1 - _PX(60), ry + _PX(6)), count_str, f_count, _GRADIENT_BLUE, img)
        else:
            _draw_text(draw, (x1 - _PX(60), ry + _PX(6)), count_str, f_count, _TEXT, img)


_PLATFORM_LABELS = {
    "telegram": "Telegram",
    "discord": "Discord",
    "qq_official": "QQ 官方",
    "qq_private": "QQ 私有",
    "wechat": "微信",
}


def _draw_platform_donut(img, xy, platform_stats: Dict[str, int]):
    """高级平台分布圆环图（现代玻璃态设计 + 动态视觉效果）。

    platform_stats: {platform_key: count}
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if not platform_stats:
        _draw_empty_state(img, xy, "暂无平台数据")
        return

    items = sorted(((k, _to_int(v)) for k, v in platform_stats.items()), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1

    # 圆环布局优化：左侧圆环，右侧图例
    donut_d = min(inner_h, inner_w * 0.45)  # 稍微缩小圆环，为图例留出更多空间
    donut_r_out = donut_d / 2
    donut_r_in = donut_r_out * 0.6  # 稍微增大内径比例
    cx = x0 + donut_r_out + _PX(16)
    cy = y0 + inner_h / 2

    # 创建圆环图层
    donut_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(donut_layer)

    start = -90.0
    for idx, (plat, val) in enumerate(items):
        color = _GRADIENT_FULL[idx % len(_GRADIENT_FULL)]
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
            
        # 绘制扇形（带抗锯齿效果）
        ld.pieslice(
            [cx - donut_r_out, cy - donut_r_out, cx + donut_r_out, cy + donut_r_out],
            start, start + sweep, fill=color + (255,),
        )
        start += sweep

    _draw_donut_separators(ld, cx, cy, donut_r_in, donut_r_out, items, total)

    # 添加圆环阴影效果
    shadow_offset = _PX(2)
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    
    # 绘制阴影圆环
    shadow_draw.pieslice(
        [cx - donut_r_out + shadow_offset, cy - donut_r_out + shadow_offset, 
         cx + donut_r_out + shadow_offset, cy + donut_r_out + shadow_offset],
        0, 360, fill=(0, 0, 0, 30),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(_PX(3)))
    img.alpha_composite(shadow_layer)

    # 中心镂空：用透明色重绘内圆，形成真正的圆环（避免全图 alpha 被置 255）
    ld.ellipse(
        [cx - donut_r_in, cy - donut_r_in, cx + donut_r_in, cy + donut_r_in],
        fill=(0, 0, 0, 0),
    )
    img.alpha_composite(donut_layer)

    # 中心区域装饰（玻璃态效果）
    center_bg = Image.new("RGBA", (int(donut_r_in * 2), int(donut_r_in * 2)), (255, 255, 255, 15))
    center_bg = center_bg.filter(ImageFilter.GaussianBlur(_PX(8)))
    img.paste(center_bg, (int(cx - donut_r_in), int(cy - donut_r_in)), center_bg)

    # 中心总量文字（渐变效果）
    f_total = _get_font(_PX(32), bold=True)
    f_total_lbl = _get_font(_PX(16))
    total_str = f"{total:,}"
    tw = _text_width(draw, total_str, f_total)
    _draw_gradient_text(draw, (cx - tw / 2, cy - _PX(28)), total_str, f_total, _GRADIENT_BLUE, img)
    
    # 总消息标签
    lw = _text_width(draw, "总消息", f_total_lbl)
    _draw_text(draw, (cx - lw / 2, cy + _PX(20)), "总消息", f_total_lbl, _TEXT_LIGHT, img)

    # 右侧图例区域（玻璃态背景）
    legend_h = inner_h - _PX(32)
    legend_bg = Image.new("RGBA", (inner_w - donut_d - _PX(56), legend_h), (255, 255, 255, 20))
    legend_bg = legend_bg.filter(ImageFilter.GaussianBlur(_PX(10)))
    img.paste(legend_bg, (x0 + donut_d + _PX(48), y0 + _PX(16)), legend_bg)

    # 图例边框
    legend_border = Image.new("RGBA", (inner_w - donut_d - _PX(56), legend_h), (0, 0, 0, 0))
    legend_border_draw = ImageDraw.Draw(legend_border)
    _round_rect(legend_border_draw, (0, 0, inner_w - donut_d - _PX(56), legend_h), 
                _PX(12), outline=(255, 255, 255, 40), width=_PX(1))
    img.paste(legend_border, (x0 + donut_d + _PX(48), y0 + _PX(16)), legend_border)

    # 图例内容
    f_name = _get_font(_PX(17))
    f_count = _get_font(_PX(16))
    row_h = _PX(42)
    legend_x = x0 + donut_d + _PX(56)
    legend_w = x1 - legend_x - _PX(16)
    max_rows = max(1, int(legend_h // row_h))
    
    for idx, (plat, val) in enumerate(items[:max_rows]):
        ry = y0 + _PX(16) + idx * row_h
        if ry + row_h > y1 - _PX(16):
            break
            
        color = _GRADIENT_FULL[idx % len(_GRADIENT_FULL)]
        label = _PLATFORM_LABELS.get(plat, plat or "未知")
        pct = val * 100 / total

        # 图例颜色标识
        color_dot = Image.new("RGBA", (_PX(20), row_h), (0, 0, 0, 0))
        color_draw = ImageDraw.Draw(color_dot)
        color_draw.ellipse([0, _PX(11), _PX(20), _PX(11) + _PX(20)], fill=color + (255,))
        img.paste(color_dot, (legend_x, ry), color_dot)
        
        # 平台名称
        _draw_text(draw, (legend_x + _PX(28), ry + _PX(8)), label, f_name, _TEXT, img)

        # 进度条背景
        bar_x = legend_x + _PX(28)
        bar_y = ry + _PX(28)
        bar_w = legend_w - _PX(28)
        bar_bg = Image.new("RGBA", (bar_w, _PX(9)), (0, 0, 0, 0))
        bar_bg_draw = ImageDraw.Draw(bar_bg)
        _round_rect(bar_bg_draw, (0, 0, bar_w, _PX(9)), _PX(5), fill=_TRACK)
        img.paste(bar_bg, (bar_x, bar_y), bar_bg)

        # 进度条（带渐变效果）
        fill_w = int(bar_w * (val / total))
        if fill_w > 0:
            bar_fill = Image.new("RGBA", (fill_w, _PX(9)), (0, 0, 0, 0))
            bar_fill_draw = ImageDraw.Draw(bar_fill)
            _round_rect(bar_fill_draw, (0, 0, fill_w, _PX(9)), _PX(5), fill=color + (255,))
            img.paste(bar_fill, (bar_x, bar_y), bar_fill)

        # 数值和百分比
        txt = f"{val:,} ({pct:.1f}%)"
        tw2 = _text_width(draw, txt, f_count)
        _draw_text(draw, (x1 - tw2 - _PX(8), ry + _PX(6)), txt, f_count, _TEXT_LIGHT, img)


def _draw_content_types(img, xy, content_types: List[Dict]):
    """内容类型分布圆环图（玻璃态，与平台分布风格统一）。

    Args:
        img: PIL Image 对象
        xy: 绘制区域 (x0, y0, x1, y1)
        content_types: 内容类型统计 [{"type","label","count"}]
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)

    if isinstance(content_types, dict):
        content_types = [
            {"type": k, "label": k, "count": v} for k, v in content_types.items()
        ]

    if not content_types:
        _draw_empty_state(img, xy, "暂无内容类型数据")
        return

    items = [
        (ct.get("label") or ct.get("type") or "未知", _to_int(ct.get("count", 0)))
        for ct in content_types
    ]
    items = [(lbl, v) for lbl, v in items if v > 0]
    if not items:
        _draw_empty_state(img, xy, "暂无内容类型数据")
        return

    items.sort(key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1

    donut_d = min(inner_h, inner_w * 0.45)
    donut_r_out = donut_d / 2
    donut_r_in = donut_r_out * 0.6
    cx = x0 + donut_r_out + _PX(16)
    cy = y0 + inner_h / 2

    donut_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(donut_layer)

    start = -90.0
    for idx, (lbl, val) in enumerate(items):
        color = _GRADIENT_FULL[idx % len(_GRADIENT_FULL)]
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
        ld.pieslice(
            [cx - donut_r_out, cy - donut_r_out, cx + donut_r_out, cy + donut_r_out],
            start, start + sweep, fill=color + (255,),
        )
        start += sweep

    _draw_donut_separators(ld, cx, cy, donut_r_in, donut_r_out, items, total)

    shadow_offset = _PX(2)
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.pieslice(
        [cx - donut_r_out + shadow_offset, cy - donut_r_out + shadow_offset,
         cx + donut_r_out + shadow_offset, cy + donut_r_out + shadow_offset],
        0, 360, fill=(0, 0, 0, 30),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(_PX(3)))
    img.alpha_composite(shadow_layer)

    ld.ellipse(
        [cx - donut_r_in, cy - donut_r_in, cx + donut_r_in, cy + donut_r_in],
        fill=(0, 0, 0, 0),
    )
    img.alpha_composite(donut_layer)

    center_bg = Image.new("RGBA", (int(donut_r_in * 2), int(donut_r_in * 2)), (255, 255, 255, 15))
    center_bg = center_bg.filter(ImageFilter.GaussianBlur(_PX(8)))
    img.paste(center_bg, (int(cx - donut_r_in), int(cy - donut_r_in)), center_bg)

    f_total = _get_font(_PX(32), bold=True)
    f_total_lbl = _get_font(_PX(16))
    total_str = f"{total:,}"
    tw = _text_width(draw, total_str, f_total)
    _draw_gradient_text(draw, (cx - tw / 2, cy - _PX(28)), total_str, f_total, _GRADIENT_BLUE, img)
    lw = _text_width(draw, "内容分布", f_total_lbl)
    _draw_text(draw, (cx - lw / 2, cy + _PX(20)), "内容分布", f_total_lbl, _TEXT_LIGHT, img)

    legend_h = inner_h - _PX(32)
    legend_w = inner_w - donut_d - _PX(56)
    legend_bg = Image.new("RGBA", (legend_w, legend_h), (255, 255, 255, 20))
    legend_bg = legend_bg.filter(ImageFilter.GaussianBlur(_PX(10)))
    img.paste(legend_bg, (x0 + donut_d + _PX(48), y0 + _PX(16)), legend_bg)

    legend_border = Image.new("RGBA", (legend_w, legend_h), (0, 0, 0, 0))
    legend_border_draw = ImageDraw.Draw(legend_border)
    _round_rect(legend_border_draw, (0, 0, legend_w, legend_h),
                _PX(12), outline=(255, 255, 255, 40), width=_PX(1))
    img.paste(legend_border, (x0 + donut_d + _PX(48), y0 + _PX(16)), legend_border)

    f_name = _get_font(_PX(17))
    f_count = _get_font(_PX(16))
    row_h = _PX(42)
    legend_x = x0 + donut_d + _PX(56)
    legend_w2 = x1 - legend_x - _PX(16)
    max_rows = max(1, int(legend_h // row_h))

    for idx, (lbl, val) in enumerate(items[:max_rows]):
        ry = y0 + _PX(16) + idx * row_h
        if ry + row_h > y1 - _PX(16):
            break

        color = _GRADIENT_FULL[idx % len(_GRADIENT_FULL)]
        pct = val * 100 / total

        color_dot = Image.new("RGBA", (_PX(20), row_h), (0, 0, 0, 0))
        color_draw = ImageDraw.Draw(color_dot)
        color_draw.ellipse([0, _PX(11), _PX(20), _PX(11) + _PX(20)], fill=color + (255,))
        img.paste(color_dot, (legend_x, ry), color_dot)

        _draw_text(draw, (legend_x + _PX(28), ry + _PX(8)), lbl, f_name, _TEXT, img)

        bar_x = legend_x + _PX(28)
        bar_y = ry + _PX(28)
        bar_w = legend_w2 - _PX(28)
        bar_bg = Image.new("RGBA", (bar_w, _PX(9)), (0, 0, 0, 0))
        bar_bg_draw = ImageDraw.Draw(bar_bg)
        _round_rect(bar_bg_draw, (0, 0, bar_w, _PX(9)), _PX(5), fill=_TRACK)
        img.paste(bar_bg, (bar_x, bar_y), bar_bg)

        fill_w = int(bar_w * (val / total))
        if fill_w > 0:
            bar_fill = Image.new("RGBA", (fill_w, _PX(9)), (0, 0, 0, 0))
            bar_fill_draw = ImageDraw.Draw(bar_fill)
            _round_rect(bar_fill_draw, (0, 0, fill_w, _PX(9)), _PX(5), fill=color + (255,))
            img.paste(bar_fill, (bar_x, bar_y), bar_fill)

        txt = f"{val:,} ({pct:.1f}%)"
        tw2 = _text_width(draw, txt, f_count)
        _draw_text(draw, (x1 - tw2 - _PX(8), ry + _PX(6)), txt, f_count, _TEXT_LIGHT, img)


def _draw_platform_detail(img, xy, platforms: List[Dict]):
    """平台消息详情堆叠柱状图（对齐 WebUI platformDetailChart：各平台群聊/私聊/频道堆叠柱）。

    platforms: [{"platform","platform_name","total","group_count","private_count","channel_count",...}]
    """
    x0, y0, x1, y1 = xy
    inner_w = x1 - x0
    inner_h = y1 - y0
    draw = ImageDraw.Draw(img)
    if isinstance(platforms, dict):
        platforms = [{"platform": k, "total": v} for k, v in platforms.items()]
    if not platforms:
        _draw_empty_state(img, xy, "暂无平台数据")
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
        return sum(_to_int(p.get(k, 0)) for _, k, _ in series_defs)

    max_total = max((seg_total(p) for p in platforms), default=1) or 1

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    for g in range(4):
        gy = chart_top + g * chart_h / 3
        ld.line([(x0, gy), (x1, gy)], fill=(0, 0, 0, 16), width=_PX(1))

    n = len(platforms)
    slot_w = inner_w / n
    bar_w = min(slot_w * 0.55, _PX(60))

    f_val = _get_font(_PX(14))
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
            ld.rectangle([cx_bar, seg_top, cx_bar + bar_w, seg_bottom], fill=color + (255,))
            seg_bottom = seg_top

        # 顶部段圆角（对齐 WebUI 柱状图圆角质感）
        top_v = next((_to_int(p.get(k, 0)) for lbl, k, c in reversed(series_defs) if _to_int(p.get(k, 0)) > 0), 0)
        top_h = h_total * top_v / total
        top_y = chart_bottom - h_total
        r = min(_PX(5), bar_w / 2, top_h / 2)
        if r > 1:
            top_color = next(c for lbl, k, c in reversed(series_defs) if _to_int(p.get(k, 0)) > 0)
            ld.rounded_rectangle([cx_bar, top_y, cx_bar + bar_w, top_y + top_h], radius=r, fill=top_color + (255,))
            if top_h > r:
                ld.rectangle([cx_bar, top_y + top_h - r, cx_bar + bar_w, top_y + top_h], fill=top_color + (255,))

        # 柱顶总量
        total_str = f"{total:,}"
        tw = _text_width(draw, total_str, f_val)
        _draw_text(draw, (cx_bar + bar_w / 2 - tw / 2, top_y - _PX(18)), total_str, f_val, _TEXT_LIGHT, img)

    img.alpha_composite(layer)

    # 图例（左上角，对齐 WebUI legend 三色）
    f_legend = _get_font(_PX(14))
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
    f_lbl = _get_font(_PX(15))
    for i, p in enumerate(platforms):
        label = _truncate(draw, str(p.get("platform_name") or p.get("platform") or "未知"), f_lbl, int(slot_w - _PX(6)))
        lw = _text_width(draw, label, f_lbl)
        lx = x0 + slot_w * i + (slot_w - lw) / 2
        _draw_text(draw, (lx, chart_bottom + _PX(8)), label, f_lbl, _TEXT_LIGHT, img)

    _draw_text(draw, (x0, y0 + _PX(18)), f"峰值 {max_total:,}", _get_font(_PX(14)), _TEXT_LIGHT, img)


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
    """渲染高级仪表盘快照 PNG（现代玻璃态UI设计）。

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

    # 增加画布高度以容纳更多内容
    canvas_h = _PX(3000)
    img = _make_background((_W_FULL, canvas_h))
    
    # 预模糊背景，供所有毛玻璃卡片复用
    # 使用更精细的模糊参数创造更好的景深效果
    blurred_bg = img.filter(ImageFilter.GaussianBlur(_PX(16)))

    y = _PX(_PADDING)
    
    # 1. 绘制头部（增强版）
    y = _draw_header(img, y, stats, generated_at)
    y += _PX(18)  # 增加间距
    
    # 2. 绘制统计卡片（玻璃态增强版）
    y = _draw_stat_cards(img, blurred_bg, y, stats, db_table_count)
    y += _PX(22)

    # 3. 时间趋势卡片（高级图表）
    chart_h = _PX(260)  # 增加高度
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + chart_h + _PX(52)), 
                     title="消息时间趋势", accent=_GRADIENT_BLUE[0])
    _draw_timeline(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(72), _W_FULL - _PX(_PADDING) - _PX(24), y + chart_h + _PX(40)),
        timeline,
    )
    y += chart_h + _PX(52) + _PX(22)

    # 4. 平台分布卡片（高级圆环图）
    plat_h = _PX(300)  # 增加高度
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + plat_h), 
                     title="平台分布", accent=_GRADIENT_FULL[0])
    _draw_platform_donut(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(72), _W_FULL - _PX(_PADDING) - _PX(24), y + plat_h - _PX(20)),
        platform_stats,
    )
    y += plat_h + _PX(22)

    # 5. 发送者 + 群组排行（玻璃态排行榜）
    gap = _PX(_CARD_GAP)
    half_w = (_W_FULL - 2 * _PX(_PADDING) - gap) // 2
    rank_h = _PX(380)  # 增加高度
    left_xy = (_PX(_PADDING), y, _PX(_PADDING) + half_w, y + rank_h)
    right_xy = (_PX(_PADDING) + half_w + gap, y, _W_FULL - _PX(_PADDING), y + rank_h)
    _draw_glass_card(img, blurred_bg, left_xy, title="发送者排行 Top 8", accent=_GRADIENT_BLUE[2])
    _draw_glass_card(img, blurred_bg, right_xy, title="群组活跃度排行 Top 8", accent=_GRADIENT_FULL[1])

    for g in group_ranking:
        gid = str(g.get("group_id") or "")
        plat = str(g.get("platform") or "")
        g["display_name"] = f"{gid} ({plat})" if gid and plat else (gid or plat or "未知")

    _draw_ranking(
        img,
        (left_xy[0] + _PX(24), left_xy[1] + _PX(72), left_xy[2] - _PX(24), left_xy[3] - _PX(20)),
        sender_ranking, "sender_name", "count", _GRADIENT_BLUE[2],
    )
    _draw_ranking(
        img,
        (right_xy[0] + _PX(24), right_xy[1] + _PX(72), right_xy[2] - _PX(24), right_xy[3] - _PX(20)),
        group_ranking, "display_name", "count", _GRADIENT_FULL[1],
    )
    y += rank_h + _PX(22)

    # 6. 平台消息详情卡片（高级堆叠图）
    pd_h = _PX(320)  # 增加高度
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + pd_h), 
                     title="平台消息详情", accent=_GRADIENT_FULL[3])
    _draw_platform_detail(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(72), _W_FULL - _PX(_PADDING) - _PX(24), y + pd_h - _PX(20)),
        platform_detail or [],
    )
    y += pd_h + _PX(22)

    # 7. 内容类型分布（高级饼图）
    ct_h = _PX(350)  # 增加高度
    _draw_glass_card(img, blurred_bg, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + ct_h), 
                     title="消息内容类型分布", accent=_GRADIENT_FULL[5])
    _draw_content_types(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(72), _W_FULL - _PX(_PADDING) - _PX(24), y + ct_h - _PX(20)),
        content_types,
    )
    y += ct_h + _PX(22)

    # 8. 底部信息区域（玻璃态水印）
    watermark_bg = Image.new("RGBA", (_W_FULL - _PX(32), _PX(40)), (255, 255, 255, 15))
    watermark_bg = watermark_bg.filter(ImageFilter.GaussianBlur(_PX(8)))
    img.paste(watermark_bg, (_PX(16), y), watermark_bg)
    
    draw = ImageDraw.Draw(img)
    watermark_text = "由狐狸插件 /huli_record snapshot 生成 · Liquid Glass 风格 v2.1"
    f_watermark = _get_font(_PX(12))
    _draw_text(draw, (_PX(24), y + _PX(12)), watermark_text, f_watermark, _TEXT_LIGHT, img)

    # 9. 最终处理
    final_h = y + _PX(48)
    img = img.crop((0, 0, _W_FULL, final_h))
    
    # 使用高质量降采样
    img = img.resize((_W, int(final_h / _SCALE)), Image.LANCZOS)

    # 保存为优化的PNG
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True, quality=95)
    return buf.getvalue()
