"""爱发电订单 / 赞助解析与格式化。

复刻自 astrbot_plugin_afdian/core/utils.py（作者 Zhalslar）。
输出使用 markdown，配合自定义 T2I 模板渲染更美观的图片。
"""

from datetime import datetime


def format_time(timestamp):
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def parse_order(order: dict) -> str:
    """解析订单数据为可读文本（markdown 格式）。"""
    fields = {
        "交易号": order.get("out_trade_no"),
        "计划标题": order.get("plan_title"),
        "用户名": order.get("user_name"),
        "用户ID": order.get("user_id"),
        "计划ID": order.get("plan_id"),
        "时长": f"{order['month']}个月" if order.get("month") else None,
        "总金额": order.get("total_amount"),
        "订单状态": order.get("status"),
        "产品类型": order.get("product_type"),
        "折扣": order.get("discount"),
        "备注": order.get("remark"),
        "兑换码ID": order.get("redeem_id"),
        "创建时间": format_time(order.get("create_time", 0)),
    }

    lines = ["### 📦 订单信息"]
    lines += [
        f"- **{k}**：{v}" for k, v in fields.items() if v not in [None, "", "N/A"]
    ]

    sku_detail = order.get("sku_detail", [])
    sku_lines = [
        f"  - **{sku.get('name', '未知')}** × {sku.get('count', 'N/A')}"
        f"（SKU ID: {sku.get('sku_id', 'N/A')}）"
        for sku in sku_detail
        if any(sku.get(key) for key in ("name", "count", "sku_id"))
    ]
    if sku_lines:
        lines.append("- **SKU 列表**：")
        lines.extend(sku_lines)

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
                "price": float(p.get("price", 0)),
            }
            for p in plans
        ]
        plan_list.sort(key=lambda x: x["price"])

        sponsor_info = {
            "name": user.get("name", ""),
            "user_id": user.get("user_id", ""),
            "avatar": user.get("avatar", ""),
            "total_amount": float(item.get("all_sum_amount", 0)),
            "current_plan": {
                "name": current.get("name", ""),
                "price": float(current.get("price", 0)),
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
