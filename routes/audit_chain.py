# -*- coding: utf-8 -*-
"""
智能审计链路由
GET /audit_chain/<object_type>/<object_id> 页面
GET /api/audit_chain/<object_type>/<object_id> JSON
POST /api/audit_chain/event 追加事件
POST /api/audit_chain/evidence 关联证据
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from services.audit_chain_service import append_event, get_chain_by_object, link_evidence
from utils.error_codes import format_error_response, get_http_status
from utils.security import current_user, has_permission, login_required

bp = Blueprint("audit_chain", __name__)

VALID_OBJECT_TYPES = {"invoice", "risk_event", "risk_case", "approval"}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.is_json


@bp.get("/audit_chain")
@login_required
def audit_chain_entry():
    """智能审计链入口页（对象选择）。"""
    if not has_permission("VIEW_AI_LEDGER", current_user() or {}):
        return (
            render_template(
                "forbidden.html",
                module_name="智能审计链",
                required_permissions=["VIEW_AI_LEDGER"],
            ),
            403,
        )
    return render_template(
        "audit_chain/chain_page.html",
        object_type="",
        object_id="",
        chain_data=None,
    )


@bp.get("/audit_chain/<object_type>/<object_id>")
@login_required
def audit_chain_page(object_type: str, object_id: str):
    """智能审计链详情页。"""
    if not has_permission("VIEW_AI_LEDGER", current_user() or {}):
        if _wants_json():
            resp = format_error_response(
                "forbidden",
                message_cn="无权限访问智能审计链",
                technical_details={"required_permission": "VIEW_AI_LEDGER"},
            )
            return jsonify(resp), 403
        return (
            render_template(
                "forbidden.html",
                module_name="智能审计链",
                required_permissions=["VIEW_AI_LEDGER"],
            ),
            403,
        )

    obj_type = _safe_text(object_type).lower()
    if obj_type not in VALID_OBJECT_TYPES:
        if _wants_json():
            resp = format_error_response(
                "validation_error",
                message_cn="不支持的对象类型",
                technical_details={"object_type": object_type, "valid_types": list(VALID_OBJECT_TYPES)},
            )
            return jsonify(resp), 400
        return render_template(
            "audit_chain/chain_page.html",
            object_type=obj_type,
            object_id=object_id,
            chain_data=None,
            error="不支持的对象类型",
        ), 400

    try:
        chain_data, error_cn = get_chain_by_object(obj_type, object_id, user=current_user())
        if error_cn:
            if _wants_json():
                resp = format_error_response(
                    "data_scope_forbidden",
                    message_cn=error_cn,
                    technical_details={
                        "object_type": obj_type,
                        "object_id": object_id,
                    },
                )
                return jsonify(resp), get_http_status("data_scope_forbidden")
            return (
                render_template(
                    "audit_chain/chain_page.html",
                    object_type=obj_type,
                    object_id=object_id,
                    chain_data=None,
                    error=error_cn,
                ),
                403,
            )

        return render_template(
            "audit_chain/chain_page.html",
            object_type=obj_type,
            object_id=object_id,
            chain_data=chain_data,
            error=None,
        )
    except Exception as exc:
        from flask import current_app
        current_app.logger.exception("audit_chain_page error: object_type=%s object_id=%s", obj_type, object_id)
        if _wants_json():
            resp = format_error_response(
                "internal_error",
                message_cn="获取审计链失败",
                technical_details={"error": str(exc), "object_type": obj_type, "object_id": object_id},
            )
            return jsonify(resp), 500
        return (
            render_template(
                "audit_chain/chain_page.html",
                object_type=obj_type,
                object_id=object_id,
                chain_data=None,
                error=f"获取审计链失败：{str(exc)}",
            ),
            500,
        )


@bp.get("/api/audit_chain/<object_type>/<object_id>")
@login_required
def audit_chain_api(object_type: str, object_id: str):
    """智能审计链 JSON 接口。"""
    if not has_permission("VIEW_AI_LEDGER", current_user() or {}):
        resp = format_error_response(
            "forbidden",
            message_cn="无权限访问智能审计链",
            technical_details={"required_permission": "VIEW_AI_LEDGER"},
        )
        return jsonify(resp), 403

    obj_type = _safe_text(object_type).lower()
    if obj_type not in VALID_OBJECT_TYPES:
        resp = format_error_response(
            "validation_error",
            message_cn="不支持的对象类型",
            technical_details={"object_type": object_type, "valid_types": list(VALID_OBJECT_TYPES)},
        )
        return jsonify(resp), 400

    chain_data, error_cn = get_chain_by_object(obj_type, object_id, user=current_user())
    if error_cn:
        resp = format_error_response(
            "data_scope_forbidden",
            message_cn=error_cn,
            technical_details={"object_type": obj_type, "object_id": object_id},
        )
        return jsonify(resp), get_http_status("data_scope_forbidden")

    return jsonify({"ok": True, "chain": chain_data})


@bp.post("/api/audit_chain/event")
@login_required
def audit_chain_append_event():
    """追加审计链事件。"""
    if not has_permission("VIEW_AI_LEDGER", current_user() or {}):
        resp = format_error_response(
            "forbidden",
            message_cn="无权限操作智能审计链",
            technical_details={"required_permission": "VIEW_AI_LEDGER"},
        )
        return jsonify(resp), 403

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        resp = format_error_response("validation_error", message_cn="请求体必须为 JSON 对象")
        return jsonify(resp), 400

    trace_id = _safe_text(payload.get("trace_id"))
    event_type = _safe_text(payload.get("event_type")).upper()
    change_reason_code = _safe_text(payload.get("change_reason_code") or "SYSTEM_AUTO").upper()
    evt_payload = payload.get("payload")
    if isinstance(evt_payload, dict):
        pass
    elif evt_payload is not None:
        evt_payload = {"value": evt_payload}
    else:
        evt_payload = {}

    if not trace_id or not event_type:
        resp = format_error_response(
            "missing_required_field",
            message_cn="trace_id 和 event_type 为必填",
            technical_details={"payload": payload},
        )
        return jsonify(resp), 400

    try:
        event_id = append_event(
            trace_id=trace_id,
            event_type=event_type,
            payload=evt_payload,
            change_reason_code=change_reason_code,
            user=current_user(),
        )
        return jsonify({"ok": True, "event_id": event_id})
    except ValueError as e:
        resp = format_error_response(
            "validation_error",
            message_cn=str(e),
            technical_details={"trace_id": trace_id, "event_type": event_type},
        )
        return jsonify(resp), 400


@bp.post("/api/audit_chain/evidence")
@login_required
def audit_chain_link_evidence():
    """关联审计链证据。"""
    if not has_permission("VIEW_AI_LEDGER", current_user() or {}):
        resp = format_error_response(
            "forbidden",
            message_cn="无权限操作智能审计链",
            technical_details={"required_permission": "VIEW_AI_LEDGER"},
        )
        return jsonify(resp), 403

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        resp = format_error_response("validation_error", message_cn="请求体必须为 JSON 对象")
        return jsonify(resp), 400

    trace_id = _safe_text(payload.get("trace_id"))
    file_path = _safe_text(payload.get("file_path"))
    object_type = _safe_text(payload.get("object_type") or "invoice").lower()
    object_id = _safe_text(payload.get("object_id"))
    evidence_type = _safe_text(payload.get("evidence_type") or "file")
    change_reason_code = _safe_text(payload.get("change_reason_code") or "SYSTEM_AUTO").upper()

    if not trace_id or not file_path:
        resp = format_error_response(
            "missing_required_field",
            message_cn="trace_id 和 file_path 为必填",
            technical_details={"payload": payload},
        )
        return jsonify(resp), 400

    try:
        evidence_id = link_evidence(
            trace_id=trace_id,
            file_path=file_path,
            object_type=object_type,
            object_id=object_id,
            evidence_type=evidence_type,
            change_reason_code=change_reason_code,
            user=current_user(),
        )
        return jsonify({"ok": True, "evidence_id": evidence_id})
    except ValueError as e:
        resp = format_error_response(
            "validation_error",
            message_cn=str(e),
            technical_details={"trace_id": trace_id, "file_path": file_path},
        )
        return jsonify(resp), 400
