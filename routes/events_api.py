from __future__ import annotations

from flask import Blueprint, jsonify, request

from events import event_bus
from utils.security import login_required, require_permission

bp = Blueprint("events_api", __name__)


@bp.get("/api/events/poll")
@login_required
@require_permission("VIEW_DASHBOARD")
def events_poll():
    cursor_raw = str(request.args.get("cursor", "0")).strip()
    try:
        cursor = int(cursor_raw)
    except Exception:
        return jsonify({"ok": False, "message": "cursor must be an integer"}), 400
    if cursor < 0:
        return jsonify({"ok": False, "message": "cursor must be >= 0"}), 400

    events, new_cursor = event_bus.get_since(cursor)
    return jsonify({"ok": True, "events": events, "cursor": new_cursor})
