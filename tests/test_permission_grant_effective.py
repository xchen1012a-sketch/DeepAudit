from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from utils.db import create_user_account, get_conn, get_user_by_id
from utils.security import (
    approval_allowed_workflow_roles,
    can_governance,
    can_manage_workflow,
    current_user_permissions,
    current_user_role_keys,
    has_permission,
)


REQUIRED_PERMISSION_KEYS = [
    "CREATE_CASE",
    "ASSIGN_CASE",
    "CLOSE_CASE",
    "MANAGE_USERS",
    "MANAGE_ROLES",
    "MANAGE_RULES",
    "MANAGE_SETTINGS",
    "MANAGE_SYSTEM",
]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@pytest.fixture
def custom_role_user():
    created_user_id = 0
    created_role_id = 0

    role_name = f"PYTEST_PERM_ROLE_{uuid4().hex[:12]}"
    role_text = f"custom_role_{uuid4().hex[:8]}"
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        role_cur = conn.execute(
            """
            INSERT INTO roles (role_name, data_scope, created_at, status, is_deleted)
            VALUES (?, ?, ?, 'ACTIVE', 0)
            """,
            (role_name, "DEPT", now_text),
        )
        created_role_id = _safe_int(role_cur.lastrowid, 0)
        assert created_role_id > 0

        placeholders = ",".join(["?"] * len(REQUIRED_PERMISSION_KEYS))
        permission_rows = conn.execute(
            f"""
            SELECT id, permission_key
            FROM permissions
            WHERE permission_key IN ({placeholders})
            """,
            tuple(REQUIRED_PERMISSION_KEYS),
        ).fetchall()
        permission_id_by_key = {
            str(row["permission_key"] or "").strip().upper(): _safe_int(row["id"], 0)
            for row in permission_rows
            if _safe_int(row["id"], 0) > 0
        }
        missing = sorted(set(REQUIRED_PERMISSION_KEYS) - set(permission_id_by_key))
        assert not missing, f"permissions missing in DB: {missing}"

        for key in REQUIRED_PERMISSION_KEYS:
            conn.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (?, ?)
                ON CONFLICT(role_id, permission_id) DO NOTHING
                """,
                (created_role_id, permission_id_by_key[key]),
            )
        conn.commit()

    created_user = create_user_account(
        username=f"pytest_perm_{uuid4().hex[:10]}",
        password="ChangeMe!2026",
        department="Finance",
        employee_name="pytest permission user",
        employee_no=f"PY{uuid4().hex[:6].upper()}",
        role_text=role_text,
        role_id=created_role_id,
    )
    assert isinstance(created_user, dict), "create_user_account failed"
    created_user_id = _safe_int(created_user.get("id"), 0)
    assert created_user_id > 0

    with get_conn() as conn:
        conn.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (created_user_id,))
        conn.commit()

    user = get_user_by_id(created_user_id)
    assert isinstance(user, dict), "get_user_by_id failed"

    yield user

    with get_conn() as conn:
        if created_user_id > 0:
            conn.execute("DELETE FROM user_roles WHERE user_id = ?", (created_user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (created_user_id,))
        if created_role_id > 0:
            conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (created_role_id,))
            conn.execute("DELETE FROM role_data_scopes WHERE role_id = ?", (created_role_id,))
            conn.execute("DELETE FROM roles WHERE id = ?", (created_role_id,))
        conn.commit()


def test_custom_role_granted_permissions_are_effective(custom_role_user):
    user = custom_role_user
    assert current_user_role_keys(user) == set()

    permissions = current_user_permissions(user)
    for key in REQUIRED_PERMISSION_KEYS:
        assert key in permissions
        assert has_permission(key, user) is True


def test_custom_role_capability_fallback_by_permissions(custom_role_user):
    user = custom_role_user
    assert can_governance(user) is True
    assert can_manage_workflow(user) is True

    allowed_roles = approval_allowed_workflow_roles(user)
    assert "MANAGER" in allowed_roles
    assert "CFO" in allowed_roles
