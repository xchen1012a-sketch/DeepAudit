# -*- coding: utf-8 -*-
"""
治理规则 i18n：规则展示名称、阈值类型/单位、变更原因选项
全链路中文，rule_key 内部不变，仅做映射展示
"""

from __future__ import annotations

from typing import Any

# 规则键 -> 中文展示名称
RULE_DISPLAY_NAME_MAP: dict[str, str] = {
    "HOTEL_LIMIT_NORMAL": "酒店住宿标准（常规）",
    "HOTEL_LIMIT_CANTON_FAIR": "酒店住宿标准（广交会）",
    "HOTEL_MEDIUM_RATIO": "酒店中等风险比例",
    "AMOUNT_WARNING_THRESHOLD": "金额预警阈值",
    "DUPLICATE_EXPENSE_THRESHOLD": "重复报销次数阈值",
    "HIGH_RISK_SCORE_THRESHOLD": "高风险评分阈值",
}

# 规则键 -> 阈值类型：amount(金额)、ratio(比例)、count(次数)、score(分值)
RULE_THRESHOLD_TYPE_MAP: dict[str, str] = {
    "HOTEL_LIMIT_NORMAL": "amount",
    "HOTEL_LIMIT_CANTON_FAIR": "amount",
    "HOTEL_MEDIUM_RATIO": "ratio",
    "AMOUNT_WARNING_THRESHOLD": "amount",
    "DUPLICATE_EXPENSE_THRESHOLD": "count",
    "HIGH_RISK_SCORE_THRESHOLD": "score",
}

# 规则键 -> 单位
RULE_THRESHOLD_UNIT_MAP: dict[str, str] = {
    "HOTEL_LIMIT_NORMAL": "元",
    "HOTEL_LIMIT_CANTON_FAIR": "元",
    "HOTEL_MEDIUM_RATIO": "",
    "AMOUNT_WARNING_THRESHOLD": "元",
    "DUPLICATE_EXPENSE_THRESHOLD": "次",
    "HIGH_RISK_SCORE_THRESHOLD": "分",
}

# 规则变更原因选项（value -> label）
RULE_CHANGE_REASON_OPTIONS: list[dict[str, str]] = [
    {"value": "MANUAL_ADJUST", "label": "人工调整"},
    {"value": "POLICY_UPDATE", "label": "政策变更"},
    {"value": "THRESHOLD_CALIBRATION", "label": "阈值校准"},
    {"value": "FALSE_POSITIVE_FIX", "label": "误报修正"},
    {"value": "TEMP_CONTROL", "label": "临时管控"},
    {"value": "RESTORE_DEFAULT", "label": "恢复默认"},
]


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().upper()


def rule_display_name(rule_key: Any) -> str:
    """规则键 -> 中文展示名称"""
    key = _normalize_key(rule_key)
    return RULE_DISPLAY_NAME_MAP.get(key, key or "—")


def rule_threshold_type(rule_key: Any) -> str:
    """规则键 -> 阈值类型：amount/ratio/count/score，未知默认 threshold"""
    key = _normalize_key(rule_key)
    return RULE_THRESHOLD_TYPE_MAP.get(key, "threshold")


def rule_threshold_unit(rule_key: Any) -> str:
    """规则键 -> 单位"""
    key = _normalize_key(rule_key)
    return RULE_THRESHOLD_UNIT_MAP.get(key, "")
