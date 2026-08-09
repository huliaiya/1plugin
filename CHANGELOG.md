# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.9] - 2026-08-09

### Added
- **快照与 WebUI 展示 MySQL 版本与连接状态**：快照图新增「MySQL 存储」卡片，Web 仪表盘新增 MySQL 存储状态卡，实时展示连接状态（已连接/已降级/未连接）、MySQL 服务器版本、存储后端与待同步消息数；连接判定基于真实连接池就绪状态，兼容未启用兜底时的降级场景
- **插件指令全面中文化**：命令组改为 `/狐狸记录`（`/huli_record` 保留为别名），子命令（统计/清理/查询/搜索/帮助/今日/昨日/历史/表列表/快照）与爱发电指令均改为中文主命令，旧英文指令仍可作为别名使用；帮助菜单同步更新并增加别名提示
- **MySQL 与 Redis 运行中断连自动重连**：MySQL 与 Redis 断连后由后台循环周期检测并自动重连（Redis 此前连接失败即永久禁用，无任何运行中恢复机制）；连续重试次数由新配置项 `connection_max_retries` 控制（默认 5，最小 1），达到上限后停止自动重连，分别进入 SQLite 降级 / 无缓存模式，并记录日志提示；运行中 Redis 断连期间自动以无缓存模式运行，恢复后自动切回缓存

### Fixed
- **状态连接判定误报**：此前用 `using_fallback` 反推连接状态，在"MySQL 故障但未启用兜底"场景会误报「已连接」；现改用连接池真实就绪状态判定，三态（已连接/已降级/未连接）准确反映 MySQL 实际可用性
- **MySQL 恢复循环无限重试**：此前 `_recovery_loop` 无限周期重连，MySQL 长时间不可用时持续占用后台资源；现达到 `connection_max_retries` 上限后停止自动重连，保持降级模式
- 版本号 bump 至 2.7.9

## [2.7.8] - 2026-08-09

### Added
- **爱发电订单存储 MySQL 自动恢复**：MySQL 故障降级到 SQLite 后，`OrderDB` 现在会周期检测主库恢复（每 30 秒，可通过 `afdian_recovery_check_interval` 配置），恢复后自动重新绑定连接池并把降级期间积累的订单幂等回写 MySQL（`INSERT IGNORE` 去重），消除此前"降级永久化、SQLite 与 MySQL 分脑"的问题
- **爱发电订单 SQLite 写保护**：SQLite 兜底连接统一启用 WAL + `busy_timeout`（30 秒）+ `synchronous=NORMAL`，并发写入（Webhook 与轮询并存）时的锁定异常被捕获记录日志而非上抛导致订单处理失败

### Fixed
- **帮助菜单补全爱发电指令**：`/狐狸菜单` 与 `/hulihelp` 此前未列出爱发电模块指令；现新增「⚡ 爱发电」分类，完整展示 `/发电 [金额]`（普通用户）及 5 个 `[管理员]` 指令（爱发电测试、同步历史订单、查询订单、查询发电、开启发电通知），与真实注册指令一一对应
- 版本号 bump 至 2.7.8

## [2.7.7] - 2026-08-09

### Added
- **本地 SQLite 兜底存储（MySQL 自动降级）**：MySQL 不可用/故障/连接中断时自动降级到本地 SQLite 文件继续记录消息与爱发电订单，MySQL 恢复后自动切回并分批幂等补写降级期间消息（`INSERT IGNORE` + `content_hash` 唯一索引去重，默认每 30 秒检测一次、单批 500 条）。降级期间查询、统计、排行、时间线、导出、快照全部保持可用，Web 面板状态卡片展示当前存储后端与未同步消息数；新增 `storage_fallback_enabled`（默认开启，零配置兜底）、`recovery_check_interval`、`backfill_batch_size`、`sqlite_max_retention_days` 四个配置项（SQLite 兜底库自动清理已同步旧消息控制文件增长）
- 版本号 bump 至 2.7.7

### Fixed
- **SQLite 兜底库清理保留未同步数据**：降级期间的自动清理（保留天数/条数）此前会删除 SQLite 中尚未补写进 MySQL 的消息，导致 MySQL 恢复补写时数据永久丢失；现仅清理已同步（`synced=1`）数据，未同步消息完整保留至补写成功
- **MySQL 恢复检测真正重建连接池**：初始化阶段 MySQL 故障降级后，恢复检测此前仅对已存在的连接池做 `SELECT 1` 探测，无法重建已失效的连接池，导致 MySQL 恢复后永不切回；现每次恢复检测重新建立连接池并初始化表结构，成功后才切回主存储并补写
- **`storage_fallback_enabled=false` 配置项容错**：`main.py` 读取新增数值配置项时改用 `_safe_int` 容错，用户填非法值时回退默认值，避免插件初始化崩溃
- 快照水印兜底版本号同步更新至 2.7.7

## [2.7.6] - 2026-08-09

### Security
- **导入 zip 解压防 zip 炸弹**：`_import_zip_package` 解压媒体文件此前无任何大小/数量限制，恶意或异常导入包可把磁盘撑爆、`data.json` 全量读入内存无上限。新增三个上限：`data.json` 最大 512MB、媒体解压总量最大 8GB、媒体条目数最大 10000，超限直接拒绝导入

### Fixed
- **aiohttp Content-Length 容错**：`media_downloader` 对服务器返回的非数字 `Content-Length` 头直接 `int()` 抛 `ValueError`，该异常不在现有 `except` 范围内导致该次下载静默失败，现已容错为 0 继续按实际内容大小限制校验
- **db_explorer 重复 LIMIT 语法错误**：`_ensure_limit` 仅识别 `LIMIT <数字>`，对参数化 `LIMIT ?`/`LIMIT %s`/`LIMIT ALL` 等已有 LIMIT 检测不到而追加第二个 LIMIT，导致 SQL 语法错误；现对任意形式的已有 LIMIT 均不再追加，仅钳制其中的数字 count
- **快照发送 unlink 竞态**：`/huli_record snapshot` 生成图片后在命令生成器 `finally` 中立即删除文件，而 AstrBot 框架在生成器结束后才实际发送图片，发送失败率高；改为登记延迟删除任务（30 秒后清理，纳入 `_pending_tasks` 生命周期管理）
- **`_pending_tasks` 无上限**：消息监听为每条消息新建后台任务并无限累积，消息洪峰时内存持续增长；新增 `MAX_PENDING_TASKS=200` 上限，超过时先等待任一任务完成再登记，形成自然背压
- **快照水印版本过期**：水印硬编码 `v2.4.3` 与当前版本脱节，改为从 `metadata.yaml` 动态读取版本号
- 版本号 bump 至 2.7.6

## [2.7.5] - 2026-08-08

### Changed
- **Redis 统计缓存实时更新**：保存消息成功后立即将新消息原子增量合并进 Redis 统计缓存（`total_count`、平台分布、group/private/channel 桶、时间区间），TTL 滑动续期，`get_stats` 命中缓存即可返回最新数据，无需等待 TTL 过期回源。Redis 不可用或缓存缺失（TTL 过期、从未回源）时自动回源数据库重建兜底，不阻塞消息保存主流程
- 版本号 bump 至 2.7.5

## [2.7.4] - 2026-08-08

### Security
- **修复媒体下载任意文件读取漏洞**：`media_downloader` 通过 AstrBot `MediaResolver` 读取媒体时，`file:///` 与绝对本地路径此前不经过校验，任意群成员发送 `file:///etc/passwd` 类图片消息即可触发宿主机任意文件读取并落盘。新增 `_safe_local_read_path` 白名单校验：仅放行 AstrBot 数据目录（含 OneBot 客户端缓存）之内的路径；OneBot 兜底 `download_file`/`get_image` 返回的本地路径同步纳入校验

### Fixed
- **非法日期导致查询接口 500**：`parse_date` 对 `2024-13-40`、`2024-02-30` 等格式合法但月/日越界的输入抛未捕获 `ValueError`，穿透 `parse_time_range` 使 Web 查询与 `/huli_record history` 功能失效。现在返回 None 并正常回退最近 24 小时
- **`limit` 参数为负数时 SQL 报错**：`api_stats_senders`/`api_stats_groups`/`api_stats_senders` 排行等接口对 `?limit=-1` 生成 `LIMIT -1`，MySQL 报 `Incorrect arguments to LIMIT`。`_safe_int` 增加 `min_val`/`max_val` 钳制，负数归零、超大值截断到上限
- **导入过期任务残留文件**：`cleanup_expired_tasks` 清理过期/崩溃的导入任务时未删除上传文件（对比导出任务分支会删除），中断的导入文件永久残留磁盘。现已与导出任务一致删除 `file_path`
- **`exports/` 目录残留**：`_cleanup_temp_dir` 启动清扫只清理 `temp/`，崩溃重启后旧导出文件残留。现已同时清理 `exports/`
- **`+1d` 相对时间无法解析**：`parse_relative_time` 正则仅接受 `-`，与文档声称支持 `+1d` 不符，已支持 `+` 前缀；极端天数（如 `999999999999d`）触发 `OverflowError` 已捕获
- **`_to_int` 不兼容 Decimal**：`snapshot_renderer._to_int` 声称兼容 MySQL 驱动的 Decimal，但 `Decimal` 实例会落入默认值返回 0，已改用 `numbers.Number` 判定
- 版本号 bump 至 2.7.4

## [2.7.3] - 2026-08-08

### Fixed
- **修复付款成功「感谢支持」不发送到用户会话**：`/发电` 生成的付款链接备注（32 位 hex）可能与爱发电回调备注的字符串大小写不一致，导致 `on_afdian_new_order` 无法匹配待确认订单。新增 `_match_pending_sender` 按备注精确/忽略大小写匹配
- **兜底私聊不再对非数字 ID 报错**：付款人 ID 非数字时跳过 `int()` 转换，走通用告警路径

### Changed
- **美化订单信息展示**：`parse_order` 输出改为分栏布局（标题分隔线 + 字段 + SKU 列表），金额统一 `¥xx.xx` 格式化，订单状态显示为「待支付/已支付」可读文案而非裸数字
- 版本号 bump 至 2.7.3

## [2.7.2] - 2026-08-08

### Removed
- **删除无引用模块 `sys_util.py` 及其测试**：进程资源采集（CPU/内存/运行时长）在 Dashboard 移除「资源占用」卡片后已无任何生产调用方，仅被测试引用
- **删除 `order_db.py` 死代码**：`using_mysql` 属性与 `get_order_by_id`/`get_orders_by_user`/`get_orders_by_status` 查询方法（无调用方）
- **删除 `web_api.py` 死代码**：未使用的 `IMPORT_RECORD_TIMEOUT` 常量、`_safe_float_metric` 辅助函数与 `List` import
- **删除 `serializer.py` 无生产引用的常量组**（`_INTERACTIVE_COMPONENT_TYPES`/`_RICH_MEDIA_COMPONENT_TYPES`/`ALL_KNOWN_COMPONENT_TYPES`，保留有测试保护的 `MEDIA_COMPONENT_TYPES` 与 `COMPONENT_TYPE_MEDIA_MAP`）
- **清理测试未使用 import**：`conftest.py`/`test_api.py`/`test_database.py`/`test_media_downloader.py`/`test_models.py`/`test_platform_adapter.py`/`test_redis_cache.py`/`test_serializer.py`/`test_time_utils.py` 中未使用的 import 与局部变量

### Changed
- **`main.py` 扩展名映射去重**：移除重复的 `"ts"` key（原被后置 `FileVideo` 覆盖），行为不变，消除字典重复键告警
- **`snapshot_renderer.py` 清理未使用变量**：`_truncate_middle` 的 `ew`、玻璃卡片绘制的 `pad`/`glass_draw`、状态卡片未接收的返回值
- **修复 `.gitignore` 粘连行**：`CLAUDE.md` 与 `test_glassmorphism_snapshot.png` 两个条目间缺失换行符
- 版本号 bump 至 2.7.2

## [2.7.1] - 2026-08-08

### Security
- **`/orders` 端点强制令牌**：未配置 `afdian_webhook_token` 时不再放行查询（原逻辑无令牌即 403，但未配置时返回所有订单，含收货手机号/地址等隐私数据）；现未配置或令牌不匹配一律 403
- **Webhook 启动未配令牌警告**：服务启动且未配置校验令牌时打印醒目警告，提示需在回调 URL 携带 `?token=xxx`
- **支付链接 remark URL 编码**：`generate_payment_url` 对 remark 做 `urllib.parse.quote`，防止特殊字符污染 query 参数

### Fixed
- **`/发电` 金额上下限校验**：金额为 0/负数/超过 100000 时拒绝并提示，校验前置到待确认订单登记之前（非数字文本仍按既有设计回退默认金额）

### Changed
- **Webhook 模式内存防泄漏**：`use_polling=False` 时轮询循环永不启动，`afdian_pending_orders`/限流状态改为在每次 `/发电` 时惰性清理，防止字典无限增长
- **统计接口标注上限**：`get_content_type_stats`/`get_platform_detail_stats`/`get_timeline_stats`/`get_group_ranking` 全表拉取标注 ponytail 注释（百万级消息时内存峰值明显，需改 SQL 聚合）
- **媒体下载 file:// 风险标注**：`_fetch_via_media_resolver` 的任意本地文件读取风险以注释说明权衡（兼容 OneBot 客户端缓存下载），未改变行为
- 版本号 bump 至 2.7.1

## [2.7.0] - 2026-08-08

### Changed
- **合并测试指令**：删除 `cmd_afdian_simulate`，`/爱发电测试` 成为唯一测试指令（别名含 `发电测试/发电模拟/模拟发电/模拟发电订单/爱发电模拟`），统一走完整订单链路
- **模拟指令推送增强**：`afdian_simulate_new_order` 完整推送所有已配置通知会话，并在当前聊天会话不在通知会话时补推，便于验证推送链路
- **history 命令复用解析结果**：`/history` 使用已解析的 `start_time/end_time` 查询，避免时间范围二次解析

### Fixed
- **修复 zip 导入记录数翻倍**：zip 分支预置 `total_records` 后又随循环累加，导致总数翻倍；移除预置统一由循环计数
- **修复 `_migrate_v3` 幂等性**：全新数据库建表已含 `content_types`，迁移 v3 重复 ADD COLUMN 会崩溃；现用 INFORMATION_SCHEMA 检查列/索引存在性后跳过
- **修复 MySQL 降级后不回退 SQLite**：`_query_mysql` 新增 `sqlite_sql` 参数，MySQL 故障降级后走 SQLite 查询
- **修复 `on_afdian_new_order` 兜底私聊内容错误**：原发订单文本 `message`，改为发 `default_reply`
- **修复 `_parse_query_filter` limit 无下限**：limit 为 0 或负值时钳制到 [1, 200]

### Removed
- **删除无用代码**：`order_db.py` 中无调用方的 `save_order/_save_mysql/_save_sqlite`、`afdian_api.py` 的 `ping()`、`media_downloader.py` 的 `cleanup_orphaned_media`、`star.py` 只写不读的 `afdian_started`、`_MockAfdianClient.query_sponsor`、`web_api.py` 未使用的 `sys_util` import、`snapshot_renderer.py` return 后的不可达代码
- **删除 19 个根目录临时调试脚本**（`debug_*.py`、`final_*.py`、`quick_test.py`、`second_check.py`、`test_*.py` 等）及 3 个过期文档（`PROJECT_SUMMARY.md`、`README_TEST_IMAGES.md`、`RENDERER_FIX_SUMMARY.md`）

### Other
- **Web API 注册数动态统计**：不再硬编码 `已注册 26 个 Web API`，改为运行时计数（当前 31 个）
- 版本号 bump 至 2.7.0

## [2.6.9] - 2026-08-08

### Fixed
- **修复限流误计数问题**：原实现先计数后生成支付链接，`generate_payment_url` 失败（如 API 异常）也会累加次数甚至误触发拉黑；现拆分为 `_afdian_rate_limit_exceeded`（判断是否达上限）与 `_afdian_record_order`（链接成功生成后才计数），失败不计数、不误拉黑
- **修复拉黑后残留待确认订单**：触发拉黑时同时清理该用户在 `afdian_pending_orders` 中的未支付记录，避免轮询持续为其工作

### Changed
- **限流内存管理**：新增 `_afdian_cleanup_rate_limit_state`，随轮询定期清理已到期拉黑与窗口外计数，防止 `afdian_order_history` / `afdian_blacklist` 无限增长
- 新增 3 项限流优化测试（判断不计数、成功后才计数、定期清理），全量 256 passed
- 版本号 bump 至 2.6.9

## [2.6.8] - 2026-08-08

### Added
- **新增 `/发电` 防刷限流**：同一用户在 `afdian_rate_limit_window`（默认 60 秒）内发起订单次数达到 `afdian_rate_limit_max_orders`（默认 3 次）时，拒绝本次 `/发电` 并拉黑 `afdian_rate_limit_ban_seconds`（默认 1 小时）；拉黑期间该用户 `/发电` 直接返回临时限制提示。可通过 `afdian_rate_limit_enabled` 开关关闭
- 新增 6 项限流单元测试（允许前两次、第三次拦截、拉黑生效、自动解除、开关关闭）

### Changed
- 版本号 bump 至 2.6.8

## [2.6.7] - 2026-08-08

### Fixed
- **修复 `/发电模拟` 命令触发受限问题**：原命令走 `_afdian_check`（要求真实 API 凭据已配置），但模拟命令使用 mock 客户端、不请求真实接口，未配置 user_id/token 时会被直接拦截；现改为仅要求功能开关开启，未配置凭据也可用于验证推送链路
- **修复模拟订单号碰撞导致重复模拟被去重跳过**：原 `out_trade_no` 使用秒级时间戳 `TEST{now}`，同一秒内重复执行会被 `save_order_if_new` 按交易号去重而跳过推送；现追加 uuid 短后缀保证每次订单号唯一

### Changed
- 版本号 bump 至 2.6.7

## [2.6.6] - 2026-08-08

### Added
- **新增 `/发电模拟` 测试指令**（别名 `/模拟发电`、`/模拟发电订单`、`/爱发电模拟`）：模拟一笔新订单并走完整检测链路——构造模拟订单 → 注入 mock API 客户端走 `afdian_poll_once`（拉单 → `save_order_if_new` 按交易号去重入库 → `on_afdian_new_order` 推送到所有已设置的通知会话/推送群，并按备注匹配向付款用户回复）；不发起任何真实网络请求，用于验证「用户发电 → 自动检测 → 订单成功 → 推送到推送群」全链路

### Changed
- 版本号 bump 至 2.6.6

## [2.6.5] - 2026-08-08

### Changed
- **轮询改为按需限时模式**：原先只要开启 `afdian_use_polling` 就常驻每 `afdian_poll_interval` 秒请求一次接口，导致后台日志刷屏；现改为用户 `/发电` 生成待确认订单时才启动轮询，每 `afdian_poll_interval` 秒（默认 5 秒）拉取一次，最多持续 `afdian_poll_timeout` 秒（默认 5 分钟），待确认订单处理完或窗口到期即自动停止，无人发电时不再请求接口
- **日志降噪**：`query_order` / `query_sponsor` 不再每次打印完整接口响应，改为有数据时打印返回条数、无数据时降为 debug 级别

### Fixed
- **订单只入库一次不覆盖旧订单**：轮询与 Webhook 均使用按 `out_trade_no` 去重的原子写入（INSERT IGNORE），旧订单不会被重复覆盖

### Changed
- 版本号 bump 至 2.6.5

## [2.6.4] - 2026-08-08

### Fixed
- **修复爱发电查询发电/查询赞助为空**：`query_sponsor` 原先默认把创作者自己的 `user_id` 当作赞助者筛选条件传给接口，导致按"创作者作为赞助者"过滤恒为空；现默认不传 `user_id` 查询全部赞助者，仅当显式指定赞助者用户 ID 时才按该 ID 筛选
- **查询发电无赞助记录时回退展示本地订单**：当账号不存在赞助关系但已同步历史订单时，查询发电回退展示本地已同步订单，保证查询结果有内容

### Changed
- 版本号 bump 至 2.6.4

## [2.6.3] - 2026-08-08

### Added
- **WebUI Redis 状态卡片增加持续浮动动画**：与统计卡片一致的 `cardFloat` 悬浮效果，风格统一

### Fixed
- **修复快照 Redis 卡片文字溢出**：运行中状态渲染 5 行信息超出固定卡片高度，现按信息行数动态计算卡片高度，各状态文字均在卡片边界内
- **修复快照 Redis 卡片标题与连接地址重合**：状态徽标原先随内容行数垂直居中，运行中 5 行时压住信息行；现徽标与标题同行右对齐，信息行整体下移至标题区下方
- **修复爱发电查询图片空白/乱码**：`t2i_template.html` 的 markdown 源文本原先使用 `{{ text | safe }}` 不做 HTML 转义，当订单备注、计划标题等含 `<`、`&`、`</textarea>` 字符时会破坏页面结构导致渲染空白或乱码；现改为强制转义，插件名与版本号同步转义

### Changed
- 版本号 bump 至 2.6.3

## [2.6.2] - 2026-08-08

### Added
- **WebUI 仪表盘新增 Redis 缓存状态大卡片**：显示运行状态（未启用 / 运行中 / 已降级）、连接地址、库编号、缓存 TTL、统计缓存与最近消息缓存条目数
- **快照新增 Redis 缓存状态卡**：`/huli_record snapshot` 快照在统计卡片下方展示 Redis 状态摘要
- `RedisCache.status()`：新增状态摘要方法，供 WebUI 与快照读取缓存健康信息

### Changed
- 版本号 bump 至 2.6.2

## [2.6.1] - 2026-08-08

### Added
- **新增 `/同步历史订单` 命令**：通过爱发电 API 主动分页拉取全部历史订单入库（按交易号去重），随时可手动补拉，不依赖 Webhook
- README 致谢新增编程语言生态（Python / JavaScript / CSS / HTML / Shell）与 GitHub 官方条目

### Fixed
- **修复爱发电 MySQL 连接池关闭后持续告警**：`OrderDB` 检测到池已关闭/acquire 失败时永久降级 SQLite（解除池引用），不再每轮轮询重复尝试 MySQL 并刷屏 `Cannot acquire connection after closing pool`；`terminate` 先停爱发电轮询/同步/Webhook 再关闭连接池

### Changed
- 版本号 bump 至 2.6.1
- README 新增 `/同步历史订单` 命令说明与历史订单同步说明

## [2.6.0] - 2026-08-07

### Added
- **新增 Redis 缓存（可选）**：新增 `fox_toolbox/redis_cache.py` 封装 `redis.asyncio`，为 WebUI 高频查询缓存消息统计（`get_stats`，按 `redis_cache_ttl` TTL 刷新）与最近消息列表
- 消息落库后自动推送最近消息缓存（单条与批量保存均覆盖，保留最近 200 条），统计接口首次查询后写缓存、TTL 内直接命中
- 新增配置项：`redis_enabled` / `redis_host` / `redis_port` / `redis_password` / `redis_db` / `redis_cache_ttl`（已同步 `_conf_schema.json` 与 README 配置说明）
- 依赖缺失、连接失败或运行中异常均自动降级为无缓存模式，绝不影响消息记录等主功能

### Fixed
- **修复媒体下载路径穿越写入**（`media_downloader.py`）：下载文件落盘前校验路径归属媒体目录，拒绝 `../` 或绝对路径等越界文件名
- **修复 SSRF 重定向绕过**（`media_downloader.py`）：下载请求改为逐跳校验重定向目标，封禁内网/链路本地地址，最多跟随 5 跳
- **修复导出任意文件读取**（`web_api.py`）：打包媒体附件前校验目标路径归属媒体目录，拒绝越界文件被导出
- **修复导入内存耗尽**（`web_api.py`）：无 ijson 回退到 `json.load` 时限制单条记录 64MB 上限，异常记录跳过并记录
- **修复统计接口整表扫描**（`database.py` `get_stats`）：改为 MySQL 端 `COUNT(*)` + `GROUP BY` 聚合，不再整表拉入 Python 内存
- **修复全文检索布尔模式 1064 错误**（`database.py`）：关键词含 `+-<>()~*"@` 保留字符时自动降级 LIKE 匹配
- **修复导出回填大文件 OOM**：占位符回填改为临时文件流式重组，避免整文件读入内存
- **修复 Redis 缓存记录 id 恒为 None**：落库后回填 `record.id`（`lastrowid`），保证缓存项可追溯
- **修复上传/分片同步 IO 阻塞事件循环**：导入写入与分片落盘改为 `asyncio.to_thread` 异步化
- **修复分片组装失败残留**：`_assemble_chunks` 异常时清理临时目录与会话，`api_import_complete` 防止 `NameError`
- **修复 db_explorer LIMIT 钳制绕过**：两参形式 `LIMIT offset, count` 的 offset 与 count 均钳制；新增危险函数拦截（`INTO OUTFILE` / `LOAD_FILE` / `SLEEP` / `BENCHMARK` / `LOAD DATA`）
- **修复初始化失败泄漏连接池**：`main.py` 初始化异常时正确关闭数据库连接池
- **爱发电 Webhook 新增可选 token 校验**：配置 `afdian_webhook_token` 后仅接受 URL query 携带正确 token 的回调，未配置保持原行为向后兼容
- **修复清理任务大事务与内存无界**：`cleanup_by_age` / `cleanup_by_limit` 改为 keyset 分页收集 + 分批 DELETE
- **修复 Telegram 频道消息并发写库**：保存操作统一受信号量约束，避免并发线程竞争
- **兼容新旧 Quart**：附件下载按版本自动选用 `download_name` / `attachment_filename` 参数

### Changed
- 版本号 bump 至 2.6.0
- README 功能特色、配置说明与致谢新增 Redis（官方 / redis-py）

## [2.5.1] - 2026-08-07

### Fixed
- **修复爱发电 Webhook 与轮询并存时的重复通知竞态**：`OrderDB.save_order_if_new` 使用 `INSERT IGNORE` / `INSERT OR IGNORE` 原子判重（替代"先查再存"），Webhook `handle_order`、轮询、历史同步统一走该路径，杜绝 TOCTOU 竞态导致的同一订单重复通知
- **修复 MySQL 5.7 建表失败**：`afdian_orders` 的 `idx_remark` 对 `VARCHAR(512)` utf8mb4 建全列索引超过 MySQL 5.7 的 767 字节索引上限（512×4=2048），改为前缀索引 `remark(191)`
- **修复轮询积压漏单**：`afdian_poll_once` 由只拉第一页改为循环分页拉取，遇到已入库订单即停，避免突发大量订单时漏掉新订单
- **修复爱发电 Webhook 与轮询并存时的重复通知**：`handle_order` 在保存订单前先查库判重，同一订单仅由先到达的通道处理并触发一次回调，避免重复通知
- **修复轮询启动与历史全量同步的竞态**：`afdian_poll_loop` 启动时先等待历史同步任务完成，避免历史订单被误判为新订单触发通知
- **修复待确认发电订单长期残留**：新增待确认订单超时清理，超时未支付记录按 `afdian_poll_timeout` 自动回收
- **修复 `/发电` 金额展示崩溃风险**：金额可能以字符串传输，增加类型转换容错

### Changed
- **爱发电查询图片整体美化**：自定义 T2I 模板全面重写（渐变品牌横幅、卡片化内容区、标题/列表/表格/引用块/代码块专项样式）；`/查询订单` 与 `/查询发电`（`/查询赞助`）共用同一渲染模板，仅指令不同
- 自定义文转图渲染改用 Star 基类 `self.html_render`（官方推荐 API），移除对 `astrbot.core.html_renderer` 内部单例的直接依赖
- 图片水印兜底版本号默认值同步为 v2.5.1
- README 致谢新增爱发电官方（AFDian 开放平台）
- `parse_order` / `parse_sponsors` 输出升级为 markdown 结构（加粗字段、条目标题），图片渲染层次更清晰

## [2.5.0] - 2026-08-07

### Added
- **集成爱发电打赏对接功能**：复刻自 [astrbot_plugin_afdian](https://github.com/Zhalslar/astrbot_plugin_afdian)（作者 [Zhalslar](https://github.com/Zhalslar)），实现发电打赏、Webhook 订单实时推送、订单/赞助查询等能力
  - 新增指令：`/发电`（别名 `/赞助`）、`/爱发电测试`、`/查询订单`、`/查询发电`（别名 `/查询赞助`）、`/开启发电通知`（别名 `/发电通知`、`/爱发电通知`）
  - 新增配置：`afdian_enabled`、`afdian_webhook_host`、`afdian_webhook_port`、`afdian_api_base_url`、`afdian_api_user_id`、`afdian_api_token`、`afdian_default_price`、`afdian_default_reply`、`afdian_notice_sessions`
  - 订单数据以 SQLite 存储于插件数据目录 `afdian/orders.db`，Webhook 服务独立于消息记录功能启动，失败不影响主功能
  - 存储引擎与主插件统一：订单写入主库 MySQL 的 `afdian_orders` 表（与消息记录同一连接池），MySQL 不可用时自动回退 SQLite 兜底
  - 启动/重载时自动分页拉取爱发电平台全部历史订单入库（按交易号去重，只存新增），Webhook 上线前订单不丢失
  - `/查询订单`、`/查询发电` 结果图片顶部水印改为插件名 + 插件版本（自定义 T2I 模板，替代默认框架水印）
  - 无公网机器支持轮询模式：新增 `afdian_use_polling` / `afdian_poll_interval` / `afdian_poll_timeout` 配置，用户发电后提示限时完成支付，插件定时（默认每 5 秒）拉取订单检测新订单，备注匹配与自动回复逻辑与 Webhook 完全一致，无需公网回调

## [2.4.3] - 2026-08-07

### Fixed
- **修复 WebUI 平台分布图 QQ 显示为紫色**：平台分布饼图此前未指定颜色，使用了 ECharts 默认调色板（首个颜色为蓝紫 #5470c6）。现已显式指定天空蓝色板，与快照配色完全一致

### Changed
- **快照整体文字清晰度提升**：统计卡标签、时间趋势轴刻度与图例、内容类型中心标签、平台详情图例/峰值/柱顶数值/X 轴标签、水印等小字号文字统一增大，压缩后的聊天快照更易读

## [2.4.2] - 2026-08-07

### Changed
- **快照卡片标题上移**：时间趋势、平台分布、排行、平台详情、内容类型等所有卡片标题整体上移，视觉更靠近卡片顶部
- **WebUI 配色全面统一为天空蓝**：成功/警告/危险语义色从绿/橙/红切换为天空蓝系（蓝青 #4dd0e1 / 天蓝 #03a9f4 / 深天空蓝 #0288d1），文本色改为深蓝灰，按钮渐变、消息卡片高光、空态文字等残留杂色全部清除

### Fixed
- 快照时间趋势卡片 Y 轴刻度标签与标题不再重叠（标题上移后已重新校验图例间距）

## [2.4.1] - 2026-08-07

### Fixed
- **修复快照时间趋势卡片文字超出边框**：Y 轴刻度标签原来绘制在图表区左侧（x0 左边），当数据量级较大时（如 1,000 以上）会越过玻璃卡片边框。现在先计算 Y 轴标签最大宽度并为图表主体预留空间，刻度标签右对齐落在卡片边框内侧

### Changed
- 快照水印版本号同步升级到 `v2.4.1`

## [2.4.0] - 2026-08-07

### Changed
- **快照配色全面切换为浅蓝/天空蓝风格**：背景改为天空蓝渐变（#e0f2fe → #cfe8fa），统计卡片、图表、玻璃边框、文字均统一为天空蓝色系，视觉更清新通透
- **WebUI 配色统一为天空蓝**：页面背景去掉绿/黄/粉杂色，改为纯净浅蓝渐变；时间趋势图线条（总消息/群聊/私聊/频道）统一为天空蓝系渐变
- 快照水印文案更新为"天空蓝清新风格"

## [2.3.2] - 2026-08-07

### Fixed
- **修复快照中文全部显示为问号/方块的根因**：当系统缺失中文字体时，`ImageFont.load_default()` 无法渲染中文。现在渲染器会在常见字体目录中自动搜索 CJK / emoji 字体，无需人工安装
- **新增 `hulihelp` / `狐狸菜单` 顶层命令**：发送 `/hulihelp` 或 `/狐狸菜单` 即可查看全部可用指令
- **继续修复快照可读性**：提升时间趋势、排行、平台详情、图例和水印的小字号字体，聊天压缩后更易读
- **修复消息类型推断散落在主流程的问题**：适配器层直接对未知 `MessageType` 按上下文回退到群聊、私聊、频道，减少统计口径漂移
- **修复 Web 面板排行时间按钮重复**：移除两个语义重复的时间范围按钮，避免界面行为混乱

### Changed
- 快照水印版本号同步升级到 `v2.3.2`
- Plugin Page 前端资源版本号同步升级到 `2.3.2`
- 更新 `RENDERER_FIX_SUMMARY.md` 版本记录到 `v2.3.2`

## [2.3.1] - 2026-08-07

### Fixed
- **修复快照统计卡大量显示 0 的根因**：统计逻辑不再只依赖 `message_type` 原值，历史 `other` / `forum` / 脏数据会结合 `group_id` 与 `channel_id` 自动归类到群聊、私聊、频道，顶部统计卡、时间趋势、平台详情、群组排行恢复正常
- **修复平台消息详情空白图**：历史 `other` 消息现在会参与堆叠柱状图统计，柱顶总量标签改为显示在柱体上方，0 值平台保留基线提示
- **修复内容类型分布缺失**：`content_types` 兼容逗号串、JSON 数组、空值回退到纯文本推断，旧数据也能生成内容类型分布图
- **修复排行文本显示问题**：过滤控制字符并改进数值右对齐，减少昵称乱码和名称/数字错位
- **修复快照水印版本号过旧**：底部水印同步更新到 `v2.3.1`

### Changed
- 数据库统计方法改为更稳健的 Python 端聚合，兼容历史数据与混合格式字段
- 内容类型圆环图增加中心总消息数显示，图例名称增加裁剪处理
- Plugin Page 前端资源版本号同步升级到 `2.3.1`

## [2.3.0] - 2026-08-06

### Added
- **全新排行榜设计**：金银铜配色排名徽章，优化进度条显示效果
- **优化平台消息详细布局**：改进堆叠柱状图布局，图例显示更清晰
- **优化内容类型分布显示**：改进饼图布局，图例空间分配更合理

### Changed
- **排行榜视觉优化**：
  - 前三名使用金银铜配色徽章
  - 进度条颜色修复，确保正确的RGBA格式
  - 排名文字颜色适配背景（金/银/铜用黑色，其他用灰色）
  - 整体视觉层次更清晰
- **平台消息详细优化**：
  - 图例位置移至顶部，避免与坐标轴重叠
  - 峰值标注移至右上角，布局更合理
  - 增加图表顶部边距，为图例预留空间
  - 优化空数据处理逻辑
- **内容类型分布优化**：
  - 饼图尺寸调整为50%，为图例留出更多空间
  - 图例间距和字体大小优化
  - 颜色标识圆圈增大，视觉效果更明显
  - 布局更加平衡美观

### Fixed
- **修复排行榜进度条颜色问题**：正确处理RGBA格式，确保颜色正常显示
- **修复平台消息详细图例重叠问题**：调整布局确保图例不与图表重叠
- **修复内容类型分布图例显示问题**：优化空间分配确保图例完整显示
- **修复排名文字颜色问题**：确保在金银铜背景上文字可读性

### Performance
- **渲染性能优化**：所有测试场景下渲染时间稳定在0.6-0.8秒
- **文件大小优化**：正常数据场景98.7KB，各种边界情况合理
- **内存使用优化**：改进数据处理逻辑，减少内存占用

## [2.2.2] - 2026-08-06

### Added
- **边缘情况处理优化**：支持大量数据、空数据、极小数据、异常数据等各种场景
- **图表显示优化**：
  - 饼图添加背景圆圈，视觉效果更清晰
  - 堆叠柱状图添加图例显示
  - 颜色循环使用，支持超过颜色数量的数据项
- **数据合并优化**：内容类型超过6个时自动合并为"其他"类别
- **平台限制优化**：平台数量超过10个时自动限制显示数量

### Changed
- **颜色方案扩展**：图表颜色从8种扩展到12种
- **图例空间优化**：根据可用空间自动调整饼图大小
- **坐标轴标签优化**：确保所有平台标签都能正确显示
- **错误处理增强**：改进异常数据的处理能力

### Fixed
- **修复大量数据显示问题**：确保10个平台和10种内容类型正常显示
- **修复空数据处理问题**：确保空数据场景下不报错
- **修复极小数据处理问题**：确保1个平台1种内容类型正常显示
- **修复异常数据处理问题**：正确处理None、空字符串、负数等异常数据

### Performance
- **渲染性能优化**：大量数据场景下渲染时间稳定在0.75秒左右
- **内存使用优化**：改进数据处理逻辑，减少内存占用
- **文件大小优化**：各种场景下文件大小合理（空数据27.4KB，极小数据54.1KB）

## [2.2.1] - 2026-08-06

### Added
- **优化背景设计**：将背景改为优雅的蓝色渐变，更加美观
- **修复平台消息详细显示**：确保平台消息详情统计正常显示
- **修复内容类型分布显示**：确保消息内容类型分布图表正常显示
- **全面测试验证**：提供多种测试场景，确保所有组件正常工作

### Changed
- **背景渐变**：从灰色渐变改为优雅的蓝色渐变（240,248,255）到（230,240,255）
- **去除装饰性光点**：简化背景，去除可能影响性能的装饰元素
- **优化数据传递**：确保所有数据正确传递到显示组件

### Fixed
- **修复平台消息详情卡片显示问题**：确保堆叠柱状图正常显示
- **修复内容类型分布饼图显示问题**：确保饼图和图例正常显示
- **修复数据传递错误**：确保所有统计数据正确传递到渲染函数

### Performance
- **渲染性能优化**：去除复杂的背景装饰，提升渲染速度
- **内存占用降低**：简化背景生成逻辑，减少内存使用

## [2.2.0] - 2026-08-06

### Added
- **现代简洁UI设计**：重新设计为简洁优雅的界面风格
- **精致的视觉效果**：微妙的渐变背景、简洁的玻璃卡片效果
- **优化的统计卡片**：居中布局、清晰的层次结构
- **修复所有显示问题**：确保所有组件正常显示
- **新增测试图片**：提供正常数据、空数据、少量数据（464条）三种场景的测试图片

### Changed
- **背景设计**：改为现代灰色渐变，添加微妙的装饰性光点
- **卡片设计**：简化为简洁的玻璃效果，去除过度装饰
- **统计卡片**：重新设计为居中布局，去除图标和装饰线条
- **配色方案**：使用更现代的蓝色系配色方案
- **性能优化**：简化渲染逻辑，提升性能
- **版本号升级**：从 v2.1.0 升级至 v2.2.0，反映UI全面重构

### Fixed
- **修复空内容类型显示问题**：解决 "list index out of range" 错误
- **修复平台详细内容类型分布显示问题**：确保小数据量下正常显示
- **修复时间显示格式问题**：确保时间正确显示

### Performance
- **渲染性能提升**：简化图层和效果，渲染时间降至 ~1.0s
- **文件大小优化**：去除复杂效果后，文件大小更加合理
- **内存占用降低**：优化图层创建，降低内存使用

### Verified
- ✅ 正常数据场景渲染：106.5KB，1.04秒
- ✅ 空数据场景渲染：47.2KB，0.88秒  
- ✅ 少量数据场景（464条）：89.4KB，0.91秒
- ✅ 所有边界情况测试通过
- ✅ 平台详细内容类型分布显示正常
- ✅ 排行榜、时间趋势、圆环图等所有组件正常显示
- ✅ 时间显示格式正确，无显示问题

## [0.4.0] - 2026-08-06

### Fixed
- **修复 `/huli_record snapshot` 快照图大面积变黑（旧版圆环图 putalpha bug）**：旧版 `_draw_platform_donut` 用全不透明掩码绘制内圆镂空，导致非圆环区域 RGB 置黑后以 alpha 255 合成，整幅图被黑色覆盖；改为在圆环图层上用透明色重绘内圆镂空，彻底解决黑屏
- 修复 `_make_background` putpixel 缺少 alpha 导致背景出现透明黑（改用 1px 渐变条 resize 方案）
- 修复 `_draw_ranking` 空数据分支引用未定义变量 `inner_h`、`_draw_glass_card` 内发光椭圆坐标越界

### Changed
- `_draw_content_types` 由旧版独立 hex 色饼图重构为与平台分布一致的玻璃态圆环图（RGBA 分段、发光中心文字、右侧图例进度条、统一配色）
- 全图文字可读性优化：标题/统计卡片数值/图例/坐标轴/柱顶值/排行榜文字整体放大 1~2 级，次要文字颜色加深（slate-600），提升长图压缩后的清晰度
- 圆环分段新增白色分隔线并加粗，增强小分段辨识度
- 排行榜长名称改为中间省略（保留首尾），长群 ID 更易辨认
- 空数据状态统一为居中的玻璃态虚线圆角框 + 空圆环图标
- 快照水印版本号同步更新

## [0.3.2] - 2026-08-07

### Fixed
- **修复插件在 AstrBot 中加载失败 `ImportError: cannot import name '_to_int'`（热重载缓存根因）**：main.py 全部 11 处 `from fox_toolbox.xxx import ...` 改为相对导入 `from .fox_toolbox.xxx import ...`，符合 AstrBot 官方插件规范
  - 此前使用绝对导入时，`fox_toolbox` 作为顶层包缓存于 `sys.modules`，AstrBot 热重载只清理 `data.plugins.<插件名>.*` 前缀模块，旧版模块残留导致更新文件后仍报错
  - 改为相对导入后，所有模块以 `data.plugins.astrbot_plugin_fox_toolbox.*` 前缀命名，热重载可正确清理，更新文件后无需完全重启进程
- 更新 `scripts/fix_deploy.sh`：改用 `cp -r src/. dest/` 合并覆盖语法，确保已存在的旧目录内文件被更新；新增同步后校验输出

### Changed
- 插件模块命名空间统一为 `data.plugins.astrbot_plugin_fox_toolbox.fox_toolbox.*`

## [0.3.1] - 2026-08-07

### Added
- 新增 `scripts/fix_deploy.sh` 一键同步脚本：在 AstrBot 部署服务器上执行，将插件代码完整对齐到远程最新版本（fox_toolbox/、main.py、pages/、metadata.yaml），避免 main.py 与 fox_toolbox/ 文件版本混用导致的 `ImportError: cannot import name '_to_int'`

## [0.3.0] - 2026-08-06

### Fixed
- **修复 `/huli_record snapshot` 报错 `'dict' object cannot be interpreted as an integer`**：新增 `_to_int` 安全类型转换函数，对所有统计数值（时间趋势、排行、平台分布、平台详情、内容类型、数据表数量）做防御性转换，兼容 MySQL 驱动的 Decimal、None、字符串数字、dict 等异常类型，杜绝渲染崩溃
- 修复 `_draw_content_types` 饼图中 `math` 未导入导致的 NameError
- 修复 `_draw_content_types` 饼图引用不存在的 `_TEXT_DARK`、`_GLASS_BG` 常量导致的 NameError（改用 `_TEXT`、`_TRACK`）
- `_draw_platform_detail`、`_draw_content_types` 兼容 dict 类型输入（自动转换为列表结构）
- **`/huli_record snapshot` 增加渲染兜底**：将快照渲染调用包入 try-except，即使渲染过程出现任何异常，命令也会返回友好提示并记录完整日志，不再让 astrbot 弹出崩溃异常
- **加固 `_draw_header` 最新消息时间戳**：`newest_timestamp` 统一经 `_to_int` 安全转换，异常类型（dict 等）不再导致 `TypeError`
- **加固 `/huli_record stats` 最早/最新消息时间戳**：同样经 `_to_int` 安全转换后再做 `/1000` 运算

### Changed
- 快照渲染器全面采用防御性编程，任意异常数据都不会导致命令崩溃，最多显示空数据占位文案
- `/huli_record stats` 与 `/huli_record snapshot` 对异常数据达到同等防御水平
- 命令名称统一为 `huli_record`（原 `msg_record`），所有子命令同步更新

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

- **`/huli_record snapshot` 指令**：将数据库统计渲染成与 WebUI 风格一致的 PNG 快照图并发到聊天，包含统计卡片、消息时间趋势、发送者/群组排行 Top 8、内容类型分布
- 新增 `fox_toolbox/snapshot_renderer.py`，基于 Pillow 渲染 Liquid Glass 风格仪表盘快照，零新增重依赖（仅复用已存在的 Pillow）
- `/huli_record help` 帮助文本补充 snapshot 指令说明

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
- **数据库浏览命令**：新增 `/huli_record tables` 命令，可在聊天中查看数据库业务表列表（自动跳过 `_schema_meta` 系统表）
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
