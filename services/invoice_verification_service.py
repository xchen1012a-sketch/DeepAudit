from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from events import event_bus
from events.types import INVOICE_VERIFIED, RISK_STAGE, STAGE_RULE_HIT, event_type_category
from integrations.tax_provider import VERIFY_STATUS_FAILED, VERIFY_STATUS_PASSED, build_tax_provider
from utils.db import get_invoice_for_verify, update_invoice_verification


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _parse_raw_json(raw_json_text: Any) -> dict[str, Any]:
    text = _safe_text(raw_json_text)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_invoice_code(raw_json: dict[str, Any]) -> str:
    for key in ("invoice_code", "invoiceCode", "code"):
        value = _safe_text(raw_json.get(key))
        if value:
            return value

    manual_entry = raw_json.get("manual_entry")
    if isinstance(manual_entry, dict):
        for key in ("invoice_code", "invoiceCode", "code"):
            value = _safe_text(manual_entry.get(key))
            if value:
                return value

    for line in _extract_lines(raw_json):
        match = re.search(r"(?:发票代码|invoice[_ ]?code)\s*[:：]?\s*([A-Za-z0-9-]+)", line, flags=re.IGNORECASE)
        if match and match.group(1):
            return _safe_text(match.group(1))
    return ""


def _extract_invoice_number(raw_json: dict[str, Any], reference_no: str) -> str:
    for key in ("invoice_number", "invoiceNo", "invoice_no", "number"):
        value = _safe_text(raw_json.get(key))
        if value:
            return value

    manual_entry = raw_json.get("manual_entry")
    if isinstance(manual_entry, dict):
        for key in ("invoice_number", "invoiceNo", "invoice_no", "number"):
            value = _safe_text(manual_entry.get(key))
            if value:
                return value

    for line in _extract_lines(raw_json):
        match = re.search(
            r"(?:发票号码|发票号|invoice[_ ]?(?:number|no))\s*[:：]?\s*([A-Za-z0-9-]+)",
            line,
            flags=re.IGNORECASE,
        )
        if match and match.group(1):
            return _safe_text(match.group(1))
    return _safe_text(reference_no)


def _extract_lines(value: Any) -> list[str]:
    lines: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                key_text = _safe_text(key)
                if isinstance(val, (dict, list, tuple)):
                    _walk(val)
                    continue
                val_text = _safe_text(val)
                if not val_text:
                    continue
                lines.append(f"{key_text}: {val_text}" if key_text else val_text)
            return
        if isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
            return

        text = _safe_text(obj)
        if text:
            lines.append(text)

    _walk(value)
    return lines


def _to_legacy_tax_status(result_status: str, result_code: str) -> str:
    if result_status == VERIFY_STATUS_PASSED:
        return "valid"

    code = _safe_text(result_code).upper()
    if "VOID" in code:
        return "void"
    if "ABNORMAL" in code:
        return "abnormal"
    if "RED" in code:
        return "red"
    return "red"


def _to_legacy_tax_result(verify_result: dict[str, Any]) -> dict[str, Any]:
    result_status = _safe_text(verify_result.get("verify_status"), VERIFY_STATUS_FAILED).upper()
    result_code = _safe_text(verify_result.get("result_code"))
    return {
        "ok": result_status == VERIFY_STATUS_PASSED,
        "status": _to_legacy_tax_status(result_status, result_code),
        "message": _safe_text(verify_result.get("verify_message")),
        "provider": _safe_text(verify_result.get("verify_provider")),
        "latency_ms": _safe_int(verify_result.get("verify_latency_ms"), 0),
        "status_code": _safe_int(verify_result.get("verify_status_code"), 0),
        "raw": verify_result.get("verify_raw_payload_dict") or {},
    }


def verify_invoice_internal(
    invoice_id: int,
    *,
    publish_event: bool = True,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], int]:
    invoice_row = get_invoice_for_verify(invoice_id)
    if not invoice_row:
        return {"ok": False, "msg": "invoice not found"}, 404

    raw_json = _parse_raw_json(invoice_row.get("raw_json"))
    invoice_code = _extract_invoice_code(raw_json)
    invoice_number = _extract_invoice_number(raw_json, _safe_text(invoice_row.get("reference_no")))
    invoice_date = _safe_text(invoice_row.get("invoice_date"))
    amount = invoice_row.get("amount")

    provider = build_tax_provider()
    try:
        provider_result = provider.verify_invoice(
            invoice_code=invoice_code,
            invoice_number=invoice_number,
            invoice_date=invoice_date or None,
            amount=amount,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        return {"ok": False, "msg": f"发票验真失败: {exc}"}, 500

    verify_status = _safe_text(provider_result.get("result_status"), VERIFY_STATUS_FAILED).upper()
    if verify_status not in {VERIFY_STATUS_PASSED, VERIFY_STATUS_FAILED}:
        verify_status = VERIFY_STATUS_FAILED
    verify_message = _safe_text(provider_result.get("result_message"), "发票验真返回空结果。")
    verify_provider = _safe_text(provider_result.get("provider"))
    verify_request_id = _safe_text(provider_result.get("request_id"))
    verify_latency_ms = _safe_int(provider_result.get("latency_ms"), 0)
    verify_status_code = _safe_int(provider_result.get("status_code"), 0)

    raw_payload = provider_result.get("raw_payload")
    if isinstance(raw_payload, str):
        try:
            verify_raw_payload_dict = json.loads(raw_payload)
            if not isinstance(verify_raw_payload_dict, dict):
                verify_raw_payload_dict = {"raw_payload": raw_payload}
        except Exception:
            verify_raw_payload_dict = {"raw_payload": raw_payload}
    elif isinstance(raw_payload, dict):
        verify_raw_payload_dict = raw_payload
    else:
        verify_raw_payload_dict = {}

    verify_checked_at = datetime.now().isoformat(timespec="seconds")
    updated_row = update_invoice_verification(
        invoice_id=int(invoice_id),
        verify_status=verify_status,
        verify_message=verify_message,
        verify_checked_at=verify_checked_at,
        verify_provider=verify_provider,
        verify_request_id=verify_request_id,
        verify_latency_ms=verify_latency_ms,
        verify_status_code=verify_status_code,
        verify_raw_payload=verify_raw_payload_dict,
    )
    if not updated_row:
        return {"ok": False, "msg": "invoice not found"}, 404

    human_status = "通过" if verify_status == VERIFY_STATUS_PASSED else "未通过"
    event_message = f"发票验真{human_status}：{verify_message}（{verify_latency_ms}ms）"
    event_payload = {
        "stage": STAGE_RULE_HIT,
        "event_type": INVOICE_VERIFIED,
        "message": event_message,
        "category": event_type_category(INVOICE_VERIFIED),
        "trace_id": verify_request_id,
        "invoice_id": int(invoice_id),
        "request_id": verify_request_id,
        "provider": verify_provider,
        "status_code": verify_status_code,
        "result_code": _safe_text(provider_result.get("result_code")).upper(),
        "result_status": verify_status,
        "latency_ms": verify_latency_ms,
        "related_ids": {
            "invoice_id": int(invoice_id),
            "request_id": verify_request_id,
        },
    }

    event_id = 0
    if publish_event:
        published = event_bus.publish(RISK_STAGE, event_payload)
        event_id = _safe_int(published.get("id"), 0)

    payload: dict[str, Any] = {
        "ok": True,
        "invoice_id": int(invoice_id),
        "verify_status": verify_status,
        "verify_message": verify_message,
        "verify_provider": verify_provider,
        "verify_request_id": verify_request_id,
        "verify_latency_ms": verify_latency_ms,
        "verify_status_code": verify_status_code,
        "verify_checked_at": _safe_text(updated_row.get("verify_checked_at"), verify_checked_at),
        "verify_count": _safe_int(updated_row.get("verify_count"), 0),
        "result_code": _safe_text(provider_result.get("result_code")).upper(),
        "event_id": event_id,
        "verify_raw_payload_dict": verify_raw_payload_dict,
    }
    payload["tax_result"] = _to_legacy_tax_result(payload)
    return payload, 200

