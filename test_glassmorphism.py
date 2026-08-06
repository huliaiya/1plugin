#!/usr/bin/env python3
"""测试改进后的玻璃态UI快照渲染器"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

def test_glassmorphism_ui():
    """测试玻璃态UI渲染功能"""
    print("🧪 开始测试玻璃态UI快照渲染器...")
    
    # 创建测试数据
    stats = MessageStats(
        total_count=12580,
        group_message_count=8920,
        private_message_count=2650,
        channel_message_count=1010,
        newest_timestamp=int(time.time() * 1000),
        platform_stats={
            "telegram": 5420,
            "discord": 3890,
            "qq_official": 2100,
            "wechat": 1170
        }
    )
    
    # 测试数据
    timeline = [
        {"date": "2026-01-01", "count": 120, "group_count": 80, "private_count": 30, "channel_count": 10},
        {"date": "2026-01-02", "count": 150, "group_count": 100, "private_count": 40, "channel_count": 10},
        {"date": "2026-01-03", "count": 180, "group_count": 120, "private_count": 50, "channel_count": 10},
        {"date": "2026-01-04", "count": 200, "group_count": 140, "private_count": 50, "channel_count": 10},
        {"date": "2026-01-05", "count": 220, "group_count": 160, "private_count": 50, "channel_count": 10},
        {"date": "2026-01-06", "count": 250, "group_count": 180, "private_count": 60, "channel_count": 10},
        {"date": "2026-01-07", "count": 280, "group_count": 210, "private_count": 60, "channel_count": 10},
    ]
    
    sender_ranking = [
        {"sender_name": "用户A", "count": 1250},
        {"sender_name": "用户B", "count": 980},
        {"sender_name": "用户C", "count": 750},
        {"sender_name": "用户D", "count": 620},
        {"sender_name": "用户E", "count": 480},
        {"sender_name": "用户F", "count": 350},
        {"sender_name": "用户G", "count": 220},
        {"sender_name": "用户H", "count": 180},
    ]
    
    group_ranking = [
        {"group_id": "group1", "platform": "telegram", "count": 2150, "sender_count": 45},
        {"group_id": "group2", "platform": "discord", "count": 1890, "sender_count": 38},
        {"group_id": "group3", "platform": "qq", "count": 1650, "sender_count": 32},
        {"group_id": "group4", "platform": "wechat", "count": 1420, "sender_count": 28},
        {"group_id": "group5", "platform": "telegram", "count": 1200, "sender_count": 25},
        {"group_id": "group6", "platform": "discord", "count": 980, "sender_count": 20},
        {"group_id": "group7", "platform": "qq", "count": 750, "sender_count": 15},
        {"group_id": "group8", "platform": "wechat", "count": 520, "sender_count": 12},
    ]
    
    content_types = [
        {"type": "Plain", "label": "文本消息", "count": 8900},
        {"type": "Image", "label": "图片消息", "count": 2100},
        {"type": "File", "label": "文件消息", "count": 980},
        {"type": "Video", "label": "视频消息", "count": 420},
        {"type": "Record", "label": "语音消息", "count": 180},
    ]
    
    platform_detail = [
        {"platform": "telegram", "platform_name": "Telegram", "total": 5420, "group_count": 3800, "private_count": 1200, "channel_count": 420},
        {"platform": "discord", "platform_name": "Discord", "total": 3890, "group_count": 2800, "private_count": 890, "channel_count": 200},
        {"platform": "qq_official", "platform_name": "QQ官方", "total": 2100, "group_count": 1500, "private_count": 500, "channel_count": 100},
        {"platform": "wechat", "platform_name": "微信", "total": 1170, "group_count": 820, "private_count": 260, "channel_count": 90},
    ]
    
    try:
        # 渲染快照
        print("🎨 正在渲染高级玻璃态UI快照...")
        start_time = time.time()
        
        png_data = render_snapshot(
            stats=stats,
            db_table_count=12,
            timeline=timeline,
            sender_ranking=sender_ranking,
            group_ranking=group_ranking,
            content_types=content_types,
            platform_stats=stats.platform_stats,
            platform_detail=platform_detail,
            generated_at=time.time()
        )
        
        end_time = time.time()
        render_time = end_time - start_time
        
        # 保存测试结果
        output_path = project_root / "test_glassmorphism_snapshot.png"
        output_path.write_bytes(png_data)
        
        print(f"✅ 玻璃态UI快照渲染成功！")
        print(f"📊 文件大小: {len(png_data) / 1024:.1f} KB")
        print(f"⏱️  渲染时间: {render_time:.2f} 秒")
        print(f"💾 输出文件: {output_path}")
        
        # 验证文件
        if output_path.exists() and output_path.stat().st_size > 0:
            print("🎯 测试通过：玻璃态UI快照已成功生成")
            return True
        else:
            print("❌ 测试失败：输出文件无效")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_glassmorphism_ui()
    sys.exit(0 if success else 1)