from __future__ import annotations

import json
import re
import time
from typing import Any

import pytest

from app import app as flask_app
from services import governance_rule_service
from utils.db import get_conn, get_user_permissions
from utils.security import SESSION_CSRF_TOKEN_KEY, SESSION_USER_ID_KEY

RULE_KEY = "HOTEL_LIMIT_NORMAL"
RULE_API_BASE = "/api/governance/rules"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def _decode_threshold_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except Exception:
            return {}
        if isinstance(payload, dict):
            return payload
    return {}


def _get_rule_by_key(rule_key: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, rule_key, enabled, threshold, threshold_json, severity, version, updated_by, updated_at
            FROM governance_rules
            WHERE UPPER(rule_key) = ?
            LIMIT 1
            """,
            (str(rule_key).strip().upper(),),
        ).fetchone()
    if row is None:
        raise AssertionError(f"rule not found: {rule_key}")
    threshold_json = str(row["threshold_json"] or "").strip()
    return {
        "id": int(row["id"]),
        "rule_key": str(row["rule_key"] or "").strip().upper(),
        "enabled": bool(int(row["enabled"] or 0)),
        "threshold": float(row["threshold"] or 0),
        "threshold_json": threshold_json,
        "threshold_json_obj": _decode_threshold_json(threshold_json),
        "severity": str(row["severity"] or "").strip().upper() or "MEDIUM",
        "version": int(row["version"] or 0),
        "updated_by": str(row["updated_by"] or "").strip(),
        "updated_at": str(row["updated_at"] or "").strip(),
    }


def _restore_rule(snapshot: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE governance_rules
            SET enabled = ?, threshold = ?, threshold_json = ?, severity = ?, version = ?, updated_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                1 if snapshot.get("enabled") else 0,
                float(snapshot.get("threshold") or 0),
                str(snapshot.get("threshold_json") or "{}"),
                str(snapshot.get("severity") or "MEDIUM"),
                int(snapshot.get("version") or 1),
                str(snapshot.get("updated_by") or "pytest"),
                str(snapshot.get("updated_at") or "1970-01-01 00:00:00"),
                int(snapshot["id"]),
            ),
        )
        conn.commit()
    governance_rule_service.clear_cache()


def _set_must_change_password(user_id: int, value: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET must_change_password = ? WHERE id = ?", (int(value), int(user_id)))
        conn.commit()


def _find_user_id(*, requires_manage_rules: bool) -> tuple[int, int] | None:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, must_change_password, status
            FROM users
            WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
            ORDER BY id ASC
            """
        ).fetchall()
    for row in rows:
        user_id = int(row["id"])
        perms = get_user_permissions(user_id)
        has_manage_rules = "MANAGE_RULES" in perms
        if requires_manage_rules and has_manage_rules:
            return user_id, int(row["must_change_password"] or 0)
        if not requires_manage_rules and not has_manage_rules:
            return user_id, int(row["must_change_password"] or 0)
    return None


def _pick_invoice_id() -> int:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, invoice_date, COALESCE(is_canton_fair, 0) AS is_canton_fair
            FROM invoices
            ORDER BY id ASC
            """
        ).fetchall()
    for row in rows:
        amount = _to_float(row["amount"])
        if amount is None or amount <= 1:
            continue
        invoice_date = str(row["invoice_date"] or "").strip()
        if not invoice_date:
            continue
        if int(row["is_canton_fair"] or 0) != 0:
            continue
        return int(row["id"])
    for row in rows:
        amount = _to_float(row["amount"])
        if amount is not None and amount > 0:
            return int(row["id"])
    raise AssertionError("no invoice record available for governance tests")


def _has_rule_hit(evidence: list[dict[str, Any]], key: str) -> bool:
    for item in evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() != "rule_hit":
            continue
        if str(item.get("key") or "") == key:
            return True
    return False


def _has_rule_hit_limit(evidence: list[dict[str, Any]], key: str, expected_limit: float) -> bool:
    for item in evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() != "rule_hit":
            continue
        if str(item.get("key") or "") != key:
            continue
        value = str(item.get("value") or "")
        match = re.search(r"limit=([0-9]+(?:\.[0-9]+)?)", value)
        if not match:
            continue
        if abs(float(match.group(1)) - expected_limit) < 1e-9:
            return True
    return False


def _count_rule_update_logs(client, rule_key: str) -> int:
    normalized_rule_key = str(rule_key or "").strip().upper()
    if not normalized_rule_key:
        return 0
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM audit_log al
            JOIN governance_rules gr ON CAST(gr.id AS TEXT) = al.target_id
            WHERE al.action = 'RULE_UPDATE'
              AND al.target_type = 'rule'
              AND UPPER(COALESCE(gr.rule_key, '')) = ?
            """,
            (normalized_rule_key,),
        ).fetchone()
    return int((row or {})["c"] or 0)


def _post_rule_update(client, csrf_token: str, rule_id: int, payload: dict[str, Any]):
    body = dict(payload or {})
    body.setdefault("change_reason_code", "DATA_CORRECTION")
    return client.post(
        f"{RULE_API_BASE}/{int(rule_id)}",
        json=body,
        headers={
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
        },
    )


def _post_invoice_ai(client, csrf_token: str, invoice_id: int):
    return client.post(
        f"/invoice/{int(invoice_id)}/ai",
        json={},
        headers={
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
        },
    )


@pytest.fixture(scope="session")
def app_instance():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture(scope="session")
def admin_user_id():
    found = _find_user_id(requires_manage_rules=True)
    if found is None:
        pytest.skip("no active user with MANAGE_RULES permission")
    user_id, original_must_change = found
    _set_must_change_password(user_id, 0)
    yield user_id
    _set_must_change_password(user_id, original_must_change)


@pytest.fixture(scope="session")
def non_governance_user_id():
    found = _find_user_id(requires_manage_rules=False)
    if found is None:
        pytest.skip("no active user without MANAGE_RULES permission")
    user_id, original_must_change = found
    _set_must_change_password(user_id, 0)
    yield user_id
    _set_must_change_password(user_id, original_must_change)


@pytest.fixture
def make_client(app_instance):
    def _make(user_id: int):
        client = app_instance.test_client()
        csrf_token = f"pytest-csrf-{int(user_id)}-{time.time_ns()}"
        with client.session_transaction() as session:
            session[SESSION_USER_ID_KEY] = int(user_id)
            session[SESSION_CSRF_TOKEN_KEY] = csrf_token
        return client, csrf_token

    return _make


@pytest.fixture
def preserve_rule_state():
    snapshots: list[dict[str, Any]] = []

    def _capture(rule_key: str) -> dict[str, Any]:
        snapshot = _get_rule_by_key(rule_key)
        snapshots.append(snapshot)
        return snapshot

    yield _capture

    for snapshot in reversed(snapshots):
        _restore_rule(snapshot)


def test_b1_threshold_json_fallback_and_invalid_json(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    preserve_rule_state(RULE_KEY)
    client, csrf_token = make_client(admin_user_id)
    rule = _get_rule_by_key(RULE_KEY)
    rule_id = int(rule["id"])

    resp_null = _post_rule_update(client, csrf_token, rule_id, {"threshold_json": None})
    assert resp_null.status_code == 200
    assert (resp_null.get_json(silent=True) or {}).get("ok") is True
    assert _get_rule_by_key(RULE_KEY)["threshold_json_obj"]

    resp_empty = _post_rule_update(client, csrf_token, rule_id, {"threshold_json": ""})
    assert resp_empty.status_code == 200
    assert (resp_empty.get_json(silent=True) or {}).get("ok") is True
    assert _get_rule_by_key(RULE_KEY)["threshold_json_obj"]

    before_bad = _get_rule_by_key(RULE_KEY)
    resp_bad = _post_rule_update(client, csrf_token, rule_id, {"threshold_json": "{invalid_json"})
    assert resp_bad.status_code == 400
    bad_payload = resp_bad.get_json(silent=True) or {}
    assert bad_payload.get("ok") is False
    assert bad_payload.get("msg") == "invalid_threshold_json"

    after_bad = _get_rule_by_key(RULE_KEY)
    assert after_bad["version"] == before_bad["version"]
    assert after_bad["threshold_json"] == before_bad["threshold_json"]


def test_b2_rule_update_takes_effect_immediately(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    preserve_rule_state(RULE_KEY)
    client, csrf_token = make_client(admin_user_id)
    invoice_id = _pick_invoice_id()
    rule = _get_rule_by_key(RULE_KEY)

    resp_update = _post_rule_update(
        client,
        csrf_token,
        int(rule["id"]),
        {"enabled": True, "threshold": 1.0, "threshold_json": {"limit": 1.0}},
    )
    assert resp_update.status_code == 200
    assert (resp_update.get_json(silent=True) or {}).get("ok") is True

    resp_ai = _post_invoice_ai(client, csrf_token, invoice_id)
    assert resp_ai.status_code == 200
    ai_payload = resp_ai.get_json(silent=True) or {}
    assert ai_payload.get("status") == "success"
    evidence = ((ai_payload.get("data") or {}).get("evidence") or [])
    assert _has_rule_hit_limit(evidence, RULE_KEY, 1.0)


def test_b3_fast_consecutive_updates_keep_version_monotonic_and_last_write_wins(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    preserve_rule_state(RULE_KEY)
    client_a, csrf_a = make_client(admin_user_id)
    client_b, csrf_b = make_client(admin_user_id)

    before_rule = _get_rule_by_key(RULE_KEY)
    before_audit_count = _count_rule_update_logs(client_a, RULE_KEY)

    resp_a = _post_rule_update(
        client_a,
        csrf_a,
        int(before_rule["id"]),
        {"enabled": True, "threshold": 211.0, "threshold_json": {"limit": 211.0}},
    )
    resp_b = _post_rule_update(
        client_b,
        csrf_b,
        int(before_rule["id"]),
        {"enabled": True, "threshold": 233.0, "threshold_json": {"limit": 233.0}},
    )
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    after_rule = _get_rule_by_key(RULE_KEY)
    assert after_rule["version"] >= before_rule["version"] + 2
    assert abs(float(after_rule["threshold"]) - 233.0) < 1e-9
    assert abs(float(after_rule["threshold_json_obj"].get("limit", 0)) - 233.0) < 1e-9

    after_audit_count = _count_rule_update_logs(client_a, RULE_KEY)
    assert after_audit_count >= before_audit_count + 2


def test_b4_enabled_off_rule_not_used_in_evidence(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    preserve_rule_state(RULE_KEY)
    client, csrf_token = make_client(admin_user_id)
    invoice_id = _pick_invoice_id()
    rule = _get_rule_by_key(RULE_KEY)

    resp_on = _post_rule_update(
        client,
        csrf_token,
        int(rule["id"]),
        {"enabled": True, "threshold": 1.0, "threshold_json": {"limit": 1.0}},
    )
    assert resp_on.status_code == 200

    resp_ai_on = _post_invoice_ai(client, csrf_token, invoice_id)
    assert resp_ai_on.status_code == 200
    evidence_on = (((resp_ai_on.get_json(silent=True) or {}).get("data") or {}).get("evidence") or [])
    assert _has_rule_hit(evidence_on, RULE_KEY)

    resp_off = _post_rule_update(client, csrf_token, int(rule["id"]), {"enabled": False})
    assert resp_off.status_code == 200

    resp_ai_off = _post_invoice_ai(client, csrf_token, invoice_id)
    assert resp_ai_off.status_code == 200
    evidence_off = (((resp_ai_off.get_json(silent=True) or {}).get("data") or {}).get("evidence") or [])
    assert all("HOTEL_LIMIT" not in str(item.get("key") or "") for item in evidence_off if isinstance(item, dict))


def test_b5_permission_regression_non_governance_forbidden_admin_allowed(
    admin_user_id: int,
    non_governance_user_id: int,
    make_client,
    preserve_rule_state,
):
    preserve_rule_state(RULE_KEY)
    admin_client, admin_csrf = make_client(admin_user_id)
    user_client, user_csrf = make_client(non_governance_user_id)
    rule = _get_rule_by_key(RULE_KEY)
    rule_id = int(rule["id"])

    forbidden_resp = _post_rule_update(user_client, user_csrf, rule_id, {"threshold": 321.0})
    assert forbidden_resp.status_code == 403
    fb_payload = forbidden_resp.get_json(silent=True) or {}
    assert fb_payload.get("ok") is False
    assert "error" in fb_payload or "message" in str(fb_payload).lower()

    allowed_resp = _post_rule_update(admin_client, admin_csrf, rule_id, {"threshold": 322.0})
    assert allowed_resp.status_code == 200


def test_b6_rule_threshold_validation_422(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    from utils.db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM governance_rules WHERE UPPER(rule_key) = 'HOTEL_MEDIUM_RATIO' LIMIT 1"
        ).fetchone()
    if not row:
        pytest.skip("HOTEL_MEDIUM_RATIO rule not found")
    ratio_rule_id = int(row["id"])
    preserve_rule_state("HOTEL_MEDIUM_RATIO")

    client, csrf_token = make_client(admin_user_id)
    resp = client.post(
        f"{RULE_API_BASE}/{ratio_rule_id}",
        json={
            "threshold": 1.5,
            "change_reason_code": "MANUAL_ADJUST",
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422
    payload = resp.get_json(silent=True) or {}
    assert payload.get("ok") is False
    err = payload.get("error") or {}
    assert "message_cn" in err or "rule_validation" in str(err).lower()


def test_b7_audit_log_contains_rule_update(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    preserve_rule_state(RULE_KEY)
    client, csrf_token = make_client(admin_user_id)
    rule = _get_rule_by_key(RULE_KEY)
    before_count = _count_rule_update_logs(client, RULE_KEY)

    _post_rule_update(client, csrf_token, int(rule["id"]), {"threshold": 499.0})
    after_count = _count_rule_update_logs(client, RULE_KEY)
    assert after_count >= before_count + 1


def test_b8_list_audit_logs_target_type_target_id(
    admin_user_id: int,
    make_client,
    preserve_rule_state,
):
    from utils.db import list_audit_logs
    preserve_rule_state(RULE_KEY)
    client, csrf_token = make_client(admin_user_id)
    rule = _get_rule_by_key(RULE_KEY)
    rule_id = int(rule["id"])
    _post_rule_update(client, csrf_token, rule_id, {"threshold": 488.0})

    logs = list_audit_logs(limit=50, target_type="rule", target_id=str(rule_id))
    assert isinstance(logs, list)
    rule_logs = [l for l in logs if str(l.get("target_id")) == str(rule_id)]
    assert len(rule_logs) >= 1
    assert any(str(l.get("action_type", "")).upper() == "RULE_UPDATE" for l in rule_logs)
