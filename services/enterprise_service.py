# -*- coding: utf-8 -*-
"""
企业服务层：多租户管理、企业配置、数据隔离逻辑
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_enterprise(
    enterprise_code: str,
    enterprise_name: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建企业租户"""
    code = _safe_text(enterprise_code)
    name = _safe_text(enterprise_name)
    if not code or not name:
        raise ValueError("企业代码和企业名称不能为空")

    settings_json = json.dumps(settings or {}, ensure_ascii=False)

    with get_conn() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            """
            INSERT INTO db_enterprises (enterprise_code, enterprise_name, settings_json, status)
            VALUES (?, ?, ?, 'active')
            """,
            (code, name, settings_json),
        )
        enterprise_id = cursor.lastrowid

        row = conn.execute(
            "SELECT * FROM db_enterprises WHERE id = ?",
            (enterprise_id,),
        ).fetchone()
        conn.row_factory = None

        return {
            "id": row[0],
            "enterprise_code": row[1],
            "enterprise_name": row[2],
            "status": row[3],
            "settings_json": row[4],
            "created_at": row[5],
        }


def get_enterprise(enterprise_id: int | None = None, enterprise_code: str | None = None) -> dict[str, Any] | None:
    """获取企业信息"""
    with get_conn() as conn:
        conn.row_factory = None
        if enterprise_id:
            row = conn.execute("SELECT * FROM db_enterprises WHERE id = ?", (enterprise_id,)).fetchone()
        elif enterprise_code:
            row = conn.execute("SELECT * FROM db_enterprises WHERE enterprise_code = ?", (enterprise_code,)).fetchone()
        else:
            return None

        if not row:
            return None

        settings = {}
        if row[4]:
            try:
                settings = json.loads(row[4])
            except Exception:
                pass

        return {
            "id": row[0],
            "enterprise_code": row[1],
            "enterprise_name": row[2],
            "status": row[3],
            "settings": settings,
            "created_at": row[5],
        }


def list_enterprises(status: str | None = None) -> list[dict[str, Any]]:
    """列出所有企业"""
    with get_conn() as conn:
        conn.row_factory = None
        if status:
            rows = conn.execute("SELECT * FROM db_enterprises WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM db_enterprises ORDER BY id").fetchall()

        result = []
        for row in rows:
            settings = {}
            if row[4]:
                try:
                    settings = json.loads(row[4])
                except Exception:
                    pass

            result.append({
                "id": row[0],
                "enterprise_code": row[1],
                "enterprise_name": row[2],
                "status": row[3],
                "settings": settings,
                "created_at": row[5],
            })
        return result


def update_enterprise_settings(enterprise_id: int, settings: dict[str, Any]) -> bool:
    """更新企业配置"""
    settings_json = json.dumps(settings, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "UPDATE db_enterprises SET settings_json = ? WHERE id = ?",
            (settings_json, enterprise_id),
        )
        return True


def create_department(
    enterprise_id: int,
    dept_code: str,
    dept_name: str,
    parent_id: int | None = None,
    manager_id: int | None = None,
) -> dict[str, Any]:
    """创建部门"""
    code = _safe_text(dept_code)
    name = _safe_text(dept_name)
    if not code or not name:
        raise ValueError("部门代码和部门名称不能为空")

    # 计算层级和路径
    level = 1
    path = ""
    if parent_id:
        with get_conn() as conn:
            conn.row_factory = None
            parent_row = conn.execute("SELECT level, path FROM db_departments WHERE id = ?", (parent_id,)).fetchone()
            if parent_row:
                level = _safe_int(parent_row[0], 1) + 1
                parent_path = _safe_text(parent_row[1])
                path = f"{parent_path}/{parent_id}" if parent_path else f"/{parent_id}"

    with get_conn() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            """
            INSERT INTO db_departments (enterprise_id, dept_code, dept_name, parent_id, level, path, manager_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (enterprise_id, code, name, parent_id, level, path, manager_id),
        )
        dept_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM db_departments WHERE id = ?", (dept_id,)).fetchone()
        return {
            "id": row[0],
            "enterprise_id": row[1],
            "dept_code": row[2],
            "dept_name": row[3],
            "parent_id": row[4],
            "level": row[5],
            "path": row[6],
            "manager_id": row[7],
        }


def get_department_tree(enterprise_id: int, parent_id: int | None = None) -> list[dict[str, Any]]:
    """获取部门树形结构"""
    with get_conn() as conn:
        conn.row_factory = None
        if parent_id is None:
            rows = conn.execute(
                "SELECT * FROM db_departments WHERE enterprise_id = ? AND parent_id IS NULL ORDER BY dept_code",
                (enterprise_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM db_departments WHERE enterprise_id = ? AND parent_id = ? ORDER BY dept_code",
                (enterprise_id, parent_id),
            ).fetchall()

        result = []
        for row in rows:
            dept = {
                "id": row[0],
                "enterprise_id": row[1],
                "dept_code": row[2],
                "dept_name": row[3],
                "parent_id": row[4],
                "level": row[5],
                "path": row[6],
                "manager_id": row[7],
            }
            # 递归获取子部门
            children = get_department_tree(enterprise_id, dept["id"])
            if children:
                dept["children"] = children
            result.append(dept)
        return result


def get_enterprise_data_scope_filter(enterprise_id: int) -> str:
    """获取企业数据范围过滤条件（用于SQL查询）"""
    return f"enterprise_id = {enterprise_id}"


def ensure_default_enterprise() -> dict[str, Any]:
    """确保存在默认企业（用于单租户模式兼容）"""
    with get_conn() as conn:
        conn.row_factory = None
        row = conn.execute("SELECT * FROM db_enterprises WHERE enterprise_code = 'DEFAULT'").fetchone()
        if row:
            settings = {}
            if row[4]:
                try:
                    settings = json.loads(row[4])
                except Exception:
                    pass
            return {
                "id": row[0],
                "enterprise_code": row[1],
                "enterprise_name": row[2],
                "status": row[3],
                "settings": settings,
                "created_at": row[5],
            }

        # 创建默认企业
        return create_enterprise("DEFAULT", "默认企业", {})
