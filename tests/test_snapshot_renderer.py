"""snapshot_renderer.py 内部辅助函数单元测试"""

from decimal import Decimal

from astrbot_plugin_fox_toolbox.fox_toolbox.snapshot_renderer import _to_int


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