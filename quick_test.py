#!/usr/bin/env python3
"""快速测试所有组件的显示效果。"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats
import time

# 创建最小测试数据
stats = MessageStats(
    total_count=1000,
    group_message_count=400,
    private_message_count=350,
    channel_message_count=250,
    platform_stats={
        "Telegram": 450,
        "Discord": 350,
        "LINE": 200,
    },
)

# 简化的测试数据
timeline = [
    {"date": "2024-01", "count": 80},
    {"date": "2024-02", "count": 90},
    {"date": "2024-03", "count": 100},
    {"date": "2024-04", "count": 110},
    {"date": "2024-05", "count": 120},
    {"date": "2024-06", "count": 130},
]

sender_ranking = [
    {"sender_id": "1", "sender_name": "Alice", "platform": "Telegram", "count": 150},
    {"sender_id": "2", "sender_name": "Bob", "platform": "Discord", "count": 130},
    {"sender_id": "3", "sender_name": "Charlie", "platform": "LINE", "count": 110},
]

group_ranking = [
    {"group_id": "1", "platform": "Telegram", "count": 200, "sender_count": 15},
    {"group_id": "2", "platform": "Discord", "count": 150, "sender_count": 12},
    {"group_id": "3", "platform": "LINE", "count": 100, "sender_count": 8},
]

content_types = [
    {"type": "text", "label": "文本消息", "count": 400},
    {"type": "image", "label": "图片消息", "count": 300},
    {"type": "file", "label": "文件消息", "count": 200},
    {"type": "video", "label": "视频消息", "count": 100},
]

platform_detail = [
    {
        "platform": "Telegram",
        "platform_name": "Telegram",
        "total": 450,
        "group_count": 200,
        "private_count": 150,
        "channel_count": 100,
        "post_count": 100,
        "reply_count": 200,
    },
    {
        "platform": "Discord",
        "platform_name": "Discord",
        "total": 350,
        "group_count": 150,
        "private_count": 120,
        "channel_count": 80,
        "post_count": 80,
        "reply_count": 150,
    },
    {
        "platform": "LINE",
        "platform_name": "LINE",
        "total": 200,
        "group_count": 100,
        "private_count": 80,
        "channel_count": 20,
        "post_count": 50,
        "reply_count": 100,
    },
]

db_table_count = 5

# 快速测试
print("开始快速测试...")
start_time = time.time()

try:
    result = render_snapshot(
        stats=stats,
        db_table_count=db_table_count,
        timeline=timeline,
        sender_ranking=sender_ranking,
        group_ranking=group_ranking,
        content_types=content_types,
        platform_stats=stats.platform_stats,
        platform_detail=platform_detail,
        generated_at=time.time(),
    )
    
    end_time = time.time()
    print(f"✅ 渲染成功！耗时: {end_time - start_time:.2f}秒")
    print(f"✅ 文件大小: {len(result) / 1024:.1f}KB")
    
    # 保存测试结果
    with open("quick_test.png", "wb") as f:
        f.write(result)
    print("✅ 测试图片已保存为: quick_test.png")
    
    # 检查文件是否存在且大小合理
    import os
    if os.path.exists("quick_test.png"):
        file_size = os.path.getsize("quick_test.png")
        print(f"✅ 文件大小: {file_size / 1024:.1f}KB")
        
        # 检查文件是否损坏
        try:
            from PIL import Image
            img = Image.open("quick_test.png")
            print(f"✅ 图片尺寸: {img.size}")
            print(f"✅ 图片模式: {img.mode}")
            print("✅ 图片文件完整且可读")
        except Exception as e:
            print(f"❌ 图片文件损坏: {e}")
    
    print("\n🎉 所有组件测试完成！")
    
except Exception as e:
    print(f"❌ 渲染失败: {e}")
    import traceback
    traceback.print_exc()