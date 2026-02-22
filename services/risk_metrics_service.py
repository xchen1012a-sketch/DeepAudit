from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from utils.db import get_conn, list_invoices

logger = logging.getLogger(__name__)

RISK_LEVELS = {"HIGH", "MEDIUM", "LOW"}
CLOSED_CASE_STATUSES = {"CLOSED", "DONE"}
RISK_SCORE_FALLBACK = {"HIGH": 90.0, "MEDIUM": 70.0, "LOW": 40.0}
MAX_METRICS_ROWS = 200000
QUERY_CHUNK_SIZE = 500


def _default_risk_metrics() -> dict[str, Any]:
    return {
        "total_txn": 0,
        "total_invoice": 0,
        "risk_event_count": 0,
        "risk_case_count": 0,
        "high_risk_case_count": 0,
        "closed_case_count": 0,
        "close_rate": 0.0,
        "risk_exposure_amount": 0.0,
        "avg_risk_score": 0.0,
        "ai_trigger_rate": 0.0,
    }


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _parse_amount(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _safe_text(value).replace(",", "")
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.\-]", "", text)
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def _round_float(value: float, ndigits: int = 2) -> float:
    return round(float(value), ndigits)


def _build_invoice_filters(date_from: date | None, date_to: date | None) -> dict[str, Any]:
    if date_from is None or date_to is None:
        return {}
    return {
        "ledger_date_start": date_from.isoformat(),
        "ledger_date_end": date_to.isoformat(),
    }


def _list_scoped_ledger_invoices(
    *,
    department_scope: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    data_scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    filters = _build_invoice_filters(date_from, date_to)
    return list_invoices(
        limit=MAX_METRICS_ROWS,
        fetch_limit=MAX_METRICS_ROWS,
        department=_safe_text(department_scope) or None,
        record_state="LEDGER",
        filters=filters,
        data_scope=data_scope,
    )


def _normalize_approval_status(row: dict[str, Any]) -> str:
    status = _safe_text(row.get("approval_status") or row.get("status"), "PENDING").upper()
    return status or "PENDING"


def _effective_risk_level(row: dict[str, Any]) -> str:
    for key in ("risk_level", "ai_risk_level"):
        level = _safe_text(row.get(key)).upper()
        if level in RISK_LEVELS:
            return level
    return "LOW"


def _effective_risk_score(row: dict[str, Any], risk_level: str) -> float:
    score = _safe_float(row.get("risk_score"), -1.0)
    if score >= 0:
        return score
    return RISK_SCORE_FALLBACK.get(risk_level, 0.0)


def _is_ai_triggered(row: dict[str, Any]) -> bool:
    ai_level = _safe_text(row.get("ai_risk_level")).upper()
    if ai_level in RISK_LEVELS:
        return True
    if _safe_text(row.get("ai_trace_id")):
        return True
    if _safe_text(row.get("ai_analysis_reason")):
        return True
    return False


def _row_day_key(row: dict[str, Any]) -> str:
    for field in ("created_at", "invoice_date"):
        raw = _safe_text(row.get(field))
        if len(raw) < 10:
            continue
        day_text = raw[:10]
        try:
            datetime.strptime(day_text, "%Y-%m-%d")
            return day_text
        except Exception:
            continue
    return ""


def _safe_day_text(value: Any) -> str:
    raw = _safe_text(value)
    if len(raw) < 10:
        return ""
    day_text = raw[:10]
    try:
        datetime.strptime(day_text, "%Y-%m-%d")
        return day_text
    except Exception:
        return ""


def _chunked(values: list[int], size: int = QUERY_CHUNK_SIZE):
    if size <= 0:
        size = QUERY_CHUNK_SIZE
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _collect_invoice_context(rows: list[dict[str, Any]]) -> tuple[list[int], dict[int, dict[str, Any]]]:
    invoice_ids: list[int] = []
    invoice_map: dict[int, dict[str, Any]] = {}
    for row in rows:
        row_map = dict(row)
        invoice_id = _safe_int(row_map.get("id"), 0)
        if invoice_id <= 0:
            continue
        if invoice_id in invoice_map:
            continue
        invoice_map[invoice_id] = row_map
        invoice_ids.append(invoice_id)
    return invoice_ids, invoice_map


def _fetch_risk_event_rows(
    invoice_ids: list[int],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    if not invoice_ids:
        return []

    has_window = date_from is not None and date_to is not None
    rows: list[dict[str, Any]] = []
    with get_conn() as conn:
        for chunk in _chunked(invoice_ids):
            placeholders = ",".join(["?"] * len(chunk))
            sql = [
                f"""
                SELECT
                    re.id,
                    re.invoice_id,
                    UPPER(COALESCE(re.risk_level, '')) AS risk_level,
                    COALESCE(re.risk_score, 0) AS risk_score,
                    re.created_at
                FROM risk_events re
                WHERE re.invoice_id IN ({placeholders})
                """
            ]
            params: list[Any] = list(chunk)
            if has_window:
                sql.append("AND DATE(COALESCE(re.created_at, '')) BETWEEN ? AND ?")
                params.extend([date_from.isoformat(), date_to.isoformat()])
            fetched = conn.execute("\n".join(sql), tuple(params)).fetchall()
            rows.extend(dict(item) for item in fetched)
    return rows


def _fetch_risk_case_rows(
    invoice_ids: list[int],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    if not invoice_ids:
        return []

    has_window = date_from is not None and date_to is not None
    rows: list[dict[str, Any]] = []
    with get_conn() as conn:
        for chunk in _chunked(invoice_ids):
            placeholders = ",".join(["?"] * len(chunk))
            sql = [
                f"""
                SELECT
                    c.id,
                    c.event_id,
                    UPPER(COALESCE(c.status, 'OPEN')) AS status,
                    c.created_at,
                    c.closed_at,
                    e.invoice_id,
                    UPPER(COALESCE(e.risk_level, '')) AS risk_level,
                    COALESCE(e.risk_score, 0) AS risk_score
                FROM risk_cases c
                JOIN risk_events e ON e.id = c.event_id
                WHERE e.invoice_id IN ({placeholders})
                """
            ]
            params: list[Any] = list(chunk)
            if has_window:
                sql.append("AND DATE(COALESCE(c.created_at, '')) BETWEEN ? AND ?")
                params.extend([date_from.isoformat(), date_to.isoformat()])
            fetched = conn.execute("\n".join(sql), tuple(params)).fetchall()
            rows.extend(dict(item) for item in fetched)
    return rows


def _latest_event_by_invoice(event_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in event_rows:
        invoice_id = _safe_int(row.get("invoice_id"), 0)
        if invoice_id <= 0:
            continue
        current = latest.get(invoice_id)
        if current is None or _safe_int(row.get("id"), 0) > _safe_int(current.get("id"), 0):
            latest[invoice_id] = row
    return latest


def _count_bank_transactions(invoice_ids: list[int]) -> int:
    if not invoice_ids:
        return 0
    unique_ids = sorted({int(item) for item in invoice_ids if int(item) > 0})
    if not unique_ids:
        return 0

    total = 0
    with get_conn() as conn:
        for chunk in _chunked(unique_ids):
            placeholders = ",".join(["?"] * len(chunk))
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM bank_transactions WHERE matched_invoice_id IN ({placeholders})",
                tuple(chunk),
            ).fetchone()
            if row:
                total += _safe_int(row["c"], 0)
    return total


def get_risk_metrics(
    *,
    department_scope: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    data_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        rows = _list_scoped_ledger_invoices(
            department_scope=department_scope,
            date_from=date_from,
            date_to=date_to,
            data_scope=data_scope,
        )
        total_invoice = len(rows)
        invoice_ids, invoice_map = _collect_invoice_context(rows)

        event_rows = _fetch_risk_event_rows(invoice_ids, date_from=date_from, date_to=date_to)
        case_rows = _fetch_risk_case_rows(invoice_ids, date_from=date_from, date_to=date_to)

        risk_event_count = len(event_rows)
        risk_case_count = len(case_rows)

        high_risk_case_count = 0
        closed_case_count = 0
        risk_score_sum = 0.0
        score_count = 0

        if case_rows:
            for case_row in case_rows:
                risk_level = _safe_text(case_row.get("risk_level")).upper()
                if risk_level == "HIGH":
                    high_risk_case_count += 1

                case_status = _safe_text(case_row.get("status")).upper()
                if case_status in CLOSED_CASE_STATUSES:
                    closed_case_count += 1

                risk_score_sum += _safe_float(case_row.get("risk_score"), 0.0)
                score_count += 1
        elif event_rows:
            for event_row in event_rows:
                risk_score_sum += _safe_float(event_row.get("risk_score"), 0.0)
                score_count += 1
        else:
            for row in rows:
                row_map = dict(row)
                risk_level = _effective_risk_level(row_map)
                risk_score_sum += _effective_risk_score(row_map, risk_level)
                score_count += 1

        if risk_event_count <= 0:
            risk_event_count = sum(
                1
                for row in rows
                if _effective_risk_level(dict(row)) in {"HIGH", "MEDIUM"}
            )

        ai_triggered_invoice_count = sum(1 for row in rows if _is_ai_triggered(dict(row)))

        exposure_invoice_ids: set[int] = set()
        if case_rows:
            for case_row in case_rows:
                case_status = _safe_text(case_row.get("status")).upper()
                if case_status in CLOSED_CASE_STATUSES:
                    continue
                risk_level = _safe_text(case_row.get("risk_level")).upper()
                if risk_level not in {"HIGH", "MEDIUM"}:
                    continue
                invoice_id = _safe_int(case_row.get("invoice_id"), 0)
                if invoice_id > 0:
                    exposure_invoice_ids.add(invoice_id)
        elif event_rows:
            for event_row in event_rows:
                risk_level = _safe_text(event_row.get("risk_level")).upper()
                if risk_level not in {"HIGH", "MEDIUM"}:
                    continue
                invoice_id = _safe_int(event_row.get("invoice_id"), 0)
                if invoice_id > 0:
                    exposure_invoice_ids.add(invoice_id)
        else:
            for row in rows:
                row_map = dict(row)
                if _effective_risk_level(row_map) in {"HIGH", "MEDIUM"}:
                    invoice_id = _safe_int(row_map.get("id"), 0)
                    if invoice_id > 0:
                        exposure_invoice_ids.add(invoice_id)

        risk_exposure_amount = 0.0
        for invoice_id in exposure_invoice_ids:
            invoice_row = invoice_map.get(invoice_id)
            if not invoice_row:
                continue
            if _normalize_approval_status(invoice_row) != "PENDING":
                continue
            risk_exposure_amount += _parse_amount(invoice_row.get("amount"))

        total_txn = _count_bank_transactions(invoice_ids)
        close_rate = _round_float((closed_case_count / risk_case_count) if risk_case_count > 0 else 0.0, 4)
        ai_trigger_rate = _round_float((ai_triggered_invoice_count / total_invoice) if total_invoice > 0 else 0.0, 4)
        avg_risk_score = _round_float((risk_score_sum / score_count) if score_count > 0 else 0.0, 2)

        return {
            "total_txn": int(total_txn),
            "total_invoice": int(total_invoice),
            "risk_event_count": int(risk_event_count),
            "risk_case_count": int(risk_case_count),
            "high_risk_case_count": int(high_risk_case_count),
            "closed_case_count": int(closed_case_count),
            "close_rate": close_rate,
            "risk_exposure_amount": _round_float(risk_exposure_amount, 2),
            "avg_risk_score": avg_risk_score,
            "ai_trigger_rate": ai_trigger_rate,
        }
    except Exception as exc:
        logger.exception("get_risk_metrics failed: %s", exc)
        return _default_risk_metrics()


def get_risk_distribution(
    *,
    department_scope: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    data_scope: dict[str, Any] | None = None,
) -> dict[str, int]:
    try:
        rows = _list_scoped_ledger_invoices(
            department_scope=department_scope,
            date_from=date_from,
            date_to=date_to,
            data_scope=data_scope,
        )
        invoice_ids, invoice_map = _collect_invoice_context(rows)
        event_rows = _fetch_risk_event_rows(invoice_ids)
    except Exception as exc:
        logger.exception("get_risk_distribution failed: %s", exc)
        return {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    data = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    if event_rows:
        latest_map = _latest_event_by_invoice(event_rows)
        for invoice_id, invoice_row in invoice_map.items():
            latest_event = latest_map.get(invoice_id)
            if latest_event:
                level = _safe_text(latest_event.get("risk_level")).upper()
            else:
                level = _effective_risk_level(invoice_row)
            if level not in data:
                level = "LOW"
            data[level] += 1
        return data

    for row in rows:
        level = _effective_risk_level(dict(row))
        if level in data:
            data[level] += 1
    return data


def _default_trends(days: int = 7, end_date: date | None = None) -> dict[str, Any]:
    end_day = end_date if end_date is not None else date.today()
    start_day = end_day - timedelta(days=days - 1)
    labels = []
    day_cursor = start_day
    while day_cursor <= end_day:
        labels.append(day_cursor.isoformat())
        day_cursor += timedelta(days=1)
    return {
        "days": days,
        "labels": labels,
        "risk_event_trend": [0] * len(labels),
        "risk_case_trend": [0] * len(labels),
    }


def get_recent_trends(
    *,
    days: int = 7,
    end_date: date | None = None,
    department_scope: str | None = None,
    data_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return _get_recent_trends_impl(
            days=days,
            end_date=end_date,
            department_scope=department_scope,
            data_scope=data_scope,
        )
    except Exception as exc:
        logger.exception("get_recent_trends failed: %s", exc)
        return _default_trends(days=days, end_date=end_date)


def _get_recent_trends_impl(
    *,
    days: int = 7,
    end_date: date | None = None,
    department_scope: str | None = None,
    data_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    window_days = max(1, int(days))
    end_day = end_date if end_date is not None else date.today()
    start_day = end_day - timedelta(days=window_days - 1)

    labels = []
    risk_events_map: dict[str, int] = {}
    risk_cases_map: dict[str, int] = {}

    day_cursor = start_day
    while day_cursor <= end_day:
        key = day_cursor.isoformat()
        labels.append(key)
        risk_events_map[key] = 0
        risk_cases_map[key] = 0
        day_cursor += timedelta(days=1)

    rows = _list_scoped_ledger_invoices(
        department_scope=department_scope,
        date_from=start_day,
        date_to=end_day,
        data_scope=data_scope,
    )
    invoice_ids, _ = _collect_invoice_context(rows)

    event_rows = _fetch_risk_event_rows(invoice_ids, date_from=start_day, date_to=end_day)
    case_rows = _fetch_risk_case_rows(invoice_ids, date_from=start_day, date_to=end_day)

    for row in event_rows:
        day_text = _safe_day_text(row.get("created_at"))
        if day_text in risk_events_map:
            risk_events_map[day_text] += 1

    for row in case_rows:
        day_text = _safe_day_text(row.get("created_at"))
        if day_text in risk_cases_map:
            risk_cases_map[day_text] += 1

    if sum(risk_events_map.values()) <= 0 and sum(risk_cases_map.values()) <= 0:
        for row in rows:
            row_map = dict(row)
            day_text = _row_day_key(row_map)
            if day_text not in risk_events_map:
                continue
            if _effective_risk_level(row_map) in {"HIGH", "MEDIUM"}:
                risk_events_map[day_text] += 1

    return {
        "days": window_days,
        "labels": labels,
        "risk_event_trend": [risk_events_map[label] for label in labels],
        "risk_case_trend": [risk_cases_map[label] for label in labels],
    }


def get_department_risk_rank(
    *,
    limit: int = 10,
    data_scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 100))
    rows = _list_scoped_ledger_invoices(
        department_scope=None,
        date_from=None,
        date_to=None,
        data_scope=data_scope,
    )
    invoice_ids, invoice_map = _collect_invoice_context(rows)
    case_rows = _fetch_risk_case_rows(invoice_ids)

    counts: dict[str, int] = {}
    for row in case_rows:
        risk_level = _safe_text(row.get("risk_level")).upper()
        if risk_level not in {"HIGH", "MEDIUM"}:
            continue
        invoice_id = _safe_int(row.get("invoice_id"), 0)
        invoice = invoice_map.get(invoice_id) or {}
        department = _safe_text(invoice.get("department"), "-")
        counts[department] = counts.get(department, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:normalized_limit]
    return [{"department": name, "risk_case_count": int(count)} for name, count in ranked]
