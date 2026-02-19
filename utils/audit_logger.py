# -*- coding: utf-8 -*-
"""统一审计日志写入函数"""

import json
from datetime import datetime
from typing import Any

from flask import g, request, session
from core.extensions import db
from models.audit_log import AuditLog


def _safe_text(value: Any, fallback: str = "") -> str:
    """安全转换为文本"""
    text = str(value or "").strip()
    return text if text else fallback


def _get_client_ip() -> str:
    """获取客户端 IP"""
    try:
        forwarded = _safe_text(request.headers.get("X-Forwarded-For"))
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
        real_ip = _safe_text(request.headers.get("X-Real-IP"))
        if real_ip:
            return real_ip
        return _safe_text(request.remote_addr, "-")
    except Exception:
        return "-"


def _sanitize_snapshot(data: dict[str, Any] | None) -> dict[str, Any]:
    """清理快照数据，移除敏感字段"""
    if not data:
        return {}
    
    sanitized = dict(data)
    # 移除密码、token 等敏感字段
    sensitive_keys = {
        "password", "password_hash", "token", "secret", "api_key",
        "access_token", "refresh_token", "csrf_token", "session_id"
    }
    
    for key in list(sanitized.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            sanitized.pop(key, None)
    
    return sanitized


def write_audit_log(
    *,
    action: str,
    actor_user_id: int | None = None,
    actor_name: str = "",
    target_type: str = "",
    target_id: str | int = "",
    snapshot_before: dict[str, Any] | None = None,
    snapshot_after: dict[str, Any] | None = None,
    trace_id: str = "",
    change_reason_code: str = "",
    detail: str = "",
) -> int | None:
    """
    统一审计日志写入函数
    
    Args:
        action: 操作类型（LOGIN_SUCCESS, UPLOAD, VERIFY, RISK_CREATE, APPROVE, REJECT, EXPORT 等）
        actor_user_id: 操作人用户ID
        actor_name: 操作人名称
        target_type: 目标类型（auth, invoice, approval, risk_event 等）
        target_id: 目标ID
        snapshot_before: 操作前快照（自动清理敏感字段）
        snapshot_after: 操作后快照（自动清理敏感字段）
        trace_id: 追踪ID
        change_reason_code: 变更原因代码
        detail: 详细信息
    
    Returns:
        审计日志ID，失败返回 None
    """
    try:
        # 获取请求上下文信息（安全处理，避免上下文缺失）
        try:
            client_ip = _get_client_ip()
        except Exception:
            client_ip = "-"
        
        try:
            user_agent = _safe_text(request.headers.get("User-Agent", ""))[:512]
        except Exception:
            user_agent = ""
        
        try:
            request_id = getattr(g, "request_id", "")
        except Exception:
            request_id = ""
        
        try:
            session_id = session.get("_id", "") if session else ""
        except Exception:
            session_id = ""
        
        # 清理快照数据
        before_json = json.dumps(_sanitize_snapshot(snapshot_before), ensure_ascii=False) if snapshot_before else ""
        after_json = json.dumps(_sanitize_snapshot(snapshot_after), ensure_ascii=False) if snapshot_after else ""
        
        # 创建审计日志记录
        log = AuditLog(
            created_at=datetime.utcnow(),
            actor_user_id=actor_user_id,
            actor_name=_safe_text(actor_name),
            action=_safe_text(action).upper(),
            target_type=_safe_text(target_type),
            target_id=str(target_id) if target_id else "",
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=_safe_text(request_id),
            session_id=_safe_text(session_id),
            snapshot_before=before_json,
            snapshot_after=after_json,
            trace_id=_safe_text(trace_id),
            change_reason_code=_safe_text(change_reason_code),
            detail=_safe_text(detail),
        )
        
        db.session.add(log)
        db.session.commit()
        
        return log.id
    except Exception as e:
        # 审计日志写入失败不应阻塞业务流程
        try:
            db.session.rollback()
        except Exception:
            pass
        
        # 记录到应用日志
        try:
            from flask import current_app
            current_app.logger.error(f"Failed to write audit log: {e}", exc_info=True)
        except Exception:
            pass
        
        return None

