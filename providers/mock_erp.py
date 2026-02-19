from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.settings import MOCK_DATA_DIR, MOCK_FAILURE_RATE, MOCK_LATENCY_MS_RANGE
from providers.base import ErpProvider
from utils.jsonl_store import read_jsonl
from utils.mock_net import pick_failure, should_fail, simulate_latency


def _get_config_value(key: str, fallback: str) -> str:
    try:
        from flask import current_app

        if current_app:
            value = current_app.config.get(key)
            if value is not None:
                return str(value)
    except Exception:
        pass
    return str(os.getenv(key, fallback))


def _parse_latency_range(value: str) -> tuple[int, int]:
    raw = str(value or "").strip()
    if "," not in raw:
        return (200, 1200)
    left, right = raw.split(",", 1)
    try:
        low = int(left.strip())
        high = int(right.strip())
    except Exception:
        return (200, 1200)
    if low < 0:
        low = 0
    if high < 0:
        high = 0
    if high < low:
        low, high = high, low
    return (low, high)


def _normalize_orders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        order_id = str(row.get("order_id") or "").strip()
        project = str(row.get("project") or "").strip()
        cost_center = str(row.get("cost_center") or "").strip()
        vendor = str(row.get("vendor") or "").strip()
        budget_subject = str(row.get("budget_subject") or "").strip()
        if not order_id or not project or not cost_center or not vendor or not budget_subject:
            continue
        normalized.append(
            {
                "order_id": order_id,
                "project": project,
                "cost_center": cost_center,
                "vendor": vendor,
                "budget_subject": budget_subject,
            }
        )
    return normalized


class MockErpProvider(ErpProvider):
    provider_name = "mock_erp_v1"

    def __init__(self) -> None:
        data_dir = _get_config_value("MOCK_DATA_DIR", MOCK_DATA_DIR)
        self.orders_file = Path(data_dir) / "mock_orders.jsonl"
        self.failure_rate = float(_get_config_value("MOCK_FAILURE_RATE", str(MOCK_FAILURE_RATE)))
        self.min_latency_ms, self.max_latency_ms = _parse_latency_range(
            _get_config_value("MOCK_LATENCY_MS_RANGE", MOCK_LATENCY_MS_RANGE)
        )
        self.employees: dict[str, dict[str, str]] = {
            "E1001": {"employee_id": "E1001", "name": "Liam Chen", "department": "Finance"},
            "E1002": {"employee_id": "E1002", "name": "Ava Lin", "department": "Engineering"},
            "E1003": {"employee_id": "E1003", "name": "Noah Wang", "department": "Marketing"},
            "E1004": {"employee_id": "E1004", "name": "Emma Liu", "department": "HR"},
            "E1005": {"employee_id": "E1005", "name": "Olivia Zhao", "department": "Procurement"},
            "E1006": {"employee_id": "E1006", "name": "Lucas Xu", "department": "Legal"},
            "E1007": {"employee_id": "E1007", "name": "Sophia Sun", "department": "Operations"},
            "E1008": {"employee_id": "E1008", "name": "Mason Guo", "department": "Security"},
            "E1009": {"employee_id": "E1009", "name": "Isabella He", "department": "Sales"},
            "E1010": {"employee_id": "E1010", "name": "Ethan Qiu", "department": "Admin"},
        }

    def _load_orders(self) -> list[dict[str, Any]]:
        rows = read_jsonl(str(self.orders_file))
        return _normalize_orders(rows)

    def search_orders(self, keyword: str, limit: int = 20) -> dict[str, Any]:
        latency_ms = simulate_latency(self.min_latency_ms, self.max_latency_ms)

        if should_fail(self.failure_rate):
            failure = pick_failure()
            return {
                "ok": False,
                "error_code": str(failure.get("error_code") or "unknown"),
                "items": [],
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": str(failure.get("message") or "外部服务异常，已进入待复核"),
            }

        normalized_keyword = str(keyword or "").strip().lower()
        normalized_limit = max(1, min(int(limit or 20), 200))
        try:
            rows = self._load_orders()
        except Exception as exc:
            return {
                "ok": False,
                "error_code": "data_error",
                "items": [],
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": f"读取模拟ERP订单失败: {exc}",
            }

        if not normalized_keyword:
            matched = rows
        else:
            matched = []
            for row in rows:
                haystack = " ".join(
                    [
                        str(row.get("order_id") or ""),
                        str(row.get("vendor") or ""),
                        str(row.get("project") or ""),
                        str(row.get("cost_center") or ""),
                    ]
                ).lower()
                if normalized_keyword in haystack:
                    matched.append(row)

        return {
            "ok": True,
            "items": matched[:normalized_limit],
            "provider": self.provider_name,
            "latency_ms": latency_ms,
            "message": f"检索成功，返回 {min(len(matched), normalized_limit)} 条订单",
        }

    def get_employee(self, employee_id: str) -> dict[str, Any]:
        latency_ms = simulate_latency(self.min_latency_ms, self.max_latency_ms)

        if should_fail(self.failure_rate):
            failure = pick_failure()
            return {
                "ok": False,
                "error_code": str(failure.get("error_code") or "unknown"),
                "item": None,
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": str(failure.get("message") or "外部服务异常，已进入待复核"),
            }

        normalized_id = str(employee_id or "").strip().upper()
        if not normalized_id:
            return {
                "ok": False,
                "error_code": "bad_request",
                "item": None,
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": "employee_id 不能为空",
            }

        employee = self.employees.get(normalized_id)
        if employee is None:
            return {
                "ok": False,
                "error_code": "not_found",
                "item": None,
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": "未找到员工（模拟）",
            }

        return {
            "ok": True,
            "item": dict(employee),
            "provider": self.provider_name,
            "latency_ms": latency_ms,
            "message": "查询成功",
        }
