"""WebUI 仪表盘快照渲染器 - 现代优雅版

用 Pillow 把数据库统计数据渲染成一张与 WebUI 风格一致的 PNG，
供 /狐狸记录 快照 指令直接发到聊天。

视觉设计：
1. 渐变背景 - 淡蓝到淡紫的优雅渐变
2. 现代玻璃卡片 - 半透明白色背景 + 柔和阴影 + 细腻边框
3. 优雅的文字层次 - 清晰的对比度和层次感
4. 精美的图表 - 简洁而不失优雅的设计
5. 2x 超采样 + LANCZOS 降采样保证清晰
6. NotoSansCJK 矢量字体 + NotoColorEmoji 彩色 emoji
"""

import io
import numbers
import time
import unicodedata
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
    if isinstance(value, numbers.Number):
        try:
            return int(value)
        except (ValueError, TypeError, OverflowError):
            return default
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (ValueError, TypeError):
            return default
    return default


def _safe_time_str(ts_ms: float, fmt: str, fallback: str = "") -> str:
    """将毫秒时间戳安全格式化为本地时间字符串。

    对超范围/非法时间戳返回 fallback，避免 time.localtime 抛
    OverflowError/OSError 导致整个快照渲染崩溃。
    """
    if not ts_ms:
        return fallback
    try:
        return time.strftime(fmt, time.localtime(float(ts_ms) / 1000))
    except (ValueError, TypeError, OverflowError, OSError):
        return fallback


def _sanitize_label(value, default="未知") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    cleaned = []
    for ch in text:
        category = unicodedata.category(ch)
        if category.startswith("C") and ch not in "\t\n\r":
            continue
        cleaned.append(ch)
    sanitized = "".join(cleaned).strip()
    return sanitized or default


def _fmt_bytes(value) -> str:
    """把字节数格式化为人类可读的容量字符串（B/KB/MB/GB）。"""
    try:
        size = float(value)
    except (ValueError, TypeError):
        return "-"
    if size < 1024:
        return f"{int(size)} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


# ========== 布局常量 ==========

_PADDING = 34
_CARD_RADIUS = 16
_CARD_GAP = 20


# ========== 色彩配置 ==========

# 天空蓝渐变背景
_BG_GRADIENT_START = (224, 242, 254)  # #e0f2fe 极浅天空蓝
_BG_GRADIENT_END = (207, 232, 250)    # #cfe8fa 浅天空蓝
_BG_WHITE = (255, 255, 255)           # 纯白色

# 主色调（天空蓝系）
_PRIMARY = (41, 182, 246)      # #29b6f6 亮天空蓝
_SUCCESS = (77, 208, 225)      # #4dd0e1 蓝青色
_WARNING = (3, 169, 244)       # #03a9f4 天蓝
_DANGER = (2, 136, 209)        # #0288d1 深天空蓝
_PURPLE = (79, 195, 247)       # #4fc3f7 天空蓝
_INDIGO = (129, 212, 250)      # #81d4fa 浅天蓝

# 文字颜色
_TEXT_DARK = (13, 52, 89)      # 深蓝灰色文字
_TEXT_MEDIUM = (55, 94, 133)   # 中蓝灰文字
_TEXT_LIGHT = (112, 150, 183)  # 浅蓝灰文字

# 现代玻璃效果
_GLASS_FILL = (255, 255, 255, 238)    # 93% 透明白色
_GLASS_BORDER = (186, 224, 247, 120) # 天空蓝透明边框
_GLASS_SHADOW = (64, 156, 214, 40)   # 柔和天蓝阴影

# 图表颜色（天空蓝系渐变，从浅到深）
_CHART_COLORS = [
    (41, 182, 246),    # #29b6f6 亮天空蓝
    (3, 169, 244),     # #03a9f4 天蓝
    (2, 136, 209),     # #0288d1 深天空蓝
    (79, 195, 247),    # #4fc3f7 天空蓝
    (129, 212, 250),   # #81d4fa 浅天蓝
    (77, 208, 225),    # #4dd0e1 蓝青色
    (179, 229, 252),   # #b3e5fc 极浅蓝
    (1, 87, 155),      # #01579b 深藏蓝
    (0, 188, 212),     # #00bcd4 水蓝
    (66, 165, 245),    # #42a5f5 柔蓝
    (144, 202, 249),   # #90caf9 淡天蓝
    (2, 119, 189),     # #0277bd 中天空蓝
]

# 统计卡片配置
_STAT_CARDS = [
    ("总消息数", _PRIMARY),
    ("群聊消息", _SUCCESS),
    ("私聊消息", _PURPLE),
    ("频道消息", _WARNING),
    ("平台数", _INDIGO),
    ("数据表数量", (2, 136, 209)),
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

_FONT_SEARCH_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/fonts",
    "~/Library/Fonts",
    "/System/Library/Fonts",
    "C:/Windows/Fonts",
]

_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
_emoji_font: Optional[ImageFont.FreeTypeFont] = None
_emoji_font_inited = False


def _get_plugin_version() -> str:
    """从 metadata.yaml 读取插件版本，作为水印标识（避免硬编码版本过期）。"""
    try:
        meta_path = Path(__file__).resolve().parent.parent / "metadata.yaml"
        if meta_path.exists():
            for line in meta_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("version:"):
                    version = line.split(":", 1)[1].strip().strip('"\'')
                    if version:
                        return version
    except Exception:
        pass
    return "2.8.0"


def _search_font_path(name_keywords: List[str]) -> Optional[str]:
    """在常见字体目录中递归搜索匹配关键字的字体文件。"""
    seen: set = set()
    for base in _FONT_SEARCH_DIRS:
        base_path = Path(base).expanduser()
        if not base_path.is_dir():
            continue
        try:
            files = sorted(base_path.rglob("*.tt*"))
        except Exception:
            continue
        for f in files:
            if str(f) in seen:
                continue
            seen.add(str(f))
            name = f.name.lower()
            if all(k in name for k in name_keywords):
                return str(f)
    return None


def _resolve_font(bold: bool) -> Optional[str]:
    target = _FONT_BOLD if bold else _FONT_REG
    if Path(target).exists():
        return target
    for c in _FONT_FALLBACK:
        if Path(c).exists():
            return c
    # 动态搜索：优先 CJK 中文字体，其次任意可用字体
    if bold:
        found = _search_font_path(["bold", "cjk"]) or _search_font_path(["cjk"])
        if found:
            return found
    found = _search_font_path(["cjk"]) or _search_font_path(["wqy"]) or _search_font_path(["noto"])
    return found


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
    path = _EMOJI_FONT
    if not Path(path).exists():
        path = _search_font_path(["emoji"]) or _search_font_path(["color"])
    if not path or not Path(path).exists():
        _emoji_font = None
        return None
    try:
        _emoji_font = ImageFont.truetype(path, 109)
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
    
    # 创建从左上到右下的优雅渐变
    w, h = size
    for i in range(h):
        # 计算当前行的颜色
        ratio = i / h
        r = int(_BG_GRADIENT_START[0] * (1 - ratio) + _BG_GRADIENT_END[0] * ratio)
        g = int(_BG_GRADIENT_START[1] * (1 - ratio) + _BG_GRADIENT_END[1] * ratio)
        b = int(_BG_GRADIENT_START[2] * (1 - ratio) + _BG_GRADIENT_END[2] * ratio)
        draw.line([(0, i), (w, i)], fill=(r, g, b, 255))
    
    return img


# ========== 液态玻璃卡片 ==========

def _draw_glass_card(img: Image.Image, xy, title: Optional[str] = None, accent: Optional[Tuple] = None):
    """绘制现代玻璃卡片，返回内容区 (x0, y0, x1, y1)。
    
    现代简洁的玻璃效果：
    - 高透明白色背景
    - 柔和阴影
    - 简洁边框
    - 可选标题
    """
    x0, y0, x1, y1 = xy
    cw, ch = x1 - x0, y1 - y0

    # 绘制阴影
    shadow_offset = _PX(4)
    shadow = Image.new("RGBA", (cw + shadow_offset * 2, ch + shadow_offset * 2), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    _round_rect(shadow_draw, (shadow_offset, shadow_offset, cw + shadow_offset, ch + shadow_offset), 
                _CARD_RADIUS, fill=_GLASS_SHADOW)
    shadow = shadow.filter(ImageFilter.GaussianBlur(_PX(8)))
    img.paste(shadow, (x0 - shadow_offset, y0 - shadow_offset), shadow)

    # 绘制玻璃主体
    glass = Image.new("RGBA", (cw, ch), _GLASS_FILL)
    
    # 添加顶部高光效果
    highlight = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    for i in range(_PX(30)):
        alpha = int(30 * (1 - i / _PX(30)))
        highlight_draw.rectangle([0, i, cw, i + 1], fill=(255, 255, 255, alpha))
    glass.alpha_composite(highlight)
    
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
        _draw_text(draw, (x0 + _PX(24), y0 + _PX(12)), title, f_title, title_color, img)
    
    return (x0 + _PX(24), y0 + _PX(52) if title else y0 + _PX(24), x1 - _PX(24), y1 - _PX(24))


# ========== 绘制函数 ==========

def _draw_header(img, y, stats: MessageStats, generated_at: float):
    """绘制头部信息。"""
    draw = ImageDraw.Draw(img)
    f_title = _get_font(_PX(36), bold=True)
    f_sub = _get_font(_PX(17))
    x = _PADDING * _SCALE
    _paste_emoji(img, (x, y), "🦊", f_title, draw)
    x += int(f_title.size * 1.3)
    _draw_text(draw, (x, y), "狐狸插件 · 仪表盘快照", f_title, _TEXT_DARK, img)

    sub = _safe_time_str(
        generated_at, "生成时间 %Y-%m-%d %H:%M:%S",
        fallback="生成时间 --"
    )
    newest_ts = _to_int(stats.newest_timestamp, default=0)
    if newest_ts > 0:
        latest = _safe_time_str(
            newest_ts, "最新消息 %m-%d %H:%M", fallback="最新消息 --"
        )
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
    card_h = _PX(100)
    draw = ImageDraw.Draw(img)
    
    for idx in range(6):
        col = idx % 3
        row = idx // 3
        cx = _PX(_PADDING) + col * (card_w + gap)
        cy = y + row * (card_h + gap)
        label, color = _STAT_CARDS[idx]
        
        # 绘制卡片
        _draw_glass_card(img, (cx, cy, cx + card_w, cy + card_h), accent=color)
        
        f_val = _get_font(_PX(32), bold=True)
        f_lbl = _get_font(_PX(15))
        val_str = f"{values[idx]:,}" if isinstance(values[idx], int) else str(values[idx])
        
        # 数值文字（居中）
        vw = _text_width(draw, val_str, f_val)
        vx = cx + (card_w - vw) // 2
        _draw_text(draw, (vx, cy + _PX(20)), val_str, f_val, _TEXT_DARK, img)
        
        # 标签文字（居中）
        lw = _text_width(draw, label, f_lbl)
        _draw_text(draw, (cx + (card_w - lw) // 2, cy + _PX(56)), label, f_lbl, _TEXT_MEDIUM, img)
    
    return y + 2 * card_h + gap + _PX(20)


def _draw_mysql_card(img, y, mysql_status: Optional[Dict] = None) -> int:
    """绘制 MySQL 连接状态卡片（单列信息布局）。

    展示 MySQL 连接状态、服务器版本与当前存储后端；
    卡片高度按信息行数动态计算，避免文字溢出卡片底部。
    """
    x0 = _PX(_PADDING)
    x1 = _W_FULL - _PX(_PADDING)
    draw = ImageDraw.Draw(img)

    status = mysql_status or {}
    connected = bool(status.get("connected"))
    fallback = bool(status.get("fallback_active"))
    version = status.get("version") or None
    table_count = status.get("table_count")
    db_size = status.get("db_size")

    if connected:
        title = "MySQL 存储"
        state_text = "运行中"
        accent = _SUCCESS
    elif fallback:
        title = "MySQL 存储"
        state_text = "SQLite 降级"
        accent = _WARNING
    else:
        title = "MySQL 存储"
        state_text = "未连接"
        accent = (176, 190, 197)

    f_val = _get_font(_PX(18), bold=True)
    parts = []
    if connected:
        parts.append(("服务器版本", version or "未知"))
        parts.append(("数据表", "-" if table_count is None else f"{table_count} 张"))
        parts.append(("数据库大小", _fmt_bytes(db_size) if db_size is not None else "-"))
        parts.append(("连接状态", "已连接"))
    elif fallback:
        unsynced = status.get("unsynced_count")
        parts.append(("存储后端", "本地 SQLite"))
        if unsynced is not None:
            parts.append(("待同步消息", f"{unsynced} 条"))
        parts.append(("连接状态", "MySQL 不可用，降级中"))
    else:
        parts.append(("存储后端", "未知"))
        parts.append(("连接状态", "未连接"))

    line_h = _PX(40)
    card_h = _PX(52) + line_h * len(parts) + _PX(16)

    _draw_glass_card(img, (x0, y, x1, y + card_h), title=title, accent=accent)

    f_state = _get_font(_PX(20), bold=True)
    sw = _text_width(draw, state_text, f_state)
    sx = x1 - sw - _PX(24)
    sy = y + _PX(10)
    _draw_text(draw, (sx, sy), state_text, f_state, accent, img)

    cx = x0 + _PX(24)
    cy = y + _PX(52)
    for k, v in parts:
        _draw_text(draw, (cx, cy), f"{k}: {v}", f_val, _TEXT_DARK, img)
        cy += line_h

    return y + card_h + _PX(12)


def _draw_redis_card(img, y, redis_status: Optional[Dict] = None) -> int:
    """绘制 Redis 缓存状态卡片（单列信息布局）。

    卡片高度按信息行数动态计算，避免文字溢出卡片底部。
    """
    x0 = _PX(_PADDING)
    x1 = _W_FULL - _PX(_PADDING)
    draw = ImageDraw.Draw(img)

    status = redis_status or {}
    configured = bool(status.get("configured"))
    available = bool(status.get("available"))
    enabled = bool(status.get("enabled"))

    if not configured:
        title = "Redis 缓存"
        state_text = "未启用"
        accent = (176, 190, 197)
    elif available:
        title = "Redis 缓存"
        state_text = "运行中"
        accent = (38, 166, 154)
    else:
        title = "Redis 缓存"
        state_text = "已降级（SQLite/无缓存）" if enabled else "已配置未启用"
        accent = (255, 167, 38) if enabled else (176, 190, 197)

    # 准备信息行（端点在配置未启用时仍展示，keys 仅在可用时展示）
    f_val = _get_font(_PX(18), bold=True)
    endpoint = f"{status.get('host') or '-'}:{status.get('port') or '-'}"
    parts = [
        ("连接", endpoint),
        ("库", f"db{status.get('db')}" if status.get("db") is not None else "-"),
        ("TTL", f"{status.get('ttl')}s" if status.get("ttl") is not None else "-"),
    ]
    if available:
        version = status.get("version")
        if version:
            parts.insert(1, ("版本", str(version)))
        key_count = status.get("key_count")
        if key_count is not None:
            parts.append(("键数量", f"{key_count} 个"))
        memory_human = status.get("memory_human")
        if memory_human:
            parts.append(("内存占用", str(memory_human)))
        keys = status.get("keys") or {}
        stats_n = keys.get("stats")
        recent_n = keys.get("recent_messages")
        parts.append(("统计缓存", "-" if stats_n is None else f"{stats_n} 条"))
        parts.append(("最近消息", "-" if recent_n is None else f"{recent_n} 条"))

    # 卡片高度 = 标题区 + 每行行高 + 底部留白
    # 标题绘制于 y + _PX(12)，内容区约定从 y + _PX(52) 开始，避免信息行压住标题
    line_h = _PX(40)
    card_h = _PX(52) + line_h * len(parts) + _PX(16)

    _draw_glass_card(img, (x0, y, x1, y + card_h), title=title, accent=accent)

    # 状态徽标（右侧，与标题同行对齐，避免与信息行重合）
    f_state = _get_font(_PX(20), bold=True)
    sw = _text_width(draw, state_text, f_state)
    sx = x1 - sw - _PX(24)
    sy = y + _PX(10)
    _draw_text(draw, (sx, sy), state_text, f_state, accent, img)

    # 信息行（标题下方内容区，左侧）
    cx = x0 + _PX(24)
    cy = y + _PX(52)
    for k, v in parts:
        _draw_text(draw, (cx, cy), f"{k}: {v}", f_val, _TEXT_DARK, img)
        cy += line_h

    return y + card_h + _PX(12)


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

    # 计算Y轴标签最大宽度，为标签预留空间，避免超出卡片边框
    f_axis = _get_font(_PX(15))
    axis_w = 0
    for g in range(5):
        value = int(max_c * (1 - g / 4))
        label = f"{value:,}"
        axis_w = max(axis_w, _text_width(draw, label, f_axis))
    plot_x0 = x0 + axis_w + _PX(12)
    inner_w = x1 - plot_x0
    step_x = inner_w / max(n - 1, 1) if n > 1 else inner_w

    # 绘制网格线
    for g in range(5):
        gy = y0 + _PX(8) + g * (inner_h - _PX(16)) / 4
        alpha = 30 if g == 0 or g == 4 else 15
        draw.line([(plot_x0, gy), (x1, gy)], fill=(0, 0, 0, alpha), width=_PX(1))

    # 绘制Y轴标签（右对齐到绘图区左侧，落在卡片边框内侧）
    for g in range(5):
        gy = y0 + _PX(8) + g * (inner_h - _PX(16)) / 4
        value = int(max_c * (1 - g / 4))
        label = f"{value:,}"
        tw = _text_width(draw, label, f_axis)
        _draw_text(draw, (plot_x0 - tw - _PX(6), gy - _PX(6)), label, f_axis, _TEXT_MEDIUM, img)

    def to_points(vals):
        pts = []
        for i, v in enumerate(vals):
            px = plot_x0 + (i * step_x if n > 1 else inner_w / 2)
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
    f_legend = _get_font(_PX(15), bold=True)
    lx = plot_x0 + _PX(16)
    ly = y0 - _PX(20)
    
    for label, key, color in series_defs:
        # 图例线条
        draw.line([(lx, ly + _PX(4)), (lx + _PX(16), ly + _PX(4))], fill=color, width=_PX(3))
        # 图例标签
        lw = _text_width(draw, label, f_legend)
        _draw_text(draw, (lx + _PX(20), ly), label, f_legend, _TEXT_DARK, img)
        lx += _PX(36) + lw + _PX(16)

    # 绘制X轴标签
    f_lbl = _get_font(_PX(15))
    label_indices = list(range(n)) if n <= 8 else [0, n // 4, n // 2, 3 * n // 4, n - 1]
    
    for i in label_indices:
        if 0 <= i < n:
            label = str(timeline[i].get("date", ""))[-5:]
            tw = _text_width(draw, label, f_lbl)
            px = plot_x0 + (i * step_x if n > 1 else inner_w / 2)
            lpx = px - tw / 2
            lpx = max(plot_x0, min(lpx, x1 - tw))
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

    f_name = _get_font(_PX(15))
    f_count = _get_font(_PX(15), bold=True)
    f_rank = _get_font(_PX(15), bold=True)
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
            
        name = _sanitize_label(it.get(name_key) or it.get("sender_id") or it.get("group_id"))
        name = _truncate_middle(draw, name, f_name, inner_w - _PX(140))
        count = _to_int(it.get(count_key, 0))
        count_str = f"{count:,}"

        # 排名徽章
        badge_size = _PX(20)
        if i < len(rank_colors):
            rank_color = rank_colors[i]
            draw.ellipse([x0 + _PX(8), ry + _PX(8), x0 + badge_size + _PX(8), ry + badge_size + _PX(8)], 
                       fill=rank_color)
            rank_color_text = (0, 0, 0)  # 金银铜用黑色文字
        else:
            draw.ellipse([x0 + _PX(8), ry + _PX(8), x0 + badge_size + _PX(8), ry + badge_size + _PX(8)], 
                       fill=(229, 231, 235))
            rank_color_text = (107, 114, 128)  # 其他排名用灰色文字
        
        # 排名文字
        rank_txt = str(i + 1)
        rw = _text_width(draw, rank_txt, f_rank)
        _draw_text(draw, (x0 + badge_size // 2 + _PX(8) - rw // 2, ry + _PX(8)), rank_txt, f_rank, rank_color_text, img)

        # 名称
        _draw_text(draw, (x0 + _PX(40), ry + _PX(8)), name, f_name, _TEXT_DARK, img)

        # 进度条背景
        bar_y = ry + _PX(24)
        bar_w = inner_w - _PX(160)
        bar_bg = Image.new("RGBA", (bar_w, _PX(6)), (0, 0, 0, 0))
        bar_bg_draw = ImageDraw.Draw(bar_bg)
        _round_rect(bar_bg_draw, (0, 0, bar_w, _PX(6)), _PX(3), fill=(229, 231, 235))
        img.paste(bar_bg, (x0 + _PX(40), bar_y), bar_bg)

        # 进度条填充 - 修复颜色问题
        fill_w = int(bar_w * (count / max_c))
        if fill_w > 0:
            bar_fill = Image.new("RGBA", (fill_w, _PX(6)), (0, 0, 0, 0))
            bar_fill_draw = ImageDraw.Draw(bar_fill)
            # 使用正确的RGBA格式
            fill_color = color + (180,) if len(color) == 3 else color
            _round_rect(bar_fill_draw, (0, 0, fill_w, _PX(6)), _PX(3), fill=fill_color)
            img.paste(bar_fill, (x0 + _PX(40), bar_y), bar_fill)

        # 数值
        count_w = _text_width(draw, count_str, f_count)
        _draw_text(draw, (x1 - count_w - _PX(8), ry + _PX(8)), count_str, f_count, _TEXT_DARK, img)


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
    f_name = _get_font(_PX(15))
    f_count = _get_font(_PX(15))

    # 数值文字宽度（右对齐到卡片边缘），进度条需让出该区域避免遮挡
    max_val_w = 0
    for idx, (plat, val) in enumerate(items):
        if idx >= 5:
            break
        pct = val * 100 / total
        txt = f"{val:,} ({pct:.1f}%)"
        max_val_w = max(max_val_w, _text_width(draw, txt, f_count))

    # 进度条宽度 = 图例可用宽度 - 数值文字区 - 间距（保证高占比也不遮挡）
    bar_w = legend_w - _PX(100) - max_val_w - _PX(16)
    bar_w = max(bar_w, _PX(20))

    for idx, (plat, val) in enumerate(items):
        if idx >= 5:  # 最多显示5个
            break
            
        ry = y0 + _PX(20) + idx * _PX(32)
        if ry + _PX(32) > y1 - _PX(20):
            break
            
        color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        label = _sanitize_label(_PLATFORM_LABELS.get(plat, plat), "未知")
        label = _truncate(draw, label, f_name, _PX(72))
        pct = val * 100 / total

        # 颜色标识
        draw.ellipse([legend_x, ry + _PX(8), legend_x + _PX(12), ry + _PX(20)], fill=color)
        
        # 平台名称
        _draw_text(draw, (legend_x + _PX(20), ry + _PX(8)), label, f_name, _TEXT_DARK, img)

        # 进度条（宽度已为右侧数值区让位）
        bar_x = legend_x + _PX(100)
        bar_y = ry + _PX(12)
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
    """绘制内容类型分布饼图。"""
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
    
    # 如果数据项太多，合并后面的为"其他"
    max_display_items = 6
    if len(items) > max_display_items:
        other_items = items[max_display_items:]
        other_count = sum(v for _, v in other_items)
        items = items[:max_display_items]
        items.append(("其他", other_count))

    # 饼图布局优化
    pie_d = min(inner_h - _PX(20), inner_w * 0.44)
    pie_r = pie_d / 2
    cx = x0 + pie_r + _PX(30)
    cy = y0 + inner_h / 2
    
    # 绘制饼图背景
    draw.ellipse([cx - pie_r, cy - pie_r, cx + pie_r, cy + pie_r], fill=(245, 247, 250))

    # 绘制饼图
    start = -90.0
    for idx, (lbl, val) in enumerate(items):
        if idx >= len(_CHART_COLORS):
            # 如果颜色不够，循环使用颜色
            color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        else:
            color = _CHART_COLORS[idx]
        sweep = val * 360.0 / total
        if sweep <= 0:
            continue
        
        # 绘制扇形
        draw.pieslice(
            [cx - pie_r, cy - pie_r, cx + pie_r, cy + pie_r],
            start, start + sweep, fill=color
        )
        start += sweep

    donut_inner = pie_r * 0.52
    draw.ellipse([cx - donut_inner, cy - donut_inner, cx + donut_inner, cy + donut_inner], fill=_BG_WHITE)

    total_str = f"{total:,}"
    f_total = _get_font(_PX(24), bold=True)
    f_total_lbl = _get_font(_PX(15))
    total_w = _text_width(draw, total_str, f_total)
    _draw_text(draw, (cx - total_w / 2, cy - _PX(18)), total_str, f_total, _TEXT_DARK, img)
    total_lbl = "总消息"
    total_lbl_w = _text_width(draw, total_lbl, f_total_lbl)
    _draw_text(draw, (cx - total_lbl_w / 2, cy + _PX(8)), total_lbl, f_total_lbl, _TEXT_MEDIUM, img)

    # 图例区域优化
    legend_x = x0 + pie_d + _PX(50)
    legend_w = inner_w - pie_d - _PX(70)
    f_name = _get_font(_PX(15))
    f_count = _get_font(_PX(15))
    
    # 检查是否有足够空间显示图例
    if legend_w < _PX(100):
        # 如果空间不足，缩小饼图尺寸
        pie_d = min(inner_h, inner_w * 0.4)
        pie_r = pie_d / 2
        cx = x0 + pie_r + _PX(30)
        legend_x = x0 + pie_d + _PX(50)
        legend_w = inner_w - pie_d - _PX(70)
    
    # 限制显示的数量，确保图例不超出边界
    max_legend_items = 6
    display_items = items[:max_legend_items]
    
    for idx, (lbl, val) in enumerate(display_items):
        if idx >= len(_CHART_COLORS):
            # 如果颜色不够，循环使用颜色
            color = _CHART_COLORS[idx % len(_CHART_COLORS)]
        else:
            color = _CHART_COLORS[idx]
            
        ry = y0 + _PX(30) + idx * _PX(35)
        if ry + _PX(35) > y1 - _PX(20):
            break
            
        pct = val * 100 / total

        # 颜色标识圆圈
        draw.ellipse([legend_x, ry + _PX(8), legend_x + _PX(14), ry + _PX(22)], fill=color)
        
        display_lbl = _truncate(draw, _sanitize_label(lbl), f_name, max(legend_w - _PX(140), _PX(70)))
        _draw_text(draw, (legend_x + _PX(24), ry + _PX(8)), display_lbl, f_name, _TEXT_DARK, img)

        # 数值和百分比
        txt = f"{val:,} ({pct:.1f}%)"
        tw2 = _text_width(draw, txt, f_count)
        _draw_text(draw, (x1 - tw2 - _PX(15), ry + _PX(8)), txt, f_count, _TEXT_MEDIUM, img)


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

    # 系列定义 - 使用正确的消息类型数据
    series_defs = [
        ("群聊", "group_count", _CHART_COLORS[0]),
        ("私聊", "private_count", _CHART_COLORS[1]),
        ("频道", "channel_count", _CHART_COLORS[2]),
    ]

    chart_top = y0 + _PX(48)
    chart_bottom = y1 - _PX(62)
    chart_h = chart_bottom - chart_top

    def seg_total(p: Dict) -> int:
        return sum(_to_int(p.get(k, 0)) for _, k, _ in series_defs)

    max_total = max((seg_total(p) for p in platforms), default=1) or 1
    
    # 限制显示的平台数量，避免过于拥挤
    max_platforms = 10
    display_platforms = platforms[:max_platforms]

    n = len(display_platforms)
    if n == 0:
        _draw_text(draw, (x0 + inner_w // 2, y0 + inner_h // 2), "暂无平台数据", 
                  _get_font(_PX(18)), _TEXT_MEDIUM, img)
        return
        
    slot_w = inner_w / n
    bar_w = min(slot_w * 0.6, _PX(50))

    # 绘制图例
    legend_y = y0 + _PX(15)
    f_legend = _get_font(_PX(14), bold=True)
    
    for idx, (label, key, color) in enumerate(series_defs):
        legend_x_pos = x0 + _PX(20) + idx * _PX(100)
        if legend_x_pos + _PX(50) > x1:
            break
            
        # 颜色块
        draw.rectangle([legend_x_pos, legend_y, legend_x_pos + _PX(8), legend_y + _PX(8)], fill=color)
        # 标签
        _draw_text(draw, (legend_x_pos + _PX(12), legend_y - _PX(1)), label, f_legend, _TEXT_MEDIUM, img)

    # 绘制峰值标注
    peak_font = _get_font(_PX(14), bold=True)
    peak_text = f"峰值 {max_total:,}"
    _draw_text(draw, (x1 - _text_width(draw, peak_text, peak_font) - _PX(20), y0 + _PX(15)), 
              peak_text, peak_font, _TEXT_MEDIUM, img)

    # 绘制柱状图
    f_val = _get_font(_PX(14), bold=True)
    for i, p in enumerate(display_platforms):
        cx_bar = x0 + slot_w * i + (slot_w - bar_w) / 2
        total = seg_total(p)
        
        # 即使total为0也要绘制坐标轴标签
        if total <= 0:
            zero_y = chart_bottom - _PX(2)
            draw.line([(cx_bar, zero_y), (cx_bar + bar_w, zero_y)], fill=(203, 213, 225), width=_PX(3))
            total_str = "0"
            tw = _text_width(draw, total_str, f_val)
            _draw_text(draw, (cx_bar + bar_w / 2 - tw / 2, chart_top - _PX(18)), total_str, f_val, _TEXT_MEDIUM, img)
            continue

        h_total = chart_h * total / max_total
        top_y = chart_bottom - h_total
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
        label_y = max(chart_top - _PX(16), top_y - _PX(18))
        _draw_text(draw, (cx_bar + bar_w / 2 - tw / 2, label_y), total_str, f_val, _TEXT_MEDIUM, img)

    # X轴平台名标签 - 确保所有平台标签都显示
    f_lbl = _get_font(_PX(14))
    for i, p in enumerate(display_platforms):
        label = _truncate(draw, _sanitize_label(p.get("platform_name") or p.get("platform")), f_lbl, int(slot_w - _PX(8)))
        lw = _text_width(draw, label, f_lbl)
        lx = x0 + slot_w * i + (slot_w - lw) / 2
        _draw_text(draw, (lx, chart_bottom + _PX(8)), label, f_lbl, _TEXT_MEDIUM, img)


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
    redis_status: Optional[Dict] = None,
    mysql_status: Optional[Dict] = None,
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
        redis_status: Redis 缓存状态摘要（未启用时为空 dict），默认 None
        mysql_status: MySQL 连接状态摘要（连接状态/服务器版本/存储后端），默认 None
    """
    if generated_at is None:
        generated_at = time.time()
    if platform_stats is None:
        platform_stats = stats.platform_stats or {}

    # 画布高度（预留卡片内容增长的余量，避免文字溢出底部）
    canvas_h = _PX(3200)
    img = _make_background((_W_FULL, canvas_h))

    y = _PX(_PADDING)
    
    # 1. 绘制头部
    y = _draw_header(img, y, stats, generated_at)
    y += _PX(20)
    
    # 2. 绘制统计卡片
    y = _draw_stat_cards(img, y, stats, db_table_count)
    y += _PX(30)

    # 2.2 绘制 MySQL 连接状态卡片
    y = _draw_mysql_card(img, y, mysql_status)
    y += _PX(10)

    # 2.5 绘制 Redis 缓存状态卡片
    y = _draw_redis_card(img, y, redis_status)
    y += _PX(10)

    # 3. 时间趋势卡片
    chart_h = _PX(240)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + chart_h), 
                     title="消息时间趋势", accent=_CHART_COLORS[0])
    _draw_timeline(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(52), _W_FULL - _PX(_PADDING) - _PX(24), y + chart_h - _PX(24)),
        timeline,
    )
    y += chart_h + _PX(30)

    # 4. 平台分布卡片
    plat_h = _PX(280)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + plat_h), 
                     title="平台分布", accent=_CHART_COLORS[0])
    _draw_platform_donut(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(52), _W_FULL - _PX(_PADDING) - _PX(24), y + plat_h - _PX(24)),
        platform_stats,
    )
    y += plat_h + _PX(30)

    # 5. 平台消息详情卡片
    pd_h = _PX(300)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + pd_h), 
                     title="平台消息详情", accent=_CHART_COLORS[2])
    _draw_platform_detail(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(52), _W_FULL - _PX(_PADDING) - _PX(24), y + pd_h - _PX(24)),
        platform_detail or [],
    )
    y += pd_h + _PX(30)

    # 6. 内容类型分布卡片
    ct_h = _PX(320)
    _draw_glass_card(img, (_PX(_PADDING), y, _W_FULL - _PX(_PADDING), y + ct_h), 
                     title="消息内容类型分布", accent=_CHART_COLORS[3])
    _draw_content_types(
        img,
        (_PX(_PADDING) + _PX(24), y + _PX(52), _W_FULL - _PX(_PADDING) - _PX(24), y + ct_h - _PX(24)),
        content_types,
    )
    y += ct_h + _PX(30)

    # 7. 发送者 + 群组排行
    gap = _PX(_CARD_GAP)
    half_w = (_W_FULL - 2 * _PX(_PADDING) - gap) // 2
    rank_h = _PX(390)
    left_xy = (_PX(_PADDING), y, _PX(_PADDING) + half_w, y + rank_h)
    right_xy = (_PX(_PADDING) + half_w + gap, y, _W_FULL - _PX(_PADDING), y + rank_h)
    _draw_glass_card(img, left_xy, title="发送者排行 Top 8", accent=_CHART_COLORS[0])
    _draw_glass_card(img, right_xy, title="群组活跃度排行 Top 8", accent=_CHART_COLORS[1])

    for g in group_ranking:
        gid = _sanitize_label(g.get("group_id"), "")
        plat = _sanitize_label(g.get("platform"), "")
        g["display_name"] = f"{gid} ({plat})" if gid and plat else (gid or plat or "未知")

    _draw_ranking(
        img,
        (left_xy[0] + _PX(24), left_xy[1] + _PX(52), left_xy[2] - _PX(24), left_xy[3] - _PX(24)),
        sender_ranking, "sender_name", "count", _CHART_COLORS[0],
    )
    _draw_ranking(
        img,
        (right_xy[0] + _PX(24), right_xy[1] + _PX(52), right_xy[2] - _PX(24), right_xy[3] - _PX(24)),
        group_ranking, "display_name", "count", _CHART_COLORS[1],
    )
    y += rank_h + _PX(30)

    # 8. 底部水印
    draw = ImageDraw.Draw(img)
    watermark_text = (
        f"由狐狸插件 /狐狸记录 快照 生成 · "
        f"天空蓝清新风格 v{_get_plugin_version()}"
    )
    f_watermark = _get_font(_PX(14))
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
