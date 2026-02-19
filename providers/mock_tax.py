from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.settings import MOCK_DATA_DIR, MOCK_FAILURE_RATE, MOCK_LATENCY_MS_RANGE
from providers.base import TaxProvider
from utils.jsonl_store import read_jsonl
from utils.mock_net import pick_failure, should_fail, simulate_latency

VALID_STATUSES = {"valid", "void", "red", "abnormal"}


def _get_config_value(key: str, default: str) -> str:
    try:
        from flask import current_app

        if current_app:
            value = current_app.config.get(key)
            if value is not None:
                return str(value)
    except Exception:
        pass
    return str(os.getenv(key, default))


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


def _extract_invoice_number(invoice: dict[str, Any]) -> str:
    for key in ("invoice_number", "number", "invoice_no"):
        text = str((invoice or {}).get(key) or "").strip()
        if text:
            return text
    return ""


class MockTaxProvider(TaxProvider):
    provider_name = "mock_tax_v1"

    def __init__(self) -> None:
        data_dir = _get_config_value("MOCK_DATA_DIR", MOCK_DATA_DIR)
        self.data_file = Path(data_dir) / "mock_tax_responses.jsonl"
        self.failure_rate = float(_get_config_value("MOCK_FAILURE_RATE", str(MOCK_FAILURE_RATE)))
        self.min_latency_ms, self.max_latency_ms = _parse_latency_range(
            _get_config_value("MOCK_LATENCY_MS_RANGE", MOCK_LATENCY_MS_RANGE)
        )

    def _load_rows(self) -> list[dict[str, Any]]:
        rows = read_jsonl(str(self.data_file))
        normalized: list[dict[str, Any]] = []
        for row in rows:
            invoice_number = str(row.get("invoice_number") or "").strip()
            if not invoice_number:
                continue
            normalized.append(dict(row))
        return normalized

    def verify_invoice(self, invoice: dict[str, Any]) -> dict[str, Any]:
        latency_ms = simulate_latency(self.min_latency_ms, self.max_latency_ms)

        if should_fail(self.failure_rate):
            failure = pick_failure()
            return {
                "ok": False,
                "status": "unknown",
                "error_code": str(failure.get("error_code") or "unknown"),
                "message": str(failure.get("message") or "外部服务异常，已进入待复核"),
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "raw": {},
            }

        invoice_number = _extract_invoice_number(invoice)
        if not invoice_number:
            return {
                "ok": False,
                "status": "unknown",
                "error_code": "bad_request",
                "message": "缺少发票号码（invoice_number）",
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "raw": {"invoice": dict(invoice or {})},
            }

        try:
            rows = self._load_rows()
        except Exception as exc:
            return {
                "ok": False,
                "status": "unknown",
                "error_code": "data_error",
                "message": f"读取模拟税务数据失败: {exc}",
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "raw": {},
            }

        matched = next(
            (row for row in rows if str(row.get("invoice_number") or "").strip() == invoice_number),
            None,
        )
        if matched is None:
            return {
                "ok": True,
                "status": "unknown",
                "message": "未匹配到验真记录（模拟），建议人工复核",
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "raw": {},
            }

        status = str(matched.get("status") or "").strip().lower()
        if status not in VALID_STATUSES:
            status = "unknown"
        raw_payload = matched.get("raw")
        if not isinstance(raw_payload, dict):
            raw_payload = {"record": dict(matched)}
        return {
            "ok": True,
            "status": status,
            "message": str(matched.get("message") or "模拟验真返回"),
            "provider": self.provider_name,
            "latency_ms": latency_ms,
            "raw": raw_payload,
        }
