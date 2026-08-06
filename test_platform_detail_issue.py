#!/usr/bin/env python3
"""测试平台详细内容类型分布显示问题"""

import sys
sys.path.append('.')
from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

# 测试小数据量场景
stats = MessageStats(total_count=464, group_message_count=312, private_message_count=98, channel_message_count=54, newest_timestamp=1672531200, platform_stats={'telegram': 280, 'discord': 120, 'qq_official': 64})
timeline = [{'date': '2023-01-01', 'count': 45, 'group_count': 30, 'private_count': 10, 'channel_count': 5}]
sender_ranking = [{'sender_id': 1, 'sender_name': '用户A', 'platform': 'telegram', 'count': 100}]
group_ranking = [{'group_id': 1, 'platform': 'telegram', 'display_name': '群组A', 'count': 50, 'sender_count': 10}]
content_types = [{'type': 'text', 'label': '文字', 'count': 300}, {'type': 'image', 'label': '图片', 'count': 100}, {'type': 'file', 'label': '文件', 'count': 64}]
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
    print('小数据量渲染成功')
    print(f'图片大小: {len(result)} bytes')
    
    # 保存图片进行查看
    with open('test_platform_detail_issue.png', 'wb') as f:
        f.write(result)
    print('图片已保存为: test_platform_detail_issue.png')
    
except Exception as e:
    print(f'渲染失败: {e}')
    import traceback
    traceback.print_exc()