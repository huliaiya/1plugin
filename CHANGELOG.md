# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.8] - 2026-08-05

### Added

- **新增数据库状态卡片**：Dashboard 统计卡片区新增“数据库状态”卡片，默认显示“运行中”，每 3 秒切换显示“已创建 X 张表”

### Changed

- **复用 stats 数据链路提供数据库状态信息**：后端 `stats` 响应新增 `db_status` 字段，前端直接从同一条统计响应里更新数据库状态卡片，避免额外独立请求
- **刷新前端资源版本号**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.1.8`，确保 AstrBot 刷新后加载最新页面资源

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`

## [0.1.7] - 2026-08-05

### Changed

- **移除 Dashboard 中不可用的三张状态卡片**：删除「插件状态 / 健康度 / 内存占用」卡片及其前端轮询与渲染逻辑，避免页面继续展示无效或误导性状态
- **清理状态卡片相关前端逻辑**：移除状态骨架屏、状态兜底文案、资源轮换与首屏“检测中”提示，Dashboard 仅保留已验证可用的统计与图表模块

### Docs

- **补全版本说明文档**：整理 `CHANGELOG.md` 顶部重复空版本标题，保留每个版本的具体更新内容；同步更新 `README.md` 更新日志

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`

## [0.1.6] - 2026-08-05

### Fixed

- **修复 AstrBot Plugin Pages 前端资源缓存导致旧脚本持续生效**：`index.html` 为 `app.js` 与 `style.css` 增加 `?v=0.1.6` 查询参数，强制刷新页面时拉取最新前端资源
- **优化状态卡片首次加载提示**：状态卡片首屏显示从 `-` 调整为“检测中 / -- / 100 / -- MB”，降低旧缓存与加载中的误判

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`：`176 passed, 63 skipped`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox`

## [0.1.5] - 2026-08-05

### Fixed

- **修复 Windows 等非 `/proc` 环境下资源卡片恒为 `0.0 MB`**：`sys_util` 新增跨平台回退逻辑，进程内存支持 Windows `GetProcessMemoryInfo`，CPU 与运行时长支持 `time.process_time()` / `time.monotonic()` 回退
- **修复统计接口异常时三张状态卡片一起失效**：`stats` 接口改为即使数据库统计失败也返回 `plugin_status` 与空统计数据，插件状态、健康度、内存占用可以独立显示

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`：`176 passed, 63 skipped`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox`

## [0.1.4] - 2026-08-05

### Fixed

- **彻底绕开 Dashboard 状态卡片的独立路由兼容问题**：后端 `stats` 接口新增 `plugin_status` 字段，前端状态卡片改为直接读取 `stats.plugin_status`，首屏渲染与 30 秒刷新都复用同一条已验证可用的数据链路
- **统一状态数据来源**：`status` 接口与 `stats.plugin_status` 现在共用同一份状态构造逻辑，避免两条链路行为不一致

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`：`176 passed, 63 skipped`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox`

## [0.1.3] - 2026-08-05

### Fixed

- **按 AstrBot Plugin Pages 官方路由约定修复状态接口**：前端状态卡片请求从 `plugin/status` 调整为插件内相对路径 `status`，后端新增 `/{plugin_name}/status` 主路由，并保留 `/{plugin_name}/plugin/status` 兼容旧路径
- **降低状态接口路由冲突风险**：状态卡片现与官方文档示例保持一致，继续通过 `bridge.apiGet()` 调用插件内相对路径

### Verified

- 对照 AstrBot 官方 `Plugin Pages` 文档核对 `register_web_api()` 与 `bridge.apiGet()` 的路由规则

## [0.1.2] - 2026-08-05

### Fixed

- **修复 Dashboard 状态卡片只显示 `-`**：前端不再把有效的 `0` 值当作空值处理，内存和 CPU 现在稳定显示 `0.0 MB` / `0.0%`，接口失败时明确显示错误状态而不是单个 `-`
- **增强 `plugin/status` 容错**：后端按指标分别采集数据库、内存、CPU、运行时长，单项失败时仍返回可显示结果；接口内部异常时返回兜底状态数据，避免整个卡片区失效
- **修复本地测试导入路径**：新增 `astrbot_plugin_fox_toolbox` 兼容包路径，恢复测试套件按项目包名导入

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`：`176 passed, 63 skipped`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox`
- `PYTHONPATH=/workspace python3 -c "import conftest, main; print('main import ok')"`

## [0.1.1] - 2026-08-05

### Fixed

- **修复状态卡片显示 '-'**：添加 `console.log` 诊断日志定位 `plugin/status` API 失败原因，新增 `clearStatusSkeletons()` 安全函数兜底清除骨架屏
- **增大图表高度**：消息时间趋势图从 280px 增至 340px，响应式断点同步调整

## [0.1.0] - 2026-08-05

### Fixed

- **修复 Dashboard 三张图表不显示**：时间趋势图、内容类型图、平台详情图在后端异常时返回 `success: true` + 空数据，前端拿不到错误信息导致图表区域空白。现改为异常时返回 `success: false`，前端 catch 块显示"暂无数据"占位符和错误原因
- **修复状态卡片 skeleton 永远不消失**：插件状态/健康度/内存占用三张卡片在 `plugin/status` API 失败时，catch 块只记日志不清 skeleton，导致卡片永远卡在加载动画。现 catch 块正确清除 skeleton 并显示"加载失败"
- **修复状态卡片 skeleton 安全清除**：新增 `clearStatusSkeletons()` 安全函数，在 `loadDashboardData` 的 `catch`/`finally` 块中兜底清除骨架屏，确保无论 API 成功或失败，状态卡片都不会永远卡在加载动画
- **增大消息时间趋势图高度**：图表区域从 280px 增大至 340px，响应式断点同步调整，图表线条更舒展
- 后端错误响应不再泄露内部异常详情（统一返回通用错误消息，详细信息仅写入日志）

### Changed

- **版本号语义化**：从 `0.0.11` 升级至 `0.1.0`，遵循语义化版本规范——`0.0.10` 之后进入 `0.1.x` 系列

### Security

- `_build_query_filter_from_dict` 新增 `order` 白名单校验（仅允许 `asc`/`desc`）
- `api_import_init` 新增 `file_size > 0` 校验，`chunk_size` 钳位到 `[1MB, 5MB]`
- 导入 merge 模式异常记录日志而非静默吞没
- `cleanup_expired_tasks` 新增崩溃任务清理（2 小时未完成视为崩溃）

## [0.0.11] - 2026-08-05

### Added

- **WebUI 新增「插件状态」卡片**：Dashboard 统计区新增插件健康状态展示，后端通过 `Database.ping()` 轻量探测数据库连通性，正常显示绿色「健康」，异常显示红色「异常」并附悬停提示
- **WebUI 新增「资源占用」卡片**：展示插件进程内存占用（MB）与 CPU 使用率（%），每 3 秒自动轮换切换显示，数据每 30 秒静默刷新
- 新增后端接口 `GET /fox_toolbox/plugin/status`，返回健康状态、数据库连接、CPU/内存/运行时长与 schema 版本
- 新增 `fox_toolbox/sys_util.py`：基于标准库读取进程资源（Linux 读取 `/proc`，macOS/BSD 回退 `resource` 模块），不引入第三方依赖

### Changed

- 统计卡片网格改为自适应布局（`auto-fit` + `minmax`），从 5 列调整至可容纳 7 张卡片
- 新增 `.stat-plain` 样式类：状态/资源卡片禁用渐变透明文字，确保状态颜色与数值可读

## [0.0.10] - 2026-08-05

### Added

- **WebUI 统计卡片新增「频道消息」**：Dashboard 统计区在「总消息数 / 群聊消息 / 私聊消息 / 平台数」之外新增「频道消息」卡片，展示 `channel_message_count`（后端统计接口与数据库查询此前已支持该字段，本次仅补充前端展示）

### Changed

- 统计卡片网格从 4 列调整为 5 列；第 5 张卡片补齐浮动动画相位与 `prefers-reduced-motion` 适配

## [0.0.9] - 2026-08-05

### Performance

- **WebUI 页面大幅减少卡顿**：
  - 移除大面积卡片（`.card`、图表容器 `.chart-container`、筛选区 `.filter-section`）的持续浮动动画，仅保留一次性入场动画，显著降低 backdrop-filter 持续合成开销
  - 统计卡片浮动动画周期放缓（6s -> 12s），保留"波浪"质感同时降低渲染负担
  - 消息卡片移除 backdrop-filter，改用接近不透明白色背景，搜索页上百条卡片滚动时不再反复重采样背景
  - body 背景移除 `background-attachment: fixed`，消除移动端固定背景的滚动性能问题
  - 消息列表渲染改为分批渲染（每批 40 条 + `requestAnimationFrame`），避免一次插入上百条卡片长时间阻塞主线程
  - 消息列表事件绑定改为容器级事件委托，搜索页不再为每条卡片创建多个监听器

## [0.0.8] - 2026-08-05

### Fixed

- **修复 WebUI 小文件导出下载失败**：`downloadExportFile` 读取 `export/download_data` 响应时缺少 `extractData()`，导致 `base64` 字段始终取不到，≤50MB 的文件下载必定失败；已改用 `extractData(result)` 后再读取 `data.base64`/`data.mimetype`/`data.filename`
- **修复 `test_schema_version` 测试断言过时**：`SCHEMA_VERSION` 已升级至 3，测试断言仍为 2，已同步更新

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
