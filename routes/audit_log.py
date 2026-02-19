# -*- coding: utf-8 -*-
"""审计日志查询蓝图"""

from datetime import datetime, timedelta
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request
from sqlalchemy import and_, or_

from core.extensions import db
from models.audit_log import AuditLog
from utils.security import current_user, has_permission, login_required

bp = Blueprint("audit_log", __name__)


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _parse_date(date_str: str) -> datetime | None:
    """解析日期字符串为当天起始时间"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


def _get_date_range(start_str: str, end_str: str) -> tuple[datetime | None, datetime | None]:
    """获取日期范围（包含结束日期当天）"""
    start_date = _parse_date(start_str)
    end_date = _parse_date(end_str)
    
    if end_date:
        # 结束日期设为当天 23:59:59
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    return start_date, end_date


def _action_to_cn(action: str) -> str:
    """操作类型中文映射"""
    mapping = {
        "LOGIN_SUCCESS": "登录成功",
        "LOGIN_FAIL": "登录失败",
        "LOGIN_LOCK": "账号锁定",
        "PASSWORD_CHANGE": "修改密码",
        "UPLOAD": "上传凭证",
        "VERIFY": "验真完成",
        "APPROVAL_APPROVE": "审批通过",
        "APPROVAL_REJECT": "审批驳回",
        "APPROVAL_RETURN": "审批退回",
        "APPROVAL_ASSIGN": "审批分配",
        "RISK_CREATE": "创建风险事件",
        "RISK_ASSESS": "风险评估",
        "RISK_CLOSE": "关闭风险事件",
        "EXPORT": "导出数据",
    }
    return mapping.get(action.upper(), action)


@bp.get("/audit-log")
@login_required
def audit_log_page():
    """审计日志查询页面"""
    user = current_user() or {}
    
    if not has_permission("VIEW_AUDIT_LOG", user):
        return render_template(
            "forbidden.html",
            module_name="审计日志查询",
            required_permissions=["VIEW_AUDIT_LOG"],
        ), 403
    
    return render_template("audit_log.html")


@bp.get("/api/audit-log/query")
@login_required
def audit_log_query_api():
    """审计日志查询 API"""
    user = current_user() or {}
    
    if not has_permission("VIEW_AUDIT_LOG", user):
        return jsonify({"ok": False, "msg": "无权访问"}), 403
    
    # 解析筛选参数
    actor_user_id = _safe_int(request.args.get("actor_user_id"))
    action = _safe_text(request.args.get("action")).upper()
    target_type = _safe_text(request.args.get("target_type"))
    request_id = _safe_text(request.args.get("request_id"))
    start_date_str = _safe_text(request.args.get("start_date"))
    end_date_str = _safe_text(request.args.get("end_date"))
    
    # 分页参数
    page = max(1, _safe_int(request.args.get("page"), 1))
    per_page = max(1, min(200, _safe_int(request.args.get("per_page"), 50)))
    
    # 构建查询
    query = db.session.query(AuditLog)
    
    # 权限过滤：普通员工只能看自己的日志
    if not has_permission("MANAGE_SYSTEM", user):
        user_id = _safe_int(user.get("id"))
        if user_id > 0:
            query = query.filter(AuditLog.actor_user_id == user_id)
        else:
            # 无有效用户ID，返回空结果
            return jsonify({"ok": True, "data": [], "total": 0, "page": page, "per_page": per_page})
    
    # 筛选条件
    if actor_user_id > 0:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    
    if action:
        query = query.filter(AuditLog.action == action)
    
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    
    if request_id:
        query = query.filter(AuditLog.request_id == request_id)
    
    # 日期范围（默认最近7天）
    start_date, end_date = _get_date_range(start_date_str, end_date_str)
    if not start_date and not end_date:
        # 默认最近7天
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
    
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
    
    # 排序
    query = query.order_by(AuditLog.created_at.desc())
    
    # 分页
    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # 转换为字典
    data = []
    for log in logs:
        data.append({
            "id": log.id,
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
            "actor_user_id": log.actor_user_id,
            "actor_name": log.actor_name,
            "action": log.action,
            "action_cn": _action_to_cn(log.action),
            "target_type": log.target_type,
            "target_id": log.target_id,
            "client_ip": log.client_ip,
            "request_id": log.request_id[:16] + "..." if len(log.request_id) > 16 else log.request_id,
            "request_id_full": log.request_id,
        })
    
    return jsonify({
        "ok": True,
        "data": data,
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@bp.get("/api/audit-log/<int:log_id>")
@login_required
def audit_log_detail_api(log_id: int):
    """审计日志详情 API"""
    user = current_user() or {}
    
    if not has_permission("VIEW_AUDIT_LOG", user):
        return jsonify({"ok": False, "msg": "无权访问"}), 403
    
    log = db.session.query(AuditLog).filter(AuditLog.id == log_id).first()
    
    if not log:
        return jsonify({"ok": False, "msg": "日志不存在"}), 404
    
    # 权限检查：普通员工只能看自己的日志
    if not has_permission("MANAGE_SYSTEM", user):
        user_id = _safe_int(user.get("id"))
        if log.actor_user_id != user_id:
            return jsonify({"ok": False, "msg": "无权访问"}), 403
    
    data = {
        "id": log.id,
        "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
        "actor_user_id": log.actor_user_id,
        "actor_name": log.actor_name,
        "action": log.action,
        "action_cn": _action_to_cn(log.action),
        "target_type": log.target_type,
        "target_id": log.target_id,
        "client_ip": log.client_ip,
        "user_agent": log.user_agent,
        "request_id": log.request_id,
        "session_id": log.session_id,
        "snapshot_before": log.snapshot_before,
        "snapshot_after": log.snapshot_after,
        "trace_id": log.trace_id,
        "change_reason_code": log.change_reason_code,
        "detail": log.detail,
    }
    
    return jsonify({"ok": True, "data": data})


@bp.get("/audit-log/health")
def health():
    return jsonify({"ok": True, "module": "audit_log"})


