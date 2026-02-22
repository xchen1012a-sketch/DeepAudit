from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app import app as flask_app
from utils.db import get_conn, get_user_permissions, insert_invoice, list_invoices
from utils.security import SESSION_CSRF_TOKEN_KEY, SESSION_USER_ID_KEY


@pytest.fixture(scope="session")
def app_instance():
    flask_app.config["TESTING"] = True
    return flask_app


def _set_must_change_password(user_id: int, value: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET must_change_password = ? WHERE id = ?", (int(value), int(user_id)))
        conn.commit()


def _find_view_invoices_user() -> tuple[int, int] | None:
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
        if "VIEW_INVOICES" in perms:
            return user_id, int(row["must_change_password"] or 0)
    return None


@pytest.fixture(scope="session")
def viewer_user_id():
    found = _find_view_invoices_user()
    if found is None:
        pytest.skip("no active user with VIEW_INVOICES permission")
    user_id, original_must_change = found
    _set_must_change_password(user_id, 0)
    yield user_id
    _set_must_change_password(user_id, original_must_change)


@pytest.fixture
def make_client(app_instance):
    def _make(user_id: int):
        client = app_instance.test_client()
        csrf_token = f"pytest-ledger-csrf-{int(user_id)}-{datetime.now().timestamp()}"
        with client.session_transaction() as session:
            session[SESSION_USER_ID_KEY] = int(user_id)
            session[SESSION_CSRF_TOKEN_KEY] = csrf_token
        return client, csrf_token

    return _make


@pytest.fixture
def created_ids():
    ids: list[int] = []
    yield ids
    if not ids:
        return

    placeholders = ",".join(["?"] * len(ids))
    id_texts = [str(int(i)) for i in ids]
    with get_conn() as conn:
        event_rows = conn.execute(
            f"SELECT id FROM risk_events WHERE invoice_id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
        event_ids = [int(row["id"]) for row in event_rows if int(row["id"]) > 0]

        if event_ids:
            event_placeholders = ",".join(["?"] * len(event_ids))
            case_rows = conn.execute(
                f"SELECT id FROM risk_cases WHERE event_id IN ({event_placeholders})",
                tuple(event_ids),
            ).fetchall()
            case_ids = [int(row["id"]) for row in case_rows if int(row["id"]) > 0]
            if case_ids:
                case_placeholders = ",".join(["?"] * len(case_ids))
                conn.execute(
                    f"DELETE FROM case_actions WHERE case_id IN ({case_placeholders})",
                    tuple(case_ids),
                )
            conn.execute(
                f"DELETE FROM risk_cases WHERE event_id IN ({event_placeholders})",
                tuple(event_ids),
            )
            conn.execute(
                f"DELETE FROM risk_events WHERE id IN ({event_placeholders})",
                tuple(event_ids),
            )

        conn.execute(
            f"DELETE FROM audit_log WHERE target_type = 'invoice' AND target_id IN ({placeholders})",
            tuple(id_texts),
        )
        conn.execute(
            f"DELETE FROM audit_logs WHERE target_type = 'invoice' AND target_id IN ({placeholders})",
            tuple(ids),
        )
        conn.execute(f"DELETE FROM invoices WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()


def _insert_invoice(*, record_state: str, amount: str, invoice_date: str) -> int:
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    suffix = uuid4().hex[:10]
    return insert_invoice(
        {
            "filename": f"pytest_{suffix}.pdf",
            "amount": amount,
            "invoice_date": invoice_date,
            "applicant": "pytest-user",
            "department": "财务部",
            "is_canton_fair": False,
            "hotel_limit": 600,
            "mode": "pytest",
            "raw_json": {"mode": "pytest", "manual_entry": {"seller_name": "pytest-vendor", "expense_category": "差旅住宿"}},
            "created_at": now_text,
            "risk_level": "MEDIUM",
            "risk_reason": "信息缺失",
            "currency": "CNY",
            "fx_flag": False,
            "fx_reason": "",
            "manual_rate": None,
            "manual_cny_amount": None,
            "ai_risk_level": "MEDIUM",
            "ai_analysis_reason": "pytest",
            "status": "PENDING",
            "record_state": record_state,
            "submitted_by_user_id": None,
            "submitter_department": "财务部",
            "submitter_name": "pytest-user",
            "submitter_no": "PY001",
        }
    )


def test_draft_not_in_default_ledger_list(created_ids):
    draft_id = _insert_invoice(record_state="DRAFT", amount="", invoice_date="")
    created_ids.append(draft_id)

    ledger_rows = list_invoices(limit=5000)
    draft_rows = list_invoices(limit=5000, record_state="DRAFT")

    assert all(int(row.get("id", 0)) != draft_id for row in ledger_rows)
    assert any(int(row.get("id", 0)) == draft_id for row in draft_rows)


def test_ledger_evidence_has_six_sections(viewer_user_id: int, make_client, created_ids):
    invoice_id = _insert_invoice(record_state="LEDGER", amount="888.00", invoice_date="2026-02-01")
    created_ids.append(invoice_id)

    client, _ = make_client(viewer_user_id)
    resp = client.get(f"/api/ledger/{invoice_id}/evidence", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    payload = resp.get_json(silent=True) or {}
    assert payload.get("ok") is True

    evidence = payload.get("evidence") or {}
    assert isinstance(evidence.get("raw_voucher"), dict)
    assert isinstance(evidence.get("structured_data"), dict)
    assert isinstance(evidence.get("verification_receipt"), dict)
    assert isinstance(evidence.get("rule_evidence"), dict)
    assert isinstance(evidence.get("approval_chain"), dict)
    assert isinstance(evidence.get("audit_trail"), list)


def test_structured_update_requires_reason_code(viewer_user_id: int, make_client, created_ids):
    invoice_id = _insert_invoice(record_state="DRAFT", amount="", invoice_date="")
    created_ids.append(invoice_id)

    client, csrf = make_client(viewer_user_id)
    resp = client.patch(
        f"/api/ledger/{invoice_id}/structured",
        json={"fields": {"amount": "520.00", "invoice_date": "2026-02-02"}},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400


def test_submit_review_rejects_draft(viewer_user_id: int, make_client, created_ids):
    invoice_id = _insert_invoice(record_state="DRAFT", amount="", invoice_date="")
    created_ids.append(invoice_id)

    client, csrf = make_client(viewer_user_id)
    resp = client.post(
        f"/api/ledger/{invoice_id}/action",
        json={"action": "SUBMIT_REVIEW", "change_reason_code": "SUBMIT_REVIEW", "comment": "pytest"},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


def test_rerun_ai_auto_links_risk_case(app_instance, created_ids, monkeypatch):
    invoice_id = _insert_invoice(record_state="LEDGER", amount="888.00", invoice_date="2026-02-01")
    created_ids.append(invoice_id)

    from routes import invoices as invoices_route

    def _fake_ai_protocol_payload(*, invoice_id: int, invoice: dict, tax_result: dict) -> dict:
        return {
            "status": "success",
            "data": {
                "risk_level": "HIGH",
                "risk_score": 91,
                "summary": "pytest_auto_case",
                "trace_id": f"pytest-trace-{invoice_id}",
                "model": "pytest",
            },
        }

    monkeypatch.setattr(invoices_route, "_build_ai_protocol_payload", _fake_ai_protocol_payload)

    with app_instance.test_request_context("/pytest_rerun_ai_auto_links_risk_case"):
        payload, _, status_code = invoices_route.run_invoice_ai_internal(
            invoice_id,
            publish_events=False,
            create_risk_event=True,
            tax_result_override={"ok": True, "status": "pass", "provider": "pytest"},
        )
    assert status_code == 200
    assert payload.get("status") == "success"

    with get_conn() as conn:
        event_rows = conn.execute(
            "SELECT id FROM risk_events WHERE invoice_id = ? ORDER BY id ASC",
            (int(invoice_id),),
        ).fetchall()
        assert len(event_rows) == 1
        event_id = int(event_rows[0]["id"])

        case_rows = conn.execute(
            """
            SELECT c.id
            FROM risk_cases c
            JOIN risk_events e ON e.id = c.event_id
            WHERE e.invoice_id = ?
            ORDER BY c.id ASC
            """,
            (int(invoice_id),),
        ).fetchall()
        assert len(case_rows) == 1

    # Re-run should not create an additional in-flight risk case for the same invoice.
    with app_instance.test_request_context("/pytest_rerun_ai_auto_links_risk_case"):
        payload, _, status_code = invoices_route.run_invoice_ai_internal(
            invoice_id,
            publish_events=False,
            create_risk_event=True,
            tax_result_override={"ok": True, "status": "pass", "provider": "pytest"},
        )
    assert status_code == 200
    assert payload.get("status") == "success"

    with get_conn() as conn:
        newer_event_rows = conn.execute(
            "SELECT id FROM risk_events WHERE invoice_id = ? ORDER BY id ASC",
            (int(invoice_id),),
        ).fetchall()
        assert len(newer_event_rows) == 2
        assert int(newer_event_rows[-1]["id"]) > event_id

        case_rows = conn.execute(
            """
            SELECT c.id
            FROM risk_cases c
            JOIN risk_events e ON e.id = c.event_id
            WHERE e.invoice_id = ? AND UPPER(COALESCE(c.status, 'OPEN')) <> 'CLOSED'
            ORDER BY c.id ASC
            """,
            (int(invoice_id),),
        ).fetchall()
        assert len(case_rows) == 1
