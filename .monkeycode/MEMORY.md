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

[Project Knowledge Summary]
- Date: 2026-08-05
- Context: Discovered by Agent while performing Dashboard 状态卡片修复与可运行性验证
- Category: Build Methods
- Instructions:
  - 本仓库本地验证可直接使用 `PYTHONPATH=/workspace python3 -m pytest -q`
  - 语法检查可使用 `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox`
  - 插件入口导入验证可使用 `PYTHONPATH=/workspace python3 -c "import conftest, main; print('main import ok')"`
