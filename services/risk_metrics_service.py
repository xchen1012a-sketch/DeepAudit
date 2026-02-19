from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from utils.db import get_conn

logger = logging.getLogger(__name__)


def _default_risk_metrics() -> dict[str, Any]:
    """指标查询失败时返回的默认结构，保证前端不报错。"""
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


def _count_sql(conn, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0
    return _safe_int(row["c"], 0)


def _avg_sql(conn, query: str, params: tuple[Any, ...] = ()) -> float:
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0.0
    return _safe_float(row["v"], 0.0)


def _date_filter_snippet(date_from: date | None, date_to: date | None) -> tuple[str, tuple[str, ...]]:
    """Returns (sql_snippet, params) for DATE(i.created_at) window. Empty when both None."""
    if date_from is None or date_to is None:
        return "", ()
    return " AND DATE(i.created_at) >= ? AND DATE(i.created_at) <= ?", (date_from.isoformat(), date_to.isoformat())


def get_risk_metrics(
    *,
    department_scope: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    scoped_department = _safe_text(department_scope)
    date_snippet, date_params = _date_filter_snippet(date_from, date_to)
    try:
        return _get_risk_metrics_impl(
            scoped_department=scoped_department,
            date_snippet=date_snippet,
            date_params=date_params,
        )
    except Exception as e:
        logger.exception("get_risk_metrics failed: %s", e)
        return _default_risk_metrics()


def _get_risk_metrics_impl(
    *,
    scoped_department: str,
    date_snippet: str,
    date_params: tuple[Any, ...],
) -> dict[str, Any]:
    with get_conn() as conn:
        if scoped_department:
            total_txn = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM bank_transactions bt
                JOIN invoices i ON i.id = bt.matched_invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            total_invoice = _count_sql(
                conn,
                "SELECT COUNT(*) AS c FROM invoices i WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'"
                + date_snippet,
                (scoped_department,) + date_params,
            )
            risk_event_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            risk_case_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            high_risk_case_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER' AND UPPER(COALESCE(re.risk_level, '')) = 'HIGH'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            closed_case_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER' AND UPPER(COALESCE(rc.status, '')) = 'CLOSED'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            avg_risk_score = _avg_sql(
                conn,
                """
                SELECT AVG(COALESCE(re.risk_score, 0)) AS v
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            ai_triggered_invoice_count = _count_sql(
                conn,
                """
                SELECT COUNT(DISTINCT l.invoice_id) AS c
                FROM ai_prompt_ledger l
                JOIN invoices i ON i.id = l.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                (scoped_department,) + date_params,
            )
            exposure_rows = conn.execute(
                """
                SELECT i.amount
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ? AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER' AND UPPER(COALESCE(rc.status, '')) IN ('OPEN', 'ASSIGNED')
                """ + date_snippet,
                (scoped_department,) + date_params,
            ).fetchall()
        else:
            total_txn = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM bank_transactions bt
                JOIN invoices i ON i.id = bt.matched_invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                date_params,
            )
            total_invoice = _count_sql(
                conn,
                "SELECT COUNT(*) AS c FROM invoices i WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'" + date_snippet,
                date_params,
            )
            risk_event_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                date_params,
            )
            risk_case_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                date_params,
            )
            high_risk_case_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND UPPER(COALESCE(re.risk_level, '')) = 'HIGH'
                """ + date_snippet,
                date_params,
            )
            closed_case_count = _count_sql(
                conn,
                """
                SELECT COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND UPPER(COALESCE(rc.status, '')) = 'CLOSED'
                """ + date_snippet,
                date_params,
            )
            avg_risk_score = _avg_sql(
                conn,
                """
                SELECT AVG(COALESCE(re.risk_score, 0)) AS v
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                date_params,
            )
            ai_triggered_invoice_count = _count_sql(
                conn,
                """
                SELECT COUNT(DISTINCT l.invoice_id) AS c
                FROM ai_prompt_ledger l
                JOIN invoices i ON i.id = l.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet,
                date_params,
            )
            exposure_rows = conn.execute(
                """
                SELECT i.amount
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND UPPER(COALESCE(rc.status, '')) IN ('OPEN', 'ASSIGNED')
                """ + date_snippet,
                date_params,
            ).fetchall()

    risk_exposure_amount = _round_float(sum(_parse_amount(row["amount"]) for row in exposure_rows), 2)
    close_rate = _round_float((closed_case_count / risk_case_count) if risk_case_count > 0 else 0.0, 4)
    ai_trigger_rate = _round_float((ai_triggered_invoice_count / total_invoice) if total_invoice > 0 else 0.0, 4)

    return {
        "total_txn": int(total_txn),
        "total_invoice": int(total_invoice),
        "risk_event_count": int(risk_event_count),
        "risk_case_count": int(risk_case_count),
        "high_risk_case_count": int(high_risk_case_count),
        "closed_case_count": int(closed_case_count),
        "close_rate": close_rate,
        "risk_exposure_amount": risk_exposure_amount,
        "avg_risk_score": _round_float(avg_risk_score, 2),
        "ai_trigger_rate": ai_trigger_rate,
    }


def get_risk_distribution(
    *,
    department_scope: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, int]:
    try:
        return _get_risk_distribution_impl(
            department_scope=department_scope,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as e:
        logger.exception("get_risk_distribution failed: %s", e)
        return {"HIGH": 0, "MEDIUM": 0, "LOW": 0}


def _get_risk_distribution_impl(
    *,
    department_scope: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, int]:
    scoped_department = _safe_text(department_scope)
    date_snippet, date_params = _date_filter_snippet(date_from, date_to)
    data = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    with get_conn() as conn:
        if scoped_department:
            rows = conn.execute(
                """
                SELECT UPPER(COALESCE(re.risk_level, '')) AS risk_level, COUNT(*) AS c
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ?
                  AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet + """
                GROUP BY UPPER(COALESCE(re.risk_level, ''))
                """,
                (scoped_department,) + date_params,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT UPPER(COALESCE(re.risk_level, '')) AS risk_level, COUNT(*) AS c
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                """ + date_snippet + """
                GROUP BY UPPER(COALESCE(re.risk_level, ''))
                """,
                date_params,
            ).fetchall()

    for row in rows:
        key = _safe_text(row["risk_level"]).upper()
        if key in data:
            data[key] = _safe_int(row["c"], 0)
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
) -> dict[str, Any]:
    try:
        return _get_recent_trends_impl(
            days=days,
            end_date=end_date,
            department_scope=department_scope,
        )
    except Exception as e:
        logger.exception("get_recent_trends failed: %s", e)
        return _default_trends(days=days, end_date=end_date)


def _get_recent_trends_impl(
    *,
    days: int = 7,
    end_date: date | None = None,
    department_scope: str | None = None,
) -> dict[str, Any]:
    window_days = max(1, int(days))
    scoped_department = _safe_text(department_scope)
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

    with get_conn() as conn:
        if scoped_department:
            risk_event_rows = conn.execute(
                """
                SELECT DATE(re.created_at) AS d, COUNT(*) AS c
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ?
                  AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND DATE(re.created_at) >= ? AND DATE(re.created_at) <= ?
                GROUP BY DATE(re.created_at)
                """,
                (scoped_department, start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
            risk_case_rows = conn.execute(
                """
                SELECT DATE(rc.created_at) AS d, COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE i.department = ?
                  AND UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND DATE(rc.created_at) >= ? AND DATE(rc.created_at) <= ?
                GROUP BY DATE(rc.created_at)
                """,
                (scoped_department, start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        else:
            risk_event_rows = conn.execute(
                """
                SELECT DATE(re.created_at) AS d, COUNT(*) AS c
                FROM risk_events re
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND DATE(re.created_at) >= ? AND DATE(re.created_at) <= ?
                GROUP BY DATE(re.created_at)
                """,
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
            risk_case_rows = conn.execute(
                """
                SELECT DATE(rc.created_at) AS d, COUNT(*) AS c
                FROM risk_cases rc
                JOIN risk_events re ON re.id = rc.event_id
                JOIN invoices i ON i.id = re.invoice_id
                WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
                  AND DATE(rc.created_at) >= ? AND DATE(rc.created_at) <= ?
                GROUP BY DATE(rc.created_at)
                """,
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()

    for row in risk_event_rows:
        day_text = _safe_text(row["d"])
        if day_text in risk_events_map:
            risk_events_map[day_text] = _safe_int(row["c"], 0)

    for row in risk_case_rows:
        day_text = _safe_text(row["d"])
        if day_text in risk_cases_map:
            risk_cases_map[day_text] = _safe_int(row["c"], 0)

    return {
        "days": window_days,
        "labels": labels,
        "risk_event_trend": [risk_events_map[label] for label in labels],
        "risk_case_trend": [risk_cases_map[label] for label in labels],
    }


def get_department_risk_rank(*, limit: int = 10) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 100))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.department AS department, COUNT(*) AS risk_case_count
            FROM risk_cases rc
            JOIN risk_events re ON re.id = rc.event_id
            JOIN invoices i ON i.id = re.invoice_id
            WHERE UPPER(COALESCE(i.record_state, 'DRAFT')) = 'LEDGER'
            GROUP BY i.department
            ORDER BY risk_case_count DESC, i.department ASC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "department": _safe_text(row["department"], "-"),
                "risk_case_count": _safe_int(row["risk_case_count"], 0),
            }
        )
    return result
