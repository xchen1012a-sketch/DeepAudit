# -*- coding: utf-8 -*-
"""
知识管理服务：案例库管理、知识检索、学习优化
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_risk_case(
    case_code: str,
    risk_type: str,
    severity: str,
    description: str,
    solution: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """创建风险案例"""
    code = _safe_text(case_code)
    if not code:
        raise ValueError("案例代码不能为空")

    tags_json = json.dumps(tags or [], ensure_ascii=False)

    with get_conn() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            """
            INSERT INTO db_risk_cases (case_code, risk_type, severity, description, solution, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, risk_type, severity, description, solution, tags_json),
        )
        case_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM db_risk_cases WHERE id = ?", (case_id,)).fetchone()
        tags_list = []
        if row[6]:
            try:
                tags_list = json.loads(row[6])
            except Exception:
                pass

        return {
            "id": row[0],
            "case_code": row[1],
            "risk_type": row[2],
            "severity": row[3],
            "description": row[4],
            "solution": row[5],
            "tags": tags_list,
            "created_at": row[7],
        }


def get_risk_case(case_id: int | None = None, case_code: str | None = None) -> dict[str, Any] | None:
    """获取风险案例"""
    with get_conn() as conn:
        conn.row_factory = None
        if case_id:
            row = conn.execute("SELECT * FROM db_risk_cases WHERE id = ?", (case_id,)).fetchone()
        elif case_code:
            row = conn.execute("SELECT * FROM db_risk_cases WHERE case_code = ?", (case_code,)).fetchone()
        else:
            return None

        if not row:
            return None

        tags = []
        if row[6]:
            try:
                tags = json.loads(row[6])
            except Exception:
                pass

        return {
            "id": row[0],
            "case_code": row[1],
            "risk_type": row[2],
            "severity": row[3],
            "description": row[4],
            "solution": row[5],
            "tags": tags,
            "created_at": row[7],
        }


def list_risk_cases(risk_type: str | None = None, severity: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """列出风险案例"""
    with get_conn() as conn:
        conn.row_factory = None
        conditions = []
        params = []

        if risk_type:
            conditions.append("risk_type = ?")
            params.append(risk_type)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM db_risk_cases WHERE {where_clause} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()

        result = []
        for row in rows:
            tags = []
            if row[6]:
                try:
                    tags = json.loads(row[6])
                except Exception:
                    pass

            result.append({
                "id": row[0],
                "case_code": row[1],
                "risk_type": row[2],
                "severity": row[3],
                "description": row[4],
                "solution": row[5],
                "tags": tags,
                "created_at": row[7],
            })
        return result


def search_knowledge(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """知识检索"""
    query_lower = query.lower()
    results = []

    # 搜索风险案例
    with get_conn() as conn:
        conn.row_factory = None
        rows = conn.execute(
            """
            SELECT * FROM db_risk_cases
            WHERE LOWER(description) LIKE ? OR LOWER(solution) LIKE ? OR LOWER(case_code) LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{query_lower}%", f"%{query_lower}%", f"%{query_lower}%", limit),
        ).fetchall()

        for row in rows:
            tags = []
            if row[6]:
                try:
                    tags = json.loads(row[6])
                except Exception:
                    pass

            results.append({
                "type": "risk_case",
                "id": row[0],
                "case_code": row[1],
                "risk_type": row[2],
                "severity": row[3],
                "description": row[4],
                "solution": row[5],
                "tags": tags,
                "created_at": row[7],
            })

    # 搜索治理规则（从governance_rules表）
    with get_conn() as conn:
        conn.row_factory = None
        rows = conn.execute(
            """
            SELECT * FROM governance_rules
            WHERE LOWER(rule_name) LIKE ? OR LOWER(rule_key) LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (f"%{query_lower}%", f"%{query_lower}%", limit),
        ).fetchall()

        for row in rows:
            results.append({
                "type": "governance_rule",
                "id": row[0],
                "rule_key": row[1],
                "rule_name": row[2],
                "threshold": row[3],
                "severity": row[6],
                "updated_at": row[8],
            })

    return results


def recommend_rule_optimization() -> list[dict[str, Any]]:
    """推荐规则优化建议"""
    recommendations = []

    # 分析规则执行效果，推荐优化
    with get_conn() as conn:
        conn.row_factory = None

        # 示例：分析高风险规则命中率
        # 如果某个规则命中率过高，可能阈值设置过低
        # 如果某个规则命中率过低，可能阈值设置过高

        # TODO: 实现实际的规则效果分析逻辑
        # 这里只是示例结构

    return recommendations


def extract_knowledge_from_case(case_id: int) -> dict[str, Any]:
    """从风险案例中提取知识"""
    case = get_risk_case(case_id=case_id)
    if not case:
        return {"ok": False, "msg": "案例不存在"}

    # 提取关键信息
    knowledge = {
        "risk_pattern": case["risk_type"],
        "severity": case["severity"],
        "description": case["description"],
        "solution": case["solution"],
        "tags": case["tags"],
    }

    return {
        "ok": True,
        "knowledge": knowledge,
    }
