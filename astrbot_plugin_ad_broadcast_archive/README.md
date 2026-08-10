# astrbot_plugin_ad_broadcast_archive（广告广播助手归档副本）

[![Version](https://img.shields.io/badge/Version-1.0.1-orange?style=for-the-badge)](README.md)

狐狸插件内置广告助手的历史归档副本，保留独立运行所需的实现，供代码追溯和兼容性参考。正式功能请使用狐狸插件内置的广告助手。

## 版本记录

### 1.0.1

- 重命名为 `astrbot_plugin_ad_broadcast_archive`，明确其归档副本用途。

## 功能特性

- 自动记录多平台群聊会话，跨平台持久化
- 富媒体广告：支持文本 + 图片（URL / 本地路径）+ @用户 + @全体
- 群聊广告开关：`/开启广告` / `/关闭广告`（写回配置 `disable_gids`，重启后仍生效）
- 平台白/黑名单：`dsgg_platforms` / `dsgg_exclude_platforms`
- 定时广播：`/定时广告 09:00,14:30` —— 后台任务整分触发，按配置的发送间隔逐群发送
- 发送失败仅记 warning，不中断整批广播

## 配置项（AstrBot WebUI → 插件 → 广告广播助手）

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `dsgg_enabled` | bool | `true` | 是否启用广告广播助手 |
| `dsgg_platforms` | list | `[]` | 平台白名单；空表示全部 |
| `dsgg_exclude_platforms` | list | `[]` | 平台黑名单 |
| `disable_gids` | list | `[]` | 不接收广告的群聊，支持 `gid` 或 `platform:gid` |
| `dsgg_send_interval` | int | `0` | 群间发送间隔秒；0 = 随机 1-3 秒 |

## 命令（除群级开关外，其余仅 ADMIN）

| 命令 | 说明 |
|---|---|
| `/开启广告` | 当前群重新接收广告 |
| `/关闭广告` | 当前群不再接收广告（自动写入配置） |
| `/添加广告 <内容>` | 添加广告；`/添加广告 文字` 纯文本，`/添加广告 文字+https://example.com/a.png` 文本+图片（回复消息也支持） |
| `/删除广告 <id>` | 删除指定广告 |
| `/广告列表` | 列出全部广告 ID 与文本预览 |
| `/查看广告 <id>` | 查看某条广告的富媒体内容 |
| `/广告群列表` | 列出当前已接入的群聊及其开关状态 |
| `/定时广告 HH:MM[,HH:MM...]` | 设置每日定时广播时间点；空参数查看当前定时 |
| `/停止广告` | 停止当前定时广播 |

## 修复的兼容问题

原版 `astrbot_plugin_furry_dsgg` 在 Telegram 上报：

```
'TelegramPlatformEvent' object has no attribute 'bot'
```

根因是 handler 通过 `event.bot.send_message` 发送图片消息。本插件统一改用 AstrBot 推荐的 `await context.send_message(umo, chain)`，跨平台一致。

## 数据目录

```
<astrbot_plugin_data_path>/astrbot_plugin_ad_broadcast/

该路径沿用原副本的数据目录名称，用于兼容已有归档数据。
├── ads.json            # 广告列表
├── schedule.json       # 定时广播时间点
└── known_groups.json   # 已接入的群聊
```

## 测试

```
python -m pytest tests/test_ad_broadcast.py -v
```

测试涵盖：群会话记录与持久化、平台白/黑名单、群级禁用、广告 CRUD、定时解析与启停、`_broadcast` 发送逻辑（含失败降级）、消息链重建与纯文本回退。

## 致谢

- 广告助手（DsggFeature）原实现：[astrbot_plugin_fox_toolbox](https://github.com/huliaiya/1plugin)
- 原版插件：[astrbot_plugin_furry_dsgg](https://github.com/FurryR/astrbot_plugin_furry_dsgg)（在 Telegram 上失效）
- AstrBot：[AstrBot](https://github.com/AstrBotDevs/AstrBot)

## 许可

MIT
