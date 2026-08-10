"""消息组件序列化模块 - 将 AstrBot MessageChain 序列化为可持久化的字典列表。

本模块移植自狐狸插件（astrbot_plugin_fox_toolbox）的 fox_toolbox/serializer.py，
仅保留广告助手所需的序列化部分。
"""

import json
from typing import Any, List

MEDIA_COMPONENT_TYPES = {"Image", "Record", "Video", "File"}

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
            continue
    return chain_data
