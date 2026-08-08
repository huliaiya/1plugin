"""time_utils.py 单元测试"""

import time
from datetime import datetime

from astrbot_plugin_fox_toolbox.fox_toolbox.time_utils import (
    get_day_start_end,
    parse_relative_time,
    parse_date,
    parse_date_range,
    parse_natural_time,
    parse_time_range,
    format_time_range,
    normalize_timestamp,
)


class TestGetDayStartEnd:
    def test_returns_millisecond_timestamps(self):
        dt = datetime(2024, 6, 15, 14, 30, 0)
        start, end = get_day_start_end(dt)
        assert start < end
        assert end - start == 86400000

    def test_start_is_midnight(self):
        dt = datetime(2024, 6, 15, 14, 30, 0)
        start, end = get_day_start_end(dt)
        start_dt = datetime.fromtimestamp(start / 1000)
        assert start_dt.hour == 0
        assert start_dt.minute == 0
        assert start_dt.second == 0

    def test_end_is_next_midnight(self):
        dt = datetime(2024, 6, 15, 14, 30, 0)
        start, end = get_day_start_end(dt)
        end_dt = datetime.fromtimestamp(end / 1000)
        assert end_dt.hour == 0
        assert end_dt.minute == 0


class TestParseRelativeTime:
    def test_negative_days(self):
        result = parse_relative_time("-1d")
        assert result is not None
        start, end = result
        assert start < end

    def test_negative_hours(self):
        result = parse_relative_time("-3h")
        assert result is not None
        start, end = result
        assert start < end

    def test_negative_minutes(self):
        result = parse_relative_time("-30m")
        assert result is not None
        start, end = result
        assert start < end

    def test_positive_days(self):
        result = parse_relative_time("1d")
        assert result is not None
        start, end = result
        assert start < end

    def test_invalid_format(self):
        assert parse_relative_time("abc") is None
        assert parse_relative_time("1w") is None
        assert parse_relative_time("") is None


class TestParseDate:
    def test_iso_date(self):
        result = parse_date("2024-06-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_iso_datetime(self):
        result = parse_date("2024-06-15 14:30")
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_slash_date(self):
        result = parse_date("2024/06/15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 6

    def test_invalid_date(self):
        assert parse_date("not a date") is None
        assert parse_date("") is None


class TestParseDateRange:
    def test_tilde_separator(self):
        result = parse_date_range("2024-06-01~2024-06-15")
        assert result is not None
        start, end = result
        assert start < end

    def test_dash_separator(self):
        result = parse_date_range("2024-06-01 - 2024-06-15")
        assert result is not None
        start, end = result
        assert start < end

    def test_invalid_range(self):
        assert parse_date_range("invalid") is None
        assert parse_date_range("2024-06-01") is None


class TestParseNaturalTime:
    def test_today(self):
        result = parse_natural_time("today")
        assert result is not None
        start, end = result
        assert start < end

    def test_yesterday(self):
        result = parse_natural_time("yesterday")
        assert result is not None
        start, end = result
        assert start < end

    def test_week(self):
        result = parse_natural_time("week")
        assert result is not None

    def test_last7d(self):
        result = parse_natural_time("last7d")
        assert result is not None

    def test_month(self):
        result = parse_natural_time("month")
        assert result is not None

    def test_last30d(self):
        result = parse_natural_time("last30d")
        assert result is not None

    def test_hour(self):
        result = parse_natural_time("hour")
        assert result is not None

    def test_last1h(self):
        result = parse_natural_time("last1h")
        assert result is not None

    def test_last3h(self):
        result = parse_natural_time("last3h")
        assert result is not None

    def test_last12h(self):
        result = parse_natural_time("last12h")
        assert result is not None

    def test_last24h(self):
        result = parse_natural_time("last24h")
        assert result is not None

    def test_last3d(self):
        result = parse_natural_time("last3d")
        assert result is not None

    def test_last14d(self):
        result = parse_natural_time("last14d")
        assert result is not None

    def test_numeric_days(self):
        result = parse_natural_time("7days")
        assert result is not None

    def test_numeric_hours(self):
        result = parse_natural_time("2hours")
        assert result is not None

    def test_case_insensitive(self):
        assert parse_natural_time("Today") is not None
        assert parse_natural_time("YESTERDAY") is not None

    def test_invalid(self):
        assert parse_natural_time("invalid") is None


class TestParseTimeRange:
    def test_natural_language(self):
        start, end = parse_time_range("today")
        assert start < end

    def test_date_range(self):
        start, end = parse_time_range("2024-06-01~2024-06-15")
        assert start < end

    def test_relative_time(self):
        start, end = parse_time_range("-1d")
        assert start < end

    def test_single_date(self):
        start, end = parse_time_range("2024-06-15")
        assert start < end

    def test_fallback_24h(self):
        start, end = parse_time_range("gibberish")
        now_ms = int(time.time() * 1000)
        assert start < now_ms
        assert end <= now_ms + 1000


class TestFormatTimeRange:
    def test_format(self):
        start = 1700000000000
        end = 1700086400000
        result = format_time_range(start, end)
        assert "~" in result


class TestNormalizeTimestamp:
    def test_seconds(self):
        ts = 1700000000
        result = normalize_timestamp(ts)
        assert result == 1700000000000

    def test_milliseconds(self):
        ts = 1700000000000
        result = normalize_timestamp(ts)
        assert result == 1700000000000

    def test_none(self):
        result = normalize_timestamp(None)
        assert result > 0
        assert result > 1000000000000

    def test_string_seconds(self):
        result = normalize_timestamp("1700000000")
        assert result == 1700000000000

    def test_string_milliseconds(self):
        result = normalize_timestamp("1700000000000")
        assert result == 1700000000000

    def test_invalid_string(self):
        result = normalize_timestamp("not a number")
        assert result > 0

    def test_small_value(self):
        result = normalize_timestamp(0)
        assert result == 0

    def test_boundary(self):
        result = normalize_timestamp(99999999999)
        assert result == 99999999999000
        result2 = normalize_timestamp(100000000000)
        assert result2 == 100000000000
