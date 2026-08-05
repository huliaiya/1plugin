"""sys_util 单元测试 - 不依赖 MySQL"""

from astrbot_plugin_fox_toolbox.fox_toolbox import sys_util


class TestSysUtil:
    def test_memory_mb_is_number(self):
        mem = sys_util.get_memory_mb()
        assert isinstance(mem, float)
        assert mem >= 0

    def test_cpu_percent_in_range(self):
        pct = sys_util.get_cpu_percent()
        assert isinstance(pct, float)
        assert 0.0 <= pct <= 100.0

    def test_uptime_is_number(self):
        uptime = sys_util.get_process_uptime()
        assert isinstance(uptime, float)
        assert uptime >= 0

    def test_cpu_second_call_also_in_range(self):
        sys_util.get_cpu_percent()
        pct = sys_util.get_cpu_percent()
        assert isinstance(pct, float)
        assert 0.0 <= pct <= 100.0
