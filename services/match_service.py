from __future__ import annotations

from datetime import date, datetime
from typing import Any

from services.bank_service import update_transaction_match
from utils.db import list_invoices


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _safe_text(value).replace(",", "")
    if not text:
        return None
    cleaned = "".join(ch for ch in text if ch in "0123456789.-")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def _parse_date(value: Any) -> date | None:
    text = _safe_text(value)
    if not text:
        return None
    if len(text) >= 10:
        text = text[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _score_match(txn: dict[str, Any], invoice: dict[str, Any]) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []

    txn_amount = _to_float(txn.get("amount"))
    inv_amount = _to_float(invoice.get("amount"))
    if txn_amount is not None and inv_amount is not None:
        diff = abs(txn_amount - inv_amount)
        if diff <= 1:
            score += 60
            reasons.append(f"amount_diff<=1({diff:.2f})")

    memo = _safe_text(txn.get("memo")).lower()
    applicant = _safe_text(invoice.get("applicant")).lower()
    merchant = _safe_text(invoice.get("merchant_name")).lower()
    reference_no = _safe_text(invoice.get("reference_no")).lower()
    ref_tail = reference_no[-6:] if len(reference_no) >= 6 else reference_no

    keyword_hit = False
    for token in (applicant, merchant, reference_no, ref_tail):
        if token and token in memo:
            keyword_hit = True
            break
    if keyword_hit:
        score += 30
        reasons.append("memo_keyword_hit")

    txn_day = _parse_date(txn.get("ts"))
    inv_day = _parse_date(invoice.get("invoice_date"))
    if txn_day is not None and inv_day is not None:
        day_diff = abs((txn_day - inv_day).days)
        if day_diff <= 7:
            score += 10
            reasons.append(f"date_diff<=7({day_diff})")

    return score, ";".join(reasons) if reasons else "no_rule_hit"


def match_bank_to_invoices(txn_rows: list[dict[str, Any]]) -> dict[str, Any]:
    invoices = list_invoices(limit=5000)
    used_invoice_ids: set[int] = set()

    matched_pairs: list[dict[str, Any]] = []
    for txn in txn_rows or []:
        if not isinstance(txn, dict):
            continue

        txn_id = _safe_text(txn.get("txn_id"))
        if not txn_id:
            continue

        txn_day = _parse_date(txn.get("ts"))
        best_invoice: dict[str, Any] | None = None
        best_score = -1
        best_reason = ""

        for invoice in invoices:
            invoice_id_raw = invoice.get("id")
            try:
                invoice_id = int(invoice_id_raw)
            except Exception:
                continue
            if invoice_id in used_invoice_ids:
                continue

            inv_day = _parse_date(invoice.get("invoice_date"))
            if txn_day is not None and inv_day is not None:
                if abs((txn_day - inv_day).days) > 30:
                    continue

            score, reason = _score_match(txn, invoice)
            if score > best_score:
                best_score = score
                best_reason = reason
                best_invoice = invoice

        if best_invoice is None or best_score < 70:
            continue

        invoice_id = int(best_invoice["id"])
        used_invoice_ids.add(invoice_id)
        update_transaction_match(
            txn_id=txn_id,
            matched_invoice_id=invoice_id,
            score=float(best_score),
            reason=best_reason,
        )
        matched_pairs.append(
            {
                "txn_id": txn_id,
                "invoice_id": invoice_id,
                "score": best_score,
                "reason": best_reason,
            }
        )

    return {
        "matched_count": len(matched_pairs),
        "matched_pairs": matched_pairs[:10],
    }
