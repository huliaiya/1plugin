"""平台适配器模块 - 为不同平台提供统一的消息处理接口"""

from typing import Optional, Dict, Type
from astrbot.api import logger
from astrbot.core.platform.message_type import MessageType


class PlatformAdapter:
    """平台适配器基类

    使用 AstrBot 已提供的 message_obj.type (MessageType) 来判断消息类型，
    而非通过 group_id 猜测。
    """

    PLATFORM_NAME: str = "generic"

    def normalize_sender_id(self, raw_id: str) -> str:
        return str(raw_id).strip() if raw_id else ""

    def normalize_sender_name(self, raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None
        return str(raw_name).strip()[:256] or None

    def normalize_group_id(self, raw_group_id: Optional[str]) -> Optional[str]:
        if not raw_group_id:
            return None
        return str(raw_group_id).strip()[:128] or None

    def extract_channel_id(self, message_obj) -> Optional[str]:
        return None

    def normalize_channel_id(self, raw_channel_id: Optional[str]) -> Optional[str]:
        if not raw_channel_id:
            return None
        cid = str(raw_channel_id).strip()
        return cid[:128] if cid else None

    def normalize_message_id(self, raw_message_id: Optional[str]) -> str:
        if not raw_message_id:
            return ""
        return str(raw_message_id).strip()[:128]

    def _has_group_context(self, message_obj) -> bool:
        raw_group_id = getattr(message_obj, "group_id", None)
        return raw_group_id is not None and str(raw_group_id).strip() != ""

    def determine_message_type(self, message_obj) -> str:
        msg_type = getattr(message_obj, 'type', None)
        if msg_type == MessageType.GROUP_MESSAGE:
            return "group"
        if msg_type == MessageType.FRIEND_MESSAGE:
            return "private"
        if self._has_group_context(message_obj):
            return "group"
        return "private"

    def extract_media_url(self, component, comp_data: dict) -> Optional[str]:
        from .serializer import extract_media_url
        return extract_media_url(comp_data)

    def extract_reply_to_id(self, component, comp_data: dict) -> Optional[str]:
        if comp_data.get("type") == "Reply":
            return comp_data.get("message_id") or comp_data.get("id")
        return None


class TelegramAdapter(PlatformAdapter):
    PLATFORM_NAME = "telegram"

    def normalize_message_id(self, raw_message_id: Optional[str]) -> str:
        if not raw_message_id:
            return ""
        try:
            return str(int(raw_message_id))
        except (ValueError, TypeError):
            return str(raw_message_id).strip()[:128]


class ChannelBasedAdapter(PlatformAdapter):
    """Channel-based 平台适配器

    适用于 group_id 代表 channel（而非传统群聊）的平台。
    GROUP_MESSAGE 记录为 "channel" 类型，extract_channel_id 从 group_id 提取。
    """

    def determine_message_type(self, message_obj) -> str:
        msg_type = getattr(message_obj, 'type', None)
        if msg_type == MessageType.GROUP_MESSAGE:
            return "channel"
        if msg_type == MessageType.FRIEND_MESSAGE:
            return "private"
        if self._has_group_context(message_obj):
            return "channel"
        return "private"

    def extract_channel_id(self, message_obj) -> Optional[str]:
        if message_obj.group_id:
            return str(message_obj.group_id)
        return None


_ADAPTER_REGISTRY: Dict[str, Type[PlatformAdapter]] = {
    # Telegram - numeric message_id
    "telegram": TelegramAdapter,
    # Channel-based platforms
    "discord": ChannelBasedAdapter,
    "slack": ChannelBasedAdapter,
    "mattermost": ChannelBasedAdapter,
    "kook": ChannelBasedAdapter,
    # 标准群聊/私聊平台
    "aiocqhttp": PlatformAdapter,
    "qq_official": PlatformAdapter,
    "qq_official_webhook": PlatformAdapter,
    "dingtalk": PlatformAdapter,
    "lark": PlatformAdapter,
    "wecom": PlatformAdapter,
    "wecom_ai_bot": PlatformAdapter,
    "weixin_oc": PlatformAdapter,
    "weixin_official_account": PlatformAdapter,
    "line": PlatformAdapter,
    "misskey": PlatformAdapter,
    "satori": PlatformAdapter,
    "webchat": PlatformAdapter,
}

_generic_adapter = PlatformAdapter()
_adapter_cache: Dict[str, PlatformAdapter] = {}


def get_adapter(platform_name: str) -> PlatformAdapter:
    if not platform_name:
        return _generic_adapter

    if platform_name in _adapter_cache:
        return _adapter_cache[platform_name]

    adapter_cls = _ADAPTER_REGISTRY.get(platform_name)
    if adapter_cls:
        adapter = adapter_cls()
    else:
        logger.debug(
            f"[FoxToolbox] 未注册的平台适配器: {platform_name}，使用通用适配器"
        )
        adapter = PlatformAdapter()

    _adapter_cache[platform_name] = adapter
    return adapter


def register_adapter(platform_name: str, adapter_cls: Type[PlatformAdapter]):
    _ADAPTER_REGISTRY[platform_name] = adapter_cls
    _adapter_cache.pop(platform_name, None)
    logger.info(f"[FoxToolbox] 已注册平台适配器: {platform_name}")
