"""宝塔面板（BtpanelFeature）单元测试"""

import hashlib

import pytest

from astrbot_plugin_fox_toolbox.fox_toolbox.btpanel.star import (
    BtpanelFeature,
    BtpanelError,
    _btpanel_sign,
    _btpanel_validate_url,
)


class _FakeConfig(dict):
    def save_config(self):
        self._saved = True


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload


class _FakePostResult:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.posted = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, data=None, headers=None, ssl=False):
        self.posted = (url, data, headers, ssl)
        return _FakePostResult(self.response)


def _patch_session(monkeypatch, payload, status=200):
    session = _FakeSession(_FakeResponse(payload, status))

    class _FakeClientSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

        def post(self, url, data=None, headers=None, ssl=False):
            return session.post(url, data=data, headers=headers, ssl=ssl)

    monkeypatch.setattr("aiohttp.ClientSession", _FakeClientSession)
    return session


def _make_feature(config=None):
    cfg = _FakeConfig({
        "btpanel_enabled": True,
        "btpanel_url": "https://127.0.0.1:8080",
        "btpanel_api_sk": "testsk",
    })
    if config:
        cfg.update(config)
    feature = BtpanelFeature.__new__(BtpanelFeature)
    feature.config = cfg
    feature._init_btpanel()
    return feature


def test_sign_formula(monkeypatch):
    monkeypatch.setattr(
        "astrbot_plugin_fox_toolbox.fox_toolbox.btpanel.star.time.time",
        lambda: 1700000000,
    )
    sign = _btpanel_sign("testsk")
    md5_sk = hashlib.md5(b"testsk").hexdigest()
    expected_token = hashlib.md5(
        f"1700000000{md5_sk}".encode("utf-8")
    ).hexdigest()
    assert sign == {"request_time": "1700000000", "request_token": expected_token}


def test_validate_url():
    assert _btpanel_validate_url(" https://127.0.0.1:8080/ ") == \
        "https://127.0.0.1:8080"
    assert _btpanel_validate_url("http://localhost:8888") == \
        "http://localhost:8888"
    with pytest.raises(BtpanelError):
        _btpanel_validate_url("")
    with pytest.raises(BtpanelError):
        _btpanel_validate_url("ftp://127.0.0.1")
    with pytest.raises(BtpanelError):
        _btpanel_validate_url("https://a.com\nhttps://evil.com")


def test_check_config():
    feature = _make_feature()
    assert feature._btpanel_check() is None
    feature = _make_feature({"btpanel_enabled": False})
    assert "未启用" in feature._btpanel_check()
    feature = _make_feature({"btpanel_url": ""})
    assert "btpanel_url" in feature._btpanel_check()
    feature = _make_feature({"btpanel_api_sk": ""})
    assert "btpanel_api_sk" in feature._btpanel_check()


@pytest.mark.asyncio
async def test_post_success(monkeypatch):
    feature = _make_feature()
    session = _patch_session(monkeypatch, {"system": "Linux"})
    result = await feature._btpanel_post("/system?action=GetSystemTotal", {})
    assert result == {"system": "Linux"}
    url, data, headers, ssl = session.posted
    assert url == "https://127.0.0.1:8080/system?action=GetSystemTotal"
    assert "request_time" in data and "request_token" in data
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert ssl is False


@pytest.mark.asyncio
async def test_post_status_false_raises(monkeypatch):
    feature = _make_feature()
    _patch_session(monkeypatch, {"status": False, "msg": "权限不足"})
    with pytest.raises(BtpanelError, match="权限不足"):
        await feature._btpanel_post("/system", {})


@pytest.mark.asyncio
async def test_post_invalid_json_raises(monkeypatch):
    feature = _make_feature()

    class _BrokenResponse(_FakeResponse):
        async def json(self):
            raise ValueError("Expecting value")

    class _BrokenSession(_FakeSession):
        def __init__(self):
            super().__init__(_BrokenResponse("not json", 500))

    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda timeout=None: _BrokenSession(),
    )
    with pytest.raises(BtpanelError, match="非 JSON"):
        await feature._btpanel_post("/system", {})


@pytest.mark.asyncio
async def test_action_constructs_path(monkeypatch):
    feature = _make_feature()
    session = _patch_session(monkeypatch, {"ok": 1})
    await feature.btpanel_action("system", "GetSystemTotal", {"a": "1"})
    url, data, _, _ = session.posted
    assert url == "https://127.0.0.1:8080/system?action=GetSystemTotal"
    assert data["a"] == "1"


@pytest.mark.asyncio
async def test_get_table_handles_list_and_dict(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        assert module == "data" and action == "getData"
        return [{"id": 1}]

    feature.btpanel_action = _action
    assert await feature._btpanel_get_table("sites") == [{"id": 1}]

    async def _action2(module, action, params=None):
        return {"data": [{"id": 2}]}

    feature.btpanel_action = _action2
    assert await feature._btpanel_get_table("sites") == [{"id": 2}]


@pytest.mark.asyncio
async def test_find_in_table(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        return [{"name": "example.com", "id": 1}, {"name": "other.com", "id": 2}]

    feature.btpanel_action = _action
    site = await feature._btpanel_find_in_table("sites", "example.com")
    assert site == {"name": "example.com", "id": 1}


@pytest.mark.asyncio
async def test_run_catches_error(monkeypatch):
    feature = _make_feature()

    async def _boom():
        raise BtpanelError("接口炸了")

    result = await feature._btpanel_run(_boom)
    assert result == "操作失败：接口炸了"

    async def _boom2():
        raise ValueError("其他错误")

    result = await feature._btpanel_run(_boom2)
    assert "操作失败" in result


@pytest.mark.asyncio
async def test_system_total_format(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        return {"system": "Linux", "version": "9.0", "time": "1 day",
                "memTotal": 2048, "memNewTotal": "2G",
                "memRealUsed": 512, "memNewRealUsed": "0.5G",
                "memAvailable": 1500, "memFree": 300,
                "memBuffers": 10, "memCached": 20, "memShared": 1,
                "cpuNum": 4, "cpuRealUsed": 12}

    feature.btpanel_action = _action
    text = await feature.btpanel_system_total()
    assert "服务器系统基础统计" in text
    assert "Linux" in text and "2G" in text and "12%" in text


@pytest.mark.asyncio
async def test_disk_info_format(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        return [{"path": "/", "type": "ext4", "size": ["20G", "5G", "15G", "25%"]}]

    feature.btpanel_action = _action
    text = await feature.btpanel_disk_info()
    assert "磁盘信息" in text and "/" in text and "25%" in text


@pytest.mark.asyncio
async def test_cpu_info_format(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        return [25, 8, [25, 26, 27, 28], "Intel Xeon", 4, 1]

    feature.btpanel_action = _action
    text = await feature.btpanel_cpu_info()
    assert "CPU 详情" in text and "Intel Xeon" in text and "核1: 25%" in text


@pytest.mark.asyncio
async def test_site_lifecycle(monkeypatch):
    feature = _make_feature()
    calls = []

    async def _action(module, action, params=None):
        calls.append((module, action, params))
        if module == "data":
            return [{"name": "example.com", "id": 7, "status": "1",
                     "path": "/www/wwwroot/example"}]
        if action == "GetSSL":
            return {"cert": {"issuer": "Let's Encrypt", "notAfter": "2026-12-01"}}
        return {"msg": "操作成功"}

    feature.btpanel_action = _action

    assert "共 1 个" in await feature.btpanel_list_sites()
    assert "操作成功" in await feature.btpanel_site_start("example.com")
    assert "操作成功" in await feature.btpanel_site_stop("example.com")
    assert "操作成功" in await feature.btpanel_site_backup("example.com")
    ssl_text = await feature.btpanel_site_ssl("example.com")
    assert "Let's Encrypt" in ssl_text and "2026-12-01" in ssl_text
    assert ("site", "SiteStart", {"id": 7, "name": "example.com"}) in calls


@pytest.mark.asyncio
async def test_site_not_found(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        return []

    feature.btpanel_action = _action
    assert "未找到网站" in await feature.btpanel_site_start("nope.com")


@pytest.mark.asyncio
async def test_database_management(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        if module == "data":
            return [{"name": "test_db", "id": 1, "username": "root",
                     "sid": 0}]
        if action == "GetRunStatus":
            return {"msg": "运行中"}
        if action == "GetMySQLInfo":
            return {"data": {"port": 3306, "bind-address": "127.0.0.1"}}
        return {"msg": "备份任务已提交"}

    feature.btpanel_action = _action
    assert "共 1 个" in await feature.btpanel_list_databases()
    assert "运行中" in await feature.btpanel_db_status()
    assert "3306" in await feature.btpanel_mysql_info()
    assert "备份任务已提交" in await feature.btpanel_db_backup("test_db")


@pytest.mark.asyncio
async def test_crontab_management(monkeypatch):
    feature = _make_feature()
    calls = []

    async def _action(module, action, params=None):
        calls.append((action, params))
        if action == "GetCrontab":
            return [{"id": 3, "name": "备份数据库", "status": 1,
                     "type": "day", "where_hour": "3", "where_minute": 0,
                     "sType": "database", "sBody": "btpython xxx"}]
        if action == "GetLogs":
            return "2026-01-01 ok\n" * 10
        return {"msg": "设置成功"}

    feature.btpanel_action = _action
    text = await feature.btpanel_list_crontab()
    assert "共 1 个" in text and "备份数据库" in text
    assert "设置成功" in await feature.btpanel_cron_status(3, 1)
    assert "设置成功" in await feature.btpanel_cron_status(3, 0)
    logs = await feature.btpanel_cron_logs(3)
    assert "ok" in logs
    assert ("set_cron_status", {"id": 3, "status": "1"}) in calls


@pytest.mark.asyncio
async def test_ftp_tasks_warning(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        if module == "data":
            return [{"id": 1, "name": "ftpuser", "status": "1",
                     "path": "/www"}]
        if action == "get_task_lists":
            return [{"name": "备份", "status": 1, "msg": "ok"}]
        if action == "get_list":
            return {"security": [{"title": "弱口令", "level": "高",
                                  "description": "root 密码过弱"}]}
        if action == "get_scan_bar":
            return {"status": "已完成", "percentage": 100, "count": 12,
                    "score": 88}
        return []

    feature.btpanel_action = _action
    assert "ftpuser" in await feature.btpanel_list_ftp()
    assert "备份" in await feature.btpanel_list_tasks()
    text = await feature.btpanel_warning_list()
    assert "弱口令" in text and "高" in text
    score = await feature.btpanel_warning_score()
    assert "88" in score and "100%" in score


@pytest.mark.asyncio
async def test_service_admin(monkeypatch):
    feature = _make_feature()

    async def _action(module, action, params=None):
        assert params == {"name": "nginx", "type": "restart"}
        return {"msg": "操作成功"}

    feature.btpanel_action = _action
    assert "操作成功" in await feature.btpanel_service_admin("nginx", "restart")


@pytest.mark.asyncio
async def test_unconfigured_returns_error():
    feature = _make_feature({"btpanel_url": "", "btpanel_api_sk": ""})

    async def _never():
        raise AssertionError("不应发起请求")

    result = await feature._btpanel_cmd(_never)
    assert "btpanel_url" in result
