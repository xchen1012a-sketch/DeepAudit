from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from services.ledger_service import load_ledger_page_context
from utils.db import get_invoice_detail, get_invoice_id_by_risk_case_id, insert_audit_log
from utils.security import (
    ROLE_KEY_CFO,
    ROLE_KEY_FIN_MANAGER,
    ROLE_KEY_FIN_STAFF,
    ROLE_KEY_FIN_SUPERVISOR,
    access_level,
    apply_data_scope_filter,
    current_user,
    current_user_role_keys,
    has_permission,
    is_system_admin,
    login_required,
)

bp = Blueprint("ledger", __name__)

LEDGER_TEMPLATE = "ledger/invoices_page.html"
LEDGER_API_VERSION = "LEDGER_API_V2"
SUPPLEMENT_ALLOWED_ROLE_KEYS = {
    ROLE_KEY_FIN_STAFF,
    ROLE_KEY_FIN_MANAGER,
    ROLE_KEY_FIN_SUPERVISOR,
    ROLE_KEY_CFO,
}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _client_ip() -> str:
    forwarded = _safe_text(request.headers.get("X-Forwarded-For"))
    if forwarded:
        first = _safe_text(forwarded.split(",", 1)[0])
        if first:
            return first
    real_ip = _safe_text(request.headers.get("X-Real-IP"))
    if real_ip:
        return real_ip
    return _safe_text(request.remote_addr, "-")


def _operator_name() -> str:
    user = current_user() or {}
    return (
        _safe_text(user.get("employee_name"))
        or _safe_text(user.get("username"))
        or _safe_text(user.get("employee_no"))
        or "system"
    )


def _operator_user_id() -> int | None:
    user = current_user() or {}
    user_id = _safe_int(user.get("id"), 0)
    return user_id if user_id > 0 else None


def _forbidden_page(*, module_name: str, required_permissions: list[str]):
    return (
        render_template(
            "forbidden.html",
            module_name=module_name,
            required_permissions=required_permissions,
        ),
        403,
    )


def _can_supplement_operate(user: dict[str, Any] | None = None) -> bool:
    target = user if user is not None else (current_user() or {})
    if not target:
        return False
    if is_system_admin(target):
        return True
    role_keys = current_user_role_keys(target)
    if role_keys & SUPPLEMENT_ALLOWED_ROLE_KEYS:
        return True
    department = _safe_text(target.get("department"))
    if "璐㈠姟" in department:
        return _safe_text(access_level(target)).upper() in {"B", "C", "D", "E"}
    return False


def _normalize_risk_level(value: str | None) -> str:
    raw = _safe_text(value).upper()
    mapping = {
        "姝ｅ父": "LOW",
        "LOW": "LOW",
        "NORMAL": "LOW",
        "鍏虫敞": "MEDIUM",
        "MEDIUM": "MEDIUM",
        "MID": "MEDIUM",
        "高风险": "HIGH",
        "HIGH": "HIGH",
    }
    return mapping.get(raw, raw if raw in {"LOW", "MEDIUM", "HIGH"} else "")


def _normalize_verify_status(value: str | None) -> str:
    raw = _safe_text(value).upper()
    mapping = {
        "閫氳繃": "PASS",
        "PASS": "PASS",
        "PASSED": "PASS",
        "涓嶉€氳繃": "FAIL",
        "FAIL": "FAIL",
        "FAILED": "FAIL",
        "未验真": "PENDING",
        "待验真": "PENDING",
        "PENDING": "PENDING",
    }
    return mapping.get(raw, raw if raw in {"PASS", "FAIL", "PENDING"} else "")


def _parse_filters(args) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ledger_date_start": _safe_text(args.get("ledger_date_start")),
        "ledger_date_end": _safe_text(args.get("ledger_date_end")),
        "expense_category": _safe_text(args.get("expense_category")),
        "risk_level": _normalize_risk_level(args.get("risk_level")),
        "verify_status": _normalize_verify_status(args.get("verify_status")),
        "keyword": _safe_text(args.get("keyword")),
        "reference_no": _safe_text(args.get("reference_no")),
    }
    return out


def _record_state_to_tab(record_state: Any) -> str:
    return "draft" if _safe_text(record_state).upper() == "DRAFT" else "ledger"


@bp.get("/invoices_page")
@login_required
def invoices_page():
    if not has_permission("VIEW_INVOICES", current_user() or {}):
        return _forbidden_page(module_name="鍑瘉鍙拌处涓績", required_permissions=["VIEW_INVOICES"])

    current_app.logger.info(
        "HIT /invoices_page route",
        extra={"route": "invoices_page", "template": LEDGER_TEMPLATE},
    )

    # Backward-compatible redirect for old deep-link style.
    focus = _safe_text(request.args.get("focus")).lower()
    if focus == "risk":
        current_app.logger.warning("Deprecated focus=risk on /invoices_page, redirecting to /risk-center")
        return redirect(url_for("risk_pages.risk_center_page"))

    filters = _parse_filters(request.args)
    filter_invoice_id: int | None = None
    filter_case_id: int | None = None
    raw_invoice_id = request.args.get("invoice_id")
    raw_case_id = request.args.get("case_id")
    if raw_invoice_id is not None and str(raw_invoice_id).strip() != "":
        try:
            filter_invoice_id = int(raw_invoice_id)
            if filter_invoice_id <= 0:
                filter_invoice_id = None
        except (TypeError, ValueError):
            filter_invoice_id = None
    if filter_invoice_id is None and raw_case_id is not None and str(raw_case_id).strip() != "":
        try:
            cid = int(raw_case_id)
            if cid > 0:
                filter_case_id = cid
                filter_invoice_id = get_invoice_id_by_risk_case_id(cid)
        except (TypeError, ValueError):
            pass
    # case_id 鍦?URL 浣嗘湭瑙ｆ瀽鍒?invoice_id锛氫粛鏍囪涓烘寜绛涢€夎繘鍏ワ紝妯℃澘鏄剧ず鏃犵粨鏋?+ 鏌ョ湅鍏ㄩ儴
    filter_by_id = filter_invoice_id is not None or filter_case_id is not None
    if filter_invoice_id is not None:
        # 褰撴湁 invoice_id 鏃讹紝娓呯┖鍏朵粬绛涢€夋潯浠讹紝鍙寜 invoice_id 鏌ヨ
        filters = {"invoice_id": filter_invoice_id}

    scope_filter = apply_data_scope_filter(user=current_user())
    context = load_ledger_page_context(
        tab=request.args.get("tab"),
        limit=request.args.get("limit"),
        data_scope=scope_filter,
        filters=filters,
    )
    rows = context["rows"]
    active_tab = _safe_text(context.get("active_tab"), "ledger").lower()
    # invoice_id deep-link should only be forbidden when out-of-scope.
    # If the invoice is visible but moved from draft <-> ledger, redirect to the correct tab.
    if filter_invoice_id is not None and len(rows) == 0:
        scoped_invoice = get_invoice_detail(filter_invoice_id, data_scope=scope_filter)
        if scoped_invoice is None:
            return (
                render_template(
                    "forbidden.html",
                    module_name="该单据不在您的数据权限范围内，无法查看（直链越权）",
                    required_permissions=[],
                ),
                403,
            )

        target_tab = _record_state_to_tab(scoped_invoice.get("record_state"))
        if target_tab != active_tab:
            redirect_query = request.args.to_dict(flat=True)
            redirect_query["tab"] = target_tab
            redirect_query["invoice_id"] = str(filter_invoice_id)
            return redirect(url_for("ledger.invoices_page", **redirect_query))

        # Defensive fallback for list query edge-cases.
        rows = [scoped_invoice]
    # case_id 入参但未解析到 invoice_id 时展示空列表 + 无结果提示
    if filter_case_id is not None and filter_invoice_id is None:
        rows = []
    current_app.logger.info("render invoices_page template=%s", LEDGER_TEMPLATE)
    return render_template(
        LEDGER_TEMPLATE,
        invoices=rows,
        active_tab=context["active_tab"],
        can_supplement_ops=_can_supplement_operate(),
        page_limit=context["page_limit"],
        page_size_options=context["page_size_options"],
        ledger_count=context["ledger_count"],
        draft_count=context["draft_count"],
        ledger_kpi=context.get("kpi", {}),
        filters=filters,
        filter_options=context.get("filter_options", {}),
        filter_by_id=filter_by_id,
        filter_invoice_id=filter_invoice_id,
        filter_case_id=filter_case_id,
        page_debug={
            "route": "/invoices_page",
            "template": LEDGER_TEMPLATE,
            "api_version": LEDGER_API_VERSION,
        },
    )


@bp.get("/ledger-center")
@login_required
def ledger_center_page():
    if not has_permission("VIEW_INVOICES", current_user() or {}):
        return _forbidden_page(module_name="鍑瘉鍙拌处涓績", required_permissions=["VIEW_INVOICES"])

    tab = _safe_text(request.args.get("tab"), "ledger").lower()
    if tab not in {"ledger", "draft"}:
        tab = "ledger"
    redirect_query = request.args.to_dict(flat=True)
    redirect_query["tab"] = tab
    return redirect(url_for("ledger.invoices_page", **redirect_query))


@bp.post("/api/ledger/ui-action-blocked")
@login_required
def ledger_ui_action_blocked():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "msg": "璇锋眰浣撳繀椤讳负 JSON 瀵硅薄"}), 400

    action = _safe_text(payload.get("action"), "UNKNOWN_ACTION").upper()
    reason = _safe_text(payload.get("reason"), "API_NOT_WIRED").upper()
    invoice_id = _safe_int(payload.get("invoice_id"), 0)
    trace_id = _safe_text(payload.get("trace_id"), "-")
    detail = (
        f"reason={reason}; "
        f"action={action}; "
        f"route=/invoices_page; "
        f"invoice_id={invoice_id if invoice_id > 0 else '-'}; "
        f"ip={_client_ip()}; "
        f"trace_id={trace_id}"
    )
    insert_audit_log(
        action_type="UI_ACTION_BLOCKED",
        operator=_operator_name(),
        actor_user_id=_operator_user_id(),
        target_type="invoice" if invoice_id > 0 else "ui",
        target_id=invoice_id if invoice_id > 0 else None,
        detail=detail,
    )
    return jsonify(
        {
            "ok": True,
            "action": action,
            "reason": reason,
            "message": "已记录“功能待接入（沙箱模式）”审计日志。",
        }
    )
