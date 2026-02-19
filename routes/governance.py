from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from audit import MISSING_REASON_MESSAGE, write_audit_log
from utils.error_codes import format_error_response, get_http_status
from services import governance_rule_service
from utils.db import (
    delete_governance_rule,
    get_governance_rule,
    get_rule_audit_history,
    insert_governance_rule,
    is_governance_rule_referenced,
    list_governance_rules,
    update_governance_rule,
    update_governance_rule_from_snapshot,
)
from utils.governance_i18n import rule_display_name, rule_threshold_unit
from utils.security import current_user, login_required, require_permission

bp = Blueprint("governance", __name__)


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _parse_threshold_json(
    value: Any,
    *,
    provided: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    if not provided:
        return None, None
    if value is None:
        return {}, None
    if isinstance(value, dict):
        return dict(value), None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}, None
        try:
            loaded = json.loads(text)
        except Exception:
            return None, "invalid_threshold_json"
        if loaded is None:
            return {}, None
        if isinstance(loaded, dict):
            return loaded, None
    return None, "invalid_threshold_json"


def _parse_payload() -> tuple[dict[str, Any], tuple[Any, int] | None]:
    payload = request.get_json(silent=True)
    if request.data and payload is None:
        return {}, (jsonify({"ok": False, "message": "request body must be JSON"}), 400)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return {}, (jsonify({"ok": False, "message": "request body must be a JSON object"}), 400)
    return payload, None


def _operator_name() -> str:
    me = current_user() or {}
    return (
        _safe_text(me.get("employee_name"))
        or _safe_text(me.get("username"))
        or _safe_text(me.get("employee_no"))
        or "system"
    )


def _rule_snapshot(rule: dict[str, Any], rule_id: int) -> dict[str, Any]:
    return {
        "id": _safe_int(rule.get("id"), rule_id),
        "rule_key": _safe_text(rule.get("rule_key")).upper(),
        "enabled": bool(rule.get("enabled")),
        "threshold": rule.get("threshold"),
        "severity": _safe_text(rule.get("severity")).upper(),
        "version": _safe_int(rule.get("version"), 0),
        "updated_by": _safe_text(rule.get("updated_by")),
        "updated_at": _safe_text(rule.get("updated_at")),
        "status": _safe_text(rule.get("status")).lower(),
        "rule_type": _safe_text(rule.get("rule_type")).lower(),
    }


def _audit_rule_change(
    *,
    rule_id: int,
    before: dict[str, Any],
    after: dict[str, Any],
    change_reason_code: str,
    change_reason_text: str | None = None,
    trace_id: str = "",
    action: str = "RULE_UPDATE",
) -> None:
    before_snapshot = _rule_snapshot(before, rule_id)
    after_snapshot = _rule_snapshot(after, rule_id)
    write_audit_log(
        action=action,
        target_type="rule",
        target_id=str(_safe_int(rule_id, 0)),
        before_obj=before_snapshot,
        after_obj=after_snapshot,
        change_reason_code=change_reason_code,
        change_reason_text=change_reason_text,
        trace_id=trace_id,
    )


def _enrich_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rules:
        row = dict(r)
        row["rule_display_name"] = rule_display_name(r.get("rule_key"))
        row["rule_threshold_unit"] = rule_threshold_unit(r.get("rule_key"))
        out.append(row)
    return out


@bp.get("/governance/rules")
@login_required
@require_permission("MANAGE_RULES")
def governance_rules_page():
    from utils.governance_i18n import RULE_CHANGE_REASON_OPTIONS
    rules = _enrich_rules(list_governance_rules())
    return render_template(
        "governance_rules.html",
        rules=rules,
        change_reason_options=RULE_CHANGE_REASON_OPTIONS,
    )


@bp.get("/api/governance/rules")
@login_required
@require_permission("MANAGE_RULES")
def governance_rules_api():
    return jsonify({"ok": True, "rules": _enrich_rules(list_governance_rules())})


@bp.post("/api/governance/rules")
@login_required
@require_permission("MANAGE_RULES")
def create_governance_rule_api():
    """新增自定义规则（仅支持自定义，保存为草稿）。"""
    payload, err = _parse_payload()
    if err is not None:
        return err
    rule_key = _safe_text(payload.get("rule_key")).upper()
    rule_name = _safe_text(payload.get("rule_name"))
    if not rule_key or not rule_name:
        return jsonify({"ok": False, "message": "rule_key 与 rule_name 必填"}), 400
    threshold_raw = payload.get("threshold")
    threshold = _safe_float(threshold_raw) if threshold_raw is not None else 0.0
    if threshold is None:
        threshold = 0.0
    ok, msg = governance_rule_service.validate_rule_threshold(rule_key, threshold_raw if threshold_raw is not None else threshold)
    if not ok:
        return jsonify({"ok": False, "message": msg}), 422
    severity_raw = _safe_text(payload.get("severity")).upper()
    severity = severity_raw if severity_raw in ("LOW", "MEDIUM", "HIGH") else "MEDIUM"
    threshold_json = payload.get("threshold_json")
    created = insert_governance_rule(
        rule_key=rule_key,
        rule_name=rule_name,
        threshold=float(threshold),
        threshold_json=threshold_json,
        severity=severity,
        operator=_operator_name(),
    )
    if not created:
        return jsonify({"ok": False, "message": "rule_key 已存在或创建失败"}), 400
    governance_rule_service.clear_cache()
    return jsonify({"ok": True, "rule": _enrich_rules([created])[0]})


@bp.post("/api/governance/rules/<int:rule_id>")
@login_required
@require_permission("MANAGE_RULES")
def update_governance_rule_api(rule_id: int):
    payload, err = _parse_payload()
    if err is not None:
        return err

    save_as_draft = payload.get("save_as_draft") is True
    change_reason_code = _safe_text(payload.get("change_reason_code")).upper()
    change_reason_text = _safe_text(payload.get("change_reason_note")) or None
    trace_id = _safe_text(payload.get("trace_id"))

    before = get_governance_rule(rule_id)
    if before is None:
        return jsonify({"ok": False, "message": "rule not found"}), 404

    rule_type = _safe_text(before.get("rule_type")).lower()
    status = _safe_text(before.get("status")).lower()
    if not save_as_draft and not change_reason_code:
        return jsonify({"ok": False, "message": MISSING_REASON_MESSAGE}), 400
    if save_as_draft and (rule_type != "custom" or status != "draft"):
        return jsonify({"ok": False, "message": "仅自定义草稿规则可保存为草稿"}), 400

    rule_key = _safe_text(before.get("rule_key")).upper()

    enabled_raw = payload.get("enabled")
    threshold_raw = payload.get("threshold")
    threshold_json_provided = "threshold_json" in payload
    threshold_json_raw = payload.get("threshold_json")
    severity_raw = payload.get("severity")

    enabled = _safe_bool(enabled_raw)
    if enabled_raw is not None and enabled is None:
        return jsonify({"ok": False, "message": "enabled must be boolean"}), 400

    threshold: float | None = None
    if threshold_raw is not None:
        ok, msg = governance_rule_service.validate_rule_threshold(rule_key, threshold_raw)
        if not ok:
            resp = format_error_response(
                "rule_validation_error",
                message_cn=msg,
                technical_details={
                    "rule_key": rule_key,
                    "field": "threshold",
                    "validation_type": "range_or_format",
                    "actual": str(threshold_raw),
                },
            )
            return jsonify(resp), get_http_status("rule_validation_error", 422)
        threshold = _safe_float(threshold_raw)

    threshold_json, threshold_json_error = _parse_threshold_json(
        threshold_json_raw,
        provided=threshold_json_provided,
    )
    if threshold_json_error:
        return jsonify({"ok": False, "msg": "invalid_threshold_json"}), 400

    severity = _safe_text(severity_raw).upper() if severity_raw is not None else None
    if severity is not None and severity not in {"LOW", "MEDIUM", "HIGH"}:
        severity = None

    if enabled is None and threshold is None and not threshold_json_provided and severity is None:
        return jsonify({"ok": False, "message": "enabled or threshold or threshold_json or severity is required"}), 400

    updated = update_governance_rule(
        rule_id,
        enabled=enabled,
        threshold=threshold,
        threshold_json=threshold_json,
        severity=severity,
        operator=_operator_name(),
    )
    if updated is None:
        return jsonify({"ok": False, "message": "rule not found"}), 404

    governance_rule_service.clear_cache()
    if not save_as_draft:
        try:
            _audit_rule_change(
                rule_id=rule_id,
                before=before,
                after=updated,
                change_reason_code=change_reason_code or "MANUAL_ADJUST",
                change_reason_text=change_reason_text,
                trace_id=trace_id,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        except Exception:
            return jsonify({"ok": False, "message": "audit log write failed"}), 500
    return jsonify({"ok": True, "rule": _enrich_rules([updated])[0]})


@bp.post("/api/governance/rules/<int:rule_id>/draft")
@login_required
@require_permission("MANAGE_RULES")
def save_governance_rule_draft_api(rule_id: int):
    """保存为草稿（仅自定义规则）。无需填写变更原因。"""
    payload, err = _parse_payload()
    if err is not None:
        return err
    before = get_governance_rule(rule_id)
    if not before or _safe_text(before.get("rule_type")).lower() != "custom":
        return jsonify({"ok": False, "message": "仅支持自定义规则保存草稿"}), 400
    if _safe_text(before.get("status")).lower() != "draft":
        return jsonify({"ok": False, "message": "仅草稿状态可执行保存草稿"}), 400
    rule_key = _safe_text(before.get("rule_key")).upper()
    enabled = _safe_bool(payload.get("enabled"))
    if payload.get("enabled") is not None and enabled is None:
        return jsonify({"ok": False, "message": "enabled must be boolean"}), 400
    threshold_raw = payload.get("threshold")
    threshold = _safe_float(threshold_raw) if threshold_raw is not None else None
    if threshold_raw is not None:
        ok, msg = governance_rule_service.validate_rule_threshold(rule_key, threshold_raw)
        if not ok:
            return jsonify({"ok": False, "message": msg}), 422
    threshold_json, _ = _parse_threshold_json(payload.get("threshold_json"), provided=("threshold_json" in payload))
    severity = _safe_text(payload.get("severity")).upper()
    severity = severity if severity in ("LOW", "MEDIUM", "HIGH") else None
    updated = update_governance_rule(
        rule_id,
        enabled=enabled,
        threshold=threshold,
        threshold_json=threshold_json,
        severity=severity,
        operator=_operator_name(),
    )
    if not updated:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    governance_rule_service.clear_cache()
    return jsonify({"ok": True, "rule": _enrich_rules([updated])[0]})


@bp.post("/api/governance/rules/<int:rule_id>/publish")
@login_required
@require_permission("MANAGE_RULES")
def publish_governance_rule_api(rule_id: int):
    """发布规则（必填原因 + 审计 diff）。"""
    payload, err = _parse_payload()
    if err is not None:
        return err
    change_reason_code = _safe_text(payload.get("change_reason_code")).upper()
    change_reason_text = _safe_text(payload.get("change_reason_note")) or None
    if not change_reason_code:
        return jsonify({"ok": False, "message": "发布必须填写变更原因（审计要求）"}), 400
    before = get_governance_rule(rule_id)
    if not before:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    from datetime import datetime as _dt
    now = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = update_governance_rule(
        rule_id,
        status="published",
        publish_reason=change_reason_text or change_reason_code,
        published_at=now,
        operator=_operator_name(),
    )
    if not updated:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    governance_rule_service.clear_cache()
    try:
        _audit_rule_change(
            rule_id=rule_id,
            before=before,
            after=updated,
            change_reason_code=change_reason_code,
            change_reason_text=change_reason_text,
            action="RULE_PUBLISH",
        )
    except Exception:
        return jsonify({"ok": False, "message": "audit log write failed"}), 500
    return jsonify({"ok": True, "rule": _enrich_rules([updated])[0]})


@bp.post("/api/governance/rules/<int:rule_id>/toggle-enabled")
@login_required
@require_permission("MANAGE_RULES")
def toggle_governance_rule_enabled_api(rule_id: int):
    """下线/启用快捷切换（必填原因）。"""
    payload, err = _parse_payload()
    if err is not None:
        return err
    change_reason_code = _safe_text(payload.get("change_reason_code")).upper()
    change_reason_text = _safe_text(payload.get("change_reason_note")) or None
    if not change_reason_code:
        return jsonify({"ok": False, "message": MISSING_REASON_MESSAGE}), 400
    before = get_governance_rule(rule_id)
    if not before:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    new_enabled = not bool(before.get("enabled"))
    updated = update_governance_rule(
        rule_id,
        enabled=new_enabled,
        operator=_operator_name(),
    )
    if not updated:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    governance_rule_service.clear_cache()
    try:
        _audit_rule_change(
            rule_id=rule_id,
            before=before,
            after=updated,
            change_reason_code=change_reason_code,
            change_reason_text=change_reason_text,
            action="RULE_UPDATE",
        )
    except Exception:
        return jsonify({"ok": False, "message": "audit log write failed"}), 500
    return jsonify({"ok": True, "rule": _enrich_rules([updated])[0], "enabled": new_enabled})


@bp.get("/api/governance/rules/<int:rule_id>/history")
@login_required
@require_permission("MANAGE_RULES")
def governance_rule_history_api(rule_id: int):
    """规则审计历史（含回滚用快照）。"""
    if get_governance_rule(rule_id) is None:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    limit = request.args.get("limit", 50, type=int)
    history = get_rule_audit_history(rule_id, limit=min(limit, 200))
    return jsonify({"ok": True, "history": history})


@bp.post("/api/governance/rules/<int:rule_id>/rollback")
@login_required
@require_permission("MANAGE_RULES")
def rollback_governance_rule_api(rule_id: int):
    """回滚到该版本（根据 audit_log 的 snapshot_after）。"""
    payload, err = _parse_payload()
    if err is not None:
        return err
    audit_log_id = payload.get("audit_log_id")
    if audit_log_id is None:
        return jsonify({"ok": False, "message": "audit_log_id 必填"}), 400
    try:
        log_id = int(audit_log_id)
    except Exception:
        return jsonify({"ok": False, "message": "audit_log_id 无效"}), 400
    history = get_rule_audit_history(rule_id, limit=500)
    entry = next((h for h in history if int(h.get("id", 0)) == log_id), None)
    if not entry:
        return jsonify({"ok": False, "message": "未找到该历史记录"}), 404
    snapshot_after = entry.get("snapshot_after")
    if isinstance(snapshot_after, str):
        import json as _json
        try:
            snapshot_after = _json.loads(snapshot_after)
        except Exception:
            return jsonify({"ok": False, "message": "快照格式无效"}), 400
    if not isinstance(snapshot_after, dict):
        return jsonify({"ok": False, "message": "快照格式无效"}), 400
    before = get_governance_rule(rule_id)
    if not before:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    updated = update_governance_rule_from_snapshot(
        rule_id,
        snapshot_after,
        operator=_operator_name(),
        rollback_reason="ROLLBACK",
    )
    if not updated:
        return jsonify({"ok": False, "message": "回滚失败"}), 500
    governance_rule_service.clear_cache()
    change_reason = _safe_text(payload.get("change_reason_code")).upper() or "RESTORE_DEFAULT"
    try:
        _audit_rule_change(
            rule_id=rule_id,
            before=before,
            after=updated,
            change_reason_code=change_reason,
            change_reason_text="回滚到该版本",
            action="RULE_ROLLBACK",
        )
    except Exception:
        pass
    return jsonify({"ok": True, "rule": _enrich_rules([updated])[0]})


@bp.get("/api/governance/rules/<int:rule_id>/can-delete")
@login_required
@require_permission("MANAGE_RULES")
def can_delete_governance_rule_api(rule_id: int):
    """是否可删除：仅未发布且未被引用的自定义规则。"""
    rule = get_governance_rule(rule_id)
    if not rule:
        return jsonify({"ok": False, "message": "rule not found"}), 404
    if _safe_text(rule.get("rule_type")).lower() != "custom":
        return jsonify({"ok": True, "can_delete": False, "reason": "仅支持删除自定义规则"})
    if _safe_text(rule.get("status")).lower() != "draft":
        return jsonify({"ok": True, "can_delete": False, "reason": "仅未发布的规则可删除"})
    if is_governance_rule_referenced(rule_id):
        return jsonify({"ok": True, "can_delete": False, "reason": "该规则已被引用，无法删除"})
    return jsonify({"ok": True, "can_delete": True, "reason": ""})


@bp.delete("/api/governance/rules/<int:rule_id>")
@login_required
@require_permission("MANAGE_RULES")
def delete_governance_rule_api(rule_id: int):
    """删除规则（仅未发布且未被引用的自定义规则）。"""
    if not delete_governance_rule(rule_id):
        rule = get_governance_rule(rule_id)
        if not rule:
            return jsonify({"ok": False, "message": "rule not found"}), 404
        if _safe_text(rule.get("rule_type")).lower() != "custom":
            return jsonify({"ok": False, "message": "仅支持删除自定义规则"}), 403
        if _safe_text(rule.get("status")).lower() != "draft":
            return jsonify({"ok": False, "message": "仅未发布的规则可删除"}), 403
        if is_governance_rule_referenced(rule_id):
            return jsonify({"ok": False, "message": "该规则已被引用，无法删除"}), 403
        return jsonify({"ok": False, "message": "删除失败"}), 403
    governance_rule_service.clear_cache()
    return jsonify({"ok": True})


@bp.get("/governance/health")
def health():
    return jsonify({"ok": True, "module": "governance"})
