# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - 2026-08-04

### Fixed

- **修复趋势图加载失败**：彻底重写 `get_timeline_stats` 为 Python 端分组，不再使用 MySQL 日期函数
- 趋势图 API 出错时返回空数据而非错误响应，前端不再显示"趋势图加载失败"
- 前端移除趋势图错误时的 `showSectionError` 调用，改为静默处理
- 修复插件更新检测问题：版本号从 0.0.1 升至 0.0.2，AstrBot 可通过版本对比检测到更新

## [0.0.1] - 2026-08-04

狐狸插件首个正式版本（基于 astrbot_plugin_message_recorder 重构）。

### Changed

- **插件更名**：从 `astrbot_plugin_message_recorder`（消息记录器）更名为 `astrbot_plugin_fox_toolbox`（狐狸插件）
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

### Security

- 修复 media_downloader.py 中的 SSRF 漏洞（URL 验证 + IP 地址检查 + 文件大小限制）
- 修复 web_api.py 中的错误信息泄露（生产环境不返回详细错误堆栈）
- 修复 web_api.py 中的导入文件内存溢出（流式写入磁盘替代内存缓存）
- 修复 app.js 中的 XSS 漏洞（对所有用户可控内容进行 HTML 转义）

### Fixed

- 修复 database.py 事务回滚缺失问题（所有写操作添加 try/except 事务回滚）
- 修复 app.js ECharts 内存泄漏（替换 setInterval 为 Promise 等待器 + 清理函数）
- 修复 web_api.py 中 asyncio 任务未被跟踪的问题（添加 _background_tasks 集合）
- 优化 database.py 的 N+1 查询问题（get_unreferenced_media_paths 改为批量查询）
- 修复插件安装问题：移除非标准的根目录 `__init__.py`
- 修复 `_conf_schema.json` 中 JSON 语法错误（hint 字段未转义双引号导致安装失败）
- 修复 metadata.yaml 中无效的 `webchat` 平台声明
- 移除未使用的 `register` 导入
- **修复趋势图加载失败**：`get_timeline_stats` SQL 查询在 MySQL 5.7 下兼容性问题
  - `timestamp` 列名添加反引号避免保留字冲突
  - 使用 `DIV` 替代 `/` 确保整数除法（避免 DECIMAL 类型问题）
  - `GROUP BY` / `ORDER BY` 使用完整表达式替代别名（避免 `ONLY_FULL_GROUP_BY` 模式冲突）

### Removed

- 移除 SQLite（aiosqlite）依赖
- 移除 SQLite WAL 模式与 FTS5 相关代码
- 移除 `db_path` 属性和本地文件路径依赖
- 移除非标准的 `keywords` 字段（metadata.yaml）

---

## 原插件历史（astrbot_plugin_message_recorder）

以下为原插件 `astrbot_plugin_message_recorder` 的变更记录，仅供参考。

### [0.0.3] - 2026-06-01

- 平台适配器全面重写，对齐 AstrBot 全部 18 个平台
- 消息类型判定改用 `MessageType` 枚举
- 新增 `ChannelBasedAdapter` 频道型平台适配器

### [0.0.2] - 2025-05-28

- 项目结构重组，核心模块移入 `message_recorder/` 子目录
- 许可证变更为 AGPL v3.0
- 完整的单元测试套件（220 个测试用例）

### [0.0.1] - 2024-12-01

- 初始发布版本
- 多平台消息记录、SQLite 存储、Web 管理面板
- FTS5 全文搜索、JSON/CSV/ZIP 导入导出
