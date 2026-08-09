"""SQLite 本地兜底存储模块。

MySQL 主存储不可用时，插件自动降级写入本地 SQLite（`messages_fallback.db`），
恢复后由 `Database` 的恢复检测任务分批补写回 MySQL。本模块只负责 SQLite
侧的读写，与 MySQL 表结构保持一致（额外含 `synced` 列用于标记是否已同步）。

所有 sqlite3 同步 API 均通过 `asyncio.to_thread` 执行，避免阻塞事件循环。
"""

import asyncio
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from astrbot.api import logger

from .models import MessageRecord, MessageStats, QueryFilter
from .serializer import compute_content_hash, extract_media_paths

_SELECT_COLUMNS = """
    id, platform, message_id, session_id, group_id, channel_id,
    sender_id, sender_name, message_type,
    message_str, message_chain, raw_message,
    reply_to_id, content_hash, content_types, timestamp, created_at
"""


def _has_value(value: Optional[str]) -> bool:
    return value is not None and str(value).strip() != ""


def _infer_message_bucket(
    message_type: Optional[str],
    group_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> str:
    """兼容历史脏数据，推断消息应归属的统计桶（与 database.py 保持一致）。"""
    from .database import _infer_message_bucket as _db_infer

    return _db_infer(message_type, group_id, channel_id)


def _parse_content_types(raw: Any, message_str: Optional[str] = None) -> List[str]:
    """兼容逗号串、JSON 数组和历史脏格式（与 database.py 保持一致）。"""
    from .database import _parse_content_types as _db_parse

    return _db_parse(raw, message_str)


def _row_to_record(row) -> MessageRecord:
    from .database import _row_to_record as _db_r2r

    return _db_r2r(row)


def _escape_like(keyword: str) -> str:
    return (
        keyword.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class SQLiteStore:
    """SQLite 消息存储后端（MySQL 兜底）。

    :param db_path: SQLite 数据库文件路径（含文件名）
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            message_id TEXT,
            session_id TEXT,
            group_id TEXT,
            channel_id TEXT,
            sender_id TEXT NOT NULL,
            sender_name TEXT,
            message_type TEXT NOT NULL,
            message_str TEXT,
            message_chain TEXT,
            raw_message TEXT,
            reply_to_id TEXT,
            content_hash TEXT,
            content_types TEXT,
            timestamp INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """

    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_schema()

    # ---- 初始化 ----

    def _init_schema(self) -> None:
        with sqlite3.connect(self._path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(self._DDL)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_content_hash "
                "ON messages(content_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform ON messages(platform)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sender ON messages(sender_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_group ON messages(group_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_synced ON messages(synced)"
            )
            conn.commit()

    # ---- 底层执行 ----

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """执行只读查询，返回行列表。"""
        with self._connect() as conn:
            return conn.execute(sql, params).fetchall()

    def _query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _execute(self, sql: str, params: tuple = ()) -> int:
        """执行写操作，返回 rowcount。"""
        with self._write_lock:
            with self._connect() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.rowcount

    # ---- 状态 ----

    async def ping(self) -> bool:
        try:
            row = await asyncio.to_thread(self._query_one, "SELECT 1")
            return row is not None
        except Exception:
            return False

    async def get_table_count(self) -> int:
        try:
            row = await asyncio.to_thread(
                self._query_one,
                "SELECT COUNT(*) AS c FROM sqlite_master WHERE type = 'table'",
            )
            return int(row["c"]) if row else 0
        except Exception as e:
            logger.warning(f"[FoxToolbox] SQLite 获取表数量失败: {e}")
            return -1

    async def get_total_count(self) -> int:
        row = await asyncio.to_thread(
            self._query_one, "SELECT COUNT(*) AS c FROM messages"
        )
        return int(row["c"]) if row else 0

    @property
    def path(self) -> str:
        return self._path

    # ---- 写入 ----

    async def save_message(self, record: MessageRecord) -> int:
        """保存单条消息，返回记录 ID（重复消息返回 -1）。"""
        return await asyncio.to_thread(self._save_message_thread, record)

    def _save_message_thread(self, record: MessageRecord) -> int:
        created_at = record.created_at or int(time.time() * 1000)
        content_hash = record.content_hash or compute_content_hash(
            record.platform, record.session_id, record.sender_id,
            record.message_str, record.timestamp,
        )
        message_id = record.message_id if record.message_id else None
        sql = """
            INSERT OR IGNORE INTO messages (
                platform, message_id, session_id, group_id, channel_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                reply_to_id, content_hash, content_types, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record.platform,
            message_id,
            record.session_id,
            record.group_id,
            record.channel_id,
            record.sender_id,
            record.sender_name,
            record.message_type,
            record.message_str,
            record.message_chain,
            record.raw_message,
            record.reply_to_id,
            content_hash,
            record.content_types,
            record.timestamp,
            created_at,
        )
        with self._write_lock:
            with self._connect() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
                if cur.rowcount > 0:
                    record.content_hash = content_hash
                    record.created_at = created_at
                    return cur.lastrowid
                return -1

    async def save_messages_batch(
        self, records: List[MessageRecord]
    ) -> Tuple[int, int]:
        """批量保存，返回 (成功数量, 跳过数量)。"""
        if not records:
            return 0, 0
        return await asyncio.to_thread(self._save_messages_batch_thread, records)

    def _save_messages_batch_thread(
        self, records: List[MessageRecord]
    ) -> Tuple[int, int]:
        now_ms = int(time.time() * 1000)
        sql = """
            INSERT OR IGNORE INTO messages (
                platform, message_id, session_id, group_id, channel_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                reply_to_id, content_hash, content_types, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        saved = 0
        skipped = 0
        with self._write_lock:
            with self._connect() as conn:
                for record in records:
                    created_at = record.created_at or now_ms
                    content_hash = record.content_hash or compute_content_hash(
                        record.platform, record.session_id, record.sender_id,
                        record.message_str, record.timestamp,
                    )
                    message_id = record.message_id if record.message_id else None
                    params = (
                        record.platform,
                        message_id,
                        record.session_id,
                        record.group_id,
                        record.channel_id,
                        record.sender_id,
                        record.sender_name,
                        record.message_type,
                        record.message_str,
                        record.message_chain,
                        record.raw_message,
                        record.reply_to_id,
                        content_hash,
                        record.content_types,
                        record.timestamp,
                        created_at,
                    )
                    cur = conn.execute(sql, params)
                    if cur.rowcount > 0:
                        record.content_hash = content_hash
                        record.created_at = created_at
                        record.id = cur.lastrowid
                        saved += 1
                    else:
                        skipped += 1
                conn.commit()
        return saved, skipped

    # ---- WHERE 构建 ----

    def _build_where(self, query_filter: QueryFilter) -> Tuple[str, List[Any]]:
        """构建 SQLite 版 WHERE 子句和参数（`?` 占位符）。"""
        conditions: List[str] = []
        params: List[Any] = []

        def safe_str(val: Any) -> str:
            return str(val) if val is not None else ""

        def safe_int(val: Any) -> int:
            if val is None:
                return 0
            try:
                return int(val)
            except (TypeError, ValueError):
                return 0

        platforms = query_filter.get_platforms()
        if platforms:
            if len(platforms) == 1:
                conditions.append("platform = ?")
                params.append(safe_str(platforms[0]))
            else:
                conditions.append(
                    f"platform IN ({','.join(['?'] * len(platforms))})"
                )
                params.extend([safe_str(p) for p in platforms])

        sender_ids = query_filter.get_sender_ids()
        if sender_ids:
            if len(sender_ids) == 1:
                conditions.append("sender_id = ?")
                params.append(safe_str(sender_ids[0]))
            else:
                conditions.append(
                    f"sender_id IN ({','.join(['?'] * len(sender_ids))})"
                )
                params.extend([safe_str(s) for s in sender_ids])

        group_ids = query_filter.get_group_ids()
        if group_ids:
            if len(group_ids) == 1:
                conditions.append("group_id = ?")
                params.append(safe_str(group_ids[0]))
            else:
                conditions.append(
                    f"group_id IN ({','.join(['?'] * len(group_ids))})"
                )
                params.extend([safe_str(g) for g in group_ids])

        session_ids = query_filter.get_session_ids()
        if session_ids:
            if len(session_ids) == 1:
                conditions.append("session_id = ?")
                params.append(safe_str(session_ids[0]))
            else:
                conditions.append(
                    f"session_id IN ({','.join(['?'] * len(session_ids))})"
                )
                params.extend([safe_str(s) for s in session_ids])

        if query_filter.channel_id:
            conditions.append("channel_id = ?")
            params.append(safe_str(query_filter.channel_id))

        if query_filter.message_type:
            conditions.append("message_type = ?")
            params.append(safe_str(query_filter.message_type))

        if query_filter.reply_to_id:
            conditions.append("reply_to_id = ?")
            params.append(safe_str(query_filter.reply_to_id))

        if query_filter.time:
            from .time_utils import parse_time_range

            start_time, end_time = parse_time_range(query_filter.time)
            conditions.append("timestamp >= ?")
            params.append(safe_int(start_time))
            conditions.append("timestamp <= ?")
            params.append(safe_int(end_time))
        else:
            if query_filter.start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(safe_int(query_filter.start_time))
            if query_filter.end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(safe_int(query_filter.end_time))

        if query_filter.keyword:
            keyword_str = safe_str(query_filter.keyword)
            escaped = _escape_like(keyword_str)
            conditions.append("message_str LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    # ---- 查询 ----

    async def query_messages(self, query_filter: QueryFilter) -> List[MessageRecord]:
        """根据过滤器查询消息，返回与 MySQL 相同的 MessageRecord 列表。"""
        return await asyncio.to_thread(self._query_messages_thread, query_filter)

    def _query_messages_thread(
        self, query_filter: QueryFilter
    ) -> List[MessageRecord]:
        where_clause, params = self._build_where(query_filter)
        order_clause = (
            "timestamp DESC"
            if query_filter.is_desc_order()
            else "timestamp ASC"
        )
        limit_val = query_filter.limit
        offset_val = query_filter.offset
        no_limit = limit_val is None or limit_val == -1 or limit_val == 0
        effective_limit = None if no_limit else int(limit_val)
        effective_offset = max(
            0, int(offset_val) if offset_val is not None else 0
        )

        if effective_limit is not None:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
            params = params + [effective_limit, effective_offset]
        else:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
            """
        rows = self._query(sql, tuple(params))
        return [_row_to_record(row) for row in rows]

    async def query_messages_batch(
        self,
        query_filter: QueryFilter,
        batch_size: int = 500,
    ) -> AsyncGenerator[MessageRecord, None]:
        """分批查询消息，返回异步生成器。"""
        where_clause, params = self._build_where(query_filter)
        order_clause = (
            "timestamp DESC"
            if query_filter.is_desc_order()
            else "timestamp ASC"
        )
        total_limit = (
            query_filter.limit
            if query_filter.limit and query_filter.limit > 0
            else None
        )
        offset_val = max(
            0, int(query_filter.offset) if query_filter.offset else 0
        )
        current_offset = offset_val
        total_fetched = 0

        while True:
            if total_limit is not None and total_fetched >= total_limit:
                break
            current_batch_size = batch_size
            if total_limit is not None:
                remaining = total_limit - total_fetched
                current_batch_size = min(batch_size, remaining)

            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
            batch_params = params + [current_batch_size, current_offset]
            rows = await asyncio.to_thread(self._query, sql, tuple(batch_params))
            if not rows:
                break
            for row in rows:
                yield _row_to_record(row)
                total_fetched += 1
            if len(rows) < current_batch_size:
                break
            current_offset += batch_size

    async def count_messages(self, query_filter: QueryFilter) -> int:
        """统计符合条件的消息数量。"""
        return await asyncio.to_thread(self._count_messages_thread, query_filter)

    def _count_messages_thread(self, query_filter: QueryFilter) -> int:
        where_clause, params = self._build_where(query_filter)
        row = self._query_one(
            f"SELECT COUNT(*) AS c FROM messages WHERE {where_clause}",
            tuple(params),
        )
        return int(row["c"]) if row else 0

    # ---- 单条 / 批量定位 ----

    async def get_message_by_id(self, message_id: int) -> Optional[MessageRecord]:
        row = await asyncio.to_thread(
            self._query_one,
            f"SELECT {_SELECT_COLUMNS} FROM messages WHERE id = ?",
            (message_id,),
        )
        return _row_to_record(row) if row else None

    async def get_message_by_platform_id(
        self,
        platform_message_id: str,
        platform: Optional[str] = None,
    ) -> Optional[MessageRecord]:
        if platform:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE message_id = ? AND platform = ?
                ORDER BY timestamp DESC LIMIT 1
            """
            params = (platform_message_id, platform)
        else:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE message_id = ?
                ORDER BY timestamp DESC LIMIT 1
            """
            params = (platform_message_id,)
        row = await asyncio.to_thread(self._query_one, sql, params)
        return _row_to_record(row) if row else None

    async def get_existing_message_ids(
        self, message_ids: List[str], platform: str
    ) -> set:
        if not message_ids:
            return set()
        placeholders = ",".join(["?"] * len(message_ids))
        sql = (
            f"SELECT message_id FROM messages "
            f"WHERE message_id IN ({placeholders}) AND platform = ?"
        )
        params = list(message_ids) + [platform]
        rows = await asyncio.to_thread(self._query, sql, tuple(params))
        return {row["message_id"] for row in rows}

    async def get_context_messages(
        self,
        message_id: int,
        before: int = 5,
        after: int = 5,
    ) -> Dict[str, List[MessageRecord]]:
        target = await self.get_message_by_id(message_id)
        if not target:
            return {"before": [], "after": []}

        if target.message_type == "channel" and target.channel_id:
            scope_conditions = (
                "platform = ? AND channel_id = ? "
                "AND message_type = 'channel'"
            )
            scope_params = [target.platform, target.channel_id]
        elif target.message_type == "group" and target.group_id:
            scope_conditions = (
                "platform = ? AND group_id = ? "
                "AND message_type = 'group'"
            )
            scope_params = [target.platform, target.group_id]
        elif target.session_id and target.session_id.strip():
            scope_conditions = "session_id = ?"
            scope_params = [target.session_id]
        else:
            scope_conditions = (
                "platform = ? AND sender_id = ? "
                "AND message_type = 'private'"
            )
            scope_params = [target.platform, target.sender_id]

        before_sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM messages
            WHERE {scope_conditions} AND timestamp < ?
            ORDER BY timestamp DESC LIMIT ?
        """
        before_rows = await asyncio.to_thread(
            self._query, before_sql, tuple(scope_params + [target.timestamp, before])
        )
        after_sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM messages
            WHERE {scope_conditions} AND timestamp > ?
            ORDER BY timestamp ASC LIMIT ?
        """
        after_rows = await asyncio.to_thread(
            self._query, after_sql, tuple(scope_params + [target.timestamp, after])
        )
        before_msgs = [_row_to_record(row) for row in reversed(before_rows)]
        after_msgs = [_row_to_record(row) for row in after_rows]
        return {"before": before_msgs, "after": after_msgs}

    # ---- 统计 ----

    async def get_stats(self) -> MessageStats:
        """获取消息统计信息（与 MySQL 聚合结果一致）。"""
        return await asyncio.to_thread(self._get_stats_thread)

    def _get_stats_thread(self) -> MessageStats:
        stats = MessageStats()
        total_row = self._query_one("SELECT COUNT(*) AS c FROM messages")
        stats.total_count = int(total_row["c"]) if total_row else 0

        group_rows = self._query(
            "SELECT platform, message_type, group_id, channel_id, "
            "COUNT(*) AS c FROM messages "
            "GROUP BY platform, message_type, group_id, channel_id"
        )
        platform_stats: Dict[str, int] = {}
        for row in group_rows:
            bucket = _infer_message_bucket(
                row["message_type"], row["group_id"], row["channel_id"]
            )
            count = int(row["c"])
            if bucket == "group":
                stats.group_message_count += count
            elif bucket == "private":
                stats.private_message_count += count
            elif bucket == "channel":
                stats.channel_message_count += count
            platform_stats[row["platform"]] = (
                platform_stats.get(row["platform"], 0) + count
            )
        stats.platform_stats = platform_stats

        time_row = self._query_one(
            "SELECT MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts, "
            "MIN(created_at) AS min_ca, MAX(created_at) AS max_ca FROM messages"
        )
        if time_row:
            stats.oldest_timestamp = time_row["min_ts"]
            stats.newest_timestamp = time_row["max_ts"]
            stats.first_record_time = time_row["min_ca"]
            stats.last_record_time = time_row["max_ca"]
        return stats

    async def get_content_type_stats(self) -> List[Dict]:
        """获取消息内容类型统计（与 MySQL 一致）。"""
        return await asyncio.to_thread(self._get_content_type_stats_thread)

    def _get_content_type_stats_thread(self) -> List[Dict]:
        rows = self._query("SELECT content_types, message_str FROM messages")
        if not rows:
            return []
        labels = {
            "text": "文字",
            "image": "图片",
            "video": "视频",
            "voice": "语音",
            "document": "文档",
            "audio": "音频文件",
            "archive": "压缩包",
            "code": "代码/程序",
            "file_image": "图片文件",
            "file_video": "视频文件",
            "other_file": "其他文件",
            "at": "@提及",
            "reply": "回复",
            "face": "表情",
            "rich": "富文本/卡片",
            "unknown": "未知/其他",
        }
        keys = [
            "text", "image", "video", "voice",
            "document", "audio", "archive", "code",
            "file_image", "file_video", "other_file",
            "at", "reply", "face", "rich", "unknown",
        ]
        counters = {key: 0 for key in keys}
        for row in rows:
            parsed_types = _parse_content_types(
                row["content_types"], row["message_str"]
            )
            if not parsed_types:
                counters["unknown"] += 1
                continue
            recognized = False
            type_set = set(parsed_types)
            if "Plain" in type_set:
                counters["text"] += 1
                recognized = True
            if "Image" in type_set:
                counters["image"] += 1
                recognized = True
            if "Video" in type_set:
                counters["video"] += 1
                recognized = True
            if "Record" in type_set:
                counters["voice"] += 1
                recognized = True
            if "FileDocument" in type_set:
                counters["document"] += 1
                recognized = True
            if "FileAudio" in type_set:
                counters["audio"] += 1
                recognized = True
            if "FileArchive" in type_set:
                counters["archive"] += 1
                recognized = True
            if "FileCode" in type_set:
                counters["code"] += 1
                recognized = True
            if "FileImage" in type_set:
                counters["file_image"] += 1
                recognized = True
            if "FileVideo" in type_set:
                counters["file_video"] += 1
                recognized = True
            if "File" in type_set:
                counters["other_file"] += 1
                recognized = True
            if "At" in type_set or "AtAll" in type_set:
                counters["at"] += 1
                recognized = True
            if "Reply" in type_set:
                counters["reply"] += 1
                recognized = True
            if "Face" in type_set:
                counters["face"] += 1
                recognized = True
            if {"Json", "Xml", "Card"} & type_set:
                counters["rich"] += 1
                recognized = True
            if not recognized:
                counters["unknown"] += 1
        result = []
        for key in keys:
            count = counters[key]
            if count > 0:
                result.append({
                    "type": key,
                    "label": labels[key],
                    "count": count,
                })
        result.sort(key=lambda x: x["count"], reverse=True)
        return result

    async def get_platform_detail_stats(self) -> List[Dict]:
        """获取各平台的详细统计（与 MySQL 一致）。"""
        return await asyncio.to_thread(self._get_platform_detail_stats_thread)

    def _get_platform_detail_stats_thread(self) -> List[Dict]:
        rows = self._query(
            "SELECT platform, message_type, group_id, channel_id, "
            "content_types, message_str, timestamp FROM messages"
        )
        platform_names = {
            "aiocqhttp": "QQ (NapCat)",
            "qq_official": "QQ官方",
            "qq_official_webhook": "QQ官方(Webhook)",
            "telegram": "Telegram",
            "discord": "Discord",
            "kook": "KOOK",
            "slack": "Slack",
            "dingtalk": "钉钉",
            "lark": "飞书",
            "wecom": "企业微信",
            "wecom_ai_bot": "企微AI助手",
            "weixin_oc": "微信客服",
            "weixin_official_account": "微信公众号",
            "line": "LINE",
            "misskey": "Misskey",
            "mattermost": "Mattermost",
            "satori": "Satori",
            "vocechat": "VoCE",
            "matrix": "Matrix",
        }
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            platform = row["platform"]
            item = grouped.setdefault(
                platform,
                {
                    "platform": platform,
                    "platform_name": platform_names.get(platform, platform),
                    "total": 0,
                    "group_count": 0,
                    "private_count": 0,
                    "channel_count": 0,
                    "image_count": 0,
                    "video_count": 0,
                    "voice_count": 0,
                    "document_count": 0,
                    "audio_count": 0,
                    "archive_count": 0,
                    "code_count": 0,
                    "other_file_count": 0,
                    "oldest_timestamp": None,
                    "newest_timestamp": None,
                },
            )
            item["total"] += 1
            bucket = _infer_message_bucket(
                row["message_type"], row["group_id"], row["channel_id"]
            )
            if bucket == "group":
                item["group_count"] += 1
            elif bucket == "private":
                item["private_count"] += 1
            elif bucket == "channel":
                item["channel_count"] += 1
            parsed_types = set(
                _parse_content_types(row["content_types"], row["message_str"])
            )
            if "Image" in parsed_types:
                item["image_count"] += 1
            if "Video" in parsed_types:
                item["video_count"] += 1
            if "Record" in parsed_types:
                item["voice_count"] += 1
            if "FileDocument" in parsed_types:
                item["document_count"] += 1
            if "FileAudio" in parsed_types:
                item["audio_count"] += 1
            if "FileArchive" in parsed_types:
                item["archive_count"] += 1
            if "FileCode" in parsed_types:
                item["code_count"] += 1
            if "File" in parsed_types:
                item["other_file_count"] += 1
            timestamp = row["timestamp"]
            if timestamp is not None:
                if item["oldest_timestamp"] is None or timestamp < item["oldest_timestamp"]:
                    item["oldest_timestamp"] = timestamp
                if item["newest_timestamp"] is None or timestamp > item["newest_timestamp"]:
                    item["newest_timestamp"] = timestamp
        return sorted(grouped.values(), key=lambda x: x["total"], reverse=True)

    async def get_timeline_stats(
        self,
        interval: str = "day",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict]:
        """按时间间隔统计消息数量（Python 端分组，与 MySQL 一致）。"""
        return await asyncio.to_thread(
            self._get_timeline_stats_thread,
            interval, start_time, end_time, platform, group_id,
        )

    def _get_timeline_stats_thread(
        self,
        interval: str,
        start_time: Optional[int],
        end_time: Optional[int],
        platform: Optional[str],
        group_id: Optional[str],
    ) -> List[Dict]:
        conditions = []
        params: List[Any] = []
        if start_time:
            conditions.append("`timestamp` >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("`timestamp` <= ?")
            params.append(end_time)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT `timestamp`, `message_type`, `group_id`, `channel_id`
            FROM messages
            WHERE {where_clause}
        """
        from collections import OrderedDict
        from datetime import datetime as _dt

        rows = self._query(sql, tuple(params))
        groups: "OrderedDict[str, Dict]" = OrderedDict()
        for row in rows:
            ts_ms = row["timestamp"]
            msg_type = row["message_type"] or ""
            dt = _dt.fromtimestamp(ts_ms / 1000)
            if interval == "week":
                iso_year, iso_week = dt.isocalendar()[0], dt.isocalendar()[1]
                key = f"{iso_year}-W{iso_week:02d}"
            elif interval == "month":
                key = dt.strftime("%Y-%m")
            else:
                key = dt.strftime("%Y-%m-%d")
            if key not in groups:
                groups[key] = {
                    "date": key,
                    "count": 0,
                    "group_count": 0,
                    "private_count": 0,
                    "channel_count": 0,
                }
            groups[key]["count"] += 1
            bucket = _infer_message_bucket(
                msg_type, row["group_id"], row["channel_id"]
            )
            if bucket == "group":
                groups[key]["group_count"] += 1
            elif bucket == "private":
                groups[key]["private_count"] += 1
            elif bucket == "channel":
                groups[key]["channel_count"] += 1
        return list(groups.values())

    async def get_sender_ranking(
        self,
        limit: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict]:
        """获取发送者排行榜（与 MySQL 一致）。"""
        return await asyncio.to_thread(
            self._get_sender_ranking_thread,
            limit, start_time, end_time, platform, group_id,
        )

    def _get_sender_ranking_thread(
        self,
        limit: int,
        start_time: Optional[int],
        end_time: Optional[int],
        platform: Optional[str],
        group_id: Optional[str],
    ) -> List[Dict]:
        conditions = []
        params: List[Any] = []
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT sender_id, MAX(sender_name) AS sender_name,
                   platform, COUNT(*) AS `count`
            FROM messages
            WHERE {where_clause}
            GROUP BY sender_id, platform
            ORDER BY `count` DESC
            LIMIT ?
        """
        params.append(limit)
        rows = self._query(sql, tuple(params))
        return [
            {
                "sender_id": row["sender_id"],
                "sender_name": row["sender_name"],
                "platform": row["platform"],
                "count": row["count"],
            }
            for row in rows
        ]

    async def get_group_ranking(
        self,
        limit: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
    ) -> List[Dict]:
        """获取群组活跃度排行（与 MySQL 一致）。"""
        return await asyncio.to_thread(
            self._get_group_ranking_thread,
            limit, start_time, end_time, platform,
        )

    def _get_group_ranking_thread(
        self,
        limit: int,
        start_time: Optional[int],
        end_time: Optional[int],
        platform: Optional[str],
    ) -> List[Dict]:
        conditions = [
            "group_id IS NOT NULL",
            "group_id != ''",
        ]
        params: List[Any] = []
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT group_id, platform, message_type, channel_id, sender_id
            FROM messages
            WHERE {where_clause}
        """
        rows = self._query(sql, tuple(params))
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for row in rows:
            bucket = _infer_message_bucket(
                row["message_type"], row["group_id"], row["channel_id"]
            )
            if bucket not in {"group", "channel"}:
                continue
            key = (row["group_id"], row["platform"])
            item = grouped.setdefault(
                key,
                {
                    "group_id": row["group_id"],
                    "platform": row["platform"],
                    "count": 0,
                    "senders": set(),
                },
            )
            item["count"] += 1
            if row["sender_id"]:
                item["senders"].add(row["sender_id"])
        ranking = []
        for item in grouped.values():
            ranking.append(
                {
                    "group_id": item["group_id"],
                    "platform": item["platform"],
                    "count": item["count"],
                    "sender_count": len(item["senders"]),
                }
            )
        ranking.sort(key=lambda item: item["count"], reverse=True)
        return ranking[:limit]

    # ---- 去重 / 列表 ----

    async def get_distinct_platforms(self) -> List[str]:
        rows = await asyncio.to_thread(
            self._query,
            "SELECT DISTINCT platform FROM messages ORDER BY platform",
        )
        return [row["platform"] for row in rows]

    async def get_distinct_senders(
        self,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        conditions = []
        params: List[Any] = []
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            f"SELECT DISTINCT sender_id, sender_name, platform "
            f"FROM messages WHERE {where_clause} "
            f"ORDER BY sender_name, sender_id LIMIT ?"
        )
        params.append(limit)
        rows = await asyncio.to_thread(self._query, sql, tuple(params))
        return [
            {"id": row["sender_id"], "name": row["sender_name"] or row["sender_id"], "platform": row["platform"]}
            for row in rows
        ]

    async def get_distinct_groups(
        self,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        conditions = [
            "message_type IN ('group', 'channel')",
            "group_id IS NOT NULL",
        ]
        params: List[Any] = []
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        where_clause = " AND ".join(conditions)
        sql = (
            f"SELECT DISTINCT group_id, platform "
            f"FROM messages WHERE {where_clause} "
            f"ORDER BY group_id LIMIT ?"
        )
        params.append(limit)
        rows = await asyncio.to_thread(self._query, sql, tuple(params))
        return [{"id": row["group_id"], "platform": row["platform"]} for row in rows]

    # ---- 媒体路径 ----

    async def get_media_paths_before(self, cutoff_timestamp: int) -> List[str]:
        rows = await asyncio.to_thread(
            self._query,
            "SELECT message_chain FROM messages "
            "WHERE timestamp < ? AND message_chain IS NOT NULL",
            (cutoff_timestamp,),
        )
        paths = []
        for row in rows:
            paths.extend(extract_media_paths(row["message_chain"]))
        return paths

    async def get_media_paths_over_limit(self, max_records: int) -> List[str]:
        def _run():
            total_row = self._query_one("SELECT COUNT(*) AS c FROM messages")
            current_count = int(total_row["c"]) if total_row else 0
            if current_count <= max_records:
                return []
            delete_count = current_count - max_records
            rows = self._query(
                "SELECT message_chain FROM messages "
                "WHERE message_chain IS NOT NULL "
                "ORDER BY timestamp ASC LIMIT ?",
                (delete_count,),
            )
            paths = []
            for row in rows:
                paths.extend(extract_media_paths(row["message_chain"]))
            return paths

        return await asyncio.to_thread(_run)

    async def get_unreferenced_media_paths(
        self, candidates: List[str]
    ) -> List[str]:
        """从候选路径中筛除仍被引用的，返回可安全删除的路径。"""
        if not candidates:
            return []
        return await asyncio.to_thread(
            self._get_unreferenced_media_paths_thread, candidates
        )

    def _get_unreferenced_media_paths_thread(self, candidates: List[str]) -> List[str]:
        BATCH_SIZE = 50
        unreferenced = []
        for i in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[i:i + BATCH_SIZE]
            conditions = []
            params = []
            for path in batch:
                escaped = _escape_like(path)
                conditions.append("message_chain LIKE ? ESCAPE '\\'")
                params.append(f"%{escaped}%")
            where_clause = " OR ".join(conditions)
            sql = f"SELECT message_chain FROM messages WHERE {where_clause}"
            rows = self._query(sql, tuple(params))
            referenced = set()
            for row in rows:
                referenced.update(extract_media_paths(row["message_chain"]))
            for path in batch:
                if path in referenced:
                    continue
                escaped = _escape_like(path)
                probe = self._query_one(
                    "SELECT 1 AS one FROM messages "
                    "WHERE message_chain LIKE ? ESCAPE '\\' LIMIT 1",
                    (f"%{escaped}%",),
                )
                if not probe:
                    unreferenced.append(path)
        return unreferenced

    # ---- 清理 ----

    async def cleanup_by_age(self, retention_days: int) -> tuple:
        """清理超过保留天数的消息，返回 (删除数量, 媒体路径列表)。

        降级期间仅清理【已同步】记录（synced=1）：未同步（synced=0）
        的消息尚未补写进 MySQL，必须保留防止数据丢失。
        """
        if retention_days <= 0:
            return 0, []
        cutoff_time = int((time.time() - retention_days * 86400) * 1000)
        return await asyncio.to_thread(self._cleanup_by_age_thread, cutoff_time)

    def _cleanup_by_age_thread(self, cutoff_time: int) -> Tuple[int, List[str]]:
        with self._write_lock:
            with self._connect() as conn:
                media_paths: List[str] = []
                last_id = 0
                while True:
                    rows = conn.execute(
                        "SELECT id, message_chain FROM messages "
                        "WHERE id > ? AND timestamp < ? "
                        "AND synced = 1 AND message_chain IS NOT NULL "
                        "ORDER BY id ASC LIMIT 500",
                        (last_id, cutoff_time),
                    ).fetchall()
                    if not rows:
                        break
                    for row in rows:
                        media_paths.extend(extract_media_paths(row["message_chain"]))
                    last_id = rows[-1]["id"]
                cur = conn.execute(
                    "DELETE FROM messages "
                    "WHERE timestamp < ? AND synced = 1",
                    (cutoff_time,),
                )
                conn.commit()
                return cur.rowcount, media_paths

    async def cleanup_by_limit(self, max_records: int) -> tuple:
        """清理超出数量限制的旧消息，返回 (删除数量, 媒体路径列表)。

        仅清理【已同步】记录（synced=1），未同步消息保留待补写。
        """
        if max_records <= 0:
            return 0, []
        return await asyncio.to_thread(self._cleanup_by_limit_thread, max_records)

    def _cleanup_by_limit_thread(self, max_records: int) -> Tuple[int, List[str]]:
        with self._write_lock:
            with self._connect() as conn:
                total_row = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()
                current_count = int(total_row["c"]) if total_row else 0
                if current_count <= max_records:
                    return 0, []
                delete_count = current_count - max_records
                media_paths: List[str] = []
                rows = conn.execute(
                    "SELECT id, message_chain FROM messages "
                    "WHERE message_chain IS NOT NULL AND synced = 1 "
                    "ORDER BY id ASC LIMIT ?",
                    (delete_count,),
                ).fetchall()
                for row in rows:
                    media_paths.extend(extract_media_paths(row["message_chain"]))
                old_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM messages "
                        "WHERE synced = 1 ORDER BY id ASC LIMIT ?",
                        (delete_count,),
                    ).fetchall()
                ]
                if not old_ids:
                    return 0, []
                placeholders = ",".join(["?"] * len(old_ids))
                cur = conn.execute(
                    f"DELETE FROM messages WHERE id IN ({placeholders})",
                    tuple(old_ids),
                )
                conn.commit()
                return cur.rowcount, media_paths

    # ---- 补写支持 ----

    async def get_unsynced_ids(self, batch_size: int = 500) -> List[int]:
        """获取未同步（synced=0）的消息 ID 列表。"""
        return await asyncio.to_thread(self._get_unsynced_ids_thread, batch_size)

    def _get_unsynced_ids_thread(self, batch_size: int) -> List[int]:
        rows = self._query(
            "SELECT id FROM messages WHERE synced = 0 ORDER BY id ASC LIMIT ?",
            (batch_size,),
        )
        return [row["id"] for row in rows]

    async def get_unsynced_count(self) -> int:
        row = await asyncio.to_thread(
            self._query_one,
            "SELECT COUNT(*) AS c FROM messages WHERE synced = 0",
        )
        return int(row["c"]) if row else 0

    async def get_records_by_ids(self, ids: List[int]) -> List[MessageRecord]:
        """按 ID 批量读取完整消息记录（供补写使用）。"""
        if not ids:
            return []
        return await asyncio.to_thread(self._get_records_by_ids_thread, ids)

    def _get_records_by_ids_thread(self, ids: List[int]) -> List[MessageRecord]:
        placeholders = ",".join(["?"] * len(ids))
        sql = (
            f"SELECT {_SELECT_COLUMNS} FROM messages "
            f"WHERE id IN ({placeholders}) ORDER BY id ASC"
        )
        rows = self._query(sql, tuple(ids))
        return [_row_to_record(row) for row in rows]

    async def mark_synced(self, ids: List[int]) -> int:
        """将指定消息标记为已同步（synced=1），返回更新的行数。"""
        if not ids:
            return 0
        return await asyncio.to_thread(self._mark_synced_thread, ids)

    def _mark_synced_thread(self, ids: List[int]) -> int:
        placeholders = ",".join(["?"] * len(ids))
        return self._execute(
            f"UPDATE messages SET synced = 1 WHERE id IN ({placeholders})",
            tuple(ids),
        )

    async def cleanup_synced(self, retention_days: int) -> int:
        """清理 SQLite 中已同步且超过保留期的记录，返回删除数量。"""
        if retention_days <= 0:
            return 0
        cutoff = int((time.time() - retention_days * 86400) * 1000)
        return await asyncio.to_thread(
            self._execute,
            "DELETE FROM messages WHERE synced = 1 AND created_at < ?",
            (cutoff,),
        )
