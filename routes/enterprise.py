# -*- coding: utf-8 -*-
"""
企业路由：企业列表、切换、配置管理
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request, session

from services.enterprise_service import (
    create_enterprise,
    get_enterprise,
    list_enterprises,
    update_enterprise_settings,
)
from utils.security import current_user, login_required, require_permission

bp = Blueprint("enterprise", __name__)


@bp.route("/enterprise/list")
@login_required
@require_permission("MANAGE_SYSTEM")
def enterprise_list():
    """企业列表页面"""
    return render_template("enterprise/enterprise_center.html")


@bp.route("/api/enterprise/list", methods=["GET"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_enterprise_list():
    """获取企业列表"""
    try:
        status = request.args.get("status")
        enterprises = list_enterprises(status=status)
        return jsonify({"ok": True, "enterprises": enterprises})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/enterprise/get", methods=["GET"])
@login_required
def api_enterprise_get():
    """获取当前企业信息"""
    try:
        enterprise_id = request.args.get("enterprise_id", type=int)
        enterprise_code = request.args.get("enterprise_code")

        enterprise = get_enterprise(enterprise_id=enterprise_id, enterprise_code=enterprise_code)
        if not enterprise:
            return jsonify({"ok": False, "msg": "企业不存在"}), 404

        return jsonify({"ok": True, "enterprise": enterprise})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/enterprise/create", methods=["POST"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_enterprise_create():
    """创建企业"""
    try:
        data = request.get_json() or {}
        enterprise_code = data.get("enterprise_code", "").strip()
        enterprise_name = data.get("enterprise_name", "").strip()
        settings = data.get("settings", {})

        if not enterprise_code or not enterprise_name:
            return jsonify({"ok": False, "msg": "企业代码和企业名称不能为空"}), 400

        enterprise = create_enterprise(enterprise_code, enterprise_name, settings)
        return jsonify({"ok": True, "enterprise": enterprise})
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/enterprise/switch", methods=["POST"])
@login_required
def api_enterprise_switch():
    """切换企业"""
    try:
        data = request.get_json() or {}
        enterprise_id = data.get("enterprise_id", type=int)

        if not enterprise_id:
            return jsonify({"ok": False, "msg": "企业ID不能为空"}), 400

        enterprise = get_enterprise(enterprise_id=enterprise_id)
        if not enterprise:
            return jsonify({"ok": False, "msg": "企业不存在"}), 404

        # 将企业ID存储到session
        session["current_enterprise_id"] = enterprise_id
        session["current_enterprise_code"] = enterprise["enterprise_code"]

        return jsonify({"ok": True, "enterprise": enterprise})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/enterprise/settings", methods=["GET", "POST"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_enterprise_settings():
    """获取或更新企业配置"""
    try:
        enterprise_id = request.args.get("enterprise_id", type=int) or request.json.get("enterprise_id", type=int) if request.is_json else None

        if not enterprise_id:
            return jsonify({"ok": False, "msg": "企业ID不能为空"}), 400

        if request.method == "GET":
            enterprise = get_enterprise(enterprise_id=enterprise_id)
            if not enterprise:
                return jsonify({"ok": False, "msg": "企业不存在"}), 404
            return jsonify({"ok": True, "settings": enterprise.get("settings", {})})

        else:  # POST
            settings = request.get_json().get("settings", {})
            update_enterprise_settings(enterprise_id, settings)
            return jsonify({"ok": True, "msg": "配置已更新"})

    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
