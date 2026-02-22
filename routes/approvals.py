from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from audit import write_audit_log
from services.approval_service import APPROVAL_STATUSES, actor_id, list_approval_rows, safe_limit, summary
from services.audit_chain_service import append_event as append_audit_chain_event
from utils.audit_logger import write_audit_log as write_audit_log_orm
from utils.db import get_conn, get_or_create_audit_trace
from utils.security import (
    approval_allowed_workflow_roles,
    can_approve,
    can_access_approval_console,
    current_scope_department,
    current_user,
    has_governance_admin_role,
    is_system_admin,
    login_required,
    require_permission,
)

bp = Blueprint("approvals", __name__)

APPROVAL_ACTIONS = {"APPROVE", "REJECT", "RETURN", "ASSIGN"}
CHANGE_REASON_CODES = {
    "POLICY_MATCH",
    "POLICY_EXCEPTION",
    "NEED_MORE_INFO",
    "DUPLICATE_SUSPECT",
    "MANUAL_OVERRIDE",
}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    return _safe_text(value).lower() in {"1", "true", "yes", "on"}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _identity_set(user: dict[str, Any]) -> set[str]:
    return {
        _safe_text(user.get("id")),
        _safe_text(user.get("username")),
        _safe_text(user.get("employee_no")),
    }


def _identity_matches(stored_value: Any, user: dict[str, Any]) -> bool:
    normalized = _safe_text(stored_value)
    if not normalized:
        return False
    return normalized in _identity_set(user)


def _normalized_identity_value(value: Any) -> str:
    return _safe_text(value).strip().lower()


def _is_self_submitted_invoice(row: dict[str, Any], user: dict[str, Any]) -> bool:
    identities = {
        _normalized_identity_value(user.get("id")),
        _normalized_identity_value(user.get("username")),
        _normalized_identity_value(user.get("employee_no")),
        _normalized_identity_value(user.get("employee_name")),
    }
    identities = {item for item in identities if item}
    if not identities:
        return False

    submitter_values = {
        _normalized_identity_value(row.get("submitted_by_user_id")),
        _normalized_identity_value(row.get("submitter_no")),
        _normalized_identity_value(row.get("submitter_name")),
        _normalized_identity_value(row.get("applicant")),
    }
    return any(item in identities for item in submitter_values if item)


def _normalize_risk_level(value: Any) -> str:
    risk = _safe_text(value).upper()
    return risk if risk in {"HIGH", "MEDIUM", "LOW"} else "LOW"


def _normalize_status(approval_status: Any, fallback_status: Any = None) -> str:
    status = _safe_text(approval_status).upper()
    if status in APPROVAL_STATUSES:
        return status
    fallback = _safe_text(fallback_status).upper()
    return fallback if fallback in APPROVAL_STATUSES else "PENDING"


def _normalize_stage(value: Any, status: str) -> str:
    stage = _safe_text(value).upper()
    if stage in {"L1", "L2", "DONE"}:
        return stage
    return "L1" if status == "PENDING" else "DONE"


def _approval_snapshot(row: dict[str, Any], *, action: str = "", comment: str = "") -> dict[str, Any]:
    payload = {
        "approval_stage": _normalize_stage(row.get("approval_stage"), _normalize_status(row.get("approval_status"), row.get("status"))),
        "approval_status": _normalize_status(row.get("approval_status"), row.get("status")),
        "queue_owner_id": _safe_text(row.get("queue_owner_id")),
        "risk_level": _normalize_risk_level(row.get("risk_level")),
    }
    if action:
        payload["action"] = action
    if comment:
        payload["comment"] = comment
    return payload


def _load_invoice_for_action(conn, approval_id: int) -> dict[str, Any] | None:
    scoped_department = current_scope_department()
    if scoped_department:
        row = conn.execute(
            """
            SELECT *
            FROM invoices
            WHERE id = ? AND department = ? AND UPPER(COALESCE(record_state, 'DRAFT')) = 'LEDGER'
            LIMIT 1
            """,
            (int(approval_id), scoped_department),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT *
            FROM invoices
            WHERE id = ? AND UPPER(COALESCE(record_state, 'DRAFT')) = 'LEDGER'
            LIMIT 1
            """,
            (int(approval_id),),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def _find_l2_reviewer(conn, *, exclude: set[str]) -> str:
    rows = conn.execute(
        """
        SELECT username, employee_no, role
        FROM users
        WHERE status = 'ACTIVE'
        ORDER BY CASE
            WHEN username = 'finance01' THEN 0
            WHEN username = 'admin01' THEN 1
            WHEN LOWER(COALESCE(role, '')) LIKE '%manager%' THEN 2
            WHEN LOWER(COALESCE(role, '')) LIKE '%admin%' THEN 3
            ELSE 10
        END, id ASC
        """
    ).fetchall()
    for row in rows:
        username = _safe_text(row["username"])
        employee_no = _safe_text(row["employee_no"])
        candidate = username or employee_no
        if not candidate:
            continue
        if candidate in exclude:
            continue
        return candidate
    return ""


def _update_invoice_fields(conn, approval_id: int, fields: dict[str, Any]) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    assignments = ", ".join([f"{key} = ?" for key in keys])
    values = [fields[key] for key in keys]
    conn.execute(
        f"UPDATE invoices SET {assignments} WHERE id = ?",
        (*values, int(approval_id)),
    )


def _filter_rows_by_inbox(rows: list[dict[str, Any]], inbox: str, user: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = _safe_text(inbox).lower()
    identity = _identity_set(user)

    def _queue_owner_matches(item: dict[str, Any]) -> bool:
        owner = _safe_text(item.get("queue_owner_id"))
        return owner in identity if owner else False

    def _processed_by_me(item: dict[str, Any]) -> bool:
        return _identity_matches(item.get("first_approver_id"), user) or _identity_matches(item.get("second_approver_id"), user)

    if normalized in {"all", "all_pending"}:
        return [item for item in rows if _normalize_status(item.get("approval_status"), item.get("status")) == "PENDING"]
    if normalized in {"mine", "my_processed", "handled"}:
        return [item for item in rows if _processed_by_me(item)]
    return [item for item in rows if _normalize_status(item.get("approval_status"), item.get("status")) == "PENDING" and _queue_owner_matches(item)]


def _scope_rows_by_workflow_role(rows: list[dict[str, Any]], user: dict[str, Any]) -> list[dict[str, Any]]:
    allowed_roles = approval_allowed_workflow_roles(user)
    if not allowed_roles:
        return []
    return [
        item
        for item in rows
        if _safe_text(item.get("workflow_required_role")).upper() in allowed_roles
    ]


def _resolve_required_role_for_action(approval_id: int, user: dict[str, Any]) -> str:
    rows = list_approval_rows(
        limit=5000,
        department_scope=current_scope_department(),
        row_cleaner=current_app.config.get("CLEAN_INVOICE_ROWS"),
    )
    for item in rows:
        if _safe_int(item.get("id"), 0) == int(approval_id):
            required = _safe_text(item.get("workflow_required_role")).upper()
            if required:
                return required
            step = _safe_text(item.get("workflow_step")).upper()
            if step == "C":
                return "CFO"
            return "MANAGER"
    return ""


@bp.get("/api/approvals")
@login_required
@require_permission("VIEW_INVOICES")
def approvals_api():
    user = current_user() or {}
    if not can_access_approval_console(user):
        return jsonify({"ok": False, "msg": "无权访问", "message": "无权访问该资源"}), 403

    rows = list_approval_rows(
        limit=safe_limit(request.args.get("limit"), default=500, max_limit=5000),
        department_scope=current_scope_department(),
        row_cleaner=current_app.config.get("CLEAN_INVOICE_ROWS"),
    )
    rows = _scope_rows_by_workflow_role(rows, user)
    full_summary = summary(rows)

    inbox = _safe_text(request.args.get("inbox"), "my_pending").lower()
    filtered = _filter_rows_by_inbox(rows, inbox, user)

    status_filter = _safe_text(request.args.get("status")).upper()
    if status_filter in APPROVAL_STATUSES:
        filtered = [item for item in filtered if _safe_text(item.get("approval_status")).upper() == status_filter]

    risk_filter = _safe_text(request.args.get("risk_level")).upper()
    if risk_filter in {"HIGH", "MEDIUM", "LOW"}:
        filtered = [item for item in filtered if _safe_text(item.get("risk_level")).upper() == risk_filter]

    step_filter = _safe_text(request.args.get("step")).upper()
    if step_filter in {"A", "B", "C", "END"}:
        filtered = [item for item in filtered if _safe_text(item.get("workflow_step")).upper() == step_filter]

    owner_filter = _safe_text(request.args.get("queue_owner_id"))
    if owner_filter:
        filtered = [item for item in filtered if _safe_text(item.get("queue_owner_id")) == owner_filter]

    return jsonify({"ok": True, "data": filtered, "summary": full_summary, "debug_marker": "APPROVAL_API_V2"})


@bp.post("/api/approvals/<int:approval_id>/action")
@login_required
@require_permission("VIEW_INVOICES")
def approval_action_api(approval_id: int):
    user = current_user() or {}
    if not can_access_approval_console(user):
        return jsonify({"ok": False, "msg": "无权访问", "message": "无权访问该资源"}), 403

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "msg": "request body must be a JSON object"}), 400

    action = _safe_text(payload.get("action")).upper()
    if action not in APPROVAL_ACTIONS:
        return jsonify({"ok": False, "msg": "invalid action"}), 400

    reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not reason_code:
        return jsonify({"ok": False, "msg": "change_reason_code is required"}), 400
    if reason_code not in CHANGE_REASON_CODES:
        return jsonify({"ok": False, "msg": "invalid change_reason_code"}), 400

    comment = _safe_text(payload.get("comment"))
    assign_to = _safe_text(payload.get("assign_to"))
    is_batch = _to_bool(payload.get("is_batch"))

    actor = actor_id(user)
    now_text = _now_text()

    with get_conn() as conn:
        row = _load_invoice_for_action(conn, approval_id)
        if row is None:
            return jsonify({"ok": False, "msg": "approval not found"}), 404

        if (
            has_governance_admin_role(user)
            and can_approve(user)
            and not is_system_admin(user)
            and _is_self_submitted_invoice(row, user)
        ):
            return (
                jsonify(
                    {
                        "ok": False,
                        "msg": "无权访问",
                        "message": "治理与审批双角色需回避本人单据审批",
                    }
                ),
                403,
            )

        allowed_roles = approval_allowed_workflow_roles(user)
        required_role = _resolve_required_role_for_action(approval_id, user)
        if not required_role:
            current_stage = _normalize_stage(row.get("approval_stage"), _normalize_status(row.get("approval_status"), row.get("status")))
            required_role = "CFO" if current_stage == "L2" else "MANAGER"
        if required_role not in allowed_roles:
            return jsonify({"ok": False, "msg": "无权访问", "message": "无权访问该资源"}), 403

        before_snapshot = _approval_snapshot(row)
        risk_level = _normalize_risk_level(row.get("risk_level"))
        current_stage = _normalize_stage(row.get("approval_stage"), _normalize_status(row.get("approval_status"), row.get("status")))
        current_status = _normalize_status(row.get("approval_status"), row.get("status"))
        trace_id = _safe_text(row.get("ai_trace_id"))

        updates: dict[str, Any] = {}

        if action == "ASSIGN":
            if not assign_to:
                return jsonify({"ok": False, "msg": "assign_to is required when action=ASSIGN"}), 400
            if current_status != "PENDING":
                return jsonify({"ok": False, "msg": "only pending approval can be assigned"}), 409
            updates["queue_owner_id"] = assign_to

        elif action == "APPROVE":
            if current_status != "PENDING":
                return jsonify({"ok": False, "msg": "approval already finished"}), 409

            if is_batch and risk_level == "HIGH" and not comment:
                return jsonify({"ok": False, "msg": "batch high-risk approval requires comment"}), 400

            if risk_level == "HIGH":
                if current_stage == "L1":
                    l2_owner = _find_l2_reviewer(conn, exclude={actor, _safe_text(row.get("queue_owner_id"))})
                    updates["first_approver_id"] = actor
                    updates["first_approved_at"] = now_text
                    updates["approval_stage"] = "L2"
                    updates["approval_status"] = "PENDING"
                    updates["status"] = "PENDING"
                    updates["queue_owner_id"] = l2_owner
                elif current_stage == "L2":
                    if _identity_matches(row.get("first_approver_id"), user):
                        return jsonify({"ok": False, "msg": "复核人不能与初审人相同"}), 400
                    if not comment:
                        return jsonify({"ok": False, "msg": "L2 approval requires comment"}), 400
                    updates["second_approver_id"] = actor
                    updates["second_approved_at"] = now_text
                    updates["approval_stage"] = "DONE"
                    updates["approval_status"] = "APPROVED"
                    updates["status"] = "APPROVED"
                    updates["queue_owner_id"] = ""
                else:
                    return jsonify({"ok": False, "msg": "invalid approval stage"}), 409
            else:
                # 低/中风险单据：一次性通过
                updates["approval_stage"] = "DONE"
                updates["approval_status"] = "APPROVED"
                updates["status"] = "APPROVED"
                updates["queue_owner_id"] = ""
                # 始终记录当前审批人
                updates["first_approver_id"] = actor
                updates["first_approved_at"] = now_text

        elif action in {"REJECT", "RETURN"}:
            if not comment:
                return jsonify({"ok": False, "msg": "comment is required for reject/return"}), 400
            target_status = "REJECTED" if action == "REJECT" else "RETURNED"
            updates["approval_stage"] = "DONE"
            updates["approval_status"] = target_status
            updates["status"] = target_status
            updates["queue_owner_id"] = ""
            # 始终记录当前审批人
            updates["first_approver_id"] = actor
            updates["first_approved_at"] = now_text

        _update_invoice_fields(conn, approval_id, updates)
        updated_row = _load_invoice_for_action(conn, approval_id)
        conn.commit()

    if updated_row is None:
        return jsonify({"ok": False, "msg": "approval not found"}), 404

    after_snapshot = _approval_snapshot(updated_row, comment=comment, action=action)
    
    # 写入新的 ORM 审计日志
    try:
        user_obj = current_user() or {}
        write_audit_log_orm(
            action=f"APPROVAL_{action}",
            actor_user_id=_safe_int(user_obj.get("id")),
            actor_name=_safe_text(user_obj.get("employee_name") or user_obj.get("username")),
            target_type="approval",
            target_id=str(approval_id),
            snapshot_before=before_snapshot,
            snapshot_after=after_snapshot,
            trace_id=trace_id,
            change_reason_code=reason_code,
            detail=f"action={action}; comment={comment[:100] if comment else ''}",
        )
    except Exception:
        current_app.logger.exception("write approval audit failed: approval_id=%s", approval_id)
    
    # 保留原有审计日志（向后兼容）
    try:
        write_audit_log(
            action="APPROVAL_ACTION",
            target_type="approval",
            target_id=str(int(approval_id)),
            before_obj=before_snapshot,
            after_obj=after_snapshot,
            change_reason_code=reason_code,
            trace_id=trace_id,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400
    except Exception:
        current_app.logger.exception("write approval audit failed: approval_id=%s", approval_id)

    stage = _normalize_stage(updated_row.get("approval_stage"), _normalize_status(updated_row.get("approval_status"), updated_row.get("status")))
    status = _normalize_status(updated_row.get("approval_status"), updated_row.get("status"))

    try:
        trace_id, _ = get_or_create_audit_trace("invoice", approval_id)
        if action == "APPROVE":
            evt = "FINAL" if stage == "DONE" else "APPROVAL"
        elif action == "REJECT":
            evt = "APPROVAL"
        elif action == "RETURN":
            evt = "RETURN"
        else:
            evt = None
        if evt:
            append_audit_chain_event(trace_id, evt, {"action": action, "status": status}, reason_code, user=user)
    except Exception:
        pass

    if action == "APPROVE" and _normalize_risk_level(updated_row.get("risk_level")) == "HIGH" and stage == "L2":
        return jsonify(
            {
                "ok": True,
                "id": int(approval_id),
                "stage": "L2",
                "status": status,
                "queue_owner_id": _safe_text(updated_row.get("queue_owner_id")),
                "message": "已提交复核，需二线复核确认。",
                "debug_marker": "APPROVAL_API_V2",
            }
        )

    return jsonify(
        {
            "ok": True,
            "id": int(approval_id),
            "stage": stage,
            "status": status,
            "queue_owner_id": _safe_text(updated_row.get("queue_owner_id")),
            "message": "审批动作已完成。",
            "debug_marker": "APPROVAL_API_V2",
        }
    )


@bp.get("/approvals/health")
def health():
    return jsonify({"ok": True, "module": "approvals"})
