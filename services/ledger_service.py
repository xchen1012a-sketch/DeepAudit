from __future__ import annotations

from typing import Any

from utils.db import list_invoices, summarize_ledger_stats


ALLOWED_LEDGER_TABS = {"ledger", "draft"}
PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 200]
DEFAULT_EXPENSE_CATEGORIES = [
    "住宿",
    "差旅交通",
    "餐饮",
    "办公采购",
    "通讯",
    "通讯网络",
    "会议会务",
    "培训学习",
    "业务招待",
    "市场营销",
    "车辆使用",
    "软件服务",
    "设备维护",
    "物业水电",
    "税费缴纳",
    "福利补贴",
    "员工福利",
    "快递物流",
    "会展活动",
    "其他",
]


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_limit(raw: Any, default: int = 20, max_limit: int = 5000) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    if value <= 0:
        value = default
    return min(value, max_limit)


def normalize_tab(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return "draft" if raw == "draft" else "ledger"


def tab_to_record_state(tab: str) -> str:
    return "DRAFT" if (str(tab or "").strip().lower() == "draft") else "LEDGER"


def _resolve_expense_categories(dynamic_categories: list[str] | None) -> list[str]:
    dynamic = [item for item in (dynamic_categories or []) if _safe_text(item)]
    if not dynamic:
        return list(DEFAULT_EXPENSE_CATEGORIES)
    ordered = list(DEFAULT_EXPENSE_CATEGORIES)
    for item in dynamic:
        if item not in ordered:
            ordered.append(item)
    return ordered


def load_ledger_page_context(
    *,
    tab: Any,
    limit: Any,
    department_scope: str | None = None,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
    data_scope: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_tab = normalize_tab(tab)
    active_state = tab_to_record_state(normalized_tab)
    page_limit = _safe_limit(limit, default=20, max_limit=5000)

    filters = filters or {}

    stats = summarize_ledger_stats(
        department=department_scope,
        filters=filters,
        max_rows=10000,
        owner_user_id=owner_user_id,
        owner_identity_values=owner_identity_values,
        data_scope=data_scope,
        record_state=active_state,
    )

    rows = list_invoices(
        limit=page_limit,
        department=department_scope,
        record_state=active_state,
        filters=filters,
        fetch_limit=max(page_limit, 5000),
        owner_user_id=owner_user_id,
        owner_identity_values=owner_identity_values,
        data_scope=data_scope,
    )

    total_count = stats.get("total_count", 0)
    return {
        "rows": rows,
        "active_tab": normalized_tab,
        "active_state": active_state,
        "page_limit": page_limit,
        "page_size_options": PAGE_SIZE_OPTIONS,
        "ledger_count": total_count if active_state == "LEDGER" else 0,
        "draft_count": total_count if active_state == "DRAFT" else 0,
        "kpi": {
            "total_count": stats.get("total_count", 0),
            "total_amount": stats.get("total_amount", 0.0),
            "abnormal_count": stats.get("abnormal_count", 0),
            "unverified_count": stats.get("unverified_count", 0),
        },
        "filters": filters,
        "filter_options": {
            "expense_categories": _resolve_expense_categories(stats.get("expense_categories")),
            "risk_levels": ["LOW", "MEDIUM", "HIGH"],
            "verify_status": ["PASS", "FAIL", "PENDING"],
        },
    }
