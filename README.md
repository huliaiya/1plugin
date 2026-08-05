<div align="center">

# 🦊 狐狸插件

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E4.16%2C%3C5-blue?style=for-the-badge)](https://github.com/Soulter/astrbot)
[![Python](https://img.shields.io/badge/Python-3.12+-green?style=for-the-badge)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=for-the-badge)](LICENSE)

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

### MySQL 数据库配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `mysql_host` | `127.0.0.1` | MySQL 服务器地址 |
| `mysql_port` | `3306` | MySQL 服务器端口 |
| `mysql_user` | `root` | MySQL 用户名 |
| `mysql_password` | `` | MySQL 密码 |
| `mysql_database` | `fox_toolbox` | MySQL 数据库名（需提前创建） |

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

| 指令 | 说明 | 示例 |
|------|------|------|
| `/msg_record stats` | 查看消息统计信息 | `/msg_record stats` |
| `/msg_record cleanup` | 手动触发清理 | `/msg_record cleanup` |
| `/msg_record query [sender_id] [limit]` | 查询消息记录 | `/msg_record query 123456 20` |
| `/msg_record search <关键词> [limit]` | 搜索消息内容 | `/msg_record search hello 10` |
| `/msg_record help` | 查看帮助信息 | `/msg_record help` |

### 时间查询指令

| 指令 | 说明 | 示例 |
|------|------|------|
| `/msg_record today` | 查看今天的消息 | `/msg_record today` |
| `/msg_record yesterday` | 查看昨天的消息 | `/msg_record yesterday` |
| `/msg_record history <时间范围>` | 按时间范围查询 | `/msg_record history last7d` |

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
- 新增 `/msg_record tables` 聊天命令，查看数据库业务表列表（自动跳过 `_schema_meta` 系统表）
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
- [aiomysql](https://github.com/aio-libs/aiomysql) - 异步 MySQL 驱动库
- [aiohttp](https://github.com/aio-libs/aiohttp) - 异步 HTTP 客户端，用于多媒体文件下载

---

<div align="center">

**如果这个插件对你有帮助，请给个 Star 支持！**

</div>
