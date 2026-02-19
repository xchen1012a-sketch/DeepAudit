# -*- coding: utf-8 -*-
"""
智能决策引擎：规则链、多模型融合、自动决策策略
"""

from __future__ import annotations

import json
from typing import Any

from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def evaluate_rule_chain(invoice_data: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    """评估规则链"""
    results = []
    total_score = 0
    max_score = 0

    for rule in rules:
        rule_key = _safe_text(rule.get("rule_key", ""))
        rule_name = _safe_text(rule.get("rule_name", ""))
        threshold = _safe_float(rule.get("threshold", 0))
        severity = _safe_text(rule.get("severity", "MEDIUM")).upper()
        enabled = rule.get("enabled", True)

        if not enabled:
            continue

        # 根据规则类型评估
        rule_result = evaluate_single_rule(invoice_data, rule)
        if rule_result["hit"]:
            results.append({
                "rule_key": rule_key,
                "rule_name": rule_name,
                "severity": severity,
                "score": rule_result["score"],
                "reason": rule_result["reason"],
            })
            total_score += rule_result["score"]
            max_score = max(max_score, rule_result["score"])

    # 计算综合风险等级
    risk_level = "LOW"
    if max_score >= 80:
        risk_level = "HIGH"
    elif max_score >= 50:
        risk_level = "MEDIUM"

    return {
        "risk_level": risk_level,
        "risk_score": max_score,
        "total_score": total_score,
        "rules_hit": results,
        "rules_count": len(results),
    }


def evaluate_single_rule(invoice_data: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """评估单个规则"""
    rule_key = _safe_text(rule.get("rule_key", "")).upper()
    threshold = _safe_float(rule.get("threshold", 0))
    threshold_json = rule.get("threshold_json", {})

    amount = _safe_float(invoice_data.get("amount", 0))
    invoice_date = _safe_text(invoice_data.get("invoice_date", ""))
    applicant = _safe_text(invoice_data.get("applicant", ""))
    department = _safe_text(invoice_data.get("department", ""))

    hit = False
    score = 0
    reason = ""

    if rule_key == "AMOUNT_WARNING_THRESHOLD":
        if amount > threshold:
            hit = True
            score = min(100, int((amount / threshold - 1) * 50))
            reason = f"金额超过预警线（{amount} > {threshold}）"

    elif rule_key == "HOTEL_LIMIT_NORMAL":
        limit = _safe_float(threshold_json.get("limit", threshold))
        if amount > limit:
            hit = True
            score = min(100, int((amount / limit - 1) * 60))
            reason = f"住宿费用超标（{amount} > {limit}）"

    elif rule_key == "SENSITIVE_WORDS":
        sensitive_words = threshold_json.get("words", [])
        ocr_text = _safe_text(invoice_data.get("ocr_text", "")).lower()
        for word in sensitive_words:
            if word.lower() in ocr_text:
                hit = True
                score = 85
                reason = f"命中敏感词：{word}"
                break

    elif rule_key == "DUPLICATE_INVOICE":
        invoice_code = _safe_text(invoice_data.get("invoice_code", ""))
        invoice_number = _safe_text(invoice_data.get("invoice_number", ""))
        if invoice_code and invoice_number:
            # 检查是否存在重复发票
            with get_conn() as conn:
                conn.row_factory = None
                existing = conn.execute(
                    "SELECT id FROM invoices WHERE invoice_code = ? AND invoice_number = ? AND id != ?",
                    (invoice_code, invoice_number, invoice_data.get("id", 0)),
                ).fetchone()
                if existing:
                    hit = True
                    score = 90
                    reason = "检测到重复发票"

    return {
        "hit": hit,
        "score": score,
        "reason": reason,
    }


def fuse_ai_models(ai_results: list[dict[str, Any]]) -> dict[str, Any]:
    """融合多个AI模型的结果"""
    if not ai_results:
        return {
            "risk_level": "LOW",
            "risk_score": 0,
            "confidence": 0.0,
            "summary": "无AI分析结果",
        }

    # 计算加权平均风险分数
    total_score = 0
    total_weight = 0
    risk_levels = []

    for result in ai_results:
        score = _safe_int(result.get("risk_score", 0))
        confidence = _safe_float(result.get("confidence", 0.5))
        level = _safe_text(result.get("risk_level", "LOW")).upper()

        weight = confidence
        total_score += score * weight
        total_weight += weight
        risk_levels.append(level)

    if total_weight > 0:
        avg_score = int(total_score / total_weight)
    else:
        avg_score = 0

    # 确定最终风险等级（取最高等级）
    final_level = "LOW"
    if "HIGH" in risk_levels:
        final_level = "HIGH"
    elif "MEDIUM" in risk_levels:
        final_level = "MEDIUM"

    # 合并摘要
    summaries = [r.get("summary", "") for r in ai_results if r.get("summary")]
    summary = "；".join(summaries) if summaries else "AI分析完成"

    return {
        "risk_level": final_level,
        "risk_score": avg_score,
        "confidence": min(1.0, total_weight / len(ai_results)) if ai_results else 0.0,
        "summary": summary,
        "model_count": len(ai_results),
    }


def auto_decision(invoice_data: dict[str, Any], rule_results: dict[str, Any], ai_results: dict[str, Any] | None = None) -> dict[str, Any]:
    """自动决策"""
    amount = _safe_float(invoice_data.get("amount", 0))
    applicant = _safe_text(invoice_data.get("applicant", ""))

    # 白名单检查
    if is_whitelist_user(applicant):
        return {
            "decision": "APPROVE",
            "reason": "白名单用户，自动通过",
            "auto": True,
        }

    # 黑名单检查
    if is_blacklist_user(applicant):
        return {
            "decision": "REJECT",
            "reason": "黑名单用户，自动拒绝",
            "auto": True,
        }

    # 综合风险评分
    risk_level = rule_results.get("risk_level", "LOW")
    risk_score = rule_results.get("risk_score", 0)

    if ai_results:
        ai_level = ai_results.get("risk_level", "LOW")
        ai_score = ai_results.get("risk_score", 0)
        # 取较高的风险等级
        if ai_level == "HIGH" or risk_level == "HIGH":
            risk_level = "HIGH"
        elif ai_level == "MEDIUM" or risk_level == "MEDIUM":
            risk_level = "MEDIUM"
        risk_score = max(risk_score, ai_score)

    # 自动决策规则
    if risk_level == "HIGH" and risk_score >= 90:
        return {
            "decision": "REJECT",
            "reason": "高风险，自动拒绝",
            "auto": True,
            "risk_level": risk_level,
            "risk_score": risk_score,
        }

    if risk_level == "LOW" and risk_score < 30 and amount < 1000:
        return {
            "decision": "APPROVE",
            "reason": "低风险小额，自动通过",
            "auto": True,
            "risk_level": risk_level,
            "risk_score": risk_score,
        }

    # 需要人工审批
    return {
        "decision": "PENDING",
        "reason": "需要人工审批",
        "auto": False,
        "risk_level": risk_level,
        "risk_score": risk_score,
    }


def is_whitelist_user(username: str) -> bool:
    """检查是否为白名单用户"""
    # TODO: 从配置或数据库读取白名单
    whitelist = []  # 示例：["admin", "finance_manager"]
    return username in whitelist


def is_blacklist_user(username: str) -> bool:
    """检查是否为黑名单用户"""
    # TODO: 从配置或数据库读取黑名单
    blacklist = []  # 示例：["blocked_user"]
    return username in blacklist


def get_approval_route(amount: float, risk_level: str) -> str:
    """根据金额和风险等级确定审批路由"""
    if risk_level == "HIGH":
        return "department_manager->finance_manager->ceo"
    elif amount >= 10000:
        return "department_manager->finance_manager"
    elif amount >= 5000:
        return "department_manager"
    else:
        return "auto"
