"""网络诊断工具：HTTP 请求、URL 检测、下载/上传测速、Ping 延迟统计。

纯异步实现，遵循 AstrBot 插件开发规范（使用 aiohttp，不使用 requests）。
所有对外请求均带超时、响应大小上限与 SSRF 约束。
"""

import asyncio
import json
import re
import shlex
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_TIMEOUT = 15  # 秒
MAX_RETRIES = 2
SPEED_CHUNK = 64 * 1024
PING_COUNT_DEFAULT = 5
PING_COUNT_MAX = 20
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class ValidationError(ValueError):
    """URL 或参数校验失败。"""


def validate_url(url: str) -> str:
    """校验并规范化 URL，限制为 http/https 且必须包含主机名。"""
    if not url or len(url) > 2048:
        raise ValidationError("URL 为空或过长")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("仅支持 http/https 协议")
    if not parsed.hostname:
        raise ValidationError("URL 缺少主机名")
    return url


def parse_curl_like(command: str) -> Dict[str, Any]:
    """解析类 curl 命令字符串，提取方法、头、数据、Cookie。"""
    result = {"method": None, "url": None, "headers": {}, "cookies": {}, "data": None}
    cur = shlex.split(command)
    if not cur:
        raise ValidationError("命令为空")
    if cur[0].lower() == "curl":
        cur = cur[1:]
    # 提取 URL（第一个非选项参数）
    url = None
    i = 0
    while i < len(cur):
        token = cur[i]
        if token in ("-X", "--request"):
            i += 1
            if i < len(cur):
                result["method"] = cur[i].upper()
        elif token in ("-H", "--header"):
            i += 1
            if i < len(cur):
                if ":" in cur[i]:
                    k, v = cur[i].split(":", 1)
                    result["headers"][k.strip()] = v.strip()
        elif token in ("-d", "--data", "--data-raw") or token.startswith(
            ("-d=", "--data=", "--data-raw=")
        ):
            data_arg = cur[i]
            if "=" in data_arg:
                result["data"] = data_arg.split("=", 1)[1]
            else:
                i += 1
                if i < len(cur):
                    result["data"] = cur[i]
        elif token in ("-b", "--cookie"):
            i += 1
            if i < len(cur):
                for piece in cur[i].split(";"):
                    if "=" in piece:
                        k, v = piece.split("=", 1)
                        result["cookies"][k.strip()] = v.strip()
        elif token.startswith("-"):
            # 跳过其它未知选项及其可能的值不易判断，保守忽略单字母选项
            pass
        elif url is None and not token.startswith("-"):
            url = token
        i += 1
    if url:
        result["url"] = validate_url(url)
    return result


async def send_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Any = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """发送一次性 HTTP 请求，返回状态码/耗时/内容等结构化结果。"""
    url = validate_url(url)
    method = method.upper()
    if method not in ALLOWED_METHODS:
        raise ValidationError(f"不支持的请求方法: {method}")
    connector = aiohttp.TCPConnector(limit=8, force_close=True)
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    started = time.perf_counter()
    last_err: Optional[Exception] = None
    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout_obj, cookies=cookies
    ) as session:
        for attempt in range(MAX_RETRIES + 1):
            try:
                kwargs: Dict[str, Any] = {"headers": headers}
                if isinstance(data, (dict, list)):
                    kwargs["json"] = data
                elif data is not None:
                    kwargs["data"] = data
                async with session.request(method, url, **kwargs) as resp:
                    duration = time.perf_counter() - started
                    cl = resp.headers.get("Content-Length")
                    if cl and int(cl) > MAX_RESPONSE_SIZE:
                        return {
                            "success": False,
                            "status_code": resp.status,
                            "message": (
                                f"响应过大: {int(cl) / 1024 / 1024:.2f}MB "
                                f"(上限 {MAX_RESPONSE_SIZE / 1024 / 1024}MB)"
                            ),
                        }
                    buffer = bytearray()
                    async for chunk in resp.content.iter_chunked(8 * 1024):
                        buffer.extend(chunk)
                        if len(buffer) > MAX_RESPONSE_SIZE:
                            return {
                                "success": False,
                                "status_code": resp.status,
                                "message": f"响应超过 {MAX_RESPONSE_SIZE / 1024 / 1024}MB 上限",
                            }
                    final_url = str(resp.url)
                    headers_out = {k: v for k, v in resp.headers.items()}
                    body = bytes(buffer)
                    return {
                        "success": True,
                        "status_code": resp.status,
                        "duration": duration,
                        "final_url": final_url,
                        "headers": headers_out,
                        "content_length": len(body),
                        "body": body,
                        "history": [str(h.url) for h in resp.history],
                    }
            except (aiohttp.ClientConnectorError, aiohttp.ServerTimeoutError,
                    asyncio.TimeoutError, aiohttp.ClientPayloadError) as e:
                last_err = e
            except aiohttp.ClientResponseError as http_err:
                return {
                    "success": False,
                    "status_code": http_err.status,
                    "message": f"HTTP 错误: {http_err}",
                }
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))
    raise last_err or RuntimeError("请求失败")


def decode_body(body: bytes) -> Tuple[Any, str]:
    """尽力解码响应体为 JSON 或文本。"""
    try:
        return json.loads(body.decode("utf-8")), "json"
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            return body.decode("utf-8", "replace"), "text"
        except Exception:
            return f"[二进制数据 {len(body)} 字节]", "binary"


async def url_check(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """URL 可用性检测：状态码、总耗时、重定向链、响应头。"""
    result = await send_http_request(url, method="GET", timeout=timeout)
    return result


async def download_speed_test(
    url: str, seconds: float = 4.0, timeout: float = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """对指定 URL 进行下载速率测试（拉取若干秒统计字节数）。"""
    url = validate_url(url)
    connector = aiohttp.TCPConnector(limit=4)
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    started = time.perf_counter()
    total_bytes = 0
    status_code: Optional[int] = None
    async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
        async with session.get(url) as resp:
            status_code = resp.status
            deadline = started + seconds
            async for chunk in resp.content.iter_chunked(SPEED_CHUNK):
                if time.perf_counter() >= deadline:
                    break
                total_bytes += len(chunk)
                if total_bytes > 200 * 1024 * 1024:
                    break
    elapsed = time.perf_counter() - started
    speed_bps = total_bytes * 8 / elapsed if elapsed > 0 else 0
    return {
        "status_code": status_code,
        "total_bytes": total_bytes,
        "elapsed": elapsed,
        "speed_bps": speed_bps,
    }


async def run_ping(host: str, count: int = PING_COUNT_DEFAULT) -> Dict[str, Any]:
    """对主机执行 ping，返回延迟与丢包统计。count 受上限约束。"""
    count = max(1, min(int(count), PING_COUNT_MAX))
    # 仅允许主机名 / IPv4 / IPv6，不做 DNS 之外的变换
    if not re.match(r"^[\w.\-:\[\]]+$", host) or " " in host or "&" in host or "|" in host:
        raise ValidationError("无效的主机名")
    cmd = ["ping", "-c", str(count)]
    cmd.append(host)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"success": False, "message": "ping 超时"}
    out = (stdout or b"").decode("utf-8", "replace")
    err = (stderr or b"").decode("utf-8", "replace")
    rtts = [float(m) for m in re.findall(r"time[=<]([\d.]+)\s*ms", out)]
    packet_match = re.search(r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:received|packets received)", out)
    transmitted = int(packet_match.group(1)) if packet_match else None
    received = int(packet_match.group(2)) if packet_match else None
    loss = None
    if transmitted is not None and transmitted > 0:
        loss = round((transmitted - received) / transmitted * 100, 1)
    avg = round(sum(rtts) / len(rtts), 1) if rtts else None
    mmin = round(min(rtts), 1) if rtts else None
    mmax = round(max(rtts), 1) if rtts else None
    return {
        "success": True,
        "host": host,
        "transmitted": transmitted,
        "received": received,
        "loss": loss,
        "rtt": rtts,
        "rtt_avg": avg,
        "rtt_min": mmin,
        "rtt_max": mmax,
        "detail": out,
        "error": err,
    }