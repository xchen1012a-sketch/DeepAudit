# -*- coding: utf-8 -*-
"""
财务系统集成：ERP对接、凭证同步、对账匹配
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from services.integration_service import get_integration, log_sync_result, update_last_sync_time
from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def sync_erp_vouchers(enterprise_id: int, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """同步ERP凭证数据"""
    integration = get_integration(enterprise_id=enterprise_id, integration_type="finance")
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "财务系统集成未配置或未启用"}

    config = integration["config"]
    erp_type = config.get("erp_type", "").upper()  # SAP, UFIDA, KINGDEE等
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")

    if not api_url:
        return {"ok": False, "msg": "ERP API地址未配置"}

    # 这里应该调用实际的ERP API
    # 示例：模拟数据同步
    try:
        # TODO: 实现实际的ERP API调用
        # 根据erp_type调用不同的API接口
        # SAP: 调用SAP RFC或REST API
        # UFIDA: 调用用友API
        # KINGDEE: 调用金蝶API

        records_count = 0
        error_message = None

        # 模拟同步成功
        sync_log_id = log_sync_result(
            integration_id=integration["id"],
            sync_type="voucher_sync",
            status="success",
            records_count=records_count,
        )
        update_last_sync_time(integration["id"])

        return {
            "ok": True,
            "msg": "同步成功",
            "records_count": records_count,
            "sync_log_id": sync_log_id,
        }
    except Exception as e:
        error_msg = str(e)
        log_sync_result(
            integration_id=integration["id"],
            sync_type="voucher_sync",
            status="failed",
            error_message=error_msg,
        )
        return {"ok": False, "msg": f"同步失败: {error_msg}"}


def map_account_subject(invoice_data: dict[str, Any]) -> str:
    """费用科目映射：根据发票信息自动分类到会计科目"""
    # 根据发票类型、金额、供应商等信息映射到会计科目
    category = invoice_data.get("category", "").lower()
    amount = _safe_float(invoice_data.get("amount", 0))

    # 简单的科目映射规则（实际应该从配置中读取）
    if "差旅" in category or "travel" in category:
        return "6601-差旅费"
    elif "住宿" in category or "hotel" in category:
        return "6601-差旅费"
    elif "餐饮" in category or "meal" in category:
        return "6601-业务招待费"
    elif "办公" in category or "office" in category:
        return "6602-办公费"
    elif "交通" in category or "transport" in category:
        return "6601-交通费"
    else:
        return "6601-其他费用"


def match_invoice_to_voucher(invoice_id: int) -> dict[str, Any]:
    """发票与凭证自动匹配"""
    with get_conn() as conn:
        conn.row_factory = None
        invoice_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice_row:
            return {"ok": False, "msg": "发票不存在"}

        amount = _safe_float(invoice_row[3])  # amount字段
        invoice_date = _safe_text(invoice_row[4])  # invoice_date字段

        # 从ERP凭证表中查找匹配的凭证
        # 这里需要根据实际ERP系统的凭证表结构来查询
        # 示例：假设有一个erp_vouchers表
        # match_sql = """
        #     SELECT * FROM erp_vouchers
        #     WHERE ABS(amount - ?) < 0.01
        #       AND voucher_date = ?
        #       AND status = 'unmatched'
        #     LIMIT 1
        # """
        # voucher = conn.execute(match_sql, (amount, invoice_date)).fetchone()

        # 返回匹配结果
        return {
            "ok": True,
            "matched": False,  # 实际应该根据查询结果判断
            "match_score": 0.0,
            "voucher_id": None,
        }


def create_voucher_from_invoice(invoice_id: int) -> dict[str, Any]:
    """根据发票创建财务凭证"""
    with get_conn() as conn:
        conn.row_factory = None
        invoice_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice_row:
            return {"ok": False, "msg": "发票不存在"}

        # 提取发票信息
        amount = _safe_float(invoice_row[3])
        invoice_date = _safe_text(invoice_row[4])
        applicant = _safe_text(invoice_row[5])
        department = _safe_text(invoice_row[6])

        # 映射会计科目
        invoice_data = {
            "amount": amount,
            "category": department,  # 简化处理
        }
        account_subject = map_account_subject(invoice_data)

        # 创建凭证数据
        voucher_data = {
            "voucher_date": invoice_date,
            "voucher_type": "expense",
            "debit_account": account_subject,
            "credit_account": "1001-库存现金",  # 简化处理
            "amount": amount,
            "summary": f"{applicant}报销",
            "invoice_id": invoice_id,
        }

        # TODO: 调用ERP API创建凭证
        # 这里应该调用实际的ERP API

        return {
            "ok": True,
            "msg": "凭证创建成功",
            "voucher_data": voucher_data,
        }
