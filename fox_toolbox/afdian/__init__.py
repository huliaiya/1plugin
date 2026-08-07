"""爱发电对接功能子包。

复刻自 astrbot_plugin_afdian（作者 Zhalslar），功能完整迁移：
- 接受用户打赏、生成支付链接
- 爱发电 Webhook 订单实时推送
- 主动查询订单 / 赞助记录
- 帖单 / 赞助解析格式化

集成进狐狸插件（astrbot_plugin_fox_toolbox）。订单存储优先写入
主插件 MySQL 连接池的 `afdian_orders` 表，MySQL 不可用时回退 SQLite。
"""

from .config import AfdianConfig
from .afdian_api import AfdianAPIClient
from .afdian_webhook import AfdianWebhookServer
from .order_db import OrderDB
from .utils import parse_order, parse_sponsors

__all__ = [
    "AfdianConfig",
    "AfdianAPIClient",
    "AfdianWebhookServer",
    "OrderDB",
    "parse_order",
    "parse_sponsors",
]