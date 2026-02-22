from __future__ import annotations

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
        csrf_token = f"pytest-ledger-return-{int(user_id)}-{time.time_ns()}"
        with client.session_transaction() as session:
            session[SESSION_USER_ID_KEY] = int(user_id)
            session[SESSION_CSRF_TOKEN_KEY] = csrf_token
        return client, csrf_token

    return _make


@pytest.fixture
def ledger_return_env():
    created_user_ids: list[int] = []
    created_role_ids: list[int] = []
    created_permission_ids: list[int] = []
    created_invoice_ids: list[int] = []

    role_name = f"PYTEST_LEDGER_RETURN_{uuid4().hex[:12]}"
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
        username = f"pytest_lr_u_{uuid4().hex[:10]}"
        employee_no = f"PLR{uuid4().hex[:6].upper()}"
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

    def _create_invoice(*, submitter: dict[str, Any], amount: str = "980.00") -> int:
        invoice_id = insert_invoice(
            {
                "filename": f"pytest_ledger_return_{uuid4().hex[:10]}.pdf",
                "amount": amount,
                "invoice_date": "2026-02-22",
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
                "status": "APPROVED",
                "approval_status": "APPROVED",
                "approval_stage": "DONE",
                "record_state": "LEDGER",
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
        return int(invoice_id)

    yield {
        "create_user": _create_user,
        "create_invoice": _create_invoice,
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


def _return_payload(*, comment: str = "need fix") -> dict[str, Any]:
    return {
        "action": "RETURN_TO_DRAFT",
        "change_reason_code": "RETURN_FOR_COMPLETION",
        "comment": comment,
    }


def test_fin_staff_return_to_draft_forbidden(ledger_return_env: dict[str, Any], make_client):
    create_user = ledger_return_env["create_user"]
    create_invoice = ledger_return_env["create_invoice"]

    fin_staff = create_user(role_text="FIN_STAFF")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter)

    client, csrf_token = make_client(fin_staff["id"])
    resp = client.post(
        f"/api/ledger/{invoice_id}/action",
        json=_return_payload(comment="staff try return"),
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 403
    assert payload.get("ok") is False
    assert "经理及以上" in str(payload.get("msg") or "")


def test_fin_staff_batch_return_forbidden(ledger_return_env: dict[str, Any], make_client):
    create_user = ledger_return_env["create_user"]
    create_invoice = ledger_return_env["create_invoice"]

    fin_staff = create_user(role_text="FIN_STAFF")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(submitter=submitter)

    client, csrf_token = make_client(fin_staff["id"])
    resp = client.post(
        "/api/ledger/batch",
        json={
            "action": "RETURN_TO_DRAFT",
            "ids": [invoice_id],
            "change_reason_code": "RETURN_FOR_COMPLETION",
            "comment": "staff batch try return",
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 403
    assert payload.get("ok") is False
    assert "经理及以上" in str(payload.get("msg") or "")


def test_fin_manager_can_batch_return_and_write_audit(ledger_return_env: dict[str, Any], make_client):
    create_user = ledger_return_env["create_user"]
    create_invoice = ledger_return_env["create_invoice"]

    fin_manager = create_user(role_text="FIN_MANAGER")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id_1 = create_invoice(submitter=submitter, amount="880.00")
    invoice_id_2 = create_invoice(submitter=submitter, amount="1280.00")

    client, csrf_token = make_client(fin_manager["id"])
    resp = client.post(
        "/api/ledger/batch",
        json={
            "action": "RETURN_TO_DRAFT",
            "ids": [invoice_id_1, invoice_id_2],
            "change_reason_code": "RETURN_FOR_COMPLETION",
            "comment": "manager batch return",
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 200
    assert payload.get("ok") is True
    assert int(payload.get("success_count") or 0) == 2
    assert int(payload.get("failed_count") or 0) == 0

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, record_state
            FROM invoices
            WHERE id IN (?, ?)
            ORDER BY id ASC
            """,
            (invoice_id_1, invoice_id_2),
        ).fetchall()
        assert len(rows) == 2
        assert all(str(row["record_state"]).upper() == "DRAFT" for row in rows)

        audit_rows = conn.execute(
            """
            SELECT action
            FROM audit_log
            WHERE target_type = 'invoice' AND target_id IN (?, ?)
            ORDER BY id DESC
            LIMIT 10
            """,
            (str(invoice_id_1), str(invoice_id_2)),
        ).fetchall()
        actions = [str(row["action"]).upper() for row in audit_rows]
        assert actions.count("BATCH_RETURN_TO_DRAFT") >= 2
