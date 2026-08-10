"""爱发电功能配置封装。

原插件（astrbot_plugin_afdian）使用嵌套 ConfigNode 结构，为兼容
狐狸插件的扁平 AstrBotConfig 配置模型，这里将配置平铺为 afdian.xxx 前缀键。
"""

from __future__ import annotations

from pathlib import Path

from astrbot.api import logger


class AfdianConfig:
    """从扁平 AstrBotConfig 中读取爱发电相关配置。"""

    def __init__(self, config, data_dir: Path):
        self._cfg = config
        self.data_dir = data_dir

    # ---- 功能开关 ----
    @property
    def enabled(self) -> bool:
        """是否启用爱发电功能。"""
        return bool(self._cfg.get("afdian_enabled", False))

    # ---- webhook 配置 ----
    @property
    def webhook_host(self) -> str:
        return str(self._cfg.get("afdian_webhook_host", "127.0.0.1"))

    @property
    def webhook_port(self) -> int:
        try:
            return int(self._cfg.get("afdian_webhook_port", 6500))
        except (TypeError, ValueError):
            return 6500

    @property
    def webhook_token(self) -> str:
        """Webhook 校验令牌。

        配置后在回调 URL 中以 ``?token=<值>`` 形式携带（如
        ``https://example.com:6500/?token=xxx``），插件仅处理携带正确
        令牌的请求，可防止伪造订单推送。留空表示不校验（向后兼容）。
        """
        return str(self._cfg.get("afdian_webhook_token", "") or "")

    # ---- API 配置 ----
    @property
    def base_url(self) -> str:
        return str(
            self._cfg.get(
                "afdian_api_base_url", "https://afdian.com/api/open"
            )
        )

    @property
    def user_id(self) -> str:
        return str(self._cfg.get("afdian_api_user_id", "") or "")

    @property
    def token(self) -> str:
        return str(self._cfg.get("afdian_api_token", "") or "")

    # ---- 支付配置 ----
    @property
    def default_price(self) -> int:
        try:
            return int(self._cfg.get("afdian_default_price", 5))
        except (TypeError, ValueError):
            return 5

    @property
    def default_reply(self) -> str:
        return str(
            self._cfg.get("afdian_default_reply", "赞助成功，感谢支持！")
        )

    # ---- 无公网轮询 ----
    @property
    def use_polling(self) -> bool:
        """无公网环境是否启用订单轮询检测（代替 Webhook 推送）。"""
        return bool(self._cfg.get("afdian_use_polling", True))

    @property
    def poll_interval(self) -> int:
        """订单轮询间隔（秒）。"""
        try:
            return max(1, int(self._cfg.get("afdian_poll_interval", 5)))
        except (TypeError, ValueError):
            return 5

    @property
    def poll_timeout(self) -> int:
        """订单轮询窗口长度（秒），发电后等待支付的最长时间。"""
        try:
            return max(10, int(self._cfg.get("afdian_poll_timeout", 300)))
        except (TypeError, ValueError):
            return 300

    @property
    def recovery_check_interval(self) -> float:
        """MySQL 恢复检测间隔（秒）。"""
        try:
            return max(5.0, float(self._cfg.get("afdian_recovery_check_interval", 30.0)))
        except (TypeError, ValueError):
            return 30.0

    # ---- 通知会话 ----
    @property
    def notice_sessions(self) -> list:
        sessions = self._cfg.get("afdian_notice_sessions", [])
        return sessions if isinstance(sessions, list) else []

    def add_notice_session(self, session_id: str) -> None:
        """添加一个接收订单通知的会话，并持久化。"""
        sessions = self.notice_sessions
        if session_id not in sessions:
            sessions.append(session_id)
            self._cfg["afdian_notice_sessions"] = sessions
            self._save_config()
        logger.info(f"[Afdian] 已添加通知会话: {session_id}")

    def _save_config(self) -> None:
        save = getattr(self._cfg, "save_config", None)
        if callable(save):
            try:
                save()
            except Exception as e:
                logger.warning(f"[Afdian] 保存配置失败: {e}")

    def ready(self) -> bool:
        """API 凭据是否就绪（user_id / token 均已填写）。"""
        return bool(self.user_id and self.token)

    # ---- 防刷限流 ----
    @property
    def rate_limit_enabled(self) -> bool:
        """是否启用 /发电 命令频率限制（1 分钟内发起订单数上限）。"""
        return bool(self._cfg.get("afdian_rate_limit_enabled", True))

    @property
    def rate_limit_max_orders(self) -> int:
        """1 分钟窗口内允许发起订单的最大次数（达到该值即触发拉黑）。"""
        try:
            return max(1, int(self._cfg.get("afdian_rate_limit_max_orders", 3)))
        except (TypeError, ValueError):
            return 3

    @property
    def rate_limit_window(self) -> int:
        """频率统计窗口（秒）。"""
        try:
            return max(10, int(self._cfg.get("afdian_rate_limit_window", 60)))
        except (TypeError, ValueError):
            return 60

    @property
    def rate_limit_ban_seconds(self) -> int:
        """触发限制后的拉黑时长（秒），默认 1 小时。"""
        try:
            return max(60, int(self._cfg.get("afdian_rate_limit_ban_seconds", 3600)))
        except (TypeError, ValueError):
            return 3600
