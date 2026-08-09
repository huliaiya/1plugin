"""MySQL 5.7 数据库操作模块（MySQL 优先 + SQLite 自动兜底）"""

import asyncio
import aiomysql
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator, TYPE_CHECKING

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .models import (
    MessageRecord, QueryFilter, MessageStats, SCHEMA_VERSION,
    DEPRECATED_TABLES, PLUGIN_DIR_NAME,
)
from .time_utils import parse_time_range
from .serializer import compute_content_hash, extract_media_paths
from .sqlite_store import SQLiteStore

if TYPE_CHECKING:  # pragma: no cover
    from .redis_cache import RedisCache


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
    """兼容历史脏数据，推断消息应归属的统计桶。"""
    normalized = str(message_type or "").strip().lower()
    if normalized in {"group", "private", "channel", "forum"}:
        if normalized == "forum":
            return "channel"
        return normalized
    if _has_value(channel_id):
        return "channel"
    if _has_value(group_id):
        return "group"
    return "private"


def _parse_content_types(raw: Any, message_str: Optional[str] = None) -> List[str]:
    """兼容逗号串、JSON 数组和历史脏格式。"""
    if raw is None:
        return ["Plain"] if message_str else []

    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        text = str(raw).strip()
        if not text:
            return ["Plain"] if message_str else []
        values: List[str] = []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    values = [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                values = []
        if not values:
            normalized = text
            for sep in ("|", ";", "/"):
                normalized = normalized.replace(sep, ",")
            values = [part.strip().strip('"\'') for part in normalized.split(",") if part.strip().strip('"\'')]

    if values:
        deduped = []
        seen = set()
        for item in values:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped
    return ["Plain"] if message_str else []


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

    def __init__(
        self,
        plugin_name: str,
        mysql_config: dict,
        redis_cache: Optional["RedisCache"] = None,
        fallback_enabled: bool = True,
        recovery_check_interval: int = 30,
        connection_max_retries: int = 5,
        backfill_batch_size: int = 500,
        sqlite_max_retention_days: int = 30,
    ):
        self.plugin_name = plugin_name
        self.mysql_config = mysql_config
        self.redis_cache = redis_cache
        self._pool: Optional[aiomysql.Pool] = None
        self._write_lock = asyncio.Lock()
        self._fts_available_cache: Optional[bool] = None

        # SQLite 兜底
        self._fallback_enabled = fallback_enabled
        self._recovery_check_interval = max(5, int(recovery_check_interval or 30))
        self._connection_max_retries = max(1, int(connection_max_retries or 5))
        self._backfill_batch_size = max(1, int(backfill_batch_size or 500))
        self._sqlite_max_retention_days = max(1, int(sqlite_max_retention_days or 30))
        self._sqlite: Optional[SQLiteStore] = None
        self._mysql_ready: bool = False
        self._degraded: bool = False
        self._mysql_version: Optional[str] = None
        self._recovery_task: Optional[asyncio.Task] = None

    def _sqlite_db_path(self) -> Path:
        data_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "messages_fallback.db"

    def _ensure_sqlite(self) -> SQLiteStore:
        """懒创建 SQLite 兜底后端。"""
        if self._sqlite is None:
            self._sqlite = SQLiteStore(self._sqlite_db_path())
        return self._sqlite

    @property
    def using_fallback(self) -> bool:
        """当前是否处于 SQLite 降级模式。"""
        return self._degraded and self._sqlite is not None

    @property
    def mysql_ready(self) -> bool:
        """MySQL 连接池是否就绪（主存储可用）。"""
        return self._mysql_ready and self._pool is not None

    async def _start_recovery_loop(self) -> None:
        """启动 MySQL 恢复检测后台任务（无论当前是否可用）。"""
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._recovery_loop())

    async def _recovery_loop(self) -> None:
        """周期检测 MySQL 是否恢复；恢复后切回并补写降级期间的消息。

        连续重连失败达到 ``connection_max_retries`` 上限后停止自动重连，
        保持 SQLite 降级模式，避免无限循环消耗资源。
        """
        consecutive_failures = 0
        while True:
            await asyncio.sleep(self._recovery_check_interval)
            try:
                if not self._mysql_ready:
                    if await self._try_reconnect_mysql():
                        consecutive_failures = 0
                        self._mysql_ready = True
                        self._degraded = False
                        self._mysql_version = None
                        logger.info("[FoxToolbox] MySQL 已恢复，切回主存储并开始补写")
                        await self._backfill_unsynced()
                    else:
                        consecutive_failures += 1
                        if consecutive_failures >= self._connection_max_retries:
                            logger.warning(
                                f"[FoxToolbox] MySQL 连续 {consecutive_failures} 次 "
                                f"重连失败，已达上限，停止自动重连，保持 SQLite 降级模式"
                            )
                            break
                else:
                    # 主存储可用时也周期性清理已同步的兜底数据
                    if self._sqlite is not None:
                        await self._sqlite.cleanup_synced(self._sqlite_max_retention_days)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"[FoxToolbox] 恢复检测异常: {e}")

    async def _try_reconnect_mysql(self) -> bool:
        """重新建立 MySQL 连接池并初始化表结构。

        仅当真正连接成功才返回 True；失败时保持 SQLite 降级状态。
        """
        host = self.mysql_config.get("host", "127.0.0.1")
        port = int(self.mysql_config.get("port", 3306))
        user = self.mysql_config.get("user", "root")
        password = self.mysql_config.get("password", "")
        database = self.mysql_config.get("database", "fox_toolbox")
        try:
            await self._close_pool()
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
            return True
        except Exception as e:
            await self._close_pool()
            logger.debug(f"[FoxToolbox] MySQL 恢复连接失败: {e}")
            return False

    async def _backfill_unsynced(self) -> None:
        """分批将 SQLite 中未同步消息补写进 MySQL。"""
        if self._sqlite is None or not self._pool:
            return
        while True:
            ids = await self._sqlite.get_unsynced_ids(self._backfill_batch_size)
            if not ids:
                break
            records = await self._sqlite.get_records_by_ids(ids)
            if not records:
                # 记录被并发清理，直接标记清空
                await self._sqlite.mark_synced(ids)
                continue
            try:
                saved, skipped = await self._save_messages_batch_mysql(records)
                # 幂等：已存在（skipped）也视为同步成功
                await self._sqlite.mark_synced(ids)
                logger.info(
                    f"[FoxToolbox] 补写批次完成: {len(ids)} 条 "
                    f"(新增 {saved}, 已存在 {skipped})"
                )
            except Exception as e:
                logger.warning(
                    f"[FoxToolbox] 补写批次失败，保留未同步待下轮重试: {e}"
                )
                # MySQL 再次故障：回到降级状态，等待下轮恢复检测
                self._mysql_ready = False
                self._degraded = True
                return
            if len(ids) < self._backfill_batch_size:
                break

    async def init(self) -> None:
        """初始化数据库连接池和表结构。

        MySQL 初始化失败且启用了兜底时，自动降级到本地 SQLite，
        不再抛出异常，插件保持可记录消息。
        """
        host = self.mysql_config.get("host", "127.0.0.1")
        port = int(self.mysql_config.get("port", 3306))
        user = self.mysql_config.get("user", "root")
        password = self.mysql_config.get("password", "")
        database = self.mysql_config.get("database", "fox_toolbox")

        try:
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
            self._mysql_ready = True
            self._degraded = False
            self._mysql_version = None
            logger.info(
                f"[FoxToolbox] MySQL 数据库初始化完成: "
                f"{host}:{port}/{database}"
            )
        except Exception as e:
            await self._close_pool()
            self._mysql_ready = False
            if not self._fallback_enabled:
                self._degraded = False
                raise
            self._ensure_sqlite()
            self._degraded = True
            logger.warning(
                f"[FoxToolbox] MySQL 不可用，已降级到本地 SQLite 存储: {e}"
            )

        await self._start_recovery_loop()

    async def _close_pool(self) -> None:
        """关闭 MySQL 连接池（若存在）。"""
        if self._pool:
            try:
                self._pool.close()
                await self._pool.wait_closed()
            except Exception:
                pass
            self._pool = None

    async def close(self) -> None:
        """关闭数据库连接池与后台任务"""
        if self._recovery_task is not None:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recovery_task = None
        await self._close_pool()
        if self._pool is None:
            logger.info("[FoxToolbox] 数据库已关闭")
        else:
            logger.info("[FoxToolbox] MySQL 连接池已关闭")

    async def ping(self) -> bool:
        """轻量数据库连通性检测（供 WebUI 状态卡片使用）。

        主存储不可用时回落到 SQLite ping，保证降级模式下状态卡片仍为「运行中」。
        """
        if not self._pool:
            if self._sqlite is not None:
                return await self._sqlite.ping()
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

    async def get_mysql_version(self) -> Optional[str]:
        """返回 MySQL 服务器版本字符串；MySQL 不可用时返回 None。

        查询结果缓存到 self._mysql_version，避免每次状态轮询重复查询。
        """
        if not self._mysql_ready or not self._pool:
            self._mysql_version = None
            return None
        if self._mysql_version:
            return self._mysql_version
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT VERSION()")
                    row = await cur.fetchone()
            self._mysql_version = str(row[0]) if row else None
            return self._mysql_version
        except Exception as e:
            logger.warning(f"[FoxToolbox] 获取 MySQL 版本失败: {e}")
            self._mysql_version = None
            return None

    async def get_table_count(self) -> int:
        """返回当前数据库内已创建的数据表数量；查询失败返回 -1。"""
        if not self._pool:
            if self._sqlite is not None:
                return await self._sqlite.get_table_count()
            return -1
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SHOW TABLES")
                    rows = await cur.fetchall()
            return len(rows or [])
        except Exception as e:
            logger.warning(f"[FoxToolbox] 获取数据表数量失败: {e}")
            return -1

    async def get_unsynced_count(self) -> int:
        """返回 SQLite 中尚未补写进 MySQL 的消息数量。"""
        if self._sqlite is None:
            return 0
        return await self._sqlite.get_unsynced_count()

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

    async def _run(self, mysql_fn, sqlite_fn):
        """MySQL 优先执行，故障时降级 SQLite 后端。

        :param mysql_fn: 无参异步可调用，MySQL 后端实现
        :param sqlite_fn: 无参异步可调用，SQLite 兜底实现
        """
        if self._mysql_ready and self._pool is not None:
            try:
                return await mysql_fn()
            except Exception as e:
                self._mysql_ready = False
                self._degraded = True
                logger.warning(f"[FoxToolbox] MySQL 故障，降级 SQLite: {e}")
                try:
                    self._ensure_sqlite()
                except Exception:
                    pass
                if self._sqlite is not None:
                    return await sqlite_fn()
                raise
        if self._sqlite is not None:
            return await sqlite_fn()
        raise RuntimeError("数据库后端不可用")

    async def save_message(self, record: MessageRecord) -> int:
        """保存消息记录，返回记录 ID（重复消息返回 -1）"""
        record.created_at = int(time.time() * 1000)

        if not record.content_hash:
            record.content_hash = compute_content_hash(
                record.platform, record.session_id, record.sender_id,
                record.message_str, record.timestamp,
            )

        record_id = await self._run(
            lambda: self._save_message_mysql(record),
            lambda: self._sqlite.save_message(record),
        )

        if record_id == -1:
            logger.debug(
                f"[FoxToolbox] 消息已存在，跳过: "
                f"platform={record.platform}, "
                f"message_id={record.message_id or record.content_hash}"
            )
        else:
            record.id = record_id  # 回填 id，供缓存载荷使用
            await self._cache_recent_message(record)
            await self._apply_stats_deltas([record])

        return record_id

    async def _save_message_mysql(self, record: MessageRecord) -> int:
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

        return record_id

    async def save_messages_batch(
        self, records: List[MessageRecord]
    ) -> tuple:
        """批量保存消息记录，返回 (成功数量, 跳过数量)"""
        if not records:
            return 0, 0

        now_ms = int(time.time() * 1000)
        for record in records:
            record.created_at = now_ms
            if not record.content_hash:
                record.content_hash = compute_content_hash(
                    record.platform, record.session_id,
                    record.sender_id, record.message_str,
                    record.timestamp,
                )

        saved, skipped = await self._run(
            lambda: self._save_messages_batch_mysql(records),
            lambda: self._sqlite.save_messages_batch(records),
        )

        cached_records = [r for r in records if r.id is not None]
        if cached_records:
            await self._cache_recent_messages(cached_records)
            await self._apply_stats_deltas(cached_records)

        logger.debug(
            f"[FoxToolbox] 批量保存完成: {saved} 成功, {skipped} 跳过"
        )
        return saved, skipped

    async def _save_messages_batch_mysql(
        self, records: List[MessageRecord]
    ) -> tuple:
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
        cached_records: List[MessageRecord] = []
        async with self._write_lock:
            async with self._pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        for record in records:
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
                                try:
                                    record.id = cur.lastrowid
                                except Exception:
                                    record.id = None
                                cached_records.append(record)
                            else:
                                skipped += 1
                        await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"[FoxToolbox] 批量保存消息失败: {e}")
                    raise

        if cached_records:
            await self._cache_recent_messages(cached_records)
            await self._apply_stats_deltas(cached_records)
        return saved, skipped

    async def _cache_recent_message(self, record: MessageRecord) -> None:
        """将单条新消息推入 Redis 最近消息缓存（失败无副作用）。"""
        if self.redis_cache is None:
            return
        try:
            await self.redis_cache.push_recent_message(self._record_cache_payload(record))
        except Exception as e:
            logger.debug(f"[FoxToolbox] 推送最近消息缓存失败: {e}")

    @staticmethod
    def _stats_delta_from_record(record: MessageRecord) -> dict:
        """构造消息对应的统计增量。"""
        return {
            "count": 1,
            "platform": record.platform,
            "bucket": _infer_message_bucket(
                record.message_type, record.group_id, record.channel_id
            ),
            "timestamp": record.timestamp,
            "created_at": record.created_at,
        }

    async def _apply_stats_deltas(self, records: List[MessageRecord]) -> None:
        """将新消息增量合并进 Redis 统计缓存（实时更新，TTL 滑动续期）。

        缓存不存在（如 TTL 过期或从未回源）时触发一次回源数据库重建，
        此时数据库已含最新消息，重建结果即正确；Redis 不可用则跳过。
        失败无副作用，不阻塞消息保存主流程。
        """
        if self.redis_cache is None or not records:
            return
        try:
            deltas = [self._stats_delta_from_record(r) for r in records]
            updated = await self.redis_cache.apply_stats_deltas(deltas)
            if not updated and self.redis_cache.available:
                await self.get_stats()  # 缓存缺失，回源重建并回填缓存
        except Exception as e:
            logger.debug(f"[FoxToolbox] 增量更新统计缓存失败: {e}")

    async def _cache_recent_messages(self, records: List[MessageRecord]) -> None:
        """将批量新消息推入 Redis 最近消息缓存（倒序逐条推送保持顺序）。"""
        if self.redis_cache is None or not records:
            return
        try:
            for record in reversed(records[-20:]):
                await self.redis_cache.push_recent_message(
                    self._record_cache_payload(record)
                )
        except Exception as e:
            logger.debug(f"[FoxToolbox] 批量推送最近消息缓存失败: {e}")

    @staticmethod
    def _record_cache_payload(record: MessageRecord) -> dict:
        """构造精简的最近消息缓存载荷。"""
        return {
            "id": record.id,
            "platform": record.platform,
            "sender_id": record.sender_id,
            "sender_name": record.sender_name,
            "message_type": record.message_type,
            "message_str": record.message_str,
            "timestamp": record.timestamp,
            "created_at": record.created_at,
        }

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
            keyword_str = safe_str(query_filter.keyword)
            # MySQL FULLTEXT 布尔模式保留字符，含这些字符会触发 1064 语法错误，
            # 自动降级到 LIKE 匹配（同样安全，参数化）
            _fts_reserved = set("+-<>()~*\"@")
            if use_fts and not (set(keyword_str) & _fts_reserved):
                conditions.append(
                    "MATCH(message_str) AGAINST(%s IN BOOLEAN MODE)"
                )
                params.append(keyword_str)
            else:
                escaped = (
                    keyword_str
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
        return await self._run(
            lambda: self._query_messages_mysql(query_filter),
            lambda: self._sqlite.query_messages(query_filter),
        )

    async def _query_messages_mysql(self, query_filter: QueryFilter) -> List[MessageRecord]:
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
        """分批查询消息，返回异步生成器（MySQL 故障时降级 SQLite）"""
        if self._mysql_ready and self._pool is not None:
            yielded = False
            try:
                async for rec in self._query_messages_batch_mysql(query_filter, batch_size):
                    yielded = True
                    yield rec
                return
            except Exception as e:
                self._mysql_ready = False
                self._degraded = True
                logger.warning(f"[FoxToolbox] MySQL 批量查询故障，降级 SQLite: {e}")
                try:
                    self._ensure_sqlite()
                except Exception:
                    pass
                if self._sqlite is None or yielded:
                    return
        async for rec in self._sqlite.query_messages_batch(query_filter, batch_size):
            yield rec

    async def _query_messages_batch_mysql(
        self,
        query_filter: QueryFilter,
        batch_size: int = 500,
    ) -> AsyncGenerator[MessageRecord, None]:
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
        return await self._run(
            lambda: self._get_message_by_id_mysql(message_id),
            lambda: self._sqlite.get_message_by_id(message_id),
        )

    async def _get_message_by_id_mysql(self, message_id: int) -> Optional[MessageRecord]:
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
        return await self._run(
            lambda: self._get_message_by_platform_id_mysql(platform_message_id, platform),
            lambda: self._sqlite.get_message_by_platform_id(platform_message_id, platform),
        )

    async def _get_message_by_platform_id_mysql(
        self,
        platform_message_id: str,
        platform: Optional[str] = None,
    ) -> Optional[MessageRecord]:
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
        return await self._run(
            lambda: self._get_existing_message_ids_mysql(message_ids, platform),
            lambda: self._sqlite.get_existing_message_ids(message_ids, platform),
        )

    async def _get_existing_message_ids_mysql(
        self, message_ids: List[str], platform: str
    ) -> set:
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
        return await self._run(
            lambda: self._get_context_messages_mysql(message_id, before, after),
            lambda: self._sqlite.get_context_messages(message_id, before, after),
        )

    async def _get_context_messages_mysql(
        self,
        message_id: int,
        before: int = 5,
        after: int = 5,
    ) -> Dict[str, List[MessageRecord]]:
        target = await self._get_message_by_id_mysql(message_id)
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
        return await self._run(
            lambda: self._count_messages_mysql(query_filter),
            lambda: self._sqlite.count_messages(query_filter),
        )

    async def _count_messages_mysql(self, query_filter: QueryFilter) -> int:
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
        """获取消息统计信息（Redis 缓存优先，TTL 内直接返回缓存）"""
        if self.redis_cache is not None:
            cached = await self.redis_cache.get_stats()
            if cached is not None:
                try:
                    stats = MessageStats(**cached)
                    logger.debug("[FoxToolbox] 命中统计缓存")
                    return stats
                except (TypeError, ValueError):
                    logger.debug("[FoxToolbox] 统计缓存数据损坏，回源数据库")

        stats = await self._run(
            lambda: self._get_stats_mysql(),
            lambda: self._sqlite.get_stats(),
        )

        if self.redis_cache is not None:
            try:
                await self.redis_cache.set_stats(asdict(stats))
            except Exception as e:
                logger.debug(f"[FoxToolbox] 写入统计缓存失败: {e}")

        return stats

    async def _get_stats_mysql(self) -> MessageStats:
        stats = MessageStats()

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 聚合统计在 MySQL 端完成，避免将整表拉入 Python 内存
                await cur.execute("SELECT COUNT(*) FROM messages")
                total_row = await cur.fetchone()
                stats.total_count = int(total_row[0]) if total_row else 0

                # 按 (platform, message_type, group_id, channel_id) 分组统计，
                # 用于平台分布与消息类型桶计数
                await cur.execute("""
                    SELECT platform, message_type, group_id, channel_id, COUNT(*)
                    FROM messages
                    GROUP BY platform, message_type, group_id, channel_id
                """)
                group_rows = await cur.fetchall()
                platform_stats: Dict[str, int] = {}
                for platform, message_type, group_id, channel_id, count in group_rows:
                    bucket = _infer_message_bucket(message_type, group_id, channel_id)
                    if bucket == "group":
                        stats.group_message_count += int(count)
                    elif bucket == "private":
                        stats.private_message_count += int(count)
                    elif bucket == "channel":
                        stats.channel_message_count += int(count)
                    platform_stats[platform] = platform_stats.get(platform, 0) + int(count)
                stats.platform_stats = platform_stats

                # 时间范围
                await cur.execute("""
                    SELECT MIN(timestamp), MAX(timestamp),
                           MIN(created_at), MAX(created_at)
                    FROM messages
                """)
                time_row = await cur.fetchone()
                if time_row:
                    stats.oldest_timestamp = time_row[0]
                    stats.newest_timestamp = time_row[1]
                    stats.first_record_time = time_row[2]
                    stats.last_record_time = time_row[3]

        return stats

    async def get_content_type_stats(self) -> List[Dict]:
        """获取消息内容类型统计（文字/图片/文件/视频/语音/文档/音频/压缩包等）"""
        return await self._run(
            lambda: self._get_content_type_stats_mysql(),
            lambda: self._sqlite.get_content_type_stats(),
        )

    async def _get_content_type_stats_mysql(self) -> List[Dict]:
        # ponytail: 全表拉取 content_types/message_str 到内存统计，
        # 百万级消息时会产生瞬时内存峰值；若数据量过大应改为 SQL 聚合或分批扫描
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT content_types, message_str FROM messages")
                rows = await cur.fetchall()

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
            "document", "audio", "archive", "code", "file_image", "file_video", "other_file",
            "at", "reply", "face", "rich", "unknown",
        ]

        counters = {key: 0 for key in keys}
        for raw_content_types, message_str in rows:
            parsed_types = _parse_content_types(raw_content_types, message_str)
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
        """获取各平台的详细统计（消息数、群聊数、私聊数等）"""
        return await self._run(
            lambda: self._get_platform_detail_stats_mysql(),
            lambda: self._sqlite.get_platform_detail_stats(),
        )

    async def _get_platform_detail_stats_mysql(self) -> List[Dict]:
        # ponytail: 全表拉取统计，百万级消息时内存峰值明显；
        # 若数据量过大应改为按平台分组 SQL 聚合
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT platform, message_type, group_id, channel_id, content_types, message_str, timestamp FROM messages"
                )
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

        grouped: Dict[str, Dict[str, Any]] = {}
        for platform, message_type, group_id, channel_id, content_types, message_str, timestamp in rows:
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
            bucket = _infer_message_bucket(message_type, group_id, channel_id)
            if bucket == "group":
                item["group_count"] += 1
            elif bucket == "private":
                item["private_count"] += 1
            elif bucket == "channel":
                item["channel_count"] += 1

            parsed_types = set(_parse_content_types(content_types, message_str))
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

            if timestamp is not None:
                if item["oldest_timestamp"] is None or timestamp < item["oldest_timestamp"]:
                    item["oldest_timestamp"] = timestamp
                if item["newest_timestamp"] is None or timestamp > item["newest_timestamp"]:
                    item["newest_timestamp"] = timestamp

        return sorted(grouped.values(), key=lambda item: item["total"], reverse=True)

    async def cleanup_by_age(self, retention_days: int) -> tuple:
        """清理超过保留天数的消息，返回 (删除数量, 被删记录的媒体路径列表)"""
        if retention_days <= 0:
            return 0, []
        return await self._run(
            lambda: self._cleanup_by_age_mysql(retention_days),
            lambda: self._sqlite.cleanup_by_age(retention_days),
        )

    async def _cleanup_by_age_mysql(self, retention_days: int) -> tuple:
        cutoff_time = int(
            (time.time() - retention_days * 86400) * 1000
        )
        try:
            media_paths: List[str] = []
            rowcount = 0
            async with self._write_lock:
                async with self._pool.acquire() as conn:
                    try:
                        async with conn.cursor() as cur:
                            # keyset 分页：基于自增主键分页，避免 buffered 游标
                            # 一次性把整表结果载入内存
                            last_id = 0
                            while True:
                                await cur.execute(
                                    "SELECT id, message_chain FROM messages "
                                    "WHERE id > %s AND timestamp < %s "
                                    "AND message_chain IS NOT NULL "
                                    "ORDER BY id ASC LIMIT 500",
                                    (last_id, cutoff_time),
                                )
                                batch_rows = await cur.fetchall()
                                if not batch_rows:
                                    break
                                for row in batch_rows:
                                    media_paths.extend(
                                        extract_media_paths(row[1])
                                    )
                                last_id = batch_rows[-1][0]

                            # 分批删除，避免单条大事务长锁行
                            while True:
                                await cur.execute(
                                    "DELETE FROM messages WHERE timestamp < %s "
                                    "LIMIT 1000",
                                    (cutoff_time,),
                                )
                                deleted = cur.rowcount
                                if deleted <= 0:
                                    break
                                rowcount += deleted
                                await conn.commit()
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
        return await self._run(
            lambda: self._cleanup_by_limit_mysql(max_records),
            lambda: self._sqlite.cleanup_by_limit(max_records),
        )

    async def _cleanup_by_limit_mysql(self, max_records: int) -> tuple:
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

                        # 收集待删记录的媒体路径（keyset 分页）
                        await cur.execute(
                            "SELECT id, message_chain FROM messages "
                            "WHERE message_chain IS NOT NULL "
                            "ORDER BY id ASC LIMIT %s",
                            (delete_count,),
                        )
                        while True:
                            rows = await cur.fetchmany(500)
                            if not rows:
                                break
                            for row in rows:
                                media_paths.extend(
                                    extract_media_paths(row[1])
                                )

                        # 分批删除最旧记录（按 id 升序），避免单条大事务
                        rowcount = 0
                        remaining = delete_count
                        while remaining > 0:
                            batch_limit = min(1000, remaining)
                            await cur.execute(
                                "DELETE FROM messages "
                                "ORDER BY id ASC LIMIT %s",
                                (batch_limit,),
                            )
                            deleted = cur.rowcount
                            if deleted <= 0:
                                break
                            rowcount += deleted
                            remaining -= deleted
                            await conn.commit()
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
        return await self._run(
            lambda: self._get_timeline_stats_mysql(
                interval, start_time, end_time, platform, group_id
            ),
            lambda: self._sqlite.get_timeline_stats(
                interval, start_time, end_time, platform, group_id
            ),
        )

    async def _get_timeline_stats_mysql(
        self,
        interval: str = "day",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict]:
        # ponytail: 无 LIMIT 全表拉取时间列，百万级消息时内存峰值明显；
        # 若数据量过大应改为 SQL 按日/周/月聚合
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
            SELECT `timestamp`, `message_type`, `group_id`, `channel_id`
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
            grp_id = row[2]
            ch_id = row[3]
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
            bucket = _infer_message_bucket(msg_type, grp_id, ch_id)
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
        """获取发送者排行榜"""
        return await self._run(
            lambda: self._get_sender_ranking_mysql(
                limit, start_time, end_time, platform, group_id
            ),
            lambda: self._sqlite.get_sender_ranking(
                limit, start_time, end_time, platform, group_id
            ),
        )

    async def _get_sender_ranking_mysql(
        self,
        limit: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict]:
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
        return await self._run(
            lambda: self._get_group_ranking_mysql(
                limit, start_time, end_time, platform
            ),
            lambda: self._sqlite.get_group_ranking(
                limit, start_time, end_time, platform
            ),
        )

    async def _get_group_ranking_mysql(
        self,
        limit: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
    ) -> List[Dict]:
        # ponytail: 全表拉取后 Python 端分组，百万级消息时内存峰值明显；
        # 若数据量过大应改为 SQL GROUP BY
        conditions = [
            "group_id IS NOT NULL",
            "group_id != ''",
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
            SELECT group_id, platform, message_type, channel_id, sender_id
            FROM messages
            WHERE {where_clause}
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for grp_id, grp_platform, message_type, channel_id, sender_id in rows:
            bucket = _infer_message_bucket(message_type, grp_id, channel_id)
            if bucket not in {"group", "channel"}:
                continue
            key = (grp_id, grp_platform)
            item = grouped.setdefault(
                key,
                {"group_id": grp_id, "platform": grp_platform, "count": 0, "senders": set()},
            )
            item["count"] += 1
            if sender_id:
                item["senders"].add(sender_id)

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

    async def get_distinct_platforms(self) -> List[str]:
        """获取所有平台列表"""
        return await self._run(
            lambda: self._get_distinct_platforms_mysql(),
            lambda: self._sqlite.get_distinct_platforms(),
        )

    async def _get_distinct_platforms_mysql(self) -> List[str]:
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
        return await self._run(
            lambda: self._get_distinct_senders_mysql(platform, group_id, limit),
            lambda: self._sqlite.get_distinct_senders(platform, group_id, limit),
        )

    async def _get_distinct_senders_mysql(
        self,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
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
        return await self._run(
            lambda: self._get_distinct_groups_mysql(platform, limit),
            lambda: self._sqlite.get_distinct_groups(platform, limit),
        )

    async def _get_distinct_groups_mysql(
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
        return await self._run(
            lambda: self._get_media_paths_before_mysql(cutoff_timestamp),
            lambda: self._sqlite.get_media_paths_before(cutoff_timestamp),
        )

    async def _get_media_paths_before_mysql(
        self, cutoff_timestamp: int
    ) -> List[str]:
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
        return await self._run(
            lambda: self._get_media_paths_over_limit_mysql(max_records),
            lambda: self._sqlite.get_media_paths_over_limit(max_records),
        )

    async def _get_media_paths_over_limit_mysql(
        self, max_records: int
    ) -> List[str]:
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
        return await self._run(
            lambda: self._get_unreferenced_media_paths_mysql(candidates),
            lambda: self._sqlite.get_unreferenced_media_paths(candidates),
        )

    async def _get_unreferenced_media_paths_mysql(
        self, candidates: List[str]
    ) -> List[str]:
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
    """v2 → v3: 添加 content_types 列（幂等：列/索引已存在时跳过）。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'messages' "
                "AND COLUMN_NAME = 'content_types'"
            )
            if (await cur.fetchone())[0] == 0:
                await cur.execute(
                    "ALTER TABLE messages ADD COLUMN content_types VARCHAR(256) "
                    "DEFAULT NULL AFTER content_hash"
                )
            await cur.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'messages' "
                "AND INDEX_NAME = 'idx_content_types'"
            )
            if (await cur.fetchone())[0] == 0:
                await cur.execute(
                    "ALTER TABLE messages ADD INDEX idx_content_types (content_types)"
                )
            await conn.commit()


_SCHEMA_MIGRATIONS: Dict[int, Any] = {
    3: _migrate_v3,
}
