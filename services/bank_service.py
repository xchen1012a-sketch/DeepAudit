from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from utils.db import get_conn


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
    try:
        return float(text)
    except Exception:
        return None


def save_transactions(items: list[dict[str, Any]]) -> dict[str, Any]:
    saved_count = 0
    skipped_count = 0
    saved_all_txn_ids: list[str] = []
    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        for raw in items or []:
            if not isinstance(raw, dict):
                skipped_count += 1
                continue

            txn_id = _safe_text(raw.get("txn_id"))
            if not txn_id:
                skipped_count += 1
                continue

            amount = _to_float(raw.get("amount"))
            ts = _safe_text(raw.get("ts"))
            counterparty = _safe_text(raw.get("counterparty"))
            memo = _safe_text(raw.get("memo"))

            try:
                conn.execute(
                    """
                    INSERT INTO bank_transactions (
                        txn_id, ts, amount, counterparty, memo, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (txn_id, ts, amount, counterparty, memo, imported_at),
                )
                saved_count += 1
                saved_all_txn_ids.append(txn_id)
            except sqlite3.IntegrityError:
                skipped_count += 1
            except Exception:
                skipped_count += 1
        conn.commit()

    return {
        "saved_count": saved_count,
        "skipped_count": skipped_count,
        "saved_txn_ids": saved_all_txn_ids[:5],
        "saved_all_txn_ids": saved_all_txn_ids,
    }


def get_transactions_by_txn_ids(txn_ids: list[str]) -> list[dict[str, Any]]:
    normalized = [str(x).strip() for x in txn_ids if str(x).strip()]
    if not normalized:
        return []

    placeholders = ",".join(["?"] * len(normalized))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, txn_id, ts, amount, counterparty, memo, imported_at,
                   matched_invoice_id, match_score, match_reason
            FROM bank_transactions
            WHERE txn_id IN ({placeholders})
            ORDER BY id ASC
            """,
            tuple(normalized),
        ).fetchall()
    return [dict(r) for r in rows]


def update_transaction_match(
    txn_id: str,
    matched_invoice_id: int,
    score: float,
    reason: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE bank_transactions
            SET matched_invoice_id = ?, match_score = ?, match_reason = ?
            WHERE txn_id = ?
            """,
            (int(matched_invoice_id), float(score), str(reason), str(txn_id)),
        )
        conn.commit()


def get_bank_stats() -> dict[str, int]:
    with get_conn() as conn:
        total_row = conn.execute("SELECT COUNT(*) AS c FROM bank_transactions").fetchone()
        matched_row = conn.execute(
            "SELECT COUNT(*) AS c FROM bank_transactions WHERE matched_invoice_id IS NOT NULL"
        ).fetchone()

    total = int(total_row["c"]) if total_row else 0
    matched = int(matched_row["c"]) if matched_row else 0
    unmatched = max(0, total - matched)
    return {
        "total_txn": total,
        "matched_txn": matched,
        "unmatched_txn": unmatched,
    }
