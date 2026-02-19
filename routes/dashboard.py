from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, render_template, request

from audit import MISSING_REASON_MESSAGE, write_audit_log
from events import event_bus
from events.types import (
    RISK_STAGE,
    STAGE_AI_EXPLAIN,
    STAGE_CASE_ASSIGNED,
    STAGE_CASE_CREATED,
    STAGE_RISK_EVENT_CREATED,
    risk_stage_category,
    risk_stage_message,
)
from routes.invoices import ensure_seed_attachment_file, run_invoice_ai_internal
from services.invoice_verification_service import verify_invoice_internal
from services.risk_case_service import (
    ConflictError,
    NotFoundError,
    ValidationError,
    assign_case,
    create_ai_risk_event_if_needed,
    create_case_from_event,
)
from services.risk_metrics_service import (
    _default_risk_metrics,
    _default_trends,
    get_department_risk_rank,
    get_recent_trends,
    get_risk_distribution,
    get_risk_metrics,
)
from tasks.jobs import pull_bank_incremental
from utils.db import (
    DATA_SCOPE_ALL,
    get_dashboard_data,
    get_dashboard_stats,
    get_system_settings,
    get_workflow_current_config,
    insert_audit_log,
    insert_invoice,
    list_invoices,
    list_workflow_versions,
    publish_workflow_config,
    save_system_settings,
    save_workflow_draft,
    rollback_workflow_config,
)
from utils.risk import evaluate_risk
from utils.security import (
    can_manage_workflow,
    current_data_scope,
    current_scope_department,
    current_user,
    has_permission,
    is_system_admin,
    login_required,
    owner_scope_identity_values,
    owner_scope_user_id,
    require_permission,
)

bp = Blueprint("dashboard", __name__)

WORKFLOW_REASON_CODES = {
    "POLICY_MATCH",
    "POLICY_EXCEPTION",
    "NEED_MORE_INFO",
    "DUPLICATE_SUSPECT",
    "MANUAL_OVERRIDE",
}


def _safe_text(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _safe_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _operator_name() -> str:
    user = current_user() or {}
    return (
        _safe_text(user.get("employee_name"), "")
        or _safe_text(user.get("username"), "")
        or _safe_text(user.get("employee_no"), "")
        or "system"
    )


def _operator_user_id() -> int | None:
    user = current_user() or {}
    user_id = _safe_int(user.get("id"), 0)
    return user_id if user_id > 0 else None


def _invoice_scope_filters(user: dict[str, Any] | None = None) -> dict[str, Any]:
    target = user if user is not None else (current_user() or {})
    return {
        "owner_user_id": owner_scope_user_id(target),
        "owner_identity_values": owner_scope_identity_values(target),
    }


def _workflow_payload() -> tuple[dict[str, Any], tuple[Any, int] | None]:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return {}, (jsonify({"ok": False, "msg": "request body must be a JSON object"}), 400)
    return payload, None


def _require_workflow_reason_code(payload: dict[str, Any]) -> tuple[str, tuple[Any, int] | None]:
    reason_code = _safe_text(payload.get("change_reason_code"), "").upper()
    if not reason_code:
        return "", (jsonify({"ok": False, "msg": MISSING_REASON_MESSAGE}), 400)
    if reason_code not in WORKFLOW_REASON_CODES:
        return "", (jsonify({"ok": False, "msg": "invalid change_reason_code"}), 400)
    return reason_code, None


def _workflow_reason_text(reason_code: str, note: str) -> str:
    trimmed_note = _safe_text(note, "")
    return f"{reason_code}: {trimmed_note}" if trimmed_note else reason_code


def _workflow_audit_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": _safe_int(record.get("version"), 0),
        "status": _safe_text(record.get("status")),
        "scope": _safe_text(record.get("scope")),
        "by": _safe_text(record.get("by")),
        "at": _safe_text(record.get("at")),
        "nodes_summary": record.get("nodes_summary") or {},
    }


def _publish_demo_stage(
    stage: str,
    *,
    trace_id: str = "",
    related_ids: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    normalized_stage = _safe_text(stage).upper()
    payload: dict[str, Any] = {
        "stage": normalized_stage,
        "event_type": normalized_stage,
        "message": risk_stage_message(normalized_stage),
        "category": risk_stage_category(normalized_stage),
        "trace_id": _safe_text(trace_id),
        "related_ids": dict(related_ids or {}),
    }
    if extra:
        payload.update(dict(extra))
    event_bus.publish(RISK_STAGE, payload)


def _record_demo_audit_log(*, action_type: str, detail: str, target_type: str = "", target_id: int | None = None) -> None:
    try:
        insert_audit_log(
            action_type=action_type,
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    except Exception:
        return


def _profile_dataset() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    user = current_user() or {}
    username = _safe_text(user.get("username"), "user")
    employee_name = _safe_text(user.get("employee_name"), username)
    employee_no = _safe_text(user.get("employee_no"), "-")
    department = _safe_text(user.get("department"), "-")
    role = _safe_text(user.get("role"), "staff")

    invoices = list_invoices(
        limit=5000,
        department=current_scope_department(user),
        **_invoice_scope_filters(user),
    )
    own_rows = [
        row
        for row in invoices
        if _safe_text(row.get("submitter_no"), "") == employee_no
        or _safe_text(row.get("submitter_name"), "") == employee_name
    ]
    if not own_rows:
        own_rows = [row for row in invoices if _safe_text(row.get("department"), "") == department]

    month_prefix = datetime.now().strftime("%Y-%m")
    month_approvals = sum(1 for row in own_rows if _safe_text(row.get("created_at"), "").startswith(month_prefix))
    risk_interventions = sum(
        1
        for row in own_rows
        if _safe_text(row.get("risk_level"), "").upper() in {"HIGH", "MEDIUM"}
        or _safe_text(row.get("status"), "").upper() == "REJECTED"
    )
    approved_count = sum(1 for row in own_rows if _safe_text(row.get("status"), "").upper() == "APPROVED")
    auto_pass_rate = f"{round((approved_count * 100.0 / len(own_rows)), 1)}%" if own_rows else "0%"

    dept_member_ids = {
        _safe_text(row.get("submitter_no"), "")
        for row in invoices
        if _safe_text(row.get("submitter_department"), "") == department and _safe_text(row.get("submitter_no"), "")
    }
    team_size = max(1, len(dept_member_ids))

    now = datetime.now()
    logins = [
        {
            "time": (now - timedelta(minutes=8)).strftime("%Y-%m-%d %H:%M"),
            "device": "Windows / Edge",
            "ip": "127.0.0.1",
            "location": "Guangzhou",
        },
        {
            "time": (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"),
            "device": "Windows / Chrome",
            "ip": "127.0.0.1",
            "location": "Guangzhou",
        },
        {
            "time": (now - timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M"),
            "device": "Windows / Edge",
            "ip": "127.0.0.1",
            "location": "Guangzhou",
        },
    ]

    profile = {
        "name": employee_name,
        "role": role,
        "department": department,
        "employee_id": employee_no,
        "email": _safe_text(user.get("email")) or f"{username}@deepaudit.local",
        "phone": _safe_text(user.get("phone")) or "",
        "location": "Guangzhou",
        "last_login": logins[0]["time"],
    }
    metrics = {
        "month_approvals": month_approvals,
        "risk_interventions": risk_interventions,
        "auto_pass_rate": auto_pass_rate,
        "team_size": team_size,
    }
    return profile, metrics, logins


def _has_any_permission(permission_keys: list[str]) -> bool:
    user = current_user() or {}
    for key in permission_keys:
        if has_permission(str(key), user=user):
            return True
    return False


def _forbidden_page(*, module_name: str, required_permissions: list[str]):
    return (
        render_template(
            "forbidden.html",
            module_name=module_name,
            required_permissions=required_permissions,
        ),
        403,
    )


@bp.get("/dashboard")
@login_required
def dashboard_page():
    try:
        if not has_permission("VIEW_DASHBOARD", current_user() or {}):
            return _forbidden_page(module_name="管理总览", required_permissions=["VIEW_DASHBOARD"])
    except Exception:
        return _forbidden_page(module_name="管理总览", required_permissions=["VIEW_DASHBOARD"])
    return render_template("dashboard.html")


@bp.get("/api/dashboard/data")
@login_required
def dashboard_data():
    range_key = str(request.args.get("range") or "7d")
    return jsonify(get_dashboard_data(range_key, department=current_scope_department()))


@bp.get("/api/dashboard/stats")
@login_required
def dashboard_stats():
    range_key = str(request.args.get("range") or "30d")
    return jsonify({"ok": True, "data": get_dashboard_stats(range_key, department=current_scope_department())})


def _dashboard_range_to_dates(range_key: str) -> tuple[date | None, date | None]:
    """Parse range (today|yesterday|7d|30d) to (date_from, date_to). Default 7d."""
    today = date.today()
    r = (str(range_key or "7d").strip().lower())
    if r == "today":
        return today, today
    if r == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if r == "30d":
        return today - timedelta(days=29), today
    # 7d or invalid
    return today - timedelta(days=6), today


def _dashboard_range_to_trends_params(range_key: str) -> tuple[int, date]:
    """Parse range to (days, end_date) for get_recent_trends."""
    today = date.today()
    r = (str(range_key or "7d").strip().lower())
    if r == "today":
        return 1, today
    if r == "yesterday":
        return 1, today - timedelta(days=1)
    if r == "30d":
        return 30, today
    return 7, today


@bp.get("/api/dashboard/metrics")
@login_required
def dashboard_metrics():
    range_key = request.args.get("range", "7d")
    try:
        date_from, date_to = _dashboard_range_to_dates(range_key)
        department_scope = current_scope_department()
        data = get_risk_metrics(
            department_scope=department_scope,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        current_app.logger.exception("dashboard_metrics: %s", exc)
        data = _default_risk_metrics()
    return jsonify({"ok": True, "data": data})


@bp.get("/api/dashboard/risk_distribution")
@login_required
def dashboard_risk_distribution():
    range_key = request.args.get("range", "7d")
    try:
        date_from, date_to = _dashboard_range_to_dates(range_key)
        data = get_risk_distribution(
            department_scope=current_scope_department(),
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        current_app.logger.exception("dashboard_risk_distribution: %s", exc)
        data = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    return jsonify({"ok": True, "data": data})


@bp.get("/api/dashboard/risk_trends")
@login_required
def dashboard_risk_trends():
    range_key = request.args.get("range", "7d")
    try:
        days, end_date = _dashboard_range_to_trends_params(range_key)
        data = get_recent_trends(
            days=days,
            end_date=end_date,
            department_scope=current_scope_department(),
        )
    except Exception as exc:
        current_app.logger.exception("dashboard_risk_trends: %s", exc)
        data = _default_trends(days=7, end_date=date.today())
    return jsonify({"ok": True, "data": data})


@bp.get("/api/dashboard/department_risk_rank")
@login_required
def dashboard_department_risk_rank():
    if current_data_scope() != DATA_SCOPE_ALL:
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403

    raw_limit = request.args.get("limit", "10")
    try:
        limit = int(raw_limit)
    except Exception:
        limit = 10
    limit = max(1, min(limit, 50))

    return jsonify(
        {
            "ok": True,
            "data": get_department_risk_rank(limit=limit),
        }
    )


@bp.get("/profile")
@login_required
def profile_page():
    profile, metrics, logins = _profile_dataset()
    return render_template("profile.html", profile=profile, metrics=metrics, logins=logins)


@bp.get("/settings")
@login_required
def settings_page():
    required_permissions = ["MANAGE_SETTINGS", "MANAGE_SYSTEM"]
    if not _has_any_permission(required_permissions):
        return _forbidden_page(module_name="系统参数", required_permissions=required_permissions)
    return render_template("settings.html")


@bp.get("/api/settings")
@login_required
def settings_api_get():
    if not _has_any_permission(["MANAGE_SETTINGS", "MANAGE_SYSTEM"]):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    return jsonify({"ok": True, "settings": get_system_settings()})


@bp.post("/api/settings")
@login_required
@require_permission("MANAGE_SETTINGS")
def settings_api_post():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "msg": "invalid payload"}), 400

    try:
        saved = save_system_settings(payload)
    except Exception as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 500

    try:
        insert_audit_log(
            action_type="SETTINGS_UPDATE",
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type="system_settings",
            detail=f"updated_keys={list(payload.keys())[:50]}",
        )
    except Exception:
        pass
    return jsonify({"ok": True, "settings": saved})


@bp.get("/api/settings/overview")
@login_required
def settings_overview_api():
    """获取设置概览：状态、指标、风险提示、最近变更"""
    if not _has_any_permission(["MANAGE_SETTINGS", "MANAGE_SYSTEM"]):
        return jsonify({"ok": False, "msg": "无权访问该资源"}), 403

    try:
        from utils.db import (
            get_conn,
            get_system_settings,
            list_roles_with_permissions,
            list_departments,
            list_governance_rules,
        )

        settings = get_system_settings()
        roles = list_roles_with_permissions()
        departments = list_departments(limit=5000)
        rules = list_governance_rules()

        # 计算配置进度（与模块状态一致）
        # 先计算各模块状态
        org_status = "已生效"
        if not settings.get("org", {}).get("role_based_access"):
            org_status = "未配置"
        elif len(roles) == 0 or len(departments) == 0:
            org_status = "待完善"

        risk_status = "已生效"
        risk_settings = settings.get("risk", {})
        if not risk_settings.get("amount_warning_threshold") or risk_settings.get("amount_warning_threshold", 0) == 0:
            risk_status = "未配置"
        elif not risk_settings.get("sensitive_words") or len(risk_settings.get("sensitive_words", [])) == 0:
            risk_status = "待完善"

        integration_status = "已生效"
        integration_settings = settings.get("integration", {})
        if not integration_settings.get("email_enabled") and not integration_settings.get("wecom_enabled"):
            integration_status = "未配置"
        elif not integration_settings.get("webhook_url"):
            integration_status = "待完善"

        # 基于状态计算进度（已生效=1，待完善=0.5，未配置=0）
        total_configs = 3
        configured_count = 0.0
        if org_status == "已生效":
            configured_count += 1.0
        elif org_status == "待完善":
            configured_count += 0.5
        if risk_status == "已生效":
            configured_count += 1.0
        elif risk_status == "待完善":
            configured_count += 0.5
        if integration_status == "已生效":
            configured_count += 1.0
        elif integration_status == "待完善":
            configured_count += 0.5

        # 高风险未配置提示（最多3条）
        risk_warnings = []
        risk_settings = settings.get("risk", {})
        if not risk_settings.get("amount_warning_threshold") or risk_settings.get("amount_warning_threshold", 0) == 0:
            risk_warnings.append("未配置单笔报销预警线")
        if not risk_settings.get("sensitive_words") or len(risk_settings.get("sensitive_words", [])) == 0:
            risk_warnings.append("未配置敏感词库")
        if not risk_settings.get("block_duplicate"):
            risk_warnings.append("未启用重复报销拦截")
        risk_warnings = risk_warnings[:3]

        # 最近一次设置变更（从audit_log获取）
        recent_change = None
        try:
            # 从audit_logs表获取SETTINGS_UPDATE类型的日志
            with get_conn() as conn:
                # 先尝试从audit_logs表查询
                row = conn.execute(
                    """
                    SELECT created_at, operator, action_type
                    FROM audit_logs
                    WHERE action_type LIKE '%SETTINGS%'
                    ORDER BY datetime(created_at) DESC, id DESC
                    LIMIT 1
                    """,
                ).fetchone()
                if not row:
                    # 如果audit_logs表没有，尝试从audit_log表查询
                    row = conn.execute(
                        """
                        SELECT created_at, actor_name, action
                        FROM audit_log
                        WHERE target_type = 'system_settings' OR action LIKE '%SETTINGS%'
                        ORDER BY datetime(created_at) DESC, id DESC
                        LIMIT 1
                        """,
                    ).fetchone()
                    if row:
                        recent_change = {
                            "time": str(row["created_at"] or ""),
                            "operator": str(row["actor_name"] or "系统"),
                            "action": str(row["action"] or "SETTINGS_UPDATE"),
                        }
                else:
                    recent_change = {
                        "time": str(row["created_at"] or ""),
                        "operator": str(row["operator"] or "系统"),
                        "action": str(row["action_type"] or "SETTINGS_UPDATE"),
                    }
        except Exception:
            pass

        # 组织与权限指标和风险级别/影响范围
        role_count = len(roles)
        dept_count = len([d for d in departments if d.get("status") == "ACTIVE"])
        data_scope_coverage = 0.0
        if role_count > 0:
            # 计算有数据范围策略的角色数（scope_type不是DEPT，或有dept_ids配置）
            roles_with_scope = 0
            for r in roles:
                scope_type = str(r.get("scope_type") or "").strip().upper()
                dept_ids = r.get("dept_ids", [])
                if isinstance(dept_ids, str):
                    try:
                        dept_ids = json.loads(dept_ids) if dept_ids else []
                    except Exception:
                        dept_ids = []
                if scope_type and scope_type != "DEPT" and scope_type != "":
                    roles_with_scope += 1
                elif isinstance(dept_ids, list) and len(dept_ids) > 0:
                    roles_with_scope += 1
            data_scope_coverage = round(roles_with_scope / role_count * 100, 1)

        # 组织与权限风险级别和影响范围
        org_risk_level = "低"
        org_impact_scope = "部门级"
        if org_status == "未配置":
            org_risk_level = "高"
            org_impact_scope = "全系统"
        elif org_status == "待完善":
            org_risk_level = "中"
            org_impact_scope = "部门级"
        else:
            if data_scope_coverage < 50:
                org_risk_level = "中"
            org_impact_scope = "全系统" if settings.get("org", {}).get("cross_department_visibility") else "部门级"

        # 风控策略指标和风险级别/影响范围
        enabled_rules_count = len([r for r in rules if r.get("enabled", 0) == 1])
        latest_rule_update = None
        if rules:
            latest_rule = max(rules, key=lambda x: x.get("updated_at", "") or "")
            latest_rule_update = latest_rule.get("updated_at", "")

        # 风控策略风险级别和影响范围
        risk_risk_level = "低"
        risk_impact_scope = "财务风险"
        if risk_status == "未配置":
            risk_risk_level = "高"
            risk_impact_scope = "财务风险、合规风险"
        elif risk_status == "待完善":
            risk_risk_level = "中"
            risk_impact_scope = "财务风险"
        else:
            # 根据启用的规则数量和类型判断风险级别
            high_severity_rules = len([r for r in rules if r.get("enabled", 0) == 1 and str(r.get("severity", "")).upper() == "HIGH"])
            if high_severity_rules == 0:
                risk_risk_level = "中"
            risk_impact_scope = "财务风险" if enabled_rules_count > 0 else "无影响"

        # 通知与集成指标和风险级别/影响范围
        integration_settings = settings.get("integration", {})

        email_status = "已启用" if integration_settings.get("email_enabled") else "未启用"
        wecom_status = "已启用" if integration_settings.get("wecom_enabled") else "未启用"
        webhook_status = "已配置" if integration_settings.get("webhook_url") else "未配置"
        last_test_result = "未测试"  # TODO: 从实际测试记录获取

        # 通知与集成风险级别和影响范围
        integration_risk_level = "低"
        integration_impact_scope = "通知延迟"
        if integration_status == "未配置":
            integration_risk_level = "中"
            integration_impact_scope = "通知失效、审批延迟"
        elif integration_status == "待完善":
            integration_risk_level = "低"
            integration_impact_scope = "部分通知失效"
        else:
            integration_impact_scope = "正常通知"

        return jsonify({
            "ok": True,
            "overview": {
                "progress": {
                    "configured": configured_count,
                    "total": total_configs,
                    "percentage": round(configured_count / total_configs * 100, 1) if total_configs > 0 else 0,
                    "display_text": f"{int(configured_count)}/{total_configs}",
                },
                "risk_warnings": risk_warnings,
                "recent_change": recent_change,
                "org": {
                    "status": org_status,
                    "risk_level": org_risk_level,
                    "impact_scope": org_impact_scope,
                    "role_count": role_count,
                    "dept_count": dept_count,
                    "data_scope_coverage": data_scope_coverage,
                },
                "risk": {
                    "status": risk_status,
                    "risk_level": risk_risk_level,
                    "impact_scope": risk_impact_scope,
                    "enabled_rules_count": enabled_rules_count,
                    "latest_update": latest_rule_update,
                },
                "integration": {
                    "status": integration_status,
                    "risk_level": integration_risk_level,
                    "impact_scope": integration_impact_scope,
                    "email_status": email_status,
                    "wecom_status": wecom_status,
                    "webhook_status": webhook_status,
                    "last_test_result": last_test_result,
                },
            },
        })
    except Exception as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 500


@bp.get("/upload")
@login_required
def upload_page():
    if not has_permission("VIEW_INVOICES", current_user() or {}):
        return _forbidden_page(module_name="费用报销受理", required_permissions=["VIEW_INVOICES"])
    return render_template("upload.html")


@bp.get("/workflow")
@login_required
def workflow_page():
    if not can_manage_workflow(current_user()):
        return _forbidden_page(module_name="审批流程管理", required_permissions=[])
    return render_template("workflow.html")


@bp.get("/api/workflow/current")
@login_required
def workflow_current_api():
    if not can_manage_workflow(current_user()):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    current = get_workflow_current_config()
    return jsonify(
        {
            "ok": True,
            "current": current,
            "reason_code_options": sorted(WORKFLOW_REASON_CODES),
        }
    )


@bp.post("/api/workflow/draft")
@login_required
@require_permission("MANAGE_SETTINGS")
def workflow_draft_api():
    if not can_manage_workflow(current_user()):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    payload, err = _workflow_payload()
    if err is not None:
        return err

    current = get_workflow_current_config()
    config = payload.get("config")
    if not isinstance(config, dict):
        config = current.get("config") if isinstance(current.get("config"), dict) else {}

    draft = save_workflow_draft(
        config=config,
        scope=_safe_text(payload.get("scope"), current.get("scope") or "ALL"),
        reason=_safe_text(payload.get("change_reason_note"), ""),
        operator=_operator_name(),
    )

    try:
        insert_audit_log(
            action_type="WORKFLOW_DRAFT_SAVE",
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type="workflow",
            target_id=_safe_int(draft.get("version"), 0) or None,
            detail=f"version={_safe_int(draft.get('version'), 0)}; scope={_safe_text(draft.get('scope'))}",
        )
    except Exception:
        pass

    return jsonify({"ok": True, "draft": draft, "current": current})


@bp.post("/api/workflow/publish")
@login_required
@require_permission("MANAGE_SETTINGS")
def workflow_publish_api():
    if not can_manage_workflow(current_user()):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    payload, err = _workflow_payload()
    if err is not None:
        return err

    reason_code, reason_err = _require_workflow_reason_code(payload)
    if reason_err is not None:
        return reason_err

    trace_id = _safe_text(payload.get("trace_id"), "")
    note = _safe_text(payload.get("change_reason_note"), "")
    before = get_workflow_current_config()
    config = payload.get("config")
    published = publish_workflow_config(
        config=config if isinstance(config, dict) else None,
        scope=_safe_text(payload.get("scope"), before.get("scope") or "ALL"),
        reason=_workflow_reason_text(reason_code, note),
        operator=_operator_name(),
    )

    try:
        write_audit_log(
            action="WORKFLOW_PUBLISH",
            target_type="workflow",
            target_id=str(_safe_int(published.get("version"), 0)),
            before_obj=_workflow_audit_snapshot(before),
            after_obj=_workflow_audit_snapshot(published),
            change_reason_code=reason_code,
            trace_id=trace_id,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400
    except Exception:
        current_app.logger.exception("workflow publish audit failed")

    return jsonify({"ok": True, "current": published})


@bp.get("/api/workflow/versions")
@login_required
def workflow_versions_api():
    if not can_manage_workflow(current_user()):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    limit = _safe_int(request.args.get("limit"), 30)
    include_config = _safe_bool(request.args.get("include_config"))
    versions = list_workflow_versions(limit=limit, include_config=include_config)
    return jsonify({"ok": True, "versions": versions})


@bp.post("/api/workflow/rollback")
@login_required
@require_permission("MANAGE_SETTINGS")
def workflow_rollback_api():
    if not can_manage_workflow(current_user()):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    payload, err = _workflow_payload()
    if err is not None:
        return err

    reason_code, reason_err = _require_workflow_reason_code(payload)
    if reason_err is not None:
        return reason_err

    target_version = _safe_int(payload.get("target_version"), 0)
    if target_version <= 0:
        return jsonify({"ok": False, "msg": "target_version is required"}), 400

    trace_id = _safe_text(payload.get("trace_id"), "")
    note = _safe_text(payload.get("change_reason_note"), "")
    before = get_workflow_current_config()
    rolled = rollback_workflow_config(
        target_version=target_version,
        reason=_workflow_reason_text(reason_code, note),
        operator=_operator_name(),
    )
    if not isinstance(rolled, dict):
        return jsonify({"ok": False, "msg": "target version not found"}), 404

    try:
        write_audit_log(
            action="WORKFLOW_ROLLBACK",
            target_type="workflow",
            target_id=str(_safe_int(rolled.get("version"), 0)),
            before_obj=_workflow_audit_snapshot(before),
            after_obj=_workflow_audit_snapshot(rolled),
            change_reason_code=reason_code,
            trace_id=trace_id,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400
    except Exception:
        current_app.logger.exception("workflow rollback audit failed")

    return jsonify({"ok": True, "current": rolled})


@bp.post("/api/demo/run")
@login_required
@require_permission("VIEW_DASHBOARD")
def demo_run_api():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "msg": "request body must be a JSON object"}), 400

    requested_count = _safe_int(payload.get("count"), 3)
    invoice_count = max(1, min(requested_count, 3))
    include_bank_pull = _safe_bool(payload.get("include_bank_pull"))

    me = current_user() or {}
    applicant = (
        _safe_text(me.get("employee_name"))
        or _safe_text(me.get("username"))
        or "运营管理专员"
    )
    department = _safe_text(me.get("department"), "-")
    submitter_no = _safe_text(me.get("employee_no"), "-")
    department_scope = current_scope_department()
    assigned_to = applicant or _safe_text(me.get("username"), "运营管理专员")
    today = datetime.now().strftime("%Y-%m-%d")

    seed_rows = [
        {
            "amount": "1680.00",
            "merchant": "华穗会展商务酒店",
            "category": "差旅住宿",
            "scenario": "DEMO_HIGH_RISK",
            "currency": "CNY",
            "is_canton_fair": False,
            "hotel_limit": 600,
            "invoice_number": "INV-TAX-0004",
        },
        {
            "amount": "520.00",
            "merchant": "粤商接待中心",
            "category": "商务招待",
            "scenario": "DEMO_MEDIUM_RISK",
            "currency": "CNY",
            "is_canton_fair": False,
            "hotel_limit": 600,
            "invoice_number": "INV-TAX-0003",
        },
        {
            "amount": "180.00",
            "merchant": "合规办公采购中心",
            "category": "办公用品",
            "scenario": "DEMO_LOW_RISK",
            "currency": "CNY",
            "is_canton_fair": False,
            "hotel_limit": 600,
            "invoice_number": "INV-TAX-0001",
        },
    ]

    selected_rows = [deepcopy(seed_rows[idx]) for idx in range(invoice_count)]
    invoice_ids: list[int] = []
    event_ids: list[int] = []
    case_ids: list[int] = []
    trace_ids: list[str] = []
    bank_pull_snapshot: dict[str, Any] | None = None

    if include_bank_pull:
        try:
            bank_pull_snapshot = pull_bank_incremental(
                run_mode="demo",
                limit=20,
                persist_cursor=True,
            )
        except Exception as exc:
            current_app.logger.exception("action=demo_run bank_pull_once_failed err=%s", exc)
            bank_pull_snapshot = {
                "ok": False,
                "status": "provider_error",
                "run_mode": "demo",
                "message": str(exc),
                "imported": 0,
                "saved": 0,
                "skipped": 0,
                "matched": 0,
                "next_cursor": None,
            }

    # Demo pipeline: AI explain -> risk event -> case -> assign (publishes RISK_STAGE events).
    for row in selected_rows:
        risk_eval = evaluate_risk(
            amount_str=row.get("amount"),
            invoice_date=today,
            hotel_limit=row.get("hotel_limit"),
            is_canton_fair=_safe_bool(row.get("is_canton_fair")),
            currency=_safe_text(row.get("currency"), "CNY"),
            manual_rate=None,
            manual_cny_amount=None,
        )

        raw_payload = {
            "mode": "ops_seed",
            "seed_source": "ONE_CLICK_IMPORT",
            "seed_label": row.get("scenario"),
            "manual_entry": {
                "seller_name": row.get("merchant"),
                "expense_category": row.get("category"),
                "invoice_number": _safe_text(row.get("invoice_number")),
            },
            "mock_meta": {
                "merchant": row.get("merchant"),
                "scenario": row.get("scenario"),
                "currency": row.get("currency"),
            },
        }
        seed_filename = f"ops_seed_{uuid4().hex[:8]}.pdf"
        ensure_seed_attachment_file(seed_filename)
        invoice_id = insert_invoice(
            {
                "filename": seed_filename,
                "amount": row.get("amount"),
                "invoice_date": today,
                "applicant": applicant,
                "department": department,
                "is_canton_fair": bool(row.get("is_canton_fair")),
                "hotel_limit": _safe_int(row.get("hotel_limit"), 600),
                "mode": "ops_seed",
                "source": "enterprise_seed",
                "raw_json": raw_payload,
                "risk_level": _safe_text(risk_eval.get("level"), "MEDIUM"),
                "risk_reason": _safe_text(risk_eval.get("reason"), "规则引擎判定"),
                "currency": _safe_text(row.get("currency"), "CNY"),
                "fx_flag": bool(risk_eval.get("fx_flag")),
                "fx_reason": _safe_text(risk_eval.get("fx_reason")),
                "manual_rate": None,
                "manual_cny_amount": None,
                "ai_risk_level": _safe_text(risk_eval.get("level"), "MEDIUM"),
                "ai_analysis_reason": _safe_text(risk_eval.get("reason"), "规则引擎判定"),
                "status": "PENDING",
                "record_state": "LEDGER",
                "submitted_by_user_id": me.get("id"),
                "submitter_department": department,
                "submitter_name": applicant,
                "submitter_no": submitter_no,
            }
        )
        invoice_ids.append(int(invoice_id))
        _record_demo_audit_log(
            action_type="DEMO_INVOICE_SEEDED",
            target_type="invoice",
            target_id=int(invoice_id),
            detail=(
                f"invoice_id={int(invoice_id)}; "
                f"scenario={_safe_text(row.get('scenario'))}; "
                f"amount={_safe_text(row.get('amount'))}; "
                "source=demo_run"
            ),
        )

        verify_payload, verify_status = verify_invoice_internal(
            invoice_id,
            publish_event=True,
            idempotency_key=f"demo_run:{uuid4()}",
        )
        if verify_status >= 400 or not bool(verify_payload.get("ok")):
            msg = _safe_text(
                verify_payload.get("msg")
                or verify_payload.get("message")
                or "发票验真失败",
                "发票验真失败",
            )
            return jsonify({"ok": False, "msg": msg}), verify_status if verify_status >= 400 else 500

        ai_payload, _, status_code = run_invoice_ai_internal(
            invoice_id,
            publish_events=False,
            create_risk_event=False,
            tax_result_override=verify_payload.get("tax_result") if isinstance(verify_payload, dict) else None,
        )
        if status_code >= 400 or str(ai_payload.get("status")) != "success":
            msg = _safe_text(ai_payload.get("message") or ai_payload.get("msg") or "AI解释失败", "AI解释失败")
            return jsonify({"ok": False, "msg": msg}), 500 if status_code < 400 else status_code

        ai_data = ai_payload.get("data") if isinstance(ai_payload.get("data"), dict) else {}
        risk_level = _safe_text(ai_data.get("risk_level"), "MEDIUM").upper()
        risk_score = _safe_int(ai_data.get("risk_score"), 0)
        trace_id = _safe_text(ai_data.get("trace_id"))
        if trace_id:
            trace_ids.append(trace_id)

        _publish_demo_stage(
            STAGE_AI_EXPLAIN,
            trace_id=trace_id,
            related_ids={"invoice_id": int(invoice_id)},
            extra={
                "invoice_id": int(invoice_id),
                "risk_level": risk_level,
                "risk_score": risk_score,
            },
        )

        try:
            risk_event = create_ai_risk_event_if_needed(invoice_id=invoice_id, ai_data=ai_data)
        except Exception as exc:
            risk_event = None
            current_app.logger.warning("action=create_risk_event invoice_id=%s err=%s", invoice_id, exc)

        if isinstance(risk_event, dict) and _safe_int(risk_event.get("id"), 0) > 0:
            event_id = _safe_int(risk_event.get("id"), 0)
            event_ids.append(event_id)
            _record_demo_audit_log(
                action_type="DEMO_RISK_EVENT_CREATED",
                target_type="risk_event",
                target_id=event_id,
                detail=(
                    f"event_id={event_id}; "
                    f"invoice_id={int(invoice_id)}; "
                    f"risk_level={_safe_text(risk_event.get('risk_level')).upper()}; "
                    "source=demo_run"
                ),
            )
            _publish_demo_stage(
                STAGE_RISK_EVENT_CREATED,
                trace_id=_safe_text(risk_event.get("trace_id")) or trace_id,
                related_ids={
                    "invoice_id": int(invoice_id),
                    "event_id": event_id,
                },
                extra={
                    "event_id": event_id,
                    "invoice_id": int(invoice_id),
                    "risk_level": _safe_text(risk_event.get("risk_level")).upper(),
                    "risk_score": _safe_int(risk_event.get("risk_score"), 0),
                },
            )

            try:
                case_row = create_case_from_event(
                    event_id=event_id,
                    operator=_operator_name(),
                    action_note="demo_run_auto_case",
                    department_scope=department_scope,
                )
            except (ValidationError, NotFoundError, ConflictError):
                case_row = None

            if isinstance(case_row, dict) and _safe_int(case_row.get("id"), 0) > 0:
                case_id = _safe_int(case_row.get("id"), 0)
                case_ids.append(case_id)
                _record_demo_audit_log(
                    action_type="CASE_CREATED",
                    target_type="risk_case",
                    target_id=case_id,
                    detail=(
                        f"case_id={case_id}; "
                        f"event_id={event_id}; "
                        f"invoice_id={int(invoice_id)}; source=demo_run"
                    ),
                )
                _publish_demo_stage(
                    STAGE_CASE_CREATED,
                    trace_id=trace_id,
                    related_ids={
                        "invoice_id": int(invoice_id),
                        "event_id": event_id,
                        "case_id": case_id,
                    },
                    extra={
                        "case_id": case_id,
                        "event_id": event_id,
                        "invoice_id": int(invoice_id),
                        "status": _safe_text(case_row.get("status"), "OPEN").upper(),
                        "operator": _operator_name(),
                    },
                )
                try:
                    assigned_case = assign_case(
                        case_id=case_id,
                        assigned_to=assigned_to,
                        operator=_operator_name(),
                        action_note="demo_run_auto_assign",
                        department_scope=department_scope,
                    )
                except (ValidationError, NotFoundError, ConflictError):
                    assigned_case = None

                if isinstance(assigned_case, dict):
                    _record_demo_audit_log(
                        action_type="CASE_ASSIGNED",
                        target_type="risk_case",
                        target_id=case_id,
                        detail=(
                            f"case_id={case_id}; "
                            f"assigned_to={_safe_text(assigned_case.get('assigned_to'), assigned_to)}; "
                            "source=demo_run"
                        ),
                    )
                    _publish_demo_stage(
                        STAGE_CASE_ASSIGNED,
                        trace_id=trace_id,
                        related_ids={
                            "invoice_id": int(invoice_id),
                            "event_id": event_id,
                            "case_id": case_id,
                        },
                        extra={
                            "case_id": case_id,
                            "event_id": event_id,
                            "invoice_id": int(invoice_id),
                            "assigned_to": _safe_text(assigned_case.get("assigned_to"), assigned_to),
                            "status": _safe_text(assigned_case.get("status"), "ASSIGNED").upper(),
                            "operator": _operator_name(),
                        },
                    )

    _record_demo_audit_log(
        action_type="DEMO_RUN",
        target_type="demo",
        detail=(
            f"invoice_count={len(invoice_ids)}; "
            f"user={_operator_name()}; "
            f"department={department}; "
            f"ids={invoice_ids}"
        ),
    )
    return jsonify(
        {
            "ok": True,
            "data": {
                "invoice_ids": invoice_ids,
                "event_ids": event_ids,
                "case_ids": case_ids,
                "trace_ids": trace_ids,
                "bank_pull": bank_pull_snapshot,
            },
        }
    )


@bp.get("/dashboard/health")
def health():
    return jsonify({"ok": True, "module": "dashboard"})


@bp.get("/api/dashboard/debug_scope")
@login_required
def dashboard_debug_scope():
    """临时调试：返回当前用户权限与数据范围，用于排查 admin01 看板为 0 的问题。"""
    u = current_user() or {}
    dept = current_scope_department()
    scope = current_data_scope()
    try:
        date_from, date_to = _dashboard_range_to_dates("7d")
        data = get_risk_metrics(department_scope=dept, date_from=date_from, date_to=date_to)
        metrics = {"total_invoice": data.get("total_invoice"), "risk_case_count": data.get("risk_case_count"), "total_txn": data.get("total_txn")}
    except Exception as e:
        metrics = {"error": str(e)}
    return jsonify({
        "user_id": u.get("id"),
        "username": u.get("username"),
        "is_system_admin": is_system_admin(u),
        "data_scope": scope,
        "scope_department": dept,
        "metrics_7d": metrics,
    })



