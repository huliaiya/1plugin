"""消息组件序列化模块 - 全面覆盖 AstrBot 所有消息组件类型"""

import json
from typing import Optional, List, Any

MEDIA_COMPONENT_TYPES = {"Image", "Record", "Video", "File"}

COMPONENT_TYPE_MEDIA_MAP = {
    "Image": "images",
    "Record": "records",
    "Video": "videos",
    "File": "files",
}

_INTERACTIVE_COMPONENT_TYPES = {"At", "AtAll", "Face", "Reply", "Poke"}
_RICH_MEDIA_COMPONENT_TYPES = {
    "Xml", "Json", "Card", "Music", "TTS",
    "Forward", "Contact", "Location", "Markdown",
    "Rps", "Dice", "Shake", "MiniApp",
}

ALL_KNOWN_COMPONENT_TYPES = (
    {"Plain"}
    | MEDIA_COMPONENT_TYPES
    | _INTERACTIVE_COMPONENT_TYPES
    | _RICH_MEDIA_COMPONENT_TYPES
)

_PREFERRED_ATTRS = {
    "Plain": ["text"],
    "Image": ["url", "file", "file_id", "file_unique_id", "width", "height", "path"],
    "Record": ["url", "file", "file_id", "path"],
    "Video": ["url", "file", "file_id", "width", "height", "path"],
    "File": ["url", "file", "file_id", "file_unique_id", "name", "path"],
    "At": ["user_id", "qq", "name"],
    "AtAll": [],
    "Face": ["id", "name"],
    "Reply": ["id", "message_id", "sender_id", "text", "time"],
    "Poke": ["id", "type"],
    "Xml": ["data", "content"],
    "Json": ["data", "content"],
    "Card": ["data"],
    "Music": ["url", "title", "content", "image"],
    "TTS": ["text", "url"],
    "Forward": ["id", "content", "nodes"],
    "Contact": ["id", "type"],
    "Location": ["lat", "lon", "title", "content"],
    "Markdown": ["content", "data"],
    "Rps": ["id"],
    "Dice": ["id"],
    "Shake": [],
    "MiniApp": ["data", "content"],
}

_SKIP_ATTRS = {"_sa_instance_state"}


def serialize_component(component) -> dict:
    result = {"type": component.__class__.__name__}

    comp_type = result["type"]
    preferred = _PREFERRED_ATTRS.get(comp_type, [])

    for attr in preferred:
        if hasattr(component, attr):
            value = getattr(component, attr)
            if value is not None:
                result[attr] = _serialize_value(value)

    # 仅对未在 _PREFERRED_ATTRS 中注册的组件类型做 dir() 回退扫描
    if comp_type in _PREFERRED_ATTRS:
        return result

    for attr in dir(component):
        if attr.startswith("_") or attr in _SKIP_ATTRS:
            continue
        if attr in result:
            continue
        if callable(getattr(type(component), attr, None)) and not isinstance(
            getattr(type(component), attr, None), property
        ):
            continue
        try:
            value = getattr(component, attr)
        except Exception:
            continue
        if value is None:
            continue
        if callable(value):
            continue
        result[attr] = _serialize_value(value)

    return result


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def serialize_message_chain(message_chain) -> List[dict]:
    if not message_chain:
        return []
    chain_data = []
    for comp in message_chain:
        try:
            chain_data.append(serialize_component(comp))
        except Exception:
            chain_data.append({"type": comp.__class__.__name__, "_serialize_error": True})
    return chain_data


def extract_reply_info(chain_data: List[dict]) -> Optional[str]:
    for comp in chain_data:
        if not isinstance(comp, dict):
            continue
        comp_type = comp.get("type", "")
        if comp_type == "Reply":
            return comp.get("message_id") or comp.get("id")
    return None


def extract_media_url(comp_data: dict) -> Optional[str]:
    """提取媒体引用（url / file / path 中的第一个非空值）。

    不再限制必须 http 开头：OneBot 实现返回的可能是 http CDN 链接、
    ``file:///`` URI、``base64://`` 负载、裸本地路径或裸文件名/hash。
    能否真正下载交给 MediaDownloader（MediaResolver + OneBot 兜底）判断，
    这里只负责把所有可能的引用都交出去，避免在提取阶段就静默丢弃。
    """
    for key in ("url", "file", "path"):
        val = comp_data.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def compute_content_hash(platform: str, session_id: str, sender_id: str,
                         message_str: Optional[str], timestamp: int) -> str:
    import hashlib
    raw = f"{platform}|{session_id}|{sender_id}|{message_str or ''}|{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def extract_media_paths(message_chain_json: Optional[str]) -> List[str]:
    if not message_chain_json:
        return []
    try:
        chain = json.loads(message_chain_json)
        if not isinstance(chain, list):
            return []
        paths = []
        for comp in chain:
            if isinstance(comp, dict) and "local_path" in comp:
                lp = comp["local_path"]
                if isinstance(lp, str) and lp:
                    paths.append(lp)
        return paths
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
