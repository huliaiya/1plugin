"""爱发电 Webhook 服务（异步）。

复刻自 astrbot_plugin_afdian/core/afdian_webhook.py（作者 Zhalslar）。
监听爱发电平台主动推送的订单消息，保存订单并触发回调。
"""

import asyncio
import errno
import hmac
import json

from aiohttp import web

from astrbot.api import logger


class AfdianWebhookServer:
    def __init__(self, host: str, port: int, db=None, token: str = ""):
        self.host = host
        self.port = port
        self.db = db
        self._token = token or ""
        self._order_callback = None
        self.app = web.Application()
        self.runner = None
        self.site = None
        self._started = False
        self._callback_tasks = set()
        self.app.add_routes(
            [
                web.post("/", self.receive_webhook),
                web.get("/orders", self.list_orders),
            ]
        )

    def _auth_ok(self, request: web.Request) -> bool:
        """校验请求携带的 webhook 令牌。

        未配置令牌时返回 True（向后兼容）；配置后要求 URL query 中的
        ``token`` 与配置值一致。爱发电回调 URL 可携带 query 参数。
        令牌比较使用恒定时间算法，避免时序侧信道泄露。
        """
        if not self._token:
            return True
        request_token = request.query.get("token", "")
        return hmac.compare_digest(request_token, self._token)

    def register_order_callback(self, callback):
        """注册订单回调函数（异步或同步函数均可）。"""
        self._order_callback = callback

    async def list_orders(self, request: web.Request):
        # /orders 返回全部订单（含收货手机号/地址），属管理端点，
        # 未配置校验令牌时一律拒绝，防止公网暴露隐私数据
        if not self._token or not self._auth_ok(request):
            return web.json_response({"ec": 403, "em": "forbidden"}, status=403)
        if not self.db:
            return web.json_response({"ec": -1, "em": "数据库未初始化"})
        orders = await self.db.get_all_orders()
        return web.json_response(orders if orders else [])

    async def receive_webhook(self, request: web.Request):
        if not self._auth_ok(request):
            logger.warning(
                "[Afdian] 收到未通过令牌校验的 Webhook 请求，已拒绝"
            )
            return web.json_response({"ec": 403, "em": "forbidden"}, status=403)
        try:
            data = await request.json()
            order_info = data.get("data", {}).get("order", {})
            if not order_info:
                logger.warning("[Afdian] 未找到订单信息")
                return web.json_response({"ec": 200, "em": "无订单"})

            logger.info(
                "[Afdian] 收到订单通知：out_trade_no=%s, user_id=%s, sku_count=%s",
                order_info.get("out_trade_no", ""),
                order_info.get("user_id", ""),
                len(order_info.get("sku_detail", []))
                if isinstance(order_info.get("sku_detail"), list)
                else 0,
            )

            await self.handle_order(order_info)
            resp = {"ec": 200, "em": ""}
            logger.info(f"[Afdian] 响应：{json.dumps(resp, ensure_ascii=False)}")
            return web.json_response(resp)

        except Exception as e:
            logger.error(f"[Afdian] 处理通知失败: {e}")
            return web.json_response({"ec": 500, "em": "server error"}, status=500)

    async def handle_order(self, order: dict):
        out_trade_no = order.get("out_trade_no")
        if self.db:
            # 原子判重：仅当订单原本不存在时才保存并触发回调，
            # 消除"先查再存"竞态，Webhook 与轮询并存时不会重复通知
            is_new = await self.db.save_order_if_new(order)
            if not is_new:
                logger.info(
                    f"[Afdian] 订单已存在，跳过重复处理：{out_trade_no}"
                )
                return
            logger.info(f"[Afdian] 订单保存成功：{out_trade_no}")

        if self._order_callback:
            res = self._order_callback(order)
            if hasattr(res, "__await__"):
                task = asyncio.create_task(res)
                self._callback_tasks.add(task)

                def on_callback_done(task: asyncio.Task) -> None:
                    self._callback_tasks.discard(task)
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"[Afdian] 订单回调处理失败: {e}")

                task.add_done_callback(on_callback_done)

    async def start(self) -> bool:
        """启动 aiohttp webhook 服务。

        Returns:
            是否成功启动。

        Raises:
            OSError: 配置的地址无法绑定（端口被占用除外）。
        """
        if self._started:
            logger.warning("[Afdian] Webhook 已经启动，无需重复绑定")
            return True

        if self.host not in {"127.0.0.1", "::1", "localhost"} and not self._token:
            logger.error(
                "[Afdian] 拒绝在非本机地址启动未配置令牌的 Webhook，"
                "请配置 afdian_webhook_token"
            )
            return False

        if self.runner or self.site:
            await self.stop()

        self.runner = web.AppRunner(self.app)
        try:
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, host=self.host, port=self.port)
            await self.site.start()
            self._started = True
        except OSError as e:
            if self.runner:
                await self.runner.cleanup()
            self.runner = None
            self.site = None
            self._started = False

            if e.errno == errno.EADDRINUSE:
                logger.error(
                    f"[Afdian] Webhook 端口已被占用，插件继续载入但不会启动监听："
                    f"{self.host}:{self.port}"
                )
                return False
            raise
        except Exception:
            if self.runner:
                await self.runner.cleanup()
            self.runner = None
            self.site = None
            self._started = False
            raise
        logger.info(f"[Afdian] Webhook 服务已启动：监听 {self.host}:{self.port}")
        if not self._token:
            logger.warning(
                "[Afdian] Webhook 未配置校验令牌（afdian_webhook_token），"
                "任何请求均可触发订单处理；若端口暴露公网，请在回调 URL 中"
                "携带 ?token=xxx 并配置令牌"
            )
        return True

    async def stop(self):
        """停止 aiohttp webhook 服务。"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        for task in self._callback_tasks:
            task.cancel()
        self._callback_tasks.clear()
        self.runner = None
        self.site = None
        self._started = False
        logger.info("[Afdian] Webhook 服务已关闭")
