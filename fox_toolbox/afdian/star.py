"""爱发电功能实现（命令与订单通知逻辑）。

复刻自 astrbot_plugin_afdian/main.py（作者 Zhalslar）中的 AfdianPlugin，
适配狐狸插件的 MessageRecorder Star 结构：功能封装为独立 mixin，由
main.py 中的主 Star 类继承使用。
"""

import asyncio
import json
import time
import uuid
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import MessageChain

from .config import AfdianConfig
from .afdian_api import AfdianAPIClient
from .afdian_webhook import AfdianWebhookServer
from .order_db import OrderDB
from .utils import parse_order, parse_sponsors


class _MockAfdianClient:
    """测试用模拟客户端：替代真实 API，仅返回一份预设模拟订单。

    用于的「发电模拟」命令走真实的 `afdian_poll_once` 检测链路
    （拉单 → save_order_if_new 入库 → on_afdian_new_order 推送），
    不发起任何真实网络请求。
    """

    def __init__(self, order: dict):
        self._order = order

    async def query_order(self, page: int = 1, out_trade_no: str = "", per_page: int = 100) -> list:
        if page > 1:
            return []
        return [self._order]

    async def query_sponsor(self, *args, **kwargs) -> dict:
        return {}


def _db_order_to_dict(row: dict) -> dict:
    """把 OrderDB 行记录还原为 parse_order 可用的订单字典。"""
    order = dict(row)
    sku_detail = order.get("sku_detail")
    if not isinstance(sku_detail, list):
        if isinstance(sku_detail, str):
            try:
                sku_detail = json.loads(sku_detail)
            except (TypeError, ValueError):
                sku_detail = []
        else:
            sku_detail = []
    order["sku_detail"] = sku_detail
    return order


class AfdianFeature:
    """爱发电功能 mixin。

    依赖宿主 Star 提供：
    - self.config: AstrBotConfig（扁平键）
    - self.context: Context
    - self.data_dir: Path（插件数据目录）
    """

    def _init_afdian(self):
        """初始化爱发电组件（幂等）。"""
        self.afdian_cfg = AfdianConfig(self.config, self.data_dir)
        self.afdian_db = OrderDB(self.afdian_cfg.data_dir / "afdian" / "orders.db")
        self.afdian_server = AfdianWebhookServer(
            host=self.afdian_cfg.webhook_host,
            port=self.afdian_cfg.webhook_port,
            db=self.afdian_db,
            token=self.afdian_cfg.webhook_token,
        )
        self.afdian_client = AfdianAPIClient(
            user_id=self.afdian_cfg.user_id,
            token=self.afdian_cfg.token,
            base_url=self.afdian_cfg.base_url,
        )
        self.afdian_pending_orders: dict = {}
        self.afdian_bots = []
        self.afdian_started = False
        self.afdian_sync_task: asyncio.Task | None = None
        self.afdian_poll_task: asyncio.Task | None = None
        self.afdian_poll_window_end: float = 0.0

    @property
    def afdian_brand(self) -> tuple:
        """插件名与版本（用于图片水印），从 metadata.yaml 读取。"""
        if getattr(self, "_afdian_brand", None):
            return self._afdian_brand
        name = "狐狸插件"
        version = "2.6.7"
        try:
            meta_path = (
                Path(__file__).resolve().parent.parent.parent / "metadata.yaml"
            )
            if meta_path.exists():
                for line in meta_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("display_name:"):
                        name = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("version:"):
                        version = line.split(":", 1)[1].strip().strip('"\'')
        except Exception as e:
            logger.warning(f"[Afdian] 读取插件元数据失败，使用默认品牌信息: {e}")
        self._afdian_brand = (name, version)
        return self._afdian_brand

    def _afdian_t2i_template(self) -> str:
        """读取自定义文转图模板（顶部水印为插件名+版本）。"""
        tmpl_path = Path(__file__).resolve().parent / "t2i_template.html"
        try:
            return tmpl_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[Afdian] 读取自定义 T2I 模板失败: {e}")
            raise

    async def afdian_render_image(self, text: str) -> str:
        """使用自定义模板渲染文本为图片，顶部显示插件名+版本。

        优先使用自定义模板（网络渲染），失败时回退到 AstrBot 默认模板。
        """
        name, version = self.afdian_brand
        try:
            tmpl = self._afdian_t2i_template()
            return await self.html_render(
                tmpl,
                {"text": text, "plugin_name": name, "version": f"v{version}"},
                return_url=True,
            )
        except Exception as e:
            logger.warning(f"[Afdian] 自定义模板渲染失败，回退默认模板: {e}")
            return await self.text_to_image(text=text)

    async def afdian_sync_history_orders(self, max_pages: int = 100):
        """启动时拉取全部历史订单入库（按 out_trade_no 去重，只存新增）。

        分页拉取爱发电 API 的历史订单，逐条保存到订单库。
        :return: (拉取总数, 新增数) 便于调用方反馈
        """
        if not self.afdian_cfg.enabled or not self.afdian_cfg.ready():
            if self.afdian_cfg.enabled and not self.afdian_cfg.ready():
                logger.warning("[Afdian] API 凭据未配置，跳过历史订单同步")
            return 0, 0
        logger.info("[Afdian] 开始拉取历史订单...")
        page = 1
        added = 0
        total = 0
        while page <= max_pages:
            try:
                orders = await self.afdian_client.query_order(
                    page=page, per_page=100
                )
            except Exception as e:
                logger.warning(f"[Afdian] 拉取历史订单失败 page={page}: {e}")
                break
            if not orders:
                break
            total += len(orders)
            for order in orders:
                out_trade_no = order.get("out_trade_no")
                if not out_trade_no:
                    continue
                if await self.afdian_db.save_order_if_new(order):
                    added += 1
            page += 1
            if len(orders) < 100:
                break
        logger.info(
            f"[Afdian] 历史订单同步完成：共 {total} 条，新增 {added} 条"
        )
        return total, added

    async def _afdian_bind_mysql(self):
        """尝试将爱发电订单存储绑定到主插件的 MySQL 连接池（同库）。"""
        try:
            host_db = getattr(self, "_db", None)
            pool = getattr(host_db, "_pool", None) if host_db else None
            if pool is None:
                logger.warning("[Afdian] 主数据库未就绪，订单存储使用 SQLite 兜底")
                return
            await self.afdian_db.bind_mysql_pool(pool)
        except Exception as e:
            logger.warning(f"[Afdian] 绑定 MySQL 失败，使用 SQLite 兜底: {e}")

    async def afdian_start(self):
        """启动爱发电服务（功能开关关闭时静默跳过）。

        - 尝试启动 Webhook 服务（有公网时由爱发电平台主动推送）
        - 启动/重载时后台拉取历史订单入库（去重，只存新增）
        - 轮询为按需模式：用户 /发电 登记待确认订单后才启动限时轮询，
          无需在启动时预启动，避免无人发电时持续请求接口
        """
        if not self.afdian_cfg.enabled:
            logger.info("[Afdian] 爱发电功能未启用，跳过服务启动")
            return
        # 优先绑定主库 MySQL，失败时回退 SQLite（已在 OrderDB 内兜底）
        await self._afdian_bind_mysql()
        try:
            self.afdian_server.register_order_callback(self.on_afdian_new_order)
            await self.afdian_server.start()
            self.afdian_started = True
        except Exception as e:
            logger.error(f"[Afdian] 启动 Webhook 服务失败: {e}")
            self.afdian_started = False

        # 启动/重载时后台拉取历史订单入库（去重，只存新增）
        if self.afdian_sync_task is None or self.afdian_sync_task.done():
            self.afdian_sync_task = asyncio.create_task(
                self.afdian_sync_history_orders()
            )

    async def afdian_stop(self):
        """停止爱发电 Webhook 服务并关闭 API 客户端。"""
        if self.afdian_poll_task and not self.afdian_poll_task.done():
            self.afdian_poll_task.cancel()
            try:
                await self.afdian_poll_task
            except (asyncio.CancelledError, Exception):
                pass
            self.afdian_poll_task = None
        if self.afdian_sync_task and not self.afdian_sync_task.done():
            self.afdian_sync_task.cancel()
            try:
                await self.afdian_sync_task
            except (asyncio.CancelledError, Exception):
                pass
            self.afdian_sync_task = None
        try:
            if self.afdian_server:
                await self.afdian_server.stop()
        except Exception as e:
            logger.warning(f"[Afdian] 停止 Webhook 服务失败: {e}")
        try:
            if self.afdian_client:
                await self.afdian_client.close()
        except Exception as e:
            logger.warning(f"[Afdian] 关闭 API 客户端失败: {e}")

    async def on_afdian_new_order(self, order: dict | None = None):
        """处理新订单回调：通知订阅者 + 针对付款用户的自动回复。"""
        logger.info(f"[Afdian] 新订单：{order}")
        message = parse_order(order) if order else "Afdian Test"

        # 通知所有订阅会话
        for umo in self.afdian_cfg.notice_sessions:
            try:
                await self.context.send_message(
                    umo, MessageChain().message(message)
                )
            except Exception as e:
                logger.warning(f"[Afdian] 通知失败 订阅者 {umo}：{e}")

        # 通过 remark（记录为付款用户ID）识别特定用户订单，发送自动回复
        if order:
            sender_id = str(order.get("remark") or "")
            info = self.afdian_pending_orders.pop(sender_id, None)
            if info:
                umo = info.get("umo")
                try:
                    await self.context.send_message(
                        umo, MessageChain().message(self.afdian_cfg.default_reply)
                    )
                except Exception as e:
                    # 兜底：尝试调用 OneBot 私聊发送
                    if self.afdian_bots:
                        try:
                            await self.afdian_bots[0].send_private_msg(
                                user_id=int(sender_id), message=message
                            )
                        except Exception as e2:
                            logger.warning(
                                f"[Afdian] 兜底私聊发送失败 {sender_id}：{e2}"
                            )
                    else:
                        logger.warning(f"[Afdian] 特定用户通知失败 {umo}：{e}")

    # ---- 命令处理 ----

    async def afdian_create_order(self, event, price=None):
        """发电 <金额> —— 生成支付跳转链接。"""
        sender_id = str(event.get_sender_id())
        self.afdian_pending_orders[sender_id] = {
            "umo": event.unified_msg_origin,
            "created_at": time.time(),
        }

        # 记录 aiocqhttp bot 用于兜底私聊
        try:
            if event.get_platform_name() == "aiocqhttp":
                bot = getattr(event, "bot", None)
                if bot:
                    self.afdian_bots.clear()
                    self.afdian_bots.append(bot)
        except Exception:
            pass

        try:
            price = float(price) if price is not None else float(
                self.afdian_cfg.default_price
            )
        except (TypeError, ValueError):
            price = float(self.afdian_cfg.default_price)

        url = self.afdian_client.generate_payment_url(
            price=price, remark=str(sender_id)
        )

        # 无公网环境：优先用轮询检测新订单
        started = False
        if self.afdian_cfg.use_polling:
            started = await self.afdian_ensure_polling()

        if started:
            tip = f"请在 {self.afdian_cfg.poll_timeout // 60} 分钟内完成支付"
            return f"{url}\n{tip}"
        return url

    # ---- 无公网轮询 ----

    async def afdian_ensure_polling(self) -> bool:
        """按需启动限时轮询：仅当存在待确认订单时启动。

        由 /发电 命令在登记待确认订单后调用，并刷新轮询窗口
        （每次发电最多 poll_timeout 秒）；窗口到期或无待确认订单
        时轮询自动停止，避免无人发电时持续请求接口刷屏日志。
        """
        if not self.afdian_cfg.use_polling:
            return False
        if not self.afdian_pending_orders:
            return False
        self.afdian_poll_window_end = time.time() + self.afdian_cfg.poll_timeout
        if self.afdian_poll_task is None or self.afdian_poll_task.done():
            try:
                self.afdian_poll_task = asyncio.create_task(
                    self.afdian_poll_loop()
                )
                logger.info("[Afdian] 启动按需轮询检测任务")
            except Exception as e:
                logger.warning(f"[Afdian] 启动轮询任务失败: {e}")
                return False
        return True

    async def afdian_poll_loop(self):
        """按需限时轮询：发电后检测新订单，窗口到期或无待确认订单即停止。

        每笔待确认订单触发一个轮询窗口（最多 poll_timeout 秒，默认 5 分钟），
        窗口内每 poll_interval 秒（默认 5 秒）拉取一次订单；订单全部处理完
        或窗口超时后自动停止，不再持续请求接口避免刷屏日志。
        """
        try:
            # 等待历史订单同步完成，避免把历史订单误判为新订单触发通知
            if self.afdian_sync_task and not self.afdian_sync_task.done():
                try:
                    await self.afdian_sync_task
                except (asyncio.CancelledError, Exception):
                    pass
            interval = self.afdian_cfg.poll_interval
            while self.afdian_cfg.enabled:
                if not self.afdian_pending_orders:
                    logger.info("[Afdian] 无待确认订单，停止轮询")
                    break
                if time.time() >= self.afdian_poll_window_end:
                    logger.info("[Afdian] 轮询窗口到期，停止轮询")
                    break
                try:
                    await self._afdian_cleanup_expired_pending()
                    await self.afdian_poll_once()
                except Exception as e:
                    logger.warning(f"[Afdian] 轮询检测失败: {e}")
                await asyncio.sleep(interval)
        finally:
            self.afdian_poll_task = None

    async def _afdian_cleanup_expired_pending(self):
        """清理超时未支付的待确认订单，避免 pending 记录无限累积。"""
        timeout = self.afdian_cfg.poll_timeout
        now = time.time()
        expired = [
            sid
            for sid, info in self.afdian_pending_orders.items()
            if now - (info.get("created_at") or now) > timeout
        ]
        for sid in expired:
            self.afdian_pending_orders.pop(sid, None)
            logger.info(f"[Afdian] 订单等待支付超时，移除待确认记录 {sid}")

    async def afdian_poll_once(self, max_pages: int = 10):
        """执行一次轮询检测：拉取最近订单并处理新增订单。

        循环拉取订单页，遇到已存在订单即停止（订单按创建时间倒序，
        已存在说明该页之后更早的订单均已处理过），避免漏掉积压新单。
        仅处理本地库中不存在的订单，避免 Webhook 与轮询重复通知。
        """
        for page in range(1, max_pages + 1):
            orders = await self.afdian_client.query_order(page=page, per_page=100)
            if not orders:
                return
            found_known = False
            for order in orders:
                out_trade_no = order.get("out_trade_no")
                if not out_trade_no:
                    continue
                is_new = await self.afdian_db.save_order_if_new(order)
                if not is_new:
                    found_known = True
                    continue
                logger.info(f"[Afdian] 轮询发现新订单：{out_trade_no}")
                await self.on_afdian_new_order(order)
            # 本页已出现已入库订单：后续页只会更早，停止拉取
            if found_known:
                return
            if len(orders) < 100:
                return

    async def afdian_query_order(self, event, out_trade_no: str):
        """查询订单 <订单号> —— 查询指定订单详情。"""
        orders = await self.afdian_client.query_order(out_trade_no=out_trade_no)
        if not orders:
            return "未找到该订单"
        texts = [parse_order(order) for order in orders]
        return "\n\n".join(texts)

    async def afdian_query_sponsor(self, event, sponsor_user_ids=None):
        """查询发电 —— 查询收到的赞助记录。

        默认查询全部赞助者（不传入自己的 user_id 作筛选，避免查空）；
        仅当无任何赞助关系记录时，回退展示本地已同步的历史订单，
        保证查询结果始终有内容。
        """
        sponsor_user_ids = (sponsor_user_ids or "").strip()
        sponsors = await self.afdian_client.query_sponsor(
            sponsor_user_ids=sponsor_user_ids
        )
        if sponsors and sponsors.get("list"):
            sponsor_list = parse_sponsors(sponsors)
            return "\n\n".join(sponsor_list)
        orders = await self.afdian_db.get_all_orders()
        if orders:
            return "\n\n".join(parse_order(_db_order_to_dict(o)) for o in orders)
        return "未找到赞助记录"

    async def afdian_simulate_new_order(self, event) -> str:
        """模拟一笔新订单并走完整检测/推送链路（测试用）。

        构造一笔模拟订单，注入 mock API 客户端后调用 `afdian_poll_once`：
        query_order 拉单 → save_order_if_new 入库 → on_afdian_new_order
        推送到所有已设置的通知会话（推送群），并匹配备注向付款人回复。
        返回文本描述模拟结果（订单号、入库状态、推送会话数）。
        """
        sender_id = str(event.get_sender_id())
        now = int(time.time())
        order = {
            "out_trade_no": f"TEST{now}-{uuid.uuid4().hex[:6]}",
            "user_id": f"sim_{sender_id}",
            "user_name": f"模拟用户({sender_id})",
            "user_private_id": "",
            "plan_id": "0",
            "plan_title": "模拟赞助订单",
            "month": 1,
            "total_amount": self.afdian_cfg.default_price,
            "show_amount": self.afdian_cfg.default_price,
            "status": 2,
            "product_type": 0,
            "discount": "0.00",
            "remark": sender_id,
            "redeem_id": "",
            "sku_detail": [{"name": "测试商品", "count": 1, "sku_id": "SKU_TEST"}],
            "address_person": "",
            "address_phone": "",
            "address_address": "",
            "create_time": now,
        }
        # 登记待确认订单，模拟用户已发起发电
        self.afdian_pending_orders[sender_id] = {
            "umo": event.unified_msg_origin,
            "created_at": time.time(),
        }
        # 记录 aiocqhttp bot 用于兜底私聊
        try:
            if event.get_platform_name() == "aiocqhttp":
                bot = getattr(event, "bot", None)
                if bot:
                    self.afdian_bots.clear()
                    self.afdian_bots.append(bot)
        except Exception:
            pass

        original_client = self.afdian_client
        self.afdian_client = _MockAfdianClient(order)
        try:
            await self.afdian_poll_once()
        finally:
            self.afdian_client = original_client

        sessions = self.afdian_cfg.notice_sessions
        if not sessions:
            return (
                f"模拟订单 {order['out_trade_no']} 已生成并入库，"
                "但当前未设置通知会话，请先使用「开启发电通知」添加推送群"
            )
        return (
            f"模拟订单 {order['out_trade_no']} 已检测并入库，"
            f"已推送到 {len(sessions)} 个通知会话：{', '.join(sessions)}"
        )

    async def afdian_add_notice_session(self, event, umo=None):
        """开启发电通知 —— 在当前会话接收爱发电订单通知。"""
        umo = umo or event.unified_msg_origin
        self.afdian_cfg.add_notice_session(umo)
        return f"[爱发电]：已添加 {umo} 为通知会话"