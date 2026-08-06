#!/usr/bin/env python3
"""详细调试各个函数的问题"""

import sys
sys.path.append('.')
from fox_toolbox.snapshot_renderer import _draw_content_types, _draw_platform_detail
from PIL import Image, ImageDraw
import traceback

# 创建测试画布
def create_test_canvas():
    width, height = 800, 400
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    return img, draw

# 测试 _draw_content_types 函数
print("🧪 测试 _draw_content_types 函数...")

# 测试数据
test_cases = [
    ("正常数据", [
        {"type": "text", "label": "文字", "count": 300},
        {"type": "image", "label": "图片", "count": 100},
        {"type": "file", "label": "文件", "count": 64}
    ]),
    ("空列表", []),
    ("空字典", {}),
    ("None值", None),
    ("零计数数据", [
        {"type": "text", "label": "文字", "count": 0},
        {"type": "image", "label": "图片", "count": 0}
    ]),
    ("单零计数", [
        {"type": "text", "label": "文字", "count": 0}
    ])
]

for case_name, content_types in test_cases:
    print(f"\n🔍 测试案例: {case_name}")
    try:
        img, draw = create_test_canvas()
        _draw_content_types(img, (50, 50, 750, 350), content_types)
        print(f"✅ {case_name} 成功")
        img.save(f"debug_{case_name.replace(' ', '_')}.png")
    except Exception as e:
        print(f"❌ {case_name} 失败: {e}")
        traceback.print_exc()

# 测试 _draw_platform_detail 函数
print("\n🧪 测试 _draw_platform_detail 函数...")

platform_test_cases = [
    ("正常数据", [
        {'platform': 'telegram', 'platform_name': 'Telegram', 'total': 280, 'group_count': 180, 'private_count': 60, 'channel_count': 40},
        {'platform': 'discord', 'platform_name': 'Discord', 'total': 120, 'group_count': 80, 'private_count': 25, 'channel_count': 15}
    ]),
    ("空列表", []),
    ("空字典", {}),
    ("None值", None),
    ("零计数数据", [
        {'platform': 'telegram', 'platform_name': 'Telegram', 'total': 0, 'group_count': 0, 'private_count': 0, 'channel_count': 0}
    ])
]

for case_name, platforms in platform_test_cases:
    print(f"\n🔍 测试案例: {case_name}")
    try:
        img, draw = create_test_canvas()
        _draw_platform_detail(img, (50, 50, 750, 350), platforms)
        print(f"✅ {case_name} 成功")
        img.save(f"debug_platform_{case_name.replace(' ', '_')}.png")
    except Exception as e:
        print(f"❌ {case_name} 失败: {e}")
        traceback.print_exc()

print("\n🎉 测试完成！")
