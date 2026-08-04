"""对外暴露的 API 接口，供其他插件调用"""

from pathlib import Path
from typing import Optional, List, Dict

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .database import Database
from .models import MessageRecord, QueryFilter, MessageStats, PLUGIN_DIR_NAME, SCHEMA_VERSION
from .media_downloader import MediaDownloader


class MessageRecorderAPI:
    """
    消息记录器 API 接口

    提供统一的 query() 和 count() 方法，支持任意条件组合。
    同时提供常用场景的快捷方法。
    """

    def __init__(self, database: Database, media_downloader: Optional[MediaDownloader] = None):
        self._db = database
        self._media_downloader = media_downloader

    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("数据库未初始化，无法执行操作")
        return self._db

    @staticmethod
    def get_media_base_path() -> Path:
        """获取媒体文件存储根目录的绝对路径"""
        return Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"

    def get_media_absolute_path(self, relative_path: str) -> Optional[Path]:
        """
        获取媒体文件的绝对路径

        Args:
            relative_path: 相对路径（如 "images/2026-04/abc123.jpg"）

        Returns:
            文件绝对路径，文件不存在则返回 None

        Examples:
            api = plugin.get_api()
            abs_path = api.get_media_absolute_path("images/2026-04/abc123.jpg")
            if abs_path:
                with open(abs_path, "rb") as f:
                    image_data = f.read()
        """
        if not relative_path:
            return None
        media_base = self.get_media_base_path()
        file_path = media_base / relative_path
        try:
            file_path.resolve().relative_to(media_base.resolve())
        except ValueError:
            return None
        if file_path.exists() and file_path.is_file():
            return file_path
        return None

    def get_media_url(self, relative_path: str) -> str:
        """
        获取媒体文件的 Web 访问 URL

        Args:
            relative_path: 相对路径（如 "images/ab/abc123.jpg"）

        Returns:
            Web URL（如 "/astrbot_plugin_fox_toolbox/media?path=images/ab/abc123.jpg"）

        Examples:
            api = plugin.get_api()
            url = api.get_media_url("images/ab/abc123.jpg")
        """
        if not relative_path:
            return ""
        from urllib.parse import urlencode
        return f"/{PLUGIN_DIR_NAME}/media?{urlencode({'path': relative_path})}"

    def extract_media_paths(self, message: MessageRecord) -> List[str]:
        """
        从消息记录中提取所有媒体文件的相对路径

        Args:
            message: 消息记录对象

        Returns:
            媒体文件相对路径列表

        Examples:
            api = plugin.get_api()
            messages = await api.query(limit=10)
            for msg in messages:
                paths = api.extract_media_paths(msg)
                for path in paths:
                    abs_path = api.get_media_absolute_path(path)
        """
        return MediaDownloader.extract_media_paths(message.message_chain)

    def get_schema_version(self) -> int:
        """
        获取当前数据库 schema 版本

        Returns:
            schema 版本号
        """
        return SCHEMA_VERSION

    # ========== 核心查询方法 ==========

    async def query(
        self,
        platform: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        sender_id: Optional[str] = None,
        sender_ids: Optional[List[str]] = None,
        group_id: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        session_ids: Optional[List[str]] = None,
        channel_id: Optional[str] = None,
        message_type: Optional[str] = None,
        time: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        keyword: Optional[str] = None,
        reply_to_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order: str = "desc",
    ) -> List[MessageRecord]:
        """
        统一查询方法 - 支持任意条件组合

        Args:
            platform: 单个平台名称
            platforms: 多个平台名称列表
            sender_id: 单个发送者 ID
            sender_ids: 多个发送者 ID 列表
            group_id: 单个群组 ID
            group_ids: 多个群组 ID 列表
            session_id: 单个会话 ID
            session_ids: 多个会话 ID 列表
            channel_id: 频道 ID（Discord 等平台）
            message_type: 消息类型 ("group"、"private"、"channel")
            time: 时间字符串，支持:
                - 自然语言: today, yesterday, week, month, hour
                - 天数范围: last7d, last30d, last3d
                - 小时范围: last1h, last3h, last12h
                - 具体日期: 2024-01-15
                - 日期范围: 2024-01-01~2024-01-15
                - 相对时间: -1d, -7d, -3h
            start_time: 开始时间戳（毫秒），与 time 互斥
            end_time: 结束时间戳（毫秒），与 time 互斥
            keyword: 消息内容关键词
            reply_to_id: 回复的目标消息 ID
            limit: 返回数量限制
            offset: 偏移量（用于分页）
            order: 排序方式 ("desc" 倒序, "asc" 正序)

        Returns:
            消息记录列表

        Examples:
            # 简单查询
            messages = await mr_api.query(limit=10)

            # 多条件组合
            messages = await mr_api.query(
                platform="telegram",
                group_id="123456",
                time="today",
                keyword="hello"
            )

            # 查询频道消息
            messages = await mr_api.query(
                channel_id="987654",
                time="week"
            )

            # 查询回复某消息的所有消息
            messages = await mr_api.query(
                reply_to_id="12345",
                platform="discord"
            )

            # 分页查询
            messages = await mr_api.query(
                group_id="123456",
                limit=20,
                offset=40
            )
        """
        query_filter = QueryFilter(
            platform=platform,
            platforms=platforms,
            sender_id=sender_id,
            sender_ids=sender_ids,
            group_id=group_id,
            group_ids=group_ids,
            session_id=session_id,
            session_ids=session_ids,
            channel_id=channel_id,
            message_type=message_type,
            time=time,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            reply_to_id=reply_to_id,
            limit=limit,
            offset=offset,
            order=order,
        )
        return await self.db.query_messages(query_filter)

    async def count(
        self,
        platform: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        sender_id: Optional[str] = None,
        sender_ids: Optional[List[str]] = None,
        group_id: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        session_ids: Optional[List[str]] = None,
        channel_id: Optional[str] = None,
        message_type: Optional[str] = None,
        time: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        keyword: Optional[str] = None,
        reply_to_id: Optional[str] = None,
    ) -> int:
        """
        统一统计方法 - 支持任意条件组合

        参数与 query() 相同（不含分页参数）

        Returns:
            符合条件的消息数量

        Examples:
            # 统计今天的消息
            count = await mr_api.count(time="today")

            # 统计某频道的消息
            count = await mr_api.count(channel_id="987654", time="month")
        """
        query_filter = QueryFilter(
            platform=platform,
            platforms=platforms,
            sender_id=sender_id,
            sender_ids=sender_ids,
            group_id=group_id,
            group_ids=group_ids,
            session_id=session_id,
            session_ids=session_ids,
            channel_id=channel_id,
            message_type=message_type,
            time=time,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            reply_to_id=reply_to_id,
        )
        return await self.db.count_messages(query_filter)

    # ========== 快捷方法 ==========

    async def get_today(self, limit: int = 50, **kwargs) -> List[MessageRecord]:
        """
        获取今天的消息

        Args:
            limit: 返回数量限制
            **kwargs: 其他筛选条件（platform, group_id, channel_id 等）

        Examples:
            messages = await mr_api.get_today(limit=20)
            messages = await mr_api.get_today(platform="telegram", limit=50)
        """
        return await self.query(time="today", limit=limit, **kwargs)

    async def get_yesterday(self, limit: int = 50, **kwargs) -> List[MessageRecord]:
        """
        获取昨天的消息

        Args:
            limit: 返回数量限制
            **kwargs: 其他筛选条件
        """
        return await self.query(time="yesterday", limit=limit, **kwargs)

    async def get_recent(
        self,
        hours: int = 24,
        limit: int = 100,
        **kwargs
    ) -> List[MessageRecord]:
        """
        获取最近 N 小时的消息

        Args:
            hours: 小时数
            limit: 返回数量限制
            **kwargs: 其他筛选条件

        Examples:
            messages = await mr_api.get_recent(hours=6)
        """
        time_str = f"last{hours}h"
        return await self.query(time=time_str, limit=limit, **kwargs)

    async def get_recent_days(
        self,
        days: int = 7,
        limit: int = 100,
        **kwargs
    ) -> List[MessageRecord]:
        """
        获取最近 N 天的消息

        Args:
            days: 天数
            limit: 返回数量限制
            **kwargs: 其他筛选条件

        Examples:
            messages = await mr_api.get_recent_days(days=30)
        """
        time_str = f"last{days}d"
        return await self.query(time=time_str, limit=limit, **kwargs)

    async def search(self, keyword: str, limit: int = 50, **kwargs) -> List[MessageRecord]:
        """
        搜索消息内容

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            **kwargs: 其他筛选条件

        Examples:
            messages = await mr_api.search("关键词")
            messages = await mr_api.search("关键词", group_id="123456", time="week")
        """
        return await self.query(keyword=keyword, limit=limit, **kwargs)

    async def get_by_id(self, message_id: int) -> Optional[MessageRecord]:
        """
        根据 ID 获取单条消息

        Args:
            message_id: 数据库记录 ID

        Returns:
            消息记录，不存在则返回 None
        """
        logger.debug(f"[FoxToolbox] API调用: get_by_id({message_id})")
        result = await self.db.get_message_by_id(message_id)
        if result:
            logger.debug(f"[FoxToolbox] 找到消息 #{message_id}")
        else:
            logger.debug(f"[FoxToolbox] 消息 #{message_id} 不存在")
        return result

    async def get_by_platform_message_id(
        self,
        platform_message_id: str,
        platform: Optional[str] = None
    ) -> Optional[MessageRecord]:
        """
        根据平台原始消息 ID 获取消息

        Args:
            platform_message_id: 平台原始消息 ID（如 Telegram/Discord 等平台的消息 ID）
            platform: 可选的平台名称，用于精确匹配（推荐指定以提高查询准确性）

        Returns:
            消息记录，不存在则返回 None

        Examples:
            message = await mr_api.get_by_platform_message_id("12345678", platform="telegram")
            message = await mr_api.get_by_platform_message_id("987654321", platform="discord")
        """
        logger.debug(
            f"[FoxToolbox] API调用: get_by_platform_message_id({platform_message_id}, platform={platform})"
        )
        result = await self.db.get_message_by_platform_id(platform_message_id, platform)
        if result:
            logger.debug(
                f"[FoxToolbox] 找到消息: platform_message_id={platform_message_id}, "
                f"db_id={result.id}, platform={result.platform}"
            )
        else:
            logger.debug(
                f"[FoxToolbox] 消息不存在: platform_message_id={platform_message_id}, "
                f"platform={platform}"
            )
        return result

    async def get_replies(
        self,
        reply_to_id: str,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> List[MessageRecord]:
        """
        获取回复某消息的所有消息

        Args:
            reply_to_id: 被回复的消息 ID（平台原始消息 ID）
            platform: 可选的平台名称
            limit: 返回数量限制

        Returns:
            回复消息列表

        Examples:
            replies = await mr_api.get_replies("12345678", platform="telegram")
        """
        logger.debug(
            f"[FoxToolbox] API调用: get_replies({reply_to_id}, platform={platform})"
        )
        return await self.query(
            reply_to_id=reply_to_id,
            platform=platform,
            limit=limit,
        )

    async def get_by_channel(
        self,
        channel_id: str,
        limit: int = 50,
        **kwargs
    ) -> List[MessageRecord]:
        """
        获取指定频道的消息

        Args:
            channel_id: 频道 ID
            limit: 返回数量限制
            **kwargs: 其他筛选条件

        Examples:
            messages = await mr_api.get_by_channel("987654", time="week")
        """
        return await self.query(channel_id=channel_id, limit=limit, **kwargs)

    async def get_context(
        self,
        message_id: int,
        before: int = 5,
        after: int = 5
    ) -> Dict[str, List[MessageRecord]]:
        """
        获取某条消息的上下文消息

        Args:
            message_id: 数据库记录 ID
            before: 获取之前多少条
            after: 获取之后多少条

        Returns:
            {"before": [...], "after": [...]}
        """
        logger.debug(
            f"[FoxToolbox] API调用: get_context(id={message_id}, before={before}, after={after})"
        )
        result = await self.db.get_context_messages(message_id, before, after)
        logger.debug(
            f"[FoxToolbox] 上下文结果: before={len(result['before'])}条, after={len(result['after'])}条"
        )
        return result

    async def get_stats(self) -> MessageStats:
        """
        获取消息统计信息

        Returns:
            MessageStats 对象，包含:
            - total_count: 总消息数
            - group_message_count: 群聊消息数
            - private_message_count: 私聊消息数
            - channel_message_count: 频道消息数
            - platform_stats: 各平台消息数
            - oldest_timestamp: 最早消息时间
            - newest_timestamp: 最新消息时间
        """
        logger.debug("[FoxToolbox] API调用: get_stats()")
        result = await self.db.get_stats()
        logger.debug(
            f"[FoxToolbox] 统计结果: total={result.total_count}, "
            f"group={result.group_message_count}, private={result.private_message_count}, "
            f"channel={result.channel_message_count}"
        )
        return result
