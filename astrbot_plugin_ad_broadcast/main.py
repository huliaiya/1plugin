"""广告广播助手 - AstrBot 多平台定时广告广播插件。

本插件复刻自狐狸插件（astrbot_plugin_fox_toolbox）的广告助手功能
（fox_toolbox/dsgg/star.py，DsggFeature），该功能源自
astrbot_plugin_furry_dsgg（作者 furryHM-mrz，AGPL-3.0）。

与原插件（astrbot_plugin_furry_dsgg）的差异与改进：
- 修复了部分平台（如 Telegram）事件对象没有 bot 属性的兼容问题：
  广播发送不再使用 event.bot，而是通过 AstrBot context.send_message 向记录的
  群聊会话（unified_msg_origin）发送广告内容，全平台通用；
- 广播目标不再依赖 QQ 平台的群列表 API，插件自动记录所有平台群聊/频道会话；
- 支持平台级白名单/黑名单与群级开关（disable_gids 支持「群ID」与「平台:群ID」）；
- 广告内容以消息组件字典列表持久化，发送时重建 MessageChain，失败降级为纯文本。
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .serializer import serialize_message_chain

PLUGIN_DATA_DIR = "astrbot_plugin_ad_broadcast"


def _make_component(cls, ctype: str, item: dict):
    """把序列化后的组件字典还原为 AstrBot 组件对象。

    仅支持常见可跨平台组件；不支持的组件返回 None 由调用方跳过。
    """
    if ctype in ("plain", "text"):
        return cls(text=str(item.get("text") or ""))
    if ctype == "image":
        file = item.get("url") or item.get("file") or item.get("path") or ""
        if not file:
            return None
        if file.startswith(("http://", "https://")):
            return cls(file=file)
        if item.get("path") and os.path.exists(str(item.get("path"))):
            return cls.fromFileSystem(str(item.get("path")))
        return cls(file=file)
    if ctype in ("record", "video"):
        file = item.get("url") or item.get("file") or item.get("path") or ""
        if not file:
            return None
        return cls(file=file)
    if ctype == "file":
        name = item.get("name") or "file"
        file = item.get("file") or item.get("path") or ""
        return cls(name=str(name), file=str(file), url=item.get("url") or "")
    if ctype == "at":
        qq = item.get("qq")
        if qq is None:
            qq = item.get("user_id")
        qq = str(qq) if qq is not None else ""
        if not qq:
            return None
        if qq.lower() == "all":
            return __import__(
                "astrbot.core.message.components", fromlist=["AtAll"]
            ).AtAll()
        return cls(qq=qq)
    if ctype == "atall":
        return __import__(
            "astrbot.core.message.components", fromlist=["AtAll"]
        ).AtAll()
    if ctype == "face":
        return cls(id=int(item.get("id") or 0))
    if ctype == "reply":
        rid = item.get("message_id") or item.get("id") or 0
        return cls(id=rid)
    if ctype == "json":
        data = item.get("data") or item.get("content") or {}
        return cls(data=data)
    return None


class AdBroadcastStar(Star):
    """广告广播助手 Star。

    插件激活后自动记录所有平台群聊/频道会话，管理员可添加广告并设置定时广播
    时间点，到点后向所有启用且未禁用的群聊广播广告内容。

    指令：
    - /开启广告、/关闭广告（所有人，群级开关）
    - /广告群列表、/添加广告、/删除广告 <ID>、/广告列表、/查看广告 <ID>、
      /定时广告 <HH:MM[,HH:MM...]>、/停止广告（仅管理员）
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_DATA_DIR
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"[AdBroadcast] 创建数据目录失败: {e}")
        self.ads: list = []
        self.scheduled_times: list = []
        self.known_groups: dict = {}
        self.broadcast_task: asyncio.Task | None = None
        self.last_broadcast_minute: str | None = None
        self.save_groups_pending: bool = False
        self._load_ads()
        self._load_schedule()
        self._load_groups()

    async def initialize(self):
        """插件激活时启动定时广播任务（仅配置了定时时间点时）。"""
        if not self.config.get("dsgg_enabled", True):
            logger.info("[AdBroadcast] 广告广播助手未启用，跳过启动")
            return
        if self.scheduled_times and (
            self.broadcast_task is None or self.broadcast_task.done()
        ):
            self.broadcast_task = asyncio.create_task(self._scheduled_broadcast())

    async def terminate(self):
        """插件禁用/重载时停止定时任务并保存群列表。"""
        if self.broadcast_task and not self.broadcast_task.done():
            self.broadcast_task.cancel()
            try:
                await self.broadcast_task
            except (asyncio.CancelledError, Exception):
                pass
            self.broadcast_task = None
        if self.save_groups_pending:
            self._save_groups()
            self.save_groups_pending = False

    # ---------- 消息监听：记录群聊会话 ----------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """记录所有平台的群聊/频道会话，供广告广播使用。"""
        try:
            message_obj = getattr(event, "message_obj", None)
            if message_obj is None:
                return
            platform = self._event_platform(event)
            group_id = self._event_group_id(event)
            channel_id = self._event_channel_id(event)
            gid = group_id or channel_id
            if not gid:
                return
            mtype = str(getattr(message_obj, "type", "") or "").lower()
            if mtype not in ("group", "channel"):
                if group_id:
                    mtype = "group"
                elif channel_id:
                    mtype = "channel"
                else:
                    return
            umo = getattr(event, "unified_msg_origin", "") or ""
            self._record_group(platform, gid, umo, mtype)
        except Exception as e:
            logger.debug(f"[AdBroadcast] 记录群聊会话失败: {e}")

    # ---------- 数据持久化 ----------

    def _ads_path(self):
        return self.data_dir / "ads.json"

    def _schedule_path(self):
        return self.data_dir / "schedule.json"

    def _groups_path(self):
        return self.data_dir / "known_groups.json"

    def _load_ads(self):
        try:
            path = self._ads_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.ads = [a for a in data if isinstance(a, dict)]
                    return
            self.ads = []
        except Exception as e:
            logger.error(f"[AdBroadcast] 加载广告内容时出错: {e}")
            self.ads = []

    def _save_ads(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._ads_path().write_text(
                json.dumps(self.ads, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[AdBroadcast] 保存广告内容时出错: {e}")

    def _load_schedule(self):
        try:
            path = self._schedule_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.scheduled_times = [
                        str(t) for t in data if isinstance(t, str)
                    ]
                    return
            self.scheduled_times = []
        except Exception as e:
            logger.error(f"[AdBroadcast] 加载定时任务时间点时出错: {e}")
            self.scheduled_times = []

    def _save_schedule(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._schedule_path().write_text(
                json.dumps(self.scheduled_times, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[AdBroadcast] 保存定时任务时间点时出错: {e}")

    def _load_groups(self):
        try:
            path = self._groups_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.known_groups = {
                        str(k): v for k, v in data.items() if isinstance(v, dict)
                    }
                    return
            self.known_groups = {}
        except Exception as e:
            logger.error(f"[AdBroadcast] 加载群聊列表时出错: {e}")
            self.known_groups = {}

    def _save_groups(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._groups_path().write_text(
                json.dumps(self.known_groups, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[AdBroadcast] 保存群聊列表时出错: {e}")

    # ---------- 群聊记录 ----------

    def _record_group(self, platform: str, group_id, umo: str, message_type: str):
        """记录一个群聊会话，供广告广播使用。"""
        if message_type not in ("group", "channel"):
            return
        if not umo or not group_id:
            return
        gid = str(group_id)
        key = f"{platform}:{gid}"
        now = int(time.time())
        entry = self.known_groups.get(key)
        if entry is None:
            self.known_groups[key] = {
                "platform": platform,
                "group_id": gid,
                "group_name": "",
                "umo": umo,
                "last_seen": now,
            }
        else:
            entry["umo"] = umo
            entry["last_seen"] = now
        if not self.save_groups_pending:
            self.save_groups_pending = True
            asyncio.create_task(self._flush_groups())

    async def _flush_groups(self):
        """节流保存群列表：合并 5 秒内的多次记录，避免高频写盘。"""
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        if self.save_groups_pending:
            self.save_groups_pending = False
            self._save_groups()

    # ---------- 事件字段提取 ----------

    def _event_platform(self, event) -> str:
        try:
            return event.get_platform_name() or "unknown"
        except Exception:
            pass
        umo = getattr(event, "unified_msg_origin", "") or ""
        if ":" in umo:
            return umo.split(":", 1)[0]
        return "unknown"

    def _event_group_id(self, event):
        try:
            gid = getattr(event.message_obj, "group_id", None)
            if gid in (None, "", 0, "0"):
                return ""
            return str(gid)
        except Exception:
            return ""

    def _event_channel_id(self, event):
        try:
            cid = getattr(event.message_obj, "channel_id", None)
            if cid in (None, "", 0, "0"):
                return ""
            return str(cid)
        except Exception:
            return ""

    def _event_group(self, event, group_index: int | None = None):
        """获取当前事件对应的群会话；管理员可指定已记录群的序号。"""
        platform = self._event_platform(event)
        group_id = self._event_group_id(event)
        if group_index and callable(getattr(event, "is_admin", None)):
            try:
                if event.is_admin():
                    idx = int(group_index)
                    keys = sorted(self.known_groups.keys())
                    if 1 <= idx <= len(keys):
                        entry = self.known_groups[keys[idx - 1]]
                        platform = entry.get("platform", platform)
                        group_id = entry.get("group_id", group_id)
            except Exception:
                pass
        return platform, str(group_id) if group_id else ""

    # ---------- 过滤 ----------

    def _platform_allowed(self, platform: str) -> bool:
        try:
            allowed = self.config.get("dsgg_platforms", None)
            excluded = self.config.get("dsgg_exclude_platforms", None)
        except Exception:
            return True
        if allowed:
            if platform not in allowed:
                return False
        if excluded and platform in excluded:
            return False
        return True

    def _is_group_disabled(self, platform: str, group_id) -> bool:
        gid = str(group_id)
        try:
            gids = self.config.get("disable_gids", None) or []
        except Exception:
            return False
        for entry in gids:
            entry = str(entry)
            if ":" in entry:
                p, g = entry.split(":", 1)
                if p == platform and g == gid:
                    return True
            else:
                if entry == gid:
                    return True
        return False

    def _get_targets(self):
        """返回广播目标列表：[(platform, group_id, umo), ...]。"""
        targets = []
        for entry in self.known_groups.values():
            if not isinstance(entry, dict):
                continue
            platform = entry.get("platform", "")
            group_id = entry.get("group_id", "")
            umo = entry.get("umo", "")
            if not platform or not group_id or not umo:
                continue
            if not self._platform_allowed(platform):
                continue
            if self._is_group_disabled(platform, group_id):
                continue
            targets.append((platform, group_id, umo))
        targets.sort(key=lambda x: (x[0], x[1]))
        return targets

    # ---------- 发送 ----------

    def _build_chain(self, chain_data: list) -> MessageChain:
        """把保存的组件字典列表重建为 AstrBot MessageChain（跨平台）。"""
        chain = MessageChain()
        try:
            from astrbot.core.message.components import ComponentTypes
        except Exception:
            return chain
        for item in chain_data or []:
            if not isinstance(item, dict):
                continue
            ctype = str(item.get("type", "")).lower()
            cls = ComponentTypes.get(ctype)
            if cls is None:
                continue
            try:
                comp = _make_component(cls, ctype, item)
                if comp is not None:
                    chain.chain.append(comp)
            except Exception:
                continue
        return chain

    async def _send_to(self, umo: str, ad: dict):
        chain = self._build_chain(ad.get("content") or [])
        if not chain.chain:
            chain = MessageChain().message(ad.get("text") or "")
        await self.context.send_message(umo, chain)

    async def _broadcast(self):
        """向所有启用且未禁用的群聊广播一条随机广告。"""
        if not self.ads:
            logger.info("[AdBroadcast] 无广告内容，跳过广播")
            return
        targets = self._get_targets()
        if not targets:
            logger.info("[AdBroadcast] 没有可广播的群聊，跳过广播")
            return
        ad = random.choice(self.ads)
        try:
            interval = int(self.config.get("dsgg_send_interval", 0) or 0)
        except (TypeError, ValueError):
            interval = 0
        success_count = 0
        failure_count = 0
        for platform, group_id, umo in targets:
            try:
                await self._send_to(umo, ad)
                success_count += 1
            except Exception as e:
                failure_count += 1
                logger.warning(f"[AdBroadcast] 向 {platform}:{group_id} 发送广告失败: {e}")
            if interval > 0:
                await asyncio.sleep(interval)
            else:
                await asyncio.sleep(random.randint(1, 3))
        logger.info(
            f"[AdBroadcast] 定时广告发送完成 - 成功: {success_count}个群, "
            f"失败: {failure_count}个群"
        )

    # ---------- 定时任务 ----------

    async def _scheduled_broadcast(self):
        logger.info("[AdBroadcast] 定时广告任务已启动")
        while True:
            try:
                now = datetime.now()
                cur = f"{now.hour:02d}:{now.minute:02d}"
                if cur in self.scheduled_times and cur != self.last_broadcast_minute:
                    self.last_broadcast_minute = cur
                    if self.ads:
                        await self._broadcast()
                await asyncio.sleep(60 - now.second)
            except asyncio.CancelledError:
                logger.info("[AdBroadcast] 定时广告任务已取消")
                break
            except Exception as e:
                logger.error(f"[AdBroadcast] 定时广告任务出错: {e}")
                await asyncio.sleep(60)

    # ---------- 广告数据操作 ----------

    def _add_ad(self, chain_data: list, text: str) -> int:
        ad_id = max([ad.get("id", 0) for ad in self.ads], default=0) + 1
        self.ads.append(
            {
                "id": ad_id,
                "content": chain_data,
                "text": text or "",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self._save_ads()
        return ad_id

    def remove_ad(self, ad_id: int) -> str:
        for i, ad in enumerate(self.ads):
            if ad.get("id") == ad_id:
                del self.ads[i]
                self._save_ads()
                return f"已删除广告 ID: {ad_id}"
        return f"未找到广告 ID: {ad_id}"

    def get_ad(self, ad_id: int):
        for ad in self.ads:
            if ad.get("id") == ad_id:
                return ad
        return None

    def list_ads(self) -> str:
        if not self.ads:
            return "暂无广告内容，可使用 /添加广告 添加"
        lines = ["广告列表:"]
        for ad in self.ads:
            preview = (ad.get("text") or "")[:30]
            lines.append(
                f"ID: {ad.get('id')} (创建时间: {ad.get('created_at', '')}) {preview}"
            )
        return "\n".join(lines)

    def _content_info(self, ad: dict) -> str:
        content = ad.get("content") or []
        parts = []
        for item in content:
            if not isinstance(item, dict):
                parts.append("[未知内容]")
                continue
            t = item.get("type", "unknown")
            if t in ("Plain", "text"):
                text = str(item.get("text") or "")
                text = text[:50] + "..." if len(text) > 50 else text
                parts.append(f"[文字:{text}]" if text else "[文字]")
            elif t == "Image":
                parts.append("[图片]")
            elif t == "File":
                parts.append("[文件]")
            elif t == "Record":
                parts.append("[语音]")
            elif t == "Video":
                parts.append("[视频]")
            elif t == "At":
                parts.append("[@]")
            elif t == "AtAll":
                parts.append("[@全体]")
            elif t == "Face":
                parts.append("[表情]")
            elif t == "Reply":
                parts.append("[回复]")
            else:
                parts.append(f"[{t}]")
        return ", ".join(parts) if parts else "空内容"

    # ---------- 群开关 ----------

    async def enable_ad(self, event, group_index: int | None = None):
        """开启当前群（或指定序号群）的广告接收。"""
        platform, group_id = self._event_group(event, group_index)
        if not group_id:
            return "当前会话不是群聊，无法开启广告"
        key = f"{platform}:{group_id}"
        if self._is_group_disabled(platform, group_id):
            gids = list(self.config.get("disable_gids", None) or [])
            gids = [g for g in gids if g != key and g != group_id]
            self.config["disable_gids"] = gids
            self.config.save_config()
            return f"【{platform}:{group_id}】可以接收广告消息了"
        return f"【{platform}:{group_id}】已开启广告，无需重复开启"

    async def disable_ad(self, event, group_index: int | None = None):
        """关闭当前群（或指定序号群）的广告接收。"""
        platform, group_id = self._event_group(event, group_index)
        if not group_id:
            return "当前会话不是群聊，无法关闭广告"
        key = f"{platform}:{group_id}"
        if not self._is_group_disabled(platform, group_id):
            gids = list(self.config.get("disable_gids", None) or [])
            if key not in gids:
                gids.append(key)
            self.config["disable_gids"] = gids
            self.config.save_config()
            return f"【{platform}:{group_id}】不再接收广告消息"
        return f"【{platform}:{group_id}】已关闭广告，无需重复关闭"

    def group_list(self) -> str:
        if not self.known_groups:
            return "暂无已接入的群聊，插件收到过群消息后会自动记录"
        lines = ["广告群列表:"]
        for idx, (key, entry) in enumerate(sorted(self.known_groups.items()), 1):
            if not isinstance(entry, dict):
                continue
            platform = entry.get("platform", "")
            gid = entry.get("group_id", "")
            state = "关闭" if self._is_group_disabled(platform, gid) else "启用"
            lines.append(f"{idx}. [{platform}] {gid} {state}")
        return "\n".join(lines)

    # ---------- 定时设置 ----------

    def schedule(self, time_str: str | None = None) -> str:
        """设置/查询定时广告时间。time_str 为空时查询当前设置。"""
        if not time_str or not time_str.strip():
            if not self.scheduled_times:
                return "当前未设置定时广告时间，使用方法：/定时广告 09:00,14:30"
            return f"当前定时广告时间：{', '.join(self.scheduled_times)}"

        parsed = []
        for tp in time_str.split(","):
            tp = tp.strip()
            if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", tp):
                return f"时间格式错误: {tp}，正确格式如: 09:00"
            parsed.append(tp)
        parsed = sorted(set(parsed))
        self.scheduled_times = parsed
        self._save_schedule()

        if self.broadcast_task and not self.broadcast_task.done():
            self.broadcast_task.cancel()
            self.broadcast_task = None
        self.last_broadcast_minute = None
        if parsed:
            self.broadcast_task = asyncio.create_task(self._scheduled_broadcast())
            return f"已设置定时广告发送时间：{', '.join(parsed)}"
        return "定时广告已取消"

    def stop_schedule(self) -> str:
        if self.broadcast_task and not self.broadcast_task.done():
            self.broadcast_task.cancel()
            self.broadcast_task = None
            self.scheduled_times = []
            self._save_schedule()
            return "已停止定时广告发送"
        return "当前没有正在运行的定时广告任务"

    # ---------- 命令 ----------

    @filter.command("开启广告", alias={"开广告"})
    async def cmd_enable_ad(self, event: AstrMessageEvent, group_index: int | None = None):
        """开启广告 - 当前群聊可接收来自管理员的定时广告"""
        msg = await self.enable_ad(event, group_index)
        yield event.plain_result(msg)

    @filter.command("关闭广告", alias={"关广告"})
    async def cmd_disable_ad(self, event: AstrMessageEvent, group_index: int | None = None):
        """关闭广告 - 当前群聊不再接收定时广告"""
        msg = await self.disable_ad(event, group_index)
        yield event.plain_result(msg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("广告群列表")
    async def cmd_group_list(self, event: AstrMessageEvent):
        """广告群列表 - 查看所有已接入群聊及其广告接收状态"""
        yield event.plain_result(self.group_list())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("添加广告")
    async def cmd_add_ad(self, event: AstrMessageEvent):
        """添加广告 - 发送指令后 30 秒内发送要添加的广告内容"""
        yield event.plain_result("请30秒内发送要添加的广告内容（发送「取消」可中止）")
        try:
            from astrbot.core.utils.session_waiter import (  # noqa: PLC0415
                session_waiter,
                SessionController,
            )
        except Exception as e:
            logger.warning(f"[AdBroadcast] 会话等待模块不可用: {e}")
            yield event.plain_result("添加广告失败：会话等待模块不可用")
            return

        @session_waiter(timeout=30, record_history_chains=True)  # type: ignore
        async def wait_for_ad_content(
            controller: SessionController, event: AstrMessageEvent
        ):
            if event.message_str == "取消":
                await event.send(event.make_result().message("已取消添加广告"))
                controller.stop()
                return
            try:
                chain_data = serialize_message_chain(event.message_obj.message)
            except Exception:
                chain_data = []
            ad_id = self._add_ad(chain_data, event.message_str or "")
            await event.send(event.make_result().message(f"广告内容已添加，ID: {ad_id}"))
            controller.stop()

        try:
            await wait_for_ad_content(event)
        except TimeoutError:
            yield event.plain_result("等待超时！")
        except Exception as e:
            logger.warning(f"[AdBroadcast] 添加广告时出错: {e}")
            yield event.plain_result(f"添加广告失败：{e}")
        finally:
            event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除广告")
    async def cmd_remove_ad(self, event: AstrMessageEvent, ad_id: int):
        """删除广告 <ID> - 删除指定广告"""
        yield event.plain_result(self.remove_ad(ad_id))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("广告列表")
    async def cmd_list_ads(self, event: AstrMessageEvent):
        """广告列表 - 列出所有已添加的广告"""
        yield event.plain_result(self.list_ads())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查看广告")
    async def cmd_view_ad(self, event: AstrMessageEvent, ad_id: int):
        """查看广告 <ID> - 查看并预览指定广告内容"""
        ad = self.get_ad(ad_id)
        if ad is None:
            yield event.plain_result(f"未找到广告 ID: {ad_id}")
            return
        basic = (
            f"广告ID: {ad_id}\n"
            f"创建时间: {ad.get('created_at', '')}\n"
            f"内容: {self._content_info(ad)}"
        )
        yield event.plain_result(basic)
        umo = getattr(event, "unified_msg_origin", None)
        if umo:
            try:
                await self._send_to(umo, ad)
            except Exception as e:
                logger.warning(f"[AdBroadcast] 预览广告发送失败: {e}")
                yield event.plain_result("广告内容发送失败，可能包含不支持的元素")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("定时广告")
    async def cmd_schedule(self, event: AstrMessageEvent, time_str: str | None = None):
        """定时广告 <HH:MM[,HH:MM...]> - 设置定时广告发送时间"""
        yield event.plain_result(self.schedule(time_str))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("停止广告")
    async def cmd_stop_schedule(self, event: AstrMessageEvent):
        """停止广告 - 停止定时广告发送"""
        yield event.plain_result(self.stop_schedule())
