from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from services.risk_service import (
    RISK_LEVEL_FILTER_OPTIONS,
    STATUS_FILTER_OPTIONS,
    load_risk_center_filter_options,
    load_risk_center_kpis,
    load_risk_center_rows,
    normalize_filter_value,
    safe_limit,
)
from utils.security import current_scope_department, current_user, has_permission, login_required

bp = Blueprint("risk_pages", __name__)

RISK_TEMPLATE = "risk/risk_center.html"
RISK_API_VERSION = "RISK_API_V2"


def _safe_text(value, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _has_any_permission(permission_keys: list[str]) -> bool:
    user = current_user() or {}
    for key in permission_keys:
        if has_permission(str(key), user=user):
            return True
    return False


def _forbidden_page(*, module_name: str, required_permissions: list[str]):
    return (
        render_template(
            "forbidden.html",
            module_name=module_name,
            required_permissions=required_permissions,
        ),
        403,
    )


@bp.get("/risk-center")
@login_required
def risk_center_page():
    current_app.logger.info(
        "HIT /risk-center route",
        extra={"route": "risk_center_page", "template": RISK_TEMPLATE},
    )

    required_permissions = ["CREATE_CASE", "ASSIGN_CASE", "CLOSE_CASE"]
    if not _has_any_permission(required_permissions):
        return _forbidden_page(module_name="风险中心", required_permissions=required_permissions)

    risk_level = normalize_filter_value(request.args.get("risk_level"), RISK_LEVEL_FILTER_OPTIONS)
    status = normalize_filter_value(request.args.get("status"), STATUS_FILTER_OPTIONS)
    department_filter = _safe_text(request.args.get("department"))
    owner_filter = _safe_text(request.args.get("owner"))

    options = load_risk_center_filter_options(department_scope=current_scope_department())
    if department_filter and department_filter not in options["departments"]:
        department_filter = ""

    kpis = load_risk_center_kpis(department_scope=current_scope_department())
    rows = load_risk_center_rows(
        limit=safe_limit(request.args.get("limit"), default=300, max_limit=2000),
        department_scope=current_scope_department(),
        risk_level=risk_level,
        status=status,
        department=department_filter,
        owner=owner_filter,
    )

    return render_template(
        RISK_TEMPLATE,
        rows=rows,
        row_count=len(rows),
        kpis=kpis,
        filter_hint="默认展示中高风险或未结案案件，按最近更新时间倒序。",
        filter_state={
            "risk_level": risk_level,
            "status": status,
            "department": department_filter,
            "owner": owner_filter,
        },
        department_options=options["departments"],
        assign_to_options=options.get("assignees", []),
        page_debug={
            "route": "/risk-center",
            "template": RISK_TEMPLATE,
            "api_version": RISK_API_VERSION,
        },
    )
