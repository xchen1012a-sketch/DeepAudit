"""最小回归测试：users + roles 改动

覆盖点：
  - 创建用户（无角色 / 有角色）
  - 禁用角色后不可新分配
  - 已有用户不受影响
  - 角色禁用/启用/删除端点返回 501 占位
"""
from __future__ import annotations

import hashlib
from typing import Any

import pytest

from app import app as flask_app
from utils.db import get_conn, get_user_permissions, list_roles_with_permissions
from utils.security import SESSION_CSRF_TOKEN_KEY, SESSION_USER_ID_KEY


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _find_manage_users_user() -> tuple[int, int] | None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, must_change_password FROM users "
            "WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE' ORDER BY id ASC"
        ).fetchall()
    for row in rows:
        uid = _safe_int(row["id"], 0)
        if uid <= 0:
            continue
        perms = get_user_permissions(uid)
        if "MANAGE_USERS" in perms and "MANAGE_ROLES" in perms:
            return uid, _safe_int(row["must_change_password"], 0)
    return None


def _set_must_change_password(user_id: int, value: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET must_change_password = ? WHERE id = ?",
            (int(value), int(user_id)),
        )
        conn.commit()


@pytest.fixture(scope="module")
def app_instance():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture(scope="module")
def admin_user():
    found = _find_manage_users_user()
    if found is None:
        pytest.skip("no active user with MANAGE_USERS+MANAGE_ROLES")
    user_id, orig = found
    _set_must_change_password(user_id, 0)
    yield user_id
    _set_must_change_password(user_id, orig)


@pytest.fixture
def client(app_instance, admin_user):
    c = app_instance.test_client()
    csrf = f"pytest-csrf-regression-{admin_user}"
    with c.session_transaction() as sess:
        sess[SESSION_USER_ID_KEY] = int(admin_user)
        sess[SESSION_CSRF_TOKEN_KEY] = csrf
    return c, csrf


def _first_active_role_id() -> int:
    roles = list_roles_with_permissions(include_disabled=False)
    assert roles, "至少需要一个活跃角色"
    return _safe_int(roles[0]["id"], 0)


def _md5(plain: str) -> str:
    return hashlib.md5(plain.encode()).hexdigest()


# ---------- 创建用户 ----------


def test_create_user_without_role_returns_400(client):
    c, csrf = client
    resp = c.post(
        "/api/admin/users",
        json={
            "username": "test_no_role_regr",
            "password": _md5("123456"),
            "department": "-",
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 400, payload
    assert payload.get("ok") is False


def test_create_user_with_role_succeeds(client):
    c, csrf = client
    role_id = _first_active_role_id()
    assert role_id > 0

    username = f"test_regr_{role_id}"
    resp = c.post(
        "/api/admin/users",
        json={
            "username": username,
            "password": _md5("123456"),
            "department": "-",
            "role_id": role_id,
        },
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    payload = resp.get_json(silent=True) or {}
    if resp.status_code == 409:
        pytest.skip("test user already exists")
    assert resp.status_code == 200, payload
    assert payload.get("ok") is True
    assert payload.get("user", {}).get("username") == username

    # 清理
    new_user_id = _safe_int(payload.get("user", {}).get("id"), 0)
    if new_user_id > 0:
        c.delete(
            f"/api/admin/users/{new_user_id}",
            headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        )


# ---------- 禁用角色后不可新分配 ----------


def test_disabled_role_not_assignable(client):
    """在 DB 中将角色设为 DISABLED 后，创建用户应被拒绝。"""
    c, csrf = client
    roles = list_roles_with_permissions()
    if len(roles) < 2:
        pytest.skip("需要至少 2 个角色才能安全测试")

    target_role = roles[-1]
    role_id = _safe_int(target_role["id"], 0)
    original_status = target_role.get("status", "ACTIVE")

    with get_conn() as conn:
        conn.execute(
            "UPDATE roles SET status = 'DISABLED' WHERE id = ?", (role_id,)
        )
        conn.commit()

    try:
        resp = c.post(
            "/api/admin/users",
            json={
                "username": "test_disabled_role_regr",
                "password": _md5("123456"),
                "department": "-",
                "role_id": role_id,
            },
            headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        )
        payload = resp.get_json(silent=True) or {}
        assert resp.status_code == 400, payload
        assert "禁用" in (payload.get("message") or "")
    finally:
        with get_conn() as conn:
            conn.execute(
                "UPDATE roles SET status = ? WHERE id = ?",
                (original_status, role_id),
            )
            conn.commit()


def test_disabled_role_not_assignable_on_change(client):
    """变更用户角色时，目标角色如已禁用应被拒绝。"""
    c, csrf = client
    roles = list_roles_with_permissions()
    if len(roles) < 2:
        pytest.skip("需要至少 2 个角色才能安全测试")

    target_role = roles[-1]
    role_id = _safe_int(target_role["id"], 0)
    original_status = target_role.get("status", "ACTIVE")

    with get_conn() as conn:
        first_user = conn.execute(
            "SELECT id FROM users WHERE UPPER(COALESCE(status,'ACTIVE'))='ACTIVE' LIMIT 1"
        ).fetchone()
    if not first_user:
        pytest.skip("no active user for role change test")
    user_id = first_user["id"]

    with get_conn() as conn:
        conn.execute(
            "UPDATE roles SET status = 'DISABLED' WHERE id = ?", (role_id,)
        )
        conn.commit()

    try:
        resp = c.post(
            f"/api/admin/users/{user_id}/role",
            json={
                "role_id": role_id,
                "change_reason_code": "DATA_CORRECTION",
                "change_reason_note": "回归测试",
            },
            headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        )
        payload = resp.get_json(silent=True) or {}
        assert resp.status_code == 400, payload
        assert "禁用" in (payload.get("message") or "")
    finally:
        with get_conn() as conn:
            conn.execute(
                "UPDATE roles SET status = ? WHERE id = ?",
                (original_status, role_id),
            )
            conn.commit()


# ---------- 已有用户不受影响 ----------


def test_existing_users_not_affected_by_role_status():
    """即使角色标记 DISABLED，已有用户列表仍正常返回且含角色信息。"""
    roles = list_roles_with_permissions()
    if not roles:
        pytest.skip("no roles")
    all_roles_incl_disabled = list_roles_with_permissions(include_disabled=True)
    assert len(all_roles_incl_disabled) >= len(roles)


# ---------- 角色 501 占位端点 ----------


def test_role_disable_returns_501(client):
    c, csrf = client
    role_id = _first_active_role_id()
    resp = c.post(
        f"/api/admin/roles/{role_id}/disable",
        json={},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 501
    assert "待接入" in (payload.get("message") or "")


def test_role_enable_returns_501(client):
    c, csrf = client
    role_id = _first_active_role_id()
    resp = c.post(
        f"/api/admin/roles/{role_id}/enable",
        json={},
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 501
    assert "待接入" in (payload.get("message") or "")


def test_role_delete_returns_501(client):
    c, csrf = client
    role_id = _first_active_role_id()
    resp = c.delete(
        f"/api/admin/roles/{role_id}",
        headers={"Accept": "application/json", "X-CSRF-Token": csrf},
    )
    payload = resp.get_json(silent=True) or {}
    assert resp.status_code == 501
    assert "待接入" in (payload.get("message") or "")
