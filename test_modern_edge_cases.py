#!/usr/bin/env python3
"""测试边界情况和空数据的现代UI渲染器"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

def test_edge_cases():
    """测试边界情况和空数据"""
    print("🧪 开始测试边界情况和空数据...")
    
    # 测试空数据
    empty_stats = MessageStats(
        total_count=0,
        group_message_count=0,
        private_message_count=0,
        channel_message_count=0,
        newest_timestamp=0,
        platform_stats={}
    )
    
    empty_timeline = []
    empty_sender_ranking = []
    empty_group_ranking = []
    empty_content_types = []
    empty_platform_detail = []
    
    try:
        # 测试空数据渲染
        print("📋 测试空数据渲染...")
        start_time = time.time()
        png_data = render_snapshot(
            stats=empty_stats,
            db_table_count=0,
            timeline=empty_timeline,
            sender_ranking=empty_sender_ranking,
            group_ranking=empty_group_ranking,
            content_types=empty_content_types,
            platform_stats={},
            platform_detail=empty_platform_detail,
            generated_at=time.time()
        )
        end_time = time.time()
        
        # 保存空数据测试结果
        output_path = "/workspace/modern_snapshot_empty.png"
        with open(output_path, "wb") as f:
            f.write(png_data)
        
        print(f"✅ 空数据渲染完成！")
        print(f"📁 输出文件: {output_path}")
        print(f"📊 文件大小: {len(png_data) / 1024:.1f} KB")
        print(f"⏱️  渲染时间: {end_time - start_time:.2f} 秒")
        
        # 测试少量数据
        print("\n📋 测试少量数据...")
        small_stats = MessageStats(
            total_count=464,  # 用户提到的数据量
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
        
        small_timeline = [
            {"date": "2024-07", "count": 150, "group_count": 100, "private_count": 30, "channel_count": 20},
            {"date": "2024-08", "count": 180, "group_count": 120, "private_count": 40, "channel_count": 20},
            {"date": "2024-09", "count": 134, "group_count": 80, "private_count": 50, "channel_count": 4},
        ]
        
        small_sender_ranking = [
            {"sender_id": "user_001", "sender_name": "用户A", "platform": "telegram", "count": 89},
            {"sender_id": "user_002", "sender_name": "用户B", "platform": "discord", "count": 67},
            {"sender_id": "user_003", "sender_name": "用户C", "platform": "qq", "count": 45},
            {"sender_id": "user_004", "sender_name": "用户D", "platform": "wechat", "count": 32},
            {"sender_id": "user_005", "sender_name": "用户E", "platform": "telegram", "count": 28},
            {"sender_id": "user_006", "sender_name": "用户F", "platform": "discord", "count": 19},
            {"sender_id": "user_007", "sender_name": "用户G", "platform": "qq", "count": 15},
            {"sender_id": "user_008", "sender_name": "用户H", "platform": "wechat", "count": 8},
        ]
        
        small_group_ranking = [
            {"group_id": "group_001", "platform": "telegram", "count": 89, "sender_count": 8},
            {"group_id": "group_002", "platform": "discord", "count": 67, "sender_count": 6},
            {"group_id": "group_003", "platform": "qq", "count": 45, "sender_count": 4},
            {"group_id": "group_004", "platform": "wechat", "count": 32, "sender_count": 3},
            {"group_id": "group_005", "platform": "telegram", "count": 28, "sender_count": 3},
            {"group_id": "group_006", "platform": "discord", "count": 19, "sender_count": 2},
            {"group_id": "group_007", "platform": "qq", "count": 15, "sender_count": 2},
            {"group_id": "group_008", "platform": "wechat", "count": 8, "sender_count": 1},
        ]
        
        small_content_types = [
            {"type": "text", "label": "文本", "count": 300},
            {"type": "image", "label": "图片", "count": 120},
            {"type": "file", "label": "文件", "count": 30},
            {"type": "video", "label": "视频", "count": 10},
            {"type": "voice", "label": "语音", "count": 4},
        ]
        
        small_platform_detail = [
            {"platform": "telegram", "platform_name": "Telegram", "total": 200, "group_count": 120, "private_count": 60, "channel_count": 20},
            {"platform": "discord", "platform_name": "Discord", "total": 150, "group_count": 80, "private_count": 45, "channel_count": 25},
            {"platform": "qq", "platform_name": "QQ", "total": 80, "group_count": 50, "private_count": 20, "channel_count": 10},
            {"platform": "wechat", "platform_name": "微信", "total": 34, "group_count": 20, "private_count": 10, "channel_count": 4},
        ]
        
        start_time = time.time()
        png_data_small = render_snapshot(
            stats=small_stats,
            db_table_count=3,
            timeline=small_timeline,
            sender_ranking=small_sender_ranking,
            group_ranking=small_group_ranking,
            content_types=small_content_types,
            platform_stats=small_stats.platform_stats,
            platform_detail=small_platform_detail,
            generated_at=time.time()
        )
        end_time = time.time()
        
        # 保存少量数据测试结果
        output_path_small = "/workspace/modern_snapshot_small.png"
        with open(output_path_small, "wb") as f:
            f.write(png_data_small)
        
        print(f"✅ 少量数据渲染完成！")
        print(f"📁 输出文件: {output_path_small}")
        print(f"📊 文件大小: {len(png_data_small) / 1024:.1f} KB")
        print(f"⏱️  渲染时间: {end_time - start_time:.2f} 秒")
        
        return [output_path, output_path_small]
        
    except Exception as e:
        print(f"❌ 边界测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    results = test_edge_cases()
    if results:
        print(f"\n🎉 边界测试成功！")
        print(f"📁 空数据测试: {results[0]}")
        print(f"📁 少量数据测试: {results[1]}")
    else:
        print("\n💥 边界测试失败！")