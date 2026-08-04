"""数据模型定义"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json

PLUGIN_DIR_NAME = "astrbot_plugin_fox_toolbox"
SCHEMA_VERSION = 2
VALID_MESSAGE_TYPES = {"group", "private", "channel", "forum"}

# 已弃用的数据库表列表
# 每次插件启动/重载时会检查并自动删除这些表
# 当你废弃某个表时，将表名添加到此处即可
DEPRECATED_TABLES = [
    # 原 SQLite 时代的 FTS5 虚拟表，迁移到 MySQL 后已弃用
    "messages_fts",
    # 预留：未来废弃的表添加到这里
]


@dataclass
class MessageRecord:
    """消息记录数据模型"""

    id: Optional[int] = None
    platform: str = ""
    message_id: str = ""
    session_id: str = ""
    group_id: Optional[str] = None
    channel_id: Optional[str] = None
    sender_id: str = ""
    sender_name: Optional[str] = None
    message_type: str = ""
    message_str: Optional[str] = None
    message_chain: Optional[str] = None
    raw_message: Optional[str] = None
    reply_to_id: Optional[str] = None
    content_hash: Optional[str] = None
    timestamp: int = 0
    created_at: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def get_message_chain_list(self) -> List[dict]:
        if self.message_chain:
            try:
                return json.loads(self.message_chain)
            except json.JSONDecodeError:
                return []
        return []

    def get_raw_message_dict(self) -> Optional[dict]:
        if self.raw_message:
            try:
                return json.loads(self.raw_message)
            except json.JSONDecodeError:
                return None
        return None


@dataclass
class QueryFilter:
    """消息查询过滤器 - 支持任意条件组合"""

    platform: Optional[str] = None
    platforms: Optional[List[str]] = None

    sender_id: Optional[str] = None
    sender_ids: Optional[List[str]] = None

    group_id: Optional[str] = None
    group_ids: Optional[List[str]] = None

    session_id: Optional[str] = None
    session_ids: Optional[List[str]] = None

    channel_id: Optional[str] = None

    message_type: Optional[str] = None

    time: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None

    keyword: Optional[str] = None

    reply_to_id: Optional[str] = None

    limit: int = 100
    offset: int = 0
    order: str = "desc"

    def get_sender_ids(self) -> List[str]:
        ids = []
        if self.sender_id:
            ids.append(self.sender_id)
        if self.sender_ids:
            ids.extend(self.sender_ids)
        return ids

    def get_group_ids(self) -> List[str]:
        ids = []
        if self.group_id:
            ids.append(self.group_id)
        if self.group_ids:
            ids.extend(self.group_ids)
        return ids

    def get_session_ids(self) -> List[str]:
        ids = []
        if self.session_id:
            ids.append(self.session_id)
        if self.session_ids:
            ids.extend(self.session_ids)
        return ids

    def get_platforms(self) -> List[str]:
        platforms = []
        if self.platform:
            platforms.append(self.platform)
        if self.platforms:
            platforms.extend(self.platforms)
        return platforms

    def is_desc_order(self) -> bool:
        return self.order.lower() != "asc"


@dataclass
class MessageStats:
    """消息统计信息"""

    total_count: int = 0
    group_message_count: int = 0
    private_message_count: int = 0
    channel_message_count: int = 0
    platform_stats: dict = field(default_factory=dict)
    oldest_timestamp: Optional[int] = None
    newest_timestamp: Optional[int] = None
    first_record_time: Optional[int] = None
    last_record_time: Optional[int] = None
