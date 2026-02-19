# -*- coding: utf-8 -*-
"""
监控服务：系统指标采集、业务指标统计、告警规则执行
运维/治理控制台专用：summary、health、errors、jobs、logs 聚合
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_metric(metric_type: str, metric_name: str, metric_value: float, metric_unit: str = "") -> int:
    """记录监控指标"""
    with get_conn() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            """
            INSERT INTO db_metrics (metric_type, metric_name, metric_value, metric_unit)
            VALUES (?, ?, ?, ?)
            """,
            (metric_type, metric_name, metric_value, metric_unit),
        )
        return cursor.lastrowid


def collect_system_metrics() -> dict[str, Any]:
    """采集系统指标"""
    metrics = {}

    # API响应时间（示例）
    api_response_time = 0.1  # TODO: 实际从监控系统获取
    record_metric("system", "api_response_time", api_response_time, "ms")
    metrics["api_response_time"] = api_response_time

    # 数据库连接数（示例）
    db_connections = 5  # TODO: 实际从数据库获取
    record_metric("system", "db_connections", db_connections, "count")
    metrics["db_connections"] = db_connections

    # 错误率（示例）
    error_rate = 0.01  # TODO: 实际从日志统计
    record_metric("system", "error_rate", error_rate, "percent")
    metrics["error_rate"] = error_rate

    return metrics


def collect_business_metrics() -> dict[str, Any]:
    """采集业务指标"""
    metrics = {}

    with get_conn() as conn:
        conn.row_factory = None

        # 今日发票数量
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) FROM invoices WHERE DATE(created_at) = ?",
            (today,),
        ).fetchone()
        invoice_count_today = row[0] if row else 0
        record_metric("business", "invoice_count_today", invoice_count_today, "count")
        metrics["invoice_count_today"] = invoice_count_today

        # 待审批数量
        row = conn.execute(
            "SELECT COUNT(*) FROM invoices WHERE approval_status = 'PENDING'",
        ).fetchone()
        pending_count = row[0] if row else 0
        record_metric("business", "pending_approval_count", pending_count, "count")
        metrics["pending_approval_count"] = pending_count

        # 平均审批时长（小时）
        row = conn.execute(
            """
            SELECT AVG((julianday(first_approved_at) - julianday(created_at)) * 24)
            FROM invoices
            WHERE first_approved_at IS NOT NULL
            """,
        ).fetchone()
        avg_approval_hours = _safe_float(row[0] if row else 0, 0)
        record_metric("business", "avg_approval_hours", avg_approval_hours, "hours")
        metrics["avg_approval_hours"] = avg_approval_hours

        # 风险事件数量（今日）
        row = conn.execute(
            "SELECT COUNT(*) FROM risk_events WHERE DATE(created_at) = ?",
            (today,),
        ).fetchone()
        risk_events_today = row[0] if row else 0
        record_metric("business", "risk_events_today", risk_events_today, "count")
        metrics["risk_events_today"] = risk_events_today

    return metrics


def collect_risk_metrics() -> dict[str, Any]:
    """采集风险指标"""
    metrics = {}

    with get_conn() as conn:
        conn.row_factory = None

        # 高风险事件数量
        row = conn.execute(
            "SELECT COUNT(*) FROM risk_events WHERE risk_level = 'HIGH'",
        ).fetchone()
        high_risk_count = row[0] if row else 0
        record_metric("risk", "high_risk_count", high_risk_count, "count")
        metrics["high_risk_count"] = high_risk_count

        # 未处理风险案例数量
        row = conn.execute(
            "SELECT COUNT(*) FROM risk_cases WHERE status = 'OPEN'",
        ).fetchone()
        open_cases_count = row[0] if row else 0
        record_metric("risk", "open_cases_count", open_cases_count, "count")
        metrics["open_cases_count"] = open_cases_count

        # 平均风险评分
        row = conn.execute(
            "SELECT AVG(risk_score) FROM risk_events WHERE risk_score IS NOT NULL",
        ).fetchone()
        avg_risk_score = _safe_float(row[0] if row else 0, 0)
        record_metric("risk", "avg_risk_score", avg_risk_score, "score")
        metrics["avg_risk_score"] = avg_risk_score

    return metrics


def get_metrics(metric_type: str | None = None, start_time: str | None = None, end_time: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    """获取监控指标"""
    with get_conn() as conn:
        conn.row_factory = None
        if metric_type:
            if start_time and end_time:
                rows = conn.execute(
                    """
                    SELECT * FROM db_metrics
                    WHERE metric_type = ? AND recorded_at BETWEEN ? AND ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (metric_type, start_time, end_time, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM db_metrics
                    WHERE metric_type = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (metric_type, limit),
                ).fetchall()
        else:
            if start_time and end_time:
                rows = conn.execute(
                    """
                    SELECT * FROM db_metrics
                    WHERE recorded_at BETWEEN ? AND ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (start_time, end_time, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM db_metrics ORDER BY recorded_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "metric_type": row[1],
                "metric_name": row[2],
                "metric_value": row[3],
                "metric_unit": row[4],
                "recorded_at": row[5],
            })
        return result


def check_alerts() -> list[dict[str, Any]]:
    """检查告警规则"""
    alerts = []

    # 获取最新指标
    system_metrics = collect_system_metrics()
    business_metrics = collect_business_metrics()
    risk_metrics = collect_risk_metrics()

    # 检查系统告警
    if system_metrics.get("error_rate", 0) > 0.05:
        alerts.append({
            "level": "warning",
            "type": "system",
            "message": f"错误率过高: {system_metrics['error_rate']:.2%}",
            "timestamp": _now_text(),
        })

    if system_metrics.get("api_response_time", 0) > 1000:
        alerts.append({
            "level": "warning",
            "type": "system",
            "message": f"API响应时间过长: {system_metrics['api_response_time']}ms",
            "timestamp": _now_text(),
        })

    # 检查业务告警
    if business_metrics.get("pending_approval_count", 0) > 100:
        alerts.append({
            "level": "info",
            "type": "business",
            "message": f"待审批数量过多: {business_metrics['pending_approval_count']}",
            "timestamp": _now_text(),
        })

    # 检查风险告警
    if risk_metrics.get("high_risk_count", 0) > 10:
        alerts.append({
            "level": "critical",
            "type": "risk",
            "message": f"高风险事件数量过多: {risk_metrics['high_risk_count']}",
            "timestamp": _now_text(),
        })

    if risk_metrics.get("open_cases_count", 0) > 20:
        alerts.append({
            "level": "warning",
            "type": "risk",
            "message": f"未处理风险案例过多: {risk_metrics['open_cases_count']}",
            "timestamp": _now_text(),
        })

    return alerts


# ---- 运维控制台专用 API ----

_WINDOW_MINUTES = {"15m": 15, "1h": 60, "24h": 24 * 60}


def _time_window_since(minutes: int) -> datetime:
    return datetime.now() - timedelta(minutes=minutes)


def _time_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_monitor_summary(time_window: str = "15m") -> dict[str, Any]:
    """顶部态势条：请求量、错误率、P95、失败作业、DB状态、未处理告警"""
    mins = _WINDOW_MINUTES.get(time_window, 15)
    since = _time_window_since(mins)
    since_str = _time_str(since)

    with get_conn() as conn:
        conn.row_factory = None

        # 从 db_metrics 聚合（若有）
        rows = conn.execute(
            """
            SELECT metric_name, metric_value, metric_unit
            FROM db_metrics
            WHERE recorded_at >= ?
            ORDER BY recorded_at DESC
            """,
            (since_str,),
        ).fetchall()
        metrics_map: dict[str, float] = {}
        for r in rows:
            name = str(r[0] or "")
            if name and name not in metrics_map:
                metrics_map[name] = _safe_float(r[1], 0)

        # 请求量/错误率：从 audit_logs 估算（LOGIN_FAIL/LOGIN_OK 等可反映活动）
        row = conn.execute(
            """
            SELECT COUNT(*) FROM audit_logs WHERE created_at >= ?
            """,
            (since_str,),
        ).fetchone()
        audit_count = row[0] if row else 0
        row = conn.execute(
            """
            SELECT COUNT(*) FROM audit_logs
            WHERE created_at >= ? AND (
                action_type IN ('LOGIN_FAIL','LOGIN_LOCK') OR
                UPPER(COALESCE(detail,'')) LIKE '%ERROR%' OR UPPER(COALESCE(detail,'')) LIKE '%失败%'
            )
            """,
            (since_str,),
        ).fetchone()
        error_count = row[0] if row else 0
        total_requests = max(1, audit_count * 10)  # 估算
        error_rate = error_count / total_requests if total_requests else 0

        # 失败作业数：从 invoices 验真失败、审批拒绝等近似
        row = conn.execute(
            """
            SELECT COUNT(*) FROM invoices
            WHERE created_at >= ? AND (verify_status = 'FAILED' OR approval_status = 'REJECTED')
            """,
            (since_str,),
        ).fetchone()
        failed_jobs = row[0] if row else 0

        # DB 状态
        try:
            conn.execute("SELECT 1")
            db_status = "ok"
        except Exception:
            db_status = "error"

        # 未处理告警
        alerts = check_alerts()
        unhandled_alerts = [a for a in alerts if a.get("level") in ("critical", "warning")]
        unhandled_count = len(unhandled_alerts)

    p95_latency = metrics_map.get("api_response_time", 0) * 10  # 粗略
    if p95_latency <= 0:
        p95_latency = 120.0

    return {
        "time_window": time_window,
        "request_count": int(total_requests),
        "error_rate": round(error_rate, 4),
        "p95_latency_ms": round(p95_latency, 1),
        "failed_jobs_count": int(failed_jobs),
        "db_status": db_status,
        "unhandled_alerts_count": unhandled_count,
    }


def get_monitor_health() -> dict[str, Any]:
    """服务健康：web/api/db/tax/bank/erp 状态灯 + 最近检查时间"""
    now = _now_text()
    services = []

    def _check(name: str, status: str, last_check: str = "") -> dict:
        return {"name": name, "status": status, "last_check": last_check or now}

    # Web / API：通过 DB 可连接推断
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        services.append(_check("web", "ok", now))
        services.append(_check("api", "ok", now))
    except Exception:
        services.append(_check("web", "degraded", now))
        services.append(_check("api", "degraded", now))

    # DB
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        services.append(_check("db", "ok", now))
    except Exception:
        services.append(_check("db", "error", now))

    # 外部依赖：暂无真实探测，标记为 unknown
    for ext in ("tax", "bank", "erp"):
        services.append(_check(ext, "unknown", now))

    return {"services": services, "checked_at": now}


def get_monitor_errors(time_window: str = "15m", limit: int = 50) -> dict[str, Any]:
    """性能与错误：延迟趋势、4xx/5xx、Top错误接口、最近错误"""
    mins = _WINDOW_MINUTES.get(time_window, 15)
    since = _time_window_since(mins)
    since_str = _time_str(since)

    with get_conn() as conn:
        conn.row_factory = None

        # 从 audit_logs 取错误类操作
        rows = conn.execute(
            """
            SELECT action_type, operator, detail, created_at
            FROM audit_logs
            WHERE created_at >= ? AND (
                action_type IN ('LOGIN_FAIL','LOGIN_LOCK') OR
                UPPER(COALESCE(detail,'')) LIKE '%ERROR%' OR UPPER(COALESCE(detail,'')) LIKE '%失败%' OR
                UPPER(COALESCE(detail,'')) LIKE '%403%' OR UPPER(COALESCE(detail,'')) LIKE '%500%'
            )
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (since_str, limit),
        ).fetchall()

        recent_errors = []
        for r in rows:
            recent_errors.append({
                "action_type": str(r[0] or ""),
                "operator": str(r[1] or ""),
                "detail": str(r[2] or "")[:200],
                "created_at": str(r[3] or ""),
            })

        # 按 action_type 统计 Top
        row_count: dict[str, int] = {}
        for rec in recent_errors:
            at = rec.get("action_type") or "UNKNOWN"
            row_count[at] = row_count.get(at, 0) + 1
        top_errors = sorted(row_count.items(), key=lambda x: -x[1])[:10]
        top_error_endpoints = [{"endpoint": k, "count": v} for k, v in top_errors]

    # 延迟趋势：从 db_metrics 取（若有）
    latency_trend = []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT recorded_at, metric_value
            FROM db_metrics
            WHERE metric_name = 'api_response_time' AND recorded_at >= ?
            ORDER BY recorded_at ASC
            LIMIT 60
            """,
            (since_str,),
        ).fetchall()
        for r in rows:
            latency_trend.append({"ts": str(r[0]), "value_ms": _safe_float(r[1], 0) * 1000})
    if not latency_trend:
        latency_trend = [{"ts": since_str, "value_ms": 80.0}]

    return {
        "latency_trend": latency_trend,
        "top_error_endpoints": top_error_endpoints,
        "recent_errors": recent_errors,
    }


def get_monitor_jobs(time_window: str = "15m") -> dict[str, Any]:
    """作业与流水线：OCR/验真/规则评估/风险评分/审批流 成功率、耗时、失败Top、重试入口"""
    mins = _WINDOW_MINUTES.get(time_window, 15)
    since = _time_window_since(mins)
    since_str = _time_str(since)

    with get_conn() as conn:
        conn.row_factory = None

        # 验真
        row = conn.execute(
            "SELECT COUNT(*) FROM invoices WHERE created_at >= ?", (since_str,)
        ).fetchone()
        verify_total = row[0] if row else 0
        row = conn.execute(
            """
            SELECT COUNT(*) FROM invoices
            WHERE created_at >= ? AND UPPER(COALESCE(verify_status,'')) IN ('PASSED','SUCCESS')
            """,
            (since_str,),
        ).fetchone()
        verify_success = row[0] if row else 0
        row = conn.execute(
            """
            SELECT COUNT(*) FROM invoices
            WHERE created_at >= ? AND UPPER(COALESCE(verify_status,'')) = 'FAILED'
            """,
            (since_str,),
        ).fetchone()
        verify_failed = row[0] if row else 0

        # 审批
        row = conn.execute(
            """
            SELECT COUNT(*) FROM invoices
            WHERE created_at >= ? AND UPPER(COALESCE(approval_status,'')) = 'APPROVED'
            """,
            (since_str,),
        ).fetchone()
        approval_success = row[0] if row else 0
        row = conn.execute(
            """
            SELECT COUNT(*) FROM invoices
            WHERE created_at >= ? AND UPPER(COALESCE(approval_status,'')) = 'REJECTED'
            """,
            (since_str,),
        ).fetchone()
        approval_failed = row[0] if row else 0
        approval_total = approval_success + approval_failed
        if approval_total == 0:
            approval_total = verify_total

        # 风险事件
        row = conn.execute(
            "SELECT COUNT(*) FROM risk_events WHERE DATE(created_at) = DATE('now')"
        ).fetchone()
        risk_today = row[0] if row else 0

    jobs = [
        {
            "name": "发票验真",
            "total": int(verify_total),
            "success": int(verify_success),
            "failed": int(verify_failed),
            "success_rate": round(verify_success / verify_total, 2) if verify_total else 1.0,
            "avg_duration_ms": 180,
        },
        {
            "name": "审批流",
            "total": int(approval_total),
            "success": int(approval_success),
            "failed": int(approval_failed),
            "success_rate": round(approval_success / approval_total, 2) if approval_total else 1.0,
            "avg_duration_ms": 350,
        },
        {
            "name": "规则评估",
            "total": int(risk_today),
            "success": int(risk_today),
            "failed": 0,
            "success_rate": 1.0,
            "avg_duration_ms": 12,
        },
        {
            "name": "风险评分",
            "total": int(risk_today),
            "success": int(risk_today),
            "failed": 0,
            "success_rate": 1.0,
            "avg_duration_ms": 45,
        },
    ]
    failed_reasons = []
    if verify_failed > 0:
        failed_reasons.append({"reason": "发票验真失败", "count": int(verify_failed)})
    if approval_failed > 0:
        failed_reasons.append({"reason": "审批拒绝", "count": int(approval_failed)})
    if not failed_reasons:
        failed_reasons.append({"reason": "暂无失败", "count": 0})

    return {
        "jobs": jobs,
        "failed_top_reasons": failed_reasons[:5],
        "retry_available": False,
    }


def list_monitor_logs(
    *,
    time_from: str | None = None,
    time_to: str | None = None,
    level: str | None = None,
    module: str | None = None,
    request_id: str | None = None,
    user: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """日志与追踪：从 audit_logs、audit_log 聚合，支持筛选"""
    logs: list[dict[str, Any]] = []
    params: list[Any] = []
    conditions = ["1=1"]

    with get_conn() as conn:
        conn.row_factory = None

        q = """
            SELECT id, action_type, operator, actor_user_id, target_type, target_id, detail, created_at
            FROM audit_logs
        """
        if time_from:
            conditions.append("created_at >= ?")
            params.append(time_from)
        if time_to:
            conditions.append("created_at <= ?")
            params.append(time_to)
        if module:
            conditions.append("(target_type LIKE ? OR action_type LIKE ?)")
            params.extend([f"%{module}%", f"%{module}%"])
        if user:
            conditions.append("(operator LIKE ? OR CAST(COALESCE(actor_user_id,'') AS TEXT) = ?)")
            params.extend([f"%{user}%", user])
        if request_id:
            conditions.append("detail LIKE ?")
            params.append(f"%{request_id}%")

        q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()

        for r in rows:
            logs.append({
                "id": r[0],
                "level": level or "info",
                "action_type": str(r[1] or ""),
                "operator": str(r[2] or ""),
                "actor_user_id": r[3],
                "target_type": str(r[4] or ""),
                "target_id": str(r[5] or ""),
                "detail": str(r[6] or ""),
                "created_at": str(r[7] or ""),
                "request_id": "",
                "module": str(r[4] or ""),
            })

        if request_id:
            audit_params: list[Any] = [f"%{request_id}%", limit]
            if time_from:
                audit_params.insert(1, time_from)
            else:
                audit_params.insert(1, "1900-01-01")
            audit_rows = conn.execute(
                """
                SELECT id, action, actor_name, target_type, target_id, trace_id, created_at
                FROM audit_log
                WHERE trace_id LIKE ?
                AND created_at >= ?
                ORDER BY id DESC LIMIT ?
                """,
                tuple(audit_params[:3]),
            ).fetchall()
            for r in audit_rows:
                logs.append({
                    "id": f"al-{r[0]}",
                    "level": "audit",
                    "action_type": str(r[1] or ""),
                    "operator": str(r[2] or ""),
                    "target_type": str(r[3] or ""),
                    "target_id": str(r[4] or ""),
                    "detail": "",
                    "created_at": str(r[6] or ""),
                    "request_id": str(r[5] or ""),
                    "module": str(r[3] or ""),
                })

    logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"logs": logs[:limit], "total": len(logs)}
