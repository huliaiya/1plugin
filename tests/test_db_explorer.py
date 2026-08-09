"""db_explorer.py 测试 - SQL 安全校验逻辑 + MySQL 只读浏览集成测试"""

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import (
    DbExplorer,
    ABSOLUTE_MAX_ROWS,
    DEFAULT_MAX_ROWS,
)


@pytest.fixture
def explorer():
    return DbExplorer(db=None)


class TestCheckDangerous:
    def test_empty_sql(self, explorer):
        dangerous, reason = explorer.check_dangerous("")
        assert dangerous is True
        assert "为空" in reason

    def test_whitespace_sql(self, explorer):
        dangerous, _ = explorer.check_dangerous("   ")
        assert dangerous is True

    def test_safe_select(self, explorer):
        dangerous, reason = explorer.check_dangerous("SELECT * FROM messages")
        assert dangerous is False
        assert reason == ""

    def test_drop_database(self, explorer):
        dangerous, reason = explorer.check_dangerous("DROP DATABASE main_db")
        assert dangerous is True
        assert "DROP" in reason

    def test_drop_table(self, explorer):
        dangerous, _ = explorer.check_dangerous("drop table messages")
        assert dangerous is True

    def test_truncate(self, explorer):
        dangerous, _ = explorer.check_dangerous("TRUNCATE TABLE messages")
        assert dangerous is True

    def test_flush(self, explorer):
        dangerous, _ = explorer.check_dangerous("FLUSH PRIVILEGES")
        assert dangerous is True

    def test_grant_revoke(self, explorer):
        assert explorer.check_dangerous("GRANT ALL ON *.* TO 'x'")[0] is True
        assert explorer.check_dangerous("REVOKE ALL ON *.* FROM 'x'")[0] is True

    def test_create_alter_user(self, explorer):
        assert explorer.check_dangerous("CREATE USER 'a'@'%'")[0] is True
        assert explorer.check_dangerous("ALTER USER 'a'@'%' IDENTIFIED BY 'x'")[0] is True

    def test_rename_table(self, explorer):
        dangerous, _ = explorer.check_dangerous("RENAME TABLE a TO b")
        assert dangerous is True

    def test_lock_tables(self, explorer):
        assert explorer.check_dangerous("LOCK TABLES messages WRITE")[0] is True

    def test_sql_comment_injection(self, explorer):
        assert explorer.check_dangerous("SELECT 1 -- comment")[0] is True
        assert explorer.check_dangerous("SELECT 1 /* comment */")[0] is True

    def test_select_with_dangerous_keyword_as_plainword(self, explorer):
        dangerous, _ = explorer.check_dangerous(
            "SELECT * FROM messages WHERE message_str LIKE '%grant%'"
        )
        assert dangerous is False

    def test_keyword_inside_string_literal_allowed(self, explorer):
        dangerous, _ = explorer.check_dangerous(
            "SELECT * FROM messages WHERE message_str = 'drop table x'"
        )
        assert dangerous is False

    def test_dash_comment_inside_string_allowed(self, explorer):
        dangerous, _ = explorer.check_dangerous(
            "SELECT * FROM messages WHERE message_str = 'a--b'"
        )
        assert dangerous is False


class TestCheckReadonlyPrefix:
    def test_select_prefix(self, explorer):
        allowed, _ = explorer._check_readonly_prefix("SELECT 1")
        assert allowed is True

    def test_lowercase_prefix(self, explorer):
        allowed, _ = explorer._check_readonly_prefix("  select * from messages")
        assert allowed is True

    def test_show_prefix(self, explorer):
        assert explorer._check_readonly_prefix("SHOW TABLES")[0] is True

    def test_describe_prefix(self, explorer):
        assert explorer._check_readonly_prefix("DESCRIBE messages")[0] is True
        assert explorer._check_readonly_prefix("desc messages")[0] is True

    def test_parenthesized_select(self, explorer):
        allowed, _ = explorer._check_readonly_prefix("(SELECT 1)")
        assert allowed is True

    def test_write_prefix_rejected(self, explorer):
        for sql in ("INSERT INTO messages VALUES (1)", "UPDATE messages SET a=1", "DELETE FROM messages", "REPLACE INTO messages VALUES(1)"):
            allowed, reason = explorer._check_readonly_prefix(sql)
            assert allowed is False
            assert "只读" in reason

    def test_with_blocked_prefix(self, explorer):
        allowed, _ = explorer._check_readonly_prefix("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert allowed is False


class TestEnsureLimit:
    def test_appends_limit(self, explorer):
        sql = explorer._ensure_limit("SELECT * FROM messages", 100)
        assert sql == "SELECT * FROM messages LIMIT 100"

    def test_appends_limit_with_trailing_semicolon(self, explorer):
        sql = explorer._ensure_limit("SELECT * FROM messages;", 100)
        assert sql.endswith("LIMIT 100")

    def test_existing_limit_kept(self, explorer):
        sql = explorer._ensure_limit("SELECT * FROM messages LIMIT 5", 100)
        assert sql == "SELECT * FROM messages LIMIT 5"

    def test_existing_limit_clamped(self, explorer):
        sql = explorer._ensure_limit("SELECT * FROM messages LIMIT 999999", 100)
        assert sql == "SELECT * FROM messages LIMIT 100"

    def test_existing_limit_within_kept(self, explorer):
        sql = explorer._ensure_limit("SELECT * FROM messages LIMIT 5", 100)
        assert sql == "SELECT * FROM messages LIMIT 5"

    def test_show_no_limit_appended(self, explorer):
        sql = explorer._ensure_limit("SHOW TABLES", 100)
        assert sql == "SHOW TABLES"

    def test_describe_no_limit_appended(self, explorer):
        sql = explorer._ensure_limit("DESCRIBE messages", 100)
        assert sql == "DESCRIBE messages"
        sql2 = explorer._ensure_limit("desc messages", 100)
        assert sql2 == "desc messages"

    def test_select_lowercase_appends_limit(self, explorer):
        sql = explorer._ensure_limit("select * from messages", 100)
        assert sql == "select * from messages LIMIT 100"

    def test_two_param_limit_both_clamped(self, explorer):
        sql = explorer._ensure_limit(
            "SELECT * FROM messages LIMIT 999999999, 5000000", 100
        )
        assert sql == "SELECT * FROM messages LIMIT 100, 100"

    def test_limit_in_string_literal_still_appended(self, explorer):
        # 字符串字面量内的 'LIMIT 999' 不应被误判为已有 LIMIT
        sql = explorer._ensure_limit(
            "SELECT * FROM messages WHERE message_str = 'LIMIT 999'", 100
        )
        assert sql.endswith("LIMIT 100")

    def test_parameterized_limit_not_duplicated(self, explorer):
        # 参数化 LIMIT 无法钳制，应保持原样而非追加第二个 LIMIT 造成语法错误
        sql = explorer._ensure_limit("SELECT * FROM messages LIMIT %s", 100)
        assert sql == "SELECT * FROM messages LIMIT %s"
        sql2 = explorer._ensure_limit("SELECT * FROM messages LIMIT ?", 100)
        assert sql2 == "SELECT * FROM messages LIMIT ?"

    def test_limit_all_not_duplicated(self, explorer):
        # 非数字 LIMIT 形式同样不能追加重复 LIMIT
        sql = explorer._ensure_limit("SELECT * FROM messages LIMIT ALL", 100)
        assert sql == "SELECT * FROM messages LIMIT ALL"

    def test_limit_offset_form_kept(self, explorer):
        sql = explorer._ensure_limit("SELECT * FROM messages LIMIT 10 OFFSET 20", 100)
        assert sql == "SELECT * FROM messages LIMIT 10 OFFSET 20"

    def test_select_into_outfile_flagged(self, explorer):
        dangerous, reason = explorer.check_dangerous(
            "SELECT * FROM messages INTO OUTFILE '/tmp/x'"
        )
        assert dangerous is True

    def test_load_file_flagged(self, explorer):
        dangerous, _ = explorer.check_dangerous(
            "SELECT LOAD_FILE('/etc/passwd')"
        )
        assert dangerous is True

    def test_sleep_flagged(self, explorer):
        dangerous, _ = explorer.check_dangerous(
            "SELECT SLEEP(5)"
        )
        assert dangerous is True

    def test_system_variable_read_flagged(self, explorer):
        # SELECT @@version / @@datadir 会泄露服务器敏感信息，应被拦截
        dangerous, reason = explorer.check_dangerous(
            "SELECT @@version"
        )
        assert dangerous is True
        assert "系统变量" in reason

    def test_system_variable_inside_string_allowed(self, explorer):
        # 字符串字面量中的 '@@' 属于数据内容，不应误判
        dangerous, reason = explorer.check_dangerous(
            "SELECT message_str FROM messages WHERE message_str = 'use @@version here'"
        )
        assert dangerous is False
        assert reason == ""

    def test_sleep_in_string_literal_allowed(self, explorer):
        # 字符串字面量中的 SLEEP 不应被误判
        dangerous, reason = explorer.check_dangerous(
            "SELECT message_str FROM messages WHERE message_str = 'SLEEP(5)'"
        )
        assert dangerous is False
        assert reason == ""


class TestListTablesCompatibility:
    """list_tables 对 tuple / dict 两种游标行的兼容性（不依赖真实 MySQL）"""

    def _make_explorer(self, table_rows):
        class FakeCursor:
            def __init__(self):
                self._sqls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, sql, *args):
                self._sqls.append(sql)

            async def fetchall(self):
                if self._sqls and self._sqls[-1].strip().upper().startswith("SHOW"):
                    return table_rows
                return []

            async def fetchone(self):
                if self._sqls and self._sqls[-1].strip().upper().startswith("SELECT COUNT"):
                    return (3,)
                return None

        class FakeConn:
            async def commit(self):
                return None

            def cursor(self, *a, **k):
                return FakeCursor()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class FakePool:
            async def acquire(self):
                return FakeConn()

            def release(self, conn):
                pass

        class FakeDb:
            _pool = FakePool()

        return DbExplorer(FakeDb())

    @pytest.mark.asyncio
    async def test_tuple_rows(self):
        explorer = self._make_explorer([("messages",), ("_schema_meta",)])
        tables = await explorer.list_tables()
        names = [t["name"] for t in tables]
        assert "messages" in names
        assert "_schema_meta" not in names
        msg = [t for t in tables if t["name"] == "messages"][0]
        assert msg["row_count"] == 3

    @pytest.mark.asyncio
    async def test_dict_rows(self):
        explorer = self._make_explorer(
            [{"Tables_in_main_db": "messages"}, {"Tables_in_main_db": "channels"}]
        )
        tables = await explorer.list_tables()
        names = [t["name"] for t in tables]
        assert "messages" in names
        assert "channels" in names

    @pytest.mark.asyncio
    async def test_empty_rows(self):
        explorer = self._make_explorer([])
        tables = await explorer.list_tables()
        assert tables == []


class TestValidateTableName:
    def test_valid_names(self, explorer):
        assert explorer._validate_table_name("messages") is True
        assert explorer._validate_table_name("_schema_meta") is True
        assert explorer._validate_table_name("user_records_01") is True

    def test_invalid_names(self, explorer):
        assert explorer._validate_table_name("messages; DROP TABLE x") is False
        assert explorer._validate_table_name("`messages`") is False
        assert explorer._validate_table_name("messages--") is False
        assert explorer._validate_table_name("") is False
        assert explorer._validate_table_name("a b") is False


class TestExplorerLimits:
    def test_default_max_rows(self, explorer):
        assert DEFAULT_MAX_ROWS == 100
        assert ABSOLUTE_MAX_ROWS == 500


@pytest.mark.asyncio
class TestMysqlExplorer:
    async def test_list_tables_excludes_schema_meta(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        tables = await explorer.list_tables()
        names = [t["name"] for t in tables]
        assert "messages" in names
        assert all(not n.endswith("_schema_meta") for n in names)
        messages = [t for t in tables if t["name"] == "messages"][0]
        assert messages["row_count"] >= 0

    async def test_get_table_schema(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        schema = await explorer.get_table_schema("messages")
        assert len(schema) > 0
        fields = {row["Field"] for row in schema}
        assert "message_id" in fields
        assert "platform" in fields

    async def test_get_table_data(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        result = await explorer.get_table_data("messages", limit=5)
        assert set(result.keys()) == {"columns", "rows", "limit", "offset"}
        assert result["limit"] == 5
        assert isinstance(result["rows"], list)

    async def test_get_table_data_limit_clamped(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        result = await explorer.get_table_data("messages", limit=99999)
        assert result["limit"] == ABSOLUTE_MAX_ROWS

    async def test_get_table_data_invalid_name(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        with pytest.raises(ValueError):
            await explorer.get_table_data("messages; DROP TABLE x")

    async def test_execute_readonly_query_select(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        result = await explorer.execute_readonly_query("SELECT * FROM messages", max_rows=10)
        assert "columns" in result
        assert "rows" in result
        assert result["row_count"] <= 10
        assert result["sql"].endswith("LIMIT 10")

    async def test_execute_readonly_query_rejects_write(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        with pytest.raises(PermissionError):
            await explorer.execute_readonly_query("DELETE FROM messages")

    async def test_execute_readonly_query_rejects_drop(self, mysql_db):
        from astrbot_plugin_fox_toolbox.fox_toolbox.db_explorer import DbExplorer

        explorer = DbExplorer(mysql_db)
        with pytest.raises(PermissionError):
            await explorer.execute_readonly_query("DROP TABLE messages")
