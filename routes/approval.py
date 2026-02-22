from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from services.approval_service import actor_id, list_approval_rows, summary
from utils.security import (
    approval_allowed_workflow_roles,
    can_access_approval_console,
    apply_data_scope_filter,
    current_user,
    login_required,
)

bp = Blueprint("approval_pages", __name__)

APPROVAL_TEMPLATE = "approval/approval_center.html"
APPROVAL_API_VERSION = "APPROVAL_API_V2"


def _safe_text(value, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _scope_approval_rows(rows: list[dict], user: dict) -> list[dict]:
    allowed_roles = approval_allowed_workflow_roles(user)
    if not allowed_roles:
        return []
    return [
        row
        for row in rows
        if _safe_text(row.get("workflow_required_role")).upper() in allowed_roles
    ]


def _forbidden_page(*, module_name: str, required_permissions: list[str]):
    return (
        render_template(
            "forbidden.html",
            module_name=module_name,
            required_permissions=required_permissions,
        ),
        403,
    )


def _apply_focus_filter(rows: list[dict]) -> tuple[list[dict], dict]:
    raw_invoice_id = _safe_text(request.args.get("invoice_id"))
    filter_invoice_id = _safe_int(raw_invoice_id, 0) if raw_invoice_id else 0
    filter_reference = _safe_text(request.args.get("ref"))

    filtered_rows = rows
    filter_by_id = False

    if filter_invoice_id > 0:
        filter_by_id = True
        filtered_rows = [
            row for row in rows if _safe_int((row or {}).get("id"), 0) == filter_invoice_id
        ]
    elif filter_reference:
        filter_by_id = True
        filtered_rows = [
            row
            for row in rows
            if _safe_text((row or {}).get("reference_no") or (row or {}).get("id")) == filter_reference
        ]

    return filtered_rows, {
        "filter_by_id": filter_by_id,
        "filter_invoice_id": filter_invoice_id if filter_invoice_id > 0 else None,
        "filter_reference": filter_reference,
    }


@bp.get("/approval_center")
@login_required
def approval_center_page():
    user = current_user() or {}
    if not can_access_approval_console(user):
        return _forbidden_page(module_name="审批管理", required_permissions=[])

    current_app.logger.info(
        "HIT /approval_center route",
        extra={"route": "approval_center_page", "template": APPROVAL_TEMPLATE},
    )
    scope_filter = apply_data_scope_filter(user=user)
    rows = list_approval_rows(
        limit=2000,
        data_scope=scope_filter,
        row_cleaner=current_app.config.get("CLEAN_INVOICE_ROWS"),
    )
    rows = _scope_approval_rows(rows, user)
    rows, focus_meta = _apply_focus_filter(rows)
    return render_template(
        APPROVAL_TEMPLATE,
        invoices=rows,
        approval_summary=summary(rows),
        approval_actor_id=actor_id(user),
        filter_by_id=focus_meta["filter_by_id"],
        filter_invoice_id=focus_meta["filter_invoice_id"],
        filter_reference=focus_meta["filter_reference"],
        page_debug={
            "route": "/approval_center",
            "template": APPROVAL_TEMPLATE,
            "api_version": APPROVAL_API_VERSION,
        },
    )


@bp.get("/audit_workbench")
@login_required
def audit_workbench_page():
    user = current_user() or {}
    if not can_access_approval_console(user):
        return _forbidden_page(module_name="审批管理", required_permissions=[])

    current_app.logger.info(
        "HIT /audit_workbench route",
        extra={"route": "audit_workbench_page", "template": APPROVAL_TEMPLATE},
    )
    scope_filter = apply_data_scope_filter(user=user)
    rows = list_approval_rows(
        limit=2000,
        data_scope=scope_filter,
        row_cleaner=current_app.config.get("CLEAN_INVOICE_ROWS"),
    )
    rows = _scope_approval_rows(rows, user)
    rows, focus_meta = _apply_focus_filter(rows)
    return render_template(
        APPROVAL_TEMPLATE,
        invoices=rows,
        approval_summary=summary(rows),
        approval_actor_id=actor_id(user),
        filter_by_id=focus_meta["filter_by_id"],
        filter_invoice_id=focus_meta["filter_invoice_id"],
        filter_reference=focus_meta["filter_reference"],
        page_debug={
            "route": "/audit_workbench",
            "template": APPROVAL_TEMPLATE,
            "api_version": APPROVAL_API_VERSION,
        },
    )
