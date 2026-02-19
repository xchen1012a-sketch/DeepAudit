from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

import pytest

from app import app as flask_app
from utils.db import create_user_account, get_conn, insert_invoice
from utils.security import SESSION_CSRF_TOKEN_KEY, SESSION_USER_ID_KEY


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


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
        csrf_token = f"pytest-approval-guard-{int(user_id)}-{time.time_ns()}"
        with client.session_transaction() as session:
            session[SESSION_USER_ID_KEY] = int(user_id)
            session[SESSION_CSRF_TOKEN_KEY] = csrf_token
        return client, csrf_token

    return _make


@pytest.fixture
def approval_guard_env():
    created_user_ids: list[int] = []
    created_role_ids: list[int] = []
    created_permission_ids: list[int] = []
    created_invoice_ids: list[int] = []

    role_name = f"PYTEST_APPROVAL_VIEW_{uuid4().hex[:12]}"
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
        username = f"pytest_u_{uuid4().hex[:10]}"
        employee_no = f"PY{uuid4().hex[:6].upper()}"
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
        amount: str,
        risk_level: str,
        approval_stage: str,
        first_approver_id: str = "",
    ) -> int:
        invoice_id = insert_invoice(
            {
                "filename": f"pytest_approval_{uuid4().hex[:10]}.pdf",
                "amount": amount,
                "invoice_date": "2026-02-17",
                "applicant": submitter["employee_name"],
                "department": submitter["department"],
                "is_canton_fair": False,
                "hotel_limit": 600,
                "mode": "pytest",
                "raw_json": {"mode": "pytest", "manual_entry": {"seller_name": "pytest vendor", "expense_category": "差旅"}},
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "risk_level": risk_level,
                "risk_reason": "pytest",
                "currency": "CNY",
                "fx_flag": False,
                "fx_reason": "",
                "manual_rate": None,
                "manual_cny_amount": None,
                "ai_risk_level": risk_level,
                "ai_analysis_reason": "pytest",
                "status": "PENDING",
                "approval_status": "PENDING",
                "approval_stage": approval_stage,
                "first_approver_id": first_approver_id,
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
                f"DELETE FROM audit_log WHERE target_type = 'approval' AND target_id IN ({placeholders})",
                tuple(id_texts),
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


def _approve_payload(*, comment: str = "pytest pass") -> dict[str, Any]:
    return {
        "action": "APPROVE",
        "change_reason_code": "POLICY_MATCH",
        "comment": comment,
    }


def test_employee_approval_api_forbidden_403_cn(approval_guard_env: dict[str, Callable[..., Any]], make_client):
    create_user = approval_guard_env["create_user"]
    create_invoice = approval_guard_env["create_invoice"]

    employee = create_user(role_text="EMPLOYEE")
    submitter = create_user(role_text="FIN_MANAGER")
    invoice_id = create_invoice(
        submitter=submitter,
        amount="880.00",
        risk_level="LOW",
        approval_stage="L1",
    )

    client, csrf_token = make_client(employee["id"])
    resp = client.post(
        f"/api/approvals/{invoice_id}/action",
        json=_approve_payload(),
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 403
    assert payload.get("ok") is False
    assert _contains_chinese(str(payload.get("message") or ""))


def test_fin_staff_approval_center_forbidden_403_cn(approval_guard_env: dict[str, Callable[..., Any]], make_client):
    create_user = approval_guard_env["create_user"]
    fin_staff = create_user(role_text="FIN_STAFF")

    client, _ = make_client(fin_staff["id"])
    resp = client.get("/approval_center", headers={"Accept": "text/html"})
    body = resp.get_data(as_text=True)

    assert resp.status_code == 403
    assert _contains_chinese(body)


def test_fin_manager_can_list_and_approve_pending(approval_guard_env: dict[str, Callable[..., Any]], make_client):
    create_user = approval_guard_env["create_user"]
    create_invoice = approval_guard_env["create_invoice"]

    fin_manager = create_user(role_text="FIN_MANAGER")
    submitter = create_user(role_text="EMPLOYEE")
    invoice_id = create_invoice(
        submitter=submitter,
        amount="990.00",
        risk_level="LOW",
        approval_stage="L1",
    )

    client, csrf_token = make_client(fin_manager["id"])
    list_resp = client.get("/api/approvals?inbox=all&limit=2000", headers={"Accept": "application/json"})
    list_payload = list_resp.get_json(silent=True) or {}

    assert list_resp.status_code == 200
    assert list_payload.get("ok") is True
    rows = list_payload.get("data") or []
    assert any(_safe_int(row.get("id"), 0) == invoice_id for row in rows)

    action_resp = client.post(
        f"/api/approvals/{invoice_id}/action",
        json=_approve_payload(),
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    action_payload = action_resp.get_json(silent=True) or {}

    assert action_resp.status_code == 200
    assert action_payload.get("ok") is True
    assert str(action_payload.get("status") or "").upper() == "APPROVED"
    assert str(action_payload.get("stage") or "").upper() == "DONE"


def test_cfo_can_finalize_l2_approval(approval_guard_env: dict[str, Callable[..., Any]], make_client):
    create_user = approval_guard_env["create_user"]
    create_invoice = approval_guard_env["create_invoice"]

    l1_reviewer = create_user(role_text="FIN_MANAGER")
    cfo = create_user(role_text="CFO")
    invoice_id = create_invoice(
        submitter=l1_reviewer,
        amount="9200.00",
        risk_level="HIGH",
        approval_stage="L2",
        first_approver_id=l1_reviewer["username"],
    )

    client, csrf_token = make_client(cfo["id"])
    resp = client.post(
        f"/api/approvals/{invoice_id}/action",
        json=_approve_payload(comment="cfo final approve"),
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 200
    assert payload.get("ok") is True
    assert str(payload.get("status") or "").upper() == "APPROVED"
    assert str(payload.get("stage") or "").upper() == "DONE"


def test_governance_and_approval_dual_role_self_recusal_forbidden(
    approval_guard_env: dict[str, Callable[..., Any]],
    make_client,
):
    create_user = approval_guard_env["create_user"]
    create_invoice = approval_guard_env["create_invoice"]

    mixed_role_user = create_user(role_text="FIN_MANAGER,GOVERNANCE_ADMIN")
    invoice_id = create_invoice(
        submitter=mixed_role_user,
        amount="1200.00",
        risk_level="LOW",
        approval_stage="L1",
    )

    client, csrf_token = make_client(mixed_role_user["id"])
    resp = client.post(
        f"/api/approvals/{invoice_id}/action",
        json=_approve_payload(comment="should be blocked"),
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    payload = resp.get_json(silent=True) or {}

    assert resp.status_code == 403
    assert payload.get("ok") is False
    assert _contains_chinese(str(payload.get("message") or ""))
    assert "回避" in str(payload.get("message") or "")


def test_system_admin_has_full_approval_control(approval_guard_env: dict[str, Callable[..., Any]], make_client):
    create_user = approval_guard_env["create_user"]
    create_invoice = approval_guard_env["create_invoice"]

    system_admin = create_user(role_text="SYSTEM_ADMIN")
    invoice_id = create_invoice(
        submitter=system_admin,
        amount="1880.00",
        risk_level="LOW",
        approval_stage="L1",
    )

    client, csrf_token = make_client(system_admin["id"])
    list_resp = client.get("/api/approvals?inbox=all&limit=2000", headers={"Accept": "application/json"})
    list_payload = list_resp.get_json(silent=True) or {}

    assert list_resp.status_code == 200
    assert list_payload.get("ok") is True
    rows = list_payload.get("data") or []
    assert any(_safe_int(row.get("id"), 0) == invoice_id for row in rows)

    action_resp = client.post(
        f"/api/approvals/{invoice_id}/action",
        json=_approve_payload(comment="system admin approve"),
        headers={"Accept": "application/json", "X-CSRF-Token": csrf_token},
    )
    action_payload = action_resp.get_json(silent=True) or {}

    assert action_resp.status_code == 200
    assert action_payload.get("ok") is True
    assert str(action_payload.get("status") or "").upper() == "APPROVED"
    assert str(action_payload.get("stage") or "").upper() == "DONE"
