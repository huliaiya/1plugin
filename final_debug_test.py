#!/usr/bin/env python3
"""重新测试所有问题"""

import sys
sys.path.append('.')
from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats
import time

# 测试数据
print("🧪 创建测试数据...")

# 正常数据量
stats = MessageStats(total_count=1256, group_message_count=842, private_message_count=312, channel_message_count=102, newest_timestamp=1672531200, platform_stats={'telegram': 796, 'discord': 289, 'qq_official': 99, 'wechat': 62, 'aiocqhttp': 10})
timeline = [
    {'date': '2023-01-01', 'count': 45, 'group_count': 30, 'private_count': 10, 'channel_count': 5},
    {'date': '2023-01-02', 'count': 52, 'group_count': 35, 'private_count': 12, 'channel_count': 5},
    {'date': '2023-01-03', 'count': 48, 'group_count': 32, 'private_count': 11, 'channel_count': 5}
]
sender_ranking = [
    {'sender_id': 1, 'sender_name': '用户A', 'platform': 'telegram', 'count': 100},
    {'sender_id': 2, 'sender_name': '用户B', 'platform': 'telegram', 'count': 80},
    {'sender_id': 3, 'sender_name': '用户C', 'platform': 'discord', 'count': 60}
]
group_ranking = [
    {'group_id': 1, 'platform': 'telegram', 'display_name': '群组A', 'count': 50, 'sender_count': 10},
    {'group_id': 2, 'platform': 'telegram', 'display_name': '群组B', 'count': 40, 'sender_count': 8},
    {'group_id': 3, 'platform': 'discord', 'display_name': '群组C', 'count': 30, 'sender_count': 6}
]
content_types = [
    {'type': 'text', 'label': '文字', 'count': 800},
    {'type': 'image', 'label': '图片', 'count': 300},
    {'type': 'file', 'label': '文件', 'count': 120},
    {'type': 'video', 'label': '视频', 'count': 30},
    {'type': 'voice', 'label': '语音', 'count': 6}
]
platform_detail = [
    {
        'platform': 'telegram', 
        'platform_name': 'Telegram', 
        'total': 796, 
        'group_count': 542, 
        'private_count': 156, 
        'channel_count': 98,
        'image_count': 200,
        'file_count': 100,
        'video_count': 20,
        'voice_count': 4
    },
    {
        'platform': 'discord', 
        'platform_name': 'Discord', 
        'total': 289, 
        'group_count': 180, 
        'private_count': 60, 
        'channel_count': 49,
        'image_count': 80,
        'file_count': 50,
        'video_count': 8,
        'voice_count': 2
    },
    {
        'platform': 'qq_official', 
        'platform_name': 'QQ官方', 
        'total': 99, 
        'group_count': 65, 
        'private_count': 20, 
        'channel_count': 14,
        'image_count': 20,
        'file_count': 15,
        'video_count': 2,
        'voice_count': 0
    }
]

print("✅ 测试数据创建完成")

# 测试渲染
print("\n🧪 开始渲染...")
start_time = time.time()
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
    end_time = time.time()
    print(f"✅ 渲染成功: {len(result)} bytes, {end_time - start_time:.2f}s")
    
    # 保存图片
    with open('final_debug_test.png', 'wb') as f:
        f.write(result)
    print("📁 图片已保存为: final_debug_test.png")
    
except Exception as e:
    print(f"❌ 渲染失败: {e}")
    import traceback
    traceback.print_exc()

# 测试各个组件的空数据情况
print("\n🧪 测试空数据情况...")

empty_cases = [
    ("空内容类型", stats, timeline, sender_ranking, group_ranking, [], platform_detail),
    ("空平台详情", stats, timeline, sender_ranking, group_ranking, content_types, []),
    ("空排行榜", stats, timeline, [], [], content_types, platform_detail),
    ("空时间趋势", stats, [], sender_ranking, group_ranking, content_types, platform_detail),
]

for case_name, *args in empty_cases:
    try:
        result = render_snapshot(
            stats=args[0], db_table_count=5, timeline=args[1], sender_ranking=args[2], 
            group_ranking=args[3], content_types=args[4], platform_detail=args[5]
        )
        
        with open(f'final_debug_{case_name}.png', 'wb') as f:
            f.write(result)
        print(f"✅ {case_name} 渲染成功: {len(result)} bytes")
        
    except Exception as e:
        print(f"❌ {case_name} 渲染失败: {e}")

print("\n🎉 测试完成！")