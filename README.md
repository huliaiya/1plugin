<div align="center">

# 🦊 狐狸插件

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E4.16%2C%3C5-blue?style=for-the-badge)](https://github.com/Soulter/astrbot)
[![Python](https://img.shields.io/badge/Python-3.12+-green?style=for-the-badge)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.8.2-orange?style=for-the-badge)](CHANGELOG.md)

**全平台聊天消息自动记录 | MySQL 5.7 存储 | Web 管理面板 | 全文搜索 | 插件 API**

</div>

---

## 为什么选择狐狸插件？

> **安装即用，零配置起步** — 插件会自动记录经过 AstrBot 的每一条消息，无需任何手动操作。需要更多功能时再按需开启。

- 聊天记录随时间流逝再也找不回来？群聊中重要的讨论沉入消息海洋？
- 管理多个平台的机器人，希望统一归档所有对话？
- 想在自己的插件中查询历史消息，却不想自己写数据库层？

**狐狸插件** 就是为此而生 —— 装上就忘，需要时随时搜索、导出、分析。

---

## ✨ 功能特色

- 🌐 **18 平台全覆盖** — 支持 AstrBot 接入的全部 18 个平台：Telegram、QQ（aiocqhttp / QQ 官方）、Discord、Slack、钉钉、飞书、企业微信、微信公众号、LINE、Misskey、Mattermost、Kook、Satori、WebChat 等
- 💾 **MySQL 5.7 存储** — 基于 MySQL 5.7 数据库，连接池管理，支持 FULLTEXT 全文搜索（ngram 分词器），兼容性强
- 📊 **完整记录** — 保存消息文本、发送者、群组/频道、时间戳、消息链、回复关系等完整信息
- 🖼️ **多媒体归档** — 可选保存图片、语音、视频、文件到本地，支持原图/缩略图模式，内容哈希自动去重（相同文件只存一份）
- 🌐 **Web 管理面板** — 内嵌于 AstrBot Dashboard，采用 Liquid Glass 液态玻璃设计风格，提供统计图表、消息搜索、数据导入导出，无需额外部署
- 🔍 **全文搜索** — 基于 MySQL FULLTEXT 索引（ngram 分词器），支持中文关键词搜索和多维度组合筛选
- 🗂️ **数据库浏览** — 内嵌只读数据库浏览器，支持查看数据表列表、表结构、表数据预览与只读 SQL 查询，自动拦截危险操作
- 📤 **数据导入导出** — 支持 JSON / CSV / ZIP（含媒体文件打包）格式，可跨实例迁移
- 🔌 **插件 API** — 提供 `query()` / `count()` / `search()` 等完整查询接口，其他插件一行代码即可调用
- 🧹 **自动清理** — 可配置保留天数和最大记录数，自动清理过期数据和孤立媒体文件
- ⚡ **异步高性能** — 全链路异步（aiomysql + aiohttp），连接池并发控制，不影响消息处理性能
- 🔒 **智能去重** — 基于 `(platform, message_id)` 和 `(platform, content_hash)` 双唯一索引，同一消息不会重复入库
- ⚡ **Redis 缓存** — 可选接入 Redis 缓存消息统计与最近消息，减轻 WebUI 高频查询对数据库的压力；未配置或连接失败时自动降级为无缓存模式，不影响任何功能
- ⚡ **爱发电打赏对接** — 对接爱发电平台，接受用户打赏、实时推送订单，支持生成支付链接、查询订单与赞助记录；无公网机器可启用订单轮询检测，替代 Webhook 推送（复刻自 astrbot_plugin_afdian）

---

## 📱 支持的平台

插件已适配 AstrBot 注册的全部 18 个平台，按类型分组：

| 类型 | 平台 |
|------|------|
| **即时通讯** | Telegram、LINE、WebChat |
| **QQ** | aiocqhttp（OneBot）、QQ 官方、QQ 官方 Webhook |
| **企业协作** | 钉钉、飞书、企业微信、企业微信 AI 助手 |
| **频道 / 社区** | Discord、Slack、Mattermost、Kook |
| **微信公众号** | 微信开放平台、微信公众号 |
| **联邦宇宙** | Misskey、Satori |

> 未列出的平台也不会丢失消息 —— 插件会自动回退到通用适配器，确保所有经过 AstrBot 的消息都能被记录。

---

## 🎯 适用场景

- **群聊存档** — 自动记录所有群聊、私聊消息，随时回溯历史讨论
- **跨平台汇总** — 同时管理 Telegram、QQ、Discord 等多个平台？所有消息统一存储，一处查询
- **数据分析** — 统计各平台活跃度、发送者排行、群组热度，用数据驱动运营决策
- **合规审计** — 保留完整的聊天记录用于审核，支持按时间、发送者、关键词检索
- **插件开发** — 在你自己的插件中查询历史消息上下文，构建更智能的回复逻辑
- **数据迁移** — 导出消息和媒体文件，在新实例上一键导入，无缝迁移

---

## 📦 安装

### 方式一：插件市场（推荐）

在 AstrBot WebUI 的 **插件市场** 中搜索「**狐狸插件**」并一键安装

### 方式二：手动安装

将本仓库克隆到 AstrBot 的插件目录：

```bash
cd AstrBot/data/plugins/
git clone https://github.com/leafliber/astrbot_plugin_fox_toolbox.git
```

然后在 AstrBot WebUI 的「插件管理」页面点击「重载插件」

### 前置要求

- MySQL 5.7+ 数据库实例（需提前创建好数据库）

---

## 🎛️ 配置项

在 AstrBot WebUI 的插件配置页面可调整以下选项：

### 功能配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_commands` | `true` | 是否启用消息记录指令 |
| `max_records` | `0` | 最大消息记录数，超过时自动清理最旧记录（0 = 不限制） |
| `retention_days` | `0` | 消息保留天数，超过此天数自动清理（0 = 永久保留） |
| `save_message_chain` | `true` | 是否保存完整消息链（包含图片、表情等） |
| `save_raw_message` | `false` | 是否保存平台原始消息对象 |
| `cleanup_interval_hours` | `24` | 自动清理间隔（小时） |
| `save_media_files` | `false` | 是否保存多媒体文件到本地 |
| `image_save_mode` | `original` | 图片保存模式：`original`（原图）/ `thumbnail`（缩略图） |

> **提示**：首次使用需先在 MySQL 中创建数据库（如 `CREATE DATABASE fox_toolbox CHARACTER SET utf8mb4;`），然后在配置页面填写连接信息。

### MySQL 数据库配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `mysql_host` | `127.0.0.1` | MySQL 服务器地址 |
| `mysql_port` | `3306` | MySQL 服务器端口 |
| `mysql_user` | `root` | MySQL 用户名 |
| `mysql_password` | `` | MySQL 密码 |
| `mysql_database` | `fox_toolbox` | MySQL 数据库名（需提前创建） |

### 本地 SQLite 兜底存储（自动降级）

MySQL 不可用、故障或连接中断时，插件自动降级到本地 SQLite 文件继续记录消息与爱发电订单，避免消息丢失；MySQL 恢复后自动切回并分批补写降级期间的消息（默认每 30 秒检测一次，单批 500 条幂等写入）。降级期间全部查询、统计、排行、导出功能保持可用，Web 面板状态卡片会标注当前存储后端与未同步消息数。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `storage_fallback_enabled` | `true` | 是否启用本地 SQLite 自动兜底存储；关闭后故障行为与旧版一致（消息无法记录） |
| `recovery_check_interval` | `30` | MySQL 恢复检测间隔（秒），最小 5 秒 |
| `connection_max_retries` | `5` | MySQL 与 Redis 断连后自动重连的最大连续次数（最小 1）；达到上限后停止自动重连，分别进入 SQLite 降级 / 无缓存模式 |
| `backfill_batch_size` | `500` | MySQL 恢复后单批补写消息条数，按批推进避免大事务 |
| `sqlite_max_retention_days` | `30` | 已补写进 MySQL 的消息在本地 SQLite 中的保留天数，超过后自动清理以控制文件增长 |

> **存储位置**：SQLite 兜底库位于插件数据目录下 `astrbot_plugin_fox_toolbox/messages_fallback.db`（如 `data/plugins/astrbot_plugin_fox_toolbox/messages_fallback.db`），无需额外安装依赖。降级与恢复全程自动，无需人工干预。
>
> **数据安全**：降级期间按保留天数/条数执行的自动清理只针对**已补写进 MySQL 的同步数据**，未同步（待补写）的消息会完整保留，确保 MySQL 恢复补写时不丢失任何消息。

### 爱发电打赏对接（可选）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `afdian_enabled` | `false` | 是否启用爱发电打赏对接功能 |
| `afdian_webhook_host` | `0.0.0.0` | 爱发电 Webhook 监听地址 |
| `afdian_webhook_port` | `6500` | 爱发电 Webhook 监听端口 |
| `afdian_webhook_token` | `` | 爱发电 Webhook 回调校验令牌（可选）：填写后回调请求需在 URL 携带 `?token=<值>` 才会被接受；留空保持向后兼容、不做校验 |
| `afdian_use_polling` | `true` | 是否启用无公网订单轮询检测（无公网机器替代 Webhook 推送） |
| `afdian_poll_interval` | `5` | 订单轮询间隔（秒），最小 1 秒 |
| `afdian_poll_timeout` | `300` | 发电后等待支付的完成时限（秒），默认 5 分钟 |
| `afdian_recovery_check_interval` | `30` | MySQL 故障降级后订单存储的恢复检测间隔（秒），恢复后自动切回并回写降级期订单，最小 5 秒 |
| `afdian_api_base_url` | `https://afdian.com/api/open` | 爱发电 API 根地址 |
| `afdian_api_user_id` | `` | 爱发电用户 ID（开发者后台获取） |
| `afdian_api_token` | `` | 爱发电 API 密钥（开发者后台获取） |
| `afdian_default_price` | `5` | 发起赞助时的默认金额（元） |
| `afdian_default_reply` | `赞助成功，感谢支持！` | 赞助成功后的默认回复语 |
| `afdian_notice_sessions` | `[]` | 接收订单通知的会话 ID（可用「开启发电通知」指令添加） |
| `afdian_rate_limit_enabled` | `true` | 是否启用 `/发电` 防刷限流 |
| `afdian_rate_limit_max_orders` | `3` | 1 分钟窗口内允许发起订单的最大次数，达到即触发拉黑 |
| `afdian_rate_limit_window` | `60` | 限流统计窗口（秒） |
| `afdian_rate_limit_ban_seconds` | `3600` | 触发限流后的拉黑时长（秒），默认 1 小时 |

> **防刷限流**：同一用户在 1 分钟窗口内发起 `/发电` 达到上限次数（默认 3 次）时，拒绝本次请求并临时拉黑（默认 1 小时），期间该用户再使用 `/发电` 会被拒绝并提示剩余等待时间，防止批量刷单/骚扰推送。

> **Webhook 要求**：爱发电订单通知需要公网可达的回调地址。请放行 `afdian_webhook_port` 对应端口，并在爱发电开发者设置中将回调地址指向该端口（如 `http://公网IP:6500/`）；若无公网 IP，可配置反向代理或内网穿透（frp / ngrok / cloudflared）转发到该端口。
>
> **无公网替代方案**：完全没有公网地址的机器可启用 `afdian_use_polling`（默认开启）。用户点击发电后，插件每 `afdian_poll_interval` 秒（默认 5 秒）拉取一次订单，并在 `afdian_poll_timeout` 秒（默认 300 秒 / 5 分钟）内发现新订单即处理（备注匹配用户并自动回复），无需公网回调；此模式同样可用全部查询指令。
>
> **数据存储**：爱发电订单会写入主插件 MySQL 数据库的 `afdian_orders` 表（与消息记录同一实例、同一库）；MySQL 不可用时自动回退到插件数据目录下的 SQLite 兜底，保证订单不丢失。

### Redis 缓存（可选）

通过 Redis 缓存消息统计与最近消息，可显著降低 WebUI 首页加载时对数据库的查询压力。未启用、未安装依赖或连接失败时，插件自动以无缓存模式运行，不影响任何功能。运行中若 Redis 断连，插件会按 `connection_max_retries`（默认 5 次）自动重连，期间自动以无缓存模式运行，恢复后自动切回缓存；达到上限仍未恢复则保持降级，需重启插件后重新建立自动重连。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `redis_enabled` | `false` | 是否启用 Redis 缓存 |
| `redis_host` | `127.0.0.1` | Redis 服务器地址 |
| `redis_port` | `6379` | Redis 服务端口 |
| `redis_password` | `` | Redis 认证密码（未设置则留空） |
| `redis_db` | `0` | Redis 数据库编号（建议使用独立编号） |
| `redis_cache_ttl` | `300` | 统计缓存有效期（秒）；消息落库后会即时更新最近消息缓存，统计缓存按此 TTL 刷新 |
| `redis_recent_window_seconds` | `1800` | 最近消息缓存时间窗口（秒，默认 1800 即 30 分钟）；超出窗口的旧消息会被清除，只保留窗口内的最新消息 |
| `redis_cache_refresh_interval` | `1800` | 缓存周期刷新间隔（秒，默认 1800 即 30 分钟）；每隔该周期从数据库重建最近消息缓存并强制对齐统计缓存，避免长期增量累积导致数据漂移 |

> **依赖安装**：使用 Redis 缓存需安装 `redis` 包。在 AstrBot 容器内执行 `pip install redis` 或在插件依赖中声明；未安装时插件会打印提示并自动降级为无缓存模式。

---

## 🌐 Web 管理面板

启用 Web 面板后，可在 AstrBot Dashboard 的插件页面中直接访问管理界面，无需额外安装依赖。

### 界面设计 — Liquid Glass 液态玻璃

Web 面板采用 **Liquid Glass** 液态玻璃设计风格，通过现代 CSS 技术实现半透明磨砂玻璃质感：

| 技术特性 | 说明 |
|----------|------|
| **磨砂玻璃** | `backdrop-filter: blur(20px) saturate(180%)` 实现背景模糊与饱和度增强 |
| **渐变高光** | `::before` 伪元素叠加斜向白色渐变，模拟玻璃表面的光线折射 |
| **内外阴影** | 外阴影提供悬浮感，内阴影（`inset`）模拟玻璃边缘高光 |
| **动态背景** | 多层径向渐变（紫、粉、蓝、黄）作为底衬，增强玻璃透明效果的视觉层次 |
| **流动光斑** | 统计卡片内部 `::after` 伪元素配合 `drift` 动画，营造液态流动感 |
| **交互反馈** | 全卡片浮动动画（统计卡片、图表容器、内容卡片、筛选区）、卡片悬停浮起、按钮高光反射、卡片入场动画（`cardAppear`） |
| **优雅降级** | 不支持 `backdrop-filter` 的浏览器自动回退为不透明背景（`@supports`） |
| **无障碍** | 尊重 `prefers-reduced-motion` 偏好，自动禁用动画 |
| **响应式** | 三套断点自适应手机（≤480px/≤768px）、平板（769~1024px）、电脑（>1024px），所有页面元素完美适配 |

> **浏览器兼容性**：液态玻璃效果需要浏览器支持 `backdrop-filter` 属性（Chrome 76+、Firefox 103+、Safari 9+）。不支持的环境会自动降级为不透明卡片样式，功能不受影响。

### 仪表盘

- **统计卡片** — 总消息数、群聊消息、私聊消息、平台数
- **MySQL 存储状态卡** — 显示 MySQL 连接状态（运行中 / SQLite 降级 / 未连接）、存储后端、MySQL 服务器版本、数据表数量、数据库占用大小、降级时的待同步消息数
- **Redis 缓存状态卡** — 显示 Redis 缓存运行状态（未启用 / 运行中 / 已降级）、连接地址、服务器版本、库编号、键数量、内存占用、缓存 TTL、统计缓存与最近消息缓存条目数
- **时间趋势图** — 消息数量随时间变化的趋势（总消息/群聊/私聊/频道四条数据线，颜色区分）
- **平台分布图** — 各平台消息占比饼图
- **发送者排行** — 消息发送量排名
- **群组排行** — 群组活跃度排名
- **时间范围切换** — 今日 / 近 7 天 / 近 30 天 / 近 90 天 / 全部

> 仪表盘采用渐进式渲染：各区域独立骨架屏加载，数据到达后即时填充。

### 消息搜索

- 多条件组合搜索（平台、群组、发送者、时间范围、关键词）
- 高级筛选（频道、消息类型、回复消息）
- 分页浏览历史消息
- 查看消息详情和上下文
- 搜索结果可一键跳转导出

### 数据导出

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| JSON | `.json` | 标准 JSON 格式，适合数据交换和程序处理 |
| CSV | `.csv` | 表格格式，可用 Excel 等工具打开 |
| ZIP | `.zip` | 专用打包格式，包含数据 + 媒体文件，支持导入还原 |

导出功能特性：
- 按条件筛选导出，复用搜索条件
- 异步后台处理，不阻塞操作
- 实时进度反馈
- ZIP 格式支持跨实例迁移

### 数据导入

- 支持 JSON、CSV、ZIP 格式
- 小文件（≤50MB）直接上传，大文件自动分片上传
- 两种导入模式：合并（添加新记录）/ 跳过重复（检测并跳过已存在记录）
- ZIP 格式自动还原媒体文件

---

## 💬 指令使用

> 指令功能可通过配置项 `enable_commands` 启用或禁用，默认启用。

### 基础指令

> 主命令均为中文；旧英文指令（如 `/huli_record stats`）仍可作为别名使用。
>
> 权限说明：`清理`、`查询`、`搜索`、`表列表`、`快照` 为管理类命令，仅管理员可执行。

| 指令 | 说明 | 示例 |
|------|------|------|
| `/狐狸记录 统计` | 查看消息统计信息 | `/狐狸记录 统计` |
| `/狐狸记录 清理` | 手动触发清理 | `/狐狸记录 清理` |
| `/狐狸记录 查询 [发送者ID] [limit]` | 查询消息记录 | `/狐狸记录 查询 123456 20` |
| `/狐狸记录 搜索 <关键词> [limit]` | 搜索消息内容 | `/狐狸记录 搜索 hello 10` |
| `/狐狸记录 帮助` | 查看帮助信息 | `/狐狸记录 帮助` |
| `/狐狸记录 今日` | 查看今天的消息 | `/狐狸记录 今日` |
| `/狐狸记录 昨日` | 查看昨天的消息 | `/狐狸记录 昨日` |
| `/狐狸记录 历史 <时间范围>` | 按时间范围查询 | `/狐狸记录 历史 last7d` |
| `/狐狸记录 快照` | 生成 WebUI 仪表盘快照图 | `/狐狸记录 快照` |
| `/狐狸记录 表列表` | 查看数据库中的业务表列表 | `/狐狸记录 表列表` |
| `/狐狸菜单` | 查看全部可用指令（旧 `/hulihelp` 仍可用） | `/狐狸菜单` |

**时间范围格式支持：**

| 格式 | 说明 | 示例 |
|------|------|------|
| 自然语言 | `today`、`yesterday`、`week`、`month`、`hour` | `week` |
| 天数范围 | `last7d`、`last30d`、`last3d` 等 | `last7d` |
| 小时范围 | `last1h`、`last3h`、`last12h` 等 | `last3h` |
| 具体日期 | YYYY-MM-DD 格式 | `2024-01-15` |
| 日期范围 | 日期范围，用 `~` 分隔 | `2024-01-01~2024-01-15` |
| 相对时间 | `-1d`（昨天）、`-7d`（7天前）等 | `-3d` |

---

## ⚡ 爱发电打赏指令

> 需在插件配置中启用 `afdian_enabled` 并填写 `afdian_api_user_id` / `afdian_api_token`。

| 指令 | 说明 | 权限 |
|------|------|------|
| `/发电 [金额]` | 生成爱发电支付链接，接受用户打赏（备注记录付款人）；别名 `/赞助`。启用轮询时提示请在设定时间内（默认 5 分钟）完成支付 | 所有人 |
| `/爱发电测试` | 模拟一笔新订单，走完整「自动检测 → 入库 → 推送到所有已设置的推送群 + 当前聊天群」链路（不请求真实接口），验证通知链路；别名 `/发电测试`、`/发电模拟`、`/模拟发电`、`/模拟发电订单`、`/爱发电模拟` | 管理员 |
| `/查询订单 <订单号>` | 查询指定订单的详情信息 | 管理员 |
| `/同步历史订单` | 通过爱发电 API 主动分页拉取全部历史订单入库（按交易号去重），随时可手动补拉 | 管理员 |
| `/查询发电` | 查询默认账号收到的赞助记录；别名 `/查询赞助` | 管理员 |
| `/开启发电通知` | 在当前会话开启爱发电订单通知；别名 `/发电通知`、`/爱发电通知` | 管理员 |

> **工作流程**：用户在机器人发送 `/发电`，获得支付链接并付款（链接备注中写入用户ID）；有公网时爱发电通过 Webhook 推送订单给插件；无公网时插件触发按需限时轮询，每 `afdian_poll_interval` 秒（默认 5 秒）拉取一次新订单，最多持续 `afdian_poll_timeout` 秒（默认 5 分钟），无待确认订单时自动停止。哪种方式下单均保存订单、通知所有订阅会话，并对该付款用户发送赞助成功回复。

> **历史订单同步**：插件启动/重载时会自动分页拉取爱发电平台的全部历史订单并入库（按交易号 `out_trade_no` 去重，只保存新增订单），保证 Webhook/轮询上线前的订单不丢失；也可随时使用 `/同步历史订单` 命令手动补拉。

> **无公网轮询（按需限时）**：无公网地址的机器可开启 `afdian_use_polling`（默认开启）。用户点击发电后插件启动限时轮询：每 `afdian_poll_interval` 秒（默认 5 秒）拉取一次订单，最多持续 `afdian_poll_timeout` 秒（默认 300 秒 = 5 分钟）；发现新订单即按与 Webhook 完全相同的备注匹配逻辑处理，订单只有首次入库（按交易号去重，旧订单不会被覆盖）；待确认订单全部处理完或轮询窗口到期后自动停止，无人发电时不会持续请求接口、避免刷屏日志。建议同时关闭 Webhook 端口对外监听。

> **图片水印**：`/查询订单`、`/查询发电` 的查询结果图片顶部显示插件名与插件版本（替代默认的框架名水印）。

---

## 🔌 其他插件调用

本插件提供了完整的 API 接口，其他插件可以通过以下方式调用：

### 获取 API 实例

```python
from astrbot.api.star import Context

async def get_fox_toolbox_api(context: Context):
    """获取狐狸插件 API"""
    recorder = context.get_registered_star("astrbot_plugin_fox_toolbox")
    if recorder:
        plugin_instance = getattr(recorder, "star_cls", None)
        if plugin_instance and hasattr(plugin_instance, "get_api"):
            return plugin_instance.get_api()
    return None
```

### 核心查询：query() 和 count()

```python
mr_api = await get_fox_toolbox_api(context)

# 基础查询
messages = await mr_api.query(limit=10)

# 多条件组合查询
messages = await mr_api.query(
    platform="telegram",
    group_id="123456",
    sender_id="user1",
    time="today",
    keyword="关键词",
    limit=20,
    order="desc"
)

# 多 ID 查询
messages = await mr_api.query(
    sender_ids=["user1", "user2", "user3"],
    time="last7d"
)

# 频道查询
messages = await mr_api.query(
    channel_id="987654",
    time="week"
)

# 回复查询
replies = await mr_api.query(
    reply_to_id="12345678",
    platform="discord"
)

# 分页查询
messages = await mr_api.query(
    group_id="123456",
    limit=20,
    offset=40
)

# 统计数量
count = await mr_api.count(platform="telegram", time="month")
```

### 快捷方法

```python
# 时间相关
messages = await mr_api.get_today(limit=20)
messages = await mr_api.get_yesterday(limit=20)
messages = await mr_api.get_recent(hours=6, limit=50)
messages = await mr_api.get_recent_days(days=30, limit=100)

# 搜索
messages = await mr_api.search("关键词", limit=20)
messages = await mr_api.search("关键词", group_id="123456", time="week")

# 单条查询
message = await mr_api.get_by_id(123)
message = await mr_api.get_by_platform_message_id("12345678", platform="telegram")

# 上下文
context_messages = await mr_api.get_context(message_id=123, before=5, after=5)

# 回复
replies = await mr_api.get_replies("12345678", platform="telegram")

# 频道
messages = await mr_api.get_by_channel("987654", time="week")

# 统计
stats = await mr_api.get_stats()
```

### query() 参数详解

| 参数 | 类型 | 说明 |
|------|------|------|
| `platform` | str | 单个平台名称 |
| `platforms` | List[str] | 多个平台列表 |
| `sender_id` | str | 单个发送者 ID |
| `sender_ids` | List[str] | 多个发送者 ID 列表 |
| `group_id` | str | 单个群组 ID |
| `group_ids` | List[str] | 多个群组 ID 列表 |
| `session_id` | str | 单个会话 ID |
| `session_ids` | List[str] | 多个会话 ID 列表 |
| `channel_id` | str | 频道 ID（Discord 等） |
| `message_type` | str | 消息类型：`group`、`private`、`channel` |
| `time` | str | 时间字符串（见时间格式表） |
| `start_time` | int | 开始时间戳（毫秒），与 time 互斥 |
| `end_time` | int | 结束时间戳（毫秒），与 time 互斥 |
| `keyword` | str | 消息内容关键词 |
| `reply_to_id` | str | 回复的目标消息 ID |
| `limit` | int | 返回数量限制 |
| `offset` | int | 偏移量（分页） |
| `order` | str | `desc` 倒序，`asc` 正序 |

### MessageRecord 数据结构

```python
@dataclass
class MessageRecord:
    id: Optional[int]           # 数据库自增ID
    platform: str               # 平台名称
    message_id: str             # 平台消息ID
    session_id: str             # 会话ID
    group_id: Optional[str]     # 群组ID (私聊为 None)
    channel_id: Optional[str]   # 频道ID (Discord等)
    sender_id: str              # 发送者ID
    sender_name: Optional[str]  # 发送者昵称
    message_type: str           # 消息类型 (group/private/channel)
    message_str: Optional[str]  # 纯文本消息内容
    message_chain: Optional[str] # 消息链JSON (包含图片、表情等)
    raw_message: Optional[str]  # 原始消息JSON
    reply_to_id: Optional[str]  # 回复的目标消息ID
    content_hash: Optional[str] # 内容哈希 (用于去重)
    timestamp: int              # 消息时间戳 (毫秒)
    created_at: int             # 记录创建时间 (毫秒)

# 辅助方法
message.to_dict()                        # 转为字典
message.get_message_chain_list()         # 解析消息链为列表
message.get_raw_message_dict()           # 解析原始消息为字典
```

---

## 🖼️ 媒体文件 API

### 其他插件获取媒体文件

```python
mr_api = await get_fox_toolbox_api(context)

messages = await mr_api.query(limit=10)

for msg in messages:
    media_paths = mr_api.extract_media_paths(msg)

    for rel_path in media_paths:
        # 获取绝对路径（文件不存在返回 None）
        abs_path = mr_api.get_media_absolute_path(rel_path)
        if abs_path:
            with open(abs_path, "rb") as f:
                image_data = f.read()

        # 获取 Web 访问 URL
        web_url = mr_api.get_media_url(rel_path)
```

### 媒体相关 API 方法

| 方法 | 说明 |
|------|------|
| `get_media_base_path()` | 获取媒体文件存储根目录的绝对路径 |
| `get_media_absolute_path(rel_path)` | 获取媒体文件的绝对路径（不存在返回 None） |
| `get_media_url(rel_path)` | 获取媒体文件的 Web 访问 URL |
| `extract_media_paths(message)` | 从消息记录中提取所有媒体文件的相对路径 |

---

## 📊 数据存储

### 数据库

消息存储在 MySQL 5.7 数据库中，需提前创建数据库：

```sql
CREATE DATABASE fox_toolbox CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
```

表结构（Schema Version 2）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT AUTO_INCREMENT | 自增主键 |
| `platform` | VARCHAR(64) NOT NULL | 平台标识 |
| `message_id` | VARCHAR(128) | 平台消息 ID |
| `session_id` | VARCHAR(128) | 会话 ID |
| `group_id` | VARCHAR(128) | 群组 ID |
| `channel_id` | VARCHAR(128) | 频道 ID |
| `sender_id` | VARCHAR(128) NOT NULL | 发送者 ID |
| `sender_name` | VARCHAR(256) | 发送者昵称 |
| `message_type` | VARCHAR(32) NOT NULL | 消息类型 |
| `message_str` | MEDIUMTEXT | 纯文本内容 |
| `message_chain` | LONGTEXT | 消息链 JSON |
| `raw_message` | LONGTEXT | 原始消息 JSON |
| `reply_to_id` | VARCHAR(128) | 回复目标消息 ID |
| `content_hash` | VARCHAR(64) | 内容哈希（去重） |
| `timestamp` | BIGINT NOT NULL | 消息时间戳 |
| `created_at` | BIGINT NOT NULL | 记录创建时间 |

索引：
- `(platform, message_id)` 唯一索引 — 防止同平台同消息重复入库
- `(platform, content_hash)` 唯一索引 — 内容级别去重
- `timestamp`、`sender_id`、`group_id`、`channel_id`、`session_id`、`reply_to_id` 常规索引
- `FULLTEXT` 全文搜索索引（ngram 分词器） — 支持中文消息内容关键词搜索

### 多媒体文件

启用多媒体保存后，文件存储路径为：

```
data/plugin_data/astrbot_plugin_fox_toolbox/media/
├── images/       # 图片
│   ├── a1/       # 按内容哈希前2位分目录
│   ├── b2/
│   └── ...
├── records/      # 语音
├── videos/       # 视频
└── files/        # 其他文件
```

**存储策略：**
- 文件名使用**内容 SHA256 哈希**（取前16位），相同内容只保存一份
- 目录按哈希前2位分组，避免单目录文件过多
- 文件名示例：`a1b2c3d4e5f6g7h8.jpg`

---

## 🔗 Web API 列表

插件注册了以下 Web API 端点（前缀 `/astrbot_plugin_fox_toolbox/`）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `stats` | GET | 获取统计概览 |
| `stats/timeline` | GET | 获取时间趋势数据 |
| `stats/senders` | GET | 获取发送者排行 |
| `stats/groups` | GET | 获取群组排行 |
| `messages` | GET | 查询消息列表 |
| `message/detail` | GET | 获取消息详情 |
| `message/context` | GET | 获取消息上下文 |
| `search` | GET | 搜索消息 |
| `export` | POST | 创建导出任务 |
| `export/status` | GET | 查询导出状态 |
| `export/download` | GET | 下载导出文件（大文件） |
| `export/download_data` | GET | 获取导出文件数据（base64，小文件） |
| `import/upload` | POST | 简单文件导入 |
| `import/init` | POST | 初始化分片导入 |
| `import/chunk/<session_id>/<index>` | POST | 上传分片 |
| `import/complete` | POST | 完成分片导入 |
| `import/status` | GET | 查询导入状态 |
| `platforms` | GET | 获取平台列表 |
| `senders` | GET | 获取发送者列表 |
| `groups` | GET | 获取群组列表 |
| `media` | GET | 获取媒体文件 |
| `schema_version` | GET | 获取数据库 Schema 版本 |

---

## 🏗️ 项目结构

```
astrbot_plugin_fox_toolbox/
├── main.py                  # 插件主入口
├── fox_toolbox/             # 核心源码
│   ├── __init__.py
│   ├── api.py               # 对外 API 接口
│   ├── database.py          # MySQL 5.7 数据库操作
│   ├── media_downloader.py  # 多媒体文件下载
│   ├── models.py            # 数据模型定义
│   ├── platform_adapter.py  # 平台适配器（18 个平台）
│   ├── serializer.py        # 消息链序列化
│   ├── time_utils.py        # 时间工具
│   └── web_api.py           # Web API 注册
├── pages/                   # Web 前端页面
│   └── recorder/
├── tests/                   # 测试用例
├── _conf_schema.json        # 配置项定义
├── metadata.yaml            # 插件元数据
└── requirements.txt         # 依赖列表
```

---

## 🛠️ 开发

### 本地调试

1. 克隆 AstrBot 本体和本插件仓库
2. 将插件目录放入 `AstrBot/data/plugins/`
3. 启动 AstrBot，在 WebUI 重载插件
4. 修改代码后点击「重载」即可热更新

### 运行测试

```bash
# 运行单元测试（不需要 MySQL）
python3 -m pytest tests/ -v -k "not mysql"

# 运行全部测试（包括 MySQL 集成测试，需启动 MySQL）
MYSQL_TEST_HOST=127.0.0.1 MYSQL_TEST_PORT=3306 \
MYSQL_TEST_USER=root MYSQL_TEST_PASSWORD=your_password \
python3 -m pytest tests/ -v
```

### 代码格式化

```bash
ruff format .
```

---

## 📝 更新日志

### v2.4.3（2026-08-07）

- **修复 WebUI 平台分布图 QQ 显示为紫色**：平台分布饼图显式指定天空蓝色板，与快照配色一致
- **快照整体文字清晰度提升**：各卡片小字号文字统一增大，压缩后更易读

### v2.4.2（2026-08-07）

- **快照卡片标题整体上移**：各卡片标题更贴近卡片顶部，布局更紧凑
- **WebUI 配色全面统一为天空蓝**：成功/警告/危险语义色、文本色、按钮渐变、卡片高光等所有残留杂色全部切换为与快照一致的天空蓝系

### v2.4.1（2026-08-07）

- **修复快照时间趋势卡片文字超出边框**：Y 轴刻度标签不再越出玻璃卡片，数据量级大时同样保持清晰完整

### v2.4.0（2026-08-07）

- **快照配色切换为浅蓝/天空蓝风格**：背景天空蓝渐变，卡片、图表、玻璃边框、文字统一为天空蓝色系
- **WebUI 配色统一为天空蓝**：页面背景去除绿/黄/粉杂色，时间趋势图线条统一为天空蓝系渐变

### v2.3.2（2026-08-07）

- **修复快照中文全部显示为问号/方块的根因**：系统缺失中文字体时，快照会全部显示为问号；现在渲染器会自动搜索系统字体目录中的 CJK / emoji 字体
- **新增 `/hulihelp` / `/狐狸菜单` 命令**：输入即可查看全部可用指令
- 继续优化快照可读性：提高时间趋势、排行榜、平台详情、图例与水印的小字号字体，长图压缩后更清晰
- 将未知消息类型的回退判断前移到平台适配器层，减少不同入口产生的统计口径漂移
- 移除 Web 面板重复的排行时间范围按钮，时间筛选行为更直接

### v2.3.1（2026-08-07）

- 修复快照统计卡大量显示 0 的根因：历史 `other` / `forum` / 脏 `message_type` 会结合 `group_id`、`channel_id` 自动归类，顶部统计卡、时间趋势、平台消息详情、群组排行恢复正常
- 修复 `消息内容类型分布` 缺失：`content_types` 兼容逗号串、JSON 数组和空值文本回退，旧数据也能统计出内容类型
- 修复平台消息详情图空白和柱顶文字位置错误：总量标签上移到柱体上方，0 值平台也保留基线提示
- 修复排行文本显示问题：过滤异常控制字符，名称裁剪与数值右对齐更稳定
- 同步版本号到 `metadata.yaml`、Plugin Page `BUILD_VERSION`、`index.html` 资源参数和快照水印

### v0.4.0（2026-08-06）

- 修复 `/huli_record snapshot` 快照图大面积变黑：旧版圆环图用全不透明掩码镂空内圆，导致整幅图被黑色覆盖，改为透明色重绘镂空彻底修复
- 修复背景渐变 putpixel 缺 alpha 导致的透明黑、排行榜空数据未定义变量、玻璃卡片发光椭圆越界等隐患
- `消息内容类型分布` 从旧版独立饼图重构为与平台分布一致的玻璃态圆环图，全图视觉风格统一
- 全图文字放大 1~2 级并加深次要文字颜色，提升长图在聊天中压缩后的可读性
- 圆环分段新增白色分隔线、长名称中间省略、空数据统一为玻璃态空状态卡片

### v0.3.2（2026-08-07）

- 修复插件加载失败 `ImportError: cannot import name '_to_int'`：main.py 全部导入改为相对导入 `from .fox_toolbox.xxx import`，符合 AstrBot 官方规范，根治热重载时顶层包模块缓存残留导致的问题（更新文件后无需完全重启 AstrBot）
- 更新 `scripts/fix_deploy.sh`：合并覆盖语法确保旧目录文件被更新，新增同步校验输出

### v0.3.1（2026-08-07）

- 新增 `scripts/fix_deploy.sh` 一键同步脚本：在 AstrBot 部署服务器上执行 `bash scripts/fix_deploy.sh`，将插件代码完整对齐到远程最新版本，避免 main.py 与 fox_toolbox/ 文件版本混用导致的导入错误

### v0.3.0（2026-08-06）

- 修复 `/huli_record snapshot` 报错 `'dict' object cannot be interpreted as an integer`：新增 `_to_int` 安全类型转换函数，对所有统计数值做防御性转换，兼容 MySQL 驱动的 Decimal、None、dict 等异常类型，杜绝渲染崩溃
- 修复 `_draw_content_types` 饼图中 `math` 未导入、`_TEXT_DARK`/`_GLASS_BG` 常量不存在导致的 NameError
- `/huli_record snapshot` 增加渲染兜底：渲染异常时返回友好提示并记录完整日志，不再让 astrbot 弹出崩溃异常
- 加固 `_draw_header` 最新消息时间戳与 `/huli_record stats` 最早/最新消息时间戳，异常类型（dict 等）不再导致 TypeError
- 命令名称统一为 `huli_record`（原 `msg_record`），所有子命令同步更新
- 快照渲染器全面采用防御性编程，任意异常数据都不会导致命令崩溃

### v0.2.10（2026-08-06）

- 快照新增"内容类型分布"卡片（对齐 WebUI）：饼图展示各内容类型消息占比，中心显示总消息数，右侧图例含颜色圆点/类型名/进度条/百分比数值，使用与 WebUI 一致的配色方案
- 内容类型分布从列表形式改为饼图形式，完全对齐 WebUI 的 contentTypeChart

### v0.2.9（2026-08-06）

- 快照新增"平台消息详情"卡片（对齐 WebUI）：堆叠柱状图展示各平台群聊/私聊/频道消息分布，顶部显示平台总消息数，左上角图例含三色圆点/系列名，平台名自动映射（Telegram/Discord/QQ 官方/微信等）
- 修复前端资源版本号同步问题（BUILD_VERSION 0.2.2 → 0.2.9），确保版本号在所有位置同步更新

### v0.2.8（2026-08-06）

- 快照新增"平台分布"卡片（对齐 WebUI）：圆环图展示各平台消息占比，中心显示总消息数，右侧图例含颜色圆点/平台名/进度条/数值百分比；平台名自动映射（Telegram/Discord/QQ 官方/微信等）

### v0.2.7（2026-08-06）

- 快照时间趋势图升级为多系列折线图（对齐 WebUI）：总消息（蓝）/群聊（绿）/私聊（橙）/频道（红）四条折线 + 左上角四色图例，"总消息"保留浅蓝区域填充
- WebUI 手机端圆环图布局修复：平台分布/内容类型圆环图图例改底部横向滚动、圆环缩小上移，避免与图例重叠；图表容器加高、主内容底部留白防导航栏遮挡

### v0.2.6（2026-08-06）

- 修复背景渲染为全黑的严重问题（Pillow `load()` 像素赋值在 resize 时丢失数据，改用 `paste`）
- 修复 emoji 模糊不可辨：改为 109px 原尺寸渲染后 LANCZOS 高质量下采样，🦊 清晰可辨
- 全面对齐 WebUI Liquid Glass 风格：浅色渐变背景、半透白磨砂卡片 + 柔和投影、蓝色渐变数值居中、移除花哨彩色外发光

### v0.2.5（2026-08-06）

- 液态玻璃质感增强：卡片边缘折射光晕改用独立大图层向外显著扩散，形成明显的 accent 色彩色散感
- 通透度提升：玻璃填充透明度降低，背景彩色光斑更易透过卡片显现
- 背景光斑更丰富：新增两组彩色光斑，为玻璃透出提供更丰富的色彩
- 高光与描边强化：顶部高光亮度提升、双层内描边亮度差加大，增强玻璃厚度感

### v0.2.4（2026-08-06）

- 快照图视觉升级为液态玻璃（Liquid Glass）风格：真实背景模糊、顶部高光、内描边、彩色折射边缘光、柔和光斑背景
- 改用 NotoSansCJK 矢量字体 + 2x 超采样降采样，解决文字模糊
- 集成 NotoColorEmoji 彩色 emoji 字体，解决表情无法显示
- 排行 Top 3 金银铜徽标、图标光晕、圆角进度条等细节美化，渲染耗时降至约 2.7s

### v0.2.3（2026-08-06）

- 新增 `/huli_record snapshot` 指令：将数据库统计渲染成与 WebUI 风格一致的 PNG 快照图发到聊天，包含统计卡片、时间趋势、发送者/群组排行、内容类型分布
- 新增 `fox_toolbox/snapshot_renderer.py`，基于 Pillow 渲染 Liquid Glass 风格仪表盘，无新增重依赖
- `/huli_record help` 补充 snapshot 指令说明

### v0.2.2（2026-08-05）

- 修复旧版 `web_api.py` 与新版 `main.py` 混用时 `register_all_web_apis` 参数不匹配崩溃，页面/API 不再因版本不同步而全部未注册
- `status`/`stats` 接口的 `db_status` 携带具体 MySQL 连接错误，前端状态卡片与顶部横幅直接展示失败原因
- Plugin Page 前端资源版本号升级到 `0.2.2`

### v0.2.1（2026-08-05）

- 修复 MySQL 不可用时 WebUI 整页空白：初始化失败后仍注册全部 Web API，页面可打开并显示降级状态
- `status`/`stats` 接口新增 `db_status.error` 透出具体连接错误，前端状态卡片与顶部横幅直接展示失败原因
- Plugin Page 前端资源版本号升级到 `0.2.1`

### v0.2.0（2026-08-05）

- 修复数据表数量卡片偶发空白：`db_status` 缺失时显示 `--` 并清除加载骨架，并自动用 `status` 接口兜底，不再停留骨架态
- 修复数据库浏览表列表崩溃：`list_tables()` 兼容 tuple 与 dict 两种游标行
- 修复只读 SQL 查询语法错误：`SHOW / DESCRIBE / DESC` 不再追加 `LIMIT`，已有超大 `LIMIT` 自动钳制
- 消息时间趋势图布局优化：图表高度压缩（手机 210px），折线下移、底部留白收紧，消除图表下方大片空白
- Plugin Page 前端资源版本号升级到 `0.2.0`

### v0.1.12（2026-08-05）

- 新增「数据库浏览」视图：数据表列表（含行数）、表结构查看、表数据预览、只读 SQL 查询面板，能力整合自参考插件 astrbot_plugin_mysql（作者 Chris95743）
- 只读查询安全策略：仅允许 `SELECT / SHOW / DESCRIBE / DESC`，拦截 DROP/TRUNCATE/GRANT/注释注入等危险操作，自动附加 LIMIT 防止大表全量拉取，查询超时上限 15 秒
- 新增 `/huli_record tables` 聊天命令，查看数据库业务表列表（自动跳过 `_schema_meta` 系统表）
- 消息时间趋势图优化：线条加粗、数据点与坐标文字放大，图表高度提升至 420px
- 统计卡片浮动动画更明显（±10px），页面背景新增动态极光流光
- 修复 SQL 安全校验误报：字符串字面量中的关键词（如 `LIKE '%grant%'`）不再被误判为危险操作
- Plugin Page 前端资源版本号升级到 `0.1.12`

### v0.1.11（2026-08-05）

- 移除 Dashboard 统计卡片的无限浮动动画，页面不再“一直刷新”，卡片仅在首次入场时淡入
- 修复数据库表数量获取不到的问题：表数量查询失败返回 `-1`，不再依赖额外的 `ping()` 前置判断
- 数据库状态卡片只展示已创建的数据表数量，标签固定为“数据表数量”，未连接时显示 `--`
- 消除数据库状态卡片双入口互相覆盖，默认复用 `stats` 响应数据，仅在 `stats` 失败时用 `status` 接口兜底
- Plugin Page 前端资源版本号升级到 `0.1.11`，刷新后会加载最新页面资源

### v0.1.10（2026-08-05）

- 数据库状态卡片只展示已创建的表数量（如 `12 张`），连接失败时显示“未连接”
- 移除“运行中/表数量”3 秒轮换逻辑，杜绝反复刷新观感
- 前端为数据库状态卡片新增独立加载入口，通过 `status` 接口兜底，`stats` 接口失败也能正常展示
- Plugin Page 前端资源版本号升级到 `0.1.10`，刷新后会加载最新页面资源

### v0.1.9（2026-08-05）

- 优化数据库状态卡片轮换逻辑，只在 Dashboard 可见时每 3 秒切换一次
- 卡片表数量文案收紧为“X 张表”，降低频繁切换时的刷新感
- `stats` 接口移除未使用的旧状态计算，减轻页面首屏加载负担

### v0.1.8（2026-08-05）

- Dashboard 新增“数据库状态”卡片，默认显示“运行中”，每 3 秒切换显示“已创建 X 张表”
- `stats` 接口新增 `db_status` 字段，数据库状态卡片直接复用统计接口返回数据
- Plugin Page 前端资源版本号升级到 `0.1.8`，刷新后会加载最新页面资源

### v0.1.7（2026-08-05）

- 移除 Dashboard 中不可用的「插件状态 / 健康度 / 内存占用」三张卡片，避免继续显示无效状态
- 清理对应的前端轮询、资源轮换和兜底文案逻辑，页面只保留已验证可用的统计卡片与图表
- 整理 `CHANGELOG.md` 中重复空版本标题，补齐版本记录可读性

### v0.1.6（2026-08-05）

- 为 Plugin Page 的 `app.js` 和 `style.css` 增加版本查询参数，强制 AstrBot 页面刷新后加载最新前端资源
- 状态卡片首屏改为“检测中”提示，减少旧缓存和加载过程中的误读

### v0.1.5（2026-08-05）

- 资源采集新增跨平台回退逻辑，Windows 等非 Linux 环境下也能获取插件进程内存、CPU 与运行时长
- `stats` 接口即使统计失败也会返回 `plugin_status`，状态卡片不再跟着统计接口一起失效

### v0.1.4（2026-08-05）

- 状态卡片改为直接读取 `stats` 接口返回的 `plugin_status`，不再依赖独立的状态接口路由
- `stats` 与 `status` 共用同一份状态构造逻辑，插件状态、健康度、内存/CPU 数值来源统一

### v0.1.3（2026-08-05）

- 依据 AstrBot 官方 `Plugin Pages` 文档修正状态接口路径，状态卡片前端请求改为插件内相对路径 `status`
- 后端新增 `status` 主路由，并保留旧的 `plugin/status` 兼容路由，降低 AstrBot 页面桥接下的接口匹配风险

### v0.1.2（2026-08-05）

- 修复 Dashboard 的「插件状态 / 健康度 / 内存占用」卡片只显示 `-` 的问题，前端现在会稳定显示明确状态和数值
- `plugin/status` 接口改为分项容错采集，数据库或资源指标局部异常时仍返回可展示结果
- 新增 `astrbot_plugin_fox_toolbox` 兼容包路径，恢复本地测试按项目包名导入
- 已完成本地验证：`176 passed, 63 skipped`，主入口 `main.py` 可正常导入

### v0.1.1（2026-08-05）

- 修复 Dashboard 状态卡片在 `plugin/status` 接口失败时显示 `-` 和骨架屏残留的问题
- 新增 `console.log` 诊断日志，便于定位 `plugin/status` 接口失败原因
- 新增 `clearStatusSkeletons()` 兜底清理逻辑，确保状态卡片最终能退出加载态
- 消息时间趋势图高度从 `280px` 调整到 `340px`，响应式断点同步更新

### v0.1.0（2026-08-05）

- 修复 Dashboard 三张图表在后端异常时区域空白的问题，前端现在会显示"暂无数据"和错误提示
- 修复状态卡片 skeleton 长时间不消失的问题，接口异常时正确显示"加载失败"
- 后端错误响应统一返回通用错误消息，详细异常仅写入日志
- `_build_query_filter_from_dict` 新增 `order` 白名单校验，导入相关接口补充文件大小和分片边界校验
- 版本号从 `0.0.11` 升级到 `0.1.0`

### v0.0.11（2026-08-05）

- Dashboard 新增「插件状态」卡片：后端 `Database.ping()` 探测数据库连通性，正常显示绿色「健康」，异常显示红色「异常」
- Dashboard 新增「资源占用」卡片：内存（MB）/ CPU（%）每 3 秒轮换显示，每 30 秒静默刷新数据
- 新增 `GET /fox_toolbox/plugin/status` 接口与 `fox_toolbox/sys_util.py`（标准库采集进程资源，无新增依赖）
- 统计卡片网格改为自适应布局，可容纳 7 张卡片

### v0.0.10（2026-08-05）

- Dashboard 统计卡片新增「频道消息」卡片（后端 `channel_message_count` 字段此前已支持，本次补齐前端展示）
- 统计卡片网格从 4 列调整为 5 列，并适配浮动动画与减少动画偏好

### v0.0.9（2026-08-05）

- WebUI 性能大幅优化，页面不再卡顿：
  - 移除大面积卡片（内容卡片、图表容器、筛选区）的持续浮动动画，仅保留一次性入场动画
  - 统计卡片浮动周期放缓（6s -> 12s）
  - 消息卡片移除 backdrop-filter，搜索页上百条卡片滚动更流畅
  - 消息列表改为分批渲染（每批 40 条），避免一次插入大量卡片阻塞主线程
  - 消息列表事件改为容器级事件委托，减少大量监听器开销

### v0.0.8（2026-08-05）

- 修复 WebUI 小文件导出下载失败（`downloadExportFile` 缺少 `extractData()`，导致 base64 下载必定失败）
- 修复 `test_schema_version` 测试断言过时（`SCHEMA_VERSION` 已升级至 3，断言仍为 2）

### v0.0.7（2026-08-05）

- WebUI 全面响应式自适应：手机/平板/电脑三套断点完美适配
- 修复 `.card` 浮动动画不生效（`contain: layout paint` 与 `translate` 冲突）
- 新增 viewport meta 标签，优化移动端浏览器体验
- 手机端浮动动画幅度降低，减少抖动感

### v0.0.6（2026-08-05）

- 修复时间趋势图频道数据不显示问题（`get_timeline_stats` 补充 `channel_count` 字段）
- 修复消息链 URL 的 XSS 漏洞（新增 `safeUrl()` 函数，仅允许 http/https 协议）
- 全卡片浮动动画：图表容器、筛选区现在与统计卡片、内容卡片一样拥有浮动效果
- 时间趋势图四条数据线添加明确颜色区分

### v0.0.1（2026-08-04）

**首个正式版本**，基于 [astrbot_plugin_message_recorder](https://github.com/leafliber/astrbot_plugin_message_recorder) 重构。

- 插件更名为「狐狸插件」，存储引擎从 SQLite 迁移至 MySQL 5.7
- Web 管理面板采用 Liquid Glass 液态玻璃设计风格
- 修复趋势图加载失败问题（MySQL 5.7 下 `FROM_UNIXTIME` + `GROUP BY` 别名兼容性）
- 修复 `_conf_schema.json` 中 JSON 语法错误（未转义双引号导致插件安装失败）
- 移除非标准的根目录 `__init__.py`（干扰 AstrBot 插件加载）
- 修复 SSRF、XSS 等安全问题，修复 ECharts 内存泄漏

完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 📄 许可证

[GNU Affero General Public License v3.0](LICENSE)

---

## 🙏 致谢

- [AstrBot](https://github.com/Soulter/astrbot) - 强大的多平台聊天机器人框架，本插件基于其插件体系开发
- [astrbot_plugin_message_recorder](https://github.com/leafliber/astrbot_plugin_message_recorder) - 原项目 **消息记录器**，由 [Leafiber](https://github.com/leafliber) 开发，狐狸插件在此基础上进行存储引擎迁移和二次开发
- [astrbot_plugin_mysql](https://github.com/Chris95743/astrbot_plugin_mysql) - 数据库表浏览 / 只读 SQL 查询的设计参考，由 [Chris95743](https://github.com/Chris95743) 开发，狐狸插件借鉴其安全校验与表浏览思路
- [astrbot_plugin_afdian](https://github.com/Zhalslar/astrbot_plugin_afdian) - 爱发电对接功能（发电打赏 / Webhook 订单推送 / 订单与赞助查询），复刻自 [Zhalslar](https://github.com/Zhalslar) 开发的同名单体插件，狐狸插件将其集成并适配扁平配置
- [爱发电 (AFDian)](https://afdian.com) - 创作者服务与打赏平台，本插件的发电打赏、订单推送与赞助查询均基于爱发电开放平台 API 实现，感谢官方提供稳定可靠的服务与开放接口
- [redis-py](https://github.com/redis/redis-py) - Python 异步 Redis 客户端库，本插件的消息统计与最近消息缓存基于其 `redis.asyncio` 接口实现
- [Redis](https://redis.io) - 高性能内存数据库，本插件可选的统计与最近消息缓存功能构建其上
- [aiomysql](https://github.com/aio-libs/aiomysql) - 异步 MySQL 驱动库
- [aiohttp](https://github.com/aio-libs/aiohttp) - 异步 HTTP 客户端，用于多媒体文件下载与爱发电 Webhook 服务
- [Python](https://www.python.org) - 本插件的主体开发语言，基于其异步生态（asyncio / aiohttp / aiomysql）构建
- [JavaScript](https://developer.mozilla.org/zh-CN/docs/Web/JavaScript) - Web 管理面板的前端逻辑实现，负责面板交互与数据请求
- [CSS](https://developer.mozilla.org/zh-CN/docs/Web/CSS) - Web 管理面板的 Liquid Glass 液态玻璃视觉样式
- [HTML](https://developer.mozilla.org/zh-CN/docs/Web/HTML) - Web 管理面板页面结构，以及爱发电查询图片的 T2I 模板
- [Shell](https://www.shellscript.sh) - 部署辅助脚本（`scripts/fix_deploy.sh`）的实现语言，用于一键同步插件代码到 AstrBot 服务器
- [GitHub](https://github.com) - 全球最大的开源协作平台，本插件的源码托管与版本管理均基于其服务，感谢官方提供稳定可靠的代码托管与协作支持

---

<div align="center">

**如果这个插件对你有帮助，请给个 Star 支持！**

</div>
