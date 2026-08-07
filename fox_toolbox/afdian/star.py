"""爱发电功能实现（命令与订单通知逻辑）。

复刻自 astrbot_plugin_afdian/main.py（作者 Zhalslar）中的 AfdianPlugin，
适配狐狸插件的 MessageRecorder Star 结构：功能封装为独立 mixin，由
main.py 中的主 Star 类继承使用。
"""

import asyncio

from astrbot.api import logger
from astrbot.api.event import MessageChain

from .config import AfdianConfig
from .afdian_api import AfdianAPIClient
from .afdian_webhook import AfdianWebhookServer
from .order_db import OrderDB
from .utils import parse_order, parse_sponsors


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
        )
        self.afdian_client = AfdianAPIClient(
            user_id=self.afdian_cfg.user_id,
            token=self.afdian_cfg.token,
            base_url=self.afdian_cfg.base_url,
        )
        self.afdian_pending_orders: dict = {}
        self.afdian_bots = []
        self.afdian_started = False

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
        """启动爱发电 Webhook 服务（功能开关关闭或端口被占用时静默跳过）。"""
        if not self.afdian_cfg.enabled:
            logger.info("[Afdian] 爱发电功能未启用，跳过 Webhook 启动")
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

    async def afdian_stop(self):
        """停止爱发电 Webhook 服务并关闭 API 客户端。"""
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
            sender_id = order.get("remark") or ""
            if sender_id in self.afdian_pending_orders:
                umo = self.afdian_pending_orders.pop(sender_id)
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
        sender_id = event.get_sender_id()
        self.afdian_pending_orders[sender_id] = event.unified_msg_origin

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
        return url

    async def afdian_query_order(self, event, out_trade_no: str):
        """查询订单 <订单号> —— 查询指定订单详情。"""
        orders = await self.afdian_client.query_order(out_trade_no=out_trade_no)
        if not orders:
            return "未找到该订单"
        texts = [parse_order(order) for order in orders]
        return "\n\n".join(texts)

    async def afdian_query_sponsor(self, event, sponsor_user_ids=None):
        """查询发电 —— 查询收到的赞助记录。"""
        sponsor_user_ids = sponsor_user_ids or self.afdian_cfg.user_id
        sponsors = await self.afdian_client.query_sponsor(
            sponsor_user_ids=sponsor_user_ids
        )
        if not sponsors or not sponsors.get("list"):
            return "未找到赞助记录"
        sponsor_list = parse_sponsors(sponsors)
        return "\n\n".join(sponsor_list)

    async def afdian_add_notice_session(self, event, umo=None):
        """开启发电通知 —— 在当前会话接收爱发电订单通知。"""
        umo = umo or event.unified_msg_origin
        self.afdian_cfg.add_notice_session(umo)
        return f"[爱发电]：已添加 {umo} 为通知会话"