"""只读数据库浏览与安全查询模块

功能参考：
    astrbot_plugin_mysql（作者 Chris95743）
    https://github.com/Chris95743/astrbot_plugin_mysql

本模块借鉴该插件的「数据库表浏览」「SQL 安全校验」「自动 LIMIT 限制」
等设计思路，但以更严格的只读策略重新实现：
- 仅允许 SELECT / SHOW / DESCRIBE / DESC 前缀语句
- 自动拦截危险关键词（DROP / TRUNCATE / GRANT / 注释注入等）
- 自动追加 LIMIT，防止大表全量拉取
- 所有查询均在独立事务外执行，绝不执行任何写操作
"""

import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import aiomysql

from astrbot.api import logger

from .database import Database

DEFAULT_MAX_ROWS = 100
ABSOLUTE_MAX_ROWS = 500
QUERY_TIMEOUT = 15.0

# 危险关键词（借鉴参考插件 SQLValidator 的危险模式并扩展）
_DANGEROUS_PATTERNS = [
    r"\bDROP\s+(?:DATABASE|TABLE)\b",
    r"\bTRUNCATE\b",
    r"\bFLUSH\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bALTER\s+USER\b",
    r"\bCREATE\s+USER\b",
    r"\bRENAME\s+TABLE\b",
    r"\bLOCK\s+(?:TABLES|INSTANCE)\b",
    r"--",
    r"/\*",
    r"\*/",
]

_ALLOWED_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC")

_SYSTEM_TABLE_SUFFIXES = (
    "_schema_meta",
)


class DbExplorer:
    """基于现有消息库连接的安全表浏览与只读查询器"""

    def __init__(self, db: Optional[Database]):
        self._db = db
        self._dangerous = [
            re.compile(p, re.IGNORECASE) for p in _DANGEROUS_PATTERNS
        ]

    @property
    def available(self) -> bool:
        return self._db is not None

    def _pool(self):
        pool = getattr(self._db, "_pool", None)
        if pool is None:
            raise RuntimeError("数据库连接池未初始化")
        return pool

    def _validate_table_name(self, table_name: str) -> bool:
        """表名安全校验：仅允许字母、数字、下划线"""
        return bool(table_name) and all(
            c.isalnum() or c == "_" for c in table_name
        )

    def _strip_string_literals(self, sql: str) -> str:
        """剥除 SQL 中的字符串字面量（含 '' 与 \\ 转义），返回用于检测的文本"""
        stripped = re.sub(r"'(?:[^'\\]|\\.|'')*'", "''", sql)
        stripped = re.sub(r'"(?:[^"\\]|\\.|"")*"', '""', stripped)
        return stripped

    def check_dangerous(self, sql: str) -> Tuple[bool, str]:
        """检查 SQL 是否包含危险操作，返回 (是否危险, 原因)

        先剥除字符串字面量，避免把数据内容中的关键词（如 LIKE '%grant%'）
        误判为危险操作，同时保留对真实 DDL/DML 命令与注释注入的拦截。
        """
        if not sql or not sql.strip():
            return True, "SQL 语句为空"
        stripped_sql = self._strip_string_literals(sql)
        for pattern in self._dangerous:
            match = pattern.search(stripped_sql)
            if match:
                return True, f"包含危险操作: {match.group()}"
        return False, ""

    def _check_readonly_prefix(self, sql: str) -> Tuple[bool, str]:
        stripped = sql.strip().lstrip("(").strip()
        upper = stripped.upper()
        for prefix in _ALLOWED_PREFIXES:
            if upper.startswith(prefix):
                return True, ""
        return False, "仅允许执行 SELECT / SHOW / DESCRIBE / DESC 只读查询"

    def _ensure_limit(self, sql: str, max_rows: int) -> str:
        """为 SELECT 自动追加/钳制 LIMIT；SHOW/DESCRIBE/DESC 不追加，避免语法错误"""
        stripped = sql.strip().lstrip("(").strip().upper()
        if not stripped.startswith("SELECT"):
            return sql
        if re.search(r"\bLIMIT\s+\d+", sql, re.IGNORECASE):
            def _clamp(m):
                value = int(m.group(2))
                return f"{m.group(1)}{min(value, max_rows)}"
            return re.sub(r"(\bLIMIT\s+)(\d+)", _clamp, sql, flags=re.IGNORECASE)
        return f"{sql.rstrip(';')} LIMIT {max_rows}"

    async def list_tables(self) -> List[Dict[str, Any]]:
        """列出数据库所有业务表及其行数概览"""
        pool = self._pool()
        tables: List[str] = []
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW TABLES")
                rows = await cur.fetchall()
                if not rows:
                    return []
                first = rows[0]
                if isinstance(first, dict):
                    field_name = next(iter(first))
                    tables = [row[field_name] for row in rows]
                else:
                    tables = [row[0] for row in rows]

        result: List[Dict[str, Any]] = []
        for name in tables:
            if name.endswith(_SYSTEM_TABLE_SUFFIXES):
                continue
            row_count = await self._count_table(name)
            result.append({"name": name, "row_count": row_count})
        return result

    async def _count_table(self, table_name: str) -> int:
        if not self._validate_table_name(table_name):
            return -1
        pool = self._pool()
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                    row = await cur.fetchone()
                    return int(row[0]) if row else 0
        except Exception as e:
            logger.warning(f"[FoxToolbox DB] 统计表 {table_name} 行数失败: {e}")
            return -1

    async def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表结构（DESCRIBE）"""
        if not self._validate_table_name(table_name):
            raise ValueError("非法的表名")
        pool = self._pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(f"DESCRIBE `{table_name}`")
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_table_data(
        self,
        table_name: str,
        limit: int = DEFAULT_MAX_ROWS,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """预览表数据，返回 {columns, rows, limit, offset}"""
        if not self._validate_table_name(table_name):
            raise ValueError("非法的表名")
        limit = max(1, min(int(limit), ABSOLUTE_MAX_ROWS))
        offset = max(0, int(offset))
        pool = self._pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT * FROM `{table_name}` LIMIT %s OFFSET %s",
                    (limit, offset),
                )
                rows = await cur.fetchall()
        data = [dict(r) for r in rows]
        columns = list(data[0].keys()) if data else []
        return {"columns": columns, "rows": data, "limit": limit, "offset": offset}

    async def execute_readonly_query(
        self,
        sql: str,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> Dict[str, Any]:
        """执行只读 SQL 查询（SELECT/SHOW/DESCRIBE），返回 {columns, rows, affected_note}"""
        is_dangerous, reason = self.check_dangerous(sql)
        if is_dangerous:
            raise PermissionError(reason)

        allowed, reason = self._check_readonly_prefix(sql)
        if not allowed:
            raise PermissionError(reason)

        max_rows = max(1, min(int(max_rows), ABSOLUTE_MAX_ROWS))
        sql_with_limit = self._ensure_limit(sql, max_rows)

        pool = self._pool()
        try:
            columns, rows = await asyncio.wait_for(
                self._run_query(pool, sql_with_limit), timeout=QUERY_TIMEOUT
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"查询超时（{QUERY_TIMEOUT} 秒）")

        return {
            "columns": columns,
            "rows": rows,
            "sql": sql_with_limit,
            "row_count": len(rows),
            "truncated": len(rows) >= max_rows,
        }

    async def _run_query(
        self, pool, sql: str
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                rows = await cur.fetchall()
        data = [dict(r) for r in rows]
        columns = list(data[0].keys()) if data else []
        return columns, data
