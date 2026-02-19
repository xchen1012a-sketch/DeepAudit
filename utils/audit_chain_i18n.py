# -*- coding: utf-8 -*-
"""
智能审计链中文映射
内部 key 不改，仅 UI 展示映射
"""

from typing import Any

EVENT_TYPE_CN_MAP: dict[str, str] = {
    "UPLOAD": "上传",
    "OCR": "OCR 识别",
    "RULE_HIT": "规则命中",
    "SCORE": "风险评分",
    "REVIEW": "复核",
    "APPROVAL": "审批",
    "RETURN": "退回",
    "FINAL": "终审",
    "EXPORT": "导出",
}

OBJECT_TYPE_CN_MAP: dict[str, str] = {
    "invoice": "凭证",
    "risk_event": "风险事件",
    "risk_case": "风险案件",
    "approval": "审批",
}


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_object_type(value: Any) -> str:
    return str(value or "").strip().lower()


def event_type_to_cn(event_type: Any) -> str:
    """事件类型转中文"""
    key = _normalize_key(event_type)
    return EVENT_TYPE_CN_MAP.get(key, key or "未知事件")


def object_type_to_cn(object_type: Any) -> str:
    """对象类型转中文"""
    key = _normalize_object_type(object_type)
    return OBJECT_TYPE_CN_MAP.get(key, key or "未知对象")
