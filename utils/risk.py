# -*- coding: utf-8 -*-

from typing import Any

from services import governance_rule_service
from utils.fx_audit import audit_manual_rate_arbitrage


def _to_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", "")
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _to_level(value: Any, fallback: str = "MEDIUM") -> str:
    text = str(value or "").strip().upper()
    if text in {"LOW", "MEDIUM", "HIGH"}:
        return text
    return fallback


def _score_for_level(level: str) -> int:
    if level == "HIGH":
        return 88
    if level == "LOW":
        return 25
    return 60


def _extract_threshold(rule: dict[str, Any] | None, *keys: str) -> float | None:
    if not isinstance(rule, dict):
        return None
    threshold = rule.get("threshold")
    if not isinstance(threshold, dict):
        return None
    for key in keys:
        value = _to_float(threshold.get(key))
        if value is not None:
            return value
    for value in threshold.values():
        numeric = _to_float(value)
        if numeric is not None:
            return numeric
    return None


def _format_num(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def evaluate_risk(
    amount_str: Any,
    invoice_date: str | None,
    hotel_limit: Any,
    is_canton_fair: bool,
    currency: str | None = None,
    manual_rate: Any = None,
    manual_cny_amount: Any = None,
) -> dict[str, Any]:
    amount = _to_float(amount_str)
    evidence: list[dict[str, str]] = []

    fx = audit_manual_rate_arbitrage(
        amount=amount,
        currency=currency,
        manual_rate=manual_rate,
        manual_cny_amount=manual_cny_amount,
    )
    fx_flag = bool(fx.get("flag"))
    fx_reason = str(fx.get("reason") or "")

    if amount is None or not invoice_date:
        return {
            "level": "MEDIUM",
            "score": 60,
            "reason": "信息缺失（金额或日期为空）",
            "evidence": evidence,
            "fx_flag": fx_flag,
            "fx_reason": fx_reason,
        }

    try:
        rules_by_key = governance_rule_service.get_enabled_rules()
    except Exception:
        rules_by_key = {}

    limit_rule_key = "HOTEL_LIMIT_CANTON_FAIR" if is_canton_fair else "HOTEL_LIMIT_NORMAL"
    limit_rule_state = governance_rule_service.get_rule(limit_rule_key)
    limit_rule = rules_by_key.get(limit_rule_key)
    limit_rule_exists = int(limit_rule_state.get("version") or 0) > 0
    limit_rule_enabled = bool(limit_rule_state.get("enabled"))

    level = "LOW"
    score = _score_for_level(level)
    reason = "正常（未触发阈值）"

    if limit_rule_exists and not limit_rule_enabled:
        limit = None
        reason = f"规则已停用（{limit_rule_key}）"
    else:
        limit = _extract_threshold(limit_rule, "limit", "threshold", "value")
        if limit is None and not limit_rule_exists:
            # Last-resort fallback for legacy rows without governance rule rows.
            limit = _to_float(hotel_limit)

    if limit is None and not (limit_rule_exists and not limit_rule_enabled):
        level = "MEDIUM"
        score = _score_for_level(level)
        reason = "信息缺失（住宿限额为空）"
    elif limit is not None:
        medium_ratio_rule = rules_by_key.get("HOTEL_MEDIUM_RATIO")
        medium_ratio_state = governance_rule_service.get_rule("HOTEL_MEDIUM_RATIO")
        medium_ratio_exists = int(medium_ratio_state.get("version") or 0) > 0
        medium_ratio_enabled = bool(medium_ratio_state.get("enabled"))

        medium_ratio = None
        if medium_ratio_enabled:
            medium_ratio = _extract_threshold(medium_ratio_rule, "ratio", "threshold", "value")
        if medium_ratio is None and not medium_ratio_exists:
            medium_ratio = 0.9
        if medium_ratio is not None:
            medium_ratio = max(0.0, min(medium_ratio, 1.5))

        if amount > limit and isinstance(limit_rule, dict):
            level = _to_level(limit_rule.get("severity"), "HIGH")
            if level == "LOW":
                level = "MEDIUM"
            score = _score_for_level(level)
            reason = "超限（金额 > 住宿限额）"
            evidence.append(
                {
                    "type": "rule_hit",
                    "key": limit_rule_key,
                    "value": (
                        f"amount={_format_num(amount)} > limit={_format_num(limit)} "
                        f"(cantonfair={str(bool(is_canton_fair)).lower()})"
                    ),
                }
            )
        elif isinstance(medium_ratio_rule, dict) and medium_ratio is not None and amount >= medium_ratio * limit:
            level = _to_level(medium_ratio_rule.get("severity"), "MEDIUM")
            if level == "LOW":
                level = "MEDIUM"
            score = _score_for_level(level)
            reason = "临界（金额接近住宿限额）"
            evidence.append(
                {
                    "type": "rule_hit",
                    "key": "HOTEL_MEDIUM_RATIO",
                    "value": (
                        f"amount={_format_num(amount)} >= ratio={_format_num(medium_ratio)}"
                        f"*limit={_format_num(limit)}"
                    ),
                }
            )
        else:
            level = "LOW"
            score = _score_for_level(level)
            reason = "正常（未触发阈值）"

    if fx_flag:
        evidence.append({"type": "rule_hit", "key": "FX_MANUAL_RATE", "value": fx_reason})
        if level == "LOW":
            level = "MEDIUM"
            score = max(score, _score_for_level("MEDIUM"))
        else:
            score = min(100, score + 8)
        reason = f"{reason}；{fx_reason}"

    return {
        "level": level,
        "score": int(score),
        "reason": reason,
        "evidence": evidence,
        "fx_flag": fx_flag,
        "fx_reason": fx_reason,
    }
