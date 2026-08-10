"""宝塔面板管理功能（基于宝塔面板官方 API）。

复刻自 btpanel-plugin（作者 桉南/yll14，MIT License）：
https://gitee.com/yll14/btpanel-plugin

宝塔面板 API 调用方式：
- 请求地址：{面板地址}/<module>?action=<接口名>，POST 表单
- 签名：request_time 为当前 unix 秒，request_token = md5(request_time + md5(API_SK))
- 响应中 status 为 false 时表示接口调用失败

与原插件的差异：
- 由 Yunzai 插件改为 AstrBot Star mixin，命令统一为「/宝塔 <子命令>」形式；
- 面板地址与 API 密钥改为 AstrBot 设置界面扁平配置（btpanel_url / btpanel_api_sk），
  不再使用每个功能一个 yaml 的字段显示开关；
- 原插件基于「主人」的写操作权限，这里对应 AstrBot 的管理员权限；
- 原插件依赖 Yunzai 的重启机制的「更新插件」命令不移植。
"""

import hashlib
import time
from urllib.parse import quote

import aiohttp

from astrbot.api import logger


class BtpanelError(Exception):
    """宝塔面板 API 调用异常。"""


def _btpanel_sign(api_sk: str) -> dict:
    """生成宝塔面板 API 签名（与原插件 getBTSign 一致）。"""
    request_time = str(int(time.time()))
    md5_sk = hashlib.md5(api_sk.encode("utf-8")).hexdigest()
    request_token = hashlib.md5(
        (request_time + md5_sk).encode("utf-8")
    ).hexdigest()
    return {"request_time": request_time, "request_token": request_token}


def _btpanel_validate_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise BtpanelError("未配置宝塔面板地址（btpanel_url）")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise BtpanelError("btpanel_url 必须以 http:// 或 https:// 开头")
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise BtpanelError("btpanel_url 包含非法字符")
    return url


class BtpanelFeature:
    """宝塔面板管理功能 mixin。

    依赖宿主 Star 提供：
    - self.config: AstrBotConfig（扁平键）
    """

    # ---------- 基础能力 ----------

    def _init_btpanel(self):
        self.btpanel_enabled = bool(self.config.get("btpanel_enabled", True))

    def _btpanel_check(self):
        """检查配置是否可用；不可用时返回提示文本，可用返回 None。"""
        if not self.config.get("btpanel_enabled", True):
            return "宝塔面板功能未启用，请在插件配置中开启 btpanel_enabled"
        try:
            _btpanel_validate_url(self.config.get("btpanel_url", ""))
        except BtpanelError as e:
            return str(e)
        if not (self.config.get("btpanel_api_sk", "") or "").strip():
            return "未配置宝塔面板 API 密钥，请在插件配置中填写 btpanel_api_sk"
        return None

    async def _btpanel_post(self, path: str, params: dict) -> dict:
        """向宝塔面板发送 POST 请求。"""
        url = _btpanel_validate_url(self.config.get("btpanel_url", ""))
        api_sk = str(self.config.get("btpanel_api_sk", "") or "").strip()
        if not api_sk:
            raise BtpanelError("未配置宝塔面板 API 密钥（btpanel_api_sk）")
        sign = _btpanel_sign(api_sk)
        form = {
            "request_time": sign["request_time"],
            "request_token": sign["request_token"],
        }
        form.update(params or {})
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url + path,
                    data=form,
                    headers=headers,
                ) as resp:
                    try:
                        payload = await resp.json()
                    except Exception:
                        raise BtpanelError(
                            f"面板返回了非 JSON 数据（HTTP {resp.status}），"
                            "请确认地址与 API 密钥是否正确"
                        )
        except aiohttp.ClientError as e:
            raise BtpanelError(
                f"请求宝塔面板失败：{e}。请确认 btpanel_url 填写完整地址（含端口，"
                "如 https://面板IP:8888），并已在面板「设置 → API 接口」开启接口、放行本机 IP"
            )
        if isinstance(payload, dict) and payload.get("status") is False:
            raise BtpanelError(str(payload.get("msg") or "宝塔 API 请求失败"))
        return payload

    async def btpanel_action(self, module: str, action: str, params: dict | None = None):
        """调用宝塔面板接口：/module?action=<接口名>。"""
        path = f"/{module}?action={quote(action)}"
        return await self._btpanel_post(path, params or {})

    async def _btpanel_get_table(self, table: str, limit: int = 100) -> list:
        """查询面板 SQLite 数据表（sites / databases / ftps 等）。"""
        res = await self.btpanel_action(
            "data", "getData",
            {"table": table, "type": "-1", "list": "true", "p": "1",
             "limit": str(limit)},
        )
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and isinstance(res.get("data"), list):
            return res["data"]
        return []

    async def _btpanel_find_in_table(self, table: str, name: str) -> dict | None:
        """按 name 在数据表中查找记录。"""
        items = await self.btpanel_action(
            "data", "getData",
            {"table": table, "type": "-1", "list": "true", "p": "1",
             "search": name, "limit": "50"},
        )
        if not isinstance(items, list):
            if isinstance(items, dict) and isinstance(items.get("data"), list):
                items = items["data"]
            else:
                return None
        for item in items:
            if isinstance(item, dict) and item.get("name") == name:
                return item
        return items[0] if items else None

    async def _btpanel_run(self, fn):
        """执行返回文本的功能函数，异常统一转换为提示文本。"""
        try:
            return await fn()
        except BtpanelError as e:
            return f"操作失败：{e}"
        except Exception as e:
            logger.error(f"[Btpanel] 调用失败: {e}")
            return f"操作失败：{e}"

    async def _btpanel_cmd(self, fn):
        """命令统一入口：检查配置后执行功能函数并处理异常。"""
        err = self._btpanel_check()
        if err:
            return err
        return await self._btpanel_run(fn)

    # ---------- 输出格式化 ----------

    def _btpanel_section(self, title: str, lines: list) -> str:
        content = "\n".join(line for line in lines if line)
        if not content:
            return ""
        return f"{title}\n{content}\n\n"

    def _btpanel_fmt(self, title: str, body: str) -> str:
        body = (body or "").strip()
        if not body:
            return "暂无信息"
        return f"【{title}】\n\n{body}"

    # ---------- 系统管理 ----------

    async def btpanel_system_total(self) -> str:
        data = await self.btpanel_action("system", "GetSystemTotal")
        body = (
            self._btpanel_section("系统信息", [
                f"• 系统：{data.get('system')}",
                f"• 面板版本：{data.get('version')}",
                f"• 运行时间：{data.get('time')}",
            ])
            + self._btpanel_section("内存信息", [
                f"• 总物理内存：{data.get('memTotal')} MB ({data.get('memNewTotal')})",
                f"• 实际使用内存：{data.get('memRealUsed')} MB ({data.get('memNewRealUsed')})",
                f"• 可用内存：{data.get('memAvailable')} MB",
                f"• 空闲内存：{data.get('memFree')} MB",
                f"• 缓冲区内存：{data.get('memBuffers')} MB",
                f"• 缓存内存：{data.get('memCached')} MB",
                f"• 共享内存：{data.get('memShared')} MB",
            ])
            + self._btpanel_section("CPU 信息", [
                f"• CPU 核心数：{data.get('cpuNum')} 核",
                f"• CPU 使用率：{data.get('cpuRealUsed')}%",
            ])
        )
        return self._btpanel_fmt("服务器系统基础统计", body)

    async def btpanel_disk_info(self) -> str:
        disks = await self.btpanel_action("system", "GetDiskInfo")
        if not isinstance(disks, list) or not disks:
            return "暂无磁盘信息"
        lines = []
        for d in disks:
            if not isinstance(d, dict):
                continue
            size = d.get("size") or []
            parts = [
                d.get("path"),
                f"[{d.get('type')}]" if d.get("type") else "",
                f"总量 {size[0]}" if len(size) > 0 and size[0] else "",
                f"已用 {size[1]}" if len(size) > 1 and size[1] else "",
                f"可用 {size[2]}" if len(size) > 2 and size[2] else "",
                size[3] if len(size) > 3 and size[3] else "",
            ]
            parts = [p for p in parts if p]
            if parts:
                lines.append(f"• {' '.join(parts)}")
        if not lines:
            return "暂无磁盘信息"
        return self._btpanel_fmt("磁盘信息", "\n".join(lines))

    async def btpanel_mem_info(self) -> str:
        d = await self.btpanel_action("system", "GetMemInfo")
        body = self._btpanel_section("内存详情", [
            f"• 总内存：{d.get('memTotal')} MB",
            f"• 实际使用：{d.get('memRealUsed')} MB",
            f"• 可用：{d.get('memAvailable')} MB",
            f"• 空闲：{d.get('memFree')} MB",
            f"• 缓冲区：{d.get('memBuffers')} MB",
            f"• 缓存：{d.get('memCached')} MB",
        ])
        return self._btpanel_fmt("内存详情", body)

    async def btpanel_cpu_info(self) -> str:
        d = await self.btpanel_action("system", "GetCpuInfo")
        if not isinstance(d, list):
            return "暂无 CPU 信息"
        core_summary = []
        if len(d) > 1:
            core_summary.append(f"逻辑核心：{d[1]}")
        if len(d) > 4:
            core_summary.append(f"物理核心：{d[4]}")
        if len(d) > 5:
            core_summary.append(f"物理 CPU：{d[5]}")
        body = self._btpanel_section("CPU 详情", [
            f"• 型号：{d[3] if len(d) > 3 and d[3] else '-'}",
            f"• 整体使用率：{d[0] if len(d) > 0 else '-'}%",
            f"• {' | '.join(core_summary)}" if core_summary else "",
            f"• 各核：{' | '.join(f'核{i+1}: {v}%' for i, v in enumerate(d[2]))}"
            if len(d) > 2 and isinstance(d[2], list) and d[2] else "",
        ])
        return self._btpanel_fmt("CPU 详情", body)

    async def btpanel_load_average(self) -> str:
        d = await self.btpanel_action("system", "GetLoadAverage")
        body = self._btpanel_section("系统负载", [
            f"• 1 分钟：{d.get('one')}",
            f"• 5 分钟：{d.get('five')}",
            f"• 15 分钟：{d.get('fifteen')}",
            f"• 安全阈值：{d.get('safe')} / 最大：{d.get('max')}",
        ])
        return self._btpanel_fmt("系统负载", body)

    async def btpanel_net_work(self) -> str:
        d = await self.btpanel_action("system", "GetNetWork")
        nic_lines = []
        network = d.get("network")
        if isinstance(network, dict):
            for name, info in network.items():
                if isinstance(info, dict):
                    nic_lines.append(
                        f"• {name} ↑{info.get('up')} KB/s ↓{info.get('down')} KB/s"
                    )
        body = (
            self._btpanel_section("网络流量", [
                f"• 系统：{d.get('system') or '-'}",
                f"• 运行时间：{d.get('time') or '-'}",
                f"• 上传速率：{d.get('up')} KB/s | 下载速率：{d.get('down')} KB/s",
                f"• 总上传：{d.get('upTotal')} | 总下载：{d.get('downTotal')}",
            ])
            + ("\n".join(nic_lines) + "\n" if nic_lines else "")
        )
        return self._btpanel_fmt("网络流量", body)

    async def btpanel_re_memory(self) -> str:
        d = await self.btpanel_action("system", "ReMemory")
        body = self._btpanel_section("内存释放完成", [
            f"• 总内存：{d.get('memTotal')} MB",
            f"• 空闲：{d.get('memFree')} MB",
            f"• 实际使用：{d.get('memRealUsed')} MB",
        ])
        return self._btpanel_fmt("释放内存", body)

    async def btpanel_re_web(self) -> str:
        d = await self.btpanel_action("system", "ReWeb")
        return d.get("msg") or "面板重启指令已发出"

    async def btpanel_clear_system(self) -> str:
        d = await self.btpanel_action("system", "ClearSystem")
        if isinstance(d, list) and len(d) >= 2:
            return f"系统清理完成：{d[0]} 个文件，{d[1]} 字节"
        return d.get("msg") or "系统清理完成"

    async def btpanel_service_admin(self, name: str, action_type: str) -> str:
        d = await self.btpanel_action(
            "system", "ServiceAdmin", {"name": name, "type": action_type}
        )
        return d.get("msg") or "操作完成"

    # ---------- 网站管理 ----------

    async def btpanel_list_sites(self) -> str:
        sites = await self._btpanel_get_table("sites")
        if not sites:
            return "暂无网站"
        lines = []
        for s in sites:
            if not isinstance(s, dict):
                continue
            status = "运行中" if str(s.get("status")) == "1" else "已停止"
            block = f"• [{s.get('id')}] {s.get('name')} ({status})\n  路径：{s.get('path')}"
            if s.get("ps"):
                block += f"\n  备注：{s.get('ps')}"
            lines.append(block)
        return f"【网站列表】共 {len(lines)} 个\n\n" + "\n\n".join(lines)

    async def btpanel_site_start(self, name: str) -> str:
        site = await self._btpanel_find_in_table("sites", name)
        if not site:
            return f"未找到网站：{name}"
        res = await self.btpanel_action(
            "site", "SiteStart", {"id": site.get("id"), "name": site.get("name")}
        )
        return res.get("msg") or "站点已启用"

    async def btpanel_site_stop(self, name: str) -> str:
        site = await self._btpanel_find_in_table("sites", name)
        if not site:
            return f"未找到网站：{name}"
        res = await self.btpanel_action(
            "site", "SiteStop", {"id": site.get("id"), "name": site.get("name")}
        )
        return res.get("msg") or "站点已停止"

    async def btpanel_site_backup(self, name: str) -> str:
        site = await self._btpanel_find_in_table("sites", name)
        if not site:
            return f"未找到网站：{name}"
        res = await self.btpanel_action("site", "ToBackup", {"id": site.get("id")})
        return res.get("msg") or "备份任务已提交"

    async def btpanel_site_ssl(self, name: str) -> str:
        site = await self._btpanel_find_in_table("sites", name)
        if not site:
            return f"未找到网站：{name}"
        res = await self.btpanel_action("site", "GetSSL", {"siteName": site.get("name")})
        cert = res.get("cert") or res
        if not isinstance(cert, dict):
            cert = {}
        return self._btpanel_fmt(f"{site.get('name')} SSL 信息", (
            f"• 证书：{cert.get('issuer') or cert.get('subject') or '未部署'}\n"
            f"• 到期：{cert.get('notAfter') or cert.get('endtime') or '-'}"
        ))

    # ---------- 数据库管理 ----------

    async def btpanel_list_databases(self) -> str:
        dbs = await self._btpanel_get_table("databases")
        if not dbs:
            return "暂无数据库"
        lines = [
            f"• [{d.get('id')}] {d.get('name')} | 用户：{d.get('username')} | "
            f"类型：{d.get('type') or 'MySQL'}"
            for d in dbs if isinstance(d, dict)
        ]
        return f"【数据库列表】共 {len(lines)} 个\n\n" + "\n".join(lines)

    async def btpanel_db_status(self) -> str:
        res = await self.btpanel_action("database", "GetRunStatus")
        body = f"• 状态：{res.get('msg') or res.get('status') or '运行中'}"
        if res.get("data"):
            body += f"\n• 详情：{res.get('data')}"
        return self._btpanel_fmt("MySQL 运行状态", body)

    async def btpanel_mysql_info(self) -> str:
        res = await self.btpanel_action("database", "GetMySQLInfo")
        info = res.get("data") or res
        if not isinstance(info, dict):
            return res.get("msg") or "暂无信息"
        lines = [f"• {k}：{v}" for k, v in list(info.items())[:12]]
        return self._btpanel_fmt("MySQL 配置", "\n".join(lines))

    async def btpanel_db_backup(self, name: str) -> str:
        db = await self._btpanel_find_in_table("databases", name)
        if not db:
            return f"未找到数据库：{name}"
        res = await self.btpanel_action(
            "database", "ToBackup",
            {"id": db.get("id"), "sid": db.get("sid") or 0},
        )
        return res.get("msg") or "备份任务已提交"

    # ---------- 计划任务 ----------

    async def btpanel_list_crontab(self) -> str:
        tasks = await self.btpanel_action("crontab", "GetCrontab")
        if not isinstance(tasks, list) or not tasks:
            return "暂无计划任务"
        type_map = {"day": "每天", "minute-n": "N分钟", "hour": "每小时",
                    "week": "每周", "month": "每月"}
        s_type_map = {"toShell": "Shell脚本", "toUrl": "访问URL", "site": "备份网站",
                      "database": "备份数据库", "logs": "日志切割"}
        lines = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            status = "启用" if t.get("status") == 1 else "暂停"
            cycle = (
                f"{type_map.get(t.get('type')) or t.get('type')} "
                f"{t.get('where_hour') or ''}:"
                f"{str(t.get('where_minute') or '').zfill(2)}"
            )
            lines.append(
                f"• [{t.get('id')}] {t.get('name')} ({status})\n"
                f"  类型：{s_type_map.get(t.get('sType')) or t.get('sType')} | "
                f"周期：{cycle}\n  内容：{(t.get('sBody') or '')[:80]}"
            )
        return f"【计划任务】共 {len(lines)} 个\n\n" + "\n\n".join(lines)

    async def btpanel_cron_status(self, task_id, status: int) -> str:
        res = await self.btpanel_action(
            "crontab", "set_cron_status", {"id": task_id, "status": str(status)}
        )
        return res.get("msg") or "设置成功"

    async def btpanel_cron_logs(self, task_id) -> str:
        res = await self.btpanel_action("crontab", "GetLogs", {"id": task_id})
        if isinstance(res, str):
            return res[-1500:] or "暂无日志"
        if isinstance(res, dict):
            return res.get("msg") or res.get("data") or str(res)[:1500]
        return str(res)[:1500]

    # ---------- FTP / 后台任务 / 安全 ----------

    async def btpanel_list_ftp(self) -> str:
        users = await self._btpanel_get_table("ftps")
        if not users:
            return "暂无 FTP 用户"
        lines = []
        for u in users:
            if not isinstance(u, dict):
                continue
            status = "启用" if str(u.get("status")) == "1" else "禁用"
            lines.append(
                f"• [{u.get('id')}] {u.get('name')} ({status})\n  路径：{u.get('path')}"
            )
        return f"【FTP 用户列表】共 {len(lines)} 个\n\n" + "\n\n".join(lines)

    async def btpanel_list_tasks(self) -> str:
        tasks = await self.btpanel_action("task", "get_task_lists")
        if not isinstance(tasks, list) or not tasks:
            return "后台任务队列为空"
        lines = []
        for i, t in enumerate(tasks):
            if not isinstance(t, dict):
                continue
            name = t.get("name") or t.get("title") or t.get("task_name") or f"任务{i + 1}"
            status = t.get("status")
            if status is None:
                status = t.get("state") or "-"
            msg = t.get("msg")
            suffix = f" | {msg}" if msg else ""
            lines.append(f"• {name} | 状态：{status}{suffix}")
        return f"【后台任务队列】共 {len(lines)} 个\n\n" + "\n".join(lines)

    async def btpanel_warning_list(self) -> str:
        res = await self.btpanel_action("warning", "get_list")
        items = res.get("security") or res.get("data")
        if isinstance(res, list):
            items = res
        if not isinstance(items, list) or not items:
            return "暂无安全风险项，或尚未扫描"
        lines = []
        for i, item in enumerate(items[:20]):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("name") or item.get("ps") or f"项目{i + 1}"
            level = item.get("level") or item.get("m_level") or "-"
            desc = item.get("msg") or item.get("description") or ""
            lines.append(f"• {title} [{level}]\n  {desc}")
        more = f"\n\n... 还有 {len(items) - 20} 项" if len(items) > 20 else ""
        return f"【安全扫描结果】共 {len(items)} 项\n\n" + "\n\n".join(lines) + more

    async def btpanel_warning_score(self) -> str:
        res = await self.btpanel_action("warning", "get_scan_bar")
        return self._btpanel_fmt("安全扫描概况", (
            f"• 状态：{res.get('status') or '-'}\n"
            f"• 进度：{res.get('percentage') or '-'}%\n"
            f"• 检测项：{res.get('count') or '-'}\n"
            f"• 安全评分：{res.get('score') or '-'}"
        ))
