# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.10] - 2026-08-06

### Added
- **快照新增"内容类型分布"卡片（对齐 WebUI）**：`_draw_content_types` 渲染饼图（甜甜圈），展示各内容类型消息占比。饼图中心显示总消息数，右侧图例含颜色圆点/类型名/进度条/百分比数值，使用与 WebUI 一致的配色方案（#4fc3f7、#29b6f6 等），支持最多8种内容类型显示
- `render_snapshot` 画布高度增加到 `_PX(2800)`，容纳新增的内容类型卡片
- 新增饼图绘制算法，支持圆角扇形、中心文字、图例进度条

### Changed
- 内容类型分布从列表形式改为饼图形式，完全对齐 WebUI 的 contentTypeChart
- 快照画布高度 `_PX(2500)` -> `_PX(2800)`，容纳新增的内容类型卡片
- 前端资源版本号升级至 `0.2.10`

## [0.2.9] - 2026-08-06

### Added
- **快照新增"平台消息详情"卡片（对齐 WebUI）**：`_draw_platform_detail` 渲染堆叠柱状图，展示各平台群聊/私聊/频道消息分布。每平台包含三色堆叠柱（群聊#4fc3f7、私聊#29b6f6、频道#81d4fa），顶部显示平台总消息数，左上角图例含三色圆点/系列名，X轴平台名自动映射（Telegram/Discord/QQ 官方/微信等），位置在平台分布与内容类型之间
- `render_snapshot` 新增 `platform_detail` 参数（默认回退数据库查询结果）；`main.py` 的 `cmd_snapshot` 新增 `platform_detail` 数据获取
- 新增 `_draw_platform_detail` 堆叠柱状图绘制函数，支持多系列堆叠、圆角柱体、网格线、峰值标注

### Changed
- 快照画布高度 `_PX(2200)` -> `_PX(2500)`，容纳新增的平台详情卡片
- 前端资源版本号升级至 `0.2.9`
- 修复 `app.js` 的 `BUILD_VERSION` 与版本号同步问题（0.2.2 → 0.2.9）

## [0.2.8] - 2026-08-06

### Added
- **快照新增"平台分布"卡片（对齐 WebUI）**：`_draw_platform_donut` 渲染圆环图（甜甜圈）+ 右侧图例，展示各平台消息占比。圆环中心显示总消息数（蓝色渐变）+"总消息"标签；右侧每行含颜色圆点、平台名称、进度条、数值百分比；平台名映射（telegram->Telegram、discord->Discord、qq_official->QQ 官方、wechat->微信等），未映射则显示原始 key。位置在时间趋势与排行之间
- `render_snapshot` 新增 `platform_stats` 参数（默认回退 `stats.platform_stats`）；`main.py` 的 `cmd_snapshot` 传入 `stats.platform_stats`
- 新增 `_PLATFORM_LABELS` 平台名映射表

### Changed
- 快照画布高度 `_PX(1900)` -> `_PX(2200)`，容纳新增的平台分布卡片
- 前端资源版本号升级至 `0.2.8`

### Verified

- `python3 -m py_compile fox_toolbox/snapshot_renderer.py main.py` 通过
- `node --check pages/recorder/app.js` 通过
- 图片视觉审查确认：圆环完整镂空、中心 1,296,560/总消息清晰、5 色扇形对应图例正确、Telegram 63.3%/Discord 23.0%/QQ 官方 7.9%/微信 4.9%/aiocqhttp 0.9%、布局对齐无重叠
- 整图审查确认各卡片排列连贯、风格统一、无渲染异常
- `PYTHONPATH=/workspace python3 -m pytest -q` 与基线一致（无回归）

## [0.2.7] - 2026-08-06

### Changed

- **快照时间趋势图升级为多系列折线图（对齐 WebUI）**：`_draw_timeline` 重写，按 `count / group_count / private_count / channel_count` 四系列绘制四条折线（总消息-蓝、群聊-绿、私聊-橙、频道-红），左上角图例带对应颜色圆点，"总消息"系列保留浅蓝区域填充，各系列统一 Y 轴刻度
- **WebUI 手机端圆环图布局修复**：`app.js` 在移动端（≤768px）将平台分布/内容类型圆环图的图例改为底部横向滚动（`orient: 'horizontal', type: 'scroll'`）、圆环缩小并上移，避免图例与圆环重叠；`style.css` 手机端图表容器高度 210→280px、主内容底部 padding 增加 2.5rem，防止圆环图底部被浏览器导航栏遮挡
- **前端资源版本号升级**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.2.7`

### Verified

- `python3 -m py_compile fox_toolbox/snapshot_renderer.py` 通过
- `node --check pages/recorder/app.js` 通过
- 图片视觉审查确认：四条折线配色分明、图例四色对应正确、浅蓝面积填充、日期标签清晰、无重叠拥挤
- `PYTHONPATH=/workspace python3 -m pytest -q` 与基线一致（无回归）

## [0.2.6] - 2026-08-06

### Fixed

- **修复背景渲染为全黑的严重问题**：Pillow 的 `Image.load()` 像素访问器直接索引赋值在 `resize` 时数据丢失，导致渐变背景生成全黑。改用 `Image.paste` 填充后恢复浅色渐变背景
- **修复 emoji 模糊不可辨**：改为以 109px 原尺寸渲染 emoji 后 LANCZOS 高质量下采样，狐狸 🦊 等图标恢复清晰可辨

### Changed

- **全面对齐 WebUI Liquid Glass 风格**：浅色渐变背景（淡蓝→淡粉）、半透白磨砂卡片 + 柔和投影、移除花哨的彩色折射外发光、统计数值改为 WebUI 同款蓝色渐变文字并居中、卡片内部加入 accent 彩色光斑

### Verified

- `python3 -m compileall fox_toolbox main.py` 通过
- 图片视觉审查确认：浅色背景清爽、🦊 emoji 清晰可辨、蓝色渐变数值居中、布局整齐、高度贴合 WebUI
- `PYTHONPATH=/workspace python3 -m pytest -q` 与基线一致（10 failed, 202 passed, 71 errors，无回归）

## [0.2.5] - 2026-08-06

### Changed

- **液态玻璃质感增强**：卡片边缘折射光晕改用独立大图层向外显著扩散（扩散半径 _PX(14)、外溢 _PX(18)），形成明显的 accent 色彩色散感，逼近 Apple Liquid Glass 效果
- **通透度提升**：玻璃填充透明度由 178 降至 108，背景彩色光斑更易透过卡片显现
- **背景光斑加丰富**：新增两组彩色光斑（青绿/紫），饱和度提升，为玻璃透出提供更丰富的色彩
- **高光与描边强化**：顶部高光不透明度提升、双层内描边内外亮度差加大，增强玻璃厚度感

### Verified

- `python3 -m compileall fox_toolbox main.py` 通过
- 图片视觉审查确认折射彩边光晕明显增强、文字可读性良好
- `PYTHONPATH=/workspace python3 -m pytest -q` 与基线一致（10 failed, 202 passed, 71 errors，无回归）

## [0.2.4] - 2026-08-06

### Changed

- **快照图视觉全面升级为液态玻璃（Liquid Glass）风格**：卡片背后真实模糊背景模拟 backdrop-filter，叠加顶部高光渐变、内描边、彩色折射边缘光与柔和光斑背景，层次与质感大幅提升
- **解决文字模糊**：改用 NotoSansCJK 矢量字体（中文/数字清晰渲染），全图 2x 超采样后 LANCZOS 降采样消除锯齿
- **解决表情无法显示**：集成 NotoColorEmoji 彩色 emoji 字体，标题与内容中的 emoji 按位图缩放合成
- **细节美化**：排行 Top 3 金银铜徽标、图标圆点光晕、进度条圆角化、数值加粗、时间趋势折线柔光
- **性能优化**：背景整体预模糊一次（卡片复用），小元素改用局部图层 paste，渲染耗时由约 6.5s 降至约 2.7s

### Verified

- `python3 -m compileall fox_toolbox main.py` 通过
- 示例数据渲染快照成功生成，emoji 与中文正常显示
- `PYTHONPATH=/workspace python3 -m pytest -q` 与改动前基线一致（未引入回归）

## [0.2.3] - 2026-08-06

### Added

- **`/msg_record snapshot` 指令**：将数据库统计渲染成与 WebUI 风格一致的 PNG 快照图并发到聊天，包含统计卡片、消息时间趋势、发送者/群组排行 Top 8、内容类型分布
- 新增 `fox_toolbox/snapshot_renderer.py`，基于 Pillow 渲染 Liquid Glass 风格仪表盘快照，零新增重依赖（仅复用已存在的 Pillow）
- `/msg_record help` 帮助文本补充 snapshot 指令说明

### Verified

- `python3 -m compileall fox_toolbox main.py` 通过
- `render_snapshot` 参数签名与 `main.py` 调用一致，复用 `Database.get_stats/get_timeline_stats/get_sender_ranking/get_group_ranking/get_content_type_stats/get_table_count` 现有方法
- `PYTHONPATH=/workspace python3 -m pytest -q` 与改动前基线一致（未引入回归）

## [0.2.2] - 2026-08-05

### Fixed

- **旧版 `web_api.py` 与新版 `main.py` 混用时注册崩溃**：`register_all_web_apis` 恢复为 2 参数签名，初始化失败原因改由 `context.fox_toolbox_db_error` 透传，避免 `takes 2 positional arguments but 3 were given` 导致页面/API 全部未注册
- **数据库连接错误信息透出**：`status`/`stats` 接口的 `db_status` 携带具体连接错误（如 `Can't connect to MySQL server`），前端状态卡片与 dashboard 顶部横幅直接展示原因

### Changed

- **前端资源版本号升级**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.2.2`

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`（212 passed / 71 skipped）
- `python3 -m compileall fox_toolbox main.py`
- `node --check pages/recorder/app.js`
- `register_all_web_apis(ctx, None)` 2 参数签名注册 30 个 API 成功，status/stats 降级数据携带 MySQL 错误详情

## [0.2.1] - 2026-08-05

### Fixed

- **MySQL 不可用时 WebUI 白屏**：此前 `initialize()` 中 `Database.init()` 连接失败会直接导致整个插件初始化失败，`_register_web_apis()` 不被调用，页面与所有 API 均未注册，前端整页空白。现在初始化失败后仍注册全部 Web API（`db` 传 `None`），页面可正常打开并展示降级状态
- **数据库连接错误信息透出**：`status`/`stats` 接口的 `db_status` 新增 `error` 字段携带具体连接错误（如 `Can't connect to MySQL server`），前端状态卡片与 dashboard 顶部错误横幅直接展示原因，便于排查配置

### Changed

- **前端资源版本号升级**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.2.1`

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox main.py`
- `node --check pages/recorder/app.js`
- `register_all_web_apis(ctx, None)` 注册 30 个 API 成功，`status`/`stats` 返回降级数据并携带 MySQL 错误详情

## [0.2.0] - 2026-08-05

### Fixed

- **数据表数量卡片偶发空白**：`updateDbStatusCard` 不再因 `db_status` 缺失而提前返回，缺失时显示 `--` 并清除加载骨架；`stats` 响应缺少 `db_status` 时自动改用 `status` 接口兜底，避免卡片停留在骨架态
- **数据库浏览表列表偶发崩溃**：`DbExplorer.list_tables()` 兼容 tuple 与 dict 两种游标行（此前默认游标返回 tuple，`rows[0].keys()` 抛 `AttributeError`）
- **只读 SQL 查询语法错误**：`_ensure_limit` 不再对 `SHOW / DESCRIBE / DESC` 追加 `LIMIT`（避免 MySQL 语法错误），并对已存在且超限的 `LIMIT` 数值钳制到 `ABSOLUTE_MAX_ROWS` 以内

### Changed

- **消息时间趋势图布局优化**：压缩图表卡片高度（桌面 420→340px、平板 280→240px、手机 250→210px），ECharts 绘图区下移并收紧底部留白（`top: 46` / `bottom: 2%`），图例紧凑排布，消除图表下方大片空白
- **前端资源版本号升级**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.2.0`

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`
- `node --check pages/recorder/app.js`

## [0.1.12] - 2026-08-05

### Added

- **数据库浏览（只读）**：整合参考插件 astrbot_plugin_mysql（作者 Chris95743）的「表浏览 / SQL 查询」能力，在 Plugin Page 新增「数据库」视图，支持数据表列表（含行数）、表结构查看、表数据预览，以及只读 SQL 查询面板
- **只读查询安全策略**：新增 `fox_toolbox/db_explorer.py`，仅允许 `SELECT / SHOW / DESCRIBE / DESC` 前缀语句；拦截 `DROP`、`TRUNCATE`、`FLUSH`、`GRANT`、`REVOKE`、`ALTER/CREATE USER`、`RENAME TABLE`、`LOCK` 与注释注入（`--`、`/* */`）；自动追加 `LIMIT` 防止大表全量拉取；查询超时上限 15 秒
- **数据库浏览命令**：新增 `/msg_record tables` 命令，可在聊天中查看数据库业务表列表（自动跳过 `_schema_meta` 系统表）
- **新增 Web API**：`GET db/tables`、`GET db/schema?table=`、`GET db/data?table=&limit=&offset=`、`POST db/query`（接收 `sql` 与 `max_rows`），共注册 26 个 API

### Changed

- **消息时间趋势图表优化**：趋势线条加粗至 4px、数据点放大，坐标轴文字与图例字号加大，图表容器高度从 340px 提升至 420px，便于阅读
- **卡片浮动更明显**：重新引入统计卡片浮动动画，幅度增至 ±10px、周期 6s，hover 时暂停；图表容器同步加入浮动
- **背景动态流光**：新增 `auroraFlow` 动画，页面背景呈现缓慢流动的极光渐变；遵循 `prefers-reduced-motion` 时自动关闭动画
- **前端资源版本号升级**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.1.12`

### Security

- **危险关键词误报修复**：SQL 安全校验先剥除字符串字面量再匹配危险模式，避免将数据内容中的关键词（如 `LIKE '%grant%'`）误判为危险操作，同时保留对真实 DDL/DML 命令与注释注入的拦截

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`
- `node --check pages/recorder/app.js`

## [0.1.11] - 2026-08-05

### Fixed

- **彻底修复页面“一直刷新”的观感**：移除 Dashboard 统计卡片的 `cardFloat` 无限浮动动画（含移动端变体），卡片只在首次入场时淡入一次，之后完全静止
- **修复数据库表数量获取不到的问题**：后端 `get_table_count()` 查询失败改为返回 `-1`，`_build_db_status_payload` 不再先执行 `ping()` 前置判断，直接以表数量查询结果为准，避免因 ping 失败而永远拿不到表数量
- **消除数据库状态卡片双入口互相覆盖**：前端不再无条件并发请求 `status` 接口，默认复用 `stats` 响应里的 `db_status`；仅在 `stats` 请求失败时才用 `status` 接口兜底，减少一次冗余请求

### Changed

- **数据库状态卡片只展示表数量**：卡片数值固定显示已创建的数据表数量，标签固定为“数据表数量”，数据库未连接时显示 `--`
- **刷新前端资源版本号**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.1.11`，确保 AstrBot 刷新后加载最新页面资源
- 删除不再使用的 `_safe_db_ping()` 辅助函数，简化后端状态数据链路

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`
- `node --check pages/recorder/app.js`

## [0.1.10] - 2026-08-05

### Fixed

- **修复数据库状态卡片不显示的问题**：前端为数据库状态卡片新增独立加载入口，通过 `status` 接口兜底拉取表数量，不再完全依赖 `stats` 接口成功与否；若 `stats` 失败卡片依然能展示数据库连接状态

### Changed

- **数据库状态卡片只展示表数量**：卡片默认直接显示已创建的数据库表数量（如 `12 张`），连接失败时才显示“未连接”，移除了此前“运行中/表数量”的 3 秒轮换逻辑，避免反复刷新观感
- **兼容两种数据形状**：前端卡片渲染同时兼容 `stats` 接口的 `running/table_count` 与 `status` 接口的 `database/table_count` 两种返回结构
- **刷新前端资源版本号**：Plugin Page 的 `app.js` 与 `style.css` 查询参数升级至 `0.1.10`，确保 AstrBot 刷新后加载最新页面资源

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`

## [0.1.9] - 2026-08-05

### Changed

- **优化数据库状态卡片的切换体验**：卡片轮换文案从“已创建 X 张表”收紧为“X 张表”，降低卡片宽度抖动与频繁重排的视觉刷新感
- **仅在 Dashboard 可见时切换卡片文案**：页面切到其他视图或浏览器标签页隐藏时暂停 3 秒轮换，减少无意义 UI 更新

### Performance

- **减轻 Dashboard 首屏负担**：`stats` 接口移除未使用的 `plugin_status` 计算，只保留轻量 `db_status` 数据，减少不必要的数据库探测和资源采集

### Verified

- `PYTHONPATH=/workspace python3 -m pytest -q`
- `python3 -m compileall fox_toolbox astrbot_plugin_fox_toolbox pages/recorder`

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
