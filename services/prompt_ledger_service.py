from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from typing import Any

from utils.db import get_conn

GENESIS_HASH = "GENESIS"
DEFAULT_PROMPT_VERSION = "tax_verify_prompt_v1"


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: Any) -> Any:
    text = _safe_text(value)
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


def _build_hash(
    *,
    hash_prev: str,
    input_json: str,
    output_json: str,
    prompt_version: str,
    provider: str,
) -> str:
    plain = f"{hash_prev}{input_json}{output_json}{prompt_version}{provider}"
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _build_input_payload(
    *,
    invoice_id: int,
    invoice: dict[str, Any] | None,
    tax_result: dict[str, Any] | None,
    ai_data: dict[str, Any] | None,
) -> dict[str, Any]:
    invoice_map = invoice or {}
    tax_map = tax_result or {}
    ai_map = ai_data or {}
    return {
        "invoice": {
            "invoice_id": int(invoice_id),
            "reference_no": _safe_text(invoice_map.get("reference_no")),
            "invoice_number": _safe_text(invoice_map.get("invoice_number")),
            "amount": _safe_text(invoice_map.get("amount")),
            "date": _safe_text(invoice_map.get("date")),
            "seller_name": _safe_text(invoice_map.get("seller_name")),
            "buyer_name": _safe_text(invoice_map.get("buyer_name")),
            "department": _safe_text(invoice_map.get("department")),
        },
        "rule_hits": {
            "tax_ok": bool(tax_map.get("ok")),
            "tax_status": _safe_text(tax_map.get("status")).lower(),
            "tax_message": _safe_text(tax_map.get("message")),
            "provider": _safe_text(tax_map.get("provider")),
            "evidence": ai_map.get("evidence") if isinstance(ai_map.get("evidence"), list) else [],
        },
        "risk_factors": {
            "risk_level": _safe_text(ai_map.get("risk_level")).upper(),
            "risk_score": _safe_int(ai_map.get("risk_score"), 0),
            "summary": _safe_text(ai_map.get("summary")),
            "model": _safe_text(ai_map.get("model")),
        },
    }


def _row_to_ledger(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    item = dict(row)
    item["id"] = _safe_int(item.get("id"))
    item["invoice_id"] = _safe_int(item.get("invoice_id"))
    item["risk_score"] = _safe_int(item.get("risk_score"))
    item["input_json"] = _json_loads(item.get("input_json"))
    item["output_json"] = _json_loads(item.get("output_json"))
    return item


def _get_last_hash(conn) -> str:
    row = conn.execute(
        "SELECT hash_curr FROM ai_prompt_ledger ORDER BY id DESC LIMIT 1",
    ).fetchone()
    if not row:
        return GENESIS_HASH
    return _safe_text(row["hash_curr"], GENESIS_HASH)


def record_ai_prompt_ledger(
    *,
    invoice_id: int,
    invoice: dict[str, Any] | None,
    tax_result: dict[str, Any] | None,
    ai_data: dict[str, Any] | None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    provider: str = "",
) -> dict[str, Any]:
    payload = ai_data or {}
    trace_id = _safe_text(payload.get("trace_id"))
    if not trace_id:
        raise ValueError("trace_id is required for prompt ledger")

    provider_value = (
        _safe_text(provider)
        or _safe_text((tax_result or {}).get("provider"))
        or _safe_text(payload.get("model"))
        or "unknown"
    )
    prompt_version_value = _safe_text(prompt_version, DEFAULT_PROMPT_VERSION)

    input_payload = _build_input_payload(
        invoice_id=invoice_id,
        invoice=invoice,
        tax_result=tax_result,
        ai_data=payload,
    )
    output_payload = dict(payload)

    input_json_text = _json_dumps(input_payload)
    output_json_text = _json_dumps(output_payload)

    with get_conn() as conn:
        existing = conn.execute(
            """
            SELECT id, trace_id, invoice_id, risk_level, risk_score, prompt_version, provider,
                   input_json, output_json, hash_prev, hash_curr, created_at
            FROM ai_prompt_ledger
            WHERE trace_id = ?
            LIMIT 1
            """,
            (trace_id,),
        ).fetchone()
        if existing:
            return _row_to_ledger(existing)

        hash_prev = _get_last_hash(conn)
        hash_curr = _build_hash(
            hash_prev=hash_prev,
            input_json=input_json_text,
            output_json=output_json_text,
            prompt_version=prompt_version_value,
            provider=provider_value,
        )
        created_at = _now_text()

        try:
            cur = conn.execute(
                """
                INSERT INTO ai_prompt_ledger (
                    trace_id, invoice_id, risk_level, risk_score,
                    prompt_version, provider, input_json, output_json,
                    hash_prev, hash_curr, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    int(invoice_id),
                    _safe_text(payload.get("risk_level")).upper(),
                    _safe_int(payload.get("risk_score"), 0),
                    prompt_version_value,
                    provider_value,
                    input_json_text,
                    output_json_text,
                    hash_prev,
                    hash_curr,
                    created_at,
                ),
            )
            ledger_id = int(cur.lastrowid)
            row = conn.execute(
                """
                SELECT id, trace_id, invoice_id, risk_level, risk_score, prompt_version, provider,
                       input_json, output_json, hash_prev, hash_curr, created_at
                FROM ai_prompt_ledger
                WHERE id = ?
                LIMIT 1
                """,
                (ledger_id,),
            ).fetchone()
            conn.commit()
            return _row_to_ledger(row)
        except sqlite3.IntegrityError:
            row = conn.execute(
                """
                SELECT id, trace_id, invoice_id, risk_level, risk_score, prompt_version, provider,
                       input_json, output_json, hash_prev, hash_curr, created_at
                FROM ai_prompt_ledger
                WHERE trace_id = ?
                LIMIT 1
                """,
                (trace_id,),
            ).fetchone()
            conn.commit()
            return _row_to_ledger(row)


def get_prompt_ledger_by_trace_id(trace_id: str, department_scope: str | None = None) -> dict[str, Any] | None:
    normalized = _safe_text(trace_id)
    if not normalized:
        return None
    scoped_department = _safe_text(department_scope)

    with get_conn() as conn:
        if scoped_department:
            row = conn.execute(
                """
                SELECT l.id, l.trace_id, l.invoice_id, l.risk_level, l.risk_score, l.prompt_version, l.provider,
                       l.input_json, l.output_json, l.hash_prev, l.hash_curr, l.created_at
                FROM ai_prompt_ledger l
                JOIN invoices i ON i.id = l.invoice_id
                WHERE l.trace_id = ? AND i.department = ?
                LIMIT 1
                """,
                (normalized, scoped_department),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, trace_id, invoice_id, risk_level, risk_score, prompt_version, provider,
                       input_json, output_json, hash_prev, hash_curr, created_at
                FROM ai_prompt_ledger
                WHERE trace_id = ?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
    if not row:
        return None
    return _row_to_ledger(row)
