"""广告助手功能模块

复刻自 furryHM-mrz 的 astrbot_plugin_furry_dsgg（v1.0.3，AGPL-3.0），
在保留原插件「定时向群聊广播广告」功能的基础上，改为基于统一消息来源
（unified_msg_origin）的多平台广播实现：不再依赖 QQ 平台的群列表 API，
而是记录插件所见过的所有群聊会话，通过 AstrBot context.send_message
向任意平台群聊发送广告，并支持按平台白名单/黑名单过滤。
"""

from .star import DsggFeature

__all__ = ["DsggFeature"]
