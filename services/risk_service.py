from __future__ import annotations

from datetime import datetime
from typing import Any

from utils.db import get_conn

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


def _display_text(value: Any, fallback: str = "-") -> str:
    text = _safe_text(value)
    if not text:
        return fallback
    normalized = text.replace("？", "?")
    if normalized and all(ch == "?" for ch in normalized):
        return fallback
    if normalized.lower() in {"none", "null"}:
        return fallback
    return text


def safe_limit(raw: Any, default: int = 200, max_limit: int = 2000) -> int:
    value = _safe_int(raw, default)
    if value <= 0:
        value = default
    return min(value, max_limit)


def normalize_filter_value(raw: Any, allowed: set[str]) -> str:
    normalized = _safe_text(raw).upper()
    return normalized if normalized in allowed else ""


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


def load_risk_center_filter_options(*, department_scope: str | None) -> dict[str, list[str]]:
    sql = [
        """
        SELECT DISTINCT
            COALESCE(i.department, '') AS department,
            COALESCE(
                NULLIF(TRIM(u_owner.employee_name), ''),
                NULLIF(TRIM(u_owner.username), ''),
                NULLIF(TRIM(rc.assigned_to), ''),
                ''
            ) AS owner
        FROM risk_cases rc
        LEFT JOIN risk_events re ON re.id = rc.event_id
        LEFT JOIN invoices i ON i.id = re.invoice_id
        LEFT JOIN users u_owner ON u_owner.id = (
            SELECT u1.id
            FROM users u1
            WHERE
                LOWER(COALESCE(u1.username, '')) = LOWER(COALESCE(rc.assigned_to, ''))
                OR LOWER(COALESCE(u1.employee_no, '')) = LOWER(COALESCE(rc.assigned_to, ''))
                OR LOWER(COALESCE(u1.employee_name, '')) = LOWER(COALESCE(rc.assigned_to, ''))
            ORDER BY u1.id ASC
            LIMIT 1
        )
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

    user_sql = [
        """
        SELECT
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(username, '') AS username
        FROM users
        WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
        """
    ]
    user_params: list[Any] = []
    if scoped_department:
        user_sql.append("AND COALESCE(department, '') = ?")
        user_params.append(scoped_department)
    user_sql.append("ORDER BY id ASC")

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(params)).fetchall()
        user_rows = conn.execute("\n".join(user_sql), tuple(user_params)).fetchall()

    department_set: set[str] = set()
    owner_set: set[str] = set()
    for row in rows:
        department_text = _display_text(row["department"], fallback="")
        owner_text = _display_text(row["owner"], fallback="")
        if department_text:
            department_set.add(department_text)
        if owner_text:
            owner_set.add(owner_text)

    assignee_set: set[str] = set(owner_set)
    for row in user_rows:
        employee_name = _safe_text(row["employee_name"])
        username = _safe_text(row["username"])
        assignee = employee_name or username
        if assignee:
            assignee_set.add(assignee)

    return {
        "departments": sorted(department_set),
        "owners": sorted(owner_set),
        "assignees": sorted(assignee_set),
    }


def load_risk_center_kpis(*, department_scope: str | None) -> dict[str, int]:
    """风险中心 KPI：与列表同口径（中高风险或未结案、LEDGER），返回待处理/高风险/已结案/超期等计数。"""
    sql = [
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN UPPER(COALESCE(rc.status, '')) IN ('OPEN', 'ASSIGNED', 'PROCESSING') THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN UPPER(COALESCE(re.risk_level, '')) = 'HIGH' THEN 1 ELSE 0 END) AS high_risk,
            SUM(CASE WHEN UPPER(COALESCE(rc.status, '')) = 'CLOSED' THEN 1 ELSE 0 END) AS closed,
            SUM(CASE
                WHEN UPPER(COALESCE(rc.status, '')) <> 'CLOSED'
                AND datetime(rc.created_at, '+48 hours') < datetime('now')
                THEN 1 ELSE 0
            END) AS overdue
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
        row = conn.execute("\n".join(sql), tuple(params)).fetchone()
    if not row:
        return {"total": 0, "pending": 0, "high_risk": 0, "closed": 0, "overdue": 0}
    return {
        "total": _safe_int(row["total"], 0),
        "pending": _safe_int(row["pending"], 0),
        "high_risk": _safe_int(row["high_risk"], 0),
        "closed": _safe_int(row["closed"], 0),
        "overdue": _safe_int(row["overdue"], 0),
    }


def load_risk_center_rows(
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
            COALESCE(re.invoice_id, 0) AS invoice_id,
            COALESCE(i.reference_no, '') AS reference_no,
            COALESCE(
                NULLIF(TRIM(i.applicant), ''),
                NULLIF(TRIM(i.submitter_name), ''),
                ''
            ) AS applicant,
            COALESCE(
                NULLIF(TRIM(i.department), ''),
                NULLIF(TRIM(i.submitter_department), ''),
                ''
            ) AS invoice_department,
            UPPER(COALESCE(re.risk_level, 'UNKNOWN')) AS risk_level,
            COALESCE(re.risk_score, 0) AS risk_score,
            UPPER(COALESCE(rc.status, 'OPEN')) AS status,
            COALESCE(rc.assigned_to, '') AS owner,
            COALESCE(
                NULLIF(TRIM(u_owner.employee_name), ''),
                NULLIF(TRIM(u_owner.username), ''),
                NULLIF(TRIM(rc.assigned_to), ''),
                ''
            ) AS owner_name,
            COALESCE(
                NULLIF(TRIM(u_owner.username), ''),
                NULLIF(TRIM(rc.assigned_to), ''),
                ''
            ) AS owner_account,
            COALESCE(NULLIF(TRIM(u_owner.department), ''), '') AS owner_department,
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
            COALESCE((
                SELECT ca.action_note
                FROM case_actions ca
                WHERE ca.case_id = rc.id
                ORDER BY ca.id DESC
                LIMIT 1
            ), '') AS latest_action_note,
            datetime(rc.created_at, '+48 hours') AS sla_due_at
        FROM risk_cases rc
        LEFT JOIN risk_events re ON re.id = rc.event_id
        LEFT JOIN invoices i ON i.id = re.invoice_id
        LEFT JOIN users u_owner ON u_owner.id = (
            SELECT u1.id
            FROM users u1
            WHERE
                LOWER(COALESCE(u1.username, '')) = LOWER(COALESCE(rc.assigned_to, ''))
                OR LOWER(COALESCE(u1.employee_no, '')) = LOWER(COALESCE(rc.assigned_to, ''))
                OR LOWER(COALESCE(u1.employee_name, '')) = LOWER(COALESCE(rc.assigned_to, ''))
            ORDER BY u1.id ASC
            LIMIT 1
        )
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
        owner_like = f"%{owner.upper()}%"
        sql.append(
            """
            AND (
                UPPER(COALESCE(rc.assigned_to, '')) LIKE ?
                OR UPPER(COALESCE(u_owner.employee_name, '')) LIKE ?
                OR UPPER(COALESCE(u_owner.username, '')) LIKE ?
                OR UPPER(COALESCE(u_owner.employee_no, '')) LIKE ?
            )
            """
        )
        params.extend([owner_like, owner_like, owner_like, owner_like])

    sql.append("ORDER BY datetime(updated_at) DESC, rc.id DESC LIMIT ?")
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(params)).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        row_map = dict(row)
        sla_due_at = _safe_text(row_map.get("sla_due_at"))
        owner_raw = _safe_text(row_map.get("owner"))
        owner_name = _display_text(row_map.get("owner_name"))
        owner_account = _display_text(row_map.get("owner_account"))
        owner_department = _display_text(row_map.get("owner_department"))
        owner_display = owner_name if owner_name != "-" else owner_account
        if owner_display == "-":
            owner_display = _display_text(owner_raw)

        applicant = _display_text(row_map.get("applicant"))
        invoice_department = _display_text(row_map.get("invoice_department"))

        result.append(
            {
                "case_id": _safe_int(row_map.get("case_id"), 0),
                "invoice_id": _safe_int(row_map.get("invoice_id"), 0),
                "reference_no": _safe_text(row_map.get("reference_no")),
                "applicant": applicant,
                "invoice_department": invoice_department,
                "risk_level": _safe_text(row_map.get("risk_level"), "UNKNOWN").upper(),
                "score": _safe_int(row_map.get("risk_score"), 0),
                "status": _safe_text(row_map.get("status"), "OPEN").upper(),
                "owner": owner_raw or "-",
                "owner_name": owner_name,
                "owner_account": owner_account,
                "owner_department": owner_department,
                "owner_display": owner_display,
                "department": invoice_department,
                "sla_due_at": sla_due_at or "-",
                "sla_remaining": _format_sla_remaining(sla_due_at),
                "latest_event": _safe_text(row_map.get("latest_event"), "CREATE").upper(),
                "latest_action_note": _safe_text(row_map.get("latest_action_note")),
                "updated_at": _safe_text(row_map.get("updated_at"), "-"),
            }
        )

    return result
