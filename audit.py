from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from flask import has_request_context, request

from utils.db import get_conn
from utils.security import current_user
from utils.status_i18n import to_cn_reason_code

MISSING_REASON_MESSAGE = "必须填写原因码（审计要求）"


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _to_snapshot_obj(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        try:
            return dict(value)
        except Exception:
            pass
    return {"value": value}


def _json_text(value: Any) -> str:
    try:
        return json.dumps(_to_snapshot_obj(value), ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return "{}"


def _calculate_diff(before_obj: Any, after_obj: Any) -> dict[str, Any]:
    """
    计算变更diff（企业级审计要求）
    
    Returns:
        包含变更字段、变更前值、变更后值的字典
    """
    before_dict = _to_snapshot_obj(before_obj)
    after_dict = _to_snapshot_obj(after_obj)
    
    diff: dict[str, Any] = {
        "changed_fields": [],
        "added_fields": [],
        "removed_fields": [],
        "details": {},
    }
    
    # 收集所有字段
    all_keys = set(before_dict.keys()) | set(after_dict.keys())
    
    for key in all_keys:
        before_val = before_dict.get(key)
        after_val = after_dict.get(key)
        
        # 字段被删除
        if key not in after_dict:
            diff["removed_fields"].append(key)
            diff["details"][key] = {"before": before_val, "after": None}
            continue
        
        # 字段被添加
        if key not in before_dict:
            diff["added_fields"].append(key)
            diff["details"][key] = {"before": None, "after": after_val}
            continue
        
        # 字段值变更
        if before_val != after_val:
            diff["changed_fields"].append(key)
            diff["details"][key] = {"before": before_val, "after": after_val}
    
    return diff


def _client_ip() -> str:
    if not has_request_context():
        return "0.0.0.0"
    forwarded = _safe_text(request.headers.get("X-Forwarded-For"))
    if forwarded:
        first = _safe_text(forwarded.split(",")[0])
        if first:
            return first
    real_ip = _safe_text(request.headers.get("X-Real-IP"))
    if real_ip:
        return real_ip
    remote_addr = _safe_text(request.remote_addr)
    return remote_addr or "0.0.0.0"


def _actor_payload() -> tuple[str, str]:
    user = current_user() or {}
    actor_user_id = _safe_text(user.get("id"))

    employee_name = _safe_text(user.get("employee_name"))
    username = _safe_text(user.get("username"))
    employee_no = _safe_text(user.get("employee_no"))

    display = employee_name or username or employee_no or "system"
    extras: list[str] = []
    if username and username != display:
        extras.append(f"username={username}")
    if employee_no and employee_no != display:
        extras.append(f"employee_no={employee_no}")
    if extras:
        return actor_user_id, f"{display} ({', '.join(extras)})"
    return actor_user_id, display


def write_audit_log(
    action: str,
    target_type: str,
    target_id: Any,
    before_obj: Any,
    after_obj: Any,
    change_reason_code: str,
    trace_id: str | None = None,
    *,
    change_reason_text: str | None = None,
) -> int:
    """
    写入审计日志（企业级增强版）
    
    Args:
        action: 操作动作（如 "UPDATE", "CREATE", "DELETE"）
        target_type: 目标类型（如 "invoice", "role", "user"）
        target_id: 目标ID
        before_obj: 变更前对象
        after_obj: 变更后对象
        change_reason_code: 变更原因码（必填）
        trace_id: 追踪ID（可选）
        change_reason_text: 变更原因文本（可选，用于补充说明）
    
    Returns:
        审计日志ID
    """
    normalized_action = _safe_text(action).upper()
    normalized_target_type = _safe_text(target_type)
    normalized_target_id = _safe_text(target_id)
    normalized_reason = _safe_text(change_reason_code).upper()
    normalized_trace_id = _safe_text(trace_id)
    reason_text = _safe_text(change_reason_text)

    if not normalized_reason:
        raise ValueError(MISSING_REASON_MESSAGE)
    if not normalized_action:
        raise ValueError("action is required")
    if not normalized_target_type:
        raise ValueError("target_type is required")
    if not normalized_target_id:
        raise ValueError("target_id is required")

    actor_user_id, actor_name = _actor_payload()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 计算diff（企业级审计要求）
    diff = _calculate_diff(before_obj, after_obj)
    
    # 构建增强的snapshot_after，包含diff信息
    enhanced_after = _to_snapshot_obj(after_obj)
    enhanced_after["_audit_meta"] = {
        "diff": diff,
        "change_reason_code": normalized_reason,
        "change_reason_code_cn": to_cn_reason_code(normalized_reason),
        "change_reason_text": reason_text,
        "changed_fields_count": len(diff["changed_fields"]),
        "added_fields_count": len(diff["added_fields"]),
        "removed_fields_count": len(diff["removed_fields"]),
    }

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_log (
                created_at,
                actor_user_id,
                actor_name,
                action,
                target_type,
                target_id,
                client_ip,
                change_reason_code,
                snapshot_before,
                snapshot_after,
                trace_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                actor_user_id,
                actor_name,
                normalized_action,
                normalized_target_type,
                normalized_target_id,
                _client_ip(),
                normalized_reason,
                _json_text(before_obj),
                _json_text(enhanced_after),
                normalized_trace_id,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
