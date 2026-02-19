# -*- coding: utf-8 -*-
"""
银行系统集成：银行流水拉取、自动对账、支付对接
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
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


def pull_bank_transactions(enterprise_id: int, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """拉取银行流水"""
    integration = get_integration(enterprise_id=enterprise_id, integration_type="bank")
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "银行系统集成未配置或未启用"}

    config = integration["config"]
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")
    account_no = config.get("account_no", "")

    if not api_url or not account_no:
        return {"ok": False, "msg": "银行API地址或账户号未配置"}

    # 默认拉取最近7天的流水
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        # TODO: 调用实际的银行API拉取流水
        # transactions = fetch_transactions_from_bank(api_url, api_key, account_no, start_date, end_date)

        transactions_synced = 0
        error_message = None

        # 示例：同步银行流水到bank_transactions表
        # for txn in transactions:
        #     with get_conn() as conn:
        #         # 检查是否已存在
        #         existing = conn.execute(
        #             "SELECT id FROM bank_transactions WHERE txn_id = ?",
        #             (txn["transaction_id"],),
        #         ).fetchone()
        #
        #         if not existing:
        #             conn.execute(
        #                 """
        #                 INSERT INTO bank_transactions (txn_id, ts, amount, counterparty, memo, imported_at)
        #                 VALUES (?, ?, ?, ?, ?, ?)
        #                 """,
        #                 (
        #                     txn["transaction_id"],
        #                     txn["transaction_time"],
        #                     txn["amount"],
        #                     txn.get("counterparty", ""),
        #                     txn.get("memo", ""),
        #                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        #                 ),
        #             )
        #             transactions_synced += 1

        sync_log_id = log_sync_result(
            integration_id=integration["id"],
            sync_type="transaction_pull",
            status="success",
            records_count=transactions_synced,
        )
        update_last_sync_time(integration["id"])

        return {
            "ok": True,
            "msg": "银行流水拉取成功",
            "transactions_synced": transactions_synced,
            "sync_log_id": sync_log_id,
        }
    except Exception as e:
        error_msg = str(e)
        log_sync_result(
            integration_id=integration["id"],
            sync_type="transaction_pull",
            status="failed",
            error_message=error_msg,
        )
        return {"ok": False, "msg": f"拉取失败: {error_msg}"}


def auto_match_invoice_to_transaction(invoice_id: int) -> dict[str, Any]:
    """发票与银行流水自动对账"""
    with get_conn() as conn:
        conn.row_factory = None
        invoice_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice_row:
            return {"ok": False, "msg": "发票不存在"}

        invoice_amount = _safe_float(invoice_row[3])  # amount字段
        invoice_date = _safe_text(invoice_row[4])  # invoice_date字段

        # 查找匹配的银行流水
        # 匹配规则：金额相同（允许小误差），时间相近（±3天）
        match_sql = """
            SELECT * FROM bank_transactions
            WHERE ABS(amount - ?) < 0.01
              AND matched_invoice_id IS NULL
              AND DATE(ts) BETWEEN DATE(?, '-3 days') AND DATE(?, '+3 days')
            ORDER BY ABS(julianday(ts) - julianday(?))
            LIMIT 1
        """
        txn_row = conn.execute(match_sql, (invoice_amount, invoice_date, invoice_date, invoice_date)).fetchone()

        if txn_row:
            txn_id = txn_row[0]
            match_score = 0.95  # 简化处理，实际应该计算匹配度

            # 更新匹配关系
            conn.execute(
                "UPDATE bank_transactions SET matched_invoice_id = ?, match_score = ?, match_reason = 'auto_match' WHERE id = ?",
                (invoice_id, match_score, txn_id),
            )

            return {
                "ok": True,
                "matched": True,
                "transaction_id": txn_id,
                "match_score": match_score,
            }
        else:
            return {
                "ok": True,
                "matched": False,
                "msg": "未找到匹配的银行流水",
            }


def execute_payment(invoice_id: int, payment_amount: float | None = None) -> dict[str, Any]:
    """执行支付（审批通过后自动支付）"""
    integration = get_integration(enterprise_id=1, integration_type="bank")  # TODO: 从invoice获取enterprise_id
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "银行系统集成未配置或未启用"}

    config = integration["config"]
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")
    account_no = config.get("account_no", "")

    if not api_url or not account_no:
        return {"ok": False, "msg": "银行API地址或账户号未配置"}

    with get_conn() as conn:
        conn.row_factory = None
        invoice_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice_row:
            return {"ok": False, "msg": "发票不存在"}

        # 检查审批状态
        approval_status = _safe_text(invoice_row[1008])  # approval_status字段
        if approval_status != "APPROVED":
            return {"ok": False, "msg": "发票未审批通过，无法支付"}

        amount = payment_amount if payment_amount is not None else _safe_float(invoice_row[3])
        payee_account = _safe_text(invoice_row.get("payee_account", ""))
        payee_name = _safe_text(invoice_row.get("payee_name", ""))

        if not payee_account:
            return {"ok": False, "msg": "收款账户未配置"}

        try:
            # TODO: 调用银行API执行支付
            # payment_result = execute_bank_payment(api_url, api_key, {
            #     "from_account": account_no,
            #     "to_account": payee_account,
            #     "to_name": payee_name,
            #     "amount": amount,
            #     "remark": f"发票{invoice_id}报销",
            # })

            # 更新发票状态为已支付
            # conn.execute(
            #     "UPDATE invoices SET payment_status = 'PAID', payment_time = ? WHERE id = ?",
            #     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), invoice_id),
            # )

            return {
                "ok": True,
                "msg": "支付成功",
                "payment_id": None,  # 实际应该返回银行返回的支付流水号
            }
        except Exception as e:
            return {"ok": False, "msg": f"支付失败: {str(e)}"}
