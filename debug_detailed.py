#!/usr/bin/env python3
"""详细调试平台消息详细和内容类型分布问题。"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fox_toolbox.snapshot_renderer import render_snapshot, _draw_platform_detail, _draw_content_types
from fox_toolbox.models import MessageStats
import time
from PIL import Image, ImageDraw

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
    oldest_timestamp=1704067200,
    newest_timestamp=1735689600,
    first_record_time=1704067200,
    last_record_time=1735689600,
)

# 测试数据
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

db_table_count = 8

print("🔍 详细调试测试...")
print("✅ 测试项目：")
print("  1. 平台消息详细统计堆叠柱状图")
print("  2. 内容类型分布饼图")
print("  3. 数据结构验证")
print("  4. 坐标计算验证")

# 测试1：单独测试平台消息详细
print("\n📊 测试1：平台消息详细统计")
try:
    # 创建测试图片
    test_img1 = Image.new("RGBA", (400, 300), (255, 255, 255, 255))
    draw1 = ImageDraw.Draw(test_img1)
    
    # 调用函数
    _draw_platform_detail(test_img1, (20, 20, 380, 280), platform_detail)
    
    print("✅ 平台消息详细统计渲染成功")
    
    # 保存测试结果
    test_img1.save("debug_platform_detail.png")
    print("✅ 平台消息详细测试图片已保存: debug_platform_detail.png")
    
except Exception as e:
    print(f"❌ 平台消息详细统计渲染失败: {e}")
    import traceback
    traceback.print_exc()

# 测试2：单独测试内容类型分布
print("\n🥧 测试2：内容类型分布")
try:
    # 创建测试图片
    test_img2 = Image.new("RGBA", (400, 300), (255, 255, 255, 255))
    draw2 = ImageDraw.Draw(test_img2)
    
    # 调用函数
    _draw_content_types(test_img2, (20, 20, 380, 280), content_types)
    
    print("✅ 内容类型分布渲染成功")
    
    # 保存测试结果
    test_img2.save("debug_content_types.png")
    print("✅ 内容类型分布测试图片已保存: debug_content_types.png")
    
except Exception as e:
    print(f"❌ 内容类型分布渲染失败: {e}")
    import traceback
    traceback.print_exc()

# 测试3：完整渲染测试
print("\n🎨 测试3：完整渲染测试")
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
    render_time = end_time - start_time
    file_size = len(result) / 1024
    
    print(f"✅ 完整渲染成功！耗时: {render_time:.2f}秒")
    print(f"✅ 文件大小: {file_size:.1f}KB")
    
    # 保存测试结果
    with open("debug_complete.png", "wb") as f:
        f.write(result)
    print("✅ 完整渲染测试图片已保存: debug_complete.png")
    
except Exception as e:
    print(f"❌ 完整渲染失败: {e}")
    import traceback
    traceback.print_exc()

# 测试4：数据结构验证
print("\n📋 测试4：数据结构验证")
print("📊 平台详细数据结构：")
for i, platform in enumerate(platform_detail):
    print(f"  平台 {i+1}: {platform}")
    print(f"    总计: {platform['total']}")
    print(f"    群聊: {platform['group_count']}")
    print(f"    私聊: {platform['private_count']}")
    print(f"    频道: {platform['channel_count']}")
    print(f"    帖子: {platform['post_count']}")
    print(f"    回复: {platform['reply_count']}")

print("\n🥧 内容类型数据结构：")
for i, content_type in enumerate(content_types):
    print(f"  类型 {i+1}: {content_type['label']} - {content_type['count']} 条")

print("\n🎯 数据验证完成！")