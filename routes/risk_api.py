from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

from audit import MISSING_REASON_MESSAGE, write_audit_log
from events import event_bus
from events.types import RISK_STAGE, STAGE_CASE_ASSIGNED, STAGE_CASE_CLOSED, STAGE_CASE_CREATED
from services.prompt_ledger_service import get_prompt_ledger_by_trace_id
from services.risk_case_service import (
    ConflictError,
    NotFoundError,
    ValidationError,
    adjust_case_score,
    assign_case,
    close_case,
    create_case_from_event,
    get_case_detail,
    list_case_actions,
)
from utils.db import get_conn, insert_audit_log
from utils.security import current_scope_department, current_user, login_required, require_permission

bp = Blueprint("risk_api", __name__)


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_limit(raw: Any, *, default: int = 100, max_limit: int = 1000) -> int:
    value = _safe_int(raw, default)
    if value <= 0:
        value = default
    return min(value, max_limit)


def _operator_name() -> str:
    user = current_user() or {}
    return (
        _safe_text(user.get("employee_name"))
        or _safe_text(user.get("username"))
        or _safe_text(user.get("employee_no"))
        or "system"
    )


def _operator_user_id() -> int | None:
    user = current_user() or {}
    user_id = _safe_int(user.get("id"), 0)
    return user_id if user_id > 0 else None


def _parse_payload() -> tuple[dict[str, Any], tuple[Any, int] | None]:
    payload = request.get_json(silent=True)
    if request.data and payload is None:
        return {}, (jsonify({"ok": False, "message": "request body must be JSON"}), 400)
    if payload is None:
        return {}, None
    if not isinstance(payload, dict):
        return {}, (jsonify({"ok": False, "message": "request body must be a JSON object"}), 400)
    return payload, None


def _publish_case_stage(stage: str, payload: dict[str, Any]) -> None:
    event_bus.publish(
        RISK_STAGE,
        {
            "stage": stage,
            **dict(payload or {}),
        },
    )


def _case_detail_url(case_id: Any) -> str:
    return url_for("risk_api.risk_case_detail_page", case_id=_safe_int(case_id, 0))


def _record_case_audit_log(*, action_type: str, case_row: dict[str, Any], detail: str) -> None:
    try:
        insert_audit_log(
            action_type=action_type,
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type="risk_case",
            target_id=_safe_int(case_row.get("id"), 0) or None,
            detail=detail,
        )
    except Exception as exc:
        current_app.logger.warning("action=write_audit_log failed action_type=%s err=%s", action_type, exc)


def _require_change_reason_code(payload: dict[str, Any]) -> tuple[str, tuple[Any, int] | None]:
    reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not reason_code:
        return "", (jsonify({"ok": False, "message": MISSING_REASON_MESSAGE}), 400)
    return reason_code, None


def _case_snapshot(case_row: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(case_row or {})
    return {
        "id": _safe_int(row.get("id"), 0),
        "event_id": _safe_int(row.get("event_id"), 0),
        "invoice_id": _safe_int(row.get("invoice_id"), 0),
        "status": _safe_text(row.get("status")).upper(),
        "risk_score": _safe_int(row.get("risk_score"), 0),
        "assigned_to": _safe_text(row.get("assigned_to")),
        "resolution_note": _safe_text(row.get("resolution_note")),
        "trace_id": _safe_text(row.get("trace_id")),
        "closed_at": _safe_text(row.get("closed_at")),
    }


def _write_case_audit(
    *,
    action: str,
    case_id: int,
    before_case: dict[str, Any] | None,
    after_case: dict[str, Any] | None,
    change_reason_code: str,
    trace_id: str,
) -> tuple[Any, int] | None:
    try:
        write_audit_log(
            action=action,
            target_type="risk_case",
            target_id=str(_safe_int(case_id, 0)),
            before_obj=_case_snapshot(before_case),
            after_obj=_case_snapshot(after_case),
            change_reason_code=change_reason_code,
            trace_id=trace_id,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception(
            "action=write_audit_log failed action=%s case_id=%s err=%s",
            action,
            case_id,
            exc,
        )
        return jsonify({"ok": False, "message": "audit log write failed"}), 500
    return None


@bp.post("/risk/events/<int:event_id>/create_case")
@login_required
@require_permission("CREATE_CASE")
def create_case_from_event_api(event_id: int):
    payload, err = _parse_payload()
    if err is not None:
        return err

    operator = _operator_name()
    department_scope = current_scope_department()
    action_note = _safe_text(payload.get("action_note"))

    try:
        case_row = create_case_from_event(
            event_id=event_id,
            operator=operator,
            action_note=action_note,
            department_scope=department_scope,
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except NotFoundError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    except ConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except Exception as exc:
        current_app.logger.exception("action=create_case_from_event failed event_id=%s err=%s", event_id, exc)
        return jsonify({"ok": False, "message": f"create case failed: {exc}"}), 500

    _record_case_audit_log(
        action_type="CREATE_CASE",
        case_row=case_row,
        detail=(
            f"case_id={_safe_int(case_row.get('id'), 0)}; "
            f"event_id={_safe_int(case_row.get('event_id'), event_id)}; "
            f"invoice_id={_safe_int(case_row.get('invoice_id'), 0)}"
        ),
    )
    _record_case_audit_log(
        action_type="CASE_CREATED",
        case_row=case_row,
        detail=(
            f"case_id={_safe_int(case_row.get('id'), 0)}; "
            f"event_id={_safe_int(case_row.get('event_id'), event_id)}; "
            f"invoice_id={_safe_int(case_row.get('invoice_id'), 0)}"
        ),
    )

    try:
        _publish_case_stage(
            STAGE_CASE_CREATED,
            {
                "case_id": _safe_int(case_row.get("id"), 0),
                "event_id": _safe_int(case_row.get("event_id"), event_id),
                "invoice_id": _safe_int(case_row.get("invoice_id"), 0),
                "status": _safe_text(case_row.get("status"), "OPEN").upper(),
                "operator": operator,
            },
        )
    except Exception as exc:
        current_app.logger.warning(
            "action=publish_stage stage=%s case_id=%s err=%s",
            STAGE_CASE_CREATED,
            case_row.get("id"),
            exc,
        )

    return jsonify({"ok": True, "case": case_row, "detail_url": _case_detail_url(case_row.get("id"))})


@bp.post("/risk/cases/<int:case_id>/assign")
@login_required
@require_permission("ASSIGN_CASE")
def assign_case_api(case_id: int):
    payload, err = _parse_payload()
    if err is not None:
        return err

    change_reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    operator = _operator_name()
    department_scope = current_scope_department()
    assigned_to = _safe_text(payload.get("assigned_to"))
    action_note = _safe_text(payload.get("action_note"))
    trace_id = _safe_text(payload.get("trace_id"))
    before_case = get_case_detail(case_id, department_scope=department_scope)

    try:
        case_row = assign_case(
            case_id=case_id,
            assigned_to=assigned_to,
            operator=operator,
            action_note=action_note,
            department_scope=department_scope,
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except NotFoundError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    except ConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except Exception as exc:
        current_app.logger.exception("action=assign_case failed case_id=%s err=%s", case_id, exc)
        return jsonify({"ok": False, "message": f"assign case failed: {exc}"}), 500

    _record_case_audit_log(
        action_type="CASE_ASSIGNED",
        case_row=case_row,
        detail=(
            f"case_id={_safe_int(case_row.get('id'), case_id)}; "
            f"assigned_to={_safe_text(case_row.get('assigned_to'))}; "
            f"event_id={_safe_int(case_row.get('event_id'), 0)}"
        ),
    )
    audit_err = _write_case_audit(
        action="CASE_STATUS_CHANGE",
        case_id=case_id,
        before_case=before_case,
        after_case=case_row,
        change_reason_code=change_reason_code,
        trace_id=trace_id or _safe_text(case_row.get("trace_id")),
    )
    if audit_err is not None:
        return audit_err

    try:
        _publish_case_stage(
            STAGE_CASE_ASSIGNED,
            {
                "case_id": _safe_int(case_row.get("id"), case_id),
                "event_id": _safe_int(case_row.get("event_id"), 0),
                "invoice_id": _safe_int(case_row.get("invoice_id"), 0),
                "assigned_to": _safe_text(case_row.get("assigned_to")),
                "status": _safe_text(case_row.get("status"), "ASSIGNED").upper(),
                "operator": operator,
            },
        )
    except Exception as exc:
        current_app.logger.warning(
            "action=publish_stage stage=%s case_id=%s err=%s",
            STAGE_CASE_ASSIGNED,
            case_row.get("id"),
            exc,
        )

    return jsonify({"ok": True, "case": case_row, "detail_url": _case_detail_url(case_row.get("id"))})


@bp.post("/risk/cases/<int:case_id>/close")
@login_required
@require_permission("CLOSE_CASE")
def close_case_api(case_id: int):
    payload, err = _parse_payload()
    if err is not None:
        return err

    change_reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    operator = _operator_name()
    department_scope = current_scope_department()
    resolution_note = _safe_text(payload.get("resolution_note"))
    action_note = _safe_text(payload.get("action_note"))
    trace_id = _safe_text(payload.get("trace_id"))
    before_case = get_case_detail(case_id, department_scope=department_scope)

    try:
        case_row = close_case(
            case_id=case_id,
            resolution_note=resolution_note,
            operator=operator,
            action_note=action_note,
            department_scope=department_scope,
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except NotFoundError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    except ConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except Exception as exc:
        current_app.logger.exception("action=close_case failed case_id=%s err=%s", case_id, exc)
        return jsonify({"ok": False, "message": f"close case failed: {exc}"}), 500

    _record_case_audit_log(
        action_type="CLOSE_CASE",
        case_row=case_row,
        detail=(
            f"case_id={_safe_int(case_row.get('id'), case_id)}; "
            f"resolution_note={_safe_text(case_row.get('resolution_note'))}; "
            f"closed_at={_safe_text(case_row.get('closed_at'))}"
        ),
    )
    _record_case_audit_log(
        action_type="CASE_CLOSED",
        case_row=case_row,
        detail=(
            f"case_id={_safe_int(case_row.get('id'), case_id)}; "
            f"resolution_note={_safe_text(case_row.get('resolution_note'))}; "
            f"closed_at={_safe_text(case_row.get('closed_at'))}"
        ),
    )
    audit_err = _write_case_audit(
        action="CASE_STATUS_CHANGE",
        case_id=case_id,
        before_case=before_case,
        after_case=case_row,
        change_reason_code=change_reason_code,
        trace_id=trace_id or _safe_text(case_row.get("trace_id")),
    )
    if audit_err is not None:
        return audit_err

    try:
        _publish_case_stage(
            STAGE_CASE_CLOSED,
            {
                "case_id": _safe_int(case_row.get("id"), case_id),
                "event_id": _safe_int(case_row.get("event_id"), 0),
                "invoice_id": _safe_int(case_row.get("invoice_id"), 0),
                "status": _safe_text(case_row.get("status"), "CLOSED").upper(),
                "resolution_note": _safe_text(case_row.get("resolution_note")),
                "closed_at": _safe_text(case_row.get("closed_at")),
                "operator": operator,
            },
        )
    except Exception as exc:
        current_app.logger.warning(
            "action=publish_stage stage=%s case_id=%s err=%s",
            STAGE_CASE_CLOSED,
            case_row.get("id"),
            exc,
        )

    return jsonify({"ok": True, "case": case_row, "detail_url": _case_detail_url(case_row.get("id"))})


@bp.post("/api/risk/cases/<int:case_id>/score")
@login_required
@require_permission("ASSIGN_CASE")
def adjust_case_score_api(case_id: int):
    payload, err = _parse_payload()
    if err is not None:
        return err

    change_reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    operator = _operator_name()
    department_scope = current_scope_department()
    risk_score = _safe_int(payload.get("risk_score"), -1)
    action_note = _safe_text(payload.get("action_note"))
    trace_id = _safe_text(payload.get("trace_id"))
    before_case = get_case_detail(case_id, department_scope=department_scope)

    try:
        case_row = adjust_case_score(
            case_id=case_id,
            risk_score=risk_score,
            operator=operator,
            action_note=action_note,
            department_scope=department_scope,
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except NotFoundError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    except ConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except Exception as exc:
        current_app.logger.exception("action=adjust_case_score failed case_id=%s err=%s", case_id, exc)
        return jsonify({"ok": False, "message": f"adjust case score failed: {exc}"}), 500

    _record_case_audit_log(
        action_type="CASE_SCORE_ADJUST",
        case_row=case_row,
        detail=(
            f"case_id={_safe_int(case_row.get('id'), case_id)}; "
            f"risk_score={_safe_int((before_case or {}).get('risk_score'), 0)}->{_safe_int(case_row.get('risk_score'), 0)}; "
            f"event_id={_safe_int(case_row.get('event_id'), 0)}"
        ),
    )
    audit_err = _write_case_audit(
        action="CASE_SCORE_ADJUST",
        case_id=case_id,
        before_case=before_case,
        after_case=case_row,
        change_reason_code=change_reason_code,
        trace_id=trace_id or _safe_text(case_row.get("trace_id")),
    )
    if audit_err is not None:
        return audit_err

    return jsonify({"ok": True, "case": case_row, "detail_url": _case_detail_url(case_row.get("id"))})


@bp.get("/api/risk/events")
@login_required
@require_permission("VIEW_DASHBOARD")
def list_risk_events_api():
    scoped_department = current_scope_department()
    invoice_id = _safe_int(request.args.get("invoice_id"), 0)
    limit = _safe_limit(request.args.get("limit"), default=100, max_limit=1000)

    sql = [
        """
        SELECT
            re.id,
            re.invoice_id,
            UPPER(COALESCE(re.risk_level, '')) AS risk_level,
            COALESCE(re.risk_score, 0) AS risk_score,
            re.trace_id,
            re.created_at
        FROM risk_events re
        JOIN invoices i ON i.id = re.invoice_id
        WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
        """
    ]
    params: list[Any] = []
    if scoped_department:
        sql.append("AND i.department = ?")
        params.append(scoped_department)
    if invoice_id > 0:
        sql.append("AND re.invoice_id = ?")
        params.append(invoice_id)
    sql.append("ORDER BY re.id DESC LIMIT ?")
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(params)).fetchall()

    events = [
        {
            "id": _safe_int(row["id"], 0),
            "invoice_id": _safe_int(row["invoice_id"], 0),
            "risk_level": _safe_text(row["risk_level"]).upper(),
            "risk_score": _safe_int(row["risk_score"], 0),
            "trace_id": _safe_text(row["trace_id"]),
            "created_at": _safe_text(row["created_at"]),
        }
        for row in rows
    ]
    return jsonify({"ok": True, "events": events, "count": len(events)})


@bp.get("/api/risk/cases")
@login_required
@require_permission("VIEW_DASHBOARD")
def list_risk_cases_api():
    scoped_department = current_scope_department()
    event_id = _safe_int(request.args.get("event_id"), 0)
    limit = _safe_limit(request.args.get("limit"), default=100, max_limit=1000)

    sql = [
        """
        SELECT
            c.id,
            c.event_id,
            c.assigned_to,
            c.status,
            c.created_at,
            c.closed_at,
            e.invoice_id,
            UPPER(COALESCE(e.risk_level, '')) AS risk_level,
            COALESCE(e.risk_score, 0) AS risk_score,
            e.trace_id
        FROM risk_cases c
        JOIN risk_events e ON e.id = c.event_id
        JOIN invoices i ON i.id = e.invoice_id
        WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
        """
    ]
    params: list[Any] = []
    if scoped_department:
        sql.append("AND i.department = ?")
        params.append(scoped_department)
    if event_id > 0:
        sql.append("AND c.event_id = ?")
        params.append(event_id)
    sql.append("ORDER BY c.id DESC LIMIT ?")
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(params)).fetchall()

    cases = [
        {
            "id": _safe_int(row["id"], 0),
            "event_id": _safe_int(row["event_id"], 0),
            "invoice_id": _safe_int(row["invoice_id"], 0),
            "risk_level": _safe_text(row["risk_level"]).upper(),
            "risk_score": _safe_int(row["risk_score"], 0),
            "trace_id": _safe_text(row["trace_id"]),
            "assigned_to": _safe_text(row["assigned_to"]),
            "status": _safe_text(row["status"]).upper(),
            "created_at": _safe_text(row["created_at"]),
            "closed_at": _safe_text(row["closed_at"]),
        }
        for row in rows
    ]
    return jsonify({"ok": True, "cases": cases, "count": len(cases)})


@bp.get("/risk/cases/<int:case_id>/detail")
@login_required
@require_permission("VIEW_INVOICES")
def risk_case_detail_page(case_id: int):
    department_scope = current_scope_department()
    case = get_case_detail(case_id, department_scope=department_scope)
    if case is None:
        return render_template("risk_case_detail.html", case=None, actions=[]), 404

    actions = list_case_actions(case_id, department_scope=department_scope)
    return render_template("risk_case_detail.html", case=case, actions=actions)


@bp.get("/api/ai/ledger/<string:trace_id>")
@login_required
@require_permission("VIEW_AI_LEDGER")
def ai_prompt_ledger_api(trace_id: str):
    ledger = get_prompt_ledger_by_trace_id(trace_id, department_scope=current_scope_department())
    if ledger is None:
        return jsonify({"ok": False, "trace_id": str(trace_id or ""), "message": "not found"})

    output_json = ledger.get("output_json")
    if not isinstance(output_json, dict):
        output_json = {}

    return jsonify(
        {
            "ok": True,
            "trace_id": ledger.get("trace_id"),
            "invoice_id": _safe_int(ledger.get("invoice_id"), 0),
            "risk_level": _safe_text(ledger.get("risk_level")).upper(),
            "risk_score": _safe_int(ledger.get("risk_score"), 0),
            "provider": _safe_text(ledger.get("provider")),
            "prompt_version": _safe_text(ledger.get("prompt_version")),
            "hash_prev": _safe_text(ledger.get("hash_prev")),
            "hash_curr": _safe_text(ledger.get("hash_curr")),
            "created_at": _safe_text(ledger.get("created_at")),
            "output_json": output_json,
        }
    )
