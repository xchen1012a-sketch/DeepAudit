from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any

from utils.db import list_governance_rules
from utils.governance_i18n import rule_threshold_type

_CACHE_TTL_SECONDS = 3.0
_CACHE_LOCK = threading.Lock()
_CACHE_RULES_BY_KEY: dict[str, dict[str, Any]] | None = None
_CACHE_EXPIRES_AT = 0.0


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


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


def _threshold_field(rule_key: str) -> str:
    mapping = {
        "HOTEL_LIMIT_NORMAL": "limit",
        "HOTEL_LIMIT_CANTON_FAIR": "limit",
        "HOTEL_MEDIUM_RATIO": "ratio",
        "DUPLICATE_EXPENSE_THRESHOLD": "count",
        "HIGH_RISK_SCORE_THRESHOLD": "score",
    }
    return mapping.get(rule_key, "threshold")


def _parse_threshold(threshold_json: Any, *, rule_key: str, fallback: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(threshold_json, dict):
        payload = dict(threshold_json)
    elif isinstance(threshold_json, str):
        try:
            loaded = json.loads(threshold_json)
            if isinstance(loaded, dict):
                payload = dict(loaded)
        except Exception:
            payload = {}

    if not payload:
        payload = {_threshold_field(rule_key): _safe_float(fallback, 0.0)}
    return payload


def _normalize_severity(value: Any) -> str:
    text = _safe_text(value).upper()
    if text in {"LOW", "MEDIUM", "HIGH"}:
        return text
    return "MEDIUM"


def _normalize_rule(row: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    rule_key = _safe_text(row.get("rule_key")).upper()
    if not rule_key:
        return None
    threshold = _parse_threshold(
        row.get("threshold_json"),
        rule_key=rule_key,
        fallback=row.get("threshold"),
    )
    status = str(row.get("status") or "published").strip().lower()
    config = {
        "rule_key": rule_key,
        "enabled": bool(row.get("enabled")),
        "threshold": threshold,
        "severity": _normalize_severity(row.get("severity")),
        "version": _safe_int(row.get("version"), 1),
        "rule_name": _safe_text(row.get("rule_name")),
        "updated_at": _safe_text(row.get("updated_at")),
        "status": status if status in ("draft", "published") else "published",
    }
    return rule_key, config


def _load_rules_from_db() -> dict[str, dict[str, Any]]:
    rows = list_governance_rules()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        normalized = _normalize_rule(row)
        if normalized is None:
            continue
        key, config = normalized
        result[key] = config
    return result


def _get_rules_cached(*, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    global _CACHE_RULES_BY_KEY, _CACHE_EXPIRES_AT
    now = time.monotonic()
    with _CACHE_LOCK:
        cache_ready = _CACHE_RULES_BY_KEY is not None and now < _CACHE_EXPIRES_AT
        if cache_ready and not force_refresh:
            return copy.deepcopy(_CACHE_RULES_BY_KEY)

    loaded = _load_rules_from_db()
    with _CACHE_LOCK:
        _CACHE_RULES_BY_KEY = loaded
        _CACHE_EXPIRES_AT = time.monotonic() + _CACHE_TTL_SECONDS
        return copy.deepcopy(_CACHE_RULES_BY_KEY)


def clear_cache() -> None:
    global _CACHE_RULES_BY_KEY, _CACHE_EXPIRES_AT
    with _CACHE_LOCK:
        _CACHE_RULES_BY_KEY = None
        _CACHE_EXPIRES_AT = 0.0


def get_enabled_rules() -> dict[str, dict[str, Any]]:
    """仅返回已发布且启用的规则（草稿不参与业务）。"""
    rules = _get_rules_cached()
    return {
        key: value
        for key, value in rules.items()
        if bool(value.get("enabled")) and str(value.get("status") or "published").strip().lower() == "published"
    }


def get_rule(rule_key: str) -> dict[str, Any]:
    key = _safe_text(rule_key).upper()
    if not key:
        return {
            "rule_key": "",
            "enabled": False,
            "threshold": {},
            "severity": "MEDIUM",
            "version": 0,
        }
    rules = _get_rules_cached()
    found = rules.get(key)
    if isinstance(found, dict):
        return copy.deepcopy(found)
    return {
        "rule_key": key,
        "enabled": False,
        "threshold": {},
        "severity": "MEDIUM",
        "version": 0,
    }


def validate_rule_threshold(rule_key: str, value: Any) -> tuple[bool, str]:
    """
    校验规则阈值：amount(>=0,2位小数)、ratio(0-1)、count(整数>=0)、score(0-100整数)。
    返回 (ok, message_cn)。
    """
    key = _safe_text(rule_key).upper()
    typ = rule_threshold_type(key)
    text = str(value).strip() if value is not None else ""
    if not text:
        return False, "阈值为必填项"
    if typ == "amount":
        try:
            v = float(text)
        except (ValueError, TypeError):
            return False, "金额类型必须为数字"
        if v < 0:
            return False, "金额必须大于等于 0"
        if round(v, 2) != v and abs(v - round(v, 2)) > 1e-9:
            return False, "金额最多保留 2 位小数"
        return True, ""
    if typ == "ratio":
        try:
            v = float(text)
        except (ValueError, TypeError):
            return False, "比例类型必须为数字"
        if v < 0 or v > 1:
            return False, "比例必须在 0～1 之间"
        return True, ""
    if typ == "count":
        try:
            v = int(float(text))
        except (ValueError, TypeError):
            return False, "次数类型必须为整数"
        if v < 0:
            return False, "次数必须大于等于 0"
        if float(text) != v:
            return False, "次数必须为整数"
        return True, ""
    if typ == "score":
        try:
            v = int(float(text))
        except (ValueError, TypeError):
            return False, "分值类型必须为整数"
        if v < 0 or v > 100:
            return False, "分值必须在 0～100 之间"
        if float(text) != v:
            return False, "分值必须为整数"
        return True, ""
    try:
        v = float(text)
        if v < 0:
            return False, "阈值必须大于等于 0"
    except (ValueError, TypeError):
        return False, "阈值必须为数字"
    return True, ""
