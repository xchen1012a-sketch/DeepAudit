import re
import secrets
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import jsonify, redirect, render_template, request, session, url_for

from utils.error_codes import format_error_response, get_http_status
from utils.permission_meta import resolve_forbidden_hint, permission_label_cn
from utils.db import (
    DATA_SCOPE_ALL,
    DATA_SCOPE_DEPT,
    DATA_SCOPE_DEPT_TREE,
    DATA_SCOPE_DEPT_WHITELIST,
    DATA_SCOPE_SELF,
    DATA_SCOPE_SELF_SUB,
    DATA_SCOPE_USER_WHITELIST,
    USER_STATUS_ACTIVE,
    get_department_names_by_ids,
    get_department_tree_names_by_name,
    get_user_by_id,
    get_user_permissions,
    get_user_role_names,
    list_user_role_data_scopes,
    list_user_ids_by_department_names,
    user_has_permission,
)

F = TypeVar("F", bound=Callable[..., Any])

SESSION_USER_ID_KEY = "user_id"
SESSION_CSRF_TOKEN_KEY = "csrf_token"

ACCESS_LEVEL_A = "A"
ACCESS_LEVEL_B = "B"
ACCESS_LEVEL_C = "C"
ACCESS_LEVEL_D = "D"
ACCESS_LEVEL_E = "E"

ACCESS_LEVEL_CN: dict[str, str] = {
    ACCESS_LEVEL_A: "\u666e\u901a\u5458\u5de5",
    ACCESS_LEVEL_B: "\u8d22\u52a1\u4e13\u5458",
    ACCESS_LEVEL_C: "\u8d22\u52a1\u7ecf\u7406/\u4e3b\u7ba1",
    ACCESS_LEVEL_D: "CFO",
    ACCESS_LEVEL_E: "\u6cbb\u7406/\u7cfb\u7edf\u7ba1\u7406",
}

ROLE_KEY_EMPLOYEE = "EMPLOYEE"
ROLE_KEY_FIN_STAFF = "FIN_STAFF"
ROLE_KEY_FIN_MANAGER = "FIN_MANAGER"
ROLE_KEY_FIN_SUPERVISOR = "FIN_SUPERVISOR"
ROLE_KEY_CFO = "CFO"
ROLE_KEY_RISK_SPECIALIST = "RISK_SPECIALIST"
ROLE_KEY_GOVERNANCE_ADMIN = "GOVERNANCE_ADMIN"
ROLE_KEY_SYSTEM_ADMIN = "SYSTEM_ADMIN"

APPROVAL_ROLE_KEYS = {
    ROLE_KEY_FIN_MANAGER,
    ROLE_KEY_FIN_SUPERVISOR,
    ROLE_KEY_CFO,
}

GOVERNANCE_ROLE_KEYS = {
    ROLE_KEY_GOVERNANCE_ADMIN,
    ROLE_KEY_SYSTEM_ADMIN,
}

NON_EMPLOYEE_ROLE_KEYS = {
    ROLE_KEY_FIN_STAFF,
    ROLE_KEY_FIN_MANAGER,
    ROLE_KEY_FIN_SUPERVISOR,
    ROLE_KEY_CFO,
    ROLE_KEY_RISK_SPECIALIST,
    ROLE_KEY_GOVERNANCE_ADMIN,
    ROLE_KEY_SYSTEM_ADMIN,
}

ROLE_ALIAS_MAP: dict[str, str] = {
    "EMPLOYEE": ROLE_KEY_EMPLOYEE,
    "\u5458\u5de5": ROLE_KEY_EMPLOYEE,
    "\u666e\u901a\u5458\u5de5": ROLE_KEY_EMPLOYEE,
    "FIN_STAFF": ROLE_KEY_FIN_STAFF,
    "FINANCE_STAFF": ROLE_KEY_FIN_STAFF,
    "FINANCE_SPECIALIST": ROLE_KEY_FIN_STAFF,
    "\u8d22\u52a1\u4e13\u5458": ROLE_KEY_FIN_STAFF,
    "\u8d22\u52a1\u4eba\u5458": ROLE_KEY_FIN_STAFF,
    "FINANCE": ROLE_KEY_FIN_STAFF,
    "FIN_MANAGER": ROLE_KEY_FIN_MANAGER,
    "FINANCE_MANAGER": ROLE_KEY_FIN_MANAGER,
    "\u8d22\u52a1\u7ecf\u7406": ROLE_KEY_FIN_MANAGER,
    "FIN_SUPERVISOR": ROLE_KEY_FIN_SUPERVISOR,
    "FINANCE_SUPERVISOR": ROLE_KEY_FIN_SUPERVISOR,
    "\u8d22\u52a1\u4e3b\u7ba1": ROLE_KEY_FIN_SUPERVISOR,
    "CFO": ROLE_KEY_CFO,
    "RISK_SPECIALIST": ROLE_KEY_RISK_SPECIALIST,
    "RISK_STAFF": ROLE_KEY_RISK_SPECIALIST,
    "\u98ce\u63a7\u4e13\u5458": ROLE_KEY_RISK_SPECIALIST,
    "GOVERNANCE_ADMIN": ROLE_KEY_GOVERNANCE_ADMIN,
    "GOV_ADMIN": ROLE_KEY_GOVERNANCE_ADMIN,
    "\u6cbb\u7406\u7ba1\u7406\u5458": ROLE_KEY_GOVERNANCE_ADMIN,
    "SYSTEM_ADMIN": ROLE_KEY_SYSTEM_ADMIN,
    "SYS_ADMIN": ROLE_KEY_SYSTEM_ADMIN,
    "ADMIN": ROLE_KEY_SYSTEM_ADMIN,
    "\u7ba1\u7406\u5458": ROLE_KEY_SYSTEM_ADMIN,
    "\u7cfb\u7edf\u7ba1\u7406\u5458": ROLE_KEY_SYSTEM_ADMIN,
}

ROLE_SPLIT_RE = re.compile(r"[,;\uFF0C\uFF1B/|\\\\]+")

# 已知系统管理员账号：即使用户表/角色表未正确关联，也视为系统管理员（兜底）
SYSTEM_ADMIN_USERNAMES = frozenset({"admin", "admin01", "administrator", "system_admin", "sys_admin"})

GOVERNANCE_PERMISSION_KEYS = {
    "MANAGE_USERS",
    "MANAGE_ROLES",
    "MANAGE_RULES",
    "MANAGE_SETTINGS",
    "MANAGE_SYSTEM",
}

APPROVAL_PERMISSION_KEYS = {
    "CREATE_CASE",
    "ASSIGN_CASE",
    "CLOSE_CASE",
}

LEGACY_ROLE_PERMISSION_FALLBACK: dict[str, set[str]] = {
    "admin": {
        "VIEW_DASHBOARD",
        "VIEW_UPLOAD_PAGE",
        "VIEW_BANK_STATS",
        "VIEW_INVOICES",
        "CREATE_CASE",
        "ASSIGN_CASE",
        "CLOSE_CASE",
        "DELETE_INVOICE",
        "PULL_BANK_TXN",
        "BANK_PULL",
        "VIEW_AI_LEDGER",
        "MANAGE_USERS",
        "MANAGE_ROLES",
        "MANAGE_RULES",
        "MANAGE_SETTINGS",
        "MANAGE_SYSTEM",
    },
    "finance_manager": {
        "VIEW_DASHBOARD",
        "VIEW_UPLOAD_PAGE",
        "VIEW_BANK_STATS",
        "VIEW_INVOICES",
        "CREATE_CASE",
        "ASSIGN_CASE",
        "CLOSE_CASE",
        "DELETE_INVOICE",
    },
    "finance": {
        "VIEW_DASHBOARD",
        "VIEW_UPLOAD_PAGE",
        "VIEW_BANK_STATS",
        "VIEW_INVOICES",
    },
    "employee": {
        "VIEW_UPLOAD_PAGE",
    },
    "staff": {
        "VIEW_UPLOAD_PAGE",
    },
    "governance_admin": {
        "MANAGE_RULES",
        "VIEW_AI_LEDGER",
    },
}

PERMISSION_ALIASES: dict[str, set[str]] = {
    "PULL_BANK_TXN": {"BANK_PULL"},
    "BANK_PULL": {"PULL_BANK_TXN"},
    "MANAGE_SETTINGS": {"MANAGE_SYSTEM"},
    "MANAGE_SYSTEM": {"MANAGE_SETTINGS"},
    "VIEW_BANK_STATS": {"VIEW_DASHBOARD"},
}

DATA_SCOPE_TYPES = {
    DATA_SCOPE_SELF,
    DATA_SCOPE_SELF_SUB,
    DATA_SCOPE_DEPT,
    DATA_SCOPE_DEPT_TREE,
    DATA_SCOPE_DEPT_WHITELIST,
    DATA_SCOPE_USER_WHITELIST,
    DATA_SCOPE_ALL,
}

DATA_SCOPE_CN_MAP: dict[str, str] = {
    DATA_SCOPE_SELF: "本人",
    DATA_SCOPE_SELF_SUB: "本人+下属",
    DATA_SCOPE_DEPT: "本部门",
    DATA_SCOPE_DEPT_TREE: "本部门+下级",
    DATA_SCOPE_DEPT_WHITELIST: "指定部门",
    DATA_SCOPE_USER_WHITELIST: "指定人员",
    DATA_SCOPE_ALL: "全量",
}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _normalize_data_scope(value: Any, fallback: str = DATA_SCOPE_DEPT) -> str:
    normalized = _safe_text(value).upper()
    if normalized in DATA_SCOPE_TYPES:
        return normalized
    fallback_scope = _safe_text(fallback, DATA_SCOPE_DEPT).upper()
    if fallback_scope in DATA_SCOPE_TYPES:
        return fallback_scope
    return DATA_SCOPE_DEPT


def _scope_priority(scope_type: str) -> int:
    normalized = _normalize_data_scope(scope_type)
    priority = {
        DATA_SCOPE_SELF: 0,
        DATA_SCOPE_SELF_SUB: 1,
        DATA_SCOPE_DEPT: 2,
        DATA_SCOPE_DEPT_TREE: 3,
        DATA_SCOPE_DEPT_WHITELIST: 4,
        DATA_SCOPE_USER_WHITELIST: 4,
        DATA_SCOPE_ALL: 5,
    }
    return int(priority.get(normalized, 0))


def _safe_positive_int(value: Any) -> int:
    try:
        normalized = int(value)
    except Exception:
        return 0
    return normalized if normalized > 0 else 0


def _normalize_role_token(value: Any) -> str:
    token = _safe_text(value).upper()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_")


def _infer_role_key_from_token(value: Any) -> str | None:
    normalized = _normalize_role_token(value)
    if not normalized:
        return None

    return ROLE_ALIAS_MAP.get(normalized)


def _extract_role_keys_from_text(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        merged: set[str] = set()
        for item in value:
            merged |= _extract_role_keys_from_text(item)
        return merged

    raw = _safe_text(value)
    if not raw:
        return set()

    role_keys: set[str] = set()
    candidates = {raw}
    for part in ROLE_SPLIT_RE.split(raw):
        normalized_part = _safe_text(part)
        if normalized_part:
            candidates.add(normalized_part)

    for candidate in candidates:
        mapped = _infer_role_key_from_token(candidate)
        if mapped:
            role_keys.add(mapped)
    return role_keys


def _is_system_admin_username(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    username = _safe_text(user.get("username")).lower()
    return username in SYSTEM_ADMIN_USERNAMES


def current_user_role_keys(user: dict[str, Any] | None = None) -> set[str]:
    target = user if user is not None else current_user()
    if not target:
        return set()

    role_keys: set[str] = set()
    # 兜底：已知系统管理员用户名直接赋予系统管理员角色
    if _is_system_admin_username(target):
        role_keys.add(ROLE_KEY_SYSTEM_ADMIN)
    role_keys |= _extract_role_keys_from_text(target.get("role"))

    user_id = target.get("id")
    for role_name in get_user_role_names(user_id):
        role_keys |= _extract_role_keys_from_text(role_name)
    return role_keys


def has_governance_admin_role(user: dict[str, Any] | None = None) -> bool:
    return bool(current_user_role_keys(user) & GOVERNANCE_ROLE_KEYS)


def is_system_admin(user: dict[str, Any] | None = None) -> bool:
    target = user if user is not None else current_user()
    username_check = _is_system_admin_username(target) if target else False
    role_check = ROLE_KEY_SYSTEM_ADMIN in current_user_role_keys(user)
    if target and username_check:
        return True
    return role_check


def can_approve(user: dict[str, Any] | None = None) -> bool:
    if is_system_admin(user):
        return True
    role_keys = current_user_role_keys(user)
    if role_keys & APPROVAL_ROLE_KEYS:
        return True
    permissions = current_user_permissions(user)
    return bool(permissions & APPROVAL_PERMISSION_KEYS)


def _expand_permission_keys(values: set[str]) -> set[str]:
    expanded = {str(item or "").strip().upper() for item in values if str(item or "").strip()}
    queue = list(expanded)
    while queue:
        key = queue.pop()
        for alias in PERMISSION_ALIASES.get(key, set()):
            normalized = str(alias or "").strip().upper()
            if not normalized or normalized in expanded:
                continue
            expanded.add(normalized)
            queue.append(normalized)
    return expanded


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_user_active(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    status = _safe_text(user.get("status"), USER_STATUS_ACTIVE).upper()
    return status == USER_STATUS_ACTIVE


def current_user() -> dict[str, Any] | None:
    raw_user_id = session.get(SESSION_USER_ID_KEY)
    if raw_user_id is None:
        return None

    try:
        user_id = int(raw_user_id)
    except Exception:
        session.pop(SESSION_USER_ID_KEY, None)
        return None

    user = get_user_by_id(user_id)
    if user is None or not _is_user_active(user):
        session.pop(SESSION_USER_ID_KEY, None)
        return None
    return user


def _legacy_permissions(user: dict[str, Any] | None) -> set[str]:
    if not user:
        return set()

    # 兜底：已知系统管理员用户名直接赋予全部管理员权限
    if _is_system_admin_username(user):
        admin_perms = LEGACY_ROLE_PERMISSION_FALLBACK.get("admin", set())
        return {item.strip().upper() for item in admin_perms if item.strip()}

    role = _safe_text(user.get("role")).lower()
    permissions: set[str] = set()
    for key, values in LEGACY_ROLE_PERMISSION_FALLBACK.items():
        if key == role or (key in role and key != "admin"):
            permissions |= values

    if role == "admin" or role.startswith("admin"):
        permissions |= LEGACY_ROLE_PERMISSION_FALLBACK.get("admin", set())
    # 中文角色名兜底：系统管理员、管理员 视为 admin
    if role in ("系统管理员", "管理员") or (role and "系统管理员" in role):
        permissions |= LEGACY_ROLE_PERMISSION_FALLBACK.get("admin", set())

    return {item.strip().upper() for item in permissions if item.strip()}


def current_user_permissions(user: dict[str, Any] | None = None) -> set[str]:
    target = user if user is not None else current_user()
    if not target:
        return set()

    user_id = target.get("id")
    # 每次都从数据库实时查询权限，避免缓存问题
    db_permissions = {item.strip().upper() for item in get_user_permissions(user_id) if item.strip()}
    
    # 系统管理员特殊处理：即使没有数据库权限记录，也给予完整权限
    if is_system_admin(target):
        admin_perms = LEGACY_ROLE_PERMISSION_FALLBACK.get("admin", set())
        db_permissions |= {item.strip().upper() for item in admin_perms if item.strip()}
    
    if db_permissions:
        return _expand_permission_keys(db_permissions)
    
    # 如果数据库中没有权限记录，使用兜底逻辑（仅用于向后兼容）
    return _expand_permission_keys(_legacy_permissions(target))


def access_level(user: dict[str, Any] | None = None) -> str:
    target = user if user is not None else current_user()
    if not target:
        return ACCESS_LEVEL_A

    role_keys = current_user_role_keys(target)
    if role_keys & GOVERNANCE_ROLE_KEYS:
        return ACCESS_LEVEL_E
    if ROLE_KEY_CFO in role_keys:
        return ACCESS_LEVEL_D
    if role_keys & {ROLE_KEY_FIN_MANAGER, ROLE_KEY_FIN_SUPERVISOR}:
        return ACCESS_LEVEL_C
    if role_keys & {ROLE_KEY_FIN_STAFF, ROLE_KEY_RISK_SPECIALIST}:
        return ACCESS_LEVEL_B
    if ROLE_KEY_EMPLOYEE in role_keys and not (role_keys - {ROLE_KEY_EMPLOYEE}):
        return ACCESS_LEVEL_A

    permissions = current_user_permissions(target)
    if permissions & GOVERNANCE_PERMISSION_KEYS:
        return ACCESS_LEVEL_E
    if permissions & APPROVAL_PERMISSION_KEYS:
        return ACCESS_LEVEL_C

    return ACCESS_LEVEL_A


def _safe_access_level_key(value: Any) -> str:
    level_key = _safe_text(value, ACCESS_LEVEL_A).upper()
    if level_key in ACCESS_LEVEL_CN:
        return level_key
    return ACCESS_LEVEL_A


def access_level_cn(user: dict[str, Any] | None = None) -> str:
    return ACCESS_LEVEL_CN[_safe_access_level_key(access_level(user))]


def _legacy_owner_scoped(user: dict[str, Any] | None = None) -> bool:
    target = user if user is not None else current_user()
    if not target:
        return False

    role_keys = current_user_role_keys(target)
    if not role_keys:
        return access_level(target) == ACCESS_LEVEL_A
    if ROLE_KEY_EMPLOYEE not in role_keys:
        return False
    return not bool((role_keys - {ROLE_KEY_EMPLOYEE}) & NON_EMPLOYEE_ROLE_KEYS)


def _user_identity_values(user: dict[str, Any] | None) -> set[str]:
    target = user if user is not None else current_user()
    if not target:
        return set()
    values = {
        _safe_text(target.get("username")).lower(),
        _safe_text(target.get("employee_no")).lower(),
        _safe_text(target.get("employee_name")).lower(),
    }
    return {item for item in values if item}


def apply_data_scope_filter(
    role: Any | None = None,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = user if user is not None else current_user()
    if not target:
        return {
            "scope_type": DATA_SCOPE_DEPT,
            "scope_type_cn": DATA_SCOPE_CN_MAP.get(DATA_SCOPE_DEPT, DATA_SCOPE_DEPT),
            "department": None,
            "department_names": [],
            "departments": [],
            "department_count": 0,
            "dept_ids": [],
            "owner_user_id": 0,
            "owner_identity_values": [],
            "self_only": False,
            "all_access": False,
            "role_scopes": [],
        }

    user_id = _safe_positive_int(target.get("id"))
    user_department = _safe_text(target.get("department"))

    # 系统管理员（如 admin01）或 user_id=1（常见首个管理员）直接返回全量范围
    if is_system_admin(target) or user_id == 1:
        return {
            "scope_type": DATA_SCOPE_ALL,
            "scope_type_cn": DATA_SCOPE_CN_MAP.get(DATA_SCOPE_ALL, DATA_SCOPE_ALL),
            "department": None,
            "department_names": [],
            "departments": [],
            "department_count": 0,
            "dept_ids": [],
            "owner_user_id": 0,
            "owner_identity_values": [],
            "self_only": False,
            "all_access": True,
            "role_scopes": [{"scope_type": DATA_SCOPE_ALL, "dept_ids": [], "user_ids": []}],
        }

    role_scopes: list[dict[str, Any]] = []
    if isinstance(role, dict):
        role_scopes = [
            {
                "scope_type": _normalize_data_scope(role.get("scope_type") or role.get("data_scope")),
                "dept_ids": role.get("dept_ids") or [],
                "user_ids": role.get("user_ids") or [],
            }
        ]
    elif isinstance(role, str) and _normalize_data_scope(role, "") in DATA_SCOPE_TYPES:
        role_scopes = [
            {
                "scope_type": _normalize_data_scope(role),
                "dept_ids": [],
                "user_ids": [],
            }
        ]
    else:
        role_id = _safe_positive_int(role)
        if role_id > 0 and user_id > 0:
            role_scopes = [
                item for item in list_user_role_data_scopes(user_id)
                if _safe_positive_int(item.get("role_id")) == role_id
            ]
        elif user_id > 0:
            role_scopes = list_user_role_data_scopes(user_id)

    if not role_scopes:
        if is_system_admin(target):
            role_scopes = [{"scope_type": DATA_SCOPE_ALL, "dept_ids": [], "user_ids": []}]
        elif _legacy_owner_scoped(target):
            role_scopes = [{"scope_type": DATA_SCOPE_SELF, "dept_ids": [], "user_ids": []}]
        else:
            role_scopes = [{"scope_type": DATA_SCOPE_DEPT, "dept_ids": [], "user_ids": []}]

    all_access = False
    contains_self = False
    effective_scope = DATA_SCOPE_SELF
    allowed_departments: list[str] = []
    allowed_user_ids: list[int] = []
    seen_departments: set[str] = set()
    seen_user_ids: set[int] = set()
    merged_dept_ids: list[int] = []
    for item in role_scopes:
        scope_type = _normalize_data_scope(item.get("scope_type") or item.get("data_scope"))
        dept_ids_raw = item.get("dept_ids")
        dept_ids: list[int] = []
        for raw in dept_ids_raw if isinstance(dept_ids_raw, (list, tuple, set)) else []:
            dept_id = _safe_positive_int(raw)
            if dept_id <= 0 or dept_id in dept_ids:
                continue
            dept_ids.append(dept_id)
            if dept_id not in merged_dept_ids:
                merged_dept_ids.append(dept_id)
        user_ids_raw = item.get("user_ids")
        item_user_ids: list[int] = []
        for raw in user_ids_raw if isinstance(user_ids_raw, (list, tuple, set)) else []:
            uid = _safe_positive_int(raw)
            if uid <= 0 or uid in item_user_ids:
                continue
            item_user_ids.append(uid)

        if _scope_priority(scope_type) > _scope_priority(effective_scope):
            effective_scope = scope_type

        if scope_type == DATA_SCOPE_ALL:
            all_access = True
            continue
        if scope_type == DATA_SCOPE_SELF:
            contains_self = True
            continue
        if scope_type == DATA_SCOPE_SELF_SUB:
            if user_department and user_department not in seen_departments:
                seen_departments.add(user_department)
                allowed_departments.append(user_department)
            sub_ids = list_user_ids_by_department_names([user_department] if user_department else [])
            if user_id > 0 and user_id not in seen_user_ids:
                seen_user_ids.add(user_id)
                allowed_user_ids.append(user_id)
            for uid in sub_ids:
                if uid > 0 and uid not in seen_user_ids:
                    seen_user_ids.add(uid)
                    allowed_user_ids.append(uid)
            continue
        if scope_type == DATA_SCOPE_DEPT:
            if user_department and user_department not in seen_departments:
                seen_departments.add(user_department)
                allowed_departments.append(user_department)
            continue
        if scope_type == DATA_SCOPE_DEPT_TREE:
            tree_names = get_department_tree_names_by_name(user_department, include_self=True) if user_department else []
            if not tree_names and user_department:
                tree_names = [user_department]
            for name in tree_names:
                normalized_name = _safe_text(name)
                if not normalized_name or normalized_name in seen_departments:
                    continue
                seen_departments.add(normalized_name)
                allowed_departments.append(normalized_name)
            continue
        if scope_type == DATA_SCOPE_DEPT_WHITELIST:
            for name in get_department_names_by_ids(dept_ids):
                normalized_name = _safe_text(name)
                if not normalized_name or normalized_name in seen_departments:
                    continue
                seen_departments.add(normalized_name)
                allowed_departments.append(normalized_name)
            continue
        if scope_type == DATA_SCOPE_USER_WHITELIST:
            for uid in item_user_ids:
                if uid > 0 and uid not in seen_user_ids:
                    seen_user_ids.add(uid)
                    allowed_user_ids.append(uid)
            continue

    if not all_access and not allowed_departments and not contains_self and not allowed_user_ids and user_department:
        allowed_departments.append(user_department)

    self_only = contains_self and not all_access and not bool(allowed_departments) and not bool(allowed_user_ids)
    owner_user_id = user_id if self_only and user_id > 0 else 0
    owner_identity_values = sorted(_user_identity_values(target)) if self_only else []

    scope_type = DATA_SCOPE_ALL if all_access else _normalize_data_scope(effective_scope, DATA_SCOPE_DEPT)
    if self_only:
        scope_type = DATA_SCOPE_SELF
    elif scope_type == DATA_SCOPE_SELF and (allowed_departments or allowed_user_ids):
        scope_type = DATA_SCOPE_DEPT

    department = allowed_departments[0] if len(allowed_departments) == 1 else None
    return {
        "scope_type": scope_type,
        "scope_type_cn": DATA_SCOPE_CN_MAP.get(scope_type, scope_type),
        "department": department,
        "department_names": allowed_departments,
        "departments": allowed_departments,
        "department_count": len(allowed_departments),
        "dept_ids": merged_dept_ids,
        "owner_user_id": owner_user_id,
        "owner_identity_values": owner_identity_values,
        "allowed_user_ids": allowed_user_ids,
        "self_only": self_only,
        "all_access": all_access,
        "role_scopes": role_scopes,
    }


def is_owner_scoped(user: dict[str, Any] | None = None) -> bool:
    scope = apply_data_scope_filter(user=user)
    return bool(scope.get("self_only"))


def owner_scope_user_id(user: dict[str, Any] | None = None) -> int | None:
    scope = apply_data_scope_filter(user=user)
    user_id = _safe_positive_int(scope.get("owner_user_id"))
    return user_id if user_id > 0 else None


def owner_scope_identity_values(user: dict[str, Any] | None = None) -> set[str]:
    scope = apply_data_scope_filter(user=user)
    values = scope.get("owner_identity_values")
    if isinstance(values, (list, tuple, set)):
        return {
            _safe_text(item).lower()
            for item in values
            if _safe_text(item)
        }
    return set()


def can_access_approval_console(user: dict[str, Any] | None = None) -> bool:
    return can_approve(user)


def can_manage_workflow(user: dict[str, Any] | None = None) -> bool:
    if is_system_admin(user):
        return True
    if has_governance_admin_role(user):
        return True
    permissions = current_user_permissions(user)
    return bool(permissions & {"MANAGE_SETTINGS", "MANAGE_SYSTEM", "MANAGE_RULES"})


def can_governance(user: dict[str, Any] | None = None) -> bool:
    if is_system_admin(user):
        return True
    if has_governance_admin_role(user):
        return True
    permissions = current_user_permissions(user)
    return bool(permissions & GOVERNANCE_PERMISSION_KEYS)


def approval_allowed_workflow_roles(user: dict[str, Any] | None = None) -> set[str]:
    if is_system_admin(user):
        return {"MANAGER", "CFO"}
    role_keys = current_user_role_keys(user)
    allowed: set[str] = set()
    if role_keys & {ROLE_KEY_FIN_MANAGER, ROLE_KEY_FIN_SUPERVISOR}:
        allowed.add('MANAGER')
    if ROLE_KEY_CFO in role_keys:
        allowed.add('CFO')
    if allowed:
        return allowed

    # Keep role-based behavior for built-in risk specialist roles.
    if ROLE_KEY_RISK_SPECIALIST in role_keys:
        return allowed

    # Fallback for custom roles: explicit permission grants should be usable.
    permissions = current_user_permissions(user)
    if permissions & APPROVAL_PERMISSION_KEYS:
        allowed.add("MANAGER")
    if (permissions & APPROVAL_PERMISSION_KEYS) and (permissions & GOVERNANCE_PERMISSION_KEYS):
        allowed.add("CFO")
    return allowed


def _permission_blocked_by_access_level(permission_key: str, user: dict[str, Any]) -> bool:
    # Explicit permissions in DB are the source of truth. Avoid role-name-based
    # secondary denials for custom roles.
    _ = permission_key, user
    return False


def has_permission(permission_key: str, user: dict[str, Any] | None = None) -> bool:
    target = user if user is not None else current_user()
    if not target:
        return False

    normalized_key = _safe_text(permission_key).upper()
    if not normalized_key:
        return False
    if is_system_admin(target):
        return True

    expanded_keys = _expand_permission_keys({normalized_key})
    if any(_permission_blocked_by_access_level(key, target) for key in expanded_keys):
        return False

    user_id = target.get("id")
    if user_has_permission(user_id, normalized_key):
        return True
    for alias_key in PERMISSION_ALIASES.get(normalized_key, set()):
        if user_has_permission(user_id, alias_key):
            return True
    return normalized_key in current_user_permissions(target)


def current_data_scope(user: dict[str, Any] | None = None) -> str:
    scope = apply_data_scope_filter(user=user)
    return _normalize_data_scope(scope.get("scope_type"), DATA_SCOPE_DEPT)


def current_scope_department(user: dict[str, Any] | None = None) -> str | None:
    scope = apply_data_scope_filter(user=user)
    return _safe_text(scope.get("department")) or None


def current_scope_departments(user: dict[str, Any] | None = None) -> list[str]:
    scope = apply_data_scope_filter(user=user)
    values = scope.get("department_names")
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        name = _safe_text(item)
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def is_finance(user: dict[str, Any] | None = None) -> bool:
    target = user if user is not None else current_user()
    if not target:
        return False

    role_keys = current_user_role_keys(target)
    if role_keys & {ROLE_KEY_FIN_STAFF, ROLE_KEY_FIN_MANAGER, ROLE_KEY_FIN_SUPERVISOR, ROLE_KEY_CFO}:
        return True

    role = str(target.get('role') or '').strip().lower()
    department = str(target.get('department') or '').strip().lower()
    if 'finance' in role or '\u8d22\u52a1' in role:
        return True
    if 'finance' in department or '\u8d22\u52a1' in department:
        return True
    return False


def is_password_change_required(user: dict[str, Any] | None = None) -> bool:
    target = user if user is not None else current_user()
    if not target:
        return False
    return _as_bool(target.get("must_change_password"))


def ensure_csrf_token() -> str:
    token = _safe_text(session.get(SESSION_CSRF_TOKEN_KEY))
    if token:
        return token
    token = secrets.token_urlsafe(32)
    session[SESSION_CSRF_TOKEN_KEY] = token
    return token


def get_csrf_token() -> str:
    return ensure_csrf_token()


def validate_csrf_request() -> bool:
    expected = _safe_text(session.get(SESSION_CSRF_TOKEN_KEY))
    if not expected:
        return False

    candidates: list[str] = []
    for key in ("X-CSRF-Token", "X-CSRFToken"):
        header_value = _safe_text(request.headers.get(key))
        if header_value:
            candidates.append(header_value)

    form_value = _safe_text(request.form.get("csrf_token"))
    if form_value:
        candidates.append(form_value)

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            body_value = _safe_text(payload.get("csrf_token"))
            if body_value:
                candidates.append(body_value)

    for candidate in candidates:
        try:
            if secrets.compare_digest(expected, candidate):
                return True
        except Exception:
            if expected == candidate:
                return True
    return False


def _wants_json_response() -> bool:
    if request.path.startswith("/api/"):
        return True
    accepts = request.accept_mimetypes
    best = accepts.best_match(["text/html", "application/json"])
    if best == "application/json":
        return accepts["application/json"] > accepts["text/html"]
    return False


def _unauthorized_response(technical_details: dict[str, Any] | None = None) -> tuple[Any, int] | Any:
    """未授权响应（401）- 企业级格式，支持技术信息折叠"""
    if _wants_json_response():
        error_response = format_error_response(
            "unauthorized",
            technical_details=technical_details or {"path": request.path, "method": request.method},
        )
        return jsonify(error_response), 401
    return redirect(url_for("auth.login", next=request.path))


def _forbidden_response(permission_key: str | None = None, technical_details: dict[str, Any] | None = None) -> tuple[Any, int] | Any:
    """权限禁止响应（403）- 企业级格式，支持技术信息折叠"""
    normalized_key = _safe_text(permission_key).upper()
    module_name, required_permissions = resolve_forbidden_hint(request.path, normalized_key)
    
    if _wants_json_response():
        # 构建技术详情
        tech_details = technical_details or {}
        tech_details.update({
            "path": request.path,
            "method": request.method,
            "required_permission": normalized_key,
            "required_permissions": required_permissions,
            "module_name": module_name,
        })
        
        # 构建权限标签列表
        permission_labels = [permission_label_cn(key) for key in required_permissions if key]
        
        error_response = format_error_response(
            "forbidden",
            message_cn=f"无权限访问{module_name}" if module_name else "无权限访问该资源",
            technical_details=tech_details,
        )
        # 添加权限提示
        if permission_labels:
            error_response["error"]["required_permissions_cn"] = permission_labels
        
        return jsonify(error_response), 403
    
    return (
        render_template(
            'forbidden.html',
            module_name=module_name,
            required_permissions=required_permissions,
        ),
        403,
    )


def _password_change_required_response() -> tuple[Any, int] | Any:
    """密码修改要求响应（403）- 企业级格式"""
    if _wants_json_response():
        error_response = format_error_response(
            "password_change_required",
            technical_details={"path": request.path},
        )
        return jsonify(error_response), 403
    return redirect("/profile?force_password=1")


def _is_password_change_allowed_path(path: str) -> bool:
    normalized = _safe_text(path)
    if not normalized:
        return False
    if normalized.startswith("/static/"):
        return True
    return normalized in {
        "/profile",
        "/logout",
        "/api/me",
        "/api/auth/change_password",
        "/api/auth/update_profile",
    }


def login_required(view_func: F) -> F:
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        user = current_user()
        if user is None:
            return _unauthorized_response()
        if is_password_change_required(user) and not _is_password_change_allowed_path(request.path):
            return _password_change_required_response()
        return view_func(*args, **kwargs)

    return cast(F, wrapper)


def finance_required(view_func: F) -> F:
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        user = current_user()
        if user is None:
            return _unauthorized_response()
        if is_password_change_required(user) and not _is_password_change_allowed_path(request.path):
            return _password_change_required_response()
        if not is_finance(user):
            return _forbidden_response()
        return view_func(*args, **kwargs)

    return cast(F, wrapper)


def require_permission(permission_key: str) -> Callable[[F], F]:
    normalized_key = _safe_text(permission_key).upper()

    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = current_user()
            if user is None:
                return _unauthorized_response()
            perm_result = has_permission(normalized_key, user)
            if not perm_result:
                return _forbidden_response(normalized_key)
            if is_password_change_required(user) and not _is_password_change_allowed_path(request.path):
                return _password_change_required_response()
            return view_func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator
