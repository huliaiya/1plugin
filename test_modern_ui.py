#!/usr/bin/env python3
"""测试简洁现代风格的玻璃态UI快照渲染器"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fox_toolbox.snapshot_renderer import render_snapshot
from fox_toolbox.models import MessageStats

def test_modern_ui():
    """测试简洁现代UI渲染功能"""
    print("🧪 开始测试简洁现代UI快照渲染器...")
    
    # 创建测试数据
    stats = MessageStats(
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
    
    # 时间趋势数据
    timeline = [
        {"date": "2024-01", "count": 120, "group_count": 80, "private_count": 25, "channel_count": 15},
        {"date": "2024-02", "count": 150, "group_count": 100, "private_count": 30, "channel_count": 20},
        {"date": "2024-03", "count": 180, "group_count": 120, "private_count": 35, "channel_count": 25},
        {"date": "2024-04", "count": 200, "group_count": 130, "private_count": 40, "channel_count": 30},
        {"date": "2024-05", "count": 220, "group_count": 140, "private_count": 45, "channel_count": 35},
        {"date": "2024-06", "count": 250, "group_count": 160, "private_count": 50, "channel_count": 40},
        {"date": "2024-07", "count": 280, "group_count": 180, "private_count": 55, "channel_count": 45},
        {"date": "2024-08", "count": 320, "group_count": 200, "private_count": 60, "channel_count": 60},
    ]
    
    # 发送者排行
    sender_ranking = [
        {"sender_id": "user_001", "sender_name": "张三", "platform": "telegram", "count": 156},
        {"sender_id": "user_002", "sender_name": "李四", "platform": "discord", "count": 134},
        {"sender_id": "user_003", "sender_name": "王五", "platform": "qq", "count": 98},
        {"sender_id": "user_004", "sender_name": "赵六", "platform": "wechat", "count": 76},
        {"sender_id": "user_005", "sender_name": "钱七", "platform": "telegram", "count": 65},
        {"sender_id": "user_006", "sender_name": "孙八", "platform": "discord", "count": 54},
        {"sender_id": "user_007", "sender_name": "周九", "platform": "qq", "count": 43},
        {"sender_id": "user_008", "sender_name": "吴十", "platform": "wechat", "count": 32},
    ]
    
    # 群组排行
    group_ranking = [
        {"group_id": "group_001", "platform": "telegram", "count": 234, "sender_count": 15},
        {"group_id": "group_002", "platform": "discord", "count": 198, "sender_count": 12},
        {"group_id": "group_003", "platform": "qq", "count": 156, "sender_count": 10},
        {"group_id": "group_004", "platform": "wechat", "count": 123, "sender_count": 8},
        {"group_id": "group_005", "platform": "telegram", "count": 98, "sender_count": 6},
        {"group_id": "group_006", "platform": "discord", "count": 76, "sender_count": 5},
        {"group_id": "group_007", "platform": "qq", "count": 54, "sender_count": 4},
        {"group_id": "group_008", "platform": "wechat", "count": 32, "sender_count": 3},
    ]
    
    # 内容类型分布
    content_types = [
        {"type": "text", "label": "文本消息", "count": 856},
        {"type": "image", "label": "图片消息", "count": 234},
        {"type": "file", "label": "文件消息", "count": 89},
        {"type": "video", "label": "视频消息", "count": 45},
        {"type": "voice", "label": "语音消息", "count": 32},
    ]
    
    # 平台详情
    platform_detail = [
        {"platform": "telegram", "platform_name": "Telegram", "total": 456, "group_count": 234, "private_count": 156, "channel_count": 66},
        {"platform": "discord", "platform_name": "Discord", "total": 342, "group_count": 198, "private_count": 89, "channel_count": 55},
        {"platform": "qq", "platform_name": "QQ", "total": 390, "group_count": 156, "private_count": 134, "channel_count": 100},
        {"platform": "wechat", "platform_name": "微信", "total": 68, "group_count": 32, "private_count": 24, "channel_count": 12},
    ]
    
    try:
        # 渲染快照
        start_time = time.time()
        png_data = render_snapshot(
            stats=stats,
            db_table_count=6,
            timeline=timeline,
            sender_ranking=sender_ranking,
            group_ranking=group_ranking,
            content_types=content_types,
            platform_stats=stats.platform_stats,
            platform_detail=platform_detail,
            generated_at=time.time()
        )
        end_time = time.time()
        
        # 保存结果
        output_path = "/workspace/modern_snapshot_test.png"
        with open(output_path, "wb") as f:
            f.write(png_data)
        
        # 统计信息
        file_size = len(png_data) / 1024  # KB
        render_time = end_time - start_time
        
        print(f"✅ 渲染完成！")
        print(f"📁 输出文件: {output_path}")
        print(f"📊 文件大小: {file_size:.1f} KB")
        print(f"⏱️  渲染时间: {render_time:.2f} 秒")
        print(f"📏 尺寸: 1080x?")
        
        return output_path
        
    except Exception as e:
        print(f"❌ 渲染失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = test_modern_ui()
    if result:
        print(f"\n🎉 测试成功！请查看生成的图片: {result}")
    else:
        print("\n💥 测试失败！")