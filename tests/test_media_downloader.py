"""media_downloader.py 单元测试"""

import asyncio
import io
import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from PIL import Image

from astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader import (
    MediaDownloader,
    MEDIA_TYPE_MAP,
)


def _make_png_bytes() -> bytes:
    """生成一个最小 PNG 的字节数据，用于测试。"""
    img = Image.new("RGB", (2, 2), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestMediaTypeMap:
    def test_all_types(self):
        assert "Image" in MEDIA_TYPE_MAP
        assert "Record" in MEDIA_TYPE_MAP
        assert "Video" in MEDIA_TYPE_MAP
        assert "File" in MEDIA_TYPE_MAP

    def test_values_are_directories(self):
        for v in MEDIA_TYPE_MAP.values():
            assert isinstance(v, str)
            assert len(v) > 0


class TestMediaDownloaderInit:
    def test_init(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            assert md.media_base_path == tmp_path / "test_plugin" / "media"
            assert md.max_retries == 2
            assert md.retry_delay == 1.0


class TestExtractMediaPaths:
    def test_delegates_to_serializer(self):
        chain = json.dumps([{"type": "Image", "local_path": "images/test.jpg"}])
        result = MediaDownloader.extract_media_paths(chain)
        assert "images/test.jpg" in result

    def test_none_input(self):
        assert MediaDownloader.extract_media_paths(None) == []

    def test_empty_string(self):
        assert MediaDownloader.extract_media_paths("") == []


class TestDeleteMediaFile:
    def test_delete_existing(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            test_file = tmp_path / "test_plugin" / "media" / "images" / "test.jpg"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("fake image")

            assert md.delete_media_file("images/test.jpg") is True
            assert not test_file.exists()

    def test_delete_nonexistent(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            assert md.delete_media_file("images/nonexistent.jpg") is False

    def test_delete_empty_path(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            assert md.delete_media_file("") is False


class TestDeleteMediaFiles:
    def test_delete_multiple(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            media_dir = tmp_path / "test_plugin" / "media" / "images"
            media_dir.mkdir(parents=True, exist_ok=True)

            f1 = media_dir / "a.jpg"
            f2 = media_dir / "b.jpg"
            f1.write_text("a")
            f2.write_text("b")

            deleted = md.delete_media_files(["images/a.jpg", "images/b.jpg", "images/c.jpg"])
            assert deleted == 2


class TestDetectImageFormat:
    def test_png(self):
        assert MediaDownloader._detect_image_format(_make_png_bytes()) == "png"

    def test_invalid_bytes(self):
        assert MediaDownloader._detect_image_format(b"not an image") is None

    def test_empty(self):
        assert MediaDownloader._detect_image_format(b"") is None


class TestDetermineExtension:
    def _make_md(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            return MediaDownloader("test_plugin")

    def test_url_extension_wins(self, tmp_path):
        md = self._make_md(tmp_path)
        ext = md._determine_extension("http://x.com/a.jpg", "", "Image", _make_png_bytes())
        assert ext == ".jpg"

    def test_image_bytes_detection(self, tmp_path):
        md = self._make_md(tmp_path)
        # data: URI 无可识别扩展名，靠 bytes 检测为 png
        ext = md._determine_extension("data:image/png;base64,xxx", "", "Image", _make_png_bytes())
        assert ext == ".png"

    def test_content_type_fallback(self, tmp_path):
        md = self._make_md(tmp_path)
        ext = md._determine_extension("http://x.com/img", "image/gif", "Image", None)
        assert ext == ".gif"

    def test_default_for_non_image(self, tmp_path):
        md = self._make_md(tmp_path)
        ext = md._determine_extension("http://x.com/noext", "", "File", None)
        assert ext == ".bin"


class TestDownloadMediaNonHttp:
    """验证非 http 引用不再被直接拒绝，而是交给下载器尝试。"""

    def _make_md(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            return MediaDownloader("test_plugin", max_retries=0)

    async def test_non_http_tries_resolver_then_fails(self, tmp_path):
        md = self._make_md(tmp_path)
        # MediaResolver / aiohttp / OneBot 均失败 → 返回 None（不再因非 http 直接返回 None）
        with patch.object(
            md, "_fetch_via_media_resolver", new_callable=AsyncMock, return_value=None
        ):
            result = await md.download_media("file:///nonexist/x.png", "Image")
        assert result is None

    async def test_non_http_succeeds_via_resolver(self, tmp_path):
        md = self._make_md(tmp_path)
        png_bytes = _make_png_bytes()
        with patch.object(
            md, "_fetch_via_media_resolver", new_callable=AsyncMock, return_value=png_bytes
        ):
            result = await md.download_media("file:///some/path.png", "Image")
        assert result is not None
        assert result.endswith(".png")

    async def test_empty_url_returns_none(self, tmp_path):
        md = self._make_md(tmp_path)
        assert await md.download_media("", "Image") is None

    async def test_bare_filename_with_onebot_fallback(self, tmp_path):
        md = self._make_md(tmp_path)
        png_bytes = _make_png_bytes()
        bot_api = MagicMock()
        bot_api.call_action = AsyncMock(
            return_value={"url": "/local/cache/abc.png", "file": "/local/cache/abc.png"}
        )
        # MediaResolver 失败 → OneBot 兜底返回本地路径（模拟不可达）→ 这里用 get_image 返回不可达路径
        # 实际上 _fetch_via_onebot 会检查 is_file()，不可达则返回 None
        # 为测通完整链路，让 get_image 返回一个真实存在的临时文件
        real_file = tmp_path / "real.png"
        real_file.write_bytes(png_bytes)
        bot_api.call_action = AsyncMock(
            return_value={"url": str(real_file)}
        )
        with patch.object(
            md, "_fetch_via_media_resolver", new_callable=AsyncMock, return_value=None
        ):
            # 将数据目录 mock 到 tmp_path，使 OneBot 返回的本地文件通过白名单校验
            with patch(
                "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_data_path",
                return_value=str(tmp_path),
            ):
                result = await md.download_media("abc123.image", "Image", bot_api=bot_api)
        assert result is not None
        assert result.endswith(".png")


class TestPathTraversalProtection:
    """验证恶意文件名（../ 或绝对路径）不会越界写入。"""

    def _make_md(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            return MediaDownloader("test_plugin", max_retries=0)

    async def test_traversal_filename_rejected(self, tmp_path):
        md = self._make_md(tmp_path)
        png_bytes = _make_png_bytes()
        with patch.object(
            md, "_fetch_via_media_resolver", new_callable=AsyncMock, return_value=png_bytes
        ):
            result = await md.download_media(
                "file:///some/path.png", "File", filename="../../../evil.png"
            )
        assert result is None
        # 确认没有文件被写到媒体目录之外
        assert not (tmp_path / "evil.png").exists()
        assert not (tmp_path.parent / "evil.png").exists()

    async def test_absolute_filename_rejected(self, tmp_path):
        md = self._make_md(tmp_path)
        png_bytes = _make_png_bytes()
        with patch.object(
            md, "_fetch_via_media_resolver", new_callable=AsyncMock, return_value=png_bytes
        ):
            result = await md.download_media(
                "file:///some/path.png", "File", filename="/etc/passwd"
            )
        assert result is None


class TestSsrRedirectProtection:
    """验证重定向到不安全地址会被拒绝。"""

    def _make_md(self, tmp_path):
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            return MediaDownloader("test_plugin", max_retries=0)

    def test_redirect_to_internal_rejected(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader import _is_safe_url

        # 对外可信域名
        assert _is_safe_url("http://example.com/img.png") is True
        # 重定向目标为内网/元数据地址 → 不安全
        assert _is_safe_url("http://169.254.169.254/latest/meta-data/") is False
        assert _is_safe_url("http://127.0.0.1:3306/") is False
        assert _is_safe_url("http://localhost/") is False


class TestLocalFileReadProtection:
    """验证 file:/// 与绝对路径的本地文件读取白名单（防止任意文件读取）。"""

    def test_file_uri_inside_data_dir_allowed(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader import (
            _safe_local_read_path,
        )

        target = tmp_path / "sub" / "cache" / "abc.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_data_path",
            return_value=str(tmp_path),
        ):
            result = _safe_local_read_path(f"file://{target}")
        assert result is not None
        assert result == target.resolve()

    def test_file_uri_outside_data_dir_rejected(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader import (
            _safe_local_read_path,
        )

        # /etc/passwd 在数据目录之外 → 拒绝
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_data_path",
            return_value=str(tmp_path),
        ):
            assert _safe_local_read_path("file:///etc/passwd") is None
            assert _safe_local_read_path("/etc/passwd") is None

    def test_absolute_path_outside_data_dir_rejected(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader import (
            _safe_local_read_path,
        )

        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_data_path",
            return_value=str(tmp_path),
        ):
            assert _safe_local_read_path("/root/.ssh/id_rsa") is None
            assert _safe_local_read_path("/etc/shadow") is None

    def test_relative_filename_not_absolute_returns_none(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader import (
            _safe_local_read_path,
        )

        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_data_path",
            return_value=str(tmp_path),
        ):
            # 纯文件名（相对路径，非绝对）不通过绝对路径校验
            assert _safe_local_read_path("abc.png") is None
            assert _safe_local_read_path("images/abc.png") is None

    def test_resolver_rejects_outside_file_uri(self, tmp_path):
        """集成：download_media 拒绝数据目录之外的 file:/// 引用。"""
        md = MediaDownloader("test_plugin", max_retries=0)
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_data_path",
            return_value=str(tmp_path),
        ):
            assert asyncio.run(md.download_media("file:///etc/passwd", "Image")) is None


class TestFetchViaAiohttpContentLength:
    """aiohttp 响应 Content-Length 非数字时的容错"""

    class _FakeContent:
        def __init__(self, body: bytes):
            self._body = body

        async def read(self, size):
            return self._body

    class _FakeResp:
        def __init__(self, status, headers, body: bytes):
            self.status = status
            self.headers = headers
            self.content = TestFetchViaAiohttpContentLength._FakeContent(body)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _FakeSession:
        def __init__(self, resp):
            self._resp = resp

        def get(self, url, allow_redirects=False):
            return self._resp

    def _make_md(self, tmp_path) -> MediaDownloader:
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            return MediaDownloader("test_plugin")

    @pytest.mark.asyncio
    async def test_non_numeric_content_length_tolerated(self, tmp_path):
        md = self._make_md(tmp_path)
        resp = self._FakeResp(200, {"Content-Length": "not-a-number"}, b"hello world")
        md._get_session = AsyncMock(return_value=self._FakeSession(resp))

        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader._is_safe_url",
            return_value=True,
        ):
            content, content_type = await md._fetch_via_aiohttp(
                "http://example.com/x.png"
            )
        assert content == b"hello world"
        assert content_type == ""

    @pytest.mark.asyncio
    async def test_numeric_oversize_rejected(self, tmp_path):
        md = self._make_md(tmp_path)
        resp = self._FakeResp(200, {"Content-Length": "999999999"}, b"")
        md._get_session = AsyncMock(return_value=self._FakeSession(resp))

        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.media_downloader._is_safe_url",
            return_value=True,
        ):
            content, _ = await md._fetch_via_aiohttp("http://example.com/big.bin")
        assert content is None
