from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from services.bank_service import get_bank_stats
from tasks.jobs import pull_bank_incremental
from utils.db import insert_audit_log
from utils.security import current_user, login_required, require_permission

bp = Blueprint("bank_api", __name__)


def _bad_request(message: str):
    return jsonify({"ok": False, "message": message}), 400


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


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


def _record_bank_audit(detail: str, *, target_id: int | None = None) -> None:
    try:
        insert_audit_log(
            action_type="BANK_PULL",
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type="bank_transaction",
            target_id=target_id,
            detail=detail,
        )
    except Exception:
        return


@bp.post("/api/bank/pull")
@login_required
@require_permission("PULL_BANK_TXN")
def bank_pull():
    payload = request.get_json(silent=True)
    if request.data and payload is None:
        return _bad_request("request body must be JSON")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _bad_request("request body must be a JSON object")

    cursor_raw = payload.get("cursor")
    if cursor_raw in ("", None):
        cursor: str | None = None
    else:
        cursor = str(cursor_raw).strip()

    limit_raw = payload.get("limit", 20)
    try:
        limit = int(limit_raw)
    except Exception:
        return _bad_request("limit must be an integer")
    if limit <= 0:
        return _bad_request("limit must be > 0")
    if limit > 500:
        limit = 500

    result = pull_bank_incremental(
        run_mode="manual",
        cursor=cursor,
        limit=limit,
        persist_cursor=True,
    )

    status = _safe_text(result.get("status"), "failed")
    imported = _safe_int(result.get("imported"), _safe_int(len(result.get("items") or []), 0))
    saved = _safe_int(result.get("saved"), 0)
    skipped = _safe_int(result.get("skipped"), 0)
    matched = _safe_int(result.get("matched"), 0)
    provider = _safe_text(result.get("provider"), "unknown")
    next_cursor = result.get("next_cursor")
    message = _safe_text(result.get("message"))
    ok = bool(result.get("ok"))

    current_app.logger.info(
        "action=bank_pull run_mode=manual status=%s ok=%s provider=%s imported=%s saved=%s "
        "skipped=%s matched=%s next_cursor=%s",
        status,
        ok,
        provider,
        imported,
        saved,
        skipped,
        matched,
        next_cursor,
    )

    _record_bank_audit(
        detail=(
            f"ok={ok}; "
            "run_mode=manual; "
            f"status={status}; "
            f"cursor={cursor}; "
            f"provider={provider}; "
            f"next_cursor={_safe_text(next_cursor)}; "
            f"imported={imported}; "
            f"saved={saved}; "
            f"skipped={skipped}; "
            f"matched={matched}"
        )
    )

    return jsonify(
        {
            "ok": ok,
            "run_mode": "manual",
            "status": status,
            "provider": provider,
            "imported": imported,
            "saved": saved,
            "skipped": skipped,
            "matched": matched,
            "next_cursor": next_cursor,
            "message": message,
        }
    )


@bp.get("/api/bank/stats")
@login_required
@require_permission("VIEW_BANK_STATS")
def bank_stats():
    try:
        stats = get_bank_stats()
    except Exception as exc:
        current_app.logger.exception("action=bank_stats failed: %s", exc)
        return jsonify({"ok": False, "message": f"failed to load bank stats: {exc}"}), 500
    return jsonify({"ok": True, **stats})
