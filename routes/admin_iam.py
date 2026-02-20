from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from audit import MISSING_REASON_MESSAGE, write_audit_log
from utils.db import (
    DATA_SCOPE_TYPES,
    DEFAULT_RESET_PASSWORD,
    count_users_by_role_id,
    create_department,
    create_position,
    create_role_record,
    create_user_account,
    data_scope_preview_user_count_and_sample,
    delete_department,
    delete_user_account,
    disable_department,
    disable_position,
    disable_user_account,
    enable_department,
    enable_position,
    enable_user_account,
    get_role_data_scope_policy,
    get_conn,
    insert_audit_log,
    list_audit_logs,
    list_department_names,
    list_departments,
    list_permissions,
    list_positions,
    list_roles_with_permissions,
    list_users_admin,
    offboard_user_account,
    reset_user_password,
    set_role_data_scope,
    set_role_data_scope_policy,
    set_role_permissions,
    soft_delete_role,
    toggle_role_status,
    update_department_name,
    user_can_be_deleted,
)
from utils.permission_meta import (
    action_permission_rules,
    enrich_permission_rows,
    menu_visibility_rules,
    permission_groups,
    permission_label_cn,
    role_change_reason_options,
    summarize_permission_names,
)
from utils.security import current_user, has_permission, login_required, require_permission
from utils.status_i18n import to_cn_reason_code

bp = Blueprint("admin_iam", __name__)

USER_CHANGE_REASON_CODES = {
    "MANUAL_OVERRIDE",
    "DATA_CORRECTION",
    "POLICY_EXCEPTION",
    "NEED_MORE_INFO",
    "SYSTEM_AUTO",
}
ROLE_CHANGE_REASON_CODES = set(USER_CHANGE_REASON_CODES)
USER_ACTION_CN_MAP = {
    "USER_ENABLE": "启用",
    "USER_DISABLE": "禁用",
    "USER_RESET_PASSWORD": "重置密码",
    "USER_ROLE_CHANGE": "角色变更",
    "USER_POSITION_CHANGE": "岗位变更",
    "USER_OFFBOARD": "离职/停用",
}
ROLE_ACTION_CN_MAP = {
    "ROLE_PERMISSION_UPDATE": "角色权限变更",
}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _parse_json_object() -> tuple[dict[str, Any], tuple[Any, int] | None]:
    payload = request.get_json(silent=True)
    if request.data and payload is None:
        return {}, (jsonify({"ok": False, "message": "request body must be JSON"}), 400)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return {}, (jsonify({"ok": False, "message": "request body must be a JSON object"}), 400)
    return payload, None


def _parse_optional_json_object() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return {}


def _operator_name() -> str:
    me = current_user() or {}
    return (
        _safe_text(me.get("employee_name"))
        or _safe_text(me.get("username"))
        or _safe_text(me.get("employee_no"))
        or "system"
    )


def _operator_user_id() -> int | None:
    me = current_user() or {}
    user_id = _safe_int(me.get("id"), 0)
    return user_id if user_id > 0 else None


def _record_admin_log(
    *,
    action_type: str,
    detail: str,
    target_type: str = "",
    target_id: int | None = None,
) -> None:
    try:
        insert_audit_log(
            action_type=action_type,
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    except Exception:
        # Audit logging must not block business operations.
        return


def _can_view_admin_audit_logs() -> bool:
    user = current_user()
    if not user:
        return False
    return (
        has_permission("MANAGE_SETTINGS", user)
        or has_permission("MANAGE_SYSTEM", user)
        or has_permission("MANAGE_USERS", user)
        or has_permission("MANAGE_ROLES", user)
        or has_permission("MANAGE_RULES", user)
    )


def _forbidden(
    *,
    module_name: str = "目标模块",
    required_permissions: list[str] | None = None,
) -> tuple[Any, int]:
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "msg": "forbidden", "message": "无权访问该资源"}), 403
    return (
        render_template(
            "forbidden.html",
            module_name=module_name,
            required_permissions=required_permissions or [],
        ),
        403,
    )

def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_json_obj(raw_text: Any) -> dict[str, Any]:
    text = _safe_text(raw_text)
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _user_action_cn(action: str) -> str:
    normalized = _safe_text(action).upper()
    return USER_ACTION_CN_MAP.get(normalized, normalized or "-")


def _user_snapshot(user: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(user or {})
    roles = row.get("roles")
    role_list = roles if isinstance(roles, list) else []
    role_ids: list[int] = []
    role_names: list[str] = []
    for role in role_list:
        if not isinstance(role, dict):
            continue
        role_id = _safe_int(role.get("id"), 0)
        if role_id > 0:
            role_ids.append(role_id)
        role_name = _safe_text(role.get("role_name"))
        if role_name:
            role_names.append(role_name)
    role_names = sorted(set(role_names))
    return {
        "id": _safe_int(row.get("id"), 0),
        "username": _safe_text(row.get("username")),
        "department": _safe_text(row.get("department"), "-"),
        "status": _safe_text(row.get("status"), "ACTIVE").upper(),
        "role_ids": sorted(set(role_ids)),
        "role_names": role_names,
        "must_change_password": bool(row.get("must_change_password")),
    }


def _load_user_admin_row(user_id: int) -> dict[str, Any] | None:
    target_id = _safe_int(user_id, 0)
    if target_id <= 0:
        return None
    for row in list_users_admin(limit=5000):
        if _safe_int(row.get("id"), 0) == target_id:
            return row
    return None


def _require_user_change_reason_code(
    payload: dict[str, Any],
    *,
    strict: bool,
) -> tuple[str, tuple[Any, int] | None]:
    reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not reason_code:
        if strict:
            return "", (jsonify({"ok": False, "message": "change_reason_code is required"}), 400)
        return "SYSTEM_AUTO", None
    if reason_code not in USER_CHANGE_REASON_CODES:
        return "", (jsonify({"ok": False, "message": "invalid change_reason_code"}), 400)
    return reason_code, None


def _write_user_audit_log(
    *,
    action: str,
    user_id: int,
    before_user: dict[str, Any] | None,
    after_user: dict[str, Any] | None,
    change_reason_code: str,
    change_reason_note: str,
    action_note: str,
) -> None:
    before_snapshot = _user_snapshot(before_user)
    after_snapshot = _user_snapshot(after_user)
    after_snapshot["change_reason_note"] = _safe_text(change_reason_note)
    if action_note:
        after_snapshot["action_note"] = _safe_text(action_note)
    try:
        write_audit_log(
            action=_safe_text(action).upper(),
            target_type="user",
            target_id=str(int(user_id)),
            before_obj=before_snapshot,
            after_obj=after_snapshot,
            change_reason_code=_safe_text(change_reason_code).upper(),
            trace_id="",
        )
    except Exception:
        return


def _latest_action_payload(
    *,
    action: str,
    change_reason_code: str,
    change_reason_note: str,
) -> dict[str, Any]:
    reason_code = _safe_text(change_reason_code).upper() or "SYSTEM_AUTO"
    return {
        "action": _safe_text(action).upper(),
        "action_cn": _user_action_cn(action),
        "operator": _operator_name(),
        "change_reason_code": reason_code,
        "change_reason_code_cn": to_cn_reason_code(reason_code),
        "note": _safe_text(change_reason_note, "-"),
        "created_at": _now_text(),
    }


def _extract_user_audit_note(
    *,
    action: str,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
) -> str:
    direct_note = (
        _safe_text(after_snapshot.get("action_note"))
        or _safe_text(after_snapshot.get("change_reason_note"))
        or _safe_text(after_snapshot.get("change_note"))
        or _safe_text(after_snapshot.get("comment"))
        or _safe_text(after_snapshot.get("note"))
    )
    if direct_note:
        return direct_note
    normalized_action = _safe_text(action).upper()
    if normalized_action == "USER_ROLE_CHANGE":
        before_roles = before_snapshot.get("role_names")
        after_roles = after_snapshot.get("role_names")
        before_text = ", ".join(before_roles) if isinstance(before_roles, list) and before_roles else "-"
        after_text = ", ".join(after_roles) if isinstance(after_roles, list) and after_roles else "-"
        if before_text != after_text:
            return f"{before_text} -> {after_text}"
    return "-"


def _role_action_cn(action: str) -> str:
    normalized = _safe_text(action).upper()
    return ROLE_ACTION_CN_MAP.get(normalized, "角色权限变更")


def _scope_cn(scope: Any) -> str:
    return "全量数据" if _safe_text(scope).upper() == "ALL" else "本部门数据"


def _is_system_admin_role_name(role_name: Any) -> bool:
    normalized = _safe_text(role_name).strip().lower()
    return normalized in {"系统管理员", "管理员", "admin", "system_admin", "sys_admin"}


def _sorted_permission_keys(role: dict[str, Any] | None) -> list[str]:
    if not isinstance(role, dict):
        return []
    permissions = role.get("permissions")
    items = permissions if isinstance(permissions, list) else []
    keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _safe_text(item.get("permission_key")).upper()
        if key:
            keys.add(key)
    return sorted(keys)


def _role_snapshot(
    role: dict[str, Any] | None,
    *,
    change_reason_note: str = "",
    summary: str = "",
) -> dict[str, Any]:
    row = dict(role or {})
    permission_keys = _sorted_permission_keys(row)
    snapshot = {
        "id": _safe_int(row.get("id"), 0),
        "role_name": _safe_text(row.get("role_name"), "-"),
        "data_scope": _safe_text(row.get("data_scope"), "DEPT").upper(),
        "data_scope_cn": _scope_cn(row.get("data_scope")),
        "permission_keys": permission_keys,
        "permission_names_cn": [permission_label_cn(key) for key in permission_keys],
        "permission_count": len(permission_keys),
    }
    if change_reason_note:
        snapshot["change_reason_note"] = _safe_text(change_reason_note)
    if summary:
        snapshot["change_summary"] = _safe_text(summary)
    return snapshot


def _role_change_summary(before_role: dict[str, Any] | None, after_role: dict[str, Any] | None) -> str:
    before_scope = _safe_text((before_role or {}).get("data_scope"), "DEPT").upper()
    after_scope = _safe_text((after_role or {}).get("data_scope"), "DEPT").upper()

    before_keys = set(_sorted_permission_keys(before_role))
    after_keys = set(_sorted_permission_keys(after_role))
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)

    parts: list[str] = []
    if before_scope != after_scope:
        parts.append(f"数据范围：{_scope_cn(before_scope)} -> {_scope_cn(after_scope)}")
    if added:
        parts.append(f"新增权限：{summarize_permission_names(added, limit=4)}")
    if removed:
        parts.append(f"移除权限：{summarize_permission_names(removed, limit=4)}")
    if not parts:
        return "权限与数据范围无变化"
    return "；".join(parts)


def _load_role_row(role_id: int) -> dict[str, Any] | None:
    target_id = _safe_int(role_id, 0)
    if target_id <= 0:
        return None
    for role in list_roles_with_permissions():
        if _safe_int(role.get("id"), 0) == target_id:
            return role
    return None


def _role_latest_action_payload(
    *,
    change_reason_code: str,
    change_reason_note: str,
    summary: str,
) -> dict[str, Any]:
    reason_code = _safe_text(change_reason_code).upper() or "SYSTEM_AUTO"
    return {
        "action": "ROLE_PERMISSION_UPDATE",
        "action_cn": _role_action_cn("ROLE_PERMISSION_UPDATE"),
        "operator": _operator_name(),
        "change_reason_code": reason_code,
        "change_reason_code_cn": to_cn_reason_code(reason_code),
        "note": _safe_text(change_reason_note, "-"),
        "summary": _safe_text(summary, "-"),
        "created_at": _now_text(),
    }


def _extract_role_audit_summary(
    *,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
) -> str:
    direct_note = _safe_text(after_snapshot.get("change_summary"))
    if direct_note:
        return direct_note
    before_scope = _safe_text(before_snapshot.get("data_scope"), "DEPT").upper()
    after_scope = _safe_text(after_snapshot.get("data_scope"), "DEPT").upper()
    before_keys = before_snapshot.get("permission_keys")
    after_keys = after_snapshot.get("permission_keys")
    before_key_list = before_keys if isinstance(before_keys, list) else []
    after_key_list = after_keys if isinstance(after_keys, list) else []
    before_role = {"data_scope": before_scope, "permissions": [{"permission_key": key} for key in before_key_list]}
    after_role = {"data_scope": after_scope, "permissions": [{"permission_key": key} for key in after_key_list]}
    return _role_change_summary(before_role, after_role)


def _role_page_payload() -> dict[str, Any]:
    roles = list_roles_with_permissions()
    for r in roles:
        r["user_bound_count"] = count_users_by_role_id(_safe_int(r.get("id"), 0))
    return {
        "roles": roles,
        "permissions": enrich_permission_rows(list_permissions()),
        "permission_groups": permission_groups(),
        "menu_rules": menu_visibility_rules(),
        "action_rules": action_permission_rules(),
        "change_reason_options": role_change_reason_options(),
    }


@bp.get("/admin/users")
@login_required
@require_permission("MANAGE_USERS")
def admin_users_page():
    users = list_users_admin(limit=2000)
    me = current_user() or {}
    me_id = _safe_int(me.get("id"), 0)
    has_delete_any_permission = has_permission("DELETE_ANY_USER", me)
    for u in users:
        user_id = _safe_int(u.get("id"), 0)
        # 不能删除自己
        if user_id == me_id:
            u["can_delete"] = False
        # 如果有DELETE_ANY_USER权限，则所有其他用户都可以删除
        elif has_delete_any_permission:
            u["can_delete"] = True
        else:
            u["can_delete"] = user_can_be_deleted(user_id)
    all_roles = list_roles_with_permissions()
    active_roles = list_roles_with_permissions(include_disabled=False)
    departments = list_department_names(limit=2000)
    positions = list_positions(include_disabled=False, limit=2000)
    return render_template(
        "admin_users.html",
        users=users,
        roles=all_roles,
        active_roles=active_roles,
        departments=departments,
        positions=positions,
        current_user_id=me_id,
    )


@bp.get("/api/admin/users")
@login_required
@require_permission("MANAGE_USERS")
def admin_users_api():
    limit = _safe_int(request.args.get("limit"), 500)
    me = current_user() or {}
    me_id = _safe_int(me.get("id"), 0)
    has_delete_any_permission = has_permission("DELETE_ANY_USER", me)
    users = list_users_admin(limit=limit)
    for u in users:
        user_id = _safe_int(u.get("id"), 0)
        # 不能删除自己
        if user_id == me_id:
            u["can_delete"] = False
        # 如果有DELETE_ANY_USER权限，则所有其他用户都可以删除
        elif has_delete_any_permission:
            u["can_delete"] = True
        else:
            u["can_delete"] = user_can_be_deleted(user_id)
    return jsonify(
        {
            "ok": True,
            "users": users,
            "roles": list_roles_with_permissions(),
            "active_roles": list_roles_with_permissions(include_disabled=False),
            "departments": list_department_names(limit=2000),
            "positions": list_positions(include_disabled=False, limit=2000),
            "current_user_id": me_id,
        }
    )


@bp.post("/api/admin/users")
@login_required
@require_permission("MANAGE_USERS")
def admin_create_user_api():
    payload, err = _parse_json_object()
    if err is not None:
        return err

    username = _safe_text(payload.get("username"))
    password = _safe_text(payload.get("password"))
    department = _safe_text(payload.get("department"), "-")
    employee_name = _safe_text(payload.get("employee_name"), username or "-")
    employee_no = _safe_text(payload.get("employee_no"), "-")
    role_text = _safe_text(payload.get("role"))
    role_id_raw = payload.get("role_id")
    role_id = _safe_int(role_id_raw, 0) if role_id_raw is not None else None
    if role_id is not None and role_id <= 0:
        role_id = None
    position_id_raw = payload.get("position_id")
    position_id = _safe_int(position_id_raw, 0) if position_id_raw is not None else None
    if position_id is not None and position_id <= 0:
        position_id = None

    if not username or not password:
        return jsonify({"ok": False, "message": "username and password are required"}), 400

    if role_id is not None:
        active_roles = list_roles_with_permissions(include_disabled=False)
        active_role_ids = {_safe_int(r.get("id"), 0) for r in active_roles}
        if role_id not in active_role_ids:
            return jsonify({"ok": False, "message": "所选角色已被禁用或不存在，无法分配给新用户"}), 400

    try:
        created = create_user_account(
            username=username,
            password=password,
            department=department,
            employee_name=employee_name,
            employee_no=employee_no,
            role_text=role_text,
            role_id=role_id,
            position_id=position_id,
        )
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "message": "username already exists"}), 409
    except Exception as exc:
        return jsonify({"ok": False, "message": f"create user failed: {exc}"}), 500

    if not created:
        return jsonify({"ok": False, "message": "create user failed"}), 500

    _record_admin_log(
        action_type="CREATE_USER",
        target_type="user",
        target_id=_safe_int(created.get("id"), 0) or None,
        detail=f"username={username}; role_id={role_id}; department={department}; position_id={position_id or ''}",
    )
    return jsonify({"ok": True, "user": created})


# ---------- 岗位管理 ----------


@bp.get("/admin/positions")
@login_required
@require_permission("MANAGE_USERS")
def admin_positions_page():
    positions = list_positions(include_disabled=True, limit=2000)
    return render_template("admin_positions.html", positions=positions)


@bp.get("/api/admin/positions")
@login_required
@require_permission("MANAGE_USERS")
def admin_positions_api():
    include_disabled = request.args.get("include_disabled", "1").strip().lower() in ("1", "true", "yes")
    positions = list_positions(include_disabled=include_disabled, limit=2000)
    return jsonify({"ok": True, "positions": positions})


@bp.post("/api/admin/positions")
@login_required
@require_permission("MANAGE_USERS")
def admin_create_position_api():
    payload, err = _parse_json_object()
    if err is not None:
        return err
    name = _safe_text(payload.get("name"))
    if not name:
        return jsonify({"ok": False, "message": "岗位名称不能为空"}), 400
    created = create_position(name)
    if created is None:
        return jsonify({"ok": False, "message": "已存在同名且已启用的岗位，请使用其他名称或先禁用原岗位"}), 409
    _record_admin_log(
        action_type="POSITION_CREATE",
        target_type="position",
        target_id=created.get("id"),
        detail=f"name={name}; id={created.get('id')}",
    )
    return jsonify({"ok": True, "position": created})


@bp.post("/api/admin/positions/<int:position_id>/disable")
@login_required
@require_permission("MANAGE_USERS")
def admin_disable_position_api(position_id: int):
    updated = disable_position(position_id)
    if updated is None:
        return jsonify({"ok": False, "message": "岗位不存在或禁用失败，请刷新列表后重试"}), 404
    _record_admin_log(
        action_type="POSITION_DISABLE",
        target_type="position",
        target_id=position_id,
        detail=f"name={updated.get('name', '')}; id={position_id}",
    )
    return jsonify({"ok": True, "position": updated})


@bp.post("/api/admin/positions/<int:position_id>/enable")
@login_required
@require_permission("MANAGE_USERS")
def admin_enable_position_api(position_id: int):
    updated = enable_position(position_id)
    if updated is None:
        return jsonify({"ok": False, "message": "岗位不存在或启用失败，请刷新列表后重试"}), 404
    _record_admin_log(
        action_type="POSITION_ENABLE",
        target_type="position",
        target_id=position_id,
        detail=f"name={updated.get('name', '')}; id={position_id}",
    )
    return jsonify({"ok": True, "position": updated})


@bp.post("/api/admin/users/<int:user_id>/disable")
@login_required
@require_permission("MANAGE_USERS")
def admin_disable_user_api(user_id: int):
    payload = _parse_optional_json_object()
    reason_code, reason_err = _require_user_change_reason_code(payload, strict=True)
    if reason_err is not None:
        return reason_err
    reason_note = _safe_text(payload.get("change_reason_note"))

    me = current_user() or {}
    if _safe_int(me.get("id"), 0) == int(user_id):
        return jsonify({"ok": False, "message": "cannot disable current user"}), 400

    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404

    updated = disable_user_account(user_id)
    if not updated:
        return jsonify({"ok": False, "message": "user not found"}), 404

    after_user = _load_user_admin_row(user_id)
    action_note = reason_note or "用户状态切换为禁用"
    _record_admin_log(
        action_type="DISABLE_USER",
        target_type="user",
        target_id=int(user_id),
        detail=(
            f"user_id={int(user_id)}; change_reason_code={reason_code}; "
            f"change_reason_note={reason_note or '-'}"
        ),
    )
    _write_user_audit_log(
        action="USER_DISABLE",
        user_id=int(user_id),
        before_user=before_user,
        after_user=after_user,
        change_reason_code=reason_code,
        change_reason_note=reason_note,
        action_note=action_note,
    )
    return jsonify(
        {
            "ok": True,
            "user_id": int(user_id),
            "status": "DISABLED",
            "user": after_user or before_user,
            "latest_action": _latest_action_payload(
                action="USER_DISABLE",
                change_reason_code=reason_code,
                change_reason_note=reason_note,
            ),
        }
    )


@bp.post("/api/admin/users/<int:user_id>/enable")
@login_required
@require_permission("MANAGE_USERS")
def admin_enable_user_api(user_id: int):
    payload = _parse_optional_json_object()
    reason_code, reason_err = _require_user_change_reason_code(payload, strict=True)
    if reason_err is not None:
        return reason_err
    reason_note = _safe_text(payload.get("change_reason_note"))

    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404

    updated = enable_user_account(user_id)
    if not updated:
        return jsonify({"ok": False, "message": "user not found"}), 404

    after_user = _load_user_admin_row(user_id)
    action_note = reason_note or "用户状态切换为启用"
    _record_admin_log(
        action_type="ENABLE_USER",
        target_type="user",
        target_id=int(user_id),
        detail=(
            f"user_id={int(user_id)}; change_reason_code={reason_code}; "
            f"change_reason_note={reason_note or '-'}"
        ),
    )
    _write_user_audit_log(
        action="USER_ENABLE",
        user_id=int(user_id),
        before_user=before_user,
        after_user=after_user,
        change_reason_code=reason_code,
        change_reason_note=reason_note,
        action_note=action_note,
    )
    return jsonify(
        {
            "ok": True,
            "user_id": int(user_id),
            "status": "ACTIVE",
            "user": after_user or before_user,
            "latest_action": _latest_action_payload(
                action="USER_ENABLE",
                change_reason_code=reason_code,
                change_reason_note=reason_note,
            ),
        }
    )


@bp.post("/api/admin/users/<int:user_id>/offboard")
@login_required
@require_permission("MANAGE_USERS")
def admin_offboard_user_api(user_id: int):
    """离职/停用：禁用 + 清空角色/数据范围，必填原因，写审计 diff。"""
    payload = _parse_optional_json_object()
    reason_code, reason_err = _require_user_change_reason_code(payload, strict=True)
    if reason_err is not None:
        return reason_err
    reason_note = _safe_text(payload.get("change_reason_note"))
    if not reason_note:
        return jsonify({"ok": False, "message": "离职/停用必须填写原因说明（change_reason_note）"}), 400

    me = current_user() or {}
    if _safe_int(me.get("id"), 0) == int(user_id):
        return jsonify({"ok": False, "message": "cannot offboard current user"}), 400

    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404

    ok = offboard_user_account(user_id)
    if not ok:
        return jsonify({"ok": False, "message": "user not found"}), 404

    after_user = _load_user_admin_row(user_id)
    _record_admin_log(
        action_type="OFFBOARD_USER",
        target_type="user",
        target_id=int(user_id),
        detail=(
            f"user_id={int(user_id)}; change_reason_code={reason_code}; "
            f"change_reason_note={reason_note}"
        ),
    )
    _write_user_audit_log(
        action="USER_OFFBOARD",
        user_id=int(user_id),
        before_user=before_user,
        after_user=after_user or before_user,
        change_reason_code=reason_code,
        change_reason_note=reason_note,
        action_note=reason_note,
    )
    return jsonify(
        {
            "ok": True,
            "user_id": int(user_id),
            "status": "DISABLED",
            "user": after_user or before_user,
            "latest_action": _latest_action_payload(
                action="USER_OFFBOARD",
                change_reason_code=reason_code,
                change_reason_note=reason_note,
            ),
        }
    )


@bp.delete("/api/admin/users/<int:user_id>")
@login_required
@require_permission("MANAGE_USERS")
def admin_delete_user_api(user_id: int):
    """删除用户：仅对无业务、无审计记录的测试账号可用。拥有DELETE_ANY_USER权限的管理员可删除任意用户。"""
    me = current_user() or {}
    me_id = _safe_int(me.get("id"), 0)
    has_delete_any_permission = has_permission("DELETE_ANY_USER", me)
    
    # 不允许删除自己
    if me_id > 0 and me_id == int(user_id):
        return jsonify({"ok": False, "message": "不能删除当前登录的账号"}), 400
    
    # 检查用户是否存在
    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404
    
    # 如果没有DELETE_ANY_USER权限，需要检查是否可以删除
    if not has_delete_any_permission:
        if not user_can_be_deleted(user_id):
            return jsonify(
                {"ok": False, "message": "仅无业务记录、无审计记录的测试账号可删除，该用户不可删除"}
            ), 400
    
    # 执行删除（如果有权限则强制删除）
    ok = delete_user_account(user_id, force=has_delete_any_permission)
    if not ok:
        return jsonify({"ok": False, "message": "delete failed"}), 500
    _record_admin_log(
        action_type="DELETE_USER",
        target_type="user",
        target_id=int(user_id),
        detail=f"user_id={int(user_id)}; username={_safe_text(before_user.get('username'))}; force={has_delete_any_permission}",
    )
    return jsonify({"ok": True, "user_id": int(user_id), "message": "用户已删除"})


@bp.post("/api/admin/users/<int:user_id>/reset_password")
@login_required
@require_permission("MANAGE_USERS")
def admin_reset_user_password_api(user_id: int):
    payload = _parse_optional_json_object()
    reason_code, reason_err = _require_user_change_reason_code(payload, strict=True)
    if reason_err is not None:
        return reason_err
    reason_note = _safe_text(payload.get("change_reason_note"))

    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404

    updated = reset_user_password(user_id, operator=_operator_name())
    if not updated:
        return jsonify({"ok": False, "message": "user not found"}), 404

    after_user = _load_user_admin_row(user_id)
    action_note = reason_note or "密码重置为默认强口令"
    _record_admin_log(
        action_type="RESET_PASSWORD",
        target_type="user",
        target_id=int(user_id),
        detail=(
            f"user_id={int(user_id)}; default_password=true; change_reason_code={reason_code}; "
            f"change_reason_note={reason_note or '-'}"
        ),
    )
    _write_user_audit_log(
        action="USER_RESET_PASSWORD",
        user_id=int(user_id),
        before_user=before_user,
        after_user=after_user,
        change_reason_code=reason_code,
        change_reason_note=reason_note,
        action_note=action_note,
    )
    return jsonify(
        {
            "ok": True,
            "user_id": int(user_id),
            "user": after_user or before_user,
            "latest_action": _latest_action_payload(
                action="USER_RESET_PASSWORD",
                change_reason_code=reason_code,
                change_reason_note=reason_note,
            ),
            "default_password": DEFAULT_RESET_PASSWORD,
            "message": "password reset to default",
        }
    )


@bp.post("/api/admin/users/<int:user_id>/role")
@login_required
@require_permission("MANAGE_USERS")
def admin_change_user_role_api(user_id: int):
    payload, err = _parse_json_object()
    if err is not None:
        return err

    role_id = _safe_int(payload.get("role_id"), 0)
    if role_id <= 0:
        return jsonify({"ok": False, "message": "role_id is required"}), 400

    reason_code, reason_err = _require_user_change_reason_code(payload, strict=True)
    if reason_err is not None:
        return reason_err
    reason_note = _safe_text(payload.get("change_reason_note"))

    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404

    role_items = list_roles_with_permissions()
    role_row = None
    for item in role_items:
        if _safe_int(item.get("id"), 0) == role_id:
            role_row = item
            break
    if role_row is None:
        return jsonify({"ok": False, "message": "role not found"}), 404

    if _safe_text(role_row.get("status")).upper() == "DISABLED":
        return jsonify({"ok": False, "message": "所选角色已被禁用，无法分配"}), 400

    target_role_name = _safe_text(role_row.get("role_name"), "-")
    with get_conn() as conn:
        user_exists = conn.execute("SELECT id FROM users WHERE id = ? LIMIT 1", (int(user_id),)).fetchone()
        if user_exists is None:
            return jsonify({"ok": False, "message": "user not found"}), 404

        conn.execute("DELETE FROM user_roles WHERE user_id = ?", (int(user_id),))
        conn.execute(
            """
            INSERT INTO user_roles (user_id, role_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, role_id) DO NOTHING
            """,
            (int(user_id), int(role_id)),
        )
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (target_role_name, int(user_id)))
        conn.commit()

    after_user = _load_user_admin_row(user_id)
    before_roles = before_user.get("roles") if isinstance(before_user.get("roles"), list) else []
    before_role_names = ", ".join(
        [_safe_text(item.get("role_name")) for item in before_roles if isinstance(item, dict) and _safe_text(item.get("role_name"))]
    )
    before_role_names = before_role_names or "-"
    action_note = reason_note or f"{before_role_names} -> {target_role_name}"

    _record_admin_log(
        action_type="CHANGE_USER_ROLE",
        target_type="user",
        target_id=int(user_id),
        detail=(
            f"user_id={int(user_id)}; role_id={int(role_id)}; role_name={target_role_name}; "
            f"change_reason_code={reason_code}; change_reason_note={reason_note or '-'}"
        ),
    )
    _write_user_audit_log(
        action="USER_ROLE_CHANGE",
        user_id=int(user_id),
        before_user=before_user,
        after_user=after_user,
        change_reason_code=reason_code,
        change_reason_note=reason_note,
        action_note=action_note,
    )
    return jsonify(
        {
            "ok": True,
            "user_id": int(user_id),
            "role_id": int(role_id),
            "role_name": target_role_name,
            "user": after_user or before_user,
            "latest_action": _latest_action_payload(
                action="USER_ROLE_CHANGE",
                change_reason_code=reason_code,
                change_reason_note=reason_note or action_note,
            ),
        }
    )


@bp.post("/api/admin/users/<int:user_id>/position")
@login_required
@require_permission("MANAGE_USERS")
def admin_change_user_position_api(user_id: int):
    """设置用户岗位"""
    payload, err = _parse_json_object()
    if err is not None:
        return err

    position_id = _safe_int(payload.get("position_id"), 0)
    if position_id <= 0:
        return jsonify({"ok": False, "message": "position_id is required"}), 400

    reason_code, reason_err = _require_user_change_reason_code(payload, strict=True)
    if reason_err is not None:
        return reason_err
    reason_note = _safe_text(payload.get("change_reason_note"))

    before_user = _load_user_admin_row(user_id)
    if before_user is None:
        return jsonify({"ok": False, "message": "user not found"}), 404

    # 检查岗位是否存在且启用
    positions = list_positions(include_disabled=False, limit=5000)
    position_row = None
    for item in positions:
        if _safe_int(item.get("id"), 0) == position_id:
            position_row = item
            break
    if position_row is None:
        return jsonify({"ok": False, "message": "岗位不存在或已被禁用"}), 404

    target_position_name = _safe_text(position_row.get("name"), "-")
    
    with get_conn() as conn:
        user_exists = conn.execute("SELECT id FROM users WHERE id = ? LIMIT 1", (int(user_id),)).fetchone()
        if user_exists is None:
            return jsonify({"ok": False, "message": "user not found"}), 404

        conn.execute("UPDATE users SET position_id = ? WHERE id = ?", (int(position_id), int(user_id)))
        conn.commit()

    after_user = _load_user_admin_row(user_id)
    before_position = _safe_text(before_user.get("position_name"), "-")
    action_note = reason_note or f"岗位变更：{before_position} -> {target_position_name}"

    _record_admin_log(
        action_type="CHANGE_USER_POSITION",
        target_type="user",
        target_id=int(user_id),
        detail=(
            f"user_id={int(user_id)}; position_id={int(position_id)}; position_name={target_position_name}; "
            f"change_reason_code={reason_code}; change_reason_note={reason_note or '-'}"
        ),
    )
    
    # 写入审计日志
    try:
        write_audit_log(
            action="USER_POSITION_CHANGE",
            target_type="user",
            target_id=str(int(user_id)),
            before_obj={"position_id": before_user.get("position_id"), "position_name": before_position},
            after_obj={"position_id": position_id, "position_name": target_position_name, "change_reason_note": reason_note},
            change_reason_code=reason_code,
            trace_id="",
        )
    except Exception:
        pass

    return jsonify(
        {
            "ok": True,
            "user_id": int(user_id),
            "position_id": int(position_id),
            "position_name": target_position_name,
            "user": after_user or before_user,
            "latest_action": _latest_action_payload(
                action="USER_POSITION_CHANGE",
                change_reason_code=reason_code,
                change_reason_note=reason_note or action_note,
            ),
        }
    )


@bp.get("/api/admin/users/<int:user_id>/audit_trail")
@login_required
@require_permission("MANAGE_USERS")
def admin_user_audit_trail_api(user_id: int):
    if _safe_int(user_id, 0) <= 0:
        return jsonify({"ok": False, "message": "invalid user_id"}), 400

    limit = _safe_int(request.args.get("limit"), 20)
    if limit <= 0:
        limit = 20
    limit = min(limit, 200)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                created_at,
                actor_name,
                action,
                change_reason_code,
                snapshot_before,
                snapshot_after
            FROM audit_log
            WHERE target_type = 'user'
              AND target_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(int(user_id)), int(limit)),
        ).fetchall()

    logs: list[dict[str, Any]] = []
    for row in rows:
        action = _safe_text(row["action"]).upper()
        reason_code = _safe_text(row["change_reason_code"], "SYSTEM_AUTO").upper() or "SYSTEM_AUTO"
        before_snapshot = _to_json_obj(row["snapshot_before"])
        after_snapshot = _to_json_obj(row["snapshot_after"])
        logs.append(
            {
                "id": _safe_int(row["id"], 0),
                "action": action,
                "action_cn": _user_action_cn(action),
                "operator": _safe_text(row["actor_name"], "-"),
                "change_reason_code": reason_code,
                "change_reason_code_cn": to_cn_reason_code(reason_code),
                "note": _extract_user_audit_note(
                    action=action,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot,
                ),
                "created_at": _safe_text(row["created_at"], "-"),
            }
        )
    return jsonify({"ok": True, "logs": logs})


@bp.get("/admin/roles")
@login_required
@require_permission("MANAGE_ROLES")
def admin_roles_page():
    return render_template("admin_roles.html", **_role_page_payload())


@bp.get("/api/admin/roles")
@login_required
@require_permission("MANAGE_ROLES")
def admin_roles_api():
    payload = _role_page_payload()
    payload["ok"] = True
    return jsonify(payload)


@bp.get("/api/admin/roles/<int:role_id>/audit_trail")
@login_required
@require_permission("MANAGE_ROLES")
def admin_role_audit_trail_api(role_id: int):
    role_row = _load_role_row(role_id)
    if role_row is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404

    limit = _safe_int(request.args.get("limit"), 20)
    if limit <= 0:
        limit = 20
    limit = min(limit, 200)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                created_at,
                actor_name,
                action,
                change_reason_code,
                snapshot_before,
                snapshot_after
            FROM audit_log
            WHERE target_type = 'role'
              AND target_id = ?
              AND action = 'ROLE_PERMISSION_UPDATE'
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(int(role_id)), int(limit)),
        ).fetchall()

    logs: list[dict[str, Any]] = []
    for row in rows:
        action = _safe_text(row["action"]).upper()
        reason_code = _safe_text(row["change_reason_code"], "SYSTEM_AUTO").upper() or "SYSTEM_AUTO"
        before_snapshot = _to_json_obj(row["snapshot_before"])
        after_snapshot = _to_json_obj(row["snapshot_after"])
        summary = _extract_role_audit_summary(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        logs.append(
            {
                "id": _safe_int(row["id"], 0),
                "action": action,
                "action_cn": _role_action_cn(action),
                "operator": _safe_text(row["actor_name"], "-"),
                "change_reason_code": reason_code,
                "change_reason_code_cn": to_cn_reason_code(reason_code),
                "note": _safe_text(after_snapshot.get("change_reason_note"), "-"),
                "summary": summary,
                "created_at": _safe_text(row["created_at"], "-"),
            }
        )
    return jsonify({"ok": True, "logs": logs})


@bp.post("/api/admin/roles/<int:role_id>/permissions")
@login_required
@require_permission("MANAGE_ROLES")
def admin_set_role_permissions_api(role_id: int):
    payload, err = _parse_json_object()
    if err is not None:
        return err

    raw_ids = payload.get("permission_ids")
    if not isinstance(raw_ids, list):
        return jsonify({"ok": False, "message": "permission_ids 必须是数组"}), 400

    permission_ids = [_safe_int(item, 0) for item in raw_ids if _safe_int(item, 0) > 0]
    data_scope = payload.get("data_scope")
    normalized_scope: str | None = None
    if data_scope is not None:
        normalized_scope = _safe_text(data_scope).upper()
        if normalized_scope not in DATA_SCOPE_TYPES:
            return jsonify({"ok": False, "message": "data_scope 仅支持：本人/本人+下属/本部门/本部门+下级/指定部门/指定人员/全量"}), 400

    reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not reason_code:
        return jsonify({"ok": False, "message": MISSING_REASON_MESSAGE}), 400
    if reason_code not in ROLE_CHANGE_REASON_CODES:
        return jsonify({"ok": False, "message": "无效的原因码"}), 400
    reason_note = _safe_text(payload.get("change_reason_note"))

    before_role = _load_role_row(role_id)
    if before_role is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404

    all_permission_rows = list_permissions()
    permission_key_by_id = {
        _safe_int(item.get("id"), 0): _safe_text(item.get("permission_key")).upper()
        for item in all_permission_rows
        if _safe_int(item.get("id"), 0) > 0 and _safe_text(item.get("permission_key"))
    }
    selected_permission_keys = {
        permission_key_by_id.get(pid, "")
        for pid in permission_ids
        if permission_key_by_id.get(pid, "")
    }

    role_name = _safe_text(before_role.get("role_name"))
    if _is_system_admin_role_name(role_name):
        permission_ids = sorted(permission_key_by_id.keys())
        normalized_scope = "ALL"

    updated = set_role_permissions(
        role_id=role_id,
        permission_ids=permission_ids,
        data_scope=normalized_scope,
    )
    if updated is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404

    summary = _role_change_summary(before_role, updated)
    before_snapshot = _role_snapshot(before_role)
    after_snapshot = _role_snapshot(
        updated,
        change_reason_note=reason_note,
        summary=summary,
    )

    try:
        write_audit_log(
            action="ROLE_PERMISSION_UPDATE",
            target_type="role",
            target_id=str(int(role_id)),
            before_obj=before_snapshot,
            after_obj=after_snapshot,
            change_reason_code=reason_code,
            trace_id="",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "message": "审计日志写入失败"}), 500

    _record_admin_log(
        action_type="ROLE_PERMISSION_UPDATE",
        target_type="role",
        target_id=int(role_id),
        detail=(
            f"role_id={int(role_id)}; "
            f"permission_ids={permission_ids}; "
            f"data_scope={normalized_scope or '-'}; "
            f"change_reason_code={reason_code}; "
            f"change_reason_note={reason_note or '-'}; "
            f"summary={summary}"
        ),
    )
    return jsonify(
        {
            "ok": True,
            "role": updated,
            "change_summary": summary,
            "latest_action": _role_latest_action_payload(
                change_reason_code=reason_code,
                change_reason_note=reason_note,
                summary=summary,
            ),
        }
    )


@bp.post("/api/admin/roles/create")
@login_required
@require_permission("MANAGE_ROLES")
def admin_create_role_api():
    payload, err = _parse_json_object()
    if err is not None:
        return err
    role_name = _safe_text(payload.get("role_name"))
    if not role_name:
        return jsonify({"ok": False, "message": "角色名称不能为空"}), 400
    created = create_role_record(role_name)
    if created is None:
        return jsonify({"ok": False, "message": "角色名称已存在"}), 409
    _record_admin_log(
        action_type="ROLE_CREATE",
        target_type="role",
        target_id=_safe_int(created.get("id"), 0) or None,
        detail=f"role_name={role_name}",
    )
    return jsonify({"ok": True, "role": created})


@bp.post("/api/admin/roles/<int:role_id>/toggle")
@login_required
@require_permission("MANAGE_ROLES")
def admin_toggle_role_api(role_id: int):
    role = _load_role_row(role_id)
    if role is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404
    if _is_system_admin_role_name(_safe_text(role.get("role_name"))):
        return jsonify({"ok": False, "message": "系统管理员角色不可禁用"}), 403
    updated = toggle_role_status(role_id)
    if updated is None:
        return jsonify({"ok": False, "message": "操作失败"}), 500
    new_status = _safe_text(updated.get("status")).upper()
    action_cn = "启用" if new_status == "ACTIVE" else "禁用"
    _record_admin_log(
        action_type=f"ROLE_{new_status}",
        target_type="role",
        target_id=int(role_id),
        detail=f"role_id={role_id}; new_status={new_status}",
    )
    return jsonify({"ok": True, "role": updated, "message": f"角色已{action_cn}"})


@bp.post("/api/admin/roles/<int:role_id>/disable")
@login_required
@require_permission("MANAGE_ROLES")
def admin_disable_role_api(role_id: int):
    role = _load_role_row(role_id)
    if role is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404
    if _is_system_admin_role_name(_safe_text(role.get("role_name"))):
        return jsonify({"ok": False, "message": "系统管理员角色不可禁用"}), 403
    if _safe_text(role.get("status")).upper() == "DISABLED":
        return jsonify({"ok": True, "message": "角色已是禁用状态"})
    updated = toggle_role_status(role_id)
    if updated is None:
        return jsonify({"ok": False, "message": "操作失败"}), 500
    _record_admin_log(
        action_type="ROLE_DISABLED",
        target_type="role",
        target_id=int(role_id),
        detail=f"role_id={role_id}",
    )
    return jsonify({"ok": True, "role": updated, "message": "角色已禁用"})


@bp.post("/api/admin/roles/<int:role_id>/enable")
@login_required
@require_permission("MANAGE_ROLES")
def admin_enable_role_api(role_id: int):
    role = _load_role_row(role_id)
    if role is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404
    if _safe_text(role.get("status")).upper() == "ACTIVE":
        return jsonify({"ok": True, "message": "角色已是启用状态"})
    updated = toggle_role_status(role_id)
    if updated is None:
        return jsonify({"ok": False, "message": "操作失败"}), 500
    _record_admin_log(
        action_type="ROLE_ENABLED",
        target_type="role",
        target_id=int(role_id),
        detail=f"role_id={role_id}",
    )
    return jsonify({"ok": True, "role": updated, "message": "角色已启用"})


@bp.delete("/api/admin/roles/<int:role_id>")
@login_required
@require_permission("MANAGE_ROLES")
def admin_delete_role_api(role_id: int):
    role = _load_role_row(role_id)
    if role is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404
    if _is_system_admin_role_name(_safe_text(role.get("role_name"))):
        return jsonify({"ok": False, "message": "系统管理员角色不可删除"}), 403
    ok, msg = soft_delete_role(role_id)
    if not ok:
        return jsonify({"ok": False, "message": msg}), 400
    _record_admin_log(
        action_type="ROLE_SOFT_DELETE",
        target_type="role",
        target_id=int(role_id),
        detail=f"role_id={role_id}; role_name={_safe_text(role.get('role_name'))}",
    )
    return jsonify({"ok": True, "message": "角色已删除（软删除）"})


@bp.get("/admin/departments")
@login_required
@require_permission("MANAGE_USERS")
def admin_departments_page():
    return render_template("admin_departments.html", departments=list_departments(limit=2000, include_disabled=True))


@bp.get("/api/admin/departments")
@login_required
@require_permission("MANAGE_USERS")
def admin_departments_api():
    return jsonify({"ok": True, "departments": list_departments(limit=2000, include_disabled=True)})


@bp.post("/api/admin/departments")
@login_required
@require_permission("MANAGE_USERS")
def admin_create_department_api():
    payload, err = _parse_json_object()
    if err is not None:
        return err

    name = _safe_text(payload.get("name"))
    if not name:
        return jsonify({"ok": False, "message": "name is required"}), 400

    created = create_department(name)
    if created is None:
        return jsonify({"ok": False, "message": "department already exists"}), 409

    _record_admin_log(
        action_type="CREATE_DEPARTMENT",
        target_type="department",
        target_id=_safe_int(created.get("id"), 0) or None,
        detail=f"name={name}",
    )
    return jsonify({"ok": True, "department": created})


@bp.post("/api/admin/departments/<int:department_id>/rename")
@login_required
@require_permission("MANAGE_USERS")
def admin_rename_department_api(department_id: int):
    payload, err = _parse_json_object()
    if err is not None:
        return err

    new_name = _safe_text(payload.get("name"))
    if not new_name:
        return jsonify({"ok": False, "message": "name is required"}), 400

    exists = any(int(row.get("id", 0)) == int(department_id) for row in list_departments(limit=5000, include_disabled=True))
    if not exists:
        return jsonify({"ok": False, "message": "department not found"}), 404

    updated = update_department_name(department_id, new_name)
    if updated is None:
        return jsonify({"ok": False, "message": "department name already exists"}), 409

    _record_admin_log(
        action_type="RENAME_DEPARTMENT",
        target_type="department",
        target_id=int(department_id),
        detail=f"department_id={int(department_id)}; new_name={new_name}",
    )
    return jsonify({"ok": True, "department": updated})


@bp.post("/api/admin/departments/<int:department_id>/disable")
@login_required
@require_permission("MANAGE_USERS")
def admin_disable_department_api(department_id: int):
    updated = disable_department(department_id)
    if updated is None:
        return jsonify({"ok": False, "message": "department not found"}), 404

    _record_admin_log(
        action_type="DISABLE_DEPARTMENT",
        target_type="department",
        target_id=int(department_id),
        detail=f"department_id={int(department_id)}",
    )
    return jsonify({"ok": True, "department": updated})


@bp.post("/api/admin/departments/<int:department_id>/enable")
@login_required
@require_permission("MANAGE_USERS")
def admin_enable_department_api(department_id: int):
    updated = enable_department(department_id)
    if updated is None:
        return jsonify({"ok": False, "message": "department not found"}), 404

    _record_admin_log(
        action_type="ENABLE_DEPARTMENT",
        target_type="department",
        target_id=int(department_id),
        detail=f"department_id={int(department_id)}",
    )
    return jsonify({"ok": True, "department": updated})


@bp.delete("/api/admin/departments/<int:department_id>")
@login_required
@require_permission("MANAGE_USERS")
def admin_delete_department_api(department_id: int):
    # 先检查部门是否存在以及是否有在职人员
    departments = list_departments(limit=5000, include_disabled=True)
    target_dept = None
    for dept in departments:
        if int(dept.get("id", 0)) == int(department_id):
            target_dept = dept
            break
    
    if target_dept is None:
        return jsonify({"ok": False, "message": "部门不存在"}), 404
    
    if int(target_dept.get("active_user_count", 0)) > 0:
        return jsonify({"ok": False, "message": "该部门有在职人员，无法删除"}), 400

    success = delete_department(department_id)
    if not success:
        return jsonify({"ok": False, "message": "删除失败"}), 500

    _record_admin_log(
        action_type="DELETE_DEPARTMENT",
        target_type="department",
        target_id=int(department_id),
        detail=f"department_id={int(department_id)}; name={_safe_text(target_dept.get('name'))}",
    )
    return jsonify({"ok": True, "message": "部门已删除"})


@bp.get("/admin/data_scope")
@login_required
@require_permission("MANAGE_ROLES")
def admin_data_scope_page():
    roles = list_roles_with_permissions()
    departments = list_departments(limit=500, include_disabled=False)
    users = list_users_admin(limit=500)
    return render_template(
        "admin_data_scope.html",
        roles=roles,
        departments=departments,
        users=users,
        role_change_reason_options=role_change_reason_options(),
    )


@bp.get("/api/admin/data_scope")
@login_required
@require_permission("MANAGE_ROLES")
def admin_data_scope_api():
    search = request.args.get("search", "").strip() or None
    roles = list_roles_with_permissions(search=search)
    return jsonify({"ok": True, "roles": roles})


def _data_scope_policy_snapshot(policy: dict[str, Any] | None) -> dict[str, Any]:
    """用于审计的 data_scope 策略快照（可序列化）。"""
    if not policy:
        return {}
    return {
        "scope_type": policy.get("scope_type"),
        "dept_ids": list(policy.get("dept_ids") or []),
        "user_ids": list(policy.get("user_ids") or []),
        "dept_names": list(policy.get("dept_names") or []),
    }


@bp.get("/api/admin/data_scope/preview")
@login_required
@require_permission("MANAGE_ROLES")
def admin_data_scope_preview_api():
    role_id = request.args.get("role_id", type=int)
    scope_type = _safe_text(request.args.get("scope_type")).upper()
    dept_ids_raw = request.args.get("dept_ids")
    user_ids_raw = request.args.get("user_ids")
    sample_size = request.args.get("sample_size", type=int) or 10
    if role_id and not scope_type:
        policy = get_role_data_scope_policy(role_id)
        if policy:
            scope_type = (policy.get("scope_type") or "DEPT").upper()
            dept_ids_raw = dept_ids_raw or (policy.get("dept_ids") and ",".join(str(x) for x in policy["dept_ids"]))
            user_ids_raw = user_ids_raw or (policy.get("user_ids") and ",".join(str(x) for x in policy["user_ids"]))
    dept_ids = [int(x) for x in (dept_ids_raw or "").replace(" ", "").split(",") if str(x).strip().isdigit()]
    user_ids = [int(x) for x in (user_ids_raw or "").replace(" ", "").split(",") if str(x).strip().isdigit()]
    if not scope_type:
        scope_type = "DEPT"
    result = data_scope_preview_user_count_and_sample(
        scope_type=scope_type,
        dept_ids=dept_ids or None,
        user_ids=user_ids or None,
        sample_size=sample_size,
    )
    return jsonify({"ok": True, "preview": result})


@bp.get("/api/admin/data_scope/<int:role_id>/history")
@login_required
@require_permission("MANAGE_ROLES")
def admin_data_scope_history_api(role_id: int):
    limit = request.args.get("limit", type=int) or 50
    logs = list_audit_logs(
        limit=limit,
        target_type="role",
        target_id=str(role_id),
        action_type="DATA_SCOPE",
    )
    out = []
    for row in logs:
        snap_after = row.get("snapshot_after")
        try:
            after_obj = json.loads(snap_after) if isinstance(snap_after, str) and snap_after else {}
        except Exception:
            after_obj = {}
        meta = (after_obj or {}).get("_audit_meta") or {}
        out.append({
            "id": row.get("id"),
            "created_at": row.get("created_at"),
            "operator": row.get("operator"),
            "action_type": row.get("action_type"),
            "change_reason_code": row.get("change_reason_code"),
            "change_reason_note": meta.get("change_reason_text"),
            "diff": meta.get("diff"),
            "snapshot_after": after_obj,
        })
    return jsonify({"ok": True, "role_id": role_id, "logs": out})


@bp.post("/api/admin/data_scope/<int:role_id>/rollback")
@login_required
@require_permission("MANAGE_ROLES")
def admin_data_scope_rollback_api(role_id: int):
    payload, err = _parse_json_object()
    if err is not None:
        return err
    log_id = payload.get("log_id") or payload.get("id")
    if not log_id:
        return jsonify({"ok": False, "message": "请指定 log_id 以回滚到该历史记录"}), 400
    reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not reason_code:
        return jsonify({"ok": False, "message": MISSING_REASON_MESSAGE}), 400
    if reason_code not in ROLE_CHANGE_REASON_CODES:
        return jsonify({"ok": False, "message": "无效的原因码"}), 400
    reason_note = _safe_text(payload.get("change_reason_note"))

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT snapshot_after, action, target_type, target_id
            FROM audit_log
            WHERE id = ? AND LOWER(TRIM(target_type)) = 'role' AND TRIM(target_id) = ?
            """,
            (int(log_id), str(role_id)),
        ).fetchone()
    if not row:
        return jsonify({"ok": False, "message": "未找到该数据范围历史记录"}), 404
    try:
        after_obj = json.loads(row["snapshot_after"]) if isinstance(row["snapshot_after"], str) else {}
    except Exception:
        after_obj = {}
    scope_type = _safe_text(after_obj.get("scope_type")).upper()
    dept_ids = list(after_obj.get("dept_ids") or [])
    user_ids = list(after_obj.get("user_ids") or [])
    if scope_type not in DATA_SCOPE_TYPES:
        scope_type = "DEPT"
    before_rollback = get_role_data_scope_policy(role_id)
    updated = set_role_data_scope_policy(
        role_id=role_id,
        scope_type=scope_type,
        dept_ids=dept_ids,
        user_ids=user_ids,
    )
    if updated is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404
    try:
        write_audit_log(
            action="DATA_SCOPE_ROLLBACK",
            target_type="role",
            target_id=str(role_id),
            before_obj=_data_scope_policy_snapshot(before_rollback),
            after_obj=_data_scope_policy_snapshot(get_role_data_scope_policy(role_id)),
            change_reason_code=reason_code,
            change_reason_text=reason_note,
        )
    except ValueError as e:
        return jsonify({"ok": False, "message": str(e)}), 400
    _record_admin_log(
        action_type="DATA_SCOPE_ROLLBACK",
        target_type="role",
        target_id=role_id,
        detail=f"role_id={role_id}; log_id={log_id}; change_reason_code={reason_code}",
    )
    return jsonify({"ok": True, "role": updated})


@bp.post("/api/admin/data_scope/<int:role_id>")
@login_required
@require_permission("MANAGE_ROLES")
def admin_update_data_scope_api(role_id: int):
    payload, err = _parse_json_object()
    if err is not None:
        return err

    scope_type = _safe_text(payload.get("data_scope") or payload.get("scope_type")).upper()
    if not scope_type:
        scope_type = "DEPT"
    if scope_type not in DATA_SCOPE_TYPES:
        return jsonify({"ok": False, "message": "数据范围类型不支持，仅支持：本人/本人+下属/本部门/本部门+下级/指定部门/指定人员/全量"}), 400

    change_reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not change_reason_code:
        return jsonify({"ok": False, "message": "变更原因码为必填（审计要求）"}), 400
    if change_reason_code not in ROLE_CHANGE_REASON_CODES:
        return jsonify({"ok": False, "message": "无效的原因码"}), 400
    change_reason_note = _safe_text(payload.get("change_reason_note"))

    raw_dept_ids = payload.get("dept_ids")
    raw_user_ids = payload.get("user_ids")
    dept_ids = [int(x) for x in (raw_dept_ids or []) if isinstance(x, int) or (isinstance(x, (str, float)) and str(x).strip().isdigit())]
    user_ids = [int(x) for x in (raw_user_ids or []) if isinstance(x, int) or (isinstance(x, (str, float)) and str(x).strip().isdigit())]
    if scope_type == "DEPT_WHITELIST" and not dept_ids:
        return jsonify({"ok": False, "message": "指定部门时请至少选择一个部门"}), 400
    if scope_type == "USER_WHITELIST" and not user_ids:
        return jsonify({"ok": False, "message": "指定人员时请至少选择一名人员"}), 400

    before_policy = get_role_data_scope_policy(role_id)
    if before_policy is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404

    user = current_user() or {}
    updated_by = (
        str(user.get("employee_name") or user.get("username") or user.get("employee_no") or "").strip()
        or None
    )
    updated = set_role_data_scope_policy(
        role_id=role_id,
        scope_type=scope_type,
        dept_ids=dept_ids if scope_type == "DEPT_WHITELIST" else None,
        user_ids=user_ids if scope_type == "USER_WHITELIST" else None,
        updated_by=updated_by,
    )
    if updated is None:
        return jsonify({"ok": False, "message": "角色不存在"}), 404

    before_snapshot = _data_scope_policy_snapshot(before_policy)
    after_snapshot = _data_scope_policy_snapshot(get_role_data_scope_policy(role_id))
    after_snapshot["change_reason_code"] = change_reason_code
    after_snapshot["change_reason_note"] = change_reason_note
    try:
        write_audit_log(
            action="DATA_SCOPE_UPDATE",
            target_type="role",
            target_id=str(role_id),
            before_obj=before_snapshot,
            after_obj=after_snapshot,
            change_reason_code=change_reason_code,
            change_reason_text=change_reason_note,
        )
    except ValueError as e:
        return jsonify({"ok": False, "message": str(e)}), 400

    _record_admin_log(
        action_type="DATA_SCOPE_CHANGE",
        target_type="role",
        target_id=int(role_id),
        detail=(
            f"role_id={int(role_id)}; scope_type={scope_type}; "
            f"dept_ids={dept_ids}; user_ids={user_ids}; "
            f"change_reason_code={change_reason_code}; change_reason_note={change_reason_note}"
        ),
    )
    return jsonify({"ok": True, "role": updated})


@bp.get("/admin/audit_logs")
@login_required
def admin_audit_logs_page():
    if not _can_view_admin_audit_logs():
        return _forbidden(
            module_name="治理审计日志",
            required_permissions=["MANAGE_SETTINGS", "MANAGE_SYSTEM", "MANAGE_USERS", "MANAGE_ROLES", "MANAGE_RULES"],
        )
    return render_template("admin_audit_logs.html")


GOVERNANCE_ACTION_CN: dict[str, str] = {
    "CREATE_USER": "创建用户",
    "DISABLE_USER": "禁用用户",
    "ENABLE_USER": "启用用户",
    "RESET_PASSWORD": "重置密码",
    "CHANGE_USER_ROLE": "变更用户角色",
    "USER_ENABLE": "启用用户",
    "USER_DISABLE": "禁用用户",
    "USER_RESET_PASSWORD": "重置密码",
    "USER_ROLE_CHANGE": "变更用户角色",
    "ROLE_PERMISSION_UPDATE": "角色权限变更",
    "DATA_SCOPE_CHANGE": "数据范围变更",
    "CREATE_DEPARTMENT": "创建部门",
    "RENAME_DEPARTMENT": "重命名部门",
    "DISABLE_DEPARTMENT": "禁用部门",
    "CREATE_CASE": "创建案件",
    "CLOSE_CASE": "关闭案件",
    "RULE_UPDATE": "修改规则",
    "SETTINGS_UPDATE": "系统设置变更",
    "INVOICE_UPDATE": "单据变更",
    "INVOICE_CREATE": "创建单据",
    "APPROVAL_SUBMIT": "提交审批",
    "APPROVAL_APPROVE": "审批通过",
    "APPROVAL_REJECT": "审批驳回",
}


def _governance_action_cn(action_code: str) -> str:
    key = _safe_text(action_code).upper()
    label = GOVERNANCE_ACTION_CN.get(key)
    if label:
        return label
    return f"未归类操作({key})" if key else "未归类操作(EMPTY)"


def _enrich_audit_row(row: dict) -> dict:
    """为单条审计日志补充中文映射与结构化字段。"""
    action_code = _safe_text(row.get("action_type") or row.get("action")).upper()
    before_raw = row.get("snapshot_before") or ""
    after_raw = row.get("snapshot_after") or ""
    try:
        before_obj = json.loads(before_raw) if isinstance(before_raw, str) and before_raw.strip() else {}
    except Exception:
        before_obj = {}
    try:
        after_obj = json.loads(after_raw) if isinstance(after_raw, str) and after_raw.strip() else {}
    except Exception:
        after_obj = {}

    audit_meta = after_obj.pop("_audit_meta", None) if isinstance(after_obj, dict) else None
    if not isinstance(audit_meta, dict):
        audit_meta = {}

    reason_code = _safe_text(
        row.get("change_reason_code")
        or audit_meta.get("change_reason_code")
    ).upper()
    reason_cn = audit_meta.get("change_reason_code_cn") or to_cn_reason_code(reason_code) if reason_code else ""
    reason_text = _safe_text(audit_meta.get("change_reason_text"))

    diff = audit_meta.get("diff") if isinstance(audit_meta.get("diff"), dict) else {}

    target_type_raw = _safe_text(row.get("target_type"))
    target_id_raw = _safe_text(row.get("target_id"))

    return {
        "id": _safe_int(row.get("id"), 0),
        "created_at": _safe_text(row.get("created_at"), "-"),
        "operator": _safe_text(row.get("operator") or row.get("actor_name"), "-"),
        "action_code": action_code,
        "action_cn": _governance_action_cn(action_code),
        "target_type": target_type_raw,
        "target_id": target_id_raw,
        "result": "成功",
        "client_ip": _safe_text(row.get("client_ip"), "-"),
        "detail": _safe_text(row.get("detail"), ""),
        "reason_code": reason_code,
        "reason_cn": reason_cn,
        "reason_text": reason_text,
        "snapshot_before": before_obj if isinstance(before_obj, dict) else {},
        "snapshot_after": after_obj if isinstance(after_obj, dict) else {},
        "diff": diff,
        "trace_id": _safe_text(row.get("trace_id"), ""),
    }


@bp.get("/api/admin/audit_logs")
@login_required
def admin_audit_logs_api():
    if not _can_view_admin_audit_logs():
        return _forbidden()
    limit = _safe_int(request.args.get("limit"), 500)
    target_type = request.args.get("target_type", "").strip() or None
    target_id = request.args.get("target_id", "").strip() or None
    action_type = request.args.get("action_type", "").strip() or None
    raw_logs = list_audit_logs(limit=limit, target_type=target_type, target_id=target_id, action_type=action_type)
    logs = [_enrich_audit_row(row) for row in raw_logs]
    return jsonify({"ok": True, "logs": logs})

