# -*- coding: utf-8 -*-
"""
智能审计链服务
获取链详情、追加事件、关联证据，含数据范围校验与审计写入
"""

from __future__ import annotations

from typing import Any

from audit import write_audit_log
from utils.audit_chain_i18n import event_type_to_cn, object_type_to_cn
from utils.data_scope_enforcer import enforce_data_scope_check
from utils.db import (
    append_audit_trace_event,
    get_audit_trace_by_object,
    get_conn,
    get_or_create_audit_trace,
    link_audit_evidence,
    list_audit_evidence,
    list_audit_trace_events,
)


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _resolve_invoice_for_scope_check(object_type: str, object_id: str | int) -> dict[str, Any] | None:
    """
    根据 object_type + object_id 解析出关联的发票信息（用于数据范围校验）。
    返回包含 department, applicant 的字典，若对象不存在则返回 None。
    """
    obj_type = str(object_type or "").strip().lower()
    obj_id = str(object_id or "").strip()
    if not obj_type or not obj_id:
        return None

    with get_conn() as conn:
        if obj_type == "invoice":
            row = conn.execute(
                "SELECT id, department, applicant FROM invoices WHERE id = ?",
                (_safe_int(obj_id),),
            ).fetchone()
            if row:
                return {
                    "department": _safe_text(row["department"]),
                    "applicant": _safe_text(row["applicant"]),
                }
            return None

        if obj_type == "risk_event":
            row = conn.execute(
                "SELECT invoice_id FROM risk_events WHERE id = ?",
                (_safe_int(obj_id),),
            ).fetchone()
            if row:
                inv_id = _safe_int(row["invoice_id"])
                if inv_id > 0:
                    inv = conn.execute(
                        "SELECT department, applicant FROM invoices WHERE id = ?",
                        (inv_id,),
                    ).fetchone()
                    if inv:
                        return {
                            "department": _safe_text(inv["department"]),
                            "applicant": _safe_text(inv["applicant"]),
                        }
            return None

        if obj_type == "risk_case":
            row = conn.execute(
                "SELECT event_id FROM risk_cases WHERE id = ?",
                (_safe_int(obj_id),),
            ).fetchone()
            if row:
                event_id = _safe_int(row["event_id"])
                if event_id > 0:
                    ev = conn.execute(
                        "SELECT invoice_id FROM risk_events WHERE id = ?",
                        (event_id,),
                    ).fetchone()
                    if ev:
                        inv_id = _safe_int(ev["invoice_id"])
                        if inv_id > 0:
                            inv = conn.execute(
                                "SELECT department, applicant FROM invoices WHERE id = ?",
                                (inv_id,),
                            ).fetchone()
                            if inv:
                                return {
                                    "department": _safe_text(inv["department"]),
                                    "applicant": _safe_text(inv["applicant"]),
                                }
            return None

        if obj_type == "approval":
            # approval 通常关联 invoice，这里 object_id 可能是 invoice_id
            row = conn.execute(
                "SELECT department, applicant FROM invoices WHERE id = ?",
                (_safe_int(obj_id),),
            ).fetchone()
            if row:
                return {
                    "department": _safe_text(row["department"]),
                    "applicant": _safe_text(row["applicant"]),
                }
            return None

    return None


def get_chain_by_object(
    object_type: str,
    object_id: str | int,
    user: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """
    获取审计链详情（含时间线+证据），内部做数据范围校验。
    返回 (chain_data, error_cn)。
    若 error_cn 非空表示越权或不存在，chain_data 为 None。
    """
    obj_type = str(object_type or "").strip().lower()
    obj_id = str(object_id or "").strip()
    if not obj_type or not obj_id:
        return None, "参数无效"

    if obj_type not in ("invoice", "risk_event", "risk_case", "approval"):
        return None, "不支持的对象类型"

    scope_info = _resolve_invoice_for_scope_check(obj_type, obj_id)
    if not scope_info:
        return None, "资源不存在或已被删除"

    allowed, reason = enforce_data_scope_check(
        target_department=scope_info.get("department"),
        target_owner_identity=scope_info.get("applicant"),
        user=user,
    )
    if not allowed:
        return None, reason or "无权访问该数据"

    trace = get_audit_trace_by_object(obj_type, obj_id)
    trace_id: str
    if trace and isinstance(trace, dict):
        trace_id = _safe_text(trace.get("trace_id"))
    else:
        trace_id, _ = get_or_create_audit_trace(obj_type, obj_id)

    events = list_audit_trace_events(trace_id, limit=100)
    evidence = list_audit_evidence(trace_id, limit=50)

    for ev in events:
        ev["event_type_cn"] = event_type_to_cn(ev.get("event_type"))

    return {
        "object_type": obj_type,
        "object_id": obj_id,
        "object_type_cn": object_type_to_cn(obj_type),
        "trace_id": trace_id,
        "events": events,
        "evidence": evidence,
    }, ""


def append_event(
    trace_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    change_reason_code: str = "SYSTEM_AUTO",
    user: dict[str, Any] | None = None,
) -> int:
    """
    追加审计链事件，并写入 audit_log。
    返回事件 id。
    """
    from utils.security import current_user

    actor = user if user is not None else current_user() or {}
    actor_user_id = str(actor.get("id") or "")
    actor_name = (
        _safe_text(actor.get("employee_name"))
        or _safe_text(actor.get("username"))
        or _safe_text(actor.get("employee_no"))
        or "system"
    )

    event_id = append_audit_trace_event(
        trace_id=trace_id,
        event_type=event_type,
        payload=payload,
        actor_user_id=actor_user_id,
        actor_name=actor_name,
    )

    after_obj = {
        "event_id": event_id,
        "event_type": event_type,
        "trace_id": trace_id,
        "payload": payload or {},
    }
    write_audit_log(
        action="APPEND_EVENT",
        target_type="audit_trace_event",
        target_id=str(event_id),
        before_obj={},
        after_obj=after_obj,
        change_reason_code=change_reason_code,
        trace_id=trace_id,
    )
    return event_id


def link_evidence(
    trace_id: str,
    file_path: str,
    *,
    object_type: str = "invoice",
    object_id: str = "",
    evidence_type: str = "file",
    change_reason_code: str = "SYSTEM_AUTO",
    user: dict[str, Any] | None = None,
) -> int:
    """
    关联审计证据，并写入 audit_log。
    返回证据 id。
    """
    from utils.security import current_user

    evidence_id = link_audit_evidence(
        trace_id=trace_id,
        file_path=file_path,
        object_type=object_type,
        object_id=object_id,
        evidence_type=evidence_type,
    )

    actor = user if user is not None else current_user() or {}
    after_obj = {
        "evidence_id": evidence_id,
        "trace_id": trace_id,
        "file_path": file_path,
        "object_type": object_type,
        "object_id": object_id,
    }
    write_audit_log(
        action="LINK_EVIDENCE",
        target_type="audit_evidence",
        target_id=str(evidence_id),
        before_obj={},
        after_obj=after_obj,
        change_reason_code=change_reason_code,
        trace_id=trace_id,
    )
    return evidence_id
