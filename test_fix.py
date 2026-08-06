#!/usr/bin/env python3
"""测试修复后的快照渲染器。"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats
import time

# 创建测试数据
stats = MessageStats(
    total_count=1234,
    group_message_count=456,
    private_message_count=378,
    channel_message_count=234,
    platform_stats={
        "Telegram": 456,
        "Discord": 378,
        "LINE": 234,
        "其他": 166,
    },
    oldest_timestamp=1704067200,  # 2024-01-01
    newest_timestamp=1735689600,  # 2024-12-31
    first_record_time=1704067200,
    last_record_time=1735689600,
)

# 其他数据作为单独参数
timeline = [
    {"date": "2024-01", "count": 123},
    {"date": "2024-02", "count": 145},
    {"date": "2024-03", "count": 167},
    {"date": "2024-04", "count": 189},
    {"date": "2024-05", "count": 210},
    {"date": "2024-06", "count": 234},
    {"date": "2024-07", "count": 256},
    {"date": "2024-08", "count": 278},
    {"date": "2024-09", "count": 300},
    {"date": "2024-10", "count": 322},
    {"date": "2024-11", "count": 344},
    {"date": "2024-12", "count": 366},
]

sender_ranking = [
    {"sender_id": "1", "sender_name": "Alice", "platform": "Telegram", "count": 156},
    {"sender_id": "2", "sender_name": "Bob", "platform": "Discord", "count": 134},
    {"sender_id": "3", "sender_name": "Charlie", "platform": "LINE", "count": 123},
    {"sender_id": "4", "sender_name": "David", "platform": "Telegram", "count": 98},
    {"sender_id": "5", "sender_name": "Eve", "platform": "Discord", "count": 87},
]

group_ranking = [
    {"group_id": "1", "platform": "Telegram", "count": 234, "sender_count": 12},
    {"group_id": "2", "platform": "Discord", "count": 189, "sender_count": 10},
    {"group_id": "3", "platform": "LINE", "count": 156, "sender_count": 8},
    {"group_id": "4", "platform": "Telegram", "count": 123, "sender_count": 6},
    {"group_id": "5", "platform": "Discord", "count": 98, "sender_count": 5},
]

content_types = [
    {"type": "text", "label": "文本消息", "count": 456},
    {"type": "image", "label": "图片消息", "count": 234},
    {"type": "file", "label": "文件消息", "count": 123},
    {"type": "video", "label": "视频消息", "count": 89},
    {"type": "audio", "label": "音频消息", "count": 67},
    {"type": "sticker", "label": "贴纸", "count": 45},
    {"type": "link", "label": "链接", "count": 34},
    {"type": "other", "label": "其他", "count": 23},
]

platform_detail = [
    {
        "platform": "Telegram",
        "platform_name": "Telegram",
        "total": 456,
        "group_count": 234,
        "private_count": 156,
        "channel_count": 66,
        "post_count": 123,
        "reply_count": 234,
    },
    {
        "platform": "Discord",
        "platform_name": "Discord",
        "total": 378,
        "group_count": 189,
        "private_count": 134,
        "channel_count": 55,
        "post_count": 98,
        "reply_count": 189,
    },
    {
        "platform": "LINE",
        "platform_name": "LINE",
        "total": 234,
        "group_count": 123,
        "private_count": 89,
        "channel_count": 22,
        "post_count": 56,
        "reply_count": 123,
    },
]

db_table_count = 8

# 测试渲染
print("开始测试修复后的快照渲染器...")
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
    print(f"渲染成功！耗时: {end_time - start_time:.2f}秒")
    print(f"文件大小: {len(result) / 1024:.1f}KB")
    
    # 保存测试结果
    with open("test_fixed_snapshot.png", "wb") as f:
        f.write(result)
    print("测试图片已保存为: test_fixed_snapshot.png")
    
except Exception as e:
    print(f"渲染失败: {e}")
    import traceback
    traceback.print_exc()