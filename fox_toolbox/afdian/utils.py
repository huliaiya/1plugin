"""爱发电订单 / 赞助解析与格式化。

复刻自 astrbot_plugin_afdian/core/utils.py（作者 Zhalslar）。
输出使用 markdown，配合自定义 T2I 模板渲染更美观的图片。
"""

from datetime import datetime


def format_time(timestamp):
    if not timestamp:
        return None
    try:
        ts = float(timestamp)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _safe_float(value, default=0.0):
    """容错解析浮点数，非法值（None/空/非数字）返回 default。"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _format_order_status(status) -> str:
    """订单状态展示。爱发电 webhook 仅推送已支付订单；
    0 为未支付，其余按已支付展示，避免暴露裸数字。"""
    try:
        status = int(status)
    except (TypeError, ValueError):
        return str(status) if status not in (None, "") else ""
    if status == 0:
        return "待支付"
    return "已支付"


def parse_order(order: dict) -> str:
    """解析订单数据为可读文本（markdown 格式）。"""
    fields = [
        ("交易号", order.get("out_trade_no")),
        ("计划标题", order.get("plan_title")),
        ("用户名", order.get("user_name")),
        ("用户ID", order.get("user_id")),
        ("计划ID", order.get("plan_id")),
        ("时长", f"{order['month']}个月" if order.get("month") else None),
        ("总金额", order.get("total_amount")),
        ("订单状态", _format_order_status(order.get("status"))),
        ("产品类型", order.get("product_type")),
        ("折扣", order.get("discount")),
        ("备注", order.get("remark")),
        ("兑换码ID", order.get("redeem_id")),
        ("创建时间", format_time(order.get("create_time", 0))),
    ]

    lines = ["📦 订单信息", "──────────────"]
    for k, v in fields:
        if v not in [None, "", "N/A"]:
            if k == "总金额":
                try:
                    v = f"¥{float(v):.2f}"
                except (TypeError, ValueError):
                    pass
            lines.append(f"**{k}**：{v}")
    lines.append("──────────────")

    sku_detail = order.get("sku_detail", [])
    sku_lines = [
        f"**{sku.get('name', '未知')}** × {sku.get('count', 'N/A')}"
        f"（SKU ID: {sku.get('sku_id', 'N/A')}）"
        for sku in sku_detail
        if any(sku.get(key) for key in ("name", "count", "sku_id"))
    ]
    if sku_lines:
        lines.append("**SKU 列表**：")
        lines.extend(f"- {s}" for s in sku_lines)

    return "\n".join(lines)


def parse_sponsors(data: dict) -> list:
    """解析赞助者数据（markdown 格式，每条赞助一个卡片）。"""
    formatted_list = []

    for item in data.get("list", []):
        user = item.get("user", {})
        current = item.get("current_plan", {})
        plans = item.get("sponsor_plans", [])

        plan_list = [
            {
                "name": p.get("name", "未知方案"),
                "price": _safe_float(p.get("price")),
            }
            for p in plans
        ]
        plan_list.sort(key=lambda x: x["price"])

        sponsor_info = {
            "name": user.get("name", ""),
            "user_id": user.get("user_id", ""),
            "avatar": user.get("avatar", ""),
            "total_amount": _safe_float(item.get("all_sum_amount")),
            "current_plan": {
                "name": current.get("name", ""),
                "price": _safe_float(current.get("price")),
            },
            "first_pay": format_time(item.get("first_pay_time", 0)),
            "last_pay": format_time(item.get("last_pay_time", 0)),
        }

        lines = [
            f"### 🎉 {sponsor_info['name']}",
            f"- **用户ID**：{sponsor_info['user_id']}",
            f"- **当前方案**：{sponsor_info['current_plan']['name']}"
            f"（¥{sponsor_info['current_plan']['price']:.2f}）",
            f"- **首次赞助**：{sponsor_info['first_pay']}",
            f"- **最近赞助**：{sponsor_info['last_pay']}",
            f"- **累计赞助**：**¥{sponsor_info['total_amount']:.2f}**",
        ]

        formatted_list.append("\n".join(lines))

    return formatted_list
