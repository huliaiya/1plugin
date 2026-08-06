#!/usr/bin/env python3
"""专门调试空内容类型问题"""

import sys
sys.path.append('.')
from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats
import traceback

# 测试空内容类型
print("🧪 测试空内容类型...")

stats = MessageStats(total_count=464, group_message_count=312, private_message_count=98, channel_message_count=54, newest_timestamp=1672531200, platform_stats={'telegram': 280, 'discord': 120, 'qq_official': 64})
timeline = [{'date': '2023-01-01', 'count': 45, 'group_count': 30, 'private_count': 10, 'channel_count': 5}]
sender_ranking = [{'sender_id': 1, 'sender_name': '用户A', 'platform': 'telegram', 'count': 100}]
group_ranking = [{'group_id': 1, 'platform': 'telegram', 'display_name': '群组A', 'count': 50, 'sender_count': 10}]
content_types = []  # 空内容类型
platform_detail = [
    {'platform': 'telegram', 'platform_name': 'Telegram', 'total': 280, 'group_count': 180, 'private_count': 60, 'channel_count': 40},
    {'platform': 'discord', 'platform_name': 'Discord', 'total': 120, 'group_count': 80, 'private_count': 25, 'channel_count': 15},
    {'platform': 'qq_official', 'platform_name': 'QQ官方', 'total': 64, 'group_count': 40, 'private_count': 13, 'channel_count': 11}
]

try:
    result = render_snapshot(
        stats=stats,
        db_table_count=3,
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
    print("详细错误信息:")
    traceback.print_exc()

# 测试空字典内容类型
print("\n🧪 测试空字典内容类型...")

content_types_dict = {}  # 空字典

try:
    result = render_snapshot(
        stats=stats,
        db_table_count=3,
        timeline=timeline,
        sender_ranking=sender_ranking,
        group_ranking=group_ranking,
        content_types=content_types_dict,
        platform_detail=platform_detail
    )
    print("✅ 空字典内容类型渲染成功")
    with open('debug_empty_dict_content_types.png', 'wb') as f:
        f.write(result)
        
except Exception as e:
    print(f"❌ 空字典内容类型渲染失败: {e}")
    print("详细错误信息:")
    traceback.print_exc()

# 测试None内容类型
print("\n🧪 测试None内容类型...")

try:
    result = render_snapshot(
        stats=stats,
        db_table_count=3,
        timeline=timeline,
        sender_ranking=sender_ranking,
        group_ranking=group_ranking,
        content_types=None,
        platform_detail=platform_detail
    )
    print("✅ None内容类型渲染成功")
    with open('debug_none_content_types.png', 'wb') as f:
        f.write(result)
        
except Exception as e:
    print(f"❌ None内容类型渲染失败: {e}")
    print("详细错误信息:")
    traceback.print_exc()

print("\n🎉 测试完成！")
