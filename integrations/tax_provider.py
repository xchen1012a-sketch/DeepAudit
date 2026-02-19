from __future__ import annotations

import os
import random
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from core.settings import MOCK_DATA_DIR, TAX_PROVIDER_NAME as DEFAULT_TAX_PROVIDER_NAME, VERIFY_MODE as DEFAULT_VERIFY_MODE
from utils.jsonl_store import read_jsonl

VERIFY_STATUS_PASSED = "PASSED"
VERIFY_STATUS_FAILED = "FAILED"

_PROVIDER_LOCK = Lock()
_PROVIDER_SINGLETONS: dict[str, "TaxProvider"] = {}

_MASKED_FIELD_KEYS = {
    "name",
    "full_name",
    "buyer_name",
    "seller_name",
    "phone",
    "mobile",
    "telephone",
    "tel",
    "address",
    "location",
    "bank",
    "bank_name",
    "bank_no",
    "bank_number",
    "bank_card",
    "card_no",
    "card_number",
    "account",
    "account_no",
    "id_no",
    "id_number",
    "identity",
    "身份证",
    "姓名",
    "手机号",
    "电话",
    "地址",
    "银行卡",
    "银行账号",
}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


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


def _resolve_verify_mode(value: str | None = None) -> str:
    mode = _safe_text(value) or _safe_text(_get_config_value("VERIFY_MODE", DEFAULT_VERIFY_MODE)).lower()
    mode = mode.lower()
    if mode in {"replay", "mock"}:
        return mode
    return "replay"


def _resolve_tax_provider_name(default_value: str = DEFAULT_TAX_PROVIDER_NAME) -> str:
    return _safe_text(_get_config_value("TAX_PROVIDER_NAME", default_value), default_value)


def _normalize_replay_key(invoice_code: Any, invoice_number: Any) -> tuple[str, str]:
    return _safe_text(invoice_code).upper(), _safe_text(invoice_number).upper()


def _resolve_result_status(raw_status: Any) -> str:
    text = _safe_text(raw_status).upper()
    if text in {VERIFY_STATUS_PASSED, VERIFY_STATUS_FAILED}:
        return text
    text = text.lower()
    if text in {"valid", "ok", "pass", "passed", "success"}:
        return VERIFY_STATUS_PASSED
    return VERIFY_STATUS_FAILED


def _mask_payload(value: Any, parent_key: str = "") -> Any:
    key = _safe_text(parent_key).lower()
    if key in _MASKED_FIELD_KEYS:
        return "***"

    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for k, v in value.items():
            key_text = _safe_text(k)
            lower_key = key_text.lower()
            if lower_key in _MASKED_FIELD_KEYS or key_text in _MASKED_FIELD_KEYS:
                masked[key_text or str(k)] = "***"
                continue
            masked[key_text or str(k)] = _mask_payload(v, key_text)
        return masked

    if isinstance(value, list):
        return [_mask_payload(item, parent_key) for item in value]

    return value


def _build_raw_request_payload(
    *,
    invoice_code: Any,
    invoice_number: Any,
    invoice_date: Any = None,
    amount: Any = None,
    idempotency_key: Any = None,
) -> dict[str, Any]:
    payload = {
        "invoice_code": _safe_text(invoice_code),
        "invoice_number": _safe_text(invoice_number),
        "invoice_date": _safe_text(invoice_date),
        "amount": _safe_text(amount),
        "idempotency_key": _safe_text(idempotency_key),
    }
    return _mask_payload(payload)


class TaxProvider(ABC):
    @abstractmethod
    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str | None = None,
        amount: str | float | int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Return shape:
        {
            "provider": str,
            "request_id": str,
            "status_code": int,
            "latency_ms": int,
            "result_status": "PASSED|FAILED",
            "result_code": str,
            "result_message": str,
            "raw_payload": dict,
        }
        """


class MockTaxProvider(TaxProvider):
    def __init__(self, provider_name: str = "GD_TAX_MOCK") -> None:
        self.provider_name = _safe_text(provider_name, "GD_TAX_MOCK")

    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str | None = None,
        amount: str | float | int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        latency_ms = random.randint(50, 800)
        code = _safe_text(invoice_code)
        number = _safe_text(invoice_number)
        request_payload = _build_raw_request_payload(
            invoice_code=code,
            invoice_number=number,
            invoice_date=invoice_date,
            amount=amount,
            idempotency_key=idempotency_key,
        )

        if not code or not number:
            return {
                "provider": self.provider_name,
                "request_id": request_id,
                "status_code": 400,
                "latency_ms": latency_ms,
                "result_status": VERIFY_STATUS_FAILED,
                "result_code": "MISSING_FIELDS",
                "result_message": "发票代码或发票号码不完整。",
                "raw_payload": request_payload,
            }

        trailing_digit = ""
        for ch in reversed(number):
            if ch.isdigit():
                trailing_digit = ch
                break
        if trailing_digit == "":
            return {
                "provider": self.provider_name,
                "request_id": request_id,
                "status_code": 400,
                "latency_ms": latency_ms,
                "result_status": VERIFY_STATUS_FAILED,
                "result_code": "INVALID_NUMBER",
                "result_message": "发票号码格式异常，无法完成验真。",
                "raw_payload": request_payload,
            }

        is_passed = int(trailing_digit) % 2 == 0
        if is_passed:
            result_status = VERIFY_STATUS_PASSED
            result_code = "EVEN_LAST_DIGIT"
            result_message = "发票验真通过（规则兜底）。"
        else:
            result_status = VERIFY_STATUS_FAILED
            result_code = "ODD_LAST_DIGIT"
            result_message = "发票验真未通过：票号校验失败（规则兜底）。"

        return {
            "provider": self.provider_name,
            "request_id": request_id,
            "status_code": 200,
            "latency_ms": latency_ms,
            "result_status": result_status,
            "result_code": result_code,
            "result_message": result_message,
            "raw_payload": request_payload,
        }


class ReplayTaxProvider(TaxProvider):
    def __init__(
        self,
        *,
        data_file: str | None = None,
        provider_name: str | None = None,
        fallback_provider: TaxProvider | None = None,
    ) -> None:
        self.provider_name = _safe_text(provider_name, _resolve_tax_provider_name())
        data_dir = _safe_text(_get_config_value("MOCK_DATA_DIR", MOCK_DATA_DIR), MOCK_DATA_DIR)
        self.data_file = Path(data_file or (Path(data_dir) / "mock_tax_responses.jsonl"))
        self.fallback_provider = fallback_provider or MockTaxProvider("GD_TAX_MOCK_FALLBACK")
        self._rows_cache: list[dict[str, Any]] | None = None
        self._index_cache: dict[tuple[str, str], dict[str, Any]] | None = None

    def _load_index(self) -> dict[tuple[str, str], dict[str, Any]]:
        if self._index_cache is not None:
            return self._index_cache

        rows = read_jsonl(str(self.data_file))
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_code = _safe_text(row.get("invoice_code") or row.get("code")).upper()
            row_number = _safe_text(row.get("invoice_number") or row.get("number")).upper()
            if not row_number:
                continue
            key = (row_code, row_number)
            if key not in index:
                index[key] = dict(row)

        self._rows_cache = rows
        self._index_cache = index
        return index

    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str | None = None,
        amount: str | float | int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        latency_ms = random.randint(50, 800)
        code = _safe_text(invoice_code).upper()
        number = _safe_text(invoice_number).upper()

        try:
            index = self._load_index()
        except Exception:
            fallback = self.fallback_provider.verify_invoice(
                invoice_code=invoice_code,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                amount=amount,
                idempotency_key=idempotency_key,
            )
            fallback["request_id"] = request_id
            fallback["latency_ms"] = latency_ms
            return fallback

        row = index.get((code, number))
        if row is None:
            fallback = self.fallback_provider.verify_invoice(
                invoice_code=invoice_code,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                amount=amount,
                idempotency_key=idempotency_key,
            )
            fallback["request_id"] = request_id
            fallback["latency_ms"] = latency_ms
            return fallback

        result_status = _resolve_result_status(row.get("result_status") or row.get("status"))
        result_code = _safe_text(row.get("result_code") or row.get("status"), "REPLAY_MATCHED").upper()
        result_message = _safe_text(row.get("message"), "发票验真完成（回放）。")
        status_code = _safe_int(row.get("status_code"), 200)
        raw_payload = row.get("raw")
        if not isinstance(raw_payload, dict):
            raw_payload = dict(row)

        return {
            "provider": self.provider_name,
            "request_id": request_id,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "result_status": result_status,
            "result_code": result_code,
            "result_message": result_message,
            "raw_payload": _mask_payload(raw_payload),
        }


def build_tax_provider(mode: str | None = None) -> TaxProvider:
    resolved_mode = _resolve_verify_mode(mode)
    provider_name = _resolve_tax_provider_name()
    data_dir = _safe_text(_get_config_value("MOCK_DATA_DIR", MOCK_DATA_DIR), MOCK_DATA_DIR)
    replay_data_file = str(Path(data_dir) / "mock_tax_responses.jsonl")
    cache_key = f"{resolved_mode}|{provider_name}|{replay_data_file}"

    with _PROVIDER_LOCK:
        cached = _PROVIDER_SINGLETONS.get(cache_key)
        if cached is not None:
            return cached

        if resolved_mode == "mock":
            provider: TaxProvider = MockTaxProvider(provider_name="GD_TAX_MOCK")
        else:
            provider = ReplayTaxProvider(
                data_file=replay_data_file,
                provider_name=provider_name,
                fallback_provider=MockTaxProvider(provider_name="GD_TAX_MOCK_FALLBACK"),
            )

        _PROVIDER_SINGLETONS[cache_key] = provider
        return provider
