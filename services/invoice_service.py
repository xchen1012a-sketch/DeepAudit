from __future__ import annotations

import json
import re
from typing import Any

from utils.db import get_conn


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


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


def _find_first(lines: list[str], patterns: list[str]) -> str:
    for line in lines:
        for pattern in patterns:
            m = re.search(pattern, line, flags=re.IGNORECASE)
            if m and m.group(1):
                return _safe_text(m.group(1))
    return ""


def _parse_raw_json(raw_text: Any) -> dict[str, Any]:
    text = _safe_text(raw_text)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_invoice_number(raw_json: dict[str, Any], reference_no: str) -> str:
    for key in ("invoice_number", "invoice_no", "number"):
        value = _safe_text(raw_json.get(key))
        if value:
            return value

    manual_entry = raw_json.get("manual_entry")
    if isinstance(manual_entry, dict):
        for key in ("invoice_number", "invoice_no", "number", "invoice_code"):
            value = _safe_text(manual_entry.get(key))
            if value:
                return value

    lines = _extract_lines(raw_json)
    found = _find_first(
        lines,
        [
            r"(?:invoice[_ ]?(?:number|no)|发票(?:号码|号))\s*[:：]?\s*([A-Za-z0-9\-]+)",
        ],
    )
    if found:
        return found

    return reference_no


def _extract_seller_name(raw_json: dict[str, Any]) -> str:
    manual_entry = raw_json.get("manual_entry")
    if isinstance(manual_entry, dict):
        value = _safe_text(manual_entry.get("seller_name"))
        if value:
            return value

    mock_meta = raw_json.get("mock_meta")
    if isinstance(mock_meta, dict):
        value = _safe_text(mock_meta.get("merchant"))
        if value:
            return value

    lines = _extract_lines(raw_json)
    return _find_first(
        lines,
        [
            r"(?:seller|vendor|merchant|销售方|开票方)\s*[:：]?\s*(.+)$",
        ],
    )


def _extract_date(raw_json: dict[str, Any], invoice_date: str) -> str:
    if invoice_date:
        return invoice_date
    lines = _extract_lines(raw_json)
    return _find_first(
        lines,
        [
            r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        ],
    )


def get_invoice_dict(invoice_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                reference_no,
                amount,
                invoice_date,
                applicant,
                department,
                raw_json,
                is_canton_fair,
                hotel_limit,
                currency,
                manual_rate,
                manual_cny_amount
            FROM invoices
            WHERE id = ?
            """,
            (invoice_id,),
        ).fetchone()

    if row is None:
        return {}

    raw_json = _parse_raw_json(row["raw_json"])
    reference_no = _safe_text(row["reference_no"])
    invoice_date = _safe_text(row["invoice_date"])
    applicant = _safe_text(row["applicant"])

    seller_name = _extract_seller_name(raw_json)
    buyer_name = _safe_text(raw_json.get("buyer_name")) or applicant
    invoice_number = _extract_invoice_number(raw_json, reference_no)

    return {
        "invoice_id": int(row["id"]),
        "invoice_number": invoice_number,
        "amount": _safe_text(row["amount"]),
        "date": _extract_date(raw_json, invoice_date),
        "invoice_date": invoice_date,
        "is_canton_fair": bool(int(row["is_canton_fair"] or 0)),
        "hotel_limit": row["hotel_limit"],
        "currency": _safe_text(row["currency"]),
        "manual_rate": _safe_text(row["manual_rate"]),
        "manual_cny_amount": _safe_text(row["manual_cny_amount"]),
        "seller_name": seller_name,
        "buyer_name": buyer_name,
        "reference_no": reference_no,
        "department": _safe_text(row["department"]),
    }

