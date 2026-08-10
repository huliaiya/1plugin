"""广告助手功能实现（多平台广告广播）。

复刻自 astrbot_plugin_furry_dsgg/main.py（作者 furryHM-mrz，AGPL-3.0）
中的 NobotPlugin 广告功能，适配狐狸插件的 MessageRecorder Star 结构：
功能封装为独立 mixin，由 main.py 中的主 Star 类继承使用。

与原插件的差异：
- 广播目标不再依赖 QQ 平台的 get_group_list 群列表 API，而是记录插件
  所见过的所有群聊/频道会话（platform + group_id + unified_msg_origin），
  通过 AstrBot context.send_message 向任意平台群聊发送广告；
- 新增平台级开关：dsgg_platforms（白名单）与 dsgg_exclude_platforms
  （黑名单），默认全部平台参与广播；
- disable_gids 支持「群ID」与「平台:群ID」两种格式，可精确到平台；
- 广告内容以 AstrBot 消息组件字典列表保存（跨平台通用），发送时重建
  MessageChain，失败时降级为纯文本。
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime

from astrbot.api import logger
from astrbot.api.event import MessageChain


def _dsgg_make_component(cls, ctype: str, item: dict):
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


class DsggFeature:
    """广告助手功能 mixin。

    依赖宿主 Star 提供：
    - self.config: AstrBotConfig（扁平键）
    - self.context: Context
    - self.data_dir: Path（插件数据目录）
    """

    def _init_dsgg(self):
        self.dsgg_ads: list = []
        self.dsgg_scheduled_times: list = []
        self.dsgg_known_groups: dict = {}
        self.dsgg_broadcast_task: asyncio.Task | None = None
        self.dsgg_last_broadcast_minute: str | None = None
        self.dsgg_save_groups_pending: bool = False
        self.dsgg_data_dir = self.data_dir / "dsgg"
        try:
            self.dsgg_data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"[Dsgg] 创建数据目录失败: {e}")
        self._dsgg_load_ads()
        self._dsgg_load_schedule()
        self._dsgg_load_groups()

    async def dsgg_start(self):
        """启动广告助手：配置启用且存在定时时间点时启动定时广播任务。"""
        if not self.config.get("dsgg_enabled", True):
            logger.info("[Dsgg] 广告助手未启用，跳过启动")
            return
        if self.dsgg_scheduled_times and (
            self.dsgg_broadcast_task is None or self.dsgg_broadcast_task.done()
        ):
            self.dsgg_broadcast_task = asyncio.create_task(
                self._dsgg_scheduled_broadcast()
            )

    async def dsgg_stop(self):
        """停止广告助手定时广播任务。"""
        if self.dsgg_broadcast_task and not self.dsgg_broadcast_task.done():
            self.dsgg_broadcast_task.cancel()
            try:
                await self.dsgg_broadcast_task
            except (asyncio.CancelledError, Exception):
                pass
            self.dsgg_broadcast_task = None
        # 保存可能积压的群列表
        if self.dsgg_save_groups_pending:
            self._dsgg_save_groups()
            self.dsgg_save_groups_pending = False

    # ---------- 数据持久化 ----------

    def _dsgg_ads_path(self):
        return self.dsgg_data_dir / "ads.json"

    def _dsgg_schedule_path(self):
        return self.dsgg_data_dir / "schedule.json"

    def _dsgg_groups_path(self):
        return self.dsgg_data_dir / "known_groups.json"

    def _dsgg_load_ads(self):
        try:
            path = self._dsgg_ads_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.dsgg_ads = [a for a in data if isinstance(a, dict)]
                    return
            self.dsgg_ads = []
        except Exception as e:
            logger.error(f"[Dsgg] 加载广告内容时出错: {e}")
            self.dsgg_ads = []

    def _dsgg_save_ads(self):
        try:
            self.dsgg_data_dir.mkdir(parents=True, exist_ok=True)
            self._dsgg_ads_path().write_text(
                json.dumps(self.dsgg_ads, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[Dsgg] 保存广告内容时出错: {e}")

    def _dsgg_load_schedule(self):
        try:
            path = self._dsgg_schedule_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.dsgg_scheduled_times = [
                        str(t) for t in data if isinstance(t, str)
                    ]
                    return
            self.dsgg_scheduled_times = []
        except Exception as e:
            logger.error(f"[Dsgg] 加载定时任务时间点时出错: {e}")
            self.dsgg_scheduled_times = []

    def _dsgg_save_schedule(self):
        try:
            self.dsgg_data_dir.mkdir(parents=True, exist_ok=True)
            self._dsgg_schedule_path().write_text(
                json.dumps(self.dsgg_scheduled_times, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[Dsgg] 保存定时任务时间点时出错: {e}")

    def _dsgg_load_groups(self):
        try:
            path = self._dsgg_groups_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.dsgg_known_groups = {
                        str(k): v for k, v in data.items() if isinstance(v, dict)
                    }
                    return
            self.dsgg_known_groups = {}
        except Exception as e:
            logger.error(f"[Dsgg] 加载群聊列表时出错: {e}")
            self.dsgg_known_groups = {}

    def _dsgg_save_groups(self):
        try:
            self.dsgg_data_dir.mkdir(parents=True, exist_ok=True)
            self._dsgg_groups_path().write_text(
                json.dumps(self.dsgg_known_groups, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[Dsgg] 保存群聊列表时出错: {e}")

    # ---------- 群聊记录 ----------

    def _dsgg_record_group(self, platform: str, group_id, umo: str, message_type: str):
        """记录一个群聊会话，供广告广播使用。"""
        if message_type not in ("group", "channel"):
            return
        if not umo or not group_id:
            return
        gid = str(group_id)
        key = f"{platform}:{gid}"
        now = int(time.time())
        entry = self.dsgg_known_groups.get(key)
        if entry is None:
            self.dsgg_known_groups[key] = {
                "platform": platform,
                "group_id": gid,
                "group_name": "",
                "umo": umo,
                "last_seen": now,
            }
        else:
            entry["umo"] = umo
            entry["last_seen"] = now
        if not self.dsgg_save_groups_pending:
            self.dsgg_save_groups_pending = True
            asyncio.create_task(self._dsgg_flush_groups())

    async def _dsgg_flush_groups(self):
        """节流保存群列表：合并 5 秒内的多次记录，避免高频写盘。"""
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        if self.dsgg_save_groups_pending:
            self.dsgg_save_groups_pending = False
            self._dsgg_save_groups()

    # ---------- 过滤 ----------

    def _dsgg_platform_allowed(self, platform: str) -> bool:
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

    def _dsgg_is_group_disabled(self, platform: str, group_id) -> bool:
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

    def _dsgg_get_targets(self):
        """返回广播目标列表：[(platform, group_id, umo), ...]。"""
        targets = []
        for entry in self.dsgg_known_groups.values():
            if not isinstance(entry, dict):
                continue
            platform = entry.get("platform", "")
            group_id = entry.get("group_id", "")
            umo = entry.get("umo", "")
            if not platform or not group_id or not umo:
                continue
            if not self._dsgg_platform_allowed(platform):
                continue
            if self._dsgg_is_group_disabled(platform, group_id):
                continue
            targets.append((platform, group_id, umo))
        targets.sort(key=lambda x: (x[0], x[1]))
        return targets

    # ---------- 发送 ----------

    def _dsgg_build_chain(self, chain_data: list) -> MessageChain:
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
                comp = _dsgg_make_component(cls, ctype, item)
                if comp is not None:
                    chain.chain.append(comp)
            except Exception:
                continue
        return chain

    async def _dsgg_send_to(self, umo: str, ad: dict):
        chain = self._dsgg_build_chain(ad.get("content") or [])
        if not chain.chain:
            chain = MessageChain().message(ad.get("text") or "")
        await self.context.send_message(umo, chain)

    async def dsgg_send_ad_to(self, umo: str, ad: dict):
        await self._dsgg_send_to(umo, ad)

    async def _dsgg_broadcast(self):
        """向所有启用且未禁用的群聊广播一条随机广告。"""
        ads = self.dsgg_ads
        if not ads:
            logger.info("[Dsgg] 无广告内容，跳过广播")
            return
        targets = self._dsgg_get_targets()
        if not targets:
            logger.info("[Dsgg] 没有可广播的群聊，跳过广播")
            return
        ad = random.choice(ads)
        try:
            interval = int(self.config.get("dsgg_send_interval", 0) or 0)
        except (TypeError, ValueError):
            interval = 0
        success_count = 0
        failure_count = 0
        for platform, group_id, umo in targets:
            try:
                await self._dsgg_send_to(umo, ad)
                success_count += 1
            except Exception as e:
                failure_count += 1
                logger.warning(f"[Dsgg] 向 {platform}:{group_id} 发送广告失败: {e}")
            if interval > 0:
                await asyncio.sleep(interval)
            else:
                await asyncio.sleep(random.randint(1, 3))
        logger.info(
            f"[Dsgg] 定时广告发送完成 - 成功: {success_count}个群, "
            f"失败: {failure_count}个群"
        )

    # ---------- 定时任务 ----------

    async def _dsgg_scheduled_broadcast(self):
        logger.info("[Dsgg] 定时广告任务已启动")
        while True:
            try:
                now = datetime.now()
                cur = f"{now.hour:02d}:{now.minute:02d}"
                if cur in self.dsgg_scheduled_times and cur != self.dsgg_last_broadcast_minute:
                    self.dsgg_last_broadcast_minute = cur
                    if self.dsgg_ads:
                        await self._dsgg_broadcast()
                await asyncio.sleep(60 - now.second)
            except asyncio.CancelledError:
                logger.info("[Dsgg] 定时广告任务已取消")
                break
            except Exception as e:
                logger.error(f"[Dsgg] 定时广告任务出错: {e}")
                await asyncio.sleep(60)

    # ---------- 命令逻辑 ----------

    def _dsgg_event_platform(self, event) -> str:
        try:
            return event.get_platform_name() or "unknown"
        except Exception:
            pass
        umo = getattr(event, "unified_msg_origin", "") or ""
        if ":" in umo:
            return umo.split(":", 1)[0]
        return "unknown"

    def _dsgg_event_group_id(self, event):
        try:
            message_obj = getattr(event, "message_obj", None)
            gid = getattr(message_obj, "group_id", None) if message_obj else None
            if gid is None:
                get_group_id = getattr(event, "get_group_id", None)
                if callable(get_group_id):
                    gid = get_group_id()
            if gid in (None, "", 0, "0"):
                return ""
            return str(gid)
        except Exception:
            return ""

    def _dsgg_event_group(self, event, group_index: int | None = None):
        """获取当前事件对应的群会话；管理员可指定已记录群的序号。"""
        platform = self._dsgg_event_platform(event)
        group_id = self._dsgg_event_group_id(event)
        if group_index and callable(getattr(event, "is_admin", None)):
            try:
                if event.is_admin():
                    idx = int(group_index)
                    keys = sorted(self.dsgg_known_groups.keys())
                    if 1 <= idx <= len(keys):
                        entry = self.dsgg_known_groups[keys[idx - 1]]
                        platform = entry.get("platform", platform)
                        group_id = entry.get("group_id", group_id)
            except Exception:
                pass
        return platform, str(group_id) if group_id else ""

    async def dsgg_enable_ad(self, event, group_index: int | None = None):
        """开启当前群（或指定序号群）的广告接收。"""
        platform, group_id = self._dsgg_event_group(event, group_index)
        if not group_id:
            return "当前会话不是群聊，无法开启广告"
        key = f"{platform}:{group_id}"
        if self._dsgg_is_group_disabled(platform, group_id):
            gids = list(self.config.get("disable_gids", None) or [])
            gids = [g for g in gids if g != key and g != group_id]
            self.config["disable_gids"] = gids
            self.config.save_config()
            return f"【{platform}:{group_id}】可以接收广告消息了"
        return f"【{platform}:{group_id}】已开启广告，无需重复开启"

    async def dsgg_disable_ad(self, event, group_index: int | None = None):
        """关闭当前群（或指定序号群）的广告接收。"""
        platform, group_id = self._dsgg_event_group(event, group_index)
        if not group_id:
            return "当前会话不是群聊，无法关闭广告"
        key = f"{platform}:{group_id}"
        if not self._dsgg_is_group_disabled(platform, group_id):
            gids = list(self.config.get("disable_gids", None) or [])
            if key not in gids:
                gids.append(key)
            self.config["disable_gids"] = gids
            self.config.save_config()
            return f"【{platform}:{group_id}】不再接收广告消息"
        return f"【{platform}:{group_id}】已关闭广告，无需重复关闭"

    def dsgg_group_list(self):
        if not self.dsgg_known_groups:
            return "暂无已接入的群聊，插件收到过群消息后会自动记录"
        lines = ["广告群列表:"]
        for idx, (key, entry) in enumerate(sorted(self.dsgg_known_groups.items()), 1):
            if not isinstance(entry, dict):
                continue
            platform = entry.get("platform", "")
            gid = entry.get("group_id", "")
            state = "关闭" if self._dsgg_is_group_disabled(platform, gid) else "启用"
            lines.append(f"{idx}. [{platform}] {gid} {state}")
        return "\n".join(lines)

    def _dsgg_add_ad(self, chain_data: list, text: str) -> int:
        ad_id = max([ad.get("id", 0) for ad in self.dsgg_ads], default=0) + 1
        self.dsgg_ads.append(
            {
                "id": ad_id,
                "content": chain_data,
                "text": text or "",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self._dsgg_save_ads()
        return ad_id

    def dsgg_remove_ad(self, ad_id: int) -> str:
        for i, ad in enumerate(self.dsgg_ads):
            if ad.get("id") == ad_id:
                del self.dsgg_ads[i]
                self._dsgg_save_ads()
                return f"已删除广告 ID: {ad_id}"
        return f"未找到广告 ID: {ad_id}"

    def dsgg_get_ad(self, ad_id: int):
        for ad in self.dsgg_ads:
            if ad.get("id") == ad_id:
                return ad
        return None

    def dsgg_list_ads(self) -> str:
        if not self.dsgg_ads:
            return "暂无广告内容，可使用 /添加广告 添加"
        lines = ["广告列表:"]
        for ad in self.dsgg_ads:
            preview = (ad.get("text") or "")[:30]
            lines.append(
                f"ID: {ad.get('id')} (创建时间: {ad.get('created_at', '')}) {preview}"
            )
        return "\n".join(lines)

    def _dsgg_content_info(self, ad: dict) -> str:
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

    def dsgg_schedule(self, time_str: str | None = None) -> str:
        """设置/查询定时广告时间。time_str 为空时查询当前设置。"""
        if not time_str or not time_str.strip():
            if not self.dsgg_scheduled_times:
                return "当前未设置定时广告时间，使用方法：/定时广告 09:00,14:30"
            return f"当前定时广告时间：{', '.join(self.dsgg_scheduled_times)}"

        parsed = []
        for tp in time_str.split(","):
            tp = tp.strip()
            if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", tp):
                return f"时间格式错误: {tp}，正确格式如: 09:00"
            parsed.append(tp)
        parsed = sorted(set(parsed))
        self.dsgg_scheduled_times = parsed
        self._dsgg_save_schedule()

        if self.dsgg_broadcast_task and not self.dsgg_broadcast_task.done():
            self.dsgg_broadcast_task.cancel()
            self.dsgg_broadcast_task = None
        self.dsgg_last_broadcast_minute = None
        if parsed:
            self.dsgg_broadcast_task = asyncio.create_task(
                self._dsgg_scheduled_broadcast()
            )
            return f"已设置定时广告发送时间：{', '.join(parsed)}"
        return "定时广告已取消"

    def dsgg_stop_schedule(self) -> str:
        if self.dsgg_broadcast_task and not self.dsgg_broadcast_task.done():
            self.dsgg_broadcast_task.cancel()
            self.dsgg_broadcast_task = None
            self.dsgg_scheduled_times = []
            self._dsgg_save_schedule()
            return "已停止定时广告发送"
        return "当前没有正在运行的定时广告任务"
