#!/usr/bin/env python3
"""全面测试边缘情况和优化效果。"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats
import time

print("🧪 全面边缘情况测试...")

# 测试1：大量数据
print("\n📊 测试1：大量数据（10个平台，10种内容类型）")
stats1 = MessageStats(
    total_count=5000,
    group_message_count=2000,
    private_message_count=1500,
    channel_message_count=1500,
    platform_stats={f"平台{i}": 500 + i * 50 for i in range(10)},
    oldest_timestamp=1704067200,
    newest_timestamp=1735689600,
)

timeline1 = [{"date": f"2024-{i:02d}", "count": 100 + i * 20} for i in range(1, 13)]
sender_ranking1 = [{"sender_id": str(i), "sender_name": f"User{i}", "platform": "平台1", "count": 100 - i * 10} for i in range(1, 6)]
group_ranking1 = [{"group_id": str(i), "platform": "平台1", "count": 50 - i * 5, "sender_count": 10 - i} for i in range(1, 6)]
content_types1 = [{"type": f"type{i}", "label": f"类型{i}", "count": 500 - i * 50} for i in range(1, 11)]
platform_detail1 = [{"platform": f"平台{i}", "platform_name": f"平台{i}", "total": 500 + i * 50, 
                     "group_count": 200 + i * 20, "private_count": 150 + i * 15, "channel_count": 150 + i * 15} for i in range(1, 11)]

start = time.time()
try:
    result1 = render_snapshot(stats1, 10, timeline1, sender_ranking1, group_ranking1, 
                             content_types1, stats1.platform_stats, platform_detail1)
    print(f"✅ 大量数据测试成功！耗时: {time.time() - start:.2f}秒，文件大小: {len(result1) / 1024:.1f}KB")
    with open("test_large_data.png", "wb") as f:
        f.write(result1)
except Exception as e:
    print(f"❌ 大量数据测试失败: {e}")

# 测试2：空数据
print("\n📊 测试2：空数据")
stats2 = MessageStats(total_count=0, platform_stats={})
start = time.time()
try:
    result2 = render_snapshot(stats2, 0, [], [], [], [], {}, [])
    print(f"✅ 空数据测试成功！耗时: {time.time() - start:.2f}秒，文件大小: {len(result2) / 1024:.1f}KB")
    with open("test_empty_data.png", "wb") as f:
        f.write(result2)
except Exception as e:
    print(f"❌ 空数据测试失败: {e}")

# 测试3：极小数据
print("\n📊 测试3：极小数据（1个平台，1种内容类型）")
stats3 = MessageStats(
    total_count=1,
    group_message_count=1,
    private_message_count=0,
    channel_message_count=0,
    platform_stats={"测试平台": 1},
    oldest_timestamp=1704067200,
    newest_timestamp=1704067200,
)

timeline3 = [{"date": "2024-01", "count": 1}]
sender_ranking3 = [{"sender_id": "1", "sender_name": "Test", "platform": "测试平台", "count": 1}]
group_ranking3 = [{"group_id": "1", "platform": "测试平台", "count": 1, "sender_count": 1}]
content_types3 = [{"type": "text", "label": "文本消息", "count": 1}]
platform_detail3 = [{"platform": "测试平台", "platform_name": "测试平台", "total": 1, 
                    "group_count": 1, "private_count": 0, "channel_count": 0}]

start = time.time()
try:
    result3 = render_snapshot(stats3, 1, timeline3, sender_ranking3, group_ranking3, 
                             content_types3, stats3.platform_stats, platform_detail3)
    print(f"✅ 极小数据测试成功！耗时: {time.time() - start:.2f}秒，文件大小: {len(result3) / 1024:.1f}KB")
    with open("test_minimal_data.png", "wb") as f:
        f.write(result3)
except Exception as e:
    print(f"❌ 极小数据测试失败: {e}")

# 测试4：异常数据
print("\n📊 测试4：异常数据（包含None、空字符串、负数）")
stats4 = MessageStats(
    total_count=100,
    group_message_count=50,
    private_message_count=30,
    channel_message_count=20,
    platform_stats={
        "正常平台": 50,
        "异常平台": 30,
        "空平台": 20,
    },
    oldest_timestamp=1704067200,
    newest_timestamp=1735689600,
)

timeline4 = [{"date": "2024-01", "count": 50}, {"date": "2024-02", "count": 30}, {"date": "2024-03", "count": 20}]
sender_ranking4 = [
    {"sender_id": "1", "sender_name": "正常用户", "platform": "正常平台", "count": 50},
    {"sender_id": "2", "sender_name": "", "platform": "异常平台", "count": 30},
    {"sender_id": "3", "sender_name": None, "platform": "空平台", "count": 20},
]
group_ranking4 = [
    {"group_id": "1", "platform": "正常平台", "count": 30, "sender_count": 5},
    {"group_id": "2", "platform": "异常平台", "count": 20, "sender_count": 3},
]
content_types4 = [
    {"type": "text", "label": "文本消息", "count": 60},
    {"type": "image", "label": "", "count": 20},
    {"type": None, "label": "未知类型", "count": 20},
]
platform_detail4 = [
    {"platform": "正常平台", "platform_name": "正常平台", "total": 50, "group_count": 30, "private_count": 20, "channel_count": 0},
    {"platform": "异常平台", "platform_name": "", "total": 30, "group_count": 20, "private_count": 10, "channel_count": 0},
    {"platform": "空平台", "platform_name": None, "total": 20, "group_count": 10, "private_count": 10, "channel_count": 0},
]

start = time.time()
try:
    result4 = render_snapshot(stats4, 3, timeline4, sender_ranking4, group_ranking4, 
                             content_types4, stats4.platform_stats, platform_detail4)
    print(f"✅ 异常数据测试成功！耗时: {time.time() - start:.2f}秒，文件大小: {len(result4) / 1024:.1f}KB")
    with open("test_abnormal_data.png", "wb") as f:
        f.write(result4)
except Exception as e:
    print(f"❌ 异常数据测试失败: {e}")

print("\n🎯 所有边缘情况测试完成！")
print("✅ 生成的测试图片：")
print("  - test_large_data.png（大量数据）")
print("  - test_empty_data.png（空数据）")
print("  - test_minimal_data.png（极小数据）")
print("  - test_abnormal_data.png（异常数据）")