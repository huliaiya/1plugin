#!/usr/bin/env python3
"""验证 _draw_redis_card 在 4 种状态下文字不溢出卡片。"""

import sys
import os
import time
from PIL import Image
import io

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

stats = MessageStats(
    total_count=1000,
    group_message_count=400,
    private_message_count=350,
    channel_message_count=250,
    platform_stats={"Telegram": 450, "Discord": 350, "LINE": 200},
)

timeline = [{"date": "2024-01", "count": 80}, {"date": "2024-02", "count": 90}]
sender_ranking = [{"sender_id": "1", "sender_name": "Alice", "platform": "Telegram", "count": 150}]
group_ranking = [{"group_id": "1", "platform": "Telegram", "count": 200, "sender_count": 15}]
content_types = [{"type": "text", "label": "文本消息", "count": 400}]
platform_detail = [{"platform": "Telegram", "platform_name": "Telegram", "total": 450}]

redis_statuses = {
    "未配置": {},
    "已配置未启用": {"configured": True, "enabled": False, "available": False,
                   "host": "127.0.0.1", "port": 6379, "db": 0, "ttl": 600},
    "运行中": {"configured": True, "enabled": True, "available": True,
              "host": "127.0.0.1", "port": 6379, "db": 3, "ttl": 600,
              "keys": {"stats": 1, "recent_messages": 5}},
    "已降级": {"configured": True, "enabled": True, "available": False,
              "host": "127.0.0.1", "port": 6379, "db": 0, "ttl": 600},
}

ok = True
for name, rs in redis_statuses.items():
    try:
        start = time.time()
        result = render_snapshot(
            stats=stats,
            db_table_count=5,
            timeline=timeline,
            sender_ranking=sender_ranking,
            group_ranking=group_ranking,
            content_types=content_types,
            platform_stats=stats.platform_stats,
            platform_detail=platform_detail,
            generated_at=time.time(),
            redis_status=rs,
        )
        img = Image.open(io.BytesIO(result))
        print(f"[{name}] 渲染成功 {time.time()-start:.2f}s, {len(result)/1024:.1f}KB, "
              f"{img.size[0]}x{img.size[1]}")
        with open(f"test_redis_{name}.png", "wb") as f:
            f.write(result)
    except Exception as e:
        ok = False
        import traceback
        traceback.print_exc()
        print(f"[{name}] 失败: {e}")

print("全部通过" if ok else "存在失败")
