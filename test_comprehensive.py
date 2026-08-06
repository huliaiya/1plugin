#!/usr/bin/env python3
"""完整测试新的简洁现代UI快照渲染器"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

def test_comprehensive():
    """全面测试新的UI渲染器"""
    print("🧪 开始全面测试简洁现代UI快照渲染器...")
    
    # 测试数据1：正常数据量
    stats1 = MessageStats(
        total_count=1256,
        group_message_count=892,
        private_message_count=234,
        channel_message_count=130,
        newest_timestamp=int(time.time() * 1000),
        platform_stats={
            "telegram": 456,
            "discord": 342,
            "qq_official": 234,
            "qq_private": 156,
            "wechat": 68
        }
    )
    
    timeline1 = [
        {"date": "2024-01", "count": 120, "group_count": 80, "private_count": 25, "channel_count": 15},
        {"date": "2024-02", "count": 150, "group_count": 100, "private_count": 30, "channel_count": 20},
        {"date": "2024-03", "count": 180, "group_count": 120, "private_count": 35, "channel_count": 25},
        {"date": "2024-04", "count": 200, "group_count": 130, "private_count": 40, "channel_count": 30},
        {"date": "2024-05", "count": 220, "group_count": 140, "private_count": 45, "channel_count": 35},
        {"date": "2024-06", "count": 250, "group_count": 160, "private_count": 50, "channel_count": 40},
        {"date": "2024-07", "count": 280, "group_count": 180, "private_count": 55, "channel_count": 45},
        {"date": "2024-08", "count": 320, "group_count": 200, "private_count": 60, "channel_count": 60},
    ]
    
    sender_ranking1 = [
        {"sender_id": "user_001", "sender_name": "张三", "platform": "telegram", "count": 156},
        {"sender_id": "user_002", "sender_name": "李四", "platform": "discord", "count": 134},
        {"sender_id": "user_003", "sender_name": "王五", "platform": "qq", "count": 98},
        {"sender_id": "user_004", "sender_name": "赵六", "platform": "wechat", "count": 76},
        {"sender_id": "user_005", "sender_name": "钱七", "platform": "telegram", "count": 65},
        {"sender_id": "user_006", "sender_name": "孙八", "platform": "discord", "count": 54},
        {"sender_id": "user_007", "sender_name": "周九", "platform": "qq", "count": 43},
        {"sender_id": "user_008", "sender_name": "吴十", "platform": "wechat", "count": 32},
    ]
    
    group_ranking1 = [
        {"group_id": "group_001", "platform": "telegram", "count": 234, "sender_count": 15},
        {"group_id": "group_002", "platform": "discord", "count": 198, "sender_count": 12},
        {"group_id": "group_003", "platform": "qq", "count": 156, "sender_count": 10},
        {"group_id": "group_004", "platform": "wechat", "count": 123, "sender_count": 8},
        {"group_id": "group_005", "platform": "telegram", "count": 98, "sender_count": 6},
        {"group_id": "group_006", "platform": "discord", "count": 76, "sender_count": 5},
        {"group_id": "group_007", "platform": "qq", "count": 54, "sender_count": 4},
        {"group_id": "group_008", "platform": "wechat", "count": 32, "sender_count": 3},
    ]
    
    content_types1 = [
        {"type": "text", "label": "文本消息", "count": 856},
        {"type": "image", "label": "图片消息", "count": 234},
        {"type": "file", "label": "文件消息", "count": 89},
        {"type": "video", "label": "视频消息", "count": 45},
        {"type": "voice", "label": "语音消息", "count": 32},
    ]
    
    platform_detail1 = [
        {"platform": "telegram", "platform_name": "Telegram", "total": 456, "group_count": 234, "private_count": 156, "channel_count": 66},
        {"platform": "discord", "platform_name": "Discord", "total": 342, "group_count": 198, "private_count": 89, "channel_count": 55},
        {"platform": "qq", "platform_name": "QQ", "total": 390, "group_count": 156, "private_count": 134, "channel_count": 100},
        {"platform": "wechat", "platform_name": "微信", "total": 68, "group_count": 32, "private_count": 24, "channel_count": 12},
    ]
    
    # 测试数据2：用户报告的小数据量场景
    stats2 = MessageStats(
        total_count=464,
        group_message_count=300,
        private_message_count=120,
        channel_message_count=44,
        newest_timestamp=int(time.time() * 1000),
        platform_stats={
            "telegram": 200,
            "discord": 150,
            "qq": 80,
            "wechat": 34
        }
    )
    
    timeline2 = [
        {"date": "2024-07", "count": 150, "group_count": 100, "private_count": 30, "channel_count": 20},
        {"date": "2024-08", "count": 180, "group_count": 120, "private_count": 40, "channel_count": 20},
        {"date": "2024-09", "count": 134, "group_count": 80, "private_count": 50, "channel_count": 4},
    ]
    
    sender_ranking2 = [
        {"sender_id": "user_001", "sender_name": "用户A", "platform": "telegram", "count": 89},
        {"sender_id": "user_002", "sender_name": "用户B", "platform": "discord", "count": 67},
        {"sender_id": "user_003", "sender_name": "用户C", "platform": "qq", "count": 45},
        {"sender_id": "user_004", "sender_name": "用户D", "platform": "wechat", "count": 32},
        {"sender_id": "user_005", "sender_name": "用户E", "platform": "telegram", "count": 28},
        {"sender_id": "user_006", "sender_name": "用户F", "platform": "discord", "count": 19},
        {"sender_id": "user_007", "sender_name": "用户G", "platform": "qq", "count": 15},
        {"sender_id": "user_008", "sender_name": "用户H", "platform": "wechat", "count": 8},
    ]
    
    group_ranking2 = [
        {"group_id": "group_001", "platform": "telegram", "count": 89, "sender_count": 8},
        {"group_id": "group_002", "platform": "discord", "count": 67, "sender_count": 6},
        {"group_id": "group_003", "platform": "qq", "count": 45, "sender_count": 4},
        {"group_id": "group_004", "platform": "wechat", "count": 32, "sender_count": 3},
        {"group_id": "group_005", "platform": "telegram", "count": 28, "sender_count": 3},
        {"group_id": "group_006", "platform": "discord", "count": 19, "sender_count": 2},
        {"group_id": "group_007", "platform": "qq", "count": 15, "sender_count": 2},
        {"group_id": "group_008", "platform": "wechat", "count": 8, "sender_count": 1},
    ]
    
    content_types2 = [
        {"type": "text", "label": "文本", "count": 300},
        {"type": "image", "label": "图片", "count": 120},
        {"type": "file", "label": "文件", "count": 30},
        {"type": "video", "label": "视频", "count": 10},
        {"type": "voice", "label": "语音", "count": 4},
    ]
    
    platform_detail2 = [
        {"platform": "telegram", "platform_name": "Telegram", "total": 200, "group_count": 120, "private_count": 60, "channel_count": 20},
        {"platform": "discord", "platform_name": "Discord", "total": 150, "group_count": 80, "private_count": 45, "channel_count": 25},
        {"platform": "qq", "platform_name": "QQ", "total": 80, "group_count": 50, "private_count": 20, "channel_count": 10},
        {"platform": "wechat", "platform_name": "微信", "total": 34, "group_count": 20, "private_count": 10, "channel_count": 4},
    ]
    
    test_cases = [
        ("正常数据量", stats1, timeline1, sender_ranking1, group_ranking1, content_types1, platform_detail1),
        ("小数据量(464条)", stats2, timeline2, sender_ranking2, group_ranking2, content_types2, platform_detail2),
        ("空数据", MessageStats(total_count=0, group_message_count=0, private_message_count=0, channel_message_count=0, newest_timestamp=0, platform_stats={}), [], [], [], [], []),
    ]
    
    results = []
    
    for test_name, stats, timeline, sender_ranking, group_ranking, content_types, platform_detail in test_cases:
        print(f"\n📋 测试: {test_name}")
        try:
            start_time = time.time()
            png_data = render_snapshot(
                stats=stats,
                db_table_count=len(stats.platform_stats) if stats.platform_stats else 0,
                timeline=timeline,
                sender_ranking=sender_ranking,
                group_ranking=group_ranking,
                content_types=content_types,
                platform_stats=stats.platform_stats,
                platform_detail=platform_detail,
                generated_at=time.time()
            )
            end_time = time.time()
            
            output_path = f"/workspace/modern_snapshot_{test_name.replace(' ', '_').lower()}.png"
            with open(output_path, "wb") as f:
                f.write(png_data)
            
            file_size = len(png_data) / 1024
            render_time = end_time - start_time
            
            print(f"✅ {test_name} 渲染完成")
            print(f"   📁 输出文件: {output_path}")
            print(f"   📊 文件大小: {file_size:.1f} KB")
            print(f"   ⏱️  渲染时间: {render_time:.2f} 秒")
            
            results.append((test_name, output_path, file_size, render_time))
            
        except Exception as e:
            print(f"❌ {test_name} 渲染失败: {e}")
            import traceback
            traceback.print_exc()
    
    return results

if __name__ == "__main__":
    results = test_comprehensive()
    print(f"\n🎉 全面测试完成！共测试 {len(results)} 个场景")
    for test_name, output_path, file_size, render_time in results:
        print(f"✅ {test_name}: {output_path} ({file_size:.1f}KB, {render_time:.2f}s)")