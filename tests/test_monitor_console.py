# -*- coding: utf-8 -*-
"""
系统监控控制台回归用例
- 权限 403：非治理/系统管理员访问 API 返回 403 中文
- 接口正常：有权限时 summary/health/errors/jobs/logs 返回 200
- 时间窗切换：window=15m/1h/24h 正常
- 日志抽屉：点击详情可打开
"""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient


def _login(client: FlaskClient, username: str, password: str) -> bool:
    r = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return r.status_code in (200, 302)


def _get_monitor_403(client: FlaskClient) -> bool:
    """无权限时是否返回 403 且包含中文"""
    r = client.get("/api/monitor/summary?window=15m")
    if r.status_code != 403:
        return False
    try:
        j = r.get_json()
        return bool(j and (j.get("message") or "").find("无权") >= 0)
    except Exception:
        return False


def _get_monitor_ok(client: FlaskClient) -> bool:
    """有权限时是否返回 200 且 ok=True"""
    r = client.get("/api/monitor/summary?window=15m")
    if r.status_code != 200:
        return False
    try:
        j = r.get_json()
        return bool(j and j.get("ok") is True and "data" in j)
    except Exception:
        return False


@pytest.mark.skip(reason="需要运行中的 app 和测试账号，可手动执行")
def test_monitor_403_forbidden(app, client: FlaskClient):
    """非治理/系统管理员访问 /api/monitor/* 返回 403 中文"""
    # 使用普通员工账号登录
    _login(client, "staff_user", "123456")
    assert _get_monitor_403(client), "普通用户应得到 403 且消息含「无权」"


@pytest.mark.skip(reason="需要运行中的 app 和治理/系统管理员账号")
def test_monitor_api_ok(app, client: FlaskClient):
    """治理/系统管理员访问接口正常"""
    _login(client, "admin_user", "123456")
    assert _get_monitor_ok(client), "管理员应得到 200 且 ok=True"


def test_monitor_time_window_params():
    """时间窗参数 15m/1h/24h 应被服务接受"""
    from services.monitoring_service import get_monitor_summary, _WINDOW_MINUTES

    for w in ("15m", "1h", "24h"):
        data = get_monitor_summary(time_window=w)
        assert "time_window" in data
        assert data["time_window"] == w
        assert "request_count" in data
        assert "db_status" in data


def test_monitor_health_returns_services():
    """健康检查返回 services 列表"""
    from services.monitoring_service import get_monitor_health

    data = get_monitor_health()
    assert "services" in data
    assert isinstance(data["services"], list)
    names = {s.get("name") for s in data["services"]}
    assert "web" in names or "db" in names
    assert "checked_at" in data


def test_monitor_jobs_structure():
    """作业接口返回 jobs 和 failed_top_reasons"""
    from services.monitoring_service import get_monitor_jobs

    data = get_monitor_jobs(time_window="15m")
    assert "jobs" in data
    assert isinstance(data["jobs"], list)
    assert "failed_top_reasons" in data
    assert isinstance(data["failed_top_reasons"], list)


def test_monitor_logs_filter():
    """日志接口支持筛选参数"""
    from services.monitoring_service import list_monitor_logs

    data = list_monitor_logs(limit=5)
    assert "logs" in data
    assert "total" in data
    assert isinstance(data["logs"], list)
    assert len(data["logs"]) <= 5
