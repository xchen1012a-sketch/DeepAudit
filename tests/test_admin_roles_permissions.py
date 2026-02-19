from __future__ import annotations

from typing import Any

import pytest

from app import app as flask_app
from audit import MISSING_REASON_MESSAGE
from utils.db import get_conn, get_user_permissions, list_permissions, list_roles_with_permissions
from utils.security import SESSION_CSRF_TOKEN_KEY, SESSION_USER_ID_KEY


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _find_user(*, require_manage_roles: bool) -> tuple[int, int] | None:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, role, must_change_password
            FROM users
            WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
            ORDER BY id ASC
            """
        ).fetchall()

    for row in rows:
        user_id = _safe_int(row["id"], 0)
        if user_id <= 0:
            continue
        role_text = str(row["role"] or "").strip().lower()
        has_manage_roles = "MANAGE_ROLES" in get_user_permissions(user_id)

        if require_manage_roles and has_manage_roles:
            return user_id, _safe_int(row["must_change_password"], 0)

        if not require_manage_roles and not has_manage_roles and "admin" not in role_text:
            return user_id, _safe_int(row["must_change_password"], 0)
    return None


def _set_must_change_password(user_id: int, value: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET must_change_password = ? WHERE id = ?", (int(value), int(user_id)))
        conn.commit()


@pytest.fixture(scope="session")
def app_instance():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture(scope="session")
def manage_roles_user():
    found = _find_user(require_manage_roles=True)
    if found is None:
        pytest.skip("no active user with MANAGE_ROLES permission")
    user_id, original_must_change = found
    _set_must_change_password(user_id, 0)
    yield user_id
    _set_must_change_password(user_id, original_must_change)


@pytest.fixture(scope="session")
def non_manage_roles_user():
    found = _find_user(require_manage_roles=False)
    if found is None:
        pytest.skip("no active user without MANAGE_ROLES permission")
    user_id, original_must_change = found
    _set_must_change_password(user_id, 0)
    yield user_id
    _set_must_change_password(user_id, original_must_change)


@pytest.fixture
def make_client(app_instance):
    def _make(user_id: int):
        client = app_instance.test_client()
        csrf_token = f"pytest-csrf-admin-roles-{int(user_id)}"
        with client.session_transaction() as session:
            session[SESSION_USER_ID_KEY] = int(user_id)
            session[SESSION_CSRF_TOKEN_KEY] = csrf_token
        return client, csrf_token

    return _make


def test_admin_roles_save_requires_change_reason_code(manage_roles_user: int, make_client):
    client, csrf_token = make_client(manage_roles_user)
    roles = list_roles_with_permissions()
    assert roles, "roles should not be empty"
    role = roles[0]
    role_id = _safe_int(role.get("id"), 0)
    assert role_id > 0

    permission_ids = [
        _safe_int(item.get("id"), 0)
        for item in (role.get("permissions") or [])
        if _safe_int(item.get("id"), 0) > 0
    ]

    resp = client.post(
        f"/api/admin/roles/{role_id}/permissions",
        json={
            "permission_ids": permission_ids,
            "data_scope": str(role.get("data_scope") or "DEPT"),
        },
        headers={
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
        },
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 400
    assert payload.get("ok") is False
    assert payload.get("message") == MISSING_REASON_MESSAGE


def test_admin_roles_page_forbidden_returns_cn_html(non_manage_roles_user: int, make_client):
    client, _ = make_client(non_manage_roles_user)
    resp = client.get("/admin/roles", headers={"Accept": "text/html"})
    body = resp.get_data(as_text=True)

    assert resp.status_code == 403
    assert "无权访问当前页面（403）" in body
    assert "建议开通权限" in body


def test_non_system_admin_role_cannot_grant_manage_system(manage_roles_user: int, make_client):
    client, csrf_token = make_client(manage_roles_user)
    roles = list_roles_with_permissions()
    role = next((item for item in roles if str(item.get("role_name") or "").strip() != "系统管理员"), None)
    assert role is not None, "non-system-admin role should exist"
    role_id = _safe_int(role.get("id"), 0)
    assert role_id > 0

    manage_system_perm = next(
        (item for item in list_permissions() if str(item.get("permission_key") or "").strip().upper() == "MANAGE_SYSTEM"),
        None,
    )
    assert manage_system_perm is not None, "MANAGE_SYSTEM permission should exist"
    manage_system_id = _safe_int(manage_system_perm.get("id"), 0)
    assert manage_system_id > 0

    permission_ids = [
        _safe_int(item.get("id"), 0)
        for item in (role.get("permissions") or [])
        if _safe_int(item.get("id"), 0) > 0
    ]
    if manage_system_id not in permission_ids:
        permission_ids.append(manage_system_id)

    resp = client.post(
        f"/api/admin/roles/{role_id}/permissions",
        json={
            "permission_ids": permission_ids,
            "data_scope": str(role.get("data_scope") or "DEPT"),
            "change_reason_code": "DATA_CORRECTION",
            "change_reason_note": "测试系统管理权限边界",
        },
        headers={
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
        },
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 400
    assert payload.get("ok") is False
    assert "仅可授予系统管理员角色" in str(payload.get("message") or "")


def test_system_admin_role_forced_full_permissions(manage_roles_user: int, make_client):
    client, csrf_token = make_client(manage_roles_user)
    roles = list_roles_with_permissions()
    role = next((item for item in roles if str(item.get("role_name") or "").strip() == "系统管理员"), None)
    assert role is not None, "system-admin role should exist"
    role_id = _safe_int(role.get("id"), 0)
    assert role_id > 0

    all_permission_rows = list_permissions()
    all_permission_ids = sorted({
        _safe_int(item.get("id"), 0)
        for item in all_permission_rows
        if _safe_int(item.get("id"), 0) > 0
    })
    assert all_permission_ids, "permission list should not be empty"

    # Submit a subset; backend should auto-correct to full permission set for system-admin role.
    subset_ids = all_permission_ids[:1]
    resp = client.post(
        f"/api/admin/roles/{role_id}/permissions",
        json={
            "permission_ids": subset_ids,
            "data_scope": "DEPT",
            "change_reason_code": "DATA_CORRECTION",
            "change_reason_note": "测试系统管理员全权限兜底",
        },
        headers={
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
        },
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 200
    assert payload.get("ok") is True
    role_payload = payload.get("role") if isinstance(payload.get("role"), dict) else {}
    saved_permission_ids = sorted({
        _safe_int(item.get("id"), 0)
        for item in (role_payload.get("permissions") or [])
        if _safe_int(item.get("id"), 0) > 0
    })
    assert saved_permission_ids == all_permission_ids
    assert str(role_payload.get("data_scope") or "").strip().upper() == "ALL"
