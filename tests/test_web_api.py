"""web_api.py 测试 - 导入包解压防护（zip 炸弹限制、路径穿越拦截）"""

import io
import json
import sqlite3
import zipfile
from unittest.mock import patch

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.web_api import (
    _export_db,
    _export_sql,
    _import_zip_package,
    _convert_sql_to_db,
    _iter_db_records,
)


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


class _FakeDb:
    def __init__(self, records):
        self.records = records

    async def query_messages_batch(self, query_filter):
        for record in self.records:
            yield record


class TestSqliteBackup:
    @pytest.mark.asyncio
    async def test_export_db_round_trip(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord, QueryFilter

        record = MessageRecord(
            id=7,
            platform="telegram",
            message_id="m-7",
            session_id="s-7",
            group_id="g-7",
            sender_id="u-7",
            sender_name="Alice",
            message_type="group",
            message_str="hello",
            message_chain='[{"type":"Plain","text":"hello"}]',
            timestamp=1700000000000,
            created_at=1700000000000,
        )
        task = {"filter": {}, "actual_count": 0}
        path = await _export_db(
            "export_test", _FakeDb([record]), QueryFilter(), tmp_path, task
        )
        assert path.suffix == ".db"
        assert task["actual_count"] == 1
        rows = list(_iter_db_records(str(path)))
        assert rows[0]["platform"] == "telegram"
        assert rows[0]["message_id"] == "m-7"
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT value FROM export_info WHERE key='schema_version'").fetchone()[0]

    def test_import_db_rejects_invalid_file(self, tmp_path):
        path = tmp_path / "invalid.db"
        path.write_bytes(b"not a sqlite database")
        with pytest.raises(sqlite3.DatabaseError):
            list(_iter_db_records(str(path)))

    def test_import_db_requires_messages_table(self, tmp_path):
        path = tmp_path / "missing.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE other (id INTEGER)")
        with pytest.raises(ValueError, match="缺少 messages 表"):
            list(_iter_db_records(str(path)))

    @pytest.mark.asyncio
    async def test_export_sql_round_trip(self, tmp_path):
        from astrbot_plugin_fox_toolbox.fox_toolbox.models import MessageRecord, QueryFilter

        record = MessageRecord(
            id=8,
            platform="discord",
            message_id="m-8",
            sender_id="u-8",
            message_type="group",
            message_str="O'Reilly",
            timestamp=1700000000000,
            created_at=1700000000000,
        )
        task = {"filter": {}, "actual_count": 0}
        path = await _export_sql(
            "export_sql_test", _FakeDb([record]), QueryFilter(), tmp_path, task
        )
        assert path.suffix == ".sql"
        converted = _convert_sql_to_db(str(path))
        rows = list(_iter_db_records(converted))
        assert task["actual_count"] == 1
        assert rows[0]["message_str"] == "O'Reilly"

    def test_sql_import_rejects_untrusted_statement(self, tmp_path):
        path = tmp_path / "unsafe.sql"
        path.write_text("CREATE TABLE messages (platform TEXT); DROP TABLE messages;", encoding="utf-8")
        with pytest.raises(Exception):
            _convert_sql_to_db(str(path))

    def test_sql_import_requires_complete_statement(self, tmp_path):
        path = tmp_path / "incomplete.sql"
        path.write_text("CREATE TABLE messages (platform TEXT)", encoding="utf-8")
        with pytest.raises(ValueError, match="缺少分号"):
            _convert_sql_to_db(str(path))
