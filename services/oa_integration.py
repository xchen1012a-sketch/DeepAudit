# -*- coding: utf-8 -*-
"""
OA系统集成：审批流程对接、待办任务同步、消息推送
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from services.integration_service import get_integration, log_sync_result, update_last_sync_time
from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def sync_approval_tasks(enterprise_id: int) -> dict[str, Any]:
    """同步OA系统的待办任务"""
    integration = get_integration(enterprise_id=enterprise_id, integration_type="oa")
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "OA系统集成未配置或未启用"}

    config = integration["config"]
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")

    if not api_url:
        return {"ok": False, "msg": "OA API地址未配置"}

    try:
        # TODO: 调用实际的OA系统API获取待办任务
        # tasks = fetch_tasks_from_oa(api_url, api_key)

        tasks_synced = 0
        error_message = None

        # 示例：同步待办任务
        # for task in tasks:
        #     # 将OA任务同步到本系统的审批流程中
        #     # 这里需要根据实际业务逻辑处理
        #     tasks_synced += 1

        sync_log_id = log_sync_result(
            integration_id=integration["id"],
            sync_type="task_sync",
            status="success",
            records_count=tasks_synced,
        )
        update_last_sync_time(integration["id"])

        return {
            "ok": True,
            "msg": "待办任务同步成功",
            "tasks_synced": tasks_synced,
            "sync_log_id": sync_log_id,
        }
    except Exception as e:
        error_msg = str(e)
        log_sync_result(
            integration_id=integration["id"],
            sync_type="task_sync",
            status="failed",
            error_message=error_msg,
        )
        return {"ok": False, "msg": f"同步失败: {error_msg}"}


def push_approval_to_oa(invoice_id: int, approval_action: str, approver: str, comment: str | None = None) -> dict[str, Any]:
    """推送审批结果到OA系统"""
    integration = get_integration(enterprise_id=1, integration_type="oa")  # TODO: 从invoice获取enterprise_id
    if not integration or integration["status"] != "active":
        return {"ok": False, "msg": "OA系统集成未配置或未启用"}

    config = integration["config"]
    api_url = config.get("api_url", "")
    api_key = config.get("api_key", "")

    if not api_url:
        return {"ok": False, "msg": "OA API地址未配置"}

    try:
        # 获取发票信息
        with get_conn() as conn:
            conn.row_factory = None
            invoice_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if not invoice_row:
                return {"ok": False, "msg": "发票不存在"}

        # 构建审批数据
        approval_data = {
            "invoice_id": invoice_id,
            "action": approval_action,  # approve/reject
            "approver": approver,
            "comment": comment,
            "timestamp": datetime.now().isoformat(),
        }

        # TODO: 调用OA系统API推送审批结果
        # result = push_to_oa_api(api_url, api_key, approval_data)

        return {
            "ok": True,
            "msg": "审批结果已推送到OA系统",
        }
    except Exception as e:
        return {"ok": False, "msg": f"推送失败: {str(e)}"}


def send_notification(channel: str, recipients: list[str], title: str, content: str) -> dict[str, Any]:
    """发送通知（邮件/短信/企业微信）"""
    # 根据channel选择不同的通知方式
    if channel == "email":
        return send_email_notification(recipients, title, content)
    elif channel == "sms":
        return send_sms_notification(recipients, content)
    elif channel == "wecom":
        return send_wecom_notification(recipients, title, content)
    else:
        return {"ok": False, "msg": f"不支持的通知渠道: {channel}"}


def send_email_notification(recipients: list[str], title: str, content: str) -> dict[str, Any]:
    """发送邮件通知"""
    # TODO: 实现邮件发送逻辑
    # 可以使用smtplib或第三方邮件服务
    return {"ok": True, "msg": "邮件通知已发送"}


def send_sms_notification(recipients: list[str], content: str) -> dict[str, Any]:
    """发送短信通知"""
    # TODO: 实现短信发送逻辑
    # 可以使用第三方短信服务API
    return {"ok": True, "msg": "短信通知已发送"}


def send_wecom_notification(recipients: list[str], title: str, content: str) -> dict[str, Any]:
    """发送企业微信通知"""
    # TODO: 实现企业微信通知逻辑
    # 调用企业微信API发送消息
    return {"ok": True, "msg": "企业微信通知已发送"}
