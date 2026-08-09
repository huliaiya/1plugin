# Requirements Document

Feature Name: local-storage-fallback

Updated: 2026-08-09

## Introduction

狐狸插件当前仅通过 MySQL 存储消息记录，MySQL 不可用时插件整体降级、消息无法记录。
本特性新增一种本地 SQLite 存储方式：默认仍使用 MySQL；MySQL 故障时自动降级到本地
SQLite 写入，MySQL 恢复后自动切回并补写（backfill）降级期间的消息，保证消息记录不丢失，
且降级期间查询、统计、排行、导出、快照等能力完整可用。爱发电订单存储
（`order_db.py`）已有"MySQL 优先 + SQLite 兜底"的实现可作模式参考。

## Glossary

- **System**: 狐狸插件消息记录器（`Database`）
- **MySQL**: 主存储数据库（默认后端）
- **SQLite**: 本地兜底存储，SQLite 文件位于插件数据目录
- **降级模式**: MySQL 不可用、消息写入本地 SQLite 的状态
- **补写（backfill）**: MySQL 恢复后，将降级期间写入 SQLite 且未同步的消息批量导入 MySQL 的过程

## Requirements

### Requirement 1: 默认使用 MySQL，SQLite 作为自动兜底

**User Story:** AS 插件用户, I want 默认使用 MySQL 存储，so that 行为与现状一致，本地存储仅在 MySQL 故障时兜底。

#### Acceptance Criteria

1. WHEN 插件启动且 MySQL 可用，the system SHALL 仅使用 MySQL 存储消息，行为与现状一致
2. WHEN 插件启动且 MySQL 不可用，且配置 `storage_fallback_enabled` 为 true（默认），the system SHALL 初始化本地 SQLite 并进入降级模式，插件保持可记录消息
3. WHEN MySQL 运行期发生写入/查询故障，the system SHALL 自动切换到降级模式并将消息写入 SQLite
4. WHEN 配置 `storage_fallback_enabled` 为 false，the system SHALL 仅使用 MySQL，故障行为与现状一致

### Requirement 2: 本地存储为 SQLite 文件

**User Story:** AS 插件用户, I want 本地存储为结构化 SQLite 文件，so that 数据可查询、可迁移。

#### Acceptance Criteria

1. WHEN 进入降级模式，the system SHALL 在插件数据目录创建 SQLite 数据库文件（`messages_fallback.db`）
2. the system SHALL 在 SQLite 中建立 `messages` 表，字段与 MySQL `messages` 表一致，并建立 `content_hash` 唯一索引以幂等去重
3. WHILE 降级模式，the system SHALL 用线程池（`asyncio.to_thread`）执行 SQLite 读写，避免阻塞事件循环

### Requirement 3: MySQL 恢复自动切回并补写

**User Story:** AS 插件用户, I want MySQL 恢复后自动切回，so that 降级期间消息不丢失、无需手工干预。

#### Acceptance Criteria

1. WHILE 处于降级模式，the system SHALL 周期性检测 MySQL 连通性（默认 30 秒）
2. WHEN 检测到 MySQL 恢复，the system SHALL 自动切回 MySQL 后端
3. WHEN 切回 MySQL，the system SHALL 分批将 SQLite 中未同步（`synced=0`）的消息补写进 MySQL，单批默认 500 条
4. 补写使用 `INSERT IGNORE` 依赖 `content_hash` 唯一索引去重，the system SHALL 保证同一条消息不会在 MySQL 中产生重复
5. 每条消息补写成功后，the system SHALL 在 SQLite 中将该条标记为 `synced=1`
6. 补写完成后，the system SHALL 清理 SQLite 中已同步且超过保留期的记录，控制 SQLite 文件增长

### Requirement 4: 降级期间查询能力完整可用

**User Story:** AS 插件用户, I want 降级期间查询/统计/排行/导出/快照仍可用，so that 降级期体验不受影响。

#### Acceptance Criteria

1. WHILE 处于降级模式，查询消息、计数、统计、内容类型统计、平台详情、时间线、发送者排行、群组排行、上下文等接口 SHALL 从 SQLite 读取，返回与 MySQL 相同数据结构
2. WHILE 处于降级模式，Web 导出（JSON/CSV/TXT）与快照 SHALL 正常工作
3. WHILE 处于降级模式，Redis 统计缓存若已启用且可用，the system SHALL 继续更新；读取统计时优先缓存，缓存缺失回源 SQLite
4. IF 降级期间保存了媒体文件，the system SHALL 按现状保存到 AstrBot 数据目录（媒体保存与数据库后端无关）

### Requirement 5: 状态可观测

**User Story:** AS 插件用户, I want 知道当前处于何种存储模式，so that 便于排查问题。

#### Acceptance Criteria

1. WHEN 插件启动进入降级模式，the system SHALL 输出警告日志说明原因
2. WHEN MySQL 恢复并切回，the system SHALL 输出信息日志
3. WebUI 状态卡片 SHALL 展示当前存储后端（MySQL / SQLite 降级）与未同步消息数量

## Open Questions

- （已确认）本地存储载体：SQLite 文件
- （已确认）存储角色：MySQL 故障自动兜底，恢复自动切回并补写
- （已确认）功能范围：完整功能兼容（查询/统计/排行/导出/快照）
- 待确认：`storage_fallback_enabled` 默认值（建议 true，零配置即获得兜底能力）
