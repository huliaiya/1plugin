# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.7] - 2026-08-05

### Added

- **WebUI 全面响应式自适应**：新增三套断点（平板 769~1024px、手机 ≤768px、小手机 ≤480px），完美适配手机、平板、电脑三种设备
  - 手机端：统计卡片 2 列布局、图表单列、筛选区垂直排列、按钮和字体缩小、模态框全宽
  - 平板端：统计卡片 2 列、图表单列、保持舒适间距
  - 小手机端：进一步缩减字号和间距，确保 320px 屏幕可用
- 新增 HTML viewport meta 标签（`width=device-width, initial-scale=1.0`），修复手机端默认缩放问题
- 新增 `theme-color` 和 `apple-mobile-web-app-capable` meta 标签，优化移动端浏览器体验
- 数据表格手机端水平滚动（`overflow-x: auto` + `-webkit-overflow-scrolling: touch`），保持表格完整性
- 手机端浮动动画幅度降低（6px -> 3px），减少移动设备抖动感

### Fixed

- **修复 `.card` 浮动动画不生效**：移除 `contain: layout paint`（与 `translate` 动画冲突导致大卡片浮动不可见），替换为 `will-change: translate`

### Changed

- 手机端 CSS 变量动态调整：圆角缩小（16px -> 12px）、模糊半径降低（14px -> 10px），减少移动设备渲染负担
- 导出格式选项在手机端改为水平排列（图标+文字横排），节省垂直空间
- 消息详情模态框在手机端 `detail-row` 改为垂直排列，标签和值分两行显示

## [0.0.6] - 2026-08-05

### Fixed

- **修复时间趋势图频道数据不显示**：`get_timeline_stats` 未返回 `channel_count` 字段，导致前端频道折线图始终为 0
- **修复消息链 URL 的 XSS 漏洞**：新增 `safeUrl()` 函数，仅允许 `http`/`https` 协议，防止 `javascript:` 等恶意协议
- 前端时间趋势图 `setOption` 添加 `notMerge: true`，确保频道数据系列完整渲染
- 所有数据系列添加 `|| 0` 回退，防止 `undefined` 导致折线断裂

### Added

- **全卡片浮动动画**：图表容器（`.chart-container`）、筛选区（`.filter-section`）现在与统计卡片、内容卡片一样拥有浮动动画效果
- 图表容器浮动相位错开（波浪效果），各容器以不同延迟浮动，视觉更自然
- 时间趋势图四条数据线添加明确颜色：总消息（蓝）、群聊（绿）、私聊（橙）、频道（红）

### Changed

- `cardFloat` 动画统一应用于所有玻璃卡片元素（`.card`、`.stat-card`、`.chart-container`、`.filter-section`）
- `prefers-reduced-motion` 媒体查询同步更新，覆盖所有新增浮动元素

## [0.0.5] - 2026-08-04

### Added

- **文件类型细分**：File 组件根据扩展名自动分类为文档/音频/压缩包/代码/图片/视频六种子类型
- **更多文件扩展名支持**：新增 50+ 种文件扩展名分类（csv, log, wav, amr, heic, iso, jar, kt, swift, scala 等）
- **平台详情表格新增列**：压缩包、代码/程序两列（共 13 列）
- `media_downloader.py` 的 `KNOWN_EXTENSIONS` 同步扩展，确保文件保存时正确识别扩展名

### Fixed

- **修复统计误匹配**：SQL 查询从 `LIKE '%Image%'` 改为 `FIND_IN_SET('Image', content_types)`
  - `LIKE '%Image%'` 会同时匹配 `Image` 和 `FileImage`，导致图片计数偏高
  - `LIKE '%Video%'` 会同时匹配 `Video` 和 `FileVideo`，导致视频计数偏高
  - `LIKE '%File%'` 需要复杂的 NOT LIKE 排除链，容易遗漏
  - `FIND_IN_SET` 精确匹配逗号分隔值，彻底解决子串误匹配问题
- **修复 At 类型误匹配**：`LIKE '%At%'` 会匹配 `AtAll`，改用 `FIND_IN_SET('At')` + `FIND_IN_SET('AtAll')`

### Changed

- `get_content_type_stats` 和 `get_platform_detail_stats` 的 SQL 全部改用 `FIND_IN_SET`
- `get_platform_detail_stats` 新增 `archive_count` 和 `code_count` 返回字段
- 前端 `updatePlatformDetailTable` 同步渲染新增的压缩包和代码列

## [0.0.4] - 2026-08-05

### Added

- **消息内容类型统计**：仪表盘新增内容类型分布饼图（文字/图片/文件/视频/语音/表情/回复等）
- **平台详情统计**：仪表盘新增平台消息详情柱状图 + 详细数据表格（各平台的群聊/私聊/频道/图片/文件/视频/语音数量）
- 新增 `content_types` 数据库字段，记录每条消息包含的组件类型
- 新增 API 端点：`stats/content-types`、`stats/platforms`

### Fixed

- **修复图片/文件/视频等非文本消息不记录的问题**：消息链中的组件类型现在会被提取并存储
- 非文本消息的 `message_str` 现在会自动生成摘要（如 `[图片]`、`[文件]`、`[视频]`），方便搜索和展示

### Changed

- Schema 版本从 v2 升级至 v3（自动迁移添加 `content_types` 列）
- `MessageRecord` 新增 `content_types` 字段
- 消息列表 API 响应新增 `content_types` 字段

## [0.0.3] - 2026-08-04

### Added

- **数据库弃用表自动清理**：插件启动/重载时自动检查并删除已弃用的表
- 在 `models.py` 中新增 `DEPRECATED_TABLES` 列表，用于管理需要清理的弃用表
- 初始弃用表：`messages_fts`（原 SQLite FTS5 虚拟表，迁移到 MySQL 后已无用）
- 清理逻辑包含表名安全校验，仅允许字母、数字、下划线

### Fixed

- **修复插件更新失败**：`metadata.yaml` 的 `repo` 字段添加 `/tree/main` 分支指定
  - AstrBot 强制更新在未指定分支时默认下载 `master` 分支，但本仓库使用 `main`，导致更新失败
  - 显式指定 `main` 分支后，强制更新可正常工作

### Changed

- `database.py` 导入 `DEPRECATED_TABLES`，`init()` 中新增 `_cleanup_deprecated_tables()` 调用

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
