"""时间解析工具模块，支持自然语言和日期格式输入"""

import re
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional, Any


def get_day_start_end(date: datetime) -> Tuple[int, int]:
    """获取某天的开始和结束时间戳（毫秒）"""
    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def parse_relative_time(time_str: str) -> Optional[Tuple[int, int]]:
    """
    解析相对时间格式，如 -1d、-7d、-1h、+1d

    返回: (start_timestamp, end_timestamp) 毫秒时间戳
    """
    match = re.match(r'^([+-]?\d+)([dhm])$', time_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    now = datetime.now()

    try:
        if unit == 'd':
            # 天
            if value < 0:
                # -1d 表示过去1天（从现在往前推）
                start = now + timedelta(days=value)
                end = now
            else:
                # +1d 表示未来1天（从现在往后推）
                start = now
                end = now + timedelta(days=value)
        elif unit == 'h':
            # 小时
            if value < 0:
                start = now + timedelta(hours=value)
                end = now
            else:
                start = now
                end = now + timedelta(hours=value)
        elif unit == 'm':
            # 分钟
            if value < 0:
                start = now + timedelta(minutes=value)
                end = now
            else:
                start = now
                end = now + timedelta(minutes=value)
        else:
            return None
    except OverflowError:
        # 极端值（如 999999999999d）导致 timedelta 溢出，视为无法解析
        return None

    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def parse_date(date_str: str) -> Optional[datetime]:
    """解析日期字符串"""
    # 支持格式: 2024-01-01, 2024-01-01 12:00, 2024/01/01
    patterns = [
        r'^(\d{4})-(\d{1,2})-(\d{1,2})$',  # 2024-01-01
        r'^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2})$',  # 2024-01-01 12:00
        r'^(\d{4})/(\d{1,2})/(\d{1,2})$',  # 2024/01/01
    ]

    for pattern in patterns:
        match = re.match(pattern, date_str.strip())
        if match:
            groups = match.groups()
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            try:
                if len(groups) >= 5:
                    hour, minute = int(groups[3]), int(groups[4])
                    return datetime(year, month, day, hour, minute)
                return datetime(year, month, day)
            except ValueError:
                # 非法日期（如 2024-13-40、2024-02-30），视为无法解析
                return None
    return None


def parse_date_range(range_str: str) -> Optional[Tuple[int, int]]:
    """
    解析日期范围，格式: 2024-01-01~2024-01-15 或 2024-01-01 - 2024-01-15
    """
    # 分隔符支持 ~ 和 - (带空格)
    parts = None
    if '~' in range_str:
        parts = range_str.split('~')
    elif ' - ' in range_str:
        parts = range_str.split(' - ')

    if not parts or len(parts) != 2:
        return None

    start_date = parse_date(parts[0].strip())
    end_date = parse_date(parts[1].strip())

    if not start_date or not end_date:
        return None

    # 开始时间从当天 0:00 开始
    start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    # 结束时间到当天 23:59:59
    end = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def parse_natural_time(time_str: str) -> Optional[Tuple[int, int]]:
    """
    解析自然语言时间

    支持: today, yesterday, week, last7d, month, last30d, hour, last1h 等
    """
    now = datetime.now()
    time_str = time_str.lower().strip()

    # 自然语言映射
    natural_time_map = {
        'today': lambda: get_day_start_end(now),
        'yesterday': lambda: get_day_start_end(now - timedelta(days=1)),
        'week': lambda: (
            int((now - timedelta(days=7)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last7d': lambda: (
            int((now - timedelta(days=7)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last7days': lambda: (
            int((now - timedelta(days=7)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'month': lambda: (
            int((now - timedelta(days=30)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last30d': lambda: (
            int((now - timedelta(days=30)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last30days': lambda: (
            int((now - timedelta(days=30)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'hour': lambda: (
            int((now - timedelta(hours=1)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last1h': lambda: (
            int((now - timedelta(hours=1)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last1hour': lambda: (
            int((now - timedelta(hours=1)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last3h': lambda: (
            int((now - timedelta(hours=3)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last6h': lambda: (
            int((now - timedelta(hours=6)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last12h': lambda: (
            int((now - timedelta(hours=12)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last24h': lambda: (
            int((now - timedelta(hours=24)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last3d': lambda: (
            int((now - timedelta(days=3)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
        'last14d': lambda: (
            int((now - timedelta(days=14)).timestamp() * 1000),
            int(now.timestamp() * 1000)
        ),
    }

    # 检查是否匹配自然语言
    if time_str in natural_time_map:
        return natural_time_map[time_str]()

    # 支持数字+单位格式，如 "3d"、"7days"、"2h"
    # 数字限长 9 位，避免超长数字串触发 int() 限制或 timedelta 溢出崩溃
    match = re.match(r'^last(\d{1,9})([dh])$', time_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        days = value if unit == 'd' else 0
        hours = 0 if unit == 'd' else value
    else:
        match = re.match(r'^(\d{1,9})(days?|hours?|h|d)$', time_str)
        if not match:
            return None
        value = int(match.group(1))
        unit = match.group(2)
        if unit in ('d', 'day', 'days'):
            days, hours = value, 0
        else:
            days, hours = 0, value
    try:
        start = now - timedelta(days=days, hours=hours)
    except OverflowError:
        # 极端值导致 timedelta 溢出，视为无法解析
        return None
    return int(start.timestamp() * 1000), int(now.timestamp() * 1000)


def parse_time_range(time_str: str) -> Tuple[int, int]:
    """
    解析时间字符串，返回 (start_timestamp, end_timestamp) 毫秒时间戳

    支持格式：
    - 自然语言: today, yesterday, week, month, hour, last7d, last30d 等
    - 日期格式: 2024-01-01, 2024-01-01 12:00
    - 日期范围: 2024-01-01~2024-01-15
    - 相对时间: -1d, -7d, -1h

    如果无法解析，返回最近24小时的时间范围
    """
    time_str = time_str.strip()

    # 尝试解析自然语言
    result = parse_natural_time(time_str)
    if result:
        return result

    # 尝试解析日期范围
    result = parse_date_range(time_str)
    if result:
        return result

    # 尝试解析相对时间
    result = parse_relative_time(time_str)
    if result:
        return result

    # 尝试解析单个日期（返回当天完整时间范围）
    date = parse_date(time_str)
    if date:
        return get_day_start_end(date)

    import logging
    logging.getLogger(__name__).warning(
        f"[FoxToolbox] 无法解析时间字符串: '{time_str}'，回退到最近24小时"
    )
    now = datetime.now()
    return (
        int((now - timedelta(hours=24)).timestamp() * 1000),
        int(now.timestamp() * 1000)
    )


def format_time_range(start_ts: int, end_ts: int) -> str:
    """格式化时间范围为可读字符串"""
    start_dt = datetime.fromtimestamp(start_ts / 1000)
    end_dt = datetime.fromtimestamp(end_ts / 1000)

    start_str = start_dt.strftime("%Y-%m-%d %H:%M")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M")

    return f"{start_str} ~ {end_str}"


def normalize_timestamp(ts: Any) -> int:
    """标准化时间戳为毫秒级

    不同平台可能返回不同单位的时间戳：
    - 秒级时间戳（约 10 位）：1744290671 ≈ 2025年
    - 毫秒级时间戳（约 13 位）：1744290671000 ≈ 2025年

    判断逻辑：如果时间戳小于 100000000000 (2286年的秒级时间戳)，
    则认为是秒级，需要乘以 1000 转换为毫秒级。
    """
    if ts is None:
        return int(time.time() * 1000)

    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return int(time.time() * 1000)

    if ts_int < 100000000000:
        return ts_int * 1000

    return ts_int