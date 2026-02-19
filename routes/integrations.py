# -*- coding: utf-8 -*-
"""
集成路由：集成配置、同步、状态查询
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from services.bank_integration import pull_bank_transactions
from services.finance_integration import sync_erp_vouchers
from services.hr_integration import sync_employees, sync_organization_structure
from services.integration_service import (
    create_integration,
    get_integration,
    get_sync_logs,
    list_integrations,
    update_integration_config,
    update_integration_status,
)
from services.oa_integration import sync_approval_tasks
from utils.security import current_user, login_required, require_permission

bp = Blueprint("integrations", __name__)


@bp.route("/integrations/center")
@login_required
@require_permission("MANAGE_SYSTEM")
def integration_center():
    """集成配置中心页面"""
    return render_template("integrations/integration_center.html")


@bp.route("/api/integrations/list", methods=["GET"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_list():
    """获取集成列表"""
    try:
        enterprise_id = request.args.get("enterprise_id", type=int)
        integrations = list_integrations(enterprise_id=enterprise_id)
        return jsonify({"ok": True, "integrations": integrations})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/integrations/get", methods=["GET"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_get():
    """获取集成配置"""
    try:
        integration_id = request.args.get("integration_id", type=int)
        enterprise_id = request.args.get("enterprise_id", type=int)
        integration_type = request.args.get("integration_type")

        integration = get_integration(
            integration_id=integration_id,
            enterprise_id=enterprise_id,
            integration_type=integration_type,
        )
        if not integration:
            return jsonify({"ok": False, "msg": "集成配置不存在"}), 404

        return jsonify({"ok": True, "integration": integration})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/integrations/create", methods=["POST"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_create():
    """创建集成配置"""
    try:
        data = request.get_json() or {}
        enterprise_id = data.get("enterprise_id", type=int)
        integration_type = data.get("integration_type", "").strip()
        config = data.get("config", {})
        status = data.get("status", "active")

        if not enterprise_id or not integration_type:
            return jsonify({"ok": False, "msg": "企业ID和集成类型不能为空"}), 400

        integration = create_integration(enterprise_id, integration_type, config, status)
        return jsonify({"ok": True, "integration": integration})
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/integrations/config", methods=["POST"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_config():
    """更新集成配置"""
    try:
        data = request.get_json() or {}
        integration_id = data.get("integration_id", type=int)
        config = data.get("config", {})

        if not integration_id:
            return jsonify({"ok": False, "msg": "集成ID不能为空"}), 400

        update_integration_config(integration_id, config)
        return jsonify({"ok": True, "msg": "配置已更新"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/integrations/status", methods=["POST"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_status():
    """更新集成状态"""
    try:
        data = request.get_json() or {}
        integration_id = data.get("integration_id", type=int)
        status = data.get("status", "active")

        if not integration_id:
            return jsonify({"ok": False, "msg": "集成ID不能为空"}), 400

        update_integration_status(integration_id, status)
        return jsonify({"ok": True, "msg": "状态已更新"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/integrations/sync", methods=["POST"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_sync():
    """手动触发同步"""
    try:
        data = request.get_json() or {}
        enterprise_id = data.get("enterprise_id", type=int)
        integration_type = data.get("integration_type", "").strip()

        if not enterprise_id or not integration_type:
            return jsonify({"ok": False, "msg": "企业ID和集成类型不能为空"}), 400

        # 根据集成类型调用相应的同步函数
        if integration_type == "finance":
            result = sync_erp_vouchers(enterprise_id)
        elif integration_type == "hr":
            # 可以选择同步组织架构或员工
            sync_type = data.get("sync_type", "org")
            if sync_type == "org":
                result = sync_organization_structure(enterprise_id)
            else:
                result = sync_employees(enterprise_id)
        elif integration_type == "oa":
            result = sync_approval_tasks(enterprise_id)
        elif integration_type == "bank":
            start_date = data.get("start_date")
            end_date = data.get("end_date")
            result = pull_bank_transactions(enterprise_id, start_date, end_date)
        else:
            return jsonify({"ok": False, "msg": f"不支持的集成类型: {integration_type}"}), 400

        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/api/integrations/sync-logs", methods=["GET"])
@login_required
@require_permission("MANAGE_SYSTEM")
def api_integration_sync_logs():
    """获取同步日志"""
    try:
        integration_id = request.args.get("integration_id", type=int)
        limit = request.args.get("limit", type=int, default=100)

        logs = get_sync_logs(integration_id=integration_id, limit=limit)
        return jsonify({"ok": True, "logs": logs})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
