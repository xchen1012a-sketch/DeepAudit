# -*- coding: utf-8 -*-
"""
监控路由：运维/治理控制台
- 系统监控页面（仅治理/系统管理员可访问）
- API: summary、health、errors、jobs、logs
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from services.monitoring_service import (
    check_alerts,
    collect_business_metrics,
    collect_risk_metrics,
    collect_system_metrics,
    get_metrics,
    get_monitor_summary,
    get_monitor_health,
    get_monitor_errors,
    get_monitor_jobs,
    list_monitor_logs,
)
from utils.security import current_user, has_permission, login_required

bp = Blueprint("monitoring", __name__)

# 治理/系统管理员权限（任一即可访问系统监控）
_MONITOR_PERMISSIONS = ["MANAGE_SYSTEM", "MANAGE_SETTINGS"]


def _has_monitor_permission() -> bool:
    user = current_user()
    if not user:
        return False
    for key in _MONITOR_PERMISSIONS:
        if has_permission(key, user):
            return True
    return False


def _monitor_forbidden():
    """无权限时返回 403 中文"""
    return (
        jsonify({"ok": False, "msg": "forbidden", "message": "您无权访问系统监控，仅治理/系统管理员可访问"}),
        403,
    )


def _monitor_page_forbidden():
    """页面 403"""
    return (
        render_template(
            "forbidden.html",
            module_name="系统监控",
            required_permissions=_MONITOR_PERMISSIONS,
        ),
        403,
    )


@bp.route("/monitoring/dashboard")
@login_required
def monitoring_dashboard():
    """系统监控页面：运维/治理控制台"""
    if not _has_monitor_permission():
        return _monitor_page_forbidden()
    return render_template("monitoring/monitoring_dashboard.html")


@bp.route("/api/monitor/summary", methods=["GET"])
@login_required
def api_monitor_summary():
    """顶部态势条"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        time_window = request.args.get("window", "15m")
        if time_window not in ("15m", "1h", "24h"):
            time_window = "15m"
        data = get_monitor_summary(time_window=time_window)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/monitor/health", methods=["GET"])
@login_required
def api_monitor_health():
    """服务健康状态"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        data = get_monitor_health()
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/monitor/errors", methods=["GET"])
@login_required
def api_monitor_errors():
    """性能与错误"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        time_window = request.args.get("window", "15m")
        limit = request.args.get("limit", type=int, default=50)
        if time_window not in ("15m", "1h", "24h"):
            time_window = "15m"
        data = get_monitor_errors(time_window=time_window, limit=min(limit, 200))
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/monitor/jobs", methods=["GET"])
@login_required
def api_monitor_jobs():
    """作业与流水线"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        time_window = request.args.get("window", "15m")
        if time_window not in ("15m", "1h", "24h"):
            time_window = "15m"
        data = get_monitor_jobs(time_window=time_window)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/monitor/logs", methods=["GET"])
@login_required
def api_monitor_logs():
    """日志与追踪"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        time_from = request.args.get("time_from")
        time_to = request.args.get("time_to")
        level = request.args.get("level")
        module = request.args.get("module")
        request_id = request.args.get("request_id")
        user = request.args.get("user")
        limit = request.args.get("limit", type=int, default=100)
        limit = min(max(limit, 1), 500)
        data = list_monitor_logs(
            time_from=time_from,
            time_to=time_to,
            level=level,
            module=module,
            request_id=request_id,
            user=user,
            limit=limit,
        )
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


# ---- 兼容旧 API ----

@bp.route("/api/monitoring/metrics", methods=["GET"])
@login_required
def api_monitoring_metrics():
    """获取监控指标（兼容）"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        metric_type = request.args.get("metric_type")
        start_time = request.args.get("start_time")
        end_time = request.args.get("end_time")
        limit = request.args.get("limit", type=int, default=1000)
        metrics = get_metrics(metric_type=metric_type, start_time=start_time, end_time=end_time, limit=limit)
        return jsonify({"ok": True, "metrics": metrics})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/monitoring/collect", methods=["POST"])
@login_required
def api_monitoring_collect():
    """手动采集指标（兼容）"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        metric_category = request.get_json().get("category", "all") if request.is_json else "all"
        result = {}
        if metric_category in ("all", "system"):
            result["system"] = collect_system_metrics()
        if metric_category in ("all", "business"):
            result["business"] = collect_business_metrics()
        if metric_category in ("all", "risk"):
            result["risk"] = collect_risk_metrics()
        return jsonify({"ok": True, "metrics": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/monitoring/alerts", methods=["GET"])
@login_required
def api_monitoring_alerts():
    """获取告警列表（兼容）"""
    if not _has_monitor_permission():
        return _monitor_forbidden()
    try:
        alerts = check_alerts()
        return jsonify({"ok": True, "alerts": alerts})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
