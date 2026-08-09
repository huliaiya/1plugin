"""web_api.py 测试 - 导入包解压防护（zip 炸弹限制、路径穿越拦截）"""

import io
import json
import zipfile
from unittest.mock import patch

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.web_api import _import_zip_package


def _make_zip(
    tmp_path,
    data_json=None,
    media_files=None,
):
    """构造导入 zip：data_json 为写入 data.json 的原始内容，media_files 为 {路径: bytes}。"""
    zip_path = tmp_path / "import.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        if data_json is not None:
            zf.writestr("data.json", data_json)
        for name, content in (media_files or {}).items():
            zf.writestr(name, content)
    return str(zip_path)


def _media_base(tmp_path):
    return tmp_path / "astrbot_plugin_fox_toolbox" / "media"


class TestImportZipPackage:
    def test_normal_import(self, tmp_path):
        data = json.dumps({"messages": [{"platform": "telegram", "message_id": "1"}]})
        zip_path = _make_zip(
            tmp_path,
            data_json=data,
            media_files={"media/images/ab/abc.jpg": b"jpgdata"},
        )
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            records, restored = _import_zip_package(zip_path)
        assert len(records) == 1
        assert records[0]["platform"] == "telegram"
        assert restored == 1
        assert (_media_base(tmp_path) / "images" / "ab" / "abc.jpg").read_bytes() == b"jpgdata"

    def test_missing_data_json(self, tmp_path):
        zip_path = _make_zip(tmp_path, media_files={"media/a.txt": b"x"})
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            with pytest.raises(ValueError, match="缺少 data.json"):
                _import_zip_package(zip_path)

    def test_data_json_too_large(self, tmp_path):
        zip_path = _make_zip(tmp_path, data_json=json.dumps({"messages": []}))
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            with patch(
                "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.MAX_IMPORT_JSON_BYTES",
                1,
            ):
                with pytest.raises(ValueError, match="data.json 过大"):
                    _import_zip_package(zip_path)

    def test_media_total_too_large(self, tmp_path):
        zip_path = _make_zip(
            tmp_path,
            data_json=json.dumps({"messages": []}),
            media_files={"media/images/ab/a.jpg": b"0123456789"},
        )
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            with patch(
                "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.MAX_IMPORT_MEDIA_BYTES",
                5,
            ):
                with pytest.raises(ValueError, match="解压总量过大"):
                    _import_zip_package(zip_path)

    def test_too_many_media_files(self, tmp_path):
        zip_path = _make_zip(
            tmp_path,
            data_json=json.dumps({"messages": []}),
            media_files={
                f"media/images/{i:02d}/a.txt": b"x" for i in range(3)
            },
        )
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            with patch(
                "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.MAX_IMPORT_MEDIA_FILES",
                2,
            ):
                with pytest.raises(ValueError, match="数量过多"):
                    _import_zip_package(zip_path)

    def test_path_traversal_media_rejected(self, tmp_path):
        zip_path = _make_zip(
            tmp_path,
            data_json=json.dumps({"messages": []}),
            media_files={
                "media/../evil.txt": b"evil",
                "media//etc/passwd": b"passwd",
            },
        )
        with patch(
            "astrbot_plugin_fox_toolbox.fox_toolbox.web_api.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            records, restored = _import_zip_package(zip_path)
        assert records == []
        assert restored == 0
        assert not (tmp_path / "evil.txt").exists()
