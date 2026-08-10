# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[User Instruction Summary]
- Date: 2026-08-05
- Context: 用户要求每次修改代码后必须同步更新文档和版本号
- Instructions:
  - 每次修改代码（修复、新增、重构等任何变更），必须同步更新后缀为 .md 的说明文档（至少更新 CHANGELOG.md 和 README.md 的更新日志）
  - 每次修改代码后必须递增版本号（metadata.yaml 的 version，小版本 +1）
  - 文档更新和版本号更新缺一不可，完成代码修改后立即执行

[User Instruction Summary]
- Date: 2026-08-05
- Context: 用户纠正版本号写法：0.1.13 应进位为 0.2.0
- Instructions:
  - 版本号规范：patch（第三位）达到 10 时进位到 minor（第二位 +1）并将第三位置 0，不使用 0.1.13、0.2.11 这种写法
  - 示例：0.2.10 的下一个版本是 0.3.0（而不是 0.2.11），之后依次为 0.3.1、0.3.2...，到 0.3.10 后再进位为 0.4.0
  - 版本号改动需同时同步 metadata.yaml、app.js BUILD_VERSION、index.html `?v=`、CHANGELOG.md、README.md
  - 若已使用了违规版本号（如 0.2.11、0.2.12），需合并为正确的进位版本号（如 0.3.0），而不是继续递增

[Project Knowledge Summary]
- Date: 2026-08-05
- Context: Discovered by Agent while performing Dashboard 状态卡片修复与可运行性验证
- Category: Build Methods
- Instructions:
  - 本仓库本地验证可直接使用 `PYTHONPATH=/workspace python3 -m pytest -q`
  - 语法检查可使用 `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox`
  - 插件入口导入验证可使用 `PYTHONPATH=/workspace python3 -c "import conftest, main; print('main import ok')"`

[Project Knowledge Summary]
- Date: 2026-08-08
- Context: Discovered by Agent while performing 全库死代码清理（曾漏扫 tests/ 导致误删被测试引用的常量）
- Category: Testing Methods
- Instructions:
  - 死代码/未使用检查（pyflakes、vulture、grep 验证）必须同时扫描 `fox_toolbox/`、`main.py`、`tests/` 三处，遗漏 tests/ 会误删被测试引用的公共符号
  - pyflakes 命令：`python3 -m pyflakes fox_toolbox/ main.py tests/`
  - vulture 报的 `__aexit__(*exc)`、mock `execute(*a, **k)`、redis `set(ex=None)` 参数是协议/API 兼容性必需，属误报，不要改
  - serializer.py 的 `MEDIA_COMPONENT_TYPES`/`COMPONENT_TYPE_MEDIA_MAP`/`ALL_KNOWN_COMPONENT_TYPES` 被 tests/test_serializer.py 引用，属公共常量，勿删

[User Instruction Summary]
- Date: 2026-08-10
- Context: 用户要求全面检查插件目录并处理无用目录
- Instructions:
  - 判断插件目录是否无用后，删除前必须先向用户确认；未确认时只做检查和报告
