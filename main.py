"""狐狸插件 - AstrBot 消息记录器插件主入口（MySQL 5.7 存储）"""

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
from fox_toolbox.db_explorer import DbExplorer
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
from fox_toolbox.snapshot_renderer import render_snapshot

MAX_CONCURRENT_SAVES = 8
MAX_CONCURRENT_DOWNLOADS = 4

# 内容类型 -> 摘要文本的映射
_CONTENT_TYPE_LABELS = {
    "Plain": "",
    "Image": "[图片]",
    "File": "[文件]",
    "FileDocument": "[文档]",
    "FileAudio": "[音频]",
    "FileArchive": "[压缩包]",
    "FileCode": "[代码]",
    "FileImage": "[图片文件]",
    "FileVideo": "[视频文件]",
    "Video": "[视频]",
    "Record": "[语音]",
    "At": "[@]",
    "AtAll": "[@全体]",
    "Face": "[表情]",
    "Reply": "[回复]",
    "Xml": "[XML]",
    "Json": "[JSON]",
    "Card": "[卡片]",
    "Music": "[音乐分享]",
    "TTS": "[TTS]",
    "Forward": "[合并转发]",
    "Contact": "[名片]",
    "Location": "[位置]",
    "Markdown": "[Markdown]",
    "Rps": "[猜拳]",
    "Dice": "[骰子]",
    "Shake": "[抖动窗口]",
    "MiniApp": "[小程序]",
    "Poke": "[戳一戳]",
}

# 文件扩展名 -> 子类型分类
_FILE_EXT_CATEGORIES = {
    # 文档
    "pdf": "FileDocument", "doc": "FileDocument", "docx": "FileDocument",
    "xls": "FileDocument", "xlsx": "FileDocument", "ppt": "FileDocument",
    "pptx": "FileDocument", "txt": "FileDocument", "md": "FileDocument",
    "wps": "FileDocument", "odt": "FileDocument", "ods": "FileDocument",
    "odp": "FileDocument", "rtf": "FileDocument", "pages": "FileDocument",
    "epub": "FileDocument", "mobi": "FileDocument",
    "csv": "FileDocument", "log": "FileDocument", "key": "FileDocument",
    "numbers": "FileDocument", "tex": "FileDocument", "chm": "FileDocument",
    "djvu": "FileDocument", "fb2": "FileDocument", "azw": "FileDocument",
    "azw3": "FileDocument",
    # 音频（非语音消息的音频文件）
    "mp3": "FileAudio", "flac": "FileAudio", "aac": "FileAudio",
    "m4a": "FileAudio", "wma": "FileAudio", "ogg": "FileAudio",
    "ape": "FileAudio", "alac": "FileAudio", "opus": "FileAudio",
    "mid": "FileAudio", "midi": "FileAudio",
    "wav": "FileAudio", "amr": "FileAudio", "aiff": "FileAudio",
    "au": "FileAudio", "dsf": "FileAudio", "dff": "FileAudio",
    "mka": "FileAudio", "weba": "FileAudio",
    # 压缩包
    "zip": "FileArchive", "rar": "FileArchive", "7z": "FileArchive",
    "tar": "FileArchive", "gz": "FileArchive", "bz2": "FileArchive",
    "xz": "FileArchive", "tgz": "FileArchive",
    "iso": "FileArchive", "jar": "FileArchive", "cab": "FileArchive",
    "deb": "FileArchive", "rpm": "FileArchive", "pkg": "FileArchive",
    "msi": "FileArchive", "lz": "FileArchive", "lzma": "FileArchive",
    "zst": "FileArchive", "ar": "FileArchive", "cpio": "FileArchive",
    # 代码/程序
    "py": "FileCode", "js": "FileCode", "ts": "FileCode", "java": "FileCode",
    "c": "FileCode", "cpp": "FileCode", "h": "FileCode", "go": "FileCode",
    "rs": "FileCode", "rb": "FileCode", "php": "FileCode", "sh": "FileCode",
    "html": "FileCode", "css": "FileCode", "json": "FileCode", "xml": "FileCode",
    "yml": "FileCode", "yaml": "FileCode", "sql": "FileCode", "bat": "FileCode",
    "apk": "FileCode", "exe": "FileCode", "dmg": "FileCode", "ipa": "FileCode",
    "kt": "FileCode", "swift": "FileCode", "scala": "FileCode", "dart": "FileCode",
    "lua": "FileCode", "r": "FileCode", "jl": "FileCode", "clj": "FileCode",
    "ps1": "FileCode", "ini": "FileCode", "toml": "FileCode", "conf": "FileCode",
    "vim": "FileCode", "gradle": "FileCode", "cmake": "FileCode",
    "makefile": "FileCode", "dockerfile": "FileCode", "asm": "FileCode",
    "vbs": "FileCode", "pl": "FileCode", "groovy": "FileCode",
    "elixir": "FileCode", "erl": "FileCode", "hs": "FileCode", "ml": "FileCode",
    "fs": "FileCode", "nim": "FileCode", "cr": "FileCode", "zig": "FileCode",
    "v": "FileCode", "obj": "FileCode",
    # 图片文件（作为文件发送的图片，非 Image 组件）
    "jpg": "FileImage", "jpeg": "FileImage", "png": "FileImage",
    "gif": "FileImage", "webp": "FileImage", "bmp": "FileImage",
    "svg": "FileImage", "ico": "FileImage", "tiff": "FileImage",
    "heic": "FileImage", "heif": "FileImage", "raw": "FileImage",
    "psd": "FileImage", "cr2": "FileImage", "nef": "FileImage",
    "arw": "FileImage", "dng": "FileImage", "avif": "FileImage",
    "jfif": "FileImage", "hdr": "FileImage",
    # 视频文件（作为文件发送的视频，非 Video 组件）
    "mp4": "FileVideo", "avi": "FileVideo", "mkv": "FileVideo",
    "mov": "FileVideo", "wmv": "FileVideo", "flv": "FileVideo",
    "webm": "FileVideo", "m4v": "FileVideo", "3gp": "FileVideo",
    "mpeg": "FileVideo", "mpg": "FileVideo", "ts": "FileVideo",
    "vob": "FileVideo", "m2ts": "FileVideo", "f4v": "FileVideo",
    "ogv": "FileVideo", "mts": "FileVideo", "rm": "FileVideo",
    "rmvb": "FileVideo",
}


def _classify_file_component(comp_data: dict) -> str:
    """根据文件名/URL 扩展名分类 File 组件的子类型。
    
    返回子类型字符串（如 FileDocument, FileAudio 等），
    无法识别时返回 "File"。
    """
    # 尝试从 name、file、url、path 中提取文件名
    filename = ""
    for key in ("name", "file", "url", "path"):
        val = comp_data.get(key)
        if isinstance(val, str) and val:
            filename = val
            break
    
    if not filename:
        return "File"
    
    # 提取扩展名（小写，去掉查询参数）
    filename_clean = filename.split("?")[0].split("#")[0]
    if "." not in filename_clean:
        return "File"
    
    ext = filename_clean.rsplit(".", 1)[-1].lower()
    return _FILE_EXT_CATEGORIES.get(ext, "File")


def _generate_message_summary(chain_data: list) -> str:
    """从消息链生成摘要文本（用于 message_str 为空时的回退）"""
    if not chain_data:
        return ""
    parts = []
    for comp in chain_data:
        if not isinstance(comp, dict):
            continue
        comp_type = comp.get("type", "")
        if comp_type == "Plain":
            text = comp.get("text", "")
            if text:
                parts.append(text)
        else:
            label = _CONTENT_TYPE_LABELS.get(comp_type, f"[{comp_type}]")
            if label:
                parts.append(label)
    summary = "".join(parts).strip()
    # 限制长度
    if len(summary) > 200:
        summary = summary[:200] + "..."
    return summary


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
        self._tg_channel_handlers: list = []  # [(platform, handler), ...]

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
            logger.info(
                f"[FoxToolbox] 尝试连接 MySQL: "
                f"{mysql_config['host']}:{mysql_config['port']}/"
                f"{mysql_config['database']} (user={mysql_config['user']})"
            )
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
            # 数据库不可用时仍需注册页面/状态 API，保证 WebUI 可打开并显示错误原因
            setattr(self.context, "fox_toolbox_db_error", self._init_error)
            await self._register_web_apis()

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

        # 清理 Telegram 频道消息 handler
        for tg_platform, handler in self._tg_channel_handlers:
            try:
                tg_platform.application.remove_handler(handler)
            except Exception:
                pass
        self._tg_channel_handlers.clear()

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

    # ========== Telegram 频道消息捕获 ==========

    @filter.on_astrbot_loaded()
    async def _setup_telegram_channel_handler(self):
        """AstrBot 加载完成后，为 Telegram 平台注册频道消息 PTB handler。

        AstrBot 的 Telegram 适配器只处理 update.message，不处理 update.channel_post，
        导致 Telegram 频道消息被静默丢弃。这里通过在 PTB Application 上注册独立的
        handler 来捕获频道消息并直接保存到数据库。
        """
        if not self._check_initialized():
            return

        try:
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            tg_platforms = [
                p for p in self.context.platform_manager.platform_insts
                if isinstance(p, TelegramPlatformAdapter)
            ]

            if not tg_platforms:
                logger.debug("[FoxToolbox] 未找到 Telegram 平台实例，跳过频道消息 handler 注册")
                return

            from telegram.ext import MessageHandler as PTBMessageHandler
            from telegram.ext import filters as ptb_filters

            for tg_platform in tg_platforms:
                handler = PTBMessageHandler(
                    filters=ptb_filters.UpdateType.CHANNEL_POSTS,
                    callback=self._on_telegram_channel_post,
                )
                tg_platform.application.add_handler(handler)
                self._tg_channel_handlers.append((tg_platform, handler))
                logger.info(
                    f"[FoxToolbox] 已为 Telegram 平台 {tg_platform.meta().id} "
                    f"注册频道消息 handler"
                )
        except ImportError:
            logger.debug("[FoxToolbox] Telegram 适配器未安装，跳过频道消息 handler 注册")
        except Exception as e:
            logger.error(f"[FoxToolbox] 注册 Telegram 频道消息 handler 失败: {e}")

    async def _on_telegram_channel_post(self, update, context):
        """PTB 回调：处理 Telegram 频道帖子，直接保存到数据库。"""
        if not self._check_initialized():
            return

        post = update.channel_post
        if not post:
            return

        try:
            chat_id = str(post.chat.id)
            message_id = str(post.message_id)
            sender_id = str(post.sender_chat.id) if post.sender_chat else (
                str(post.from_user.id) if post.from_user else ""
            )
            sender_name = (
                post.sender_chat.title if post.sender_chat and post.sender_chat.title
                else (post.from_user.username if post.from_user else "Channel")
            )

            message_str = post.text or post.caption or ""

            chain_data = []
            content_types = []

            if post.text:
                chain_data.append({"type": "Plain", "text": post.text})
                content_types.append("Plain")
            if post.caption:
                if not message_str:
                    message_str = post.caption
                if not any(c.get("type") == "Plain" for c in chain_data):
                    chain_data.append({"type": "Plain", "text": post.caption})
                    content_types.append("Plain")
            if post.photo:
                chain_data.append({"type": "Image", "url": ""})
                content_types.append("Image")
            if post.video:
                chain_data.append({"type": "Video", "url": ""})
                content_types.append("Video")
            if post.document:
                chain_data.append({"type": "File", "name": post.document.file_name or "", "url": ""})
                content_types.append("File")
            if post.voice:
                chain_data.append({"type": "Record", "url": ""})
                content_types.append("Record")
            if post.sticker:
                chain_data.append({"type": "Image", "url": ""})
                content_types.append("Image")

            if not message_str:
                message_str = ""

            adapter = get_adapter("telegram")
            normalized_ts = normalize_timestamp(post.date.timestamp() if post.date else time.time())

            record = MessageRecord(
                platform="telegram",
                message_id=adapter.normalize_message_id(message_id),
                session_id=chat_id,
                group_id=chat_id,
                channel_id=chat_id,
                sender_id=adapter.normalize_sender_id(sender_id),
                sender_name=adapter.normalize_sender_name(sender_name),
                message_type="channel",
                message_str=message_str,
                timestamp=normalized_ts,
            )

            if chain_data:
                record.message_chain = json.dumps(chain_data, ensure_ascii=False)
                record.content_types = ",".join(content_types)

            record_id = await self._db.save_message(record)

            if record_id != -1:
                content_preview = (
                    (message_str[:30] + "...")
                    if message_str and len(message_str) > 30
                    else (message_str or "[非文本]")
                )
                logger.debug(
                    f"[FoxToolbox] 频道消息保存成功 #{record_id} | "
                    f"平台: telegram | 类型: channel | "
                    f"发送者: {sender_name} | 内容: {content_preview}"
                )
        except Exception as e:
            logger.error(f"[FoxToolbox] 保存 Telegram 频道消息失败: {e}")

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

                    # 提取内容类型，用于统计和搜索
                    # 对 File 组件根据扩展名进一步细分类别
                    comp_types = []
                    for c in chain_data:
                        if not isinstance(c, dict):
                            continue
                        raw_type = c.get("type", "")
                        if raw_type == "File":
                            # 细分文件子类型
                            subtype = _classify_file_component(c)
                            comp_types.append(subtype)
                        else:
                            comp_types.append(raw_type)
                    if comp_types:
                        record.content_types = ",".join(comp_types)

                    # 如果 message_str 为空，从消息链生成摘要
                    if not record.message_str:
                        record.message_str = _generate_message_summary(chain_data)

            # 即使没有消息链，也尝试设置一个基础的 message_str
            if not record.message_str:
                record.message_str = ""

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

    def _cmd_check(self, event):
        if not self._check_commands_enabled(event) or not self._api:
            return False
        return True

    def _fmt_msgs(self, messages, header, limit=50):
        lines = [header]
        for msg in messages[:limit]:
            ts = time.strftime("%m-%d %H:%M", time.localtime(msg.timestamp / 1000))
            c = (msg.message_str or "[非文本消息]")[:50]
            lines.append(f"[{ts}] {msg.sender_name or msg.sender_id}: {c}")
        return "\n".join(lines)

    @msg_record.command("stats")
    async def cmd_stats(self, event: AstrMessageEvent):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        try:
            stats = await self._api.get_stats()
        except Exception as e:
            yield event.plain_result(f"获取统计失败: {e}")
            return
        lines = [f"📊 消息记录统计\n总记录数: {stats.total_count}\n群聊消息: {stats.group_message_count}\n私聊消息: {stats.private_message_count}"]
        if stats.channel_message_count:
            lines.append(f"频道消息: {stats.channel_message_count}")
        if stats.platform_stats:
            lines.append("平台分布:\n" + "\n".join(f"  - {p}: {c}" for p, c in stats.platform_stats.items()))
        if stats.oldest_timestamp:
            lines.append("最早消息: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats.oldest_timestamp / 1000)))
        if stats.newest_timestamp:
            lines.append("最新消息: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats.newest_timestamp / 1000)))
        yield event.plain_result("\n".join(lines))

    @msg_record.command("cleanup")
    async def cmd_cleanup(self, event: AstrMessageEvent):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        try:
            result = await self._do_cleanup()
        except Exception as e:
            yield event.plain_result(f"清理失败: {e}")
            return
        yield event.plain_result(f"✅ 已清理 {result['by_age'] + result['by_limit']} 条消息记录")

    @msg_record.command("query")
    async def cmd_query(self, event: AstrMessageEvent, sender_id: str = "", limit: int = 10):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        limit = max(1, min(limit, 50))
        try:
            msgs = await self._api.query(sender_id=sender_id, limit=limit)
        except Exception as e:
            yield event.plain_result(f"查询失败: {e}")
            return
        if not msgs:
            yield event.plain_result("未找到消息记录")
            return
        yield event.plain_result(self._fmt_msgs(msgs, f"📝 查询到 {len(msgs)} 条消息:"))

    @msg_record.command("search")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str, limit: int = 10):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        limit = max(1, min(limit, 50))
        try:
            msgs = await self._api.search(keyword, limit=limit)
        except Exception as e:
            yield event.plain_result(f"搜索失败: {e}")
            return
        if not msgs:
            yield event.plain_result(f"未找到包含 '{keyword}' 的消息")
            return
        yield event.plain_result(self._fmt_msgs(msgs, f"🔍 找到 {len(msgs)} 条包含 '{keyword}' 的消息:"))

    @msg_record.command("help")
    async def cmd_help(self, event: AstrMessageEvent):
        if not self._check_commands_enabled(event):
            return
        yield event.plain_result("""📖 消息记录器帮助

📊 统计与管理:
/msg_record stats - 查看统计信息
/msg_record snapshot - 生成 WebUI 仪表盘快照图
/msg_record cleanup - 手动清理过期消息

📝 时间查询:
/msg_record today [limit] - 查看今天的消息
/msg_record yesterday [limit] - 查看昨天的消息
/msg_record history [time_range] [limit] - 按时间查询
  时间范围: last7d、last30d、week、month 或日期如 2024-01-01

🔍 查询与搜索:
/msg_record query [sender_id] [limit] - 按发送者查询消息
/msg_record search <keyword> [limit] - 全文搜索消息

🗂️ 数据库浏览（只读）:
/msg_record tables - 查看数据库中的业务表列表

选项: limit 默认 10，最大 50""")

    @msg_record.command("today")
    async def cmd_today(self, event: AstrMessageEvent, limit: int = 20):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        limit = max(1, min(limit, 50))
        try:
            msgs = await self._api.get_today(limit=limit)
        except Exception as e:
            yield event.plain_result(f"查询失败: {e}")
            return
        if not msgs:
            yield event.plain_result("今天暂无消息记录")
            return
        yield event.plain_result(self._fmt_msgs(msgs, f"📅 今天共 {len(msgs)} 条消息:"))

    @msg_record.command("yesterday")
    async def cmd_yesterday(self, event: AstrMessageEvent, limit: int = 20):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        limit = max(1, min(limit, 50))
        try:
            msgs = await self._api.get_yesterday(limit=limit)
        except Exception as e:
            yield event.plain_result(f"查询失败: {e}")
            return
        if not msgs:
            yield event.plain_result("昨天暂无消息记录")
            return
        yield event.plain_result(self._fmt_msgs(msgs, f"📅 昨天共 {len(msgs)} 条消息:"))

    @msg_record.command("history")
    async def cmd_history(self, event: AstrMessageEvent, time_range: str = "week", limit: int = 30):
        if not self._cmd_check(event):
            if not self._api: yield event.plain_result("数据库未初始化")
            return
        limit = max(1, min(limit, 50))
        try:
            start_time, end_time = parse_time_range(time_range)
            time_desc = format_time_range(start_time, end_time)
            msgs = await self._api.query(time=time_range, limit=limit)
        except Exception as e:
            yield event.plain_result(f"查询失败: {e}")
            return
        if not msgs:
            yield event.plain_result(f"在 {time_desc} 期间暂无消息记录")
            return
        yield event.plain_result(self._fmt_msgs(msgs, f"📅 {time_desc} 共 {len(msgs)} 条消息:"))

    @msg_record.command("tables")
    async def cmd_tables(self, event: AstrMessageEvent):
        """查看数据库中已创建的数据表（只读浏览）

        参考 astrbot_plugin_mysql（作者 Chris95743）的表浏览设计。
        """
        if not self._db:
            yield event.plain_result("数据库未初始化")
            return
        explorer = DbExplorer(self._db)
        try:
            tables = await explorer.list_tables()
        except Exception as e:
            yield event.plain_result(f"获取数据表失败: {e}")
            return
        if not tables:
            yield event.plain_result("数据库中暂无业务表")
            return
        lines = [f"🗂️ 数据库共 {len(tables)} 张业务表:"]
        for t in tables:
            row_text = f"{t['row_count']} 行" if t["row_count"] >= 0 else "?"
            lines.append(f"  - {t['name']}（{row_text}）")
        yield event.plain_result("\n".join(lines))

    @msg_record.command("snapshot")
    async def cmd_snapshot(self, event: AstrMessageEvent):
        """生成 WebUI 仪表盘快照图片并发送。

        用 Pillow 将数据库统计数据渲染成与 WebUI 风格一致的 PNG，
        包含统计卡片、时间趋势、发送者/群组排行、内容类型分布。
        数据库不可用时降级返回文本提示。
        """
        if not self._check_initialized() or not self._db:
            yield event.plain_result("数据库未初始化，无法生成快照")
            return
        try:
            stats = await self._db.get_stats()
            table_count = await self._db.get_table_count()
            timeline = await self._db.get_timeline_stats(interval="day")
            sender_ranking = await self._db.get_sender_ranking(limit=8)
            group_ranking = await self._db.get_group_ranking(limit=8)
            content_types = await self._db.get_content_type_stats()
        except Exception as e:
            yield event.plain_result(f"生成快照失败: {e}")
            return

        if stats.total_count == 0:
            yield event.plain_result("暂无消息记录，无法生成快照")
            return

        png_data = await asyncio.to_thread(
            render_snapshot,
            stats,
            max(table_count, 0),
            timeline,
            sender_ranking,
            group_ranking,
            content_types,
            stats.platform_stats or {},
        )

        from fox_toolbox.web_api import _get_plugin_data_dir
        temp_dir = _get_plugin_data_dir() / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = temp_dir / f"snapshot_{int(time.time() * 1000)}.png"
        snapshot_path.write_bytes(png_data)

        try:
            yield event.image_result(str(snapshot_path))
        finally:
            try:
                snapshot_path.unlink(missing_ok=True)
            except Exception:
                pass
