"""插件运行时资源与状态采集工具（仅依赖标准库）

在 Linux 上优先读取 /proc 获取进程 CPU 时间、常驻内存与运行时长；
macOS/BSD 通过 resource 模块回退读取峰值内存；
无法获取时返回 0，保证 WebUI 状态卡片不会因环境差异报错。
"""

import os
import sys
import time
import ctypes

_PROC_STAT = "/proc/self/stat"
_PROC_UPTIME = "/proc/uptime"
_PROC_STATUS = "/proc/self/status"

_PROCESS_START_MONO = time.monotonic()
_last_cpu_sample = {"ts": None, "cpu_ticks": 0.0, "process_seconds": None}


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _clock_ticks() -> float:
    try:
        ticks = os.sysconf("SC_CLK_TCK")
        return float(ticks or 100)
    except (AttributeError, OSError, ValueError):
        return 100.0


def _read_proc_stat():
    """从 /proc/self/stat 解析 (utime, stime) 时钟滴答数，失败返回 None"""
    try:
        with open(_PROC_STAT, "r") as f:
            line = f.read()
        idx = line.rfind(")")
        if idx < 0:
            return None
        fields = line[idx + 2:].split()
        if len(fields) < 20:
            return None
        return float(fields[11]), float(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def get_process_uptime() -> float:
    """进程已运行秒数（无 /proc 时返回 0）"""
    try:
        with open(_PROC_STAT, "r") as f:
            line = f.read()
        idx = line.rfind(")")
        if idx < 0:
            return 0.0
        fields = line[idx + 2:].split()
        if len(fields) < 20:
            return 0.0
        start_ticks = float(fields[19])
        with open(_PROC_UPTIME, "r") as f:
            uptime = float(f.read().split()[0])
        return max(0.0, uptime - start_ticks / _clock_ticks())
    except (OSError, ValueError, IndexError):
        return max(0.0, time.monotonic() - _PROCESS_START_MONO)


def _get_process_cpu_seconds_fallback() -> float:
    try:
        return float(time.process_time())
    except Exception:
        return 0.0


def get_cpu_percent() -> float:
    """进程 CPU 使用率（0~100%）

    首次调用返回自进程启动以来的平均占用；
    之后返回自上次调用以来的瞬时占用。无 /proc 环境返回 0。
    """
    global _last_cpu_sample
    sample = _read_proc_stat()
    now = time.monotonic()
    prev_ts = _last_cpu_sample["ts"]
    prev_cpu = _last_cpu_sample["cpu_ticks"]
    prev_process_seconds = _last_cpu_sample["process_seconds"]

    if sample is None:
        process_seconds = _get_process_cpu_seconds_fallback()
        _last_cpu_sample = {"ts": now, "cpu_ticks": 0.0, "process_seconds": process_seconds}
        if prev_ts is None or prev_process_seconds is None:
            uptime = get_process_uptime()
            if uptime <= 0:
                return 0.0
            pct = process_seconds / uptime * 100.0
        else:
            dt = now - prev_ts
            if dt <= 0:
                return 0.0
            pct = (process_seconds - prev_process_seconds) / dt * 100.0
    else:
        cpu_ticks = sample[0] + sample[1]
        ticks = _clock_ticks()
        _last_cpu_sample = {"ts": now, "cpu_ticks": cpu_ticks, "process_seconds": None}
        if prev_ts is None:
            uptime = get_process_uptime()
            if uptime <= 0:
                return 0.0
            pct = cpu_ticks / ticks / uptime * 100.0
        else:
            dt = now - prev_ts
            if dt <= 0:
                return 0.0
            pct = (cpu_ticks - prev_cpu) / ticks / dt * 100.0
    return min(100.0, max(0.0, pct))


def _get_windows_memory_mb() -> float:
    try:
        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
        process = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        if ok:
            return float(counters.WorkingSetSize) / 1024.0 / 1024.0
    except Exception:
        pass
    return 0.0


def get_memory_mb() -> float:
    """进程常驻内存（MB），无法获取时返回 0"""
    try:
        with open(_PROC_STATUS, "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return float(parts[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return rss / 1024.0 / 1024.0
        return rss / 1024.0
    except (ImportError, OSError, ValueError):
        pass
    if sys.platform.startswith("win"):
        return _get_windows_memory_mb()
    return 0.0
