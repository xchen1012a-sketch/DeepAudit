from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.settings import MOCK_DATA_DIR, MOCK_FAILURE_RATE, MOCK_LATENCY_MS_RANGE
from providers.base import BankProvider
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


def _normalize_txn_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_txn_ids: set[str] = set()
    for row in rows:
        txn_id = str(row.get("txn_id") or "").strip()
        ts = str(row.get("ts") or "").strip()
        counterparty = str(row.get("counterparty") or "").strip()
        memo = str(row.get("memo") or "").strip()
        amount = row.get("amount")

        if not txn_id or not ts or not counterparty or not memo:
            continue
        if txn_id in seen_txn_ids:
            continue
        try:
            amount_number = float(amount)
        except Exception:
            continue

        seen_txn_ids.add(txn_id)
        result.append(
            {
                "txn_id": txn_id,
                "amount": amount_number,
                "ts": ts,
                "counterparty": counterparty,
                "memo": memo,
            }
        )
    return result


class MockBankProvider(BankProvider):
    provider_name = "mock_bank_v1"

    def __init__(self) -> None:
        data_dir = _get_config_value("MOCK_DATA_DIR", MOCK_DATA_DIR)
        self.data_file = Path(data_dir) / "mock_bank_txn.jsonl"
        self.failure_rate = float(_get_config_value("MOCK_FAILURE_RATE", str(MOCK_FAILURE_RATE)))
        self.min_latency_ms, self.max_latency_ms = _parse_latency_range(
            _get_config_value("MOCK_LATENCY_MS_RANGE", MOCK_LATENCY_MS_RANGE)
        )

    def _load_rows(self) -> list[dict[str, Any]]:
        rows = read_jsonl(str(self.data_file))
        return _normalize_txn_rows(rows)

    def pull_transactions(self, cursor: str | None, limit: int = 50) -> dict[str, Any]:
        latency_ms = simulate_latency(self.min_latency_ms, self.max_latency_ms)

        if should_fail(self.failure_rate):
            failure = pick_failure()
            return {
                "ok": False,
                "error_code": str(failure.get("error_code") or "unknown"),
                "next_cursor": cursor,
                "items": [],
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": str(failure.get("message") or "外部服务异常，已进入待复核"),
            }

        normalized_limit = max(1, min(int(limit or 50), 500))
        try:
            start = int(str(cursor).strip()) if cursor is not None else 0
        except Exception:
            start = 0
        if start < 0:
            start = 0

        try:
            all_items = self._load_rows()
        except Exception as exc:
            return {
                "ok": False,
                "error_code": "data_error",
                "next_cursor": cursor,
                "items": [],
                "provider": self.provider_name,
                "latency_ms": latency_ms,
                "message": f"读取模拟银行流水失败: {exc}",
            }

        if start > len(all_items):
            start = len(all_items)
        end = min(start + normalized_limit, len(all_items))
        items = all_items[start:end]
        next_cursor = str(end) if end < len(all_items) else None

        return {
            "ok": True,
            "next_cursor": next_cursor,
            "items": items,
            "provider": self.provider_name,
            "latency_ms": latency_ms,
            "message": f"拉取成功，返回 {len(items)} 条流水",
        }
