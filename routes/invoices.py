from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pandas as pd
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    current_app,
    g,
    redirect,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from audit import MISSING_REASON_MESSAGE, write_audit_log
import config
from events import event_bus
from events.types import (
    RISK_STAGE,
    STAGE_AI_EXPLAIN,
    STAGE_RISK_EVENT_CREATED,
    risk_stage_category,
    risk_stage_message,
)
from services.invoice_service import get_invoice_dict
from services.audit_chain_service import append_event as append_audit_chain_event, link_evidence as link_audit_evidence
from services.invoice_verification_service import verify_invoice_internal
from services.prompt_ledger_service import DEFAULT_PROMPT_VERSION, record_ai_prompt_ledger
from services.risk_case_service import create_ai_risk_event_if_needed
from utils.audit_logger import write_audit_log as write_audit_log_orm
from utils.db import (
    delete_invoices,
    get_conn,
    get_invoice_detail,
    get_invoice_raw,
    get_or_create_audit_trace,
    insert_audit_log,
    insert_invoice,
    invoice_exists,
    list_invoice_audit_trail,
    list_all_invoices_for_export,
    list_invoices,
    normalize_record_state,
    resolve_record_state,
    update_invoice_status,
)
from utils.error_codes import format_error_response, get_http_status
from utils.fx_audit import detect_currency
from utils.llm_audit import semantic_audit
from utils.ocr_helper import recognize_invoice
from utils.risk import evaluate_risk
from utils.security import (
    apply_data_scope_filter,
    current_user,
    login_required,
    require_permission,
)
from utils.status_i18n import (
    to_cn_approval_stage,
    to_cn_approval_status,
    to_cn_ledger_action,
    to_cn_ledger_state,
    to_cn_reason_code,
    to_cn_verify_status,
)

bp = Blueprint("invoices", __name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = PROJECT_ROOT / "uploads"
SEED_ATTACHMENT_PREFIXES = ("ops_seed_", "demo_seed_", "seed_")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".pdf"}
LEDGER_REASON_CODES = {
    "DATA_COMPLETION",
    "DATA_CORRECTION",
    "SUBMIT_REVIEW",
    "RETURN_FOR_COMPLETION",
    "RERUN_AI_RISK",
    "MANUAL_OVERRIDE",
    "POLICY_EXCEPTION",
    "NEED_MORE_INFO",
    "SYSTEM_AUTO",
}
LEDGER_ACTIONS = {"SUBMIT_REVIEW", "RETURN_TO_DRAFT", "RERUN_AI_RISK", "POST_LEDGER"}


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _normalize_filename(value: Any) -> str:
    return Path(_safe_text(value)).name


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


def _record_invoice_audit_log(*, action_type: str, detail: str, target_id: int | None = None) -> None:
    try:
        insert_audit_log(
            action_type=action_type,
            operator=_operator_name(),
            actor_user_id=_operator_user_id(),
            target_type="invoice",
            target_id=target_id,
            detail=detail,
        )
    except Exception:
        return


def _parse_payload() -> tuple[dict[str, Any], tuple[Any, int] | None]:
    payload = request.get_json(silent=True)
    if request.data and payload is None:
        return {}, (jsonify({"ok": False, "msg": "请求体必须为 JSON"}), 400)
    if payload is None:
        return {}, None
    if not isinstance(payload, dict):
        return {}, (jsonify({"ok": False, "msg": "请求体必须是 JSON 对象"}), 400)
    return payload, None


def _require_change_reason_code(payload: dict[str, Any]) -> tuple[str, tuple[Any, int] | None]:
    reason_code = _safe_text(payload.get("change_reason_code")).upper()
    if not reason_code:
        return "", (jsonify({"ok": False, "msg": MISSING_REASON_MESSAGE}), 400)
    if reason_code not in LEDGER_REASON_CODES:
        return "", (jsonify({"ok": False, "msg": "变更原因码无效"}), 400)
    return reason_code, None


def _parse_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        try:
            invoice_id = int(value)
        except Exception:
            continue
        if invoice_id <= 0 or invoice_id in seen:
            continue
        seen.add(invoice_id)
        result.append(invoice_id)
    return result


def _invoice_snapshot(invoice: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(invoice or {})
    return {
        "id": _safe_int(row.get("id"), 0),
        "record_state": normalize_record_state(row.get("record_state"), fallback="DRAFT"),
        "amount": _safe_text(row.get("amount")),
        "invoice_date": _safe_text(row.get("invoice_date")),
        "risk_level": _safe_text(row.get("risk_level")).upper(),
        "risk_reason": _safe_text(row.get("risk_reason_biz") or row.get("risk_reason")),
        "rule_explain": _safe_text(row.get("rule_explain_biz") or row.get("rule_explain")),
        "approval_status": _safe_text(row.get("approval_status") or row.get("status")).upper(),
        "approval_stage": _safe_text(row.get("approval_stage")).upper(),
        "queue_owner_id": _safe_text(row.get("queue_owner_id")),
        "verify_status": _safe_text(row.get("verify_status")).upper(),
        "trace_id": _safe_text(row.get("ai_trace_id")),
    }


def _write_invoice_audit(
    *,
    action: str,
    invoice_id: int,
    before_obj: dict[str, Any] | None,
    after_obj: dict[str, Any] | None,
    change_reason_code: str,
    trace_id: str = "",
) -> tuple[Any, int] | None:
    try:
        write_audit_log(
            action=action,
            target_type="invoice",
            target_id=str(int(invoice_id)),
            before_obj=_invoice_snapshot(before_obj),
            after_obj=_invoice_snapshot(after_obj),
            change_reason_code=change_reason_code,
            trace_id=_safe_text(trace_id),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400
    except Exception:
        current_app.logger.exception("action=write_invoice_audit_failed invoice_id=%s action=%s", invoice_id, action)
        return jsonify({"ok": False, "msg": "审计日志写入失败"}), 500
    return None


def _current_scope_filter() -> dict[str, Any]:
    return apply_data_scope_filter(user=current_user())


def _get_invoice_for_scope(invoice_id: int, *, include_raw_json: bool = False) -> dict[str, Any] | None:
    return get_invoice_detail(
        invoice_id,
        include_raw_json=include_raw_json,
        data_scope=_current_scope_filter(),
    )


def _get_invoice_or_scope_error(
    invoice_id: int, *, include_raw_json: bool = False
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
    """
    获取发票详情，若因数据范围越权无权限则返回 403 中文错误。
    Returns:
        (invoice, error_response, status_code)
        - 有权限: (invoice, None, 200)
        - 越权: (None, error_dict, 403)
        - 不存在: (None, None, 404)
    """
    invoice = _get_invoice_for_scope(invoice_id, include_raw_json=include_raw_json)
    if invoice is not None:
        return invoice, None, 200
    if invoice_exists(invoice_id):
        return (
            None,
            format_error_response(
                "data_scope_forbidden",
                message_cn="您无权访问该数据范围的数据",
                technical_details={"invoice_id": invoice_id},
            ),
            403,
        )
    return None, None, 404


def _is_ledger_ready(invoice_row: dict[str, Any] | None) -> bool:
    if not isinstance(invoice_row, dict):
        return False
    resolved = resolve_record_state(
        amount=invoice_row.get("amount"),
        invoice_date=invoice_row.get("invoice_date"),
        preferred="LEDGER",
    )
    return resolved == "LEDGER"


def _resolve_file_hash(filename: str) -> str:
    safe_name = _normalize_filename(filename)
    if not safe_name:
        return "-"
    path = UPLOAD_DIR / safe_name
    if not path.exists() or not path.is_file():
        return "-"
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
    except Exception:
        return "-"
    return hasher.hexdigest()


def _decode_raw_json(raw_json: Any) -> dict[str, Any]:
    if isinstance(raw_json, dict):
        return dict(raw_json)
    text = _safe_text(raw_json)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _compute_rule_ratio(amount_text: str, threshold_text: str) -> str:
    try:
        actual = float(str(amount_text).replace(",", ""))
        threshold = float(str(threshold_text).replace(",", ""))
    except Exception:
        return "-"
    if threshold <= 0:
        return "-"
    ratio = ((actual - threshold) / threshold) * 100.0
    return f"{ratio:.2f}%"


def _rule_suggestion(risk_level: str) -> str:
    normalized = _safe_text(risk_level).upper()
    if normalized == "HIGH":
        return "建议提交特批并升级二线复核"
    if normalized == "MEDIUM":
        return "建议补充业务佐证后复核"
    return "建议按常规流程处理"


def _normalize_structured_patch(payload: dict[str, Any]) -> dict[str, Any]:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        fields = payload

    updates: dict[str, Any] = {}
    if "amount" in fields:
        updates["amount"] = _safe_text(fields.get("amount"))
    if "invoice_date" in fields:
        updates["invoice_date"] = _normalize_date_string(_safe_text(fields.get("invoice_date")))
    if "applicant" in fields:
        updates["applicant"] = _safe_text(fields.get("applicant"))
    if "department" in fields:
        updates["department"] = _safe_text(fields.get("department"))
    return updates


def _apply_structured_update(invoice_id: int, updates: dict[str, Any]) -> None:
    if not updates:
        return
    keys = list(updates.keys())
    assignments = ", ".join([f"{key} = ?" for key in keys])
    values = [updates[key] for key in keys]
    with get_conn() as conn:
        conn.execute(
            f"UPDATE invoices SET {assignments} WHERE id = ?",
            (*values, int(invoice_id)),
        )
        conn.commit()


def _set_record_state(
    invoice_id: int,
    *,
    record_state: str,
    set_pending_status: bool = False,
    return_to_draft: bool = False,
) -> None:
    normalized = normalize_record_state(record_state, fallback="DRAFT")
    updates: dict[str, Any] = {"record_state": normalized}
    if return_to_draft:
        updates["status"] = "RETURNED"
        updates["approval_status"] = "RETURNED"
        updates["approval_stage"] = "DONE"
        updates["queue_owner_id"] = ""
    elif set_pending_status:
        updates["status"] = "PENDING"
        updates["approval_status"] = "PENDING"
        updates["approval_stage"] = "L1"

    keys = list(updates.keys())
    assignments = ", ".join([f"{key} = ?" for key in keys])
    values = [updates[key] for key in keys]
    with get_conn() as conn:
        conn.execute(
            f"UPDATE invoices SET {assignments} WHERE id = ?",
            (*values, int(invoice_id)),
        )
        conn.commit()


def _build_evidence_payload(invoice_row: dict[str, Any]) -> dict[str, Any]:
    filename = _normalize_filename(invoice_row.get("filename"))
    ext = Path(filename).suffix.lower().lstrip(".") or "-"
    file_type = ext.upper() if ext else "-"
    raw_json = _decode_raw_json(invoice_row.get("raw_json"))
    preview_available = bool(filename) and (UPLOAD_DIR / filename).is_file()
    if filename and not preview_available and ensure_seed_attachment_file(filename):
        preview_available = bool((UPLOAD_DIR / filename).is_file())

    structured_data = {
        "invoice_id": _safe_int(invoice_row.get("id"), 0),
        "reference_no": _safe_text(invoice_row.get("reference_no"), "-"),
        "record_state": normalize_record_state(invoice_row.get("record_state"), fallback="DRAFT"),
        "record_state_cn": to_cn_ledger_state(invoice_row.get("record_state")),
        "amount": _safe_text(invoice_row.get("amount")),
        "invoice_date": _safe_text(invoice_row.get("invoice_date")),
        "applicant": _safe_text(invoice_row.get("applicant")),
        "department": _safe_text(invoice_row.get("department")),
        "vendor": _safe_text(invoice_row.get("merchant_name")),
        "expense_type": _safe_text(invoice_row.get("item_name")),
        "raw_json": raw_json,
    }

    verify_block = {
        "verify_status": _safe_text(invoice_row.get("verify_status"), "暂无"),
        "verify_status_cn": to_cn_verify_status(invoice_row.get("verify_status")),
        "checked_at": _safe_text(invoice_row.get("verify_checked_at"), "暂无"),
        "check_count": _safe_int(invoice_row.get("verify_count"), 0),
        "request_id": _safe_text(invoice_row.get("verify_request_id"), "暂无"),
    }

    invoice_meta = {
        "invoice_code": _safe_text(invoice_row.get("invoice_code") or raw_json.get("invoice_code")),
        "invoice_number": _safe_text(invoice_row.get("invoice_number") or raw_json.get("invoice_number")),
        "invoice_date": _safe_text(invoice_row.get("invoice_date") or raw_json.get("invoice_date")),
        "seller_name": _safe_text(invoice_row.get("seller_name") or raw_json.get("seller_name") or raw_json.get("seller")),
        "buyer_name": _safe_text(invoice_row.get("buyer_name") or raw_json.get("buyer_name") or raw_json.get("purchaser")),
        "total_amount": _safe_text(invoice_row.get("amount") or raw_json.get("total_amount") or raw_json.get("amount")),
        "tax_amount": _safe_text(invoice_row.get("tax_amount") or raw_json.get("tax_amount") or raw_json.get("tax")),
        "verify_status": verify_block["verify_status"],
        "verify_status_cn": verify_block["verify_status_cn"],
        "file_type": file_type,
        "filename": filename,
        "preview_url": url_for("invoices.uploads_file", filename=filename) if filename else "",
        "preview_available": preview_available,
    }

    threshold_text = _safe_text(invoice_row.get("hotel_limit"), "-")
    actual_text = _safe_text(invoice_row.get("amount"), "-")
    rule_block = {
        "rule_name": _safe_text(invoice_row.get("rule_hit_id"), "RULE_RISK_LEVEL"),
        "rule_version": "v1-local",
        "threshold": threshold_text,
        "actual": actual_text,
        "ratio": _compute_rule_ratio(actual_text, threshold_text),
        "suggestion": _rule_suggestion(_safe_text(invoice_row.get("risk_level")).upper()),
        "summary": _safe_text(invoice_row.get("rule_explain_biz") or invoice_row.get("risk_reason_biz")),
    }

    approval_block = {
        "approval_stage": _safe_text(invoice_row.get("approval_stage"), "暂无"),
        "approval_stage_cn": to_cn_approval_stage(invoice_row.get("approval_stage")),
        "approval_status": _safe_text(invoice_row.get("approval_status") or invoice_row.get("status"), "暂无"),
        "approval_status_cn": to_cn_approval_status(invoice_row.get("approval_status") or invoice_row.get("status")),
        "first_approver": _safe_text(invoice_row.get("first_approver_id"), "暂无"),
        "first_approved_at": _safe_text(invoice_row.get("first_approved_at"), "暂无"),
        "second_approver": _safe_text(invoice_row.get("second_approver_id"), "暂无"),
        "second_approved_at": _safe_text(invoice_row.get("second_approved_at"), "暂无"),
    }

    audit_logs = list_invoice_audit_trail(_safe_int(invoice_row.get("id"), 0), limit=20)

    return {
        "raw_voucher": {
            "filename": filename or "-",
            "file_type": file_type or "-",
            "page_count": 1,
            "uploaded_at": _safe_text(invoice_row.get("created_at"), "-"),
            "uploaded_by": _safe_text(invoice_row.get("submitter_name") or invoice_row.get("applicant"), "-"),
            "file_hash": _resolve_file_hash(filename),
        },
        "structured_data": structured_data,
        "verification_receipt": verify_block,
        "rule_evidence": rule_block,
        "approval_chain": approval_block,
        "audit_trail": audit_logs,
        "invoice_meta": invoice_meta,
    }


def _invoice_in_scope(invoice: dict[str, Any] | None) -> bool:
    if not isinstance(invoice, dict):
        return False
    scope_filter = _current_scope_filter()
    if bool(scope_filter.get("all_access")):
        return True

    scoped_departments = {
        _safe_text(item)
        for item in (scope_filter.get("department_names") or [])
        if _safe_text(item)
    }
    invoice_department = _safe_text(invoice.get("department"))
    if scoped_departments and invoice_department not in scoped_departments:
        return False

    if bool(scope_filter.get("self_only")):
        me = current_user() or {}
        identities = {
            _safe_text(me.get("id")).lower(),
            _safe_text(me.get("username")).lower(),
            _safe_text(me.get("employee_no")).lower(),
            _safe_text(me.get("employee_name")).lower(),
        }
        identities = {item for item in identities if item}
        invoice_identities = {
            _safe_text(invoice.get("submitted_by_user_id")).lower(),
            _safe_text(invoice.get("submitter_no")).lower(),
            _safe_text(invoice.get("submitter_name")).lower(),
            _safe_text(invoice.get("applicant")).lower(),
        }
        return any(item in identities for item in invoice_identities if item)
    return True


def _safe_limit(raw: Any, default: int = 50, max_limit: int = 5000) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    if value <= 0:
        value = default
    return min(value, max_limit)


def _wants_json() -> bool:
    if request.path.startswith("/api/") or request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _is_allowed_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_EXTENSIONS


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _is_seed_attachment_name(filename: str) -> bool:
    safe_name = _normalize_filename(filename).lower()
    return safe_name.endswith(".pdf") and safe_name.startswith(SEED_ATTACHMENT_PREFIXES)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_seed_pdf_bytes(filename: str) -> bytes:
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "DeepAudit Pro",
        "Seed Attachment",
        f"File: {filename}",
        f"Generated: {now_text}",
    ]
    text_ops = ["BT", "/F1 13 Tf", "50 780 Td"]
    for idx, line in enumerate(lines):
        safe_line = _pdf_escape(line)
        if idx == 0:
            text_ops.append(f"({safe_line}) Tj")
        else:
            text_ops.append(f"0 -20 Td ({safe_line}) Tj")
    text_ops.append("ET")
    content_stream = "\n".join(text_ops)
    content_bytes = content_stream.encode("latin-1", errors="ignore")

    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        (
            "3 0 obj\n"
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\n"
            "endobj\n"
        ),
        (
            "4 0 obj\n"
            f"<< /Length {len(content_bytes)} >>\n"
            "stream\n"
            f"{content_stream}\n"
            "endstream\n"
            "endobj\n"
        ),
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    pdf_bytes = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(pdf_bytes))
        pdf_bytes.extend(obj.encode("latin-1", errors="ignore"))

    xref_pos = len(pdf_bytes)
    pdf_bytes.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf_bytes.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_bytes.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf_bytes.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(pdf_bytes)


def ensure_seed_attachment_file(filename: str) -> bool:
    safe_name = _normalize_filename(filename)
    if not safe_name or not _is_seed_attachment_name(safe_name):
        return False
    _ensure_upload_dir()
    target_path = UPLOAD_DIR / safe_name
    if target_path.exists():
        return True
    try:
        target_path.write_bytes(_build_seed_pdf_bytes(safe_name))
        return True
    except Exception:
        try:
            current_app.logger.exception("action=seed_attachment_materialize_failed filename=%s", safe_name)
        except Exception:
            pass
        return False


def _build_storage_name(original_name: str) -> str:
    secured = secure_filename(Path(original_name).name)
    if not secured:
        secured = "invoice"
    stem = Path(secured).stem or "invoice"
    suffix = Path(secured).suffix.lower()
    return f"{stem}_{uuid4().hex[:8]}{suffix}"


def _save_file(file_obj: FileStorage) -> tuple[str, Path]:
    _ensure_upload_dir()
    storage_name = _build_storage_name(file_obj.filename or "invoice")
    target_path = UPLOAD_DIR / storage_name
    file_obj.save(target_path)
    return storage_name, target_path


def _normalize_date_string(value: str) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    text = (
        text.replace(".", "-")
        .replace("/", "-")
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
    )
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if not m:
        return ""
    yyyy, mm, dd = m.groups()
    try:
        return date(int(yyyy), int(mm), int(dd)).isoformat()
    except Exception:
        return ""


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
                if key_text:
                    lines.append(f"{key_text}: {val_text}")
                else:
                    lines.append(val_text)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
        else:
            text = _safe_text(obj)
            if text:
                lines.append(text)

    _walk(value)
    dedup: list[str] = []
    seen: set[str] = set()
    for item in lines:
        if item in seen:
            continue
        seen.add(item)
        dedup.append(item)
    return dedup


def _extract_amount_and_date(payload: dict[str, Any]) -> tuple[str, str]:
    lines = _extract_lines(payload)

    date_value = ""
    amount_value = ""

    for line in lines:
        if not date_value:
            m_date = re.search(r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})", line)
            if m_date:
                normalized = _normalize_date_string(m_date.group(1))
                if normalized:
                    date_value = normalized

        if not amount_value:
            key_lower = line.lower()
            if any(token in key_lower for token in ("amount", "total", "sum", "金额", "价税", "合计")):
                m_amount = re.search(r"(-?\d+(?:\.\d{1,2})?)", line.replace(",", ""))
                if m_amount:
                    amount_value = m_amount.group(1)

    if not amount_value:
        for line in lines:
            m_amount = re.search(r"(-?\d+(?:\.\d{1,2})?)", line.replace(",", ""))
            if m_amount:
                amount_value = m_amount.group(1)
                break

    return amount_value, date_value


def _is_canton_fair_day(invoice_date_text: str) -> bool:
    normalized = _normalize_date_string(invoice_date_text)
    if not normalized:
        return False
    try:
        target = datetime.strptime(normalized, "%Y-%m-%d").date()
    except Exception:
        return False

    for start_mmdd, end_mmdd in getattr(config, "CANTON_FAIR_WINDOWS", []):
        try:
            start_day = datetime.strptime(f"{target.year}-{start_mmdd}", "%Y-%m-%d").date()
            end_day = datetime.strptime(f"{target.year}-{end_mmdd}", "%Y-%m-%d").date()
        except Exception:
            continue
        if start_day <= target <= end_day:
            return True
    return False


def _collect_currency(form_currency: str, payload: dict[str, Any]) -> str:
    normalized = _safe_text(form_currency).upper()
    if normalized:
        return normalized

    for line in _extract_lines(payload):
        detected = detect_currency(line)
        if detected:
            return detected
    return "CNY"


def _collect_ai_items(payload: dict[str, Any], manual_entry: dict[str, Any]) -> list[str]:
    items = [
        _safe_text(manual_entry.get("seller_name")),
        _safe_text(manual_entry.get("expense_category")),
        _safe_text(manual_entry.get("expense_description")),
    ]
    items.extend(_extract_lines(payload)[:12])
    return [item for item in items if item]


def _remove_uploaded_files(filenames: list[str]) -> None:
    for name in filenames:
        file_name = _normalize_filename(name)
        if not file_name:
            continue
        path = UPLOAD_DIR / file_name
        try:
            if path.exists():
                path.unlink()
        except Exception:
            continue


def _map_tax_status_to_risk(status: str) -> tuple[str, int]:
    normalized = _safe_text(status).lower()
    if normalized == "valid":
        return "LOW", 25
    if normalized == "red":
        return "MEDIUM", 65
    if normalized in {"void", "abnormal"}:
        return "HIGH", 88
    return "MEDIUM", 55


def _risk_rank(level: str) -> int:
    normalized = _safe_text(level).upper()
    if normalized == "HIGH":
        return 3
    if normalized == "MEDIUM":
        return 2
    return 1


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = _safe_text(value).lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return False


def _merge_risk_result(
    tax_level: str,
    tax_score: int,
    rule_level: str,
    rule_score: int,
) -> tuple[str, int]:
    tax_level_n = _safe_text(tax_level, "MEDIUM").upper()
    rule_level_n = _safe_text(rule_level, "LOW").upper()
    level = tax_level_n if _risk_rank(tax_level_n) >= _risk_rank(rule_level_n) else rule_level_n

    score = max(0, min(100, max(_safe_int(tax_score, 0), _safe_int(rule_score, 0))))
    if level == "HIGH":
        score = max(score, 85)
    elif level == "MEDIUM":
        score = max(score, 55)
    else:
        score = min(score, 50)
    return level, score


def _normalize_evidence_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = _safe_text(item.get("key"))
        val = _safe_text(item.get("value"))
        if not key and not val:
            continue
        normalized.append(
            {
                "type": _safe_text(item.get("type"), "field"),
                "key": key or "-",
                "value": val or "-",
            }
        )
    return normalized


def _build_ai_summary(risk_level: str, tax_status: str, tax_message: str) -> str:
    if risk_level == "HIGH":
        return f"税务验真状态为 {tax_status}，存在高风险特征，建议立即人工复核。"
    if risk_level == "LOW":
        return "税务验真通过，当前未发现明显高风险特征。"
    return f"税务验真状态为 {tax_status}，建议补充材料后复核。"


def _build_ai_suggestion(risk_level: str) -> str:
    if risk_level == "HIGH":
        return "建议暂缓付款并转人工复核，补齐业务说明与凭证。"
    if risk_level == "LOW":
        return "建议按既定流程继续审批，并保留审计留痕。"
    return "建议补充合同、行程或收款依据后继续复核。"


def _build_ai_details(invoice: dict[str, Any], tax_status: str, tax_message: str) -> str:
    invoice_no = _safe_text(invoice.get("invoice_number"), "-")
    seller = _safe_text(invoice.get("seller_name"), "-")
    buyer = _safe_text(invoice.get("buyer_name"), "-")
    amount = _safe_text(invoice.get("amount"), "-")
    bill_date = _safe_text(invoice.get("date"), "-")
    return "\n".join(
        [
            f"1. 发票号：{invoice_no}",
            f"2. 税务验真：{tax_status}（{tax_message}）",
            f"3. 商户：{seller}，报销人：{buyer}",
            f"4. 金额：{amount} CNY，日期：{bill_date}",
        ]
    )


def _build_ai_evidence(invoice: dict[str, Any], tax_status: str, tax_message: str) -> list[dict[str, str]]:
    amount = _safe_text(invoice.get("amount"), "-")
    seller = _safe_text(invoice.get("seller_name"), "-")
    invoice_no = _safe_text(invoice.get("invoice_number"), "-")
    bill_date = _safe_text(invoice.get("date"), "-")

    evidence = [
        {"type": "rule_hit", "key": "税务验真", "value": f"{tax_status}（{tax_message}）"},
        {"type": "field", "key": "商户", "value": seller},
        {"type": "field", "key": "金额", "value": f"{amount} CNY"},
        {"type": "field", "key": "发票号", "value": invoice_no},
    ]
    if bill_date and bill_date != "-":
        evidence.append({"type": "field", "key": "日期", "value": bill_date})
    return evidence


def _build_ai_protocol_payload(
    invoice_id: int,
    invoice: dict[str, Any],
    tax_result: dict[str, Any],
) -> dict[str, Any]:
    tax_ok = bool(tax_result.get("ok"))
    tax_status = _safe_text(tax_result.get("status"), "unknown").lower()
    if tax_status not in {"valid", "void", "red", "abnormal", "unknown"}:
        tax_status = "unknown"
    tax_message = _safe_text(tax_result.get("message"), "税务验真返回空结果")

    tax_level, tax_score = _map_tax_status_to_risk(tax_status)
    if not tax_ok:
        # Provider failed but keep protocol stable for offline demo.
        tax_level, tax_score = "MEDIUM", 60
        if not tax_message:
            tax_message = "税务验真服务异常，已转入人工复核建议。"

    rule_eval = evaluate_risk(
        amount_str=invoice.get("amount"),
        invoice_date=_safe_text(invoice.get("invoice_date")) or _safe_text(invoice.get("date")),
        hotel_limit=invoice.get("hotel_limit"),
        is_canton_fair=_safe_bool(invoice.get("is_canton_fair")),
        currency=_safe_text(invoice.get("currency")) or "CNY",
        manual_rate=invoice.get("manual_rate"),
        manual_cny_amount=invoice.get("manual_cny_amount"),
    )
    rule_level = _safe_text(rule_eval.get("level"), "LOW").upper()
    rule_score = _safe_int(rule_eval.get("score"), 0)
    risk_level, risk_score = _merge_risk_result(tax_level, tax_score, rule_level, rule_score)

    raw_trace_id = _safe_text(getattr(g, "trace_id", ""))
    trace_id = str(uuid4())
    if raw_trace_id:
        try:
            # Normalize 32-char hex trace_id to canonical UUID format.
            if len(raw_trace_id) == 32:
                trace_id = str(UUID(hex=raw_trace_id))
            else:
                trace_id = raw_trace_id
        except Exception:
            trace_id = str(uuid4())

    rule_reason = _safe_text(rule_eval.get("reason"))
    details = _build_ai_details(invoice, tax_status, tax_message)
    if rule_reason:
        details = f"{details}\n5. 规则引擎：{rule_reason}"

    evidence = _build_ai_evidence(invoice, tax_status, tax_message)
    evidence.extend(_normalize_evidence_items(rule_eval.get("evidence")))

    summary = _build_ai_summary(risk_level, tax_status, tax_message)
    if rule_reason and risk_level in {"MEDIUM", "HIGH"}:
        summary = f"{summary} 规则判定：{rule_reason}。"

    data = {
        "risk_level": risk_level,
        "risk_score": int(risk_score),
        "summary": summary,
        "details": details,
        "suggestion": _build_ai_suggestion(risk_level),
        "evidence": evidence,
        "model": "mock_sentinel_v1",
        "trace_id": trace_id,
    }
    return {"status": "success", "data": data}


@bp.get("/invoices")
@login_required
def invoices_api():
    tab = _safe_text(request.args.get("tab"), "ledger").lower()
    active_state = "DRAFT" if tab == "draft" else "LEDGER"
    scope_filter = _current_scope_filter()

    offset_val = _safe_int(request.args.get("offset"), 0)
    if offset_val < 0:
        offset_val = 0

    date_filters: dict[str, Any] = {}
    date_start = _safe_text(request.args.get("date_start"))
    date_end = _safe_text(request.args.get("date_end"))
    if date_start:
        date_filters["ledger_date_start"] = date_start
    if date_end:
        date_filters["ledger_date_end"] = date_end

    rows = list_invoices(
        limit=_safe_limit(request.args.get("limit"), default=50),
        offset=offset_val,
        record_state=active_state,
        data_scope=scope_filter,
        filters=date_filters if date_filters else None,
    )
    cleaner = current_app.config.get("CLEAN_INVOICE_ROWS")
    if callable(cleaner):
        rows = cleaner(rows)
    return jsonify(
        {
            "ok": True,
            "data": rows,
            "tab": tab,
            "record_state": active_state,
            "offset": offset_val,
            "debug_marker": "LEDGER_API_V2",
        }
    )


@bp.post("/upload")
@login_required
def upload_invoice():
    file_obj = request.files.get("file")
    if file_obj is None or not _safe_text(file_obj.filename):
        msg = "请先选择发票文件。"
        if _wants_json():
            return jsonify({"ok": False, "msg": msg}), 400
        flash(msg, "warning")
        return redirect(url_for("dashboard.upload_page"))

    if not _is_allowed_file(file_obj.filename or ""):
        msg = "仅支持图片或 PDF 文件。"
        if _wants_json():
            return jsonify({"ok": False, "msg": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("dashboard.upload_page"))

    try:
        stored_filename, saved_path = _save_file(file_obj)
    except Exception as exc:
        msg = f"文件保存失败：{exc}"
        if _wants_json():
            return jsonify({"ok": False, "msg": msg}), 500
        flash(msg, "danger")
        return redirect(url_for("dashboard.upload_page"))

    user = current_user() or {}
    entry_mode = _safe_text(request.form.get("entry_mode"), "ocr").lower()
    manual_entry = {
        "invoice_code": _safe_text(request.form.get("invoice_code")),
        "invoice_number": _safe_text(request.form.get("invoice_number")),
        "seller_name": _safe_text(request.form.get("seller_name")),
        "expense_category": _safe_text(request.form.get("expense_category")),
        "expense_description": _safe_text(request.form.get("expense_description")),
    }
    applicant = _safe_text(user.get("employee_name")) or _safe_text(user.get("username"), "-")
    department = _safe_text(user.get("department"), "-")
    submitter_no = _safe_text(user.get("employee_no"), "-")

    try:
        if entry_mode == "manual":
            raw_payload: dict[str, Any] = {
                "mode": "manual_entry",
                "entry_mode": "manual",
                "manual_entry": manual_entry,
            }
            amount = _safe_text(request.form.get("amount"))
            invoice_date = _normalize_date_string(_safe_text(request.form.get("invoice_date")))
        else:
            try:
                raw_payload = recognize_invoice(str(saved_path))
                raw_payload["entry_mode"] = "ocr"
            except Exception as ocr_exc:
                raw_payload = {
                    "mode": "ocr_failed",
                    "error": str(ocr_exc),
                    "entry_mode": "ocr",
                }
            amount, invoice_date = _extract_amount_and_date(raw_payload)

        currency = _collect_currency(_safe_text(request.form.get("currency")), raw_payload)
        manual_rate = _safe_text(request.form.get("manual_rate")) or None
        manual_cny_amount = _safe_text(request.form.get("manual_cny_amount")) or None

        is_canton_fair = _is_canton_fair_day(invoice_date)
        hotel_limit = int(config.HOTEL_LIMIT_CANTON_FAIR if is_canton_fair else config.HOTEL_LIMIT_NORMAL)
        risk = evaluate_risk(
            amount_str=amount,
            invoice_date=invoice_date,
            hotel_limit=hotel_limit,
            is_canton_fair=is_canton_fair,
            currency=currency,
            manual_rate=manual_rate,
            manual_cny_amount=manual_cny_amount,
        )
        ai_result = semantic_audit(
            items=_collect_ai_items(raw_payload, manual_entry),
            ocr_json=raw_payload,
        )

        invoice_id = insert_invoice(
            {
                "filename": stored_filename,
                "amount": amount,
                "invoice_date": invoice_date,
                "applicant": applicant,
                "department": department,
                "is_canton_fair": is_canton_fair,
                "hotel_limit": hotel_limit,
                "mode": _safe_text(raw_payload.get("mode"), entry_mode),
                "raw_json": raw_payload,
                "risk_level": _safe_text(risk.get("level"), "MEDIUM"),
                "risk_reason": _safe_text(risk.get("reason"), "规则引擎未返回说明"),
                "currency": currency,
                "fx_flag": bool(risk.get("fx_flag")),
                "fx_reason": _safe_text(risk.get("fx_reason")),
                "manual_rate": manual_rate,
                "manual_cny_amount": manual_cny_amount,
                "ai_risk_level": _safe_text(ai_result.get("risk_level"), "MEDIUM"),
                "ai_analysis_reason": _safe_text(ai_result.get("reason"), "AI 暂未返回结论"),
                "status": "PENDING",
                "record_state": "DRAFT",
                "submitted_by_user_id": user.get("id"),
                "submitter_department": department,
                "submitter_name": applicant,
                "submitter_no": submitter_no,
            }
        )
        try:
            trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
            append_audit_chain_event(trace_id, "UPLOAD", {"filename": stored_filename}, "SYSTEM_AUTO")
        except Exception as aexc:
            current_app.logger.warning("audit_chain UPLOAD append failed invoice_id=%s err=%s", invoice_id, aexc)
        
        # 写入新的 ORM 审计日志
        try:
            write_audit_log_orm(
                action="UPLOAD",
                actor_user_id=user.get("id"),
                actor_name=applicant,
                target_type="invoice",
                target_id=str(invoice_id),
                snapshot_after={
                    "filename": stored_filename,
                    "amount": amount,
                    "invoice_date": invoice_date,
                    "department": department,
                    "risk_level": _safe_text(risk.get("level"), "MEDIUM"),
                },
                detail=f"filename={stored_filename}; entry_mode={entry_mode}",
            )
        except Exception:
            current_app.logger.exception("write upload audit failed: invoice_id=%s", invoice_id)
    except Exception as exc:
        current_app.logger.exception(
            "action=upload_pipeline_failed filename=%s entry_mode=%s",
            stored_filename,
            entry_mode,
        )
        degraded_reason = _safe_text(exc, "unknown_error")[:500]
        try:
            fallback_invoice_id = insert_invoice(
                {
                    "filename": stored_filename,
                    "amount": "",
                    "invoice_date": "",
                    "applicant": applicant,
                    "department": department,
                    "is_canton_fair": False,
                    "hotel_limit": int(getattr(config, "HOTEL_LIMIT_NORMAL", 500)),
                    "mode": f"{entry_mode}_failed",
                    "raw_json": {
                        "mode": "upload_pipeline_failed",
                        "entry_mode": entry_mode,
                        "error": degraded_reason,
                        "manual_entry": manual_entry,
                    },
                    "risk_level": "MEDIUM",
                    "risk_reason": "自动解析失败，待人工补录",
                    "currency": _safe_text(request.form.get("currency"), "CNY") or "CNY",
                    "fx_flag": False,
                    "fx_reason": "",
                    "manual_rate": _safe_text(request.form.get("manual_rate")) or None,
                    "manual_cny_amount": _safe_text(request.form.get("manual_cny_amount")) or None,
                    "ai_risk_level": "MEDIUM",
                    "ai_analysis_reason": "AI未执行（上传降级）",
                    "status": "PENDING",
                    "record_state": "DRAFT",
                    "submitted_by_user_id": user.get("id"),
                    "submitter_department": department,
                    "submitter_name": applicant,
                    "submitter_no": submitter_no,
                }
            )
        except Exception:
            current_app.logger.exception(
                "action=upload_fallback_insert_failed filename=%s entry_mode=%s",
                stored_filename,
                entry_mode,
            )
            msg = f"上传处理失败：{exc}"
            if _wants_json():
                return jsonify({"ok": False, "msg": msg}), 500
            flash(msg, "danger")
            return redirect(url_for("dashboard.upload_page"))

        try:
            trace_id, _ = get_or_create_audit_trace("invoice", fallback_invoice_id)
            append_audit_chain_event(trace_id, "UPLOAD", {"filename": stored_filename, "degraded": True}, "SYSTEM_AUTO")
        except Exception:
            pass
        degraded_msg = "上传成功，但自动解析失败。系统已生成待补录草稿，请在右侧「我的单据」中补录后提交。"
        if _wants_json():
            return jsonify(
                {
                    "ok": True,
                    "id": fallback_invoice_id,
                    "filename": stored_filename,
                    "degraded": True,
                    "msg": degraded_msg,
                }
            )
        flash(degraded_msg, "warning")
        return redirect(url_for("dashboard.upload_page"))

    ok_msg = "提交成功。请在右侧「我的单据」中点击该单据的「查看详情」，在详情中点击「入账并进入审批」，单据即可进入审批流程。"
    if _wants_json():
        return jsonify({"ok": True, "id": invoice_id, "filename": stored_filename})
    flash(ok_msg, "success")
    return redirect(url_for("dashboard.upload_page"))


@bp.get("/invoice/<int:invoice_id>/raw")
@login_required
def invoice_raw(invoice_id: int):
    invoice, err_resp, status = _get_invoice_or_scope_error(invoice_id)
    if err_resp is not None:
        return jsonify(err_resp), get_http_status("data_scope_forbidden")
    if invoice is None:
        return jsonify({"ok": False, "msg": "invoice not found"}), 404

    payload = get_invoice_raw(invoice_id)
    if payload is None:
        return jsonify({"ok": False, "msg": "invoice not found"}), 404
    return jsonify({"ok": True, "data": payload})


def run_invoice_ai_internal(
    invoice_id: int,
    *,
    publish_events: bool = True,
    create_risk_event: bool = True,
    tax_result_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
    invoice_row = _get_invoice_for_scope(invoice_id, include_raw_json=False)
    invoice = get_invoice_dict(invoice_id)
    if not invoice_row or not invoice:
        return (
            {"status": "error", "error_code": "not_found", "message": "未找到单据"},
            None,
            404,
        )

    record_state = normalize_record_state(invoice_row.get("record_state"), fallback="DRAFT")
    allow_risk_event = create_risk_event and record_state == "LEDGER"

    result = tax_result_override
    if result is None:
        verify_payload, verify_status = verify_invoice_internal(
            invoice_id,
            publish_event=publish_events,
        )
        if verify_status >= 400 or not bool(verify_payload.get("ok")):
            message = _safe_text(
                verify_payload.get("msg")
                or verify_payload.get("message")
                or "发票验真失败",
                "发票验真失败",
            )
            return (
                {
                    "status": "error",
                    "error_code": "verify_failed",
                    "message": message,
                },
                None,
                verify_status if verify_status >= 400 else 500,
            )
        result = verify_payload.get("tax_result")

    if not isinstance(result, dict):
        result = {
            "ok": False,
            "status": "unknown",
            "message": "税务验真返回异常结构，已降级为人工复核建议",
        }

    try:
        trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
        append_audit_chain_event(
            trace_id, "OCR",
            {"verify_status": str(result.get("status", "")), "provider": str(result.get("provider", ""))},
            "SYSTEM_AUTO",
        )
        if result.get("ok") is False or str(result.get("status", "")).lower() in ("fail", "failed"):
            append_audit_chain_event(
                trace_id, "RULE_HIT",
                {"message": str(result.get("message", "")), "status": str(result.get("status", ""))},
                "SYSTEM_AUTO",
            )
    except Exception:
        pass

    response_payload = _build_ai_protocol_payload(invoice_id=invoice_id, invoice=invoice, tax_result=result)
    data = response_payload.get("data", {})
    if not isinstance(data, dict):
        data = {}

    if str(response_payload.get("status")) == "success":
        try:
            ledger_row = record_ai_prompt_ledger(
                invoice_id=invoice_id,
                invoice=invoice,
                tax_result=result,
                ai_data=data,
                prompt_version=DEFAULT_PROMPT_VERSION,
                provider=_safe_text(result.get("provider")),
            )
            current_app.logger.info(
                "action=prompt_ledger_saved invoice_id=%s trace_id=%s hash_curr=%s",
                invoice_id,
                ledger_row.get("trace_id"),
                ledger_row.get("hash_curr"),
            )
            try:
                tid, _ = get_or_create_audit_trace("invoice", invoice_id)
                append_audit_chain_event(
                    tid, "SCORE",
                    {"risk_level": str(data.get("risk_level", "")), "risk_score": int(data.get("risk_score") or 0)},
                    "SYSTEM_AUTO",
                )
            except Exception:
                pass
        except Exception as exc:
            current_app.logger.warning(
                "action=prompt_ledger_save_failed invoice_id=%s trace_id=%s err=%s",
                invoice_id,
                _safe_text(data.get("trace_id")),
                exc,
            )

    if publish_events:
        try:
            event_bus.publish(
                RISK_STAGE,
                {
                    "stage": STAGE_AI_EXPLAIN,
                    "event_type": STAGE_AI_EXPLAIN,
                    "message": risk_stage_message(STAGE_AI_EXPLAIN),
                    "category": risk_stage_category(STAGE_AI_EXPLAIN),
                    "invoice_id": int(invoice_id),
                    "risk_level": _safe_text(data.get("risk_level")).upper(),
                    "risk_score": _safe_int(data.get("risk_score"), 0),
                    "trace_id": _safe_text(data.get("trace_id")),
                    "related_ids": {"invoice_id": int(invoice_id)},
                },
            )
        except Exception as exc:
            current_app.logger.warning(
                "action=publish_stage invoice_id=%s stage=%s err=%s",
                invoice_id,
                STAGE_AI_EXPLAIN,
                exc,
            )

    risk_event = None
    if allow_risk_event:
        try:
            risk_event = create_ai_risk_event_if_needed(invoice_id=invoice_id, ai_data=data)
        except Exception as exc:
            risk_event = None
            current_app.logger.warning("action=create_risk_event invoice_id=%s err=%s", invoice_id, exc)

        if publish_events and isinstance(risk_event, dict) and risk_event.get("id"):
            try:
                event_id = _safe_int(risk_event.get("id"), 0)
                event_bus.publish(
                    RISK_STAGE,
                    {
                        "stage": STAGE_RISK_EVENT_CREATED,
                        "event_type": STAGE_RISK_EVENT_CREATED,
                        "message": risk_stage_message(STAGE_RISK_EVENT_CREATED),
                        "category": risk_stage_category(STAGE_RISK_EVENT_CREATED),
                        "event_id": event_id,
                        "invoice_id": _safe_int(risk_event.get("invoice_id"), invoice_id),
                        "risk_level": _safe_text(risk_event.get("risk_level")).upper(),
                        "risk_score": _safe_int(risk_event.get("risk_score"), 0),
                        "trace_id": _safe_text(risk_event.get("trace_id")),
                        "related_ids": {
                            "invoice_id": _safe_int(risk_event.get("invoice_id"), invoice_id),
                            "event_id": event_id,
                        },
                    },
                )
            except Exception as exc:
                current_app.logger.warning(
                    "action=publish_stage invoice_id=%s stage=%s err=%s",
                    invoice_id,
                    STAGE_RISK_EVENT_CREATED,
                    exc,
                )

    current_app.logger.info(
        "action=tax_verify invoice_id=%s risk_level=%s model=%s trace_id=%s",
        invoice_id,
        data.get("risk_level"),
        data.get("model"),
        data.get("trace_id"),
    )
    return response_payload, risk_event, 200


@bp.route("/invoice/<int:invoice_id>/ai", methods=["GET", "POST"])
@login_required
def invoice_ai(invoice_id: int):
    response_payload, _, status_code = run_invoice_ai_internal(
        invoice_id,
        publish_events=True,
        create_risk_event=True,
    )
    return jsonify(response_payload), status_code


@bp.post("/api/invoices/<int:invoice_id>/verify")
@login_required
@require_permission("VIEW_INVOICES")
def invoice_verify_api(invoice_id: int):
    invoice = _get_invoice_for_scope(invoice_id)
    if not invoice:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404

    payload = request.get_json(silent=True) or {}
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"ok": False, "msg": "请求体必须是 JSON 对象"}), 400

    verify_payload, status_code = verify_invoice_internal(
        invoice_id,
        publish_event=True,
        idempotency_key=_safe_text(payload.get("idempotency_key")) if isinstance(payload, dict) else "",
    )
    if status_code >= 400 or not bool(verify_payload.get("ok")):
        return jsonify({"ok": False, "msg": _safe_text(verify_payload.get("msg") or verify_payload.get("message"))}), status_code

    # 写入新的 ORM 审计日志
    try:
        user = current_user() or {}
        write_audit_log_orm(
            action="VERIFY",
            actor_user_id=user.get("id"),
            actor_name=_safe_text(user.get("employee_name") or user.get("username")),
            target_type="invoice",
            target_id=str(invoice_id),
            snapshot_after={
                "verify_status": _safe_text(verify_payload.get("verify_status")),
                "verify_message": _safe_text(verify_payload.get("verify_message")),
                "verify_provider": _safe_text(verify_payload.get("verify_provider")),
            },
            detail=f"verify_status={_safe_text(verify_payload.get('verify_status'))}; provider={_safe_text(verify_payload.get('verify_provider'))}",
        )
    except Exception:
        current_app.logger.exception("write verify audit failed: invoice_id=%s", invoice_id)

    return jsonify(
        {
            "ok": True,
            "invoice_id": _safe_int(verify_payload.get("invoice_id"), int(invoice_id)),
            "verify_status": _safe_text(verify_payload.get("verify_status"), "PENDING"),
            "verify_status_cn": to_cn_verify_status(verify_payload.get("verify_status")),
            "verify_message": _safe_text(verify_payload.get("verify_message")),
            "verify_provider": _safe_text(verify_payload.get("verify_provider")),
            "verify_request_id": _safe_text(verify_payload.get("verify_request_id")),
            "verify_latency_ms": _safe_int(verify_payload.get("verify_latency_ms"), 0),
            "verify_status_code": _safe_int(verify_payload.get("verify_status_code"), 0),
            "verify_checked_at": _safe_text(verify_payload.get("verify_checked_at")),
            "verify_count": _safe_int(verify_payload.get("verify_count"), 0),
            "result_code": _safe_text(verify_payload.get("result_code")),
            "event_id": _safe_int(verify_payload.get("event_id"), 0),
        }
    )


@bp.post("/api/invoice/<int:invoice_id>/status")
@login_required
@require_permission("VIEW_INVOICES")
def update_invoice_status_api(invoice_id: int):
    payload, parse_err = _parse_payload()
    if parse_err is not None:
        return parse_err
    reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    status = _safe_text(payload.get("status")).upper()
    if status not in {"PENDING", "APPROVED", "REJECTED", "RETURNED"}:
        return jsonify({"ok": False, "msg": "无效审批状态"}), 400

    invoice = _get_invoice_for_scope(invoice_id)
    if not invoice:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404
    if normalize_record_state(invoice.get("record_state"), fallback="DRAFT") != "LEDGER":
        return jsonify({"ok": False, "msg": "待补录单据不可直接更新审批状态，请先补全并入账。"}), 409

    before_obj = dict(invoice)
    updated = update_invoice_status(invoice_id, status, ledger_only=True)
    if not updated:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404
    after_obj = _get_invoice_for_scope(invoice_id)
    audit_err = _write_invoice_audit(
        action="INVOICE_STATUS_CHANGE",
        invoice_id=invoice_id,
        before_obj=before_obj,
        after_obj=after_obj,
        change_reason_code=reason_code,
        trace_id=_safe_text((after_obj or {}).get("ai_trace_id")),
    )
    if audit_err is not None:
        return audit_err

    _record_invoice_audit_log(
        action_type="APPROVAL_STATUS_CHANGE",
        target_id=int(invoice_id),
        detail=f"invoice_id={int(invoice_id)}; status={status}; reason={reason_code}",
    )
    return jsonify({"ok": True, "id": invoice_id, "status": status, "status_cn": to_cn_approval_status(status)})


@bp.get("/api/ledger/<int:invoice_id>/evidence")
@login_required
@require_permission("VIEW_INVOICES")
def ledger_evidence_api(invoice_id: int):
    invoice = _get_invoice_for_scope(invoice_id, include_raw_json=True)
    if not invoice:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404

    evidence = _build_evidence_payload(invoice)
    return jsonify(
        {
            "ok": True,
            "invoice_id": invoice_id,
            "record_state": normalize_record_state(invoice.get("record_state"), fallback="DRAFT"),
            "record_state_cn": to_cn_ledger_state(invoice.get("record_state")),
            "evidence": evidence,
            "debug_marker": "LEDGER_API_V2",
        }
    )


@bp.patch("/api/ledger/<int:invoice_id>/structured")
@login_required
@require_permission("VIEW_INVOICES")
def ledger_update_structured_api(invoice_id: int):
    payload, parse_err = _parse_payload()
    if parse_err is not None:
        return parse_err
    reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    before_row = _get_invoice_for_scope(invoice_id)
    if not before_row:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404

    updates = _normalize_structured_patch(payload)
    if not updates:
        return jsonify({"ok": False, "msg": "未提供可编辑字段"}), 400

    _apply_structured_update(invoice_id, updates)
    refreshed = _get_invoice_for_scope(invoice_id)
    if not refreshed:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404

    desired_state = resolve_record_state(
        amount=refreshed.get("amount"),
        invoice_date=refreshed.get("invoice_date"),
        preferred=refreshed.get("record_state"),
    )
    current_state = normalize_record_state(refreshed.get("record_state"), fallback="DRAFT")
    if desired_state != current_state:
        _set_record_state(
            invoice_id,
            record_state=desired_state,
            set_pending_status=(desired_state == "LEDGER"),
            return_to_draft=(desired_state == "DRAFT"),
        )
        refreshed = _get_invoice_for_scope(invoice_id) or refreshed

    audit_err = _write_invoice_audit(
        action="LEDGER_STRUCTURED_EDIT",
        invoice_id=invoice_id,
        before_obj=before_row,
        after_obj=refreshed,
        change_reason_code=reason_code,
        trace_id=_safe_text(refreshed.get("ai_trace_id")),
    )
    if audit_err is not None:
        return audit_err

    try:
        trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
        filename = _safe_text(refreshed.get("filename"))
        if filename:
            link_audit_evidence(trace_id, filename, object_type="invoice", object_id=str(invoice_id), change_reason_code=reason_code)
    except Exception:
        pass

    return jsonify(
        {
            "ok": True,
            "invoice_id": invoice_id,
            "record_state": normalize_record_state(refreshed.get("record_state"), fallback="DRAFT"),
            "record_state_cn": to_cn_ledger_state(refreshed.get("record_state")),
            "invoice": refreshed,
        }
    )


@bp.post("/api/ledger/<int:invoice_id>/action")
@login_required
@require_permission("VIEW_INVOICES")
def ledger_action_api(invoice_id: int):
    payload, parse_err = _parse_payload()
    if parse_err is not None:
        return parse_err
    reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    action = _safe_text(payload.get("action")).upper()
    current_app.logger.info("ledger_action_api invoice_id=%s action=%s", invoice_id, action)
    if action not in LEDGER_ACTIONS:
        return jsonify({"ok": False, "msg": "无效动作"}), 400

    before_row = _get_invoice_for_scope(invoice_id)
    if not before_row:
        return jsonify({"ok": False, "msg": "未找到单据"}), 404

    record_state = normalize_record_state(before_row.get("record_state"), fallback="DRAFT")
    comment = _safe_text(payload.get("comment"))
    message = ""
    ai_payload: dict[str, Any] | None = None

    if action == "SUBMIT_REVIEW":
        if record_state != "LEDGER":
            return jsonify({"ok": False, "msg": "待补录单据不可提交复核，请先补全并入账。"}), 409
        _set_record_state(invoice_id, record_state="LEDGER", set_pending_status=True)
        try:
            trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
            append_audit_chain_event(trace_id, "REVIEW", {"action": "SUBMIT_REVIEW"}, reason_code)
        except Exception:
            pass
        assignee = _safe_text((current_user() or {}).get("username")) or _safe_text((current_user() or {}).get("employee_no"))
        if assignee:
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE invoices
                    SET queue_owner_id = CASE WHEN TRIM(COALESCE(queue_owner_id, '')) = '' THEN ? ELSE queue_owner_id END
                    WHERE id = ?
                    """,
                    (assignee, int(invoice_id)),
                )
                conn.commit()
        message = "已提交复核，单据进入审批队列。"

    elif action == "RETURN_TO_DRAFT":
        if not comment:
            return jsonify({"ok": False, "msg": "打回补录必须填写说明"}), 400
        _set_record_state(invoice_id, record_state="DRAFT", return_to_draft=True)
        try:
            trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
            append_audit_chain_event(trace_id, "RETURN", {"comment": comment}, reason_code)
        except Exception:
            pass
        message = "已打回补录，单据已转为待补录状态。"

    elif action == "POST_LEDGER":
        if not _is_ledger_ready(before_row):
            return jsonify({"ok": False, "msg": "金额或开票日期缺失，无法入账"}), 409
        _set_record_state(invoice_id, record_state="LEDGER", set_pending_status=True)
        try:
            trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
            append_audit_chain_event(trace_id, "REVIEW", {"action": "POST_LEDGER"}, reason_code)
        except Exception:
            pass
        message = "补录完成，单据已入账。"

    elif action == "RERUN_AI_RISK":
        ai_payload, _, status_code = run_invoice_ai_internal(
            invoice_id,
            publish_events=True,
            create_risk_event=True,
        )
        if status_code >= 400:
            return jsonify({"ok": False, "msg": _safe_text(ai_payload.get("message") or ai_payload.get("msg") or "重跑失败")}), status_code
        message = "已完成重跑识别/重算风险。"

    after_row = _get_invoice_for_scope(invoice_id) or before_row
    audit_err = _write_invoice_audit(
        action=action,
        invoice_id=invoice_id,
        before_obj=before_row,
        after_obj=after_row,
        change_reason_code=reason_code,
        trace_id=_safe_text(after_row.get("ai_trace_id")),
    )
    if audit_err is not None:
        return audit_err

    return jsonify(
        {
            "ok": True,
            "invoice_id": invoice_id,
            "action": action,
            "action_cn": to_cn_ledger_action(action),
            "record_state": normalize_record_state(after_row.get("record_state"), fallback="DRAFT"),
            "record_state_cn": to_cn_ledger_state(after_row.get("record_state")),
            "approval_status": _safe_text(after_row.get("approval_status") or after_row.get("status"), "PENDING").upper(),
            "approval_status_cn": to_cn_approval_status(after_row.get("approval_status") or after_row.get("status")),
            "change_reason_code": reason_code,
            "change_reason_code_cn": to_cn_reason_code(reason_code),
            "message": message or "处理完成",
            "ai_result": ai_payload,
        }
    )


@bp.post("/api/ledger/batch")
@login_required
@require_permission("VIEW_INVOICES")
def ledger_batch_api():
    payload, parse_err = _parse_payload()
    if parse_err is not None:
        return parse_err
    reason_code, reason_err = _require_change_reason_code(payload)
    if reason_err is not None:
        return reason_err

    action = _safe_text(payload.get("action")).upper()
    if action not in {"RETURN_TO_DRAFT", "SUPPLEMENT"}:
        return jsonify({"ok": False, "msg": "无效动作"}), 400

    ids = _parse_int_list(payload.get("ids"))
    if not ids:
        return jsonify({"ok": False, "msg": "请先选择待处理单据"}), 400

    comment = _safe_text(payload.get("comment"))
    if action == "RETURN_TO_DRAFT" and not comment:
        return jsonify({"ok": False, "msg": "批量打回补录必须填写说明"}), 400

    updates = _normalize_structured_patch(payload)
    if action == "SUPPLEMENT" and not updates:
        return jsonify({"ok": False, "msg": "请至少填写一个补录字段"}), 400

    auto_post_ledger = bool(payload.get("post_ledger", True))
    success_ids: list[int] = []
    failed: list[dict[str, Any]] = []

    for invoice_id in ids:
        before_row = _get_invoice_for_scope(invoice_id)
        if not before_row:
            failed.append({"id": invoice_id, "msg": "未找到单据"})
            continue

        try:
            if action == "RETURN_TO_DRAFT":
                _set_record_state(invoice_id, record_state="DRAFT", return_to_draft=True)
                try:
                    trace_id, _ = get_or_create_audit_trace("invoice", invoice_id)
                    append_audit_chain_event(trace_id, "RETURN", {"comment": comment}, reason_code)
                except Exception:
                    pass
            else:
                _apply_structured_update(invoice_id, updates)
                refreshed = _get_invoice_for_scope(invoice_id)
                if refreshed:
                    next_state = resolve_record_state(
                        amount=refreshed.get("amount"),
                        invoice_date=refreshed.get("invoice_date"),
                        preferred=refreshed.get("record_state"),
                    )
                    if next_state == "DRAFT":
                        _set_record_state(invoice_id, record_state="DRAFT", return_to_draft=True)
                    elif auto_post_ledger:
                        _set_record_state(invoice_id, record_state="LEDGER", set_pending_status=True)

            after_row = _get_invoice_for_scope(invoice_id) or before_row
            audit_err = _write_invoice_audit(
                action=f"BATCH_{action}",
                invoice_id=invoice_id,
                before_obj=before_row,
                after_obj=after_row,
                change_reason_code=reason_code,
                trace_id=_safe_text(after_row.get("ai_trace_id")),
            )
            if audit_err is not None:
                failed.append({"id": invoice_id, "msg": "审计日志写入失败"})
                continue
            success_ids.append(invoice_id)
        except Exception as exc:
            failed.append({"id": invoice_id, "msg": str(exc)})

    return jsonify(
        {
            "ok": True,
            "action": action,
            "action_cn": to_cn_ledger_action(action),
            "change_reason_code": reason_code,
            "change_reason_code_cn": to_cn_reason_code(reason_code),
            "success_count": len(success_ids),
            "failed_count": len(failed),
            "success_ids": success_ids,
            "failed": failed,
        }
    )


@bp.post("/api/invoices/batch-delete")
@login_required
@require_permission("DELETE_INVOICE")
def batch_delete_invoices():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids")
    if not isinstance(ids, list):
        return jsonify({"ok": False, "msg": "ids must be a list"}), 400

    scope_filter = _current_scope_filter()
    if not bool(scope_filter.get("all_access")):
        allowed_rows = list_invoices(
            limit=5000,
            data_scope=scope_filter,
        )
        allowed_ids = {int(row.get("id", 0)) for row in allowed_rows if int(row.get("id", 0)) > 0}
        scoped_ids: list[int] = []
        for raw in ids:
            try:
                invoice_id = int(raw)
            except Exception:
                continue
            if invoice_id in allowed_ids and invoice_id not in scoped_ids:
                scoped_ids.append(invoice_id)
        result = delete_invoices(scoped_ids)
    else:
        result = delete_invoices(ids)

    _remove_uploaded_files(result.get("filenames", []))

    deleted_ids = [int(item) for item in (result.get("ids") or []) if _safe_int(item, 0) > 0]
    _record_invoice_audit_log(
        action_type="BATCH_DELETE",
        detail=(
            f"requested={len(ids)}; "
            f"deleted={_safe_int(result.get('deleted_count'), 0)}; "
            f"ids={deleted_ids[:100]}"
        ),
    )
    return jsonify({"ok": True, **result})


def _normalize_export_risk_level(raw: Any) -> str:
    text = _safe_text(raw).upper()
    mapping = {"NORMAL": "LOW", "LOW": "LOW", "ATTENTION": "MEDIUM", "MEDIUM": "MEDIUM", "HIGH": "HIGH"}
    return mapping.get(text, text if text in {"LOW", "MEDIUM", "HIGH"} else "")


def _normalize_export_verify_status(raw: Any) -> str:
    text = _safe_text(raw).upper()
    mapping = {"PASS": "PASS", "PASSED": "PASS", "FAIL": "FAIL", "FAILED": "FAIL", "PENDING": "PENDING"}
    return mapping.get(text, text if text in {"PASS", "FAIL", "PENDING"} else "")


@bp.get("/export")
@login_required
def export_excel():
    filters = {
        "ledger_date_start": _safe_text(request.args.get("ledger_date_start")),
        "ledger_date_end": _safe_text(request.args.get("ledger_date_end")),
        "expense_category": _safe_text(request.args.get("expense_category")),
        "risk_level": _normalize_export_risk_level(request.args.get("risk_level")),
        "verify_status": _normalize_export_verify_status(request.args.get("verify_status")),
        "keyword": _safe_text(request.args.get("keyword")),
        "reference_no": _safe_text(request.args.get("reference_no")),
    }
    scope_filter = _current_scope_filter()
    rows = list_all_invoices_for_export(
        record_state="LEDGER",
        filters=filters,
        data_scope=scope_filter,
    )
    for i, row in enumerate(rows[:50]):
        try:
            inv_id = int((row or {}).get("id", 0))
            if inv_id > 0:
                trace_id, _ = get_or_create_audit_trace("invoice", inv_id)
                append_audit_chain_event(trace_id, "EXPORT", {"format": "excel"}, "SYSTEM_AUTO")
        except Exception:
            pass
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.rename(
            columns={
                "id": "台账编号",
                "reference_no": "单据编号",
                "filename": "文件名",
                "amount": "金额",
                "invoice_date": "开票日期",
                "applicant": "报销人",
                "department": "部门",
                "currency": "币种",
                "risk_level": "规则风险等级",
                "risk_reason": "规则风险说明",
                "ai_risk_level": "AI风险等级",
                "ai_analysis_reason": "AI分析说明",
                "status": "审批状态",
                "record_state": "台账状态",
                "created_at": "入账时间",
                "is_canton_fair": "广交会标识",
                "hotel_limit": "酒店阈值",
                "mode": "来源模式",
                "submitter_department": "提交人部门",
                "submitter_name": "提交人姓名",
                "submitter_no": "提交人工号",
                "source": "来源系统",
                "verify_status": "验真状态",
                "verify_message": "验真说明",
                "verify_checked_at": "验真时间",
                "verify_count": "验真次数",
                "verify_provider": "验真渠道",
                "verify_request_id": "验真请求号",
                "verify_latency_ms": "验真耗时(ms)",
                "verify_status_code": "验真状态码",
                "approval_stage": "审批环节",
                "approval_status": "审批状态",
                "first_approver_id": "一级审批人",
                "second_approver_id": "二级审批人",
                "first_approved_at": "一级审批时间",
                "second_approved_at": "二级审批时间",
                "sla_due_at": "时限到期时间",
                "queue_owner_id": "队列归属",
                "rule_hit_id": "命中规则编号",
                "rule_explain": "风险说明",
                "ai_trace_id": "AI 追踪编号",
                "manual_rate": "手动汇率",
                "manual_cny_amount": "人民币金额",
                "fx_flag": "外币标识",
                "fx_reason": "外币说明",
            }
        )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="invoices")
    output.seek(0)

    today_text = date.today().strftime("%Y%m%d")
    return send_file(
        output,
        as_attachment=True,
        download_name=f"deepaudit_invoices_{today_text}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.get("/uploads/<path:filename>")
@login_required
def uploads_file(filename: str):
    safe_name = _normalize_filename(filename)
    if not safe_name:
        abort(404)
    _ensure_upload_dir()
    path = UPLOAD_DIR / safe_name
    if not path.is_file() and _is_seed_attachment_name(safe_name):
        ensure_seed_attachment_file(safe_name)
    if not path.is_file():
        abort(404)
    return send_from_directory(str(UPLOAD_DIR.resolve()), safe_name, as_attachment=False)


@bp.get("/invoices/health")
def health():
    return jsonify({"ok": True, "module": "invoices"})

