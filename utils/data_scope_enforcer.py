# -*- coding: utf-8 -*-
"""
企业级数据范围强制过滤工具
确保所有数据查询都应用数据范围过滤，防止越权访问
"""

from typing import Any

from utils.security import (
    apply_data_scope_filter,
    current_user,
    is_system_admin,
    DATA_SCOPE_ALL,
)


def enforce_data_scope_check(
    target_department: str | None = None,
    target_owner_id: int | None = None,
    target_owner_identity: str | None = None,
    *,
    user: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    强制检查数据范围权限（企业级越权防护）
    
    Args:
        target_department: 目标数据所属部门
        target_owner_id: 目标数据所有者ID
        target_owner_identity: 目标数据所有者身份标识（用户名/工号等）
        user: 当前用户（如果为None则从session获取）
    
    Returns:
        (is_allowed, reason_cn) - 是否允许访问，不允许时的中文原因
    """
    target = user if user is not None else current_user()
    if not target:
        return False, "未登录用户无权访问"
    
    # 系统管理员拥有所有权限
    if is_system_admin(target):
        return True, ""
    
    # 获取用户的数据范围
    scope_filter = apply_data_scope_filter(user=target)
    scope_type = scope_filter.get("scope_type", "")
    all_access = scope_filter.get("all_access", False)
    
    if all_access or scope_type == DATA_SCOPE_ALL:
        return True, ""
    
    # 检查部门范围
    if target_department:
        allowed_departments = scope_filter.get("department_names", [])
        if allowed_departments and target_department not in allowed_departments:
            return False, f"无权访问部门「{target_department}」的数据"

    # 检查所有者/指定人员范围（self_only 或 allowed_user_ids）
    allowed_user_ids = scope_filter.get("allowed_user_ids") or []
    if scope_filter.get("self_only", False):
        user_id = target.get("id")
        if target_owner_id is not None and target_owner_id != user_id:
            return False, "无权访问其他用户的数据"
        if target_owner_identity:
            owner_identity_values = scope_filter.get("owner_identity_values", [])
            normalized_identity = str(target_owner_identity or "").strip().lower()
            if owner_identity_values and normalized_identity not in [
                str(v).lower() for v in owner_identity_values
            ]:
                return False, "无权访问其他用户的数据"
    elif allowed_user_ids and target_owner_id is not None and target_owner_id not in allowed_user_ids:
        return False, "您无权访问该数据范围的数据（指定人员外）"

    return True, ""


def get_enforced_data_scope(user: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    获取强制应用的数据范围过滤器（用于SQL查询）
    
    Returns:
        数据范围过滤器字典，包含 department, owner_user_id, owner_identity_values 等
    """
    target = user if user is not None else current_user()
    if not target:
        # 未登录用户返回最严格的范围
        return {
            "scope_type": "SELF",
            "department_names": [],
            "owner_user_id": 0,
            "owner_identity_values": [],
            "self_only": True,
            "all_access": False,
        }
    
    return apply_data_scope_filter(user=target)
