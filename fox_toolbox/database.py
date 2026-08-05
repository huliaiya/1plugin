"""MySQL 5.7 数据库操作模块"""

import asyncio
import aiomysql
import json
import time
from typing import Optional, List, Dict, Any, AsyncGenerator

from astrbot.api import logger

from .models import MessageRecord, QueryFilter, MessageStats, SCHEMA_VERSION, DEPRECATED_TABLES
from .time_utils import parse_time_range
from .serializer import compute_content_hash, extract_media_paths


_SELECT_COLUMNS = """
    id, platform, message_id, session_id, group_id, channel_id,
    sender_id, sender_name, message_type,
    message_str, message_chain, raw_message,
    reply_to_id, content_hash, content_types, timestamp, created_at
"""


def _row_to_record(row) -> MessageRecord:
    return MessageRecord(
        id=row[0],
        platform=row[1],
        message_id=row[2] or "",
        session_id=row[3] or "",
        group_id=row[4],
        channel_id=row[5],
        sender_id=row[6],
        sender_name=row[7],
        message_type=row[8],
        message_str=row[9],
        message_chain=row[10],
        raw_message=row[11],
        reply_to_id=row[12],
        content_hash=row[13],
        content_types=row[14],
        timestamp=row[15],
        created_at=row[16],
    )


class Database:
    """MySQL 数据库管理类（兼容 MySQL 5.7）"""

    def __init__(self, plugin_name: str, mysql_config: dict):
        self.plugin_name = plugin_name
        self.mysql_config = mysql_config
        self._pool: Optional[aiomysql.Pool] = None
        self._write_lock = asyncio.Lock()
        self._fts_available_cache: Optional[bool] = None

    async def init(self) -> None:
        """初始化数据库连接池和表结构"""
        host = self.mysql_config.get("host", "127.0.0.1")
        port = int(self.mysql_config.get("port", 3306))
        user = self.mysql_config.get("user", "root")
        password = self.mysql_config.get("password", "")
        database = self.mysql_config.get("database", "fox_toolbox")

        self._pool = await aiomysql.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            db=database,
            charset="utf8mb4",
            autocommit=False,
            minsize=1,
            maxsize=10,
        )

        await self._create_tables()
        await self._ensure_schema_version()
        await self._cleanup_deprecated_tables()
        logger.info(
            f"[FoxToolbox] MySQL 数据库初始化完成: "
            f"{host}:{port}/{database}"
        )

    async def close(self) -> None:
        """关闭数据库连接池"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            logger.info("[FoxToolbox] MySQL 连接池已关闭")

    async def ping(self) -> bool:
        """轻量数据库连通性检测（供 WebUI 状态卡片使用）"""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()
            return True
        except Exception as e:
            logger.warning(f"[FoxToolbox] 数据库 ping 失败: {e}")
            return False

    async def get_table_count(self) -> int:
        """返回当前数据库内已创建的数据表数量。"""
        if not self._pool:
            return 0
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SHOW TABLES")
                    rows = await cur.fetchall()
            return len(rows or [])
        except Exception as e:
            logger.warning(f"[FoxToolbox] 获取数据表数量失败: {e}")
            return 0

    async def _create_tables(self) -> None:
        """创建数据表和索引"""
        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute("""
                            CREATE TABLE IF NOT EXISTS messages (
                                id INT PRIMARY KEY AUTO_INCREMENT,
                                platform VARCHAR(64) NOT NULL,
                                message_id VARCHAR(128) DEFAULT NULL,
                                session_id VARCHAR(128) DEFAULT NULL,
                                group_id VARCHAR(128) DEFAULT NULL,
                                channel_id VARCHAR(128) DEFAULT NULL,
                                sender_id VARCHAR(128) NOT NULL,
                                sender_name VARCHAR(256) DEFAULT NULL,
                                message_type VARCHAR(32) NOT NULL,
                                message_str MEDIUMTEXT,
                                message_chain LONGTEXT,
                                raw_message LONGTEXT,
                                reply_to_id VARCHAR(128) DEFAULT NULL,
                                content_hash VARCHAR(64) DEFAULT NULL,
                                content_types VARCHAR(256) DEFAULT NULL,
                                timestamp BIGINT NOT NULL,
                                created_at BIGINT NOT NULL,
                                INDEX idx_platform (platform),
                                INDEX idx_sender_id (sender_id),
                                INDEX idx_group_id (group_id),
                                INDEX idx_timestamp (timestamp),
                                INDEX idx_session_id (session_id),
                                INDEX idx_channel_id (channel_id),
                                INDEX idx_content_hash (content_hash),
                                INDEX idx_reply_to_id (reply_to_id),
                                UNIQUE INDEX idx_platform_message_id_unique (platform, message_id),
                                UNIQUE INDEX idx_platform_content_hash_unique (platform, content_hash),
                                INDEX idx_platform_group_timestamp (platform, group_id, timestamp),
                                INDEX idx_platform_sender_timestamp (platform, sender_id, timestamp),
                                INDEX idx_type_timestamp (message_type, timestamp)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """)
                        await self._ensure_fts(cur)
                        await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise

    async def _ensure_fts(self, cur) -> None:
        """确保 FULLTEXT 全文搜索索引存在（MySQL 5.7 ngram 分词器，支持中文）"""
        await cur.execute("""
            SELECT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'messages'
              AND INDEX_NAME = 'idx_message_str_fts'
        """)
        if not await cur.fetchone():
            try:
                await cur.execute(
                    "CREATE FULLTEXT INDEX idx_message_str_fts "
                    "ON messages(message_str) WITH PARSER ngram"
                )
                logger.info("[FoxToolbox] 已创建 FULLTEXT 全文搜索索引 (ngram)")
            except Exception as e:
                logger.warning(
                    f"[FoxToolbox] 创建 FULLTEXT 索引失败: {e}"
                )

    async def _ensure_schema_version(self) -> None:
        """检查并执行 schema 迁移"""
        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute("""
                            CREATE TABLE IF NOT EXISTS _schema_meta (
                                `key` VARCHAR(64) PRIMARY KEY,
                                `value` VARCHAR(255) NOT NULL
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """)
                        await cur.execute(
                            "SELECT `value` FROM _schema_meta WHERE `key` = 'schema_version'"
                        )
                        row = await cur.fetchone()
                        current_version = int(row[0]) if row else 0

                        if current_version < SCHEMA_VERSION:
                            for version in range(current_version + 1, SCHEMA_VERSION + 1):
                                migration = _SCHEMA_MIGRATIONS.get(version)
                                if migration:
                                    logger.info(
                                        f"[FoxToolbox] 执行 schema 迁移: "
                                        f"{current_version} → {version}"
                                    )
                                    await migration(self._pool)
                            await cur.execute(
                                "INSERT INTO _schema_meta (`key`, `value`) "
                                "VALUES ('schema_version', %s) "
                                "ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)",
                                (str(SCHEMA_VERSION),),
                            )
                            await conn.commit()
                            logger.info(
                                f"[FoxToolbox] Schema 版本已更新至 {SCHEMA_VERSION}"
                            )
                except Exception:
                    await conn.rollback()
                    raise

    async def _cleanup_deprecated_tables(self) -> None:
        """清理已弃用的表（每次启动/重载时自动执行）"""
        if not DEPRECATED_TABLES:
            return

        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute("SHOW TABLES")
                        existing_tables = {row[0] for row in await cur.fetchall()}

                        dropped = 0
                        for table in DEPRECATED_TABLES:
                            # 安全校验：表名仅允许字母、数字、下划线
                            if not all(c.isalnum() or c == "_" for c in table):
                                logger.warning(
                                    f"[FoxToolbox] 跳过非法表名: {table}"
                                )
                                continue
                            if table in existing_tables:
                                logger.info(f"[FoxToolbox] 删除已弃用表: {table}")
                                await cur.execute(f"DROP TABLE `{table}`")
                                dropped += 1

                        if dropped > 0:
                            await conn.commit()
                            logger.info(
                                f"[FoxToolbox] 已清理 {dropped} 个弃用表"
                            )
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"[FoxToolbox] 清理弃用表失败: {e}")

    async def save_message(self, record: MessageRecord) -> int:
        """保存消息记录，返回记录 ID（重复消息返回 -1）"""
        record.created_at = int(time.time() * 1000)

        if not record.content_hash:
            record.content_hash = compute_content_hash(
                record.platform, record.session_id, record.sender_id,
                record.message_str, record.timestamp,
            )

        # MySQL 唯一索引允许 NULL 但不允许空字符串重复，
        # 因此将空 message_id 转为 None
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
            record.content_hash,
            record.content_types,
            record.timestamp,
            record.created_at,
        )

        insert_sql = """
            INSERT IGNORE INTO messages (
                platform, message_id, session_id, group_id, channel_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                reply_to_id, content_hash, content_types, timestamp, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute(insert_sql, params)
                        await conn.commit()
                        if cur.rowcount > 0:
                            record_id = cur.lastrowid
                        else:
                            record_id = -1
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"[FoxToolbox] 保存消息失败: {e}")
                    raise

        if record_id == -1:
            logger.debug(
                f"[FoxToolbox] 消息已存在，跳过: "
                f"platform={record.platform}, "
                f"message_id={record.message_id or record.content_hash}"
            )

        return record_id

    async def save_messages_batch(
        self, records: List[MessageRecord]
    ) -> tuple:
        """批量保存消息记录，返回 (成功数量, 跳过数量)"""
        if not records:
            return 0, 0

        now_ms = int(time.time() * 1000)
        insert_sql = """
            INSERT IGNORE INTO messages (
                platform, message_id, session_id, group_id, channel_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                reply_to_id, content_hash, content_types, timestamp, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        saved = 0
        skipped = 0
        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        for record in records:
                            record.created_at = now_ms
                            if not record.content_hash:
                                record.content_hash = compute_content_hash(
                                    record.platform, record.session_id,
                                    record.sender_id, record.message_str,
                                    record.timestamp,
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
                                record.content_hash,
                                record.content_types,
                                record.timestamp,
                                record.created_at,
                            )
                            await cur.execute(insert_sql, params)
                            if cur.rowcount > 0:
                                saved += 1
                            else:
                                skipped += 1
                        await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"[FoxToolbox] 批量保存消息失败: {e}")
                    raise

        logger.debug(
            f"[FoxToolbox] 批量保存完成: {saved} 成功, {skipped} 跳过"
        )
        return saved, skipped

    def _build_where_clause(
        self, query_filter: QueryFilter, use_fts: bool = False
    ) -> tuple:
        """构建 WHERE 子句和参数"""
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
                conditions.append("platform = %s")
                params.append(safe_str(platforms[0]))
            else:
                conditions.append(
                    f"platform IN ({','.join(['%s'] * len(platforms))})"
                )
                params.extend([safe_str(p) for p in platforms])

        sender_ids = query_filter.get_sender_ids()
        if sender_ids:
            if len(sender_ids) == 1:
                conditions.append("sender_id = %s")
                params.append(safe_str(sender_ids[0]))
            else:
                conditions.append(
                    f"sender_id IN ({','.join(['%s'] * len(sender_ids))})"
                )
                params.extend([safe_str(s) for s in sender_ids])

        group_ids = query_filter.get_group_ids()
        if group_ids:
            if len(group_ids) == 1:
                conditions.append("group_id = %s")
                params.append(safe_str(group_ids[0]))
            else:
                conditions.append(
                    f"group_id IN ({','.join(['%s'] * len(group_ids))})"
                )
                params.extend([safe_str(g) for g in group_ids])

        session_ids = query_filter.get_session_ids()
        if session_ids:
            if len(session_ids) == 1:
                conditions.append("session_id = %s")
                params.append(safe_str(session_ids[0]))
            else:
                conditions.append(
                    f"session_id IN ({','.join(['%s'] * len(session_ids))})"
                )
                params.extend([safe_str(s) for s in session_ids])

        if query_filter.channel_id:
            conditions.append("channel_id = %s")
            params.append(safe_str(query_filter.channel_id))

        if query_filter.message_type:
            conditions.append("message_type = %s")
            params.append(safe_str(query_filter.message_type))

        if query_filter.reply_to_id:
            conditions.append("reply_to_id = %s")
            params.append(safe_str(query_filter.reply_to_id))

        if query_filter.time:
            start_time, end_time = parse_time_range(query_filter.time)
            conditions.append("timestamp >= %s")
            params.append(safe_int(start_time))
            conditions.append("timestamp <= %s")
            params.append(safe_int(end_time))
        else:
            if query_filter.start_time is not None:
                conditions.append("timestamp >= %s")
                params.append(safe_int(query_filter.start_time))
            if query_filter.end_time is not None:
                conditions.append("timestamp <= %s")
                params.append(safe_int(query_filter.end_time))

        if query_filter.keyword:
            if use_fts:
                conditions.append(
                    "MATCH(message_str) AGAINST(%s IN BOOLEAN MODE)"
                )
                params.append(query_filter.keyword)
            else:
                escaped = (
                    safe_str(query_filter.keyword)
                    .replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                conditions.append("message_str LIKE %s")
                params.append(f"%{escaped}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    async def _fts_available(self) -> bool:
        """检查 FULLTEXT 索引是否可用（结果缓存）"""
        if self._fts_available_cache is not None:
            return self._fts_available_cache
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        SELECT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                          AND TABLE_NAME = 'messages'
                          AND INDEX_NAME = 'idx_message_str_fts'
                    """)
                    self._fts_available_cache = (
                        await cur.fetchone() is not None
                    )
        except Exception:
            self._fts_available_cache = False
        return self._fts_available_cache

    async def query_messages(self, query_filter: QueryFilter) -> List[MessageRecord]:
        """根据过滤器查询消息"""
        use_fts = (
            bool(query_filter.keyword)
            and len(query_filter.keyword) >= 2
            and await self._fts_available()
        )
        where_clause, params = self._build_where_clause(
            query_filter, use_fts=use_fts
        )
        order_clause = (
            "timestamp DESC" if query_filter.is_desc_order() else "timestamp ASC"
        )

        limit_val = query_filter.limit
        offset_val = query_filter.offset

        no_limit = limit_val is None or limit_val == -1 or limit_val == 0
        effective_limit = None if no_limit else int(limit_val)
        effective_offset = max(
            0, int(offset_val) if offset_val is not None else 0
        )

        logger.debug(
            f"[FoxToolbox] 执行查询: WHERE {where_clause}, "
            f"limit={effective_limit}, offset={effective_offset}, fts={use_fts}"
        )

        if effective_limit is not None:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """
            params.extend([effective_limit, effective_offset])
        else:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
            """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()

        records = [_row_to_record(row) for row in rows]
        logger.debug(f"[FoxToolbox] 查询返回 {len(records)} 条记录")
        return records

    async def query_messages_batch(
        self,
        query_filter: QueryFilter,
        batch_size: int = 500,
    ) -> AsyncGenerator[MessageRecord, None]:
        """分批查询消息，返回异步生成器"""
        use_fts = (
            bool(query_filter.keyword)
            and len(query_filter.keyword) >= 2
            and await self._fts_available()
        )
        where_clause, params = self._build_where_clause(
            query_filter, use_fts=use_fts
        )
        order_clause = (
            "timestamp DESC" if query_filter.is_desc_order() else "timestamp ASC"
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
                LIMIT %s OFFSET %s
            """
            batch_params = params + [current_batch_size, current_offset]

            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, batch_params)
                    rows = await cur.fetchall()

            if not rows:
                break

            for row in rows:
                yield _row_to_record(row)
                total_fetched += 1

            if len(rows) < current_batch_size:
                break
            current_offset += batch_size

    async def get_message_by_id(self, message_id: int) -> Optional[MessageRecord]:
        """根据数据库 ID 获取单条消息"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_SELECT_COLUMNS} FROM messages WHERE id = %s",
                    (message_id,),
                )
                row = await cur.fetchone()
        return _row_to_record(row) if row else None

    async def get_message_by_platform_id(
        self,
        platform_message_id: str,
        platform: Optional[str] = None,
    ) -> Optional[MessageRecord]:
        """根据平台原始消息 ID 获取消息"""
        if platform:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE message_id = %s AND platform = %s
                ORDER BY timestamp DESC LIMIT 1
            """
            params = (platform_message_id, platform)
        else:
            sql = f"""
                SELECT {_SELECT_COLUMNS}
                FROM messages
                WHERE message_id = %s
                ORDER BY timestamp DESC LIMIT 1
            """
            params = (platform_message_id,)

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
        return _row_to_record(row) if row else None

    async def get_existing_message_ids(
        self, message_ids: List[str], platform: str
    ) -> set:
        """批量查询已存在的消息ID"""
        if not message_ids:
            return set()
        placeholders = ",".join(["%s"] * len(message_ids))
        sql = f"""
            SELECT message_id FROM messages
            WHERE message_id IN ({placeholders}) AND platform = %s
        """
        params = list(message_ids) + [platform]
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return {row[0] for row in rows}

    async def get_context_messages(
        self,
        message_id: int,
        before: int = 5,
        after: int = 5,
    ) -> Dict[str, List[MessageRecord]]:
        """获取某条消息的上下文消息"""
        target = await self.get_message_by_id(message_id)
        if not target:
            return {"before": [], "after": []}

        if target.message_type == "channel" and target.channel_id:
            scope_conditions = (
                "platform = %s AND channel_id = %s "
                "AND message_type = 'channel'"
            )
            scope_params = [target.platform, target.channel_id]
        elif target.message_type == "group" and target.group_id:
            scope_conditions = (
                "platform = %s AND group_id = %s "
                "AND message_type = 'group'"
            )
            scope_params = [target.platform, target.group_id]
        elif target.session_id and target.session_id.strip():
            scope_conditions = "session_id = %s"
            scope_params = [target.session_id]
        else:
            scope_conditions = (
                "platform = %s AND sender_id = %s "
                "AND message_type = 'private'"
            )
            scope_params = [target.platform, target.sender_id]

        before_sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM messages
            WHERE {scope_conditions} AND timestamp < %s
            ORDER BY timestamp DESC LIMIT %s
        """
        before_params = scope_params + [target.timestamp, before]

        after_sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM messages
            WHERE {scope_conditions} AND timestamp > %s
            ORDER BY timestamp ASC LIMIT %s
        """
        after_params = scope_params + [target.timestamp, after]

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(before_sql, before_params)
                before_rows = await cur.fetchall()

                await cur.execute(after_sql, after_params)
                after_rows = await cur.fetchall()

        before_msgs = [_row_to_record(row) for row in reversed(before_rows)]
        after_msgs = [_row_to_record(row) for row in after_rows]

        return {"before": before_msgs, "after": after_msgs}

    async def count_messages(self, query_filter: QueryFilter) -> int:
        """统计符合条件的消息数量"""
        use_fts = (
            bool(query_filter.keyword)
            and len(query_filter.keyword) >= 2
            and await self._fts_available()
        )
        where_clause, params = self._build_where_clause(
            query_filter, use_fts=use_fts
        )

        sql = f"SELECT COUNT(*) FROM messages WHERE {where_clause}"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                result = await cur.fetchone()
        count = result[0] if result else 0

        logger.debug(f"[FoxToolbox] 统计结果: {count} 条")
        return count

    async def get_stats(self) -> MessageStats:
        """获取消息统计信息"""
        stats = MessageStats()

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN message_type = 'group'
                            THEN 1 ELSE 0 END),
                        SUM(CASE WHEN message_type = 'private'
                            THEN 1 ELSE 0 END),
                        SUM(CASE WHEN message_type = 'channel'
                            THEN 1 ELSE 0 END),
                        MIN(timestamp),
                        MAX(timestamp),
                        MIN(created_at),
                        MAX(created_at)
                    FROM messages
                """)
                row = await cur.fetchone()
                if row and row[0]:
                    stats.total_count = row[0]
                    stats.group_message_count = row[1] or 0
                    stats.private_message_count = row[2] or 0
                    stats.channel_message_count = row[3] or 0
                    stats.oldest_timestamp = row[4]
                    stats.newest_timestamp = row[5]
                    stats.first_record_time = row[6]
                    stats.last_record_time = row[7]

                await cur.execute(
                    "SELECT platform, COUNT(*) FROM messages "
                    "GROUP BY platform"
                )
                rows = await cur.fetchall()
                stats.platform_stats = {row[0]: row[1] for row in rows}

        return stats

    async def get_content_type_stats(self) -> List[Dict]:
        """获取消息内容类型统计（文字/图片/文件/视频/语音/文档/音频/压缩包等）"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # content_types 存储逗号分隔的组件类型，如 "Plain,Image" 或 "FileDocument"
                # 使用 FIND_IN_SET 精确匹配逗号分隔值，避免 LIKE '%Image%' 误匹配 FileImage
                await cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN FIND_IN_SET('Plain', content_types) > 0 THEN 1 ELSE 0 END) AS text_count,
                        SUM(CASE WHEN FIND_IN_SET('Image', content_types) > 0 THEN 1 ELSE 0 END) AS image_count,
                        SUM(CASE WHEN FIND_IN_SET('Video', content_types) > 0 THEN 1 ELSE 0 END) AS video_count,
                        SUM(CASE WHEN FIND_IN_SET('Record', content_types) > 0 THEN 1 ELSE 0 END) AS voice_count,
                        SUM(CASE WHEN FIND_IN_SET('FileDocument', content_types) > 0 THEN 1 ELSE 0 END) AS document_count,
                        SUM(CASE WHEN FIND_IN_SET('FileAudio', content_types) > 0 THEN 1 ELSE 0 END) AS audio_count,
                        SUM(CASE WHEN FIND_IN_SET('FileArchive', content_types) > 0 THEN 1 ELSE 0 END) AS archive_count,
                        SUM(CASE WHEN FIND_IN_SET('FileCode', content_types) > 0 THEN 1 ELSE 0 END) AS code_count,
                        SUM(CASE WHEN FIND_IN_SET('FileImage', content_types) > 0 THEN 1 ELSE 0 END) AS file_image_count,
                        SUM(CASE WHEN FIND_IN_SET('FileVideo', content_types) > 0 THEN 1 ELSE 0 END) AS file_video_count,
                        SUM(CASE WHEN FIND_IN_SET('File', content_types) > 0 THEN 1 ELSE 0 END) AS other_file_count,
                        SUM(CASE WHEN FIND_IN_SET('At', content_types) > 0 OR FIND_IN_SET('AtAll', content_types) > 0 THEN 1 ELSE 0 END) AS at_count,
                        SUM(CASE WHEN FIND_IN_SET('Reply', content_types) > 0 THEN 1 ELSE 0 END) AS reply_count,
                        SUM(CASE WHEN FIND_IN_SET('Face', content_types) > 0 THEN 1 ELSE 0 END) AS face_count,
                        SUM(CASE WHEN FIND_IN_SET('Json', content_types) > 0 OR FIND_IN_SET('Xml', content_types) > 0 OR FIND_IN_SET('Card', content_types) > 0 THEN 1 ELSE 0 END) AS rich_count,
                        SUM(CASE WHEN content_types IS NULL OR content_types = '' THEN 1 ELSE 0 END) AS unknown_count
                    FROM messages
                """)
                row = await cur.fetchone()

        if not row:
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
            "document", "audio", "archive", "code", "file_image", "file_video", "other_file",
            "at", "reply", "face", "rich", "unknown",
        ]

        result = []
        for i, key in enumerate(keys):
            count = row[i + 1] or 0
            if count > 0:
                result.append({
                    "type": key,
                    "label": labels[key],
                    "count": count,
                })

        result.sort(key=lambda x: x["count"], reverse=True)
        return result

    async def get_platform_detail_stats(self) -> List[Dict]:
        """获取各平台的详细统计（消息数、群聊数、私聊数等）"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 使用 FIND_IN_SET 精确匹配，避免 LIKE '%Image%' 误匹配 FileImage
                await cur.execute("""
                    SELECT
                        platform,
                        COUNT(*) AS total,
                        SUM(CASE WHEN message_type = 'group' THEN 1 ELSE 0 END) AS group_count,
                        SUM(CASE WHEN message_type = 'private' THEN 1 ELSE 0 END) AS private_count,
                        SUM(CASE WHEN message_type = 'channel' THEN 1 ELSE 0 END) AS channel_count,
                        SUM(CASE WHEN FIND_IN_SET('Image', content_types) > 0 THEN 1 ELSE 0 END) AS image_count,
                        SUM(CASE WHEN FIND_IN_SET('Video', content_types) > 0 THEN 1 ELSE 0 END) AS video_count,
                        SUM(CASE WHEN FIND_IN_SET('Record', content_types) > 0 THEN 1 ELSE 0 END) AS voice_count,
                        SUM(CASE WHEN FIND_IN_SET('FileDocument', content_types) > 0 THEN 1 ELSE 0 END) AS document_count,
                        SUM(CASE WHEN FIND_IN_SET('FileAudio', content_types) > 0 THEN 1 ELSE 0 END) AS audio_count,
                        SUM(CASE WHEN FIND_IN_SET('FileArchive', content_types) > 0 THEN 1 ELSE 0 END) AS archive_count,
                        SUM(CASE WHEN FIND_IN_SET('FileCode', content_types) > 0 THEN 1 ELSE 0 END) AS code_count,
                        SUM(CASE WHEN FIND_IN_SET('File', content_types) > 0 THEN 1 ELSE 0 END) AS other_file_count,
                        MIN(timestamp) AS oldest,
                        MAX(timestamp) AS newest
                    FROM messages
                    GROUP BY platform
                    ORDER BY total DESC
                """)
                rows = await cur.fetchall()

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

        result = []
        for row in rows:
            result.append({
                "platform": row[0],
                "platform_name": platform_names.get(row[0], row[0]),
                "total": row[1],
                "group_count": row[2] or 0,
                "private_count": row[3] or 0,
                "channel_count": row[4] or 0,
                "image_count": row[5] or 0,
                "video_count": row[6] or 0,
                "voice_count": row[7] or 0,
                "document_count": row[8] or 0,
                "audio_count": row[9] or 0,
                "archive_count": row[10] or 0,
                "code_count": row[11] or 0,
                "other_file_count": row[12] or 0,
                "oldest_timestamp": row[13],
                "newest_timestamp": row[14],
            })
        return result

    async def cleanup_by_age(self, retention_days: int) -> tuple:
        """清理超过保留天数的消息，返回 (删除数量, 被删记录的媒体路径列表)"""
        if retention_days <= 0:
            return 0, []
        cutoff_time = int(
            (time.time() - retention_days * 86400) * 1000
        )
        try:
            media_paths: List[str] = []
            async with self._write_lock:
                async with self._pool.acquire() as conn:
                    try:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "SELECT message_chain FROM messages "
                                "WHERE timestamp < %s "
                                "AND message_chain IS NOT NULL",
                                (cutoff_time,),
                            )
                            while True:
                                rows = await cur.fetchmany(500)
                                if not rows:
                                    break
                                for row in rows:
                                    media_paths.extend(
                                        extract_media_paths(row[0])
                                    )

                            await cur.execute(
                                "DELETE FROM messages WHERE timestamp < %s",
                                (cutoff_time,),
                            )
                            await conn.commit()
                            rowcount = cur.rowcount
                    except Exception:
                        await conn.rollback()
                        raise
            return rowcount, media_paths
        except aiomysql.Error as e:
            logger.error(f"[FoxToolbox] 按时间清理失败: {e}")
            return 0, []

    async def cleanup_by_limit(self, max_records: int) -> tuple:
        """清理超出数量限制的旧消息，返回 (删除数量, 被删记录的媒体路径列表)"""
        if max_records <= 0:
            return 0, []
        media_paths: List[str] = []
        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT COUNT(*) FROM messages")
                        result = await cur.fetchone()
                        current_count = result[0] if result else 0
                        if current_count <= max_records:
                            return 0, []
                        delete_count = current_count - max_records

                        await cur.execute(
                            "SELECT message_chain FROM messages "
                            "WHERE message_chain IS NOT NULL "
                            "ORDER BY timestamp ASC LIMIT %s",
                            (delete_count,),
                        )
                        while True:
                            rows = await cur.fetchmany(500)
                            if not rows:
                                break
                            for row in rows:
                                media_paths.extend(
                                    extract_media_paths(row[0])
                                )

                        await cur.execute(
                            "DELETE FROM messages "
                            "ORDER BY timestamp ASC LIMIT %s",
                            (delete_count,),
                        )
                        await conn.commit()
                        rowcount = cur.rowcount
                except Exception:
                    await conn.rollback()
                    raise
        return rowcount, media_paths

    async def get_timeline_stats(
        self,
        interval: str = "day",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict]:
        """按时间间隔统计消息数量（Python 端分组，彻底兼容 MySQL 5.7）"""
        conditions = []
        params: List[Any] = []
        if start_time:
            conditions.append("`timestamp` >= %s")
            params.append(start_time)
        if end_time:
            conditions.append("`timestamp` <= %s")
            params.append(end_time)
        if platform:
            conditions.append("platform = %s")
            params.append(platform)
        if group_id:
            conditions.append("group_id = %s")
            params.append(group_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT `timestamp`, `message_type`
            FROM messages
            WHERE {where_clause}
        """
        from collections import OrderedDict
        from datetime import datetime as _dt

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()

        groups: "OrderedDict[str, Dict]" = OrderedDict()
        for row in rows:
            ts_ms = row[0]
            msg_type = row[1] or ""
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
            if msg_type == "group":
                groups[key]["group_count"] += 1
            elif msg_type == "private":
                groups[key]["private_count"] += 1
            elif msg_type == "channel":
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
        """获取发送者排行榜"""
        conditions = []
        params: List[Any] = []
        if start_time:
            conditions.append("timestamp >= %s")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= %s")
            params.append(end_time)
        if platform:
            conditions.append("platform = %s")
            params.append(platform)
        if group_id:
            conditions.append("group_id = %s")
            params.append(group_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT sender_id, ANY_VALUE(sender_name) AS sender_name,
                   platform, COUNT(*) AS `count`
            FROM messages
            WHERE {where_clause}
            GROUP BY sender_id, platform
            ORDER BY `count` DESC
            LIMIT %s
        """
        params.append(limit)
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [
            {
                "sender_id": row[0],
                "sender_name": row[1],
                "platform": row[2],
                "count": row[3],
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
        """获取群组活跃度排行"""
        conditions = [
            "message_type IN ('group', 'channel')",
            "group_id IS NOT NULL",
        ]
        params: List[Any] = []
        if start_time:
            conditions.append("timestamp >= %s")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= %s")
            params.append(end_time)
        if platform:
            conditions.append("platform = %s")
            params.append(platform)

        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT group_id, platform, COUNT(*) AS `count`,
                   COUNT(DISTINCT sender_id) AS sender_count
            FROM messages
            WHERE {where_clause}
            GROUP BY group_id, platform
            ORDER BY `count` DESC
            LIMIT %s
        """
        params.append(limit)
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [
            {
                "group_id": row[0],
                "platform": row[1],
                "count": row[2],
                "sender_count": row[3],
            }
            for row in rows
        ]

    async def get_distinct_platforms(self) -> List[str]:
        """获取所有平台列表"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT DISTINCT platform FROM messages "
                    "ORDER BY platform"
                )
                rows = await cur.fetchall()
        return [row[0] for row in rows]

    async def get_distinct_senders(
        self,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """获取发送者列表"""
        conditions = []
        params: List[Any] = []
        if platform:
            conditions.append("platform = %s")
            params.append(platform)
        if group_id:
            conditions.append("group_id = %s")
            params.append(group_id)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT DISTINCT sender_id, sender_name, platform
            FROM messages WHERE {where_clause}
            ORDER BY sender_name, sender_id LIMIT %s
        """
        params.append(limit)
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [
            {"id": row[0], "name": row[1] or row[0], "platform": row[2]}
            for row in rows
        ]

    async def get_distinct_groups(
        self,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """获取群组列表"""
        conditions = [
            "message_type IN ('group', 'channel')",
            "group_id IS NOT NULL",
        ]
        params: List[Any] = []
        if platform:
            conditions.append("platform = %s")
            params.append(platform)
        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT DISTINCT group_id, platform
            FROM messages WHERE {where_clause}
            ORDER BY group_id LIMIT %s
        """
        params.append(limit)
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [{"id": row[0], "platform": row[1]} for row in rows]

    async def get_media_paths_before(
        self, cutoff_timestamp: int
    ) -> List[str]:
        """获取指定时间戳之前的消息中包含的媒体文件路径"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT message_chain FROM messages "
                    "WHERE timestamp < %s "
                    "AND message_chain IS NOT NULL",
                    (cutoff_timestamp,),
                )
                rows = await cur.fetchall()
        paths = []
        for row in rows:
            paths.extend(extract_media_paths(row[0]))
        return paths

    async def get_media_paths_over_limit(
        self, max_records: int
    ) -> List[str]:
        """获取超出数量限制的旧消息中包含的媒体文件路径"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM messages")
                result = await cur.fetchone()
                current_count = result[0] if result else 0
                if current_count <= max_records:
                    return []
                delete_count = current_count - max_records
                await cur.execute(
                    "SELECT message_chain FROM messages "
                    "WHERE message_chain IS NOT NULL "
                    "ORDER BY timestamp ASC LIMIT %s",
                    (delete_count,),
                )
                rows = await cur.fetchall()
        paths = []
        for row in rows:
            paths.extend(extract_media_paths(row[0]))
        return paths

    async def get_unreferenced_media_paths(
        self, candidates: List[str]
    ) -> List[str]:
        """从候选路径中筛除仍被数据库引用的，返回可安全删除的路径。

        优化：使用批量 OR 查询替代逐条查询，减少 N+1 问题。
        """
        if not candidates:
            return []

        BATCH_SIZE = 50
        unreferenced = []

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                for i in range(0, len(candidates), BATCH_SIZE):
                    batch = candidates[i:i + BATCH_SIZE]
                    conditions = []
                    params = []
                    for path in batch:
                        escaped = (
                            path.replace("\\", "\\\\")
                            .replace("%", "\\%")
                            .replace("_", "\\_")
                        )
                        conditions.append("message_chain LIKE %s")
                        params.append(f"%{escaped}%")

                    where_clause = " OR ".join(conditions)
                    sql = (
                        f"SELECT message_chain FROM messages "
                        f"WHERE {where_clause}"
                    )
                    await cur.execute(sql, params)
                    rows = await cur.fetchall()

                    # 提取所有匹配消息中的实际媒体路径
                    referenced = set()
                    for row in rows:
                        referenced.update(extract_media_paths(row[0]))

                    # 对批量查询未找到的路径，回退到精确 LIKE 检查
                    for path in batch:
                        if path in referenced:
                            continue
                        escaped = (
                            path.replace("\\", "\\\\")
                            .replace("%", "\\%")
                            .replace("_", "\\_")
                        )
                        await cur.execute(
                            "SELECT 1 FROM messages "
                            "WHERE message_chain LIKE %s LIMIT 1",
                            (f"%{escaped}%",),
                        )
                        if not await cur.fetchone():
                            unreferenced.append(path)

        return unreferenced


# Schema 迁移注册表：version -> async migration function
# 每个迁移函数接收 aiomysql.Pool 参数


async def _migrate_v3(pool: aiomysql.Pool) -> None:
    """v2 → v3: 添加 content_types 列"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "ALTER TABLE messages ADD COLUMN content_types VARCHAR(256) DEFAULT NULL "
                "AFTER content_hash"
            )
            await cur.execute(
                "ALTER TABLE messages ADD INDEX idx_content_types (content_types)"
            )
            await conn.commit()


_SCHEMA_MIGRATIONS: Dict[int, Any] = {
    3: _migrate_v3,
}
