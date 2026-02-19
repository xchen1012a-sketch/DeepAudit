# -*- coding: utf-8 -*-
"""
HR系统集成：组织架构同步、人员信息同步、权限自动分配
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from services.enterprise_service import create_department, get_department_tree
from services.integration_service import get_integration, log_sync_result, update_last_sync_time
from utils.db import get_conn, generate_password_hash


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def sync_organization_structure(enterprise_id: int) -> dict[str, Any]:
    """同步组织架构"""
    integration = get_integration(enterprise_id=enterprise_id, integration_type="hr")
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "HR系统集成未配置或未启用"}

    config = integration["config"]
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")

    if not api_url:
        return {"ok": False, "msg": "HR API地址未配置"}

    try:
        # TODO: 调用实际的HR系统API获取组织架构
        # 示例：从HR系统获取部门列表
        # departments = fetch_departments_from_hr(api_url, api_key)

        # 模拟同步
        departments_synced = 0
        error_message = None

        # 示例：同步部门数据
        # for dept in departments:
        #     create_department(
        #         enterprise_id=enterprise_id,
        #         dept_code=dept["code"],
        #         dept_name=dept["name"],
        #         parent_id=dept.get("parent_id"),
        #         manager_id=dept.get("manager_id"),
        #     )
        #     departments_synced += 1

        sync_log_id = log_sync_result(
            integration_id=integration["id"],
            sync_type="org_structure_sync",
            status="success",
            records_count=departments_synced,
        )
        update_last_sync_time(integration["id"])

        return {
            "ok": True,
            "msg": "组织架构同步成功",
            "departments_synced": departments_synced,
            "sync_log_id": sync_log_id,
        }
    except Exception as e:
        error_msg = str(e)
        log_sync_result(
            integration_id=integration["id"],
            sync_type="org_structure_sync",
            status="failed",
            error_message=error_msg,
        )
        return {"ok": False, "msg": f"同步失败: {error_msg}"}


def sync_employees(enterprise_id: int) -> dict[str, Any]:
    """同步人员信息"""
    integration = get_integration(enterprise_id=enterprise_id, integration_type="hr")
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "HR系统集成未配置或未启用"}

    config = integration["config"]
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")

    if not api_url:
        return {"ok": False, "msg": "HR API地址未配置"}

    try:
        # TODO: 调用实际的HR系统API获取员工列表
        # employees = fetch_employees_from_hr(api_url, api_key)

        employees_synced = 0
        error_message = None

        # 示例：同步员工数据到users表
        # for emp in employees:
        #     with get_conn() as conn:
        #         # 检查用户是否已存在
        #         existing = conn.execute(
        #             "SELECT id FROM users WHERE username = ?",
        #             (emp["employee_no"],),
        #         ).fetchone()
        #
        #         if not existing:
        #             # 创建新用户，默认密码123456的MD5
        #             default_password_hash = generate_password_hash("123456")
        #             conn.execute(
        #                 """
        #                 INSERT INTO users (username, password_hash, department, employee_name, employee_no, status)
        #                 VALUES (?, ?, ?, ?, ?, 'ACTIVE')
        #                 """,
        #                 (
        #                     emp["employee_no"],
        #                     default_password_hash,
        #                     emp["department"],
        #                     emp["name"],
        #                     emp["employee_no"],
        #                 ),
        #             )
        #             employees_synced += 1

        sync_log_id = log_sync_result(
            integration_id=integration["id"],
            sync_type="employee_sync",
            status="success",
            records_count=employees_synced,
        )
        update_last_sync_time(integration["id"])

        return {
            "ok": True,
            "msg": "人员信息同步成功",
            "employees_synced": employees_synced,
            "sync_log_id": sync_log_id,
        }
    except Exception as e:
        error_msg = str(e)
        log_sync_result(
            integration_id=integration["id"],
            sync_type="employee_sync",
            status="failed",
            error_message=error_msg,
        )
        return {"ok": False, "msg": f"同步失败: {error_msg}"}


def auto_assign_role_by_position(employee_no: str, position: str) -> bool:
    """根据岗位自动分配角色"""
    # 岗位到角色的映射规则
    position_role_map = {
        "财务经理": "财务经理",
        "财务专员": "财务专员",
        "风控专员": "风控专员",
        "系统管理员": "系统管理员",
    }

    role_name = position_role_map.get(position)
    if not role_name:
        return False

    with get_conn() as conn:
        # 获取用户ID
        user_row = conn.execute("SELECT id FROM users WHERE employee_no = ?", (employee_no,)).fetchone()
        if not user_row:
            return False

        user_id = user_row[0]

        # 获取角色ID
        role_row = conn.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,)).fetchone()
        if not role_row:
            return False

        role_id = role_row[0]

        # 检查是否已分配
        existing = conn.execute(
            "SELECT id FROM user_roles WHERE user_id = ? AND role_id = ?",
            (user_id, role_id),
        ).fetchone()

        if not existing:
            conn.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, role_id),
            )

        return True


def handle_employee_change(change_type: str, employee_data: dict[str, Any]) -> dict[str, Any]:
    """处理员工变动（离职、调岗等）"""
    employee_no = _safe_text(employee_data.get("employee_no", ""))
    if not employee_no:
        return {"ok": False, "msg": "员工编号不能为空"}

    with get_conn() as conn:
        user_row = conn.execute("SELECT id FROM users WHERE employee_no = ?", (employee_no,)).fetchone()
        if not user_row:
            return {"ok": False, "msg": "用户不存在"}

        user_id = user_row[0]

        if change_type == "离职":
            # 禁用用户
            conn.execute("UPDATE users SET status = 'INACTIVE' WHERE id = ?", (user_id,))
            return {"ok": True, "msg": "用户已禁用"}

        elif change_type == "调岗":
            # 更新部门和岗位
            new_department = _safe_text(employee_data.get("new_department", ""))
            new_position = _safe_text(employee_data.get("new_position", ""))
            if new_department:
                conn.execute("UPDATE users SET department = ? WHERE id = ?", (new_department, user_id))
            if new_position:
                auto_assign_role_by_position(employee_no, new_position)
            return {"ok": True, "msg": "用户信息已更新"}

        else:
            return {"ok": False, "msg": f"不支持的变动类型: {change_type}"}
