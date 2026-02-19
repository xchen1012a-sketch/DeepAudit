# -*- coding: utf-8 -*-
"""
统一集成服务：数据同步调度、集成状态监控
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_integration(
    enterprise_id: int,
    integration_type: str,
    config: dict[str, Any],
    status: str = "active",
) -> dict[str, Any]:
    """创建集成配置"""
    integration_type = _safe_text(integration_type).lower()
    if integration_type not in {"finance", "hr", "oa", "bank"}:
        raise ValueError(f"不支持的集成类型: {integration_type}")

    config_json = json.dumps(config, ensure_ascii=False)

    with get_conn() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            """
            INSERT INTO db_integrations (enterprise_id, integration_type, config_json, status)
            VALUES (?, ?, ?, ?)
            """,
            (enterprise_id, integration_type, config_json, status),
        )
        integration_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM db_integrations WHERE id = ?", (integration_id,)).fetchone()
        config_dict = {}
        if row[2]:
            try:
                config_dict = json.loads(row[2])
            except Exception:
                pass

        return {
            "id": row[0],
            "enterprise_id": row[1],
            "integration_type": row[2],
            "config": config_dict,
            "status": row[4],
            "last_sync_at": row[5],
        }


def get_integration(integration_id: int | None = None, enterprise_id: int | None = None, integration_type: str | None = None) -> dict[str, Any] | None:
    """获取集成配置"""
    with get_conn() as conn:
        conn.row_factory = None
        if integration_id:
            row = conn.execute("SELECT * FROM db_integrations WHERE id = ?", (integration_id,)).fetchone()
        elif enterprise_id and integration_type:
            row = conn.execute(
                "SELECT * FROM db_integrations WHERE enterprise_id = ? AND integration_type = ?",
                (enterprise_id, integration_type),
            ).fetchone()
        else:
            return None

        if not row:
            return None

        config = {}
        if row[2]:
            try:
                config = json.loads(row[2])
            except Exception:
                pass

        return {
            "id": row[0],
            "enterprise_id": row[1],
            "integration_type": row[2],
            "config": config,
            "status": row[4],
            "last_sync_at": row[5],
        }


def list_integrations(enterprise_id: int | None = None) -> list[dict[str, Any]]:
    """列出集成配置"""
    with get_conn() as conn:
        conn.row_factory = None
        if enterprise_id:
            rows = conn.execute(
                "SELECT * FROM db_integrations WHERE enterprise_id = ? ORDER BY integration_type",
                (enterprise_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM db_integrations ORDER BY enterprise_id, integration_type").fetchall()

        result = []
        for row in rows:
            config = {}
            if row[2]:
                try:
                    config = json.loads(row[2])
                except Exception:
                    pass

            result.append({
                "id": row[0],
                "enterprise_id": row[1],
                "integration_type": row[2],
                "config": config,
                "status": row[4],
                "last_sync_at": row[5],
            })
        return result


def update_integration_config(integration_id: int, config: dict[str, Any]) -> bool:
    """更新集成配置"""
    config_json = json.dumps(config, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "UPDATE db_integrations SET config_json = ? WHERE id = ?",
            (config_json, integration_id),
        )
        return True


def update_integration_status(integration_id: int, status: str) -> bool:
    """更新集成状态"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE db_integrations SET status = ? WHERE id = ?",
            (status, integration_id),
        )
        return True


def update_last_sync_time(integration_id: int) -> bool:
    """更新最后同步时间"""
    sync_time = _now_text()
    with get_conn() as conn:
        conn.execute(
            "UPDATE db_integrations SET last_sync_at = ? WHERE id = ?",
            (sync_time, integration_id),
        )
        return True


def log_sync_result(
    integration_id: int,
    sync_type: str,
    status: str,
    records_count: int = 0,
    error_message: str | None = None,
) -> int:
    """记录同步日志"""
    with get_conn() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            """
            INSERT INTO db_sync_logs (integration_id, sync_type, status, records_count, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (integration_id, sync_type, status, records_count, error_message),
        )
        return cursor.lastrowid


def get_sync_logs(integration_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """获取同步日志"""
    with get_conn() as conn:
        conn.row_factory = None
        if integration_id:
            rows = conn.execute(
                "SELECT * FROM db_sync_logs WHERE integration_id = ? ORDER BY sync_at DESC LIMIT ?",
                (integration_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM db_sync_logs ORDER BY sync_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "integration_id": row[1],
                "sync_type": row[2],
                "status": row[3],
                "records_count": row[4],
                "error_message": row[5],
                "sync_at": row[6],
            })
        return result
