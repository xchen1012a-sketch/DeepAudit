from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from utils.db import get_workflow_current_config, list_invoices, to_business_risk_reason

APPROVAL_STATUSES = {"PENDING", "APPROVED", "REJECTED", "RETURNED"}
APPROVAL_STAGES = {"L1", "L2", "DONE"}
SLA_HOURS = {"HIGH": 2, "MEDIUM": 24, "LOW": 72}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _parse_amount(value: Any) -> float:
    text = _safe_text(value)
    cleaned = text.replace(",", "").replace("¥", "").replace("￥", "")
    return _safe_float(cleaned, 0.0)


def safe_limit(raw: Any, default: int = 200, max_limit: int = 5000) -> int:
    value = _safe_int(raw, default)
    if value <= 0:
        value = default
    return min(value, max_limit)


def actor_id(user: dict[str, Any]) -> str:
    return (
        _safe_text(user.get("username"))
        or _safe_text(user.get("employee_no"))
        or _safe_text(user.get("id"))
        or "system"
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = _safe_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _normalize_risk_level(value: Any) -> str:
    risk = _safe_text(value).upper()
    return risk if risk in {"HIGH", "MEDIUM", "LOW"} else "LOW"


def _normalize_stage(value: Any, status: str) -> str:
    stage = _safe_text(value).upper()
    if stage in APPROVAL_STAGES:
        return stage
    return "L1" if status == "PENDING" else "DONE"


def _normalize_status(approval_status: Any, fallback_status: Any = None) -> str:
    status = _safe_text(approval_status).upper()
    if status in APPROVAL_STATUSES:
        return status
    fallback = _safe_text(fallback_status).upper()
    return fallback if fallback in APPROVAL_STATUSES else "PENDING"


def _default_sla_minutes(risk_level: str) -> int:
    return int(SLA_HOURS.get(risk_level, SLA_HOURS["LOW"])) * 60


def _effective_sla_due_at(row: dict[str, Any]) -> datetime | None:
    explicit_due = _parse_datetime(row.get("sla_due_at"))
    if explicit_due is not None:
        return explicit_due

    created = _parse_datetime(row.get("created_at"))
    if created is None:
        return None

    risk_level = _normalize_risk_level(row.get("risk_level"))
    return created + timedelta(minutes=_default_sla_minutes(risk_level))


def _rule_evidence(row: dict[str, Any]) -> dict[str, Any]:
    amount_text = _safe_text(row.get("amount"))
    threshold_text = _safe_text(row.get("hotel_limit"))
    rule_hit_id = _safe_text(row.get("rule_hit_id")) or "RULE_RISK_LEVEL"
    explanation = (
        _safe_text(row.get("rule_explain_biz"))
        or _safe_text(row.get("rule_explain"))
        or _safe_text(row.get("risk_reason_biz"))
        or _safe_text(row.get("risk_reason"))
    )
    explanation = to_business_risk_reason(
        explanation,
        source=row.get("source"),
        amount=row.get("amount"),
        threshold=row.get("hotel_limit"),
    )

    ratio_text = "-"
    try:
        amount_value = float(amount_text.replace(",", "").replace("¥", "").replace("￥", ""))
        threshold_value = float(threshold_text)
        if threshold_value > 0:
            ratio_value = ((amount_value - threshold_value) / threshold_value) * 100.0
            ratio_text = f"{ratio_value:.1f}%"
    except Exception:
        ratio_text = "-"

    risk_level = _normalize_risk_level(row.get("risk_level"))
    suggestion = "建议直接通过"
    if risk_level == "MEDIUM":
        suggestion = "建议补充材料后处理"
    elif risk_level == "HIGH":
        suggestion = "建议提交二线复核"

    return {
        "rule_hit_id": rule_hit_id,
        "rule_version": "v1-local",
        "threshold": threshold_text or "-",
        "actual_value": amount_text or "-",
        "over_ratio": ratio_text,
        "suggestion": suggestion,
        "summary": explanation or "无规则说明",
    }


def _rule_hit_count(row: dict[str, Any]) -> int:
    raw = _safe_text(row.get("rule_hit_id"))
    if not raw:
        return 0
    return len([item for item in raw.split(",") if _safe_text(item)])


def _workflow_node(workflow_config: dict[str, Any], step: str) -> dict[str, Any]:
    nodes = workflow_config.get("nodes")
    if not isinstance(nodes, dict):
        return {}
    node = nodes.get(step)
    return dict(node) if isinstance(node, dict) else {}


def _matches_workflow_conditions(row: dict[str, Any], conditions: dict[str, Any]) -> bool:
    if not isinstance(conditions, dict):
        return False

    amount_gte = _safe_float(conditions.get("amount_gte"), 0.0)
    if _parse_amount(row.get("amount")) < amount_gte:
        return False

    hit_count_gte = _safe_int(conditions.get("rule_hit_count_gte"), 0)
    if _rule_hit_count(row) < max(0, hit_count_gte):
        return False

    raw_levels = conditions.get("risk_levels")
    levels = []
    if isinstance(raw_levels, (list, tuple, set)):
        levels = [_safe_text(item).upper() for item in raw_levels if _safe_text(item)]
    if levels:
        if _normalize_risk_level(row.get("risk_level")) not in levels:
            return False

    return True


def _workflow_step_for_row(row: dict[str, Any], workflow_config: dict[str, Any]) -> str:
    status = _normalize_status(row.get("approval_status"), row.get("status"))
    if status != "PENDING":
        return "END"

    stage = _normalize_stage(row.get("approval_stage"), status)
    if stage == "L2":
        return "C"

    node_c = _workflow_node(workflow_config, "C")
    conditions_c = node_c.get("conditions") if isinstance(node_c.get("conditions"), dict) else {}
    if _matches_workflow_conditions(row, conditions_c):
        return "C"

    node_b = _workflow_node(workflow_config, "B")
    conditions_b = node_b.get("conditions") if isinstance(node_b.get("conditions"), dict) else {}
    if _matches_workflow_conditions(row, conditions_b):
        return "B"

    return "A"


def _enrich_row(row: dict[str, Any], *, workflow_config: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["risk_level"] = _normalize_risk_level(item.get("risk_level"))
    item["approval_status"] = _normalize_status(item.get("approval_status"), item.get("status"))
    item["approval_stage"] = _normalize_stage(item.get("approval_stage"), item["approval_status"])
    item["status"] = item["approval_status"]

    created = _parse_datetime(item.get("created_at"))
    now_dt = datetime.now()
    waiting_minutes = 0
    if created is not None:
        waiting_minutes = max(0, int((now_dt - created).total_seconds() // 60))

    due_dt = _effective_sla_due_at(item)
    sla_remaining_minutes = 0
    if due_dt is not None:
        sla_remaining_minutes = int((due_dt - now_dt).total_seconds() // 60)

    item["waiting_minutes"] = waiting_minutes
    item["sla_remaining_minutes"] = sla_remaining_minutes
    item["is_overdue"] = due_dt is not None and sla_remaining_minutes < 0
    item["rule_evidence"] = _rule_evidence(item)
    item["risk_reason"] = _safe_text(item.get("risk_reason_biz")) or _safe_text(item.get("risk_reason"))
    item["rule_explain"] = (
        _safe_text(item.get("rule_explain_biz"))
        or _safe_text(item.get("rule_explain"))
        or _safe_text(item.get("risk_reason"))
    )
    item["verify_status"] = _safe_text(item.get("verify_status"), "PENDING").upper()
    item["ai_trace_id"] = _safe_text(item.get("ai_trace_id"))
    item["workflow_rule_hit_count"] = _rule_hit_count(item)
    item["workflow_step"] = _workflow_step_for_row(item, workflow_config)
    workflow_step = _safe_text(item.get("workflow_step")).upper()
    node = _workflow_node(workflow_config, workflow_step)
    if workflow_step == "B":
        default_role = "MANAGER"
    elif workflow_step == "C":
        default_role = "CFO"
    elif workflow_step == "A":
        default_role = "AI_SENTINEL"
    else:
        default_role = "NONE"
    item["workflow_required_role"] = _safe_text(node.get("required_role"), default_role).upper()
    return item


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = list(rows)
    sorted_rows.sort(
        key=lambda item: (
            0 if bool(item.get("is_overdue")) else 1,
            int(item.get("sla_remaining_minutes", 0)),
            -int(item.get("waiting_minutes", 0)),
            -_safe_int(item.get("id"), 0),
        )
    )
    return sorted_rows


def list_approval_rows(
    *,
    limit: int,
    department_scope: str | None = None,
    data_scope: dict[str, Any] | None = None,
    row_cleaner: Any = None,
) -> list[dict[str, Any]]:
    rows = list_invoices(
        limit=limit,
        department=department_scope,
        record_state="LEDGER",
        data_scope=data_scope,
    )
    if callable(row_cleaner):
        rows = row_cleaner(rows)
    workflow_current = get_workflow_current_config()
    workflow_config_raw = workflow_current.get("config") if isinstance(workflow_current, dict) else {}
    workflow_config = dict(workflow_config_raw) if isinstance(workflow_config_raw, dict) else {}
    return _sort_rows([_enrich_row(dict(item), workflow_config=workflow_config) for item in rows])


def summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    pending_rows = [
        item
        for item in rows
        if _normalize_status(item.get("approval_status"), item.get("status")) == "PENDING"
        and _safe_text(item.get("queue_owner_id"))
    ]
    high_pending = [item for item in pending_rows if _normalize_risk_level(item.get("risk_level")) == "HIGH"]
    sla_lt_4h = [item for item in pending_rows if int(item.get("sla_remaining_minutes", 0)) <= 240]
    overdue = [item for item in pending_rows if bool(item.get("is_overdue"))]
    return {
        "pending_total": len(pending_rows),
        "high_pending": len(high_pending),
        "sla_lt_4h": len(sla_lt_4h),
        "overdue": len(overdue),
    }
