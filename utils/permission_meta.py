from __future__ import annotations

from typing import Any, Iterable

PERMISSION_GROUPS: list[dict[str, str]] = [
    {
        "key": "DASHBOARD",
        "name_cn": "看板",
        "description_cn": "查看经营概览、统计报表与监控指标。",
    },
    {
        "key": "UPLOAD_LEDGER",
        "name_cn": "上传&台账",
        "description_cn": "处理单据上传、台账查看与流水能力。",
    },
    {
        "key": "RISK",
        "name_cn": "风险",
        "description_cn": "发起风险事件与风险案件。",
    },
    {
        "key": "APPROVAL",
        "name_cn": "审批",
        "description_cn": "执行审批分派与责任指派。",
    },
    {
        "key": "WORKFLOW",
        "name_cn": "流程",
        "description_cn": "处理流程节点推进与关单。",
    },
    {
        "key": "ORG",
        "name_cn": "组织权限",
        "description_cn": "维护人员、角色与组织授权。",
    },
    {
        "key": "SYSTEM",
        "name_cn": "系统设置",
        "description_cn": "维护规则、参数与系统级配置。",
    },
]

PERMISSION_META: dict[str, dict[str, str]] = {
    "VIEW_DASHBOARD": {
        "name_cn": "查看管理总览",
        "description_cn": "可查看管理看板、指标趋势与监控视图。",
        "group": "DASHBOARD",
    },
    "VIEW_BANK_STATS": {
        "name_cn": "查看银行流水统计",
        "description_cn": "可查看银行流水相关统计图表和汇总。",
        "group": "DASHBOARD",
    },
    "VIEW_UPLOAD_PAGE": {
        "name_cn": "仅可使用费用报销受理页面",
        "description_cn": "可访问费用报销受理页面并提交单据，不包含凭证台账中心权限。",
        "group": "UPLOAD_LEDGER",
    },
    "VIEW_INVOICES": {
        "name_cn": "查看凭证台账中心",
        "description_cn": "可查看凭证台账、单据详情以及台账相关操作。",
        "group": "UPLOAD_LEDGER",
    },
    "DELETE_INVOICE": {
        "name_cn": "删除台账单据",
        "description_cn": "可删除台账中的单据记录（高风险操作）。",
        "group": "UPLOAD_LEDGER",
    },
    "PULL_BANK_TXN": {
        "name_cn": "拉取银行流水",
        "description_cn": "可触发银行流水拉取并写入系统。",
        "group": "UPLOAD_LEDGER",
    },
    "BANK_PULL": {
        "name_cn": "拉取银行流水（兼容权限）",
        "description_cn": "历史兼容权限，等价于“拉取银行流水”。",
        "group": "UPLOAD_LEDGER",
    },
    "VIEW_AI_LEDGER": {
        "name_cn": "查看智能审计链",
        "description_cn": "可查看智能审计链台账、追踪信息与解释详情。",
        "group": "UPLOAD_LEDGER",
    },
    "CREATE_CASE": {
        "name_cn": "创建风险案件",
        "description_cn": "可从风险事件创建案件并进入处置流程。",
        "group": "RISK",
    },
    "ASSIGN_CASE": {
        "name_cn": "分派案件",
        "description_cn": "可分派案件责任人与审批处理人。",
        "group": "APPROVAL",
    },
    "CLOSE_CASE": {
        "name_cn": "关闭案件",
        "description_cn": "可结束流程并关闭案件。",
        "group": "WORKFLOW",
    },
    "MANAGE_USERS": {
        "name_cn": "人员与部门管理",
        "description_cn": "可新增用户、启停账号并维护部门组织。",
        "group": "ORG",
    },
    "DELETE_ANY_USER": {
        "name_cn": "删除任意用户",
        "description_cn": "可删除任意用户账号，包括有业务记录和审计记录的用户（高风险操作）。",
        "group": "ORG",
    },
    "MANAGE_ROLES": {
        "name_cn": "角色权限管理",
        "description_cn": "可维护角色、权限点与数据范围策略。",
        "group": "ORG",
    },
    "MANAGE_RULES": {
        "name_cn": "规则与政策管理",
        "description_cn": "可维护治理规则、阈值与策略。",
        "group": "SYSTEM",
    },
    "MANAGE_SETTINGS": {
        "name_cn": "系统参数管理",
        "description_cn": "可修改系统参数、平台配置与关键开关。",
        "group": "SYSTEM",
    },
    "MANAGE_SYSTEM": {
        "name_cn": "系统运维管理",
        "description_cn": "系统级运维权限，覆盖关键配置能力。",
        "group": "SYSTEM",
    },
    "VIEW_AUDIT_LOG": {
        "name_cn": "查看审计日志",
        "description_cn": "可查看系统操作审计日志与追踪记录。",
        "group": "SYSTEM",
    },
}

MENU_VISIBILITY_RULES: list[dict[str, Any]] = [
    {"id": "ops_dashboard", "name_cn": "管理总览", "group_cn": "业务运营", "mode": "any", "permissions": ["VIEW_DASHBOARD"]},
    {"id": "ops_upload", "name_cn": "费用报销受理", "group_cn": "业务运营", "mode": "any", "permissions": ["VIEW_UPLOAD_PAGE", "VIEW_INVOICES"]},
    {"id": "ops_ledger", "name_cn": "凭证台账中心", "group_cn": "业务运营", "mode": "any", "permissions": ["VIEW_INVOICES"]},
    {
        "id": "risk_center",
        "name_cn": "风险中心（事件/案件入口）",
        "group_cn": "风险与审批",
        "mode": "any",
        "permissions": ["CREATE_CASE", "ASSIGN_CASE", "CLOSE_CASE"],
    },
    {
        "id": "risk_approval",
        "name_cn": "审批管理",
        "group_cn": "风险与审批",
        "mode": "any",
        "permissions": ["VIEW_INVOICES", "ASSIGN_CASE", "CLOSE_CASE"],
    },
    {
        "id": "risk_workflow",
        "name_cn": "审批流程管理",
        "group_cn": "风险与审批",
        "mode": "any",
        "permissions": ["VIEW_INVOICES", "ASSIGN_CASE", "CLOSE_CASE"],
    },
    {"id": "org_users", "name_cn": "人员管理", "group_cn": "组织与权限", "mode": "any", "permissions": ["MANAGE_USERS"]},
    {"id": "org_roles", "name_cn": "角色权限", "group_cn": "组织与权限", "mode": "any", "permissions": ["MANAGE_ROLES"]},
    {"id": "org_departments", "name_cn": "部门管理", "group_cn": "组织与权限", "mode": "any", "permissions": ["MANAGE_USERS"]},
    {"id": "org_scope", "name_cn": "数据范围策略", "group_cn": "组织与权限", "mode": "any", "permissions": ["MANAGE_ROLES"]},
    {"id": "gov_rules", "name_cn": "规则与政策管理", "group_cn": "治理与规则", "mode": "any", "permissions": ["MANAGE_RULES"]},
    {"id": "gov_ai_ledger", "name_cn": "智能审计链", "group_cn": "治理与规则", "mode": "any", "permissions": ["VIEW_AI_LEDGER"]},
    {
        "id": "gov_sys_params",
        "name_cn": "系统参数",
        "group_cn": "治理与规则",
        "mode": "any",
        "permissions": ["MANAGE_SETTINGS", "MANAGE_SYSTEM"],
    },
    {
        "id": "monitor_logs",
        "name_cn": "操作日志",
        "group_cn": "系统监控",
        "mode": "any",
        "permissions": ["MANAGE_SETTINGS", "MANAGE_SYSTEM", "MANAGE_USERS", "MANAGE_ROLES", "MANAGE_RULES"],
    },
    {"id": "monitor_system", "name_cn": "系统监控", "group_cn": "系统监控", "mode": "any", "permissions": ["MANAGE_SYSTEM", "MANAGE_SETTINGS"]},
]

ACTION_PERMISSION_RULES: list[dict[str, Any]] = [
    {"id": "action_delete_invoice", "name_cn": "删除台账单据", "mode": "any", "permissions": ["DELETE_INVOICE"]},
    {"id": "action_pull_bank_txn", "name_cn": "拉取银行流水", "mode": "any", "permissions": ["PULL_BANK_TXN", "BANK_PULL"]},
    {"id": "action_create_case", "name_cn": "创建风险案件", "mode": "any", "permissions": ["CREATE_CASE"]},
    {"id": "action_assign_case", "name_cn": "分派案件", "mode": "any", "permissions": ["ASSIGN_CASE"]},
    {"id": "action_close_case", "name_cn": "关闭案件", "mode": "any", "permissions": ["CLOSE_CASE"]},
    {"id": "action_manage_users", "name_cn": "维护用户与部门", "mode": "any", "permissions": ["MANAGE_USERS"]},
    {"id": "action_manage_roles", "name_cn": "保存角色权限配置", "mode": "any", "permissions": ["MANAGE_ROLES"]},
    {"id": "action_manage_rules", "name_cn": "发布治理规则", "mode": "any", "permissions": ["MANAGE_RULES"]},
    {"id": "action_manage_settings", "name_cn": "修改系统参数", "mode": "any", "permissions": ["MANAGE_SETTINGS", "MANAGE_SYSTEM"]},
    {"id": "action_view_ai_ledger", "name_cn": "查看智能审计链", "mode": "any", "permissions": ["VIEW_AI_LEDGER"]},
]

ROLE_CHANGE_REASON_OPTIONS: list[dict[str, str]] = [
    {"value": "MANUAL_OVERRIDE", "label": "人工覆盖"},
    {"value": "DATA_CORRECTION", "label": "数据修正"},
    {"value": "POLICY_EXCEPTION", "label": "制度例外"},
    {"value": "NEED_MORE_INFO", "label": "需要补充信息"},
    {"value": "SYSTEM_AUTO", "label": "系统自动处理"},
]

FORBIDDEN_ROUTE_HINTS: list[dict[str, Any]] = [
    {
        "path_prefix": "/admin/roles",
        "module_name": "角色权限管理",
        "permissions": ["MANAGE_ROLES"],
    },
    {
        "path_prefix": "/admin/users",
        "module_name": "人员管理",
        "permissions": ["MANAGE_USERS"],
    },
    {
        "path_prefix": "/admin/departments",
        "module_name": "部门管理",
        "permissions": ["MANAGE_USERS"],
    },
    {
        "path_prefix": "/admin/data_scope",
        "module_name": "数据范围策略",
        "permissions": ["MANAGE_ROLES"],
    },
    {
        "path_prefix": "/governance/rules",
        "module_name": "规则与政策管理",
        "permissions": ["MANAGE_RULES"],
    },
    {
        "path_prefix": "/settings",
        "module_name": "系统参数",
        "permissions": ["MANAGE_SETTINGS", "MANAGE_SYSTEM"],
    },
    {
        "path_prefix": "/monitoring",
        "module_name": "系统监控",
        "permissions": ["MANAGE_SYSTEM", "MANAGE_SETTINGS"],
    },
    {
        "path_prefix": "/audit_chain",
        "module_name": "智能审计链",
        "permissions": ["VIEW_AI_LEDGER"],
    },
]


def normalize_permission_key(value: Any) -> str:
    return str(value or "").strip().upper()


def permission_groups() -> list[dict[str, str]]:
    return [dict(item) for item in PERMISSION_GROUPS]


def permission_label_cn(permission_key: Any) -> str:
    key = normalize_permission_key(permission_key)
    meta = PERMISSION_META.get(key) or {}
    label = str(meta.get("name_cn") or "").strip()
    return label or "未映射权限"


def permission_description_cn(permission_key: Any) -> str:
    key = normalize_permission_key(permission_key)
    meta = PERMISSION_META.get(key) or {}
    desc = str(meta.get("description_cn") or "").strip()
    return desc or "该权限尚未配置中文说明。"


def permission_group_key(permission_key: Any) -> str:
    key = normalize_permission_key(permission_key)
    meta = PERMISSION_META.get(key) or {}
    group_key = str(meta.get("group") or "").strip().upper()
    if not group_key:
        return "SYSTEM"
    return group_key


def permission_group_name(permission_key: Any) -> str:
    group_key = permission_group_key(permission_key)
    for group in PERMISSION_GROUPS:
        if normalize_permission_key(group.get("key")) == group_key:
            return str(group.get("name_cn") or "系统设置")
    return "系统设置"


def menu_visibility_rules() -> list[dict[str, Any]]:
    return [dict(item) for item in MENU_VISIBILITY_RULES]


def action_permission_rules() -> list[dict[str, Any]]:
    return [dict(item) for item in ACTION_PERMISSION_RULES]


def role_change_reason_options() -> list[dict[str, str]]:
    return [dict(item) for item in ROLE_CHANGE_REASON_OPTIONS]


def enrich_permission_rows(permission_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    group_order = {normalize_permission_key(item.get("key")): idx for idx, item in enumerate(PERMISSION_GROUPS, start=1)}
    normalized_rows: list[dict[str, Any]] = []
    for row in permission_rows or []:
        item = dict(row or {})
        key = normalize_permission_key(item.get("permission_key"))
        normalized_rows.append(
            {
                "id": int(item.get("id") or 0),
                "permission_key": key,
                "raw_description": str(item.get("description") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "name_cn": permission_label_cn(key),
                "description_cn": permission_description_cn(key),
                "group_key": permission_group_key(key),
                "group_name_cn": permission_group_name(key),
                "group_order": group_order.get(permission_group_key(key), 999),
            }
        )

    normalized_rows.sort(key=lambda item: (int(item.get("group_order") or 999), int(item.get("id") or 0), str(item.get("permission_key") or "")))
    return normalized_rows


def summarize_permission_names(permission_keys: Iterable[str], *, limit: int = 3) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for raw_key in permission_keys or []:
        key = normalize_permission_key(raw_key)
        if not key or key in seen:
            continue
        seen.add(key)
        labels.append(permission_label_cn(key))
    if not labels:
        return "无"
    if len(labels) <= max(1, int(limit)):
        return "、".join(labels)
    head = "、".join(labels[: max(1, int(limit))])
    return f"{head} 等 {len(labels)} 项"


def resolve_forbidden_hint(path: str, permission_key: str | None = None) -> tuple[str, list[str]]:
    target_path = str(path or "").strip()
    for item in FORBIDDEN_ROUTE_HINTS:
        prefix = str(item.get("path_prefix") or "").strip()
        if prefix and target_path.startswith(prefix):
            module_name = str(item.get("module_name") or "目标模块").strip() or "目标模块"
            required_permissions = [normalize_permission_key(key) for key in item.get("permissions") or [] if normalize_permission_key(key)]
            return module_name, required_permissions

    key = normalize_permission_key(permission_key)
    if key:
        return "权限受限页面", [key]
    return "权限受限页面", []
