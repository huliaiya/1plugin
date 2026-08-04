# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-04

### Changed

- **插件更名**：从 `astrbot_plugin_message_recorder`（消息记录器）更名为 `astrbot_plugin_fox_toolbox`（狐狸工具箱）
- **存储引擎迁移**：从 SQLite（aiosqlite）全面迁移至 MySQL 5.7（aiomysql），MySQL 成为唯一存储方式
- **核心目录更名**：`message_recorder/` 目录更名为 `fox_toolbox/`
- **全文搜索迁移**：从 SQLite FTS5 迁移至 MySQL FULLTEXT 索引（ngram 分词器，支持中文）
- **连接池管理**：使用 aiomysql 连接池替代 SQLite 单连接，支持并发读写
- **日志前缀变更**：所有日志前缀从 `[MessageRecorder]` 变更为 `[FoxToolbox]`
- **Web API 路由前缀变更**：从 `/message_recorder/api/` 变更为 `/astrbot_plugin_fox_toolbox/`
- **UI 升级**：Web 管理面板全面采用 Liquid Glass 液态玻璃设计风格
- **动态背景**：添加多层径向渐变背景，为玻璃质感提供色彩底衬
- **玻璃质感**：所有卡片、导航栏、模态框使用 `backdrop-filter` 实现半透明磨砂玻璃效果，配合渐变高光模拟玻璃折射
- **交互动画**：统计卡片悬停浮起、内部流动光斑动画、按钮高光反射、卡片入场动画
- **优雅降级**：不支持 `backdrop-filter` 的浏览器自动回退为不透明背景
- **无障碍**：尊重 `prefers-reduced-motion` 偏好，自动禁用动画

### Added

- MySQL 数据库连接配置项（`mysql_host`、`mysql_port`、`mysql_user`、`mysql_password`、`mysql_database`）
- MySQL 连接池初始化与自动表结构创建
- MySQL Schema 版本管理与迁移机制
- 测试环境 MySQL 集成测试支持（通过环境变量配置连接）

### Removed

- 移除 SQLite（aiosqlite）依赖
- 移除 SQLite WAL 模式与 FTS5 相关代码
- 移除 `db_path` 属性和本地文件路径依赖

## [0.0.3] - 2026-06-01

### Changed

- **平台适配器全面重写**：对齐 AstrBot 实际注册的全部 18 个平台，删除不存在的 `qq_private` / `wechat` 适配器，补全所有缺失平台
- **消息类型判定改用 `MessageType` 枚举**：基类 `determine_message_type` 直接读取 AstrBot 已提供的 `message_obj.type`，不再通过 `group_id` 猜测，准确率 100%
- **新增 `ChannelBasedAdapter`**：统一处理 Discord、Slack、Mattermost、Kook 等频道型平台，`group_id` 即 channel ID，消息类型记录为 `"channel"`
- **修复 Discord 适配器 Bug**：`extract_channel_id` 不再检查不存在的 `message_obj.channel_id` 属性，改为从 `group_id` 提取

### Added

- 注册全部 18 个 AstrBot 平台适配器：telegram、discord、slack、mattermost、kook、aiocqhttp、qq_official、qq_official_webhook、dingtalk、lark、wecom、wecom_ai_bot、weixin_oc、weixin_official_account、line、misskey、satori、webchat
- `ChannelBasedAdapter` 频道型平台适配器（Discord / Slack / Mattermost / Kook）

### Removed

- 删除 `QQPrivateAdapter`（`qq_private` 不是 AstrBot 平台名）
- 删除 `WechatAdapter`（`wechat` 不是 AstrBot 平台名）
- 删除 `QQOfficialAdapter` 子类覆盖（基类已通过 `MessageType` 覆盖）

## [0.0.2] - 2025-05-28

### Changed

- **项目结构重组**：将核心模块移入 `message_recorder/` 子目录，`main.py` 通过 `sys.path` 引入插件根目录，使用 `from message_recorder.xxx` 形式导入，避免与其他插件冲突
- **许可证变更**：从 MIT License 更改为 GNU Affero General Public License v3.0
- **配置默认值调整**：`max_records` 默认值从 `100000` 改为 `0`（不限制），`retention_days` 默认值从 `30` 改为 `0`（永久保留）

### Added

- 新增 `message_recorder/` 目录，包含以下模块：
  - `api.py` — 对外 API 接口
  - `database.py` — SQLite 数据库操作
  - `media_downloader.py` — 多媒体文件下载与保存
  - `models.py` — 数据模型定义（MessageRecord、QueryFilter、MessageStats）
  - `platform_adapter.py` — 平台适配器（支持全部 AstrBot 平台）
  - `serializer.py` — 消息链序列化与反序列化
  - `time_utils.py` — 时间解析与格式化工具
  - `web_api.py` — Web API 注册模块
- 新增 `CHANGELOG.md` 变更日志文件
- 完整的单元测试套件（220 个测试用例）

### Removed

- 移除根目录下的散落模块文件（已移入 `message_recorder/` 目录）

## [0.0.1] - 2024-12-01

### Added

- 初始发布版本
- 多平台消息记录（支持全部 AstrBot 平台）
- SQLite 数据库存储（WAL 模式）
- 完整消息链、回复关系、内容哈希去重
- 多媒体文件保存（图片、语音、视频、文件）
- Web 管理面板（仪表盘、消息搜索、数据导入导出）
- 指令系统（stats、query、search、today、yesterday、history）
- 对外 API 接口供其他插件调用
- 自动清理过期数据和孤立媒体文件
- FTS5 全文搜索索引
- JSON/CSV/ZIP 格式导入导出
