from __future__ import annotations

from datetime import datetime
from typing import Any

from utils.db import get_conn

RISK_EVENT_LEVELS = {"MEDIUM", "HIGH"}
CASE_STATUS_OPEN = "OPEN"
CASE_STATUS_ASSIGNED = "ASSIGNED"
CASE_STATUS_PROCESSING = "PROCESSING"
CASE_STATUS_CLOSED = "CLOSED"
MIN_RISK_SCORE = 0
MAX_RISK_SCORE = 100


class RiskCaseError(Exception):
    pass


class NotFoundError(RiskCaseError):
    pass


class ConflictError(RiskCaseError):
    pass


class ValidationError(RiskCaseError):
    pass


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_scope_department(department_scope: str | None) -> str:
    return _safe_text(department_scope)


def _fetch_risk_event(conn, event_id: int, *, department_scope: str | None = None) -> dict[str, Any] | None:
    scoped_department = _normalize_scope_department(department_scope)
    if scoped_department:
        row = conn.execute(
            """
            SELECT re.id, re.invoice_id, re.risk_level, re.risk_score, re.rule_summary, re.trace_id, re.created_at
            FROM risk_events re
            JOIN invoices i ON i.id = re.invoice_id
            WHERE re.id = ? AND i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
            """,
            (int(event_id), scoped_department),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT re.id, re.invoice_id, re.risk_level, re.risk_score, re.rule_summary, re.trace_id, re.created_at
            FROM risk_events re
            JOIN invoices i ON i.id = re.invoice_id
            WHERE re.id = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
            """,
            (int(event_id),),
        ).fetchone()
    return dict(row) if row else None


def _invoice_eligible_for_risk_event(conn, invoice_id: int) -> bool:
    row = conn.execute(
        """
        SELECT amount, invoice_date, record_state
        FROM invoices
        WHERE id = ?
        LIMIT 1
        """,
        (int(invoice_id),),
    ).fetchone()
    if row is None:
        return False
    record_state = _safe_text(row["record_state"]).upper()
    amount = _safe_text(row["amount"])
    invoice_date = _safe_text(row["invoice_date"])
    return record_state == "LEDGER" and bool(amount) and bool(invoice_date)


def _fetch_case(conn, case_id: int, *, department_scope: str | None = None) -> dict[str, Any] | None:
    scoped_department = _normalize_scope_department(department_scope)
    if scoped_department:
        row = conn.execute(
            """
            SELECT c.id, c.event_id, c.assigned_to, c.status, c.resolution_note, c.created_at, c.closed_at,
                   e.invoice_id, e.risk_level, e.risk_score, e.rule_summary, e.trace_id,
                   i.department
            FROM risk_cases c
            LEFT JOIN risk_events e ON e.id = c.event_id
            LEFT JOIN invoices i ON i.id = e.invoice_id
            WHERE c.id = ? AND i.department = ?
            """,
            (int(case_id), scoped_department),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT c.id, c.event_id, c.assigned_to, c.status, c.resolution_note, c.created_at, c.closed_at,
                   e.invoice_id, e.risk_level, e.risk_score, e.rule_summary, e.trace_id,
                   i.department
            FROM risk_cases c
            LEFT JOIN risk_events e ON e.id = c.event_id
            LEFT JOIN invoices i ON i.id = e.invoice_id
            WHERE c.id = ?
            """,
            (int(case_id),),
        ).fetchone()
    return dict(row) if row else None


def _insert_case_action(
    conn,
    *,
    case_id: int,
    action_type: str,
    operator: str,
    action_note: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO case_actions (case_id, action_type, operator, action_note, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(case_id),
            _safe_text(action_type).upper(),
            _safe_text(operator, "system"),
            _safe_text(action_note),
            _now_text(),
        ),
    )
    return int(cur.lastrowid)


def create_risk_event(
    *,
    invoice_id: int,
    risk_level: str,
    risk_score: int,
    rule_summary: str,
    trace_id: str,
) -> dict[str, Any]:
    normalized_level = _safe_text(risk_level).upper()
    if not normalized_level:
        normalized_level = "MEDIUM"

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO risk_events (invoice_id, risk_level, risk_score, rule_summary, trace_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(invoice_id),
                normalized_level,
                _safe_int(risk_score),
                _safe_text(rule_summary),
                _safe_text(trace_id),
                _now_text(),
            ),
        )
        event_id = int(cur.lastrowid)
        row = _fetch_risk_event(conn, event_id)
        conn.commit()
    return row or {"id": event_id}


def create_ai_risk_event_if_needed(
    *,
    invoice_id: int,
    ai_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    payload = ai_data or {}
    risk_level = _safe_text(payload.get("risk_level")).upper()
    if risk_level not in RISK_EVENT_LEVELS:
        return None

    with get_conn() as conn:
        if not _invoice_eligible_for_risk_event(conn, int(invoice_id)):
            return None

    return create_risk_event(
        invoice_id=int(invoice_id),
        risk_level=risk_level,
        risk_score=_safe_int(payload.get("risk_score"), 0),
        rule_summary=_safe_text(payload.get("summary")),
        trace_id=_safe_text(payload.get("trace_id")),
    )


def create_case_from_event(
    *,
    event_id: int,
    operator: str,
    action_note: str = "",
    department_scope: str | None = None,
) -> dict[str, Any]:
    normalized_event_id = _safe_int(event_id, 0)
    if normalized_event_id <= 0:
        raise ValidationError("invalid event id")

    with get_conn() as conn:
        event_row = _fetch_risk_event(conn, normalized_event_id, department_scope=department_scope)
        if event_row is None:
            raise NotFoundError("risk event not found")

        existing = conn.execute(
            "SELECT id FROM risk_cases WHERE event_id = ? LIMIT 1",
            (normalized_event_id,),
        ).fetchone()
        if existing:
            raise ConflictError("risk case already exists for this event")

        cur = conn.execute(
            """
            INSERT INTO risk_cases (event_id, assigned_to, status, resolution_note, created_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_event_id,
                None,
                CASE_STATUS_OPEN,
                None,
                _now_text(),
                None,
            ),
        )
        case_id = int(cur.lastrowid)
        _insert_case_action(
            conn,
            case_id=case_id,
            action_type="CREATE",
            operator=operator,
            action_note=_safe_text(action_note, "由风险事件创建案件"),
        )
        case_row = _fetch_case(conn, case_id, department_scope=department_scope)
        conn.commit()
    return case_row or {"id": case_id, "event_id": normalized_event_id}


def assign_case(
    *,
    case_id: int,
    assigned_to: str,
    operator: str,
    action_note: str = "",
    department_scope: str | None = None,
) -> dict[str, Any]:
    normalized_case_id = _safe_int(case_id, 0)
    if normalized_case_id <= 0:
        raise ValidationError("invalid case id")

    normalized_assignee = _safe_text(assigned_to)
    if not normalized_assignee:
        raise ValidationError("assigned_to is required")

    with get_conn() as conn:
        case_row = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
        if case_row is None:
            raise NotFoundError("risk case not found")
        if _safe_text(case_row.get("status")).upper() == CASE_STATUS_CLOSED:
            raise ConflictError("closed case cannot be assigned")

        conn.execute(
            """
            UPDATE risk_cases
            SET assigned_to = ?, status = ?
            WHERE id = ?
            """,
            (normalized_assignee, CASE_STATUS_ASSIGNED, normalized_case_id),
        )
        _insert_case_action(
            conn,
            case_id=normalized_case_id,
            action_type="ASSIGN",
            operator=operator,
            action_note=_safe_text(action_note, f"指派给 {normalized_assignee}"),
        )
        updated = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
        conn.commit()
    return updated or {"id": normalized_case_id}


def close_case(
    *,
    case_id: int,
    resolution_note: str,
    operator: str,
    action_note: str = "",
    department_scope: str | None = None,
) -> dict[str, Any]:
    normalized_case_id = _safe_int(case_id, 0)
    if normalized_case_id <= 0:
        raise ValidationError("invalid case id")

    normalized_note = _safe_text(resolution_note)
    if not normalized_note:
        raise ValidationError("resolution_note is required")

    with get_conn() as conn:
        case_row = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
        if case_row is None:
            raise NotFoundError("risk case not found")
        if _safe_text(case_row.get("status")).upper() == CASE_STATUS_CLOSED:
            raise ConflictError("risk case already closed")

        closed_at = _now_text()
        conn.execute(
            """
            UPDATE risk_cases
            SET status = ?, resolution_note = ?, closed_at = ?
            WHERE id = ?
            """,
            (CASE_STATUS_CLOSED, normalized_note, closed_at, normalized_case_id),
        )
        _insert_case_action(
            conn,
            case_id=normalized_case_id,
            action_type="CLOSE",
            operator=operator,
            action_note=_safe_text(action_note, normalized_note),
        )
        updated = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
        conn.commit()
    return updated or {"id": normalized_case_id}


def adjust_case_score(
    *,
    case_id: int,
    risk_score: int,
    operator: str,
    action_note: str = "",
    department_scope: str | None = None,
) -> dict[str, Any]:
    normalized_case_id = _safe_int(case_id, 0)
    if normalized_case_id <= 0:
        raise ValidationError("invalid case id")

    normalized_score = _safe_int(risk_score, -1)
    if normalized_score < MIN_RISK_SCORE or normalized_score > MAX_RISK_SCORE:
        raise ValidationError("risk_score must be between 0 and 100")

    with get_conn() as conn:
        case_row = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
        if case_row is None:
            raise NotFoundError("risk case not found")
        if _safe_text(case_row.get("status")).upper() == CASE_STATUS_CLOSED:
            raise ConflictError("closed case cannot be adjusted")

        event_id = _safe_int(case_row.get("event_id"), 0)
        if event_id <= 0:
            raise ValidationError("risk event not found")

        previous_score = _safe_int(case_row.get("risk_score"), 0)
        conn.execute(
            """
            UPDATE risk_events
            SET risk_score = ?
            WHERE id = ?
            """,
            (normalized_score, event_id),
        )
        _insert_case_action(
            conn,
            case_id=normalized_case_id,
            action_type="SCORE_ADJUST",
            operator=operator,
            action_note=_safe_text(action_note, f"risk_score={previous_score}->{normalized_score}"),
        )
        updated = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
        conn.commit()
    return updated or {"id": normalized_case_id}


def find_active_case_by_invoice(
    invoice_id: int,
    *,
    department_scope: str | None = None,
) -> dict[str, Any] | None:
    normalized_invoice_id = _safe_int(invoice_id, 0)
    if normalized_invoice_id <= 0:
        return None

    scoped_department = _normalize_scope_department(department_scope)
    with get_conn() as conn:
        if scoped_department:
            row = conn.execute(
                """
                SELECT c.id
                FROM risk_cases c
                JOIN risk_events e ON e.id = c.event_id
                JOIN invoices i ON i.id = e.invoice_id
                WHERE e.invoice_id = ?
                  AND i.department = ?
                  AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND UPPER(COALESCE(c.status, 'OPEN')) <> 'CLOSED'
                ORDER BY c.id DESC
                LIMIT 1
                """,
                (normalized_invoice_id, scoped_department),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT c.id
                FROM risk_cases c
                JOIN risk_events e ON e.id = c.event_id
                JOIN invoices i ON i.id = e.invoice_id
                WHERE e.invoice_id = ?
                  AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND UPPER(COALESCE(c.status, 'OPEN')) <> 'CLOSED'
                ORDER BY c.id DESC
                LIMIT 1
                """,
                (normalized_invoice_id,),
            ).fetchone()

        if not row:
            return None
        return _fetch_case(conn, _safe_int(row["id"], 0), department_scope=department_scope)


def get_case_detail(case_id: int, department_scope: str | None = None) -> dict[str, Any] | None:
    normalized_case_id = _safe_int(case_id, 0)
    if normalized_case_id <= 0:
        return None

    with get_conn() as conn:
        return _fetch_case(conn, normalized_case_id, department_scope=department_scope)


def list_case_actions(case_id: int, department_scope: str | None = None) -> list[dict[str, Any]]:
    normalized_case_id = _safe_int(case_id, 0)
    if normalized_case_id <= 0:
        return []

    with get_conn() as conn:
        if _normalize_scope_department(department_scope):
            case_row = _fetch_case(conn, normalized_case_id, department_scope=department_scope)
            if case_row is None:
                return []
        rows = conn.execute(
            """
            SELECT id, case_id, action_type, operator, action_note, created_at
            FROM case_actions
            WHERE case_id = ?
            ORDER BY id ASC
            """,
            (normalized_case_id,),
        ).fetchall()
    return [dict(row) for row in rows]
