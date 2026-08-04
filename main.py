"""狐狸工具箱 - AstrBot 消息记录器插件主入口（MySQL 5.7 存储）"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional, Any

plugin_root = Path(__file__).parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

from fox_toolbox.database import Database
from fox_toolbox.api import MessageRecorderAPI
from fox_toolbox.models import MessageRecord
from fox_toolbox.time_utils import parse_time_range, format_time_range, normalize_timestamp
from fox_toolbox.media_downloader import MediaDownloader, MEDIA_TYPE_MAP
from fox_toolbox.serializer import (
    serialize_message_chain,
    extract_reply_info,
    extract_media_url as serializer_extract_media_url,
)
from fox_toolbox.platform_adapter import get_adapter
from fox_toolbox.web_api import register_all_web_apis, cleanup_expired_tasks

MAX_CONCURRENT_SAVES = 8
MAX_CONCURRENT_DOWNLOADS = 4


class MessageRecorder(Star):
    """消息记录器插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._db: Optional[Database] = None
        self._api: Optional[MessageRecorderAPI] = None
        self._media_downloader: Optional[MediaDownloader] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._web_cleanup_task: Optional[asyncio.Task] = None
        self._pending_tasks: set = set()
        self._save_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SAVES)
        self._download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self._initialized: bool = False
        self._init_error: Optional[str] = None

    async def initialize(self):
        """插件初始化"""
        try:
            mysql_config = {
                "host": self.config.get("mysql_host", "127.0.0.1"),
                "port": int(self.config.get("mysql_port", 3306)),
                "user": self.config.get("mysql_user", "root"),
                "password": self.config.get("mysql_password", ""),
                "database": self.config.get("mysql_database", "fox_toolbox"),
            }
            self._db = Database("astrbot_plugin_fox_toolbox", mysql_config)
            await self._db.init()

            if self.config.get("save_media_files", False):
                image_save_mode = self.config.get("image_save_mode", "original")
                self._media_downloader = MediaDownloader(
                    "astrbot_plugin_fox_toolbox",
                    image_save_mode=image_save_mode,
                )
                logger.info(
                    f"[FoxToolbox] 多媒体文件保存已启用，"
                    f"图片模式: {image_save_mode}"
                )

            self._api = MessageRecorderAPI(self._db, self._media_downloader)

            self._start_cleanup_task()
            await self._register_web_apis()
            self._web_cleanup_task = asyncio.create_task(cleanup_expired_tasks())
            self._initialized = True
            logger.info("[FoxToolbox] 插件初始化完成")
        except Exception as e:
            self._initialized = False
            self._init_error = str(e)
            self._db = None
            self._api = None
            self._media_downloader = None
            logger.error(f"[FoxToolbox] 初始化失败: {e}")

    def _check_initialized(self) -> bool:
        if not self._initialized:
            logger.warning(f"[FoxToolbox] 插件未初始化或初始化失败: {self._init_error}")
            return False
        return True

    async def terminate(self):
        """插件终止"""
        if self._pending_tasks:
            for task in self._pending_tasks:
                task.cancel()
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._web_cleanup_task:
            self._web_cleanup_task.cancel()
            try:
                await self._web_cleanup_task
            except asyncio.CancelledError:
                pass

        if self._media_downloader:
            await self._media_downloader.close()

        if self._db:
            await self._db.close()
        logger.info("[FoxToolbox] 插件已终止")

    def _start_cleanup_task(self):
        interval_hours = self.config.get("cleanup_interval_hours", 24)
        if interval_hours <= 0:
            return
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(interval_hours)
        )

    async def _cleanup_loop(self, interval_hours: int):
        interval_seconds = interval_hours * 3600
        while True:
            try:
                await self._do_cleanup()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[FoxToolbox] 清理任务出错: {e}")

    async def _do_cleanup(self) -> dict:
        result = {"by_age": 0, "by_limit": 0, "media_files": 0}
        if not self._db:
            return result

        retention_days = self.config.get("retention_days", 30)
        if retention_days > 0:
            deleted, media_paths = await self._db.cleanup_by_age(retention_days)
            result["by_age"] = deleted
            if self._media_downloader and media_paths:
                unreferenced = await self._db.get_unreferenced_media_paths(media_paths)
                result["media_files"] += self._media_downloader.delete_media_files(
                    unreferenced
                )

        max_records = self.config.get("max_records", 100000)
        if max_records > 0:
            deleted, media_paths = await self._db.cleanup_by_limit(max_records)
            result["by_limit"] = deleted
            if self._media_downloader and media_paths:
                unreferenced = await self._db.get_unreferenced_media_paths(media_paths)
                result["media_files"] += self._media_downloader.delete_media_files(
                    unreferenced
                )

        total = result["by_age"] + result["by_limit"]
        if total > 0:
            logger.info(
                f"[FoxToolbox] 已清理 {total} 条消息记录，"
                f"{result['media_files']} 个媒体文件"
            )

        return result

    def get_api(self) -> Optional[MessageRecorderAPI]:
        return self._api

    async def _register_web_apis(self):
        try:
            await register_all_web_apis(self.context, self._db)
            logger.info("[FoxToolbox] Web API 已注册到 AstrBot Dashboard")
        except Exception as e:
            logger.error(f"[FoxToolbox] 注册 Web API 失败: {e}")

    # ========== 消息监听 ==========

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not self._check_initialized():
            return

        task = asyncio.create_task(self._save_message_async(event))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _save_message_async(self, event: AstrMessageEvent):
        async with self._save_semaphore:
            await self._do_save_message(event)

    async def _do_save_message(self, event: AstrMessageEvent):
        logger.debug("[FoxToolbox] 收到消息事件，开始处理")

        try:
            message_obj = event.message_obj
            platform = self._get_platform_name(event)
            adapter = get_adapter(platform)

            normalized_timestamp = normalize_timestamp(message_obj.timestamp)

            sender_id = adapter.normalize_sender_id(
                message_obj.sender.user_id if message_obj.sender else ""
            )
            sender_name = adapter.normalize_sender_name(
                message_obj.sender.nickname if message_obj.sender else None
            )
            group_id = adapter.normalize_group_id(message_obj.group_id)
            raw_channel_id = adapter.extract_channel_id(message_obj)
            channel_id = adapter.normalize_channel_id(raw_channel_id)
            message_id = adapter.normalize_message_id(message_obj.message_id)
            message_type = adapter.determine_message_type(message_obj)

            record = MessageRecord(
                platform=platform,
                message_id=message_id,
                session_id=message_obj.session_id or "",
                group_id=group_id,
                channel_id=channel_id,
                sender_id=sender_id,
                sender_name=sender_name,
                message_type=message_type,
                message_str=event.message_str,
                timestamp=normalized_timestamp,
            )

            if self.config.get("save_message_chain", True):
                message_chain = message_obj.message
                if message_chain:
                    chain_data = serialize_message_chain(message_chain)

                    reply_to = extract_reply_info(chain_data)
                    if reply_to:
                        record.reply_to_id = adapter.normalize_message_id(reply_to)

                    if self._media_downloader and self.config.get("save_media_files", False):
                        download_tasks = [
                            self._download_media_for_component(comp, comp_data, adapter, event)
                            for comp, comp_data in zip(message_chain, chain_data)
                            if comp_data.get("type") in MEDIA_TYPE_MAP
                        ]
                        if download_tasks:
                            await asyncio.gather(*download_tasks, return_exceptions=True)

                    record.message_chain = json.dumps(chain_data, ensure_ascii=False)

            if self.config.get("save_raw_message", False):
                raw_msg = message_obj.raw_message
                if raw_msg:
                    try:
                        record.raw_message = json.dumps(raw_msg, ensure_ascii=False)
                    except (TypeError, ValueError):
                        record.raw_message = str(raw_msg)

            record_id = await self._db.save_message(record)

            if record_id == -1:
                return

            content_preview = (
                (event.message_str[:30] + "...")
                if event.message_str and len(event.message_str) > 30
                else (event.message_str or "[非文本]")
            )

            logger.debug(
                f"[FoxToolbox] 消息保存成功 #{record_id} | "
                f"平台: {platform} | 类型: {record.message_type} | "
                f"发送者: {record.sender_name or record.sender_id} | "
                f"内容: {content_preview}"
            )

        except Exception as e:
            logger.error(f"[FoxToolbox] 保存消息失败: {e}")

    def _get_platform_name(self, event: AstrMessageEvent) -> str:
        try:
            return event.get_platform_name() or "unknown"
        except Exception:
            return "unknown"

    async def _download_media_for_component(self, component, comp_data: dict, adapter, event):
        comp_type = comp_data.get("type", "")
        if comp_type not in MEDIA_TYPE_MAP:
            return

        url = adapter.extract_media_url(component, comp_data)
        if not url:
            url = serializer_extract_media_url(comp_data)
        if not url:
            return

        bot_api = self._get_bot_api(event)

        async with self._download_semaphore:
            try:
                filename = None
                if comp_type == "File" and hasattr(component, "name") and component.name:
                    filename = component.name

                local_path = await self._media_downloader.download_media(
                    url=url,
                    component_type=comp_type,
                    filename=filename,
                    bot_api=bot_api,
                )
                if local_path:
                    comp_data["local_path"] = local_path
            except Exception as e:
                logger.warning(
                    f"[FoxToolbox] 下载多媒体文件失败 "
                    f"(type={comp_type}): {e}"
                )

    def _get_bot_api(self, event) -> Optional[Any]:
        """从事件获取 OneBot api 对象（需支持 call_action，主要用于 aiocqhttp 兜底）。

        非 OneBot 平台或不支持 call_action 时返回 None，此时下载器仅使用
        MediaResolver + aiohttp，不会调用 OneBot get_image / download_file。
        """
        try:
            bot = getattr(event, 'bot', None)
            if bot is None:
                return None
            api = getattr(bot, 'api', None)
            if api is not None and hasattr(api, 'call_action'):
                return api
            if hasattr(bot, 'call_action'):
                return bot
        except Exception:
            pass
        return None

    def _check_commands_enabled(self, event: AstrMessageEvent) -> bool:
        return self.config.get("enable_commands", True)

    # ========== 管理指令 ==========

    @filter.command_group("msg_record")
    def msg_record():
        pass

    @msg_record.command("stats")
    async def cmd_stats(self, event: AstrMessageEvent):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        stats = await self._api.get_stats()

        lines = [
            "📊 消息记录统计",
            f"总记录数: {stats.total_count}",
            f"群聊消息: {stats.group_message_count}",
            f"私聊消息: {stats.private_message_count}",
        ]

        if stats.channel_message_count:
            lines.append(f"频道消息: {stats.channel_message_count}")

        if stats.platform_stats:
            lines.append("平台分布:")
            for platform, count in stats.platform_stats.items():
                lines.append(f"  - {platform}: {count}")

        if stats.oldest_timestamp:
            oldest_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stats.oldest_timestamp / 1000)
            )
            lines.append(f"最早消息: {oldest_time}")

        if stats.newest_timestamp:
            newest_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stats.newest_timestamp / 1000)
            )
            lines.append(f"最新消息: {newest_time}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("cleanup")
    async def cmd_cleanup(self, event: AstrMessageEvent):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        result = await self._do_cleanup()
        total = result["by_age"] + result["by_limit"]

        yield event.plain_result(f"✅ 已清理 {total} 条消息记录")

    @msg_record.command("query")
    async def cmd_query(self, event: AstrMessageEvent, sender: str = "", limit: int = 10):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.query(sender_id=sender, limit=limit)

        if not messages:
            yield event.plain_result("未找到消息记录")
            return

        lines = [f"📝 查询到 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("search")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str, limit: int = 10):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.search(keyword, limit=limit)

        if not messages:
            yield event.plain_result(f"未找到包含 '{keyword}' 的消息")
            return

        lines = [f"🔍 找到 {len(messages)} 条包含 '{keyword}' 的消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("help")
    async def cmd_help(self, event: AstrMessageEvent):
        if not self._check_commands_enabled(event):
            return
        help_text = """📖 消息记录器帮助

📊 统计与管理:
/msg_record stats - 查看统计信息
/msg_record cleanup - 手动清理

📝 时间查询:
/msg_record today - 查看今天的消息
/msg_record yesterday - 查看昨天的消息
/msg_record history <时间范围> - 按时间查询
  时间范围支持: last7d、last30d、week、month
  或日期: 2024-01-01、2024-01-01~2024-01-15

🔍 其他查询:
/msg_record query [sender_id] [limit] - 查询消息
/msg_record search <关键词> [limit] - 搜索消息

其他插件可通过 get_api() 方法调用查询接口。"""
        yield event.plain_result(help_text)

    @msg_record.command("today")
    async def cmd_today(self, event: AstrMessageEvent, limit: int = 20):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.get_today(limit=limit)

        if not messages:
            yield event.plain_result("今天暂无消息记录")
            return

        lines = [f"📅 今天共 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("yesterday")
    async def cmd_yesterday(self, event: AstrMessageEvent, limit: int = 20):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.get_yesterday(limit=limit)

        if not messages:
            yield event.plain_result("昨天暂无消息记录")
            return

        lines = [f"📅 昨天共 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("history")
    async def cmd_history(self, event: AstrMessageEvent, time_range: str = "week", limit: int = 30):
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        start_time, end_time = parse_time_range(time_range)
        time_desc = format_time_range(start_time, end_time)

        messages = await self._api.query(time=time_range, limit=limit)

        if not messages:
            yield event.plain_result(f"在 {time_desc} 期间暂无消息记录")
            return

        lines = [f"📅 {time_desc} 共 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))
