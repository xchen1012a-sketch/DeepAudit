import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest

from app import app as flask_app
from utils.db import create_user_account, get_conn, insert_invoice
from utils.security import SESSION_CSRF_TOKEN_KEY, SESSION_USER_ID_KEY


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


@pytest.fixture(scope="session")
def app_instance():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def make_client(app_instance):
    def _make(user_id: int):
        client = app_instance.test_client()
        csrf_token = f"pytest-ledger-post-{int(user_id)}-{time.time_ns()}"
        with client.session_transaction() as session:
            session[SESSION_USER_ID_KEY] = int(user_id)
            session[SESSION_CSRF_TOKEN_KEY] = csrf_token
        return client, csrf_token

    return _make


@pytest.fixture
def ledger_post_env():
    created_user_ids: list[int] = []
    created_role_ids: list[int] = []
    created_permission_ids: list[int] = []
    created_invoice_ids: list[int] = []

    role_name = f"PYTEST_LEDGER_POST_{uuid4().hex[:12]}"
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        perm_row = conn.execute(
            "SELECT id FROM permissions WHERE permission_key = ? LIMIT 1",
            ("VIEW_INVOICES",),
        ).fetchone()
        if perm_row is None:
            cur = conn.execute(
                "INSERT INTO permissions (permission_key, description) VALUES (?, ?)",
                ("VIEW_INVOICES", "pytest seed"),
            )
            permission_id = int(cur.lastrowid)
            created_permission_ids.append(permission_id)
        else:
            permission_id = int(perm_row["id"])

        role_cur = conn.execute(
            "INSERT INTO roles (role_name, data_scope, created_at) VALUES (?, ?, ?)",
            (role_name, "DEPT", now_text),
        )
        role_id = int(role_cur.lastrowid)
        created_role_ids.append(role_id)

        conn.execute(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            (role_id, int(permission_id)),
        )
        conn.commit()

    def _create_user(*, role_text: str, department: str = "财务部") -> dict[str, Any]:
        username = f"pytest_lp_u_{uuid4().hex[:10]}"
        employee_no = f"PLP{uuid4().hex[:6].upper()}"
        user_row = create_user_account(
            username=username,
            password="ChangeMe!2026",
            department=department,
            employee_name=username,
            employee_no=employee_no,
            role_text=role_text,
            role_id=role_id,
        )
        assert isinstance(user_row, dict), "create_user_account failed"
        user_id = _safe_int(user_row.get("id"), 0)
        assert user_id > 0
        created_user_ids.append(user_id)

        with get_conn() as conn:
            conn.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (user_id,))
            conn.commit()

        return {
            "id": user_id,
            "username": username,
            "employee_no": employee_no,
            "employee_name": username,
            "department": department,
            "role_text": role_text,
        }

    def _create_invoice(
        *,
        submitter: dict[str, Any],
        amount: str = "980.00",
        invoice_date: str = "2026-02-22",
        verify_status: str = "PENDING",
    ) -> int:
        invoice_id = insert_invoice(
            {
                "filename": f"pytest_ledger_post_{uuid4().hex[:10]}.pdf",
                "amount": amount,
                "invoice_date": invoice_date,
                "applicant": submitter["employee_name"],
                "department": submitter["department"],
                "is_canton_fair": False,
                "hotel_limit": 600,
                "mode": "pytest",
                "raw_json": {"mode": "pytest", "manual_entry": {"seller_name": "pytest vendor", "expense_category": "差旅"}},
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "risk_level": "LOW",
                "risk_reason": "pytest",
                "currency": "CNY",
                "fx_flag": False,
                "fx_reason": "",
                "manual_rate": None,
                "manual_cny_amount": None,
                "ai_risk_level": "LOW",
                "ai_analysis_reason": "pytest",
                "status": "PENDING",
                "approval_status": "PENDING",
                "approval_stage": "L1",
                "record_state": "DRAFT",
                "submitted_by_user_id": int(submitter["id"]),
                "submitter_department": submitter["department"],
                "submitter_name": submitter["employee_name"],
                "submitter_no": submitter["employee_no"],
                "rule_hit_id": "RULE_PYTEST",
                "rule_explain": "pytest rule",
                "queue_owner_id": "",
            }
        )
        created_invoice_ids.append(int(invoice_id))
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE invoices
                SET verify_status = ?, verify_checked_at = ?, verify_message = ?
                WHERE id = ?
                """,
                (
                    str(verify_status or "PENDING").upper(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "pytest verify",
                    int(invoice_id),
                ),
            )
            conn.commit()
        return int(invoice_id)

    def _record_state(invoice_id: int) -> str:
        with get_conn() as conn:
            row = conn.execute("SELECT record_state FROM invoices WHERE id = ?", (int(invoice_id),)).fetchone()
        if not row:
            return ""
        return str(row["record_state"] or "").upper()

    yield {
        "create_user": _create_user,
        "create_invoice": _create_invoice,
        "record_state": _record_state,
    }

    with get_conn() as conn:
        if created_invoice_ids:
            placeholders = ",".join(["?"] * len(created_invoice_ids))
            id_texts = [str(int(item)) for item in created_invoice_ids]
            conn.execute(
                f"DELETE FROM audit_log WHERE target_type = 'invoice' AND target_id IN ({placeholders})",
                tuple(id_texts),
            )
            conn.execute(
                f"DELETE FROM audit_logs WHERE target_type = 'invoice' AND target_id IN ({placeholders})",
                tuple(created_invoice_ids),
            )
            conn.execute(
                f"DELETE FROM invoices WHERE id IN ({placeholders})",
                tuple(created_invoice_ids),
            )

        if created_user_ids:
            user_placeholders = ",".join(["?"] * len(created_user_ids))
            conn.execute(f"DELETE FROM user_roles WHERE user_id IN ({user_placeholders})", tuple(created_user_ids))
            conn.execute(f"DELETE FROM users WHERE id IN ({user_placeholders})", tuple(created_user_ids))

        if created_role_ids:
            role_placeholders = ",".join(["?"] * len(created_role_ids))
            conn.execute(f"DELETE FROM role_permissions WHERE role_id IN ({role_placeholders})", tuple(created_role_ids))
            conn.execute(f"DELETE FROM roles WHERE id IN ({role_placeholders})", tuple(created_role_ids))

        if created_permission_ids:
            permission_placeholders = ",".join(["?"] * len(created_permission_ids))
            conn.execute(
                f"DELETE FROM permissions WHERE id IN ({permission_placeholders})",
                tuple(created_permission_ids),
            )

        conn.commit()


def test_employee_post_ledger_forbidden(ledger_post_env: dict[str, Any], make_client):
    create_user = ledger_post_env["create_user"]
    create_invoice = ledger_post_env["create_invoice"]

    employee = create_user(role_text="EMPLOYEE", department="财务部")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter, verify_status="PASSED")

    client, csrf_token = make_client(employee["id"])
    resp = client.post(
        f"/api/ledger/{invoice_id}/action",
        json={"action": "POST_LEDGER", "change_reason_code": "DATA_COMPLETION", "comment": "pytest"},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 403
    assert payload.get("ok") is False


def test_fin_staff_post_ledger_requires_verify_pass(ledger_post_env: dict[str, Any], make_client):
    create_user = ledger_post_env["create_user"]
    create_invoice = ledger_post_env["create_invoice"]

    fin_staff = create_user(role_text="FIN_STAFF")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter, verify_status="PENDING")

    client, csrf_token = make_client(fin_staff["id"])
    resp = client.post(
        f"/api/ledger/{invoice_id}/action",
        json={"action": "POST_LEDGER", "change_reason_code": "DATA_COMPLETION", "comment": "pytest"},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 409
    assert payload.get("ok") is False


def test_fin_staff_post_ledger_success_when_verify_pass(ledger_post_env: dict[str, Any], make_client):
    create_user = ledger_post_env["create_user"]
    create_invoice = ledger_post_env["create_invoice"]
    record_state = ledger_post_env["record_state"]

    fin_staff = create_user(role_text="FIN_STAFF")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter, verify_status="PASSED")

    client, csrf_token = make_client(fin_staff["id"])
    resp = client.post(
        f"/api/ledger/{invoice_id}/action",
        json={"action": "POST_LEDGER", "change_reason_code": "DATA_COMPLETION", "comment": "pytest"},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 200
    assert payload.get("ok") is True
    assert record_state(invoice_id) == "LEDGER"


def test_employee_structured_supplement_forbidden(ledger_post_env: dict[str, Any], make_client):
    create_user = ledger_post_env["create_user"]
    create_invoice = ledger_post_env["create_invoice"]

    employee = create_user(role_text="EMPLOYEE", department="财务部")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter, amount="", invoice_date="", verify_status="PENDING")

    client, csrf_token = make_client(employee["id"])
    resp = client.patch(
        f"/api/ledger/{invoice_id}/structured",
        json={
            "change_reason_code": "DATA_COMPLETION",
            "fields": {"amount": "520.00", "invoice_date": "2026-02-22"},
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 403
    assert payload.get("ok") is False


def test_fin_staff_batch_supplement_auto_post_respects_verify(ledger_post_env: dict[str, Any], make_client):
    create_user = ledger_post_env["create_user"]
    create_invoice = ledger_post_env["create_invoice"]
    record_state = ledger_post_env["record_state"]

    fin_staff = create_user(role_text="FIN_STAFF")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter, amount="", invoice_date="", verify_status="PENDING")

    client, csrf_token = make_client(fin_staff["id"])
    resp = client.post(
        "/api/ledger/batch",
        json={
            "action": "SUPPLEMENT",
            "ids": [invoice_id],
            "change_reason_code": "DATA_COMPLETION",
            "comment": "pytest supplement",
            "post_ledger": True,
            "fields": {"amount": "188.00", "invoice_date": "2026-02-20"},
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 200
    assert payload.get("ok") is True
    assert payload.get("success_count") == 1
    assert record_state(invoice_id) == "DRAFT"
