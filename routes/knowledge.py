# -*- coding: utf-8 -*-
"""
知识路由：案例库、规则库、知识检索
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from services.knowledge_service import (
    create_risk_case,
    extract_knowledge_from_case,
    get_risk_case,
    list_risk_cases,
    recommend_rule_optimization,
    search_knowledge,
)
from utils.security import current_user, login_required, require_permission

bp = Blueprint("knowledge", __name__)


@bp.route("/knowledge/cases")
@login_required
def knowledge_cases():
    """案例库页面"""
    return render_template("knowledge/knowledge_center.html")


@bp.route("/knowledge/rules")
@login_required
def knowledge_rules():
    """规则库页面"""
    return render_template("knowledge/knowledge_center.html")


@bp.route("/api/knowledge/cases", methods=["GET"])
@login_required
def api_knowledge_cases():
    """获取风险案例列表"""
    try:
        risk_type = request.args.get("risk_type")
        severity = request.args.get("severity")
        limit = request.args.get("limit", type=int, default=100)

        cases = list_risk_cases(risk_type=risk_type, severity=severity, limit=limit)
        return jsonify({"ok": True, "cases": cases})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/knowledge/cases/<int:case_id>", methods=["GET"])
@login_required
def api_knowledge_case_detail(case_id: int):
    """获取风险案例详情"""
    try:
        case = get_risk_case(case_id=case_id)
        if not case:
            return jsonify({"ok": False, "msg": "案例不存在"}), 404

        return jsonify({"ok": True, "case": case})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/knowledge/cases/create", methods=["POST"])
@login_required
@require_permission("MANAGE_RULES")
def api_knowledge_case_create():
    """创建风险案例"""
    try:
        data = request.get_json() or {}
        case_code = data.get("case_code", "").strip()
        risk_type = data.get("risk_type", "").strip()
        severity = data.get("severity", "MEDIUM").strip()
        description = data.get("description", "").strip()
        solution = data.get("solution", "").strip()
        tags = data.get("tags", [])

        if not case_code or not description:
            return jsonify({"ok": False, "msg": "案例代码和描述不能为空"}), 400

        case = create_risk_case(case_code, risk_type, severity, description, solution, tags)
        return jsonify({"ok": True, "case": case})
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/knowledge/search", methods=["GET"])
@login_required
def api_knowledge_search():
    """知识检索"""
    try:
        query = request.args.get("query", "").strip()
        limit = request.args.get("limit", type=int, default=20)

        if not query:
            return jsonify({"ok": False, "msg": "搜索关键词不能为空"}), 400

        results = search_knowledge(query, limit=limit)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/knowledge/extract/<int:case_id>", methods=["POST"])
@login_required
@require_permission("MANAGE_RULES")
def api_knowledge_extract(case_id: int):
    """从案例中提取知识"""
    try:
        result = extract_knowledge_from_case(case_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/knowledge/optimization", methods=["GET"])
@login_required
@require_permission("MANAGE_RULES")
def api_knowledge_optimization():
    """获取规则优化建议"""
    try:
        recommendations = recommend_rule_optimization()
        return jsonify({"ok": True, "recommendations": recommendations})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
