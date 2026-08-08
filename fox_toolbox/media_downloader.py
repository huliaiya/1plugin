"""多媒体文件下载与保存模块"""

import asyncio
import hashlib
import io
import ipaddress
import socket
from pathlib import Path
from typing import Optional, List, Any, Tuple
from urllib.parse import urlparse

import aiohttp
from PIL import Image

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path


MEDIA_TYPE_MAP = {
    "Image": "images",
    "Record": "records",
    "Video": "videos",
    "File": "files",
}

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/amr": ".amr",
    "audio/flac": ".flac",
    "audio/silk": ".silk",
    "application/octet-stream": ".bin",
}

KNOWN_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "tiff",
    "heic", "heif", "avif", "jfif",
    "mp4", "avi", "mkv", "mov", "webm", "wmv", "flv", "m4v", "3gp",
    "mpeg", "mpg", "ts", "m2ts", "ogv", "rm", "rmvb",
    "mp3", "wav", "ogg", "amr", "flac", "silk", "aac", "m4a", "wma",
    "ape", "alac", "opus", "aiff", "au",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "md", "csv", "log", "rtf", "odt", "ods", "odp",
    "epub", "mobi", "azw", "azw3",
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz",
    "iso", "jar", "cab", "deb", "rpm", "pkg", "msi",
    "py", "js", "ts", "java", "c", "cpp", "h", "go", "rs", "rb",
    "php", "sh", "html", "css", "json", "xml", "yml", "yaml", "sql",
    "bat", "apk", "exe", "dmg", "ipa", "kt", "swift", "scala", "dart",
    "lua", "r", "jl", "clj", "ps1", "ini", "toml", "conf",
}

THUMBNAIL_MAX_SIZE = 320
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 1.0
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024  # 100MB
SSRF_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}


def _is_safe_url(url: str) -> bool:
    """检查 URL 是否安全，防止 SSRF 攻击。

    拒绝以下情况：
    - 非 http/https 协议
    - 指向本地/内网地址的主机名
    - 无法解析的主机名
    """
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # 拒绝明显的本地地址
    if hostname.lower() in SSRF_BLOCKED_HOSTS:
        return False

    # 尝试解析主机名，检查是否为内网地址
    try:
        # 如果 hostname 本身就是 IP 地址
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
            return True
        except ValueError:
            pass

        # 解析域名
        addrinfos = socket.getaddrinfo(hostname, None)
        for addrinfo in addrinfos:
            ip_str = addrinfo[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
            except ValueError:
                continue
    except socket.gaierror:
        # 无法解析的主机名，拒绝
        return False

    return True


class MediaDownloader:
    """多媒体文件下载器"""

    def __init__(
        self,
        plugin_name: str,
        image_save_mode: str = "original",
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ):
        self.plugin_name = plugin_name
        self.image_save_mode = image_save_mode
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.media_base_path = (
            Path(get_astrbot_plugin_data_path())
            / plugin_name
            / "media"
        )
        self.media_base_path.mkdir(parents=True, exist_ok=True)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def get_media_base_path(self) -> Path:
        return self.media_base_path

    async def download_media(
        self,
        url: str,
        component_type: str,
        filename: Optional[str] = None,
        bot_api: Optional[Any] = None,
    ) -> Optional[str]:
        """下载媒体文件。

        Args:
            url: 媒体引用。可为 http(s) URL、``file:///`` URI、``base64://``
                负载、``data:`` URI、裸本地路径或 OneBot 文件名/hash。
            component_type: 组件类型（Image/Record/Video/File）。
            filename: 指定文件名（仅 File 组件常用）。
            bot_api: 可选的 OneBot api 对象（需有 ``call_action`` 方法）。
                常规下载失败时调用 ``get_image`` / ``download_file`` 兜底。
        """
        if not url:
            return None

        media_subdir = MEDIA_TYPE_MAP.get(component_type, "files")

        for attempt in range(self.max_retries + 1):
            try:
                result = await self._do_download(
                    url, component_type, media_subdir, filename, bot_api
                )
                if result is not None:
                    return result

                # 所有下载方式均失败
                if attempt < self.max_retries:
                    logger.debug(
                        f"[MediaDownloader] 下载失败 (尝试 {attempt + 1}/{self.max_retries + 1}): "
                        f"{url[:100]}"
                    )
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.warning(
                        f"[MediaDownloader] 下载失败，已重试 {self.max_retries} 次: "
                        f"URL: {url[:100]}"
                    )
                    return None
            except Exception as e:
                logger.warning(f"[MediaDownloader] 下载出错: {e}")
                return None
        return None

    async def _do_download(
        self,
        url: str,
        component_type: str,
        media_subdir: str,
        filename: Optional[str],
        bot_api: Optional[Any],
    ) -> Optional[str]:
        content, content_type = await self._fetch_bytes(
            url, component_type, bot_api
        )
        if not content:
            return None

        ext = self._determine_extension(url, content_type, component_type, content)

        if component_type == "Image" and self.image_save_mode == "thumbnail":
            content = self._create_thumbnail(content)

        content_hash = hashlib.sha256(content).hexdigest()[:16]

        if not filename:
            filename = f"{content_hash}{ext}"

        hash_dir = self._get_hash_dir(media_subdir, content_hash)
        file_path = hash_dir / filename

        # 防护：filename 可能来自平台消息中的 File 组件名（含 ../ 或绝对路径）
        # 必须在写入前校验最终路径仍在媒体目录内，避免路径穿越写入
        try:
            file_path.resolve().relative_to(self.media_base_path.resolve())
        except ValueError:
            logger.warning(
                f"[MediaDownloader] 拒绝越界文件名（路径穿越防护）: {filename}"
            )
            return None

        if file_path.exists():
            rel_path = file_path.relative_to(self.media_base_path)
            logger.debug(
                f"[MediaDownloader] 文件已存在，跳过保存: {rel_path}"
            )
            return str(rel_path)

        hash_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(file_path.write_bytes, content)

        rel_path = file_path.relative_to(self.media_base_path)
        logger.debug(
            f"[MediaDownloader] 文件已保存: {rel_path} "
            f"({len(content)} bytes)"
        )
        return str(rel_path)

    async def _fetch_bytes(
        self,
        url: str,
        component_type: str,
        bot_api: Optional[Any],
    ) -> Tuple[Optional[bytes], str]:
        """获取媒体字节数据，返回 (bytes, content_type)。

        下载优先级：
        1. AstrBot 官方 ``MediaResolver``（支持 http/file:///base64/data:/裸路径）
        2. aiohttp（仅 http(s)，可拿到 content_type）
        3. OneBot 兜底（get_image / download_file，需 bot_api）
        """
        # 1. MediaResolver：统一处理各种引用格式
        content = await self._fetch_via_media_resolver(url, component_type)
        if content:
            return content, ""

        # 2. aiohttp：仅对 http(s) 链接
        if url.startswith(("http://", "https://")):
            content, content_type = await self._fetch_via_aiohttp(url)
            if content:
                return content, content_type

        # 3. OneBot 兜底：裸文件名 / 过期 CDN / 不可达本地路径
        if bot_api is not None:
            content = await self._fetch_via_onebot(url, bot_api)
            if content:
                return content, ""

        logger.warning(
            f"[MediaDownloader] 所有下载方式均失败: {url[:100]}"
        )
        return None, ""

    async def _fetch_via_media_resolver(
        self, url: str, component_type: str
    ) -> Optional[bytes]:
        """通过 AstrBot 官方 MediaResolver 获取字节。

        统一处理 http(s)、``file:///``、``base64://``、``data:`` 以及裸本地路径。

        ponytail: MediaResolver 在 aiohttp SSRF 检查之前执行，且支持 file:///
        与裸本地路径，任意群成员发送 file:///etc/passwd 类消息会触发读取本地
        文件并入库（信息被记录，需 WebUI 权限导出可见）。保留是为兼容 OneBot
        客户端缓存文件的正常下载；若对隐私敏感，应在调用前对 file:// 路径
        增加目录白名单校验。
        """
        media_type_map = {
            "Image": "image",
            "Record": "audio",
            "Video": "video",
            "File": "file",
        }
        media_type = media_type_map.get(component_type, "file")
        try:
            from astrbot.core.utils.media_utils import MediaResolver

            data = await MediaResolver(url, media_type=media_type).to_bytes()
            if data:
                logger.debug(
                    f"[MediaDownloader] MediaResolver 成功: {url[:80]} "
                    f"({len(data)} bytes)"
                )
                return data
        except Exception as e:
            logger.debug(
                f"[MediaDownloader] MediaResolver 失败: {url[:80]}, "
                f"错误: {type(e).__name__}: {e}"
            )
        return None

    async def _fetch_via_aiohttp(
        self, url: str
    ) -> Tuple[Optional[bytes], str]:
        """通过 aiohttp 下载 http(s) URL。返回 (bytes, content_type)。

        包含 SSRF 防护和响应大小限制。
        """
        if not _is_safe_url(url):
            logger.warning(
                f"[MediaDownloader] 拒绝不安全的URL (SSRF防护): {url[:80]}"
            )
            return None, ""

        session = await self._get_session()
        try:
            current_url = url
            # 逐跳校验重定向，防止重定向到内网/元数据地址绕过 SSRF 防护
            for _redirect in range(5):
                async with session.get(
                    current_url, allow_redirects=False
                ) as resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        location = resp.headers.get("Location")
                        if not location:
                            return None, ""
                        next_url = str(
                            resp.url.join(location) if hasattr(resp.url, "join") else location
                        )
                        if not _is_safe_url(next_url):
                            logger.warning(
                                f"[MediaDownloader] 重定向目标不安全，拒绝 (SSRF防护): "
                                f"{next_url[:80]}"
                            )
                            return None, ""
                        current_url = next_url
                        continue

                    if resp.status != 200:
                        logger.debug(
                            f"[MediaDownloader] aiohttp 下载失败: HTTP {resp.status}, "
                            f"URL: {current_url[:80]}"
                        )
                        return None, ""

                    content_length = resp.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
                        logger.warning(
                            f"[MediaDownloader] 文件过大，拒绝下载: "
                            f"{int(content_length)} bytes, URL: {current_url[:80]}"
                        )
                        return None, ""

                    content = await resp.content.read(MAX_DOWNLOAD_SIZE + 1)
                    if len(content) > MAX_DOWNLOAD_SIZE:
                        logger.warning(
                            f"[MediaDownloader] 下载内容超过大小限制 "
                            f"({MAX_DOWNLOAD_SIZE} bytes), URL: {current_url[:80]}"
                        )
                        return None, ""

                    content_type = resp.headers.get("Content-Type", "")
                    if content:
                        logger.debug(
                            f"[MediaDownloader] aiohttp 成功: {current_url[:80]} "
                            f"({len(content)} bytes)"
                        )
                    return content, content_type
            logger.warning(
                f"[MediaDownloader] 重定向次数过多，拒绝下载: {url[:80]}"
            )
            return None, ""
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(
                f"[MediaDownloader] aiohttp 异常: {url[:80]}, "
                f"错误: {type(e).__name__}: {e}"
            )
            return None, ""

    async def _fetch_via_onebot(
        self, url: str, bot_api: Any
    ) -> Optional[bytes]:
        """通过 OneBot API（get_image / download_file）兜底下载。

        覆盖场景：
        - url 为 http(s) 且常规下载失败（CDN 过期）：调 ``download_file`` 重下
        - url 为裸文件名 / 不可达本地路径：取文件名调 ``get_image`` 换取可访问地址
        """
        from pathlib import Path as PathLib

        try:
            # 场景1：http(s) 链接 → download_file
            if url.startswith(("http://", "https://")):
                result = await bot_api.call_action(
                    "download_file", url=url, thread_cnt=1
                )
                if isinstance(result, dict):
                    path = result.get("file") or result.get("body")
                    if path:
                        logger.debug(
                            f"[MediaDownloader] OneBot download_file 成功: "
                            f"{url[:50]}... -> {path}"
                        )
                        return await asyncio.to_thread(PathLib(path).read_bytes)
                return None

            # 场景2：裸文件名 / 本地路径 → get_image
            file_name = PathLib(url).name
            if not file_name:
                return None
            result = await bot_api.call_action("get_image", file=file_name)
            if not isinstance(result, dict):
                return None
            returned_url = result.get("url") or result.get("file")
            if not returned_url:
                return None

            # 返回 http → download_file 下载
            if returned_url.startswith(("http://", "https://")):
                dl_result = await bot_api.call_action(
                    "download_file", url=returned_url, thread_cnt=1
                )
                if isinstance(dl_result, dict):
                    path = dl_result.get("file") or dl_result.get("body")
                    if path:
                        logger.debug(
                            f"[MediaDownloader] OneBot get_image+download_file 成功: "
                            f"{file_name} -> {path}"
                        )
                        return await asyncio.to_thread(PathLib(path).read_bytes)
                return None

            # 返回本地可达路径 → 直接读
            if PathLib(returned_url).is_file():
                logger.debug(
                    f"[MediaDownloader] OneBot get_image 本地路径成功: "
                    f"{file_name} -> {returned_url}"
                )
                return await asyncio.to_thread(PathLib(returned_url).read_bytes)
            return None
        except Exception as e:
            logger.debug(
                f"[MediaDownloader] OneBot 兜底失败: {url[:80]}, "
                f"错误: {type(e).__name__}: {e}"
            )
            return None

    def _create_thumbnail(self, image_data: bytes) -> bytes:
        try:
            img = Image.open(io.BytesIO(image_data))
            img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.LANCZOS)
            output = io.BytesIO()
            img_format = img.format or "JPEG"
            if img_format == "PNG" and img.mode in ("RGBA", "LA", "P"):
                img.save(output, format="PNG", optimize=True)
            else:
                img = img.convert("RGB")
                img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
        except Exception as e:
            logger.warning(
                f"[MediaDownloader] 缩略图生成失败，使用原图: {e}"
            )
            return image_data

    def _get_hash_dir(self, media_subdir: str, content_hash: str) -> Path:
        prefix = content_hash[:2]
        return self.media_base_path / media_subdir / prefix

    def _determine_extension(
        self,
        url: str,
        content_type: str,
        component_type: str,
        content: Optional[bytes] = None,
    ) -> str:
        url_path = url.split("?")[0]
        if "." in url_path:
            ext = url_path.rsplit(".", 1)[-1].lower()
            if ext in KNOWN_EXTENSIONS:
                return f".{ext}"

        for ct, ext in CONTENT_TYPE_EXT.items():
            if ct in content_type:
                return ext

        # 图片：通过文件头检测真实格式（base64/data: 等无扩展名场景）
        if component_type == "Image" and content:
            detected = self._detect_image_format(content)
            if detected:
                return f".{detected}"

        defaults = {
            "Image": ".jpg",
            "Record": ".wav",
            "Video": ".mp4",
            "File": ".bin",
        }
        return defaults.get(component_type, ".bin")

    @staticmethod
    def _detect_image_format(content: bytes) -> Optional[str]:
        """通过文件头检测图片格式，返回不带点的扩展名。"""
        try:
            img = Image.open(io.BytesIO(content))
            fmt = (img.format or "").upper()
            fmt_map = {
                "JPEG": "jpg",
                "PNG": "png",
                "GIF": "gif",
                "WEBP": "webp",
                "BMP": "bmp",
            }
            return fmt_map.get(fmt)
        except Exception:
            return None

    def delete_media_file(self, relative_path: str) -> bool:
        if not relative_path:
            return False
        try:
            file_path = self.media_base_path / relative_path
            try:
                file_path.resolve().relative_to(self.media_base_path.resolve())
            except ValueError:
                logger.warning(f"[MediaDownloader] 拒绝删除 media 目录外的文件: {relative_path}")
                return False
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                self._cleanup_empty_parents(file_path.parent)
                logger.debug(f"[MediaDownloader] 已删除媒体文件: {relative_path}")
                return True
            return False
        except Exception as e:
            logger.warning(f"[MediaDownloader] 删除媒体文件失败: {e}")
            return False

    def _cleanup_empty_parents(self, dir_path: Path) -> None:
        """向上清理因文件删除而产生的空目录，停在 media_base_path"""
        try:
            while dir_path != self.media_base_path and dir_path.is_dir():
                if any(dir_path.iterdir()):
                    break
                dir_path.rmdir()
                dir_path = dir_path.parent
        except OSError:
            pass

    def delete_media_files(self, relative_paths: List[str]) -> int:
        deleted = 0
        for path in relative_paths:
            if self.delete_media_file(path):
                deleted += 1
        return deleted

    @staticmethod
    def extract_media_paths(message_chain_json: Optional[str]) -> List[str]:
        from .serializer import extract_media_paths as _extract
        return _extract(message_chain_json)
