#!/usr/bin/env python3
"""专门测试空内容类型问题"""

import sys
sys.path.append('.')
from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

# 空内容类型测试
print("🧪 专门测试空内容类型问题...")

stats = MessageStats(total_count=1256, group_message_count=842, private_message_count=312, channel_message_count=102, newest_timestamp=1672531200, platform_stats={'telegram': 796, 'discord': 289, 'qq_official': 99, 'wechat': 62, 'aiocqhttp': 10})
timeline = [{'date': '2023-01-01', 'count': 45, 'group_count': 30, 'private_count': 10, 'channel_count': 5}]
sender_ranking = [{'sender_id': 1, 'sender_name': '用户A', 'platform': 'telegram', 'count': 100}]
group_ranking = [{'group_id': 1, 'platform': 'telegram', 'display_name': '群组A', 'count': 50, 'sender_count': 10}]
content_types = []  # 空内容类型
platform_detail = [{'platform': 'telegram', 'platform_name': 'Telegram', 'total': 796, 'group_count': 542, 'private_count': 156, 'channel_count': 98}]

try:
    result = render_snapshot(
        stats=stats,
        db_table_count=5,
        timeline=timeline,
        sender_ranking=sender_ranking,
        group_ranking=group_ranking,
        content_types=content_types,
        platform_detail=platform_detail
    )
    print("✅ 空内容类型渲染成功")
    with open('debug_empty_content_types.png', 'wb') as f:
        f.write(result)
except Exception as e:
    print(f"❌ 空内容类型渲染失败: {e}")
    import traceback
    traceback.print_exc()

# 测试只有一个内容类型的情况
print("\n🧪 测试只有一个内容类型...")
content_types_one = [{'type': 'text', 'label': '文字', 'count': 1256}]

try:
    result = render_snapshot(
        stats=stats,
        db_table_count=5,
        timeline=timeline,
        sender_ranking=sender_ranking,
        group_ranking=group_ranking,
        content_types=content_types_one,
        platform_detail=platform_detail
    )
    print("✅ 单一内容类型渲染成功")
    with open('debug_single_content_type.png', 'wb') as f:
        f.write(result)
except Exception as e:
    print(f"❌ 单一内容类型渲染失败: {e}")
    import traceback
    traceback.print_exc()