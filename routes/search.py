# -*- coding: utf-8 -*-
"""全局搜索路由 — 页面跳转 + JSON API（按权限/数据范围过滤）"""
from __future__ import annotations

import re
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from utils.db import get_conn
from utils.security import current_user, login_required, can_access_approval_console
from utils.data_scope_enforcer import get_enforced_data_scope

bp = Blueprint("search", __name__)

_SAFE_Q_RE = re.compile(r"[^\w\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s\-./]", re.UNICODE)
_MAX_LIMIT = 50
_DEFAULT_LIMIT = 20


def _sanitize_query(raw: str) -> str:
    return _SAFE_Q_RE.sub("", raw.strip())[:120]


def _build_scope_sql(
    scope: dict[str, Any],
    dept_col: str = "department",
    owner_col: str = "submitted_by_user_id",
) -> tuple[str, list[Any]]:
    """Return (WHERE fragment, params) enforcing data-scope on a table."""
    if scope.get("all_access"):
        return "", []

    clauses: list[str] = []
    params: list[Any] = []

    if scope.get("self_only"):
        uid = scope.get("owner_user_id")
        if uid:
            clauses.append(f"{owner_col} = ?")
            params.append(uid)
        else:
            clauses.append("1=0")
    elif scope.get("department_names"):
        depts = scope["department_names"]
        placeholders = ",".join("?" for _ in depts)
        clauses.append(f"{dept_col} IN ({placeholders})")
        params.extend(depts)

    allowed_ids = scope.get("allowed_user_ids") or []
    if allowed_ids and not scope.get("self_only"):
        placeholders = ",".join("?" for _ in allowed_ids)
        clauses.append(f"{owner_col} IN ({placeholders})")
        params.extend(allowed_ids)

    if not clauses:
        return "", []
    return " AND (" + " OR ".join(clauses) + ")", params


def _search_invoices(
    keyword: str,
    scope: dict[str, Any],
    limit: int,
    *,
    include_approval_location: bool = False,
) -> list[dict[str, Any]]:
    like = f"%{keyword}%"
    exact_match = keyword.strip()
    scope_sql, scope_params = _build_scope_sql(
        scope, dept_col="department", owner_col="submitted_by_user_id",
    )
    
    # 优先匹配：1. ID完全匹配 2. reference_no完全匹配 3. 其他匹配
    sql = (
        "SELECT id, reference_no, filename, amount, department, applicant, "
        "risk_level, status, approval_status, invoice_date, created_at, record_state, "
        "CASE "
        "  WHEN CAST(id AS TEXT) = ? THEN 1 "
        "  WHEN LOWER(COALESCE(reference_no,'')) = LOWER(?) THEN 2 "
        "  WHEN LOWER(COALESCE(reference_no,'')) LIKE LOWER(?) THEN 3 "
        "  WHEN LOWER(COALESCE(filename,'')) LIKE LOWER(?) THEN 4 "
        "  WHEN LOWER(COALESCE(applicant,'')) LIKE LOWER(?) THEN 5 "
        "  ELSE 6 "
        "END AS match_priority "
        "FROM invoices WHERE ("
        "  CAST(id AS TEXT) = ?"
        "  OR LOWER(COALESCE(reference_no,'')) = LOWER(?)"
        "  OR LOWER(COALESCE(reference_no,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(filename,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(applicant,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(department,'')) LIKE LOWER(?)"
        ")" + scope_sql + " ORDER BY match_priority ASC, id DESC LIMIT ?"
    )
    params: list[Any] = [
        exact_match, exact_match, like, like, like,  # match_priority计算
        exact_match, exact_match, like, like, like, like,  # WHERE条件
        *scope_params, limit
    ]
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        title = r["reference_no"] or r["filename"] or f"单据#{r['id']}"
        subtitle_parts = [
            r["department"] or "",
            r["applicant"] or "",
            f"¥{r['amount']}" if r["amount"] else "",
        ]
        record_state = str(r["record_state"] or "").strip().upper()
        active_tab = "draft" if record_state == "DRAFT" else "ledger"
        locations: list[dict[str, str]] = [
            {
                "key": "ledger",
                "label": "待补录" if active_tab == "draft" else "入账台账",
                "url": f"/ledger-center?tab={active_tab}&invoice_id={r['id']}",
            }
        ]
        approval_status = str(r["approval_status"] or r["status"] or "").strip().upper()
        if include_approval_location and record_state == "LEDGER" and approval_status == "PENDING":
            locations.append({
                "key": "approval",
                "label": "审批管理",
                "url": f"/approval_center?invoice_id={r['id']}",
            })
        results.append({
            "type": "invoice",
            "id": r["id"],
            "title": title,
            "subtitle": " · ".join(p for p in subtitle_parts if p),
            "url": locations[0]["url"],
            "locations": locations,
            "location_count": len(locations),
            "match_priority": r["match_priority"] if "match_priority" in r.keys() else 999,
        })
    return results


def _search_risk_cases(
    keyword: str, scope: dict[str, Any], limit: int,
) -> list[dict[str, Any]]:
    like = f"%{keyword}%"
    exact_match = keyword.strip()
    sql = (
        "SELECT rc.id, rc.status, rc.assigned_to, rc.created_at, "
        "re.risk_level, re.rule_summary, "
        "CASE "
        "  WHEN CAST(rc.id AS TEXT) = ? THEN 1 "
        "  WHEN LOWER(COALESCE(rc.assigned_to,'')) = LOWER(?) THEN 2 "
        "  WHEN LOWER(COALESCE(rc.assigned_to,'')) LIKE LOWER(?) THEN 3 "
        "  WHEN LOWER(COALESCE(re.rule_summary,'')) LIKE LOWER(?) THEN 4 "
        "  ELSE 5 "
        "END AS match_priority "
        "FROM risk_cases rc "
        "LEFT JOIN risk_events re ON re.id = rc.event_id "
        "WHERE ("
        "  CAST(rc.id AS TEXT) = ?"
        "  OR LOWER(COALESCE(rc.assigned_to,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(re.rule_summary,'')) LIKE LOWER(?)"
        ") ORDER BY match_priority ASC, rc.id DESC LIMIT ?"
    )
    with get_conn() as conn:
        rows = conn.execute(sql, [
            exact_match, exact_match, like, like,  # match_priority计算
            exact_match, like, like, limit  # WHERE条件
        ]).fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        title = f"风险案例 #{r['id']}"
        subtitle_parts = [
            r["status"] or "",
            r["assigned_to"] or "",
            r["rule_summary"][:40] if r["rule_summary"] else "",
        ]
        results.append({
            "type": "risk_case",
            "id": r["id"],
            "title": title,
            "subtitle": " · ".join(p for p in subtitle_parts if p),
            "url": f"/risk-center/case/{r['id']}",
            "match_priority": r["match_priority"] if "match_priority" in r.keys() else 999,
        })
    return results


def _search_bank_transactions(
    keyword: str, scope: dict[str, Any], limit: int,
) -> list[dict[str, Any]]:
    # 优先匹配ID
    try:
        exact_id = int(keyword)
        sql = (
            "SELECT id, txn_id, amount, counterparty, memo, ts "
            "FROM bank_transactions WHERE id = ? LIMIT 1"
        )
        with get_conn() as conn:
            row = conn.execute(sql, [exact_id]).fetchone()
            if row:
                r = row
                title = r["txn_id"] or f"交易#{r['id']}"
                subtitle_parts = [
                    r["counterparty"] or "",
                    f"¥{r['amount']}" if r["amount"] else "",
                    r["ts"] or "",
                ]
                return [{
                    "type": "bank_txn",
                    "id": r["id"],
                    "title": title,
                    "subtitle": " · ".join(p for p in subtitle_parts if p),
                    "url": f"/ledger-center?tab=bank&txn_id={r['id']}",
                }]
    except (ValueError, TypeError):
        pass
    
    # 完全匹配txn_id
    exact_txn_sql = (
        "SELECT id, txn_id, amount, counterparty, memo, ts "
        "FROM bank_transactions WHERE LOWER(COALESCE(txn_id,'')) = LOWER(?) LIMIT 1"
    )
    with get_conn() as conn:
        exact_txn_row = conn.execute(exact_txn_sql, [keyword]).fetchone()
        if exact_txn_row:
            r = exact_txn_row
            title = r["txn_id"] or f"交易#{r['id']}"
            subtitle_parts = [
                r["counterparty"] or "",
                f"¥{r['amount']}" if r["amount"] else "",
                r["ts"] or "",
            ]
            return [{
                "type": "bank_txn",
                "id": r["id"],
                "title": title,
                "subtitle": " · ".join(p for p in subtitle_parts if p),
                "url": f"/ledger-center?tab=bank&txn_id={r['id']}",
            }]
    
    # 模糊匹配，只返回第一条
    like = f"%{keyword}%"
    sql = (
        "SELECT id, txn_id, amount, counterparty, memo, ts "
        "FROM bank_transactions WHERE ("
        "  LOWER(COALESCE(txn_id,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(counterparty,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(memo,'')) LIKE LOWER(?)"
        ") ORDER BY id DESC LIMIT 1"
    )
    with get_conn() as conn:
        row = conn.execute(sql, [like, like, like]).fetchone()
    
    if not row:
        return []
    
    r = row
    title = r["txn_id"] or f"交易#{r['id']}"
    subtitle_parts = [
        r["counterparty"] or "",
        f"¥{r['amount']}" if r["amount"] else "",
        r["ts"] or "",
    ]
    return [{
        "type": "bank_txn",
        "id": r["id"],
        "title": title,
        "subtitle": " · ".join(p for p in subtitle_parts if p),
        "url": f"/ledger-center?tab=bank&txn_id={r['id']}",
    }]


def _search_governance_rules(
    keyword: str, limit: int,
) -> list[dict[str, Any]]:
    # 优先匹配ID
    try:
        exact_id = int(keyword)
        sql = (
            "SELECT id, rule_key, rule_name, severity, enabled "
            "FROM governance_rules WHERE id = ? LIMIT 1"
        )
        with get_conn() as conn:
            row = conn.execute(sql, [exact_id]).fetchone()
            if row:
                r = row
                state_label = "启用" if r["enabled"] else "停用"
                return [{
                    "type": "governance_rule",
                    "id": r["id"],
                    "title": r["rule_name"] or r["rule_key"],
                    "subtitle": f"{r['severity'] or ''} · {state_label}",
                    "url": "/governance-rules",
                }]
    except (ValueError, TypeError):
        pass
    
    # 完全匹配rule_key或rule_name
    exact_match_sql = (
        "SELECT id, rule_key, rule_name, severity, enabled "
        "FROM governance_rules WHERE ("
        "  LOWER(COALESCE(rule_name,'')) = LOWER(?)"
        "  OR LOWER(COALESCE(rule_key,'')) = LOWER(?)"
        ") LIMIT 1"
    )
    with get_conn() as conn:
        exact_row = conn.execute(exact_match_sql, [keyword, keyword]).fetchone()
        if exact_row:
            r = exact_row
            state_label = "启用" if r["enabled"] else "停用"
            return [{
                "type": "governance_rule",
                "id": r["id"],
                "title": r["rule_name"] or r["rule_key"],
                "subtitle": f"{r['severity'] or ''} · {state_label}",
                "url": "/governance-rules",
            }]
    
    # 模糊匹配，只返回第一条
    like = f"%{keyword}%"
    sql = (
        "SELECT id, rule_key, rule_name, severity, enabled "
        "FROM governance_rules WHERE ("
        "  LOWER(COALESCE(rule_name,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(rule_key,'')) LIKE LOWER(?)"
        ") ORDER BY id DESC LIMIT 1"
    )
    with get_conn() as conn:
        row = conn.execute(sql, [like, like]).fetchone()
    
    if not row:
        return []
    
    r = row
    state_label = "启用" if r["enabled"] else "停用"
    return [{
        "type": "governance_rule",
        "id": r["id"],
        "title": r["rule_name"] or r["rule_key"],
        "subtitle": f"{r['severity'] or ''} · {state_label}",
        "url": "/governance-rules",
    }]


TYPE_LABEL = {
    "invoice": "单据/发票",
    "risk_case": "风险案例",
    "bank_txn": "银行台账",
    "governance_rule": "治理规则",
}


@bp.get("/search")
@login_required
def search_page():
    q = _sanitize_query(request.args.get("q", ""))
    return render_template("search_results.html", q=q)


@bp.get("/api/search")
@login_required
def search_api():
    q = _sanitize_query(request.args.get("q", ""))
    if len(q) < 2:
        return jsonify({"results": [], "q": q, "total": 0})

    try:
        user = current_user()
        scope = get_enforced_data_scope(user)
        
        # 如果用户有审批权限，放宽数据范围限制（与审批管理页面保持一致）
        approval_console_access = False
        try:
            if can_access_approval_console(user):
                approval_console_access = True
                scope = {"all_access": True}
        except Exception:
            pass  # 如果检查权限失败，使用默认的 scope

        # 搜索所有类型，返回所有匹配结果
        # 每个类型最多返回 10 条，按优先级排序
        results: list[dict[str, Any]] = []
        
        invoice_results = _search_invoices(
            q,
            scope,
            10,
            include_approval_location=approval_console_access,
        )
        results.extend(invoice_results)
        
        risk_results = _search_risk_cases(q, scope, 10)
        results.extend(risk_results)
        
        bank_results = _search_bank_transactions(q, scope, 10)
        results.extend(bank_results)
        
        rule_results = _search_governance_rules(q, 10)
        results.extend(rule_results)
        
        # 按匹配优先级和类型优先级排序
        # 类型优先级：单据(1) > 风险案例(2) > 银行交易(3) > 治理规则(4)
        type_priority = {"invoice": 1, "risk_case": 2, "bank_txn": 3, "governance_rule": 4}
        results.sort(key=lambda x: (x.get("match_priority", 999), type_priority.get(x.get("type", ""), 999)))
        
        return jsonify({"results": results, "q": q, "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e), "results": [], "q": q, "total": 0}), 500
