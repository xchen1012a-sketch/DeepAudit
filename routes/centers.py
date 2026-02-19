from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from flask import Blueprint, redirect, render_template, request, url_for

from utils.db import get_conn, list_invoices
from utils.security import current_scope_department, current_user, has_permission, login_required

bp = Blueprint("centers", __name__)

RISK_LEVEL_FILTER_OPTIONS = {"HIGH", "MEDIUM", "LOW"}
STATUS_FILTER_OPTIONS = {"OPEN", "ASSIGNED", "PROCESSING", "CLOSED"}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_limit(raw: Any, default: int = 200, max_limit: int = 2000) -> int:
    value = _safe_int(raw, default)
    if value <= 0:
        value = default
    return min(value, max_limit)


def _parse_datetime(value: Any) -> datetime | None:
    text = _safe_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _parse_date(value: Any) -> date | None:
    text = _safe_text(value)
    if not text:
        return None
    if len(text) >= 10:
        text = text[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _format_amount(raw_amount: Any, currency: Any) -> str:
    text = _safe_text(raw_amount, "-")
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned:
        return text
    try:
        value = float(cleaned)
    except Exception:
        return text

    cur = _safe_text(currency).upper() or "CNY"
    if cur in {"CNY", "RMB"}:
        return f"\u00a5{value:,.2f}"
    if cur == "USD":
        return f"${value:,.2f}"
    if cur == "HKD":
        return f"HK${value:,.2f}"
    return f"{cur} {value:,.2f}"


def _normalize_filter_value(raw: Any, allowed: set[str]) -> str:
    normalized = _safe_text(raw).upper()
    return normalized if normalized in allowed else ""


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


def _format_sla_remaining(sla_due_at_text: str) -> str:
    due_dt = _parse_datetime(sla_due_at_text)
    if due_dt is None:
        return "-"

    now = datetime.now()
    seconds = int((due_dt - now).total_seconds())
    abs_seconds = abs(seconds)
    hours, rem = divmod(abs_seconds, 3600)
    minutes = rem // 60

    if seconds >= 0:
        return f"剩余 {hours}h {minutes}m"
    return f"已超时 {hours}h {minutes}m"


def _load_risk_center_filter_options(*, department_scope: str | None) -> dict[str, list[str]]:
    sql = [
        """
        SELECT DISTINCT
            COALESCE(i.department, '') AS department,
            COALESCE(rc.assigned_to, '') AS owner
        FROM risk_cases rc
        LEFT JOIN risk_events re ON re.id = rc.event_id
        LEFT JOIN invoices i ON i.id = re.invoice_id
        WHERE (
            UPPER(COALESCE(re.risk_level, '')) IN ('MEDIUM', 'HIGH')
            OR UPPER(COALESCE(rc.status, '')) <> 'CLOSED'
        )
          AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
        """
    ]
    params: list[Any] = []

    scoped_department = _safe_text(department_scope)
    if scoped_department:
        sql.append("AND i.department = ?")
        params.append(scoped_department)

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(params)).fetchall()

    department_set: set[str] = set()
    owner_set: set[str] = set()
    for row in rows:
        department_text = _safe_text(row["department"])
        owner_text = _safe_text(row["owner"])
        if department_text:
            department_set.add(department_text)
        if owner_text:
            owner_set.add(owner_text)

    return {
        "departments": sorted(department_set),
        "owners": sorted(owner_set),
    }


def _load_risk_center_rows(
    *,
    limit: int,
    department_scope: str | None,
    risk_level: str,
    status: str,
    department: str,
    owner: str,
) -> list[dict[str, Any]]:
    sql = [
        """
        SELECT
            rc.id AS case_id,
            UPPER(COALESCE(re.risk_level, 'UNKNOWN')) AS risk_level,
            COALESCE(re.risk_score, 0) AS risk_score,
            UPPER(COALESCE(rc.status, 'OPEN')) AS status,
            COALESCE(rc.assigned_to, '') AS owner,
            COALESCE(i.department, '') AS department,
            COALESCE((
                SELECT ca.action_type
                FROM case_actions ca
                WHERE ca.case_id = rc.id
                ORDER BY ca.id DESC
                LIMIT 1
            ), 'CREATE') AS latest_event,
            COALESCE((
                SELECT ca.created_at
                FROM case_actions ca
                WHERE ca.case_id = rc.id
                ORDER BY ca.id DESC
                LIMIT 1
            ), rc.closed_at, rc.created_at) AS updated_at,
            datetime(rc.created_at, '+48 hours') AS sla_due_at
        FROM risk_cases rc
        LEFT JOIN risk_events re ON re.id = rc.event_id
        LEFT JOIN invoices i ON i.id = re.invoice_id
        WHERE (
            UPPER(COALESCE(re.risk_level, '')) IN ('MEDIUM', 'HIGH')
            OR UPPER(COALESCE(rc.status, '')) <> 'CLOSED'
        )
          AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
        """
    ]
    params: list[Any] = []

    scoped_department = _safe_text(department_scope)
    if scoped_department:
        sql.append("AND i.department = ?")
        params.append(scoped_department)

    if risk_level:
        sql.append("AND UPPER(COALESCE(re.risk_level, '')) = ?")
        params.append(risk_level)
    if status:
        sql.append("AND UPPER(COALESCE(rc.status, '')) = ?")
        params.append(status)
    if department:
        sql.append("AND COALESCE(i.department, '') = ?")
        params.append(department)
    if owner:
        sql.append("AND UPPER(COALESCE(rc.assigned_to, '')) LIKE ?")
        params.append(f"%{owner.upper()}%")

    sql.append("ORDER BY datetime(updated_at) DESC, rc.id DESC LIMIT ?")
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(params)).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        row_map = dict(row)
        sla_due_at = _safe_text(row_map.get("sla_due_at"))
        result.append(
            {
                "case_id": _safe_int(row_map.get("case_id"), 0),
                "risk_level": _safe_text(row_map.get("risk_level"), "UNKNOWN").upper(),
                "score": _safe_int(row_map.get("risk_score"), 0),
                "status": _safe_text(row_map.get("status"), "OPEN").upper(),
                "owner": _safe_text(row_map.get("owner"), "-"),
                "department": _safe_text(row_map.get("department"), "-"),
                "sla_due_at": sla_due_at or "-",
                "sla_remaining": _format_sla_remaining(sla_due_at),
                "latest_event": _safe_text(row_map.get("latest_event"), "CREATE").upper(),
                "updated_at": _safe_text(row_map.get("updated_at"), "-"),
            }
        )

    return result


def _load_ledger_rows(
    *,
    limit: int,
    department_scope: str | None,
    range_key: str,
) -> list[dict[str, Any]]:
    rows = list_invoices(limit=limit, department=department_scope)
    cleaned_rows: list[dict[str, Any]] = [dict(row) for row in rows]

    if range_key == "7d":
        cutoff = date.today() - timedelta(days=6)
        filtered: list[dict[str, Any]] = []
        for row in cleaned_rows:
            base_day = _parse_date(row.get("invoice_date")) or _parse_date(row.get("created_at"))
            if base_day is None or base_day >= cutoff:
                filtered.append(row)
        cleaned_rows = filtered

    result: list[dict[str, Any]] = []
    for row in cleaned_rows:
        invoice_id = _safe_int(row.get("id"), 0)
        applicant = _safe_text(row.get("applicant"), "-")
        department = _safe_text(row.get("department"), "-")
        verify_status = _safe_text(row.get("verify_status"), "PENDING").upper()
        approval_status = _safe_text(row.get("status"), "PENDING").upper()
        risk_level = _safe_text(row.get("risk_level") or row.get("ai_risk_level"), "UNKNOWN").upper()
        result.append(
            {
                "id": invoice_id,
                "document_no": _safe_text(row.get("reference_no"), f"DOC-{invoice_id}"),
                "invoice_date": _safe_text(row.get("invoice_date"), "-"),
                "employee_department": f"{applicant} / {department}",
                "vendor": _safe_text(row.get("merchant_name"), "-"),
                "expense_type": _safe_text(row.get("item_name"), "-"),
                "amount": _format_amount(row.get("amount"), row.get("currency")),
                "verify_status": verify_status,
                "approval_status": approval_status,
                "risk_level": risk_level,
            }
        )
    return result

