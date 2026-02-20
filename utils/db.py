# utils/db.py
# -*- coding: utf-8 -*-

import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from werkzeug.security import check_password_hash, generate_password_hash
from utils.status_i18n import (
    localize_status_snapshot,
    to_cn_ledger_action,
    to_cn_reason_code,
    with_cn_status_fields,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 支持从 DATABASE_URL 环境变量读取数据库路径
# 格式：sqlite:///database.db 或 sqlite:///path/to/database.db
def _get_db_path_from_env() -> str:
    """从环境变量解析数据库路径，优先级：DATABASE_URL > DB_PATH > 默认值"""
    # 优先读取 DATABASE_URL（SQLAlchemy 格式）
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        # 解析 sqlite:///xxx.db 格式
        if database_url.startswith("sqlite:///"):
            db_file = database_url[10:]  # 去掉 "sqlite:///"
            if db_file:
                # 如果是相对路径，相对于项目根目录
                if not os.path.isabs(db_file):
                    return os.path.abspath(str(PROJECT_ROOT / db_file))
                return os.path.abspath(db_file)
    
    # 兼容旧的 DB_PATH 环境变量
    db_path = os.getenv("DB_PATH", "").strip()
    if db_path:
        return os.path.abspath(db_path)
    
    # 默认值
    return os.path.abspath(str(PROJECT_ROOT / "database.db"))

DB_PATH = _get_db_path_from_env()

# 启动时打印数据库路径（仅打印一次）
if not os.getenv("_DB_PATH_LOGGED"):
    os.environ["_DB_PATH_LOGGED"] = "1"
    print(f"[utils.db] DB_PATH 初始化完成: {DB_PATH}")
    print(f"[utils.db] 数据库文件存在: {os.path.exists(DB_PATH)}")

REQUIRED_APPROVAL_COLUMNS = {"status", "applicant", "department"}
DEFAULT_SYSTEM_SETTINGS: Dict[str, Any] = {
    "risk": {
        "amount_warning_threshold": 5000,
        "tier1_hotel_limit": 600,
        "sensitive_words": ["KTV", "按摩", "礼品卡", "茅台"],
        "block_duplicate": True,
        "detect_serial": True,
    },
    "org": {
        "role_based_access": True,
        "approval_chain": "department_manager",
        "cross_department_visibility": False,
    },
    "integration": {
        "email_enabled": True,
        "sms_enabled": False,
        "wecom_enabled": True,
        "webhook_url": "",
    },
    "workflow": {
        "ai_model_param": "balanced",
        "confidence_threshold": 0.85,
        "auto_reject": True,
        "ai_trust_mode": False,
        "amount_limit": 5000,
    },
}
WORKFLOW_STEP_CODES = ("A", "B", "C")
WORKFLOW_DEST_CODES = ("A", "B", "C", "END")
WORKFLOW_STATUS_DRAFT = "DRAFT"
WORKFLOW_STATUS_PUBLISHED = "PUBLISHED"

# 闭环流程状态定义
INVOICE_STATUS_DRAFT = "DRAFT"
INVOICE_STATUS_UPLOADED = "UPLOADED"
INVOICE_STATUS_OCR_COMPLETED = "OCR_COMPLETED"
INVOICE_STATUS_AI_AUDITED = "AI_AUDITED"
INVOICE_STATUS_RISK_ASSESSED = "RISK_ASSESSED"
INVOICE_STATUS_APPROVAL_PENDING = "APPROVAL_PENDING"
INVOICE_STATUS_APPROVED = "APPROVED"
INVOICE_STATUS_REJECTED = "REJECTED"
INVOICE_STATUS_EXECUTED = "EXECUTED"
INVOICE_STATUS_MONITORED = "MONITORED"
INVOICE_STATUS_CLOSED = "CLOSED"

# 闭环流程状态集合
INVOICE_STATUS_SET = {
    INVOICE_STATUS_DRAFT,
    INVOICE_STATUS_UPLOADED,
    INVOICE_STATUS_OCR_COMPLETED,
    INVOICE_STATUS_AI_AUDITED,
    INVOICE_STATUS_RISK_ASSESSED,
    INVOICE_STATUS_APPROVAL_PENDING,
    INVOICE_STATUS_APPROVED,
    INVOICE_STATUS_REJECTED,
    INVOICE_STATUS_EXECUTED,
    INVOICE_STATUS_MONITORED,
    INVOICE_STATUS_CLOSED,
}

# 状态流转规则（允许的状态转换）
INVOICE_STATUS_TRANSITIONS: dict[str, set[str]] = {
    INVOICE_STATUS_DRAFT: {INVOICE_STATUS_UPLOADED},
    INVOICE_STATUS_UPLOADED: {INVOICE_STATUS_OCR_COMPLETED},
    INVOICE_STATUS_OCR_COMPLETED: {INVOICE_STATUS_AI_AUDITED},
    INVOICE_STATUS_AI_AUDITED: {INVOICE_STATUS_RISK_ASSESSED},
    INVOICE_STATUS_RISK_ASSESSED: {INVOICE_STATUS_APPROVAL_PENDING},
    INVOICE_STATUS_APPROVAL_PENDING: {INVOICE_STATUS_APPROVED, INVOICE_STATUS_REJECTED},
    INVOICE_STATUS_APPROVED: {INVOICE_STATUS_EXECUTED},
    INVOICE_STATUS_REJECTED: {INVOICE_STATUS_CLOSED},
    INVOICE_STATUS_EXECUTED: {INVOICE_STATUS_MONITORED},
    INVOICE_STATUS_MONITORED: {INVOICE_STATUS_CLOSED},
    INVOICE_STATUS_CLOSED: set(),  # 终态，不允许再转换
}


def normalize_invoice_status(value: Any, *, fallback: str = INVOICE_STATUS_DRAFT) -> str:
    """规范化发票状态"""
    text = _safe_text(value).upper()
    if text in INVOICE_STATUS_SET:
        return text
    return fallback if fallback in INVOICE_STATUS_SET else INVOICE_STATUS_DRAFT


def can_transition_status(from_status: str, to_status: str) -> bool:
    """检查状态转换是否允许"""
    from_status = normalize_invoice_status(from_status)
    to_status = normalize_invoice_status(to_status)
    allowed = INVOICE_STATUS_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def get_next_valid_statuses(current_status: str) -> list[str]:
    """获取当前状态可以转换到的下一状态列表"""
    current_status = normalize_invoice_status(current_status)
    return list(INVOICE_STATUS_TRANSITIONS.get(current_status, set()))
DEFAULT_WORKFLOW_CONSOLE_CONFIG: Dict[str, Any] = {
    "chain": ["START", "A", "B", "C", "END"],
    "nodes": {
        "A": {
            "required_role": "AI_SENTINEL",
            "conditions": {
                "amount_gte": 0,
                "risk_levels": ["LOW", "MEDIUM", "HIGH"],
                "rule_hit_count_gte": 0,
            },
            "next_map": {
                "approve": "B",
                "return": "END",
                "assign": "B",
                "false_positive": "END",
                "close": "END",
            },
        },
        "B": {
            "required_role": "MANAGER",
            "conditions": {
                "amount_gte": 0,
                "risk_levels": ["LOW", "MEDIUM", "HIGH"],
                "rule_hit_count_gte": 0,
            },
            "next_map": {
                "approve": "C",
                "return": "A",
                "assign": "B",
                "false_positive": "END",
                "close": "END",
            },
        },
        "C": {
            "required_role": "CFO",
            "conditions": {
                "amount_gte": 5000,
                "risk_levels": ["HIGH"],
                "rule_hit_count_gte": 2,
            },
            "next_map": {
                "approve": "END",
                "return": "B",
                "assign": "C",
                "false_positive": "END",
                "close": "END",
            },
        },
    },
}
REFERENCE_NO_PREFIX = "EXP"
USER_STATUS_ACTIVE = "ACTIVE"
USER_STATUS_DISABLED = "DISABLED"
DEFAULT_RESET_PASSWORD = os.getenv("DEFAULT_RESET_PASSWORD", "ChangeMe!2026")
DEPARTMENT_STATUS_ACTIVE = "ACTIVE"
DEPARTMENT_STATUS_DISABLED = "DISABLED"
POSITION_STATUS_ACTIVE = "ACTIVE"
POSITION_STATUS_DISABLED = "DISABLED"
DATA_SCOPE_ALL = "ALL"
DATA_SCOPE_DEPT = "DEPT"
DATA_SCOPE_DEPT_TREE = "DEPT_TREE"
DATA_SCOPE_DEPT_WHITELIST = "DEPT_WHITELIST"
DATA_SCOPE_SELF = "SELF"
DATA_SCOPE_SELF_SUB = "SELF_SUB"  # 本人+下属
DATA_SCOPE_USER_WHITELIST = "USER_WHITELIST"  # 指定人员
DATA_SCOPE_TYPES = {
    DATA_SCOPE_SELF,
    DATA_SCOPE_SELF_SUB,
    DATA_SCOPE_DEPT,
    DATA_SCOPE_DEPT_TREE,
    DATA_SCOPE_DEPT_WHITELIST,
    DATA_SCOPE_USER_WHITELIST,
    DATA_SCOPE_ALL,
}
DEFAULT_PERMISSIONS: list[tuple[str, str]] = [
    ("VIEW_DASHBOARD", "View dashboard pages and metrics"),
    ("VIEW_INVOICES", "View invoice ledger data"),
    ("CREATE_CASE", "Create risk cases from risk events"),
    ("ASSIGN_CASE", "Assign risk cases"),
    ("CLOSE_CASE", "Close risk cases"),
    ("VIEW_AI_LEDGER", "View AI prompt ledger details"),
    ("MANAGE_USERS", "Create or disable users"),
    ("MANAGE_ROLES", "Manage role permissions"),
]
DEFAULT_ROLES: list[dict[str, Any]] = [
    {
        "role_name": "管理员",
        "data_scope": DATA_SCOPE_ALL,
        "permissions": [item[0] for item in DEFAULT_PERMISSIONS],
    },
    {
        "role_name": "财务专员",
        "data_scope": DATA_SCOPE_DEPT,
        "permissions": ["VIEW_DASHBOARD", "VIEW_INVOICES", "VIEW_AI_LEDGER"],
    },
    {
        "role_name": "风控专员",
        "data_scope": DATA_SCOPE_DEPT,
        "permissions": [
            "VIEW_DASHBOARD",
            "VIEW_INVOICES",
            "CREATE_CASE",
            "ASSIGN_CASE",
            "CLOSE_CASE",
            "VIEW_AI_LEDGER",
        ],
    },
    {
        "role_name": "财务经理",
        "data_scope": DATA_SCOPE_DEPT,
        "permissions": [
            "VIEW_DASHBOARD",
            "VIEW_INVOICES",
            "CREATE_CASE",
            "ASSIGN_CASE",
            "CLOSE_CASE",
            "VIEW_AI_LEDGER",
            "MANAGE_USERS",
            "MANAGE_ROLES",
        ],
    },
]
DEFAULT_GOVERNANCE_RULES: list[dict[str, Any]] = [
    {
        "rule_key": "AMOUNT_WARNING_THRESHOLD",
        "rule_name": "Amount Warning Threshold",
        "threshold": 5000.0,
    },
    {
        "rule_key": "DUPLICATE_EXPENSE_THRESHOLD",
        "rule_name": "Duplicate Expense Threshold",
        "threshold": 2.0,
    },
    {
        "rule_key": "HIGH_RISK_SCORE_THRESHOLD",
        "rule_name": "High Risk Score Threshold",
        "threshold": 85.0,
    },
]

# Stage-5 security/governance baseline overrides.
# 弱密码检测：从环境变量读取，如果未设置则不进行弱密码检测
# 注意：生产环境应移除此默认值，强制使用强密码策略
DEFAULT_WEAK_PASSWORD = os.getenv("DEFAULT_WEAK_PASSWORD", "")
DEFAULT_RESET_PASSWORD = os.getenv("DEFAULT_RESET_PASSWORD", "ChangeMe!2026")
LOGIN_LOCK_MAX_FAILURES = 5
LOGIN_LOCK_MINUTES = 10
LOGIN_LOCK_WINDOW_MINUTES = 10

DEFAULT_PERMISSIONS = [
    ("VIEW_DASHBOARD", "View dashboard pages and metrics"),
    ("VIEW_INVOICES", "View invoice ledger data"),
    ("CREATE_CASE", "Create risk cases from risk events"),
    ("ASSIGN_CASE", "Assign risk cases"),
    ("CLOSE_CASE", "Close risk cases"),
    ("DELETE_INVOICE", "Delete invoices from ledger"),
    ("PULL_BANK_TXN", "Pull bank transactions from provider"),
    ("VIEW_BANK_STATS", "View bank transaction statistics"),
    ("MANAGE_SETTINGS", "Manage system settings and platform parameters"),
    ("VIEW_AUDIT_LOG", "View audit log and system operation records"),
    # Legacy aliases, retained for backward compatibility.
    ("BANK_PULL", "Pull bank transactions from provider"),
    ("VIEW_AI_LEDGER", "View AI prompt ledger details"),
    ("MANAGE_USERS", "Create or disable users"),
    ("MANAGE_ROLES", "Manage role permissions"),
    ("MANAGE_RULES", "Manage governance rules and thresholds"),
    ("MANAGE_SYSTEM", "Manage system settings and platform parameters"),
]

ROLE_SYSTEM_ADMIN = "系统管理员"
ROLE_LEGACY_ADMIN = "管理员"
ROLE_FINANCE_SPECIALIST = "财务专员"
ROLE_RISK_SPECIALIST = "风控专员"
ROLE_FINANCE_MANAGER = "财务经理"
ROLE_GOVERNANCE_ADMIN = "治理管理员"
ROLE_EMPLOYEE_GENERAL = "通用员工"

DEFAULT_ROLES = [
    {
        "role_name": ROLE_SYSTEM_ADMIN,
        "legacy_names": [ROLE_LEGACY_ADMIN],
        "data_scope": DATA_SCOPE_ALL,
        # 系统管理员拥有所有权限 - 在代码层面通过 is_system_admin() 检查自动授予所有权限
        # 这里列出所有权限以确保数据库中也正确记录，便于审计和权限管理
        "permissions": [
            "VIEW_DASHBOARD",
            "VIEW_BANK_STATS",
            "VIEW_INVOICES",
            "CREATE_CASE",
            "ASSIGN_CASE",
            "CLOSE_CASE",
            "DELETE_INVOICE",
            "PULL_BANK_TXN",
            "BANK_PULL",
            "VIEW_AI_LEDGER",
            "MANAGE_USERS",
            "MANAGE_ROLES",
            "MANAGE_RULES",
            "MANAGE_SETTINGS",
            "MANAGE_SYSTEM",
        ],
    },
    {
        "role_name": ROLE_FINANCE_SPECIALIST,
        "data_scope": DATA_SCOPE_DEPT,
        "permissions": ["VIEW_DASHBOARD", "VIEW_BANK_STATS", "VIEW_INVOICES"],
    },
    {
        "role_name": ROLE_RISK_SPECIALIST,
        "data_scope": DATA_SCOPE_DEPT,
        "permissions": ["VIEW_DASHBOARD", "VIEW_BANK_STATS", "VIEW_INVOICES", "CREATE_CASE", "ASSIGN_CASE", "CLOSE_CASE"],
    },
    {
        "role_name": ROLE_FINANCE_MANAGER,
        "data_scope": DATA_SCOPE_DEPT,
        "permissions": [
            "VIEW_DASHBOARD",
            "VIEW_BANK_STATS",
            "VIEW_INVOICES",
            "CREATE_CASE",
            "ASSIGN_CASE",
            "CLOSE_CASE",
            "DELETE_INVOICE",
        ],
    },
    {
        "role_name": ROLE_GOVERNANCE_ADMIN,
        "data_scope": DATA_SCOPE_ALL,
        "permissions": ["MANAGE_RULES", "VIEW_AI_LEDGER"],
    },
    {
        "role_name": ROLE_EMPLOYEE_GENERAL,
        "data_scope": DATA_SCOPE_SELF,
        "permissions": ["VIEW_DASHBOARD"],
    },
]
DEFAULT_GOVERNANCE_RULES = [
    {
        "rule_key": "HOTEL_LIMIT_NORMAL",
        "rule_name": "Hotel Limit (Normal)",
        "threshold": 500.0,
        "threshold_json": {"limit": 500.0},
        "severity": "HIGH",
    },
    {
        "rule_key": "HOTEL_LIMIT_CANTON_FAIR",
        "rule_name": "Hotel Limit (Canton Fair)",
        "threshold": 1000.0,
        "threshold_json": {"limit": 1000.0},
        "severity": "HIGH",
    },
    {
        "rule_key": "HOTEL_MEDIUM_RATIO",
        "rule_name": "Hotel Medium Risk Ratio",
        "threshold": 0.9,
        "threshold_json": {"ratio": 0.9},
        "severity": "MEDIUM",
    },
    {
        "rule_key": "AMOUNT_WARNING_THRESHOLD",
        "rule_name": "Amount Warning Threshold",
        "threshold": 5000.0,
        "threshold_json": {"threshold": 5000.0},
        "severity": "MEDIUM",
    },
    {
        "rule_key": "DUPLICATE_EXPENSE_THRESHOLD",
        "rule_name": "Duplicate Expense Threshold",
        "threshold": 2.0,
        "threshold_json": {"count": 2.0},
        "severity": "MEDIUM",
    },
    {
        "rule_key": "HIGH_RISK_SCORE_THRESHOLD",
        "rule_name": "High Risk Score Threshold",
        "threshold": 85.0,
        "threshold_json": {"score": 85.0},
        "severity": "HIGH",
    },
]
DEFAULT_GOVERNANCE_RULES_BY_KEY: dict[str, dict[str, Any]] = {
    str(item.get("rule_key") or "").strip().upper(): item for item in DEFAULT_GOVERNANCE_RULES
}
RECORD_STATE_DRAFT = "DRAFT"
RECORD_STATE_LEDGER = "LEDGER"
RECORD_STATE_SET = {RECORD_STATE_DRAFT, RECORD_STATE_LEDGER}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_add_column(conn: sqlite3.Connection, ddl: str) -> None:
    try:
        conn.execute(ddl)
    except sqlite3.OperationalError:
        # Column already exists.
        pass


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    # 安全验证：只允许字母、数字、下划线，防止 SQL 注入
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    # 使用参数化查询（虽然 PRAGMA 不支持参数化，但我们已经验证了表名）
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    names: set[str] = set()
    for row in rows:
        if isinstance(row, sqlite3.Row):
            names.add(str(row["name"]))
        else:
            names.add(str(row[1]))
    return names


def _safe_json_loads(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def normalize_record_state(value: Any, *, fallback: str = RECORD_STATE_DRAFT) -> str:
    text = _safe_text(value).upper()
    if text in RECORD_STATE_SET:
        return text
    return fallback if fallback in RECORD_STATE_SET else RECORD_STATE_DRAFT


def _has_ledger_required_fields(amount: Any, invoice_date: Any) -> bool:
    amount_text = _safe_text(amount)
    date_text = _safe_text(invoice_date)
    if not amount_text or not date_text:
        return False

    cleaned_amount = re.sub(r"[^\d.\-]", "", amount_text.replace(",", ""))
    if not cleaned_amount:
        return False
    try:
        float(cleaned_amount)
    except Exception:
        return False

    normalized_date = (
        date_text.replace(".", "-")
        .replace("/", "-")
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
    )
    try:
        datetime.strptime(normalized_date, "%Y-%m-%d")
    except Exception:
        return False
    return True


def resolve_record_state(*, amount: Any, invoice_date: Any, preferred: Any = None) -> str:
    preferred_state = normalize_record_state(preferred, fallback=RECORD_STATE_DRAFT)
    if not _has_ledger_required_fields(amount, invoice_date):
        return RECORD_STATE_DRAFT
    if preferred_state == RECORD_STATE_LEDGER:
        return RECORD_STATE_LEDGER
    return RECORD_STATE_DRAFT


def _format_amount_for_business_text(value: Any) -> str:
    raw_text = _safe_text(value)
    if not raw_text:
        return "-"
    cleaned = re.sub(r"[^\d.\-]", "", raw_text.replace(",", ""))
    if not cleaned:
        return raw_text
    try:
        numeric = float(cleaned)
    except Exception:
        return raw_text
    return f"{numeric:,.2f}"


def to_business_risk_reason(
    reason: Any,
    *,
    source: Any = None,
    amount: Any = None,
    threshold: Any = None,
) -> str:
    reason_text = _safe_text(reason)
    reason_lower = reason_text.lower()
    source_text = _safe_text(source).lower()

    if "seed" in reason_lower or source_text in {"demo", "demo_seed", "seed"}:
        return "系统演示数据（不计入真实统计）"

    if "信息缺失" in reason_text or "missing" in reason_lower:
        return "凭证要素不全（缺：金额/日期），需补录后复核"

    if "超限" in reason_text or "over limit" in reason_lower or "limit" in reason_lower:
        actual_text = _format_amount_for_business_text(amount)
        threshold_text = _format_amount_for_business_text(threshold)
        return f"差旅住宿超标（实际 {actual_text} > 标准 {threshold_text}），需按制度特批"

    return reason_text


def _rule_threshold_field(rule_key: str) -> str:
    mapping = {
        "HOTEL_LIMIT_NORMAL": "limit",
        "HOTEL_LIMIT_CANTON_FAIR": "limit",
        "HOTEL_MEDIUM_RATIO": "ratio",
        "DUPLICATE_EXPENSE_THRESHOLD": "count",
        "HIGH_RISK_SCORE_THRESHOLD": "score",
    }
    return mapping.get(str(rule_key or "").strip().upper(), "threshold")


def _normalize_rule_severity(value: Any, *, fallback: str = "MEDIUM") -> str:
    text = str(value or "").strip().upper()
    if text in {"LOW", "MEDIUM", "HIGH"}:
        return text
    try:
        numeric = float(value)
    except Exception:
        return fallback
    if numeric >= 80:
        return "HIGH"
    if numeric >= 40:
        return "MEDIUM"
    return "LOW"


def _default_threshold_payload(rule_key: str, fallback_threshold: Any = None) -> dict[str, Any]:
    key = str(rule_key or "").strip().upper()
    seed = DEFAULT_GOVERNANCE_RULES_BY_KEY.get(key) or {}
    default_payload = seed.get("threshold_json")
    if isinstance(default_payload, dict):
        payload = dict(default_payload)
    else:
        payload = {}

    threshold_value: float | None = None
    if fallback_threshold is not None:
        try:
            threshold_value = float(fallback_threshold)
        except Exception:
            threshold_value = None
    if threshold_value is None:
        try:
            threshold_value = float(seed.get("threshold", 0))
        except Exception:
            threshold_value = 0.0

    if not payload:
        payload[_rule_threshold_field(key)] = threshold_value
    return payload


def _normalize_threshold_payload(rule_key: str, payload: Any, *, fallback_threshold: Any = None) -> dict[str, Any]:
    if isinstance(payload, dict):
        candidate = dict(payload)
    elif isinstance(payload, str):
        loaded = _safe_json_loads(payload)
        candidate = dict(loaded) if isinstance(loaded, dict) else {}
    else:
        candidate = {}

    if not candidate:
        return _default_threshold_payload(rule_key, fallback_threshold)

    field = _rule_threshold_field(rule_key)
    if field not in candidate:
        try:
            candidate[field] = float(fallback_threshold)
        except Exception:
            pass
    return candidate


def _extract_threshold_value(rule_key: str, payload: dict[str, Any], fallback: Any = 0) -> float:
    field = _rule_threshold_field(rule_key)
    candidates: list[Any] = [payload.get(field), payload.get("threshold"), payload.get("value")]
    for value in payload.values():
        if isinstance(value, (int, float)):
            candidates.append(value)

    for value in candidates:
        try:
            return float(value)
        except Exception:
            continue
    try:
        return float(fallback)
    except Exception:
        return 0.0


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _workflow_now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_workflow_risk_levels(value: Any, fallback: list[str]) -> list[str]:
    levels: list[str] = []
    if isinstance(value, (list, tuple, set)):
        for item in value:
            level = _safe_text(item).upper()
            if level in {"LOW", "MEDIUM", "HIGH"} and level not in levels:
                levels.append(level)
    if levels:
        return levels

    fallback_levels: list[str] = []
    for item in fallback:
        level = _safe_text(item).upper()
        if level in {"LOW", "MEDIUM", "HIGH"} and level not in fallback_levels:
            fallback_levels.append(level)
    return fallback_levels or ["LOW", "MEDIUM", "HIGH"]


def _normalize_workflow_next_map(value: Any, fallback: dict[str, Any]) -> dict[str, str]:
    source = dict(value) if isinstance(value, dict) else {}
    result: dict[str, str] = {}
    for action in ("approve", "return", "assign", "false_positive", "close"):
        default_dest = _safe_text(fallback.get(action), "END").upper()
        if default_dest not in WORKFLOW_DEST_CODES:
            default_dest = "END"
        dest = _safe_text(source.get(action), default_dest).upper()
        if dest not in WORKFLOW_DEST_CODES:
            dest = default_dest
        result[action] = dest
    return result


def _normalize_workflow_node(step: str, node: Any, fallback_node: dict[str, Any]) -> dict[str, Any]:
    source = dict(node) if isinstance(node, dict) else {}
    fallback_required_role = _safe_text(fallback_node.get("required_role"), "MANAGER")
    required_role = _safe_text(source.get("required_role"), fallback_required_role).upper() or fallback_required_role

    fallback_conditions = fallback_node.get("conditions")
    fallback_conditions_map = dict(fallback_conditions) if isinstance(fallback_conditions, dict) else {}
    source_conditions = source.get("conditions")
    source_conditions_map = dict(source_conditions) if isinstance(source_conditions, dict) else {}

    try:
        amount_gte = float(source_conditions_map.get("amount_gte", fallback_conditions_map.get("amount_gte", 0)))
    except Exception:
        amount_gte = float(fallback_conditions_map.get("amount_gte", 0) or 0)
    if amount_gte < 0:
        amount_gte = 0.0

    try:
        rule_hit_count_gte = int(
            source_conditions_map.get(
                "rule_hit_count_gte",
                fallback_conditions_map.get("rule_hit_count_gte", 0),
            )
        )
    except Exception:
        rule_hit_count_gte = int(fallback_conditions_map.get("rule_hit_count_gte", 0) or 0)
    if rule_hit_count_gte < 0:
        rule_hit_count_gte = 0

    risk_levels = _normalize_workflow_risk_levels(
        source_conditions_map.get("risk_levels"),
        list(fallback_conditions_map.get("risk_levels") or []),
    )

    fallback_next_map = fallback_node.get("next_map")
    fallback_next_map_obj = dict(fallback_next_map) if isinstance(fallback_next_map, dict) else {}
    next_map = _normalize_workflow_next_map(source.get("next_map"), fallback_next_map_obj)

    return {
        "step": step,
        "required_role": required_role,
        "conditions": {
            "amount_gte": amount_gte,
            "risk_levels": risk_levels,
            "rule_hit_count_gte": rule_hit_count_gte,
        },
        "next_map": next_map,
    }


def normalize_workflow_config(config: Any) -> dict[str, Any]:
    source = dict(config) if isinstance(config, dict) else {}
    source_nodes = source.get("nodes")
    source_nodes_map = dict(source_nodes) if isinstance(source_nodes, dict) else {}
    default_nodes = dict(DEFAULT_WORKFLOW_CONSOLE_CONFIG.get("nodes") or {})

    normalized_nodes: dict[str, Any] = {}
    for step in WORKFLOW_STEP_CODES:
        fallback_node_raw = default_nodes.get(step)
        fallback_node = dict(fallback_node_raw) if isinstance(fallback_node_raw, dict) else {}
        normalized_nodes[step] = _normalize_workflow_node(step, source_nodes_map.get(step), fallback_node)

    return {
        "chain": list(DEFAULT_WORKFLOW_CONSOLE_CONFIG.get("chain") or ["START", "A", "B", "C", "END"]),
        "nodes": normalized_nodes,
    }


def _seed_workflow_config_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS c FROM workflow_config").fetchone()
    count = int(row["c"] or 0) if row else 0
    if count > 0:
        return

    conn.execute(
        """
        INSERT INTO workflow_config (version, status, config_json, scope, reason, "by", at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            WORKFLOW_STATUS_PUBLISHED,
            json.dumps(normalize_workflow_config(DEFAULT_WORKFLOW_CONSOLE_CONFIG), ensure_ascii=False),
            "ALL",
            "SYSTEM_BOOTSTRAP",
            "system",
            _workflow_now_text(),
        ),
    )


def _reference_date_part(created_at: Any) -> str:
    text = str(created_at or "").strip()
    if text:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y%m%d")
            except Exception:
                continue
        if len(text) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", text[:10]):
            return text[:10].replace("-", "")
    return datetime.now().strftime("%Y%m%d")


def _next_reference_no(conn: sqlite3.Connection, created_at: Any) -> str:
    date_part = _reference_date_part(created_at)
    prefix = f"{REFERENCE_NO_PREFIX}-{date_part}-"
    rows = conn.execute(
        "SELECT reference_no FROM invoices WHERE reference_no LIKE ?",
        (f"{prefix}%",),
    ).fetchall()

    max_seq = 0
    for row in rows:
        raw_ref = row["reference_no"] if isinstance(row, sqlite3.Row) else row[0]
        ref_text = str(raw_ref or "").strip()
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", ref_text)
        if not m:
            continue
        try:
            max_seq = max(max_seq, int(m.group(1)))
        except Exception:
            continue
    seq = max_seq + 1

    while True:
        candidate = f"{prefix}{seq:04d}"
        exists = conn.execute(
            "SELECT 1 FROM invoices WHERE reference_no = ? LIMIT 1",
            (candidate,),
        ).fetchone()
        if not exists:
            return candidate
        seq += 1


def _backfill_reference_no(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, created_at FROM invoices "
        "WHERE reference_no IS NULL OR TRIM(reference_no) = '' "
        "ORDER BY datetime(created_at) ASC, id ASC"
    ).fetchall()
    for row in rows:
        invoice_id = int(row["id"]) if isinstance(row, sqlite3.Row) else int(row[0])
        created_at = row["created_at"] if isinstance(row, sqlite3.Row) else row[1]
        next_ref = _next_reference_no(conn, created_at)
        conn.execute(
            "UPDATE invoices SET reference_no = ? WHERE id = ?",
            (next_ref, invoice_id),
        )


def _parse_datetime_text(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _default_sla_hours_by_risk(risk_level: Any) -> int:
    risk = str(risk_level or "").strip().upper()
    if risk == "HIGH":
        return 2
    if risk == "MEDIUM":
        return 24
    return 72


def _compute_sla_due_at_text(created_at: Any, risk_level: Any) -> str:
    base_dt = _parse_datetime_text(created_at) or datetime.now()
    due_at = base_dt + timedelta(hours=_default_sla_hours_by_risk(risk_level))
    return due_at.strftime("%Y-%m-%d %H:%M:%S")


def _backfill_invoice_trace_id(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            """
            UPDATE invoices
            SET ai_trace_id = COALESCE((
                SELECT apl.trace_id
                FROM ai_prompt_ledger apl
                WHERE apl.invoice_id = invoices.id
                  AND apl.trace_id IS NOT NULL
                  AND TRIM(apl.trace_id) <> ''
                ORDER BY apl.id DESC
                LIMIT 1
            ), '')
            WHERE ai_trace_id IS NULL OR TRIM(ai_trace_id) = ''
            """
        )
    except Exception:
        return


def _backfill_approval_demo_data(conn: sqlite3.Connection) -> None:
    # Keep rule summary visible on approval evidence cards.
    conn.execute(
        "UPDATE invoices SET rule_explain = risk_reason "
        "WHERE (rule_explain IS NULL OR TRIM(rule_explain) = '') "
        "  AND risk_reason IS NOT NULL AND TRIM(risk_reason) <> ''"
    )
    conn.execute(
        "UPDATE invoices SET rule_hit_id = 'RULE_RISK_LEVEL' "
        "WHERE (rule_hit_id IS NULL OR TRIM(rule_hit_id) = '') "
        "  AND COALESCE(TRIM(risk_level), '') <> ''"
    )

    # Keep approval_status synchronized with the historical status column.
    conn.execute(
        "UPDATE invoices SET approval_status = UPPER(COALESCE(status, 'PENDING')) "
        "WHERE approval_status IS NULL OR TRIM(approval_status) = ''"
    )
    conn.execute(
        "UPDATE invoices SET approval_stage = CASE "
        "WHEN UPPER(COALESCE(approval_status, 'PENDING')) = 'PENDING' THEN 'L1' "
        "ELSE 'DONE' END "
        "WHERE approval_stage IS NULL OR TRIM(approval_stage) = ''"
    )

    rows = conn.execute(
        """
        SELECT id, created_at, risk_level, sla_due_at
        FROM invoices
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        invoice_id = int(row["id"])
        due_at_text = str(row["sla_due_at"] or "").strip()
        if not due_at_text:
            due_at_text = _compute_sla_due_at_text(row["created_at"], row["risk_level"])
            conn.execute(
                "UPDATE invoices SET sla_due_at = ? WHERE id = ?",
                (due_at_text, invoice_id),
            )

    # Demo normalization: replace bulk ADMIN/System Admin records with business departments.
    demo_people = [
        ("采购部", "张三", "A0001"),
        ("财务部", "李明", "F0002"),
        ("行政部", "王芳", "A0003"),
    ]
    target_rows = conn.execute(
        """
        SELECT id
        FROM invoices
        WHERE UPPER(COALESCE(department, '')) IN ('ADMIN', 'SYSTEM', '-')
           OR UPPER(COALESCE(applicant, '')) IN ('SYSTEM ADMIN', 'ADMIN', '-', 'SYSTEM')
           OR UPPER(COALESCE(submitter_name, '')) IN ('SYSTEM ADMIN', 'ADMIN', '-')
        ORDER BY id ASC
        """
    ).fetchall()
    for idx, row in enumerate(target_rows):
        department, applicant, submitter_no = demo_people[idx % len(demo_people)]
        conn.execute(
            """
            UPDATE invoices
            SET department = ?,
                applicant = ?,
                submitter_department = ?,
                submitter_name = ?,
                submitter_no = ?
            WHERE id = ?
            """,
            (department, applicant, department, applicant, submitter_no, int(row["id"])),
        )

    # Seed queue owners for inbox demo.
    preferred_owner_rows = conn.execute(
        """
        SELECT username
        FROM users
        WHERE status = ?
          AND employee_no IN ('A0001', 'F0002', 'A0003')
        ORDER BY id ASC
        """,
        (USER_STATUS_ACTIVE,),
    ).fetchall()
    queue_owners = [str(item["username"] or "").strip() for item in preferred_owner_rows if str(item["username"] or "").strip()]
    if not queue_owners:
        fallback_rows = conn.execute(
            """
            SELECT username
            FROM users
            WHERE status = ?
            ORDER BY CASE
                WHEN username = 'finance01' THEN 0
                WHEN username = 'staff01' THEN 1
                WHEN username = 'admin01' THEN 2
                ELSE 10
            END, id ASC
            LIMIT 3
            """,
            (USER_STATUS_ACTIVE,),
        ).fetchall()
        queue_owners = [str(item["username"] or "").strip() for item in fallback_rows if str(item["username"] or "").strip()]

    pending_rows = conn.execute(
        """
        SELECT id
        FROM invoices
        WHERE UPPER(COALESCE(approval_status, 'PENDING')) = 'PENDING'
          AND (queue_owner_id IS NULL OR TRIM(queue_owner_id) = '')
        ORDER BY id ASC
        """
    ).fetchall()
    for idx, row in enumerate(pending_rows):
        if not queue_owners:
            break
        owner = queue_owners[idx % len(queue_owners)]
        conn.execute(
            "UPDATE invoices SET queue_owner_id = ? WHERE id = ?",
            (owner, int(row["id"])),
        )


def _rebuild_db_if_required() -> None:
    """
    If a legacy DB is missing critical approval columns, archive it and rebuild.
    This avoids ALTER conflicts and startup failures after schema upgrades.
    """
    if not os.path.exists(DB_PATH):
        return

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        if not _table_exists(conn, "invoices"):
            return

        existing = _get_table_columns(conn, "invoices")
        missing = sorted(REQUIRED_APPROVAL_COLUMNS - existing)
        if not missing:
            return
    except Exception as exc:
        raise RuntimeError(
            f"Failed to inspect existing DB schema: {exc}. "
            f"Please close processes and remove {DB_PATH} manually."
        ) from exc
    finally:
        if conn is not None:
            conn.close()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{DB_PATH}.legacy_{ts}.bak"
    try:
        os.replace(DB_PATH, backup_path)
        print(
            "[db] Legacy schema detected (missing columns: "
            f"{', '.join(missing)}). Archived old DB to: {backup_path}"
        )
    except Exception as exc:
        raise RuntimeError(
            "Legacy DB schema is incompatible and auto-rebuild failed. "
            f"Please manually remove {DB_PATH}. Error: {exc}"
        ) from exc


def init_db() -> None:
    _rebuild_db_if_required()
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_no TEXT UNIQUE,
                filename TEXT NOT NULL,
                amount TEXT,
                invoice_date TEXT,
                applicant TEXT,
                department TEXT,
                is_canton_fair INTEGER NOT NULL DEFAULT 0,
                hotel_limit INTEGER NOT NULL DEFAULT 500,
                mode TEXT,
                raw_json TEXT,
                risk_level TEXT,
                risk_reason TEXT,
                currency TEXT,
                fx_flag INTEGER DEFAULT 0,
                fx_reason TEXT,
                manual_rate TEXT,
                manual_cny_amount TEXT,
                ai_risk_level TEXT,
                ai_analysis_reason TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                record_state TEXT NOT NULL DEFAULT 'DRAFT',
                source TEXT NOT NULL DEFAULT 'normal',
                verify_status TEXT NOT NULL DEFAULT 'PENDING',
                verify_message TEXT DEFAULT '',
                verify_checked_at TEXT DEFAULT NULL,
                verify_count INTEGER NOT NULL DEFAULT 0,
                verify_provider TEXT DEFAULT '',
                verify_request_id TEXT DEFAULT '',
                verify_latency_ms INTEGER DEFAULT 0,
                verify_status_code INTEGER DEFAULT 0,
                verify_raw_payload TEXT DEFAULT '',
                approval_stage TEXT NOT NULL DEFAULT 'L1',
                approval_status TEXT NOT NULL DEFAULT 'PENDING',
                first_approver_id TEXT DEFAULT '',
                second_approver_id TEXT DEFAULT '',
                first_approved_at TEXT DEFAULT NULL,
                second_approved_at TEXT DEFAULT NULL,
                sla_due_at TEXT DEFAULT NULL,
                queue_owner_id TEXT DEFAULT '',
                rule_hit_id TEXT DEFAULT '',
                rule_explain TEXT DEFAULT '',
                ai_trace_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                department TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                employee_no TEXT NOT NULL,
                role TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                must_change_password INTEGER NOT NULL DEFAULT 0,
                failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                lock_until TEXT,
                password_updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_security_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                failed_count INTEGER NOT NULL DEFAULT 0,
                window_start TEXT,
                lock_until TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_id TEXT NOT NULL UNIQUE,
                ts TEXT,
                amount REAL,
                counterparty TEXT,
                memo TEXT,
                imported_at TEXT NOT NULL,
                matched_invoice_id INTEGER,
                match_score REAL,
                match_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER,
                risk_level TEXT,
                risk_score INTEGER,
                rule_summary TEXT,
                trace_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                assigned_to TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                resolution_note TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                action_type TEXT,
                operator TEXT,
                action_note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_prompt_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                invoice_id INTEGER,
                risk_level TEXT,
                risk_score INTEGER,
                prompt_version TEXT,
                provider TEXT,
                input_json TEXT,
                output_json TEXT,
                hash_prev TEXT,
                hash_curr TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                parent_id INTEGER,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_name TEXT NOT NULL UNIQUE,
                data_scope TEXT NOT NULL DEFAULT 'DEPT',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_data_scopes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL UNIQUE,
                scope_type TEXT NOT NULL DEFAULT 'DEPT',
                dept_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permission_key TEXT NOT NULL UNIQUE,
                description TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                operator TEXT NOT NULL,
                actor_user_id INTEGER,
                target_type TEXT,
                target_id INTEGER,
                detail TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor_user_id TEXT DEFAULT '',
                actor_name TEXT DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                target_type TEXT NOT NULL DEFAULT '',
                target_id TEXT NOT NULL DEFAULT '',
                client_ip TEXT NOT NULL DEFAULT '',
                change_reason_code TEXT NOT NULL DEFAULT 'SYSTEM_AUTO',
                snapshot_before TEXT NOT NULL DEFAULT '{}',
                snapshot_after TEXT NOT NULL DEFAULT '{}',
                trace_id TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                trace_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                actor_user_id TEXT DEFAULT '',
                actor_name TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                object_type TEXT NOT NULL DEFAULT 'invoice',
                object_id TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL,
                evidence_type TEXT NOT NULL DEFAULT 'file',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_key TEXT NOT NULL UNIQUE,
                rule_name TEXT NOT NULL,
                threshold REAL NOT NULL DEFAULT 0,
                threshold_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                severity TEXT NOT NULL DEFAULT 'MEDIUM',
                version INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                config_json TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'ALL',
                reason TEXT DEFAULT '',
                "by" TEXT DEFAULT '',
                at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_enterprises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise_code TEXT UNIQUE NOT NULL,
                enterprise_name TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                settings_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise_id INTEGER,
                dept_code TEXT NOT NULL,
                dept_name TEXT NOT NULL,
                parent_id INTEGER,
                level INTEGER DEFAULT 1,
                path TEXT,
                manager_id INTEGER,
                FOREIGN KEY (enterprise_id) REFERENCES db_enterprises(id),
                FOREIGN KEY (parent_id) REFERENCES db_departments(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_integrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise_id INTEGER,
                integration_type TEXT NOT NULL,
                config_json TEXT,
                status TEXT DEFAULT 'active',
                last_sync_at TEXT,
                FOREIGN KEY (enterprise_id) REFERENCES db_enterprises(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_id INTEGER,
                sync_type TEXT,
                status TEXT,
                records_count INTEGER,
                error_message TEXT,
                sync_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (integration_id) REFERENCES db_integrations(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_risk_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_code TEXT UNIQUE NOT NULL,
                risk_type TEXT,
                severity TEXT,
                description TEXT,
                solution TEXT,
                tags TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                metric_unit TEXT,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Lightweight migration for older local databases.
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN risk_level TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN risk_reason TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN currency TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN fx_flag INTEGER DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN fx_reason TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN manual_rate TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN manual_cny_amount TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN ai_risk_level TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN ai_analysis_reason TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING'")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN record_state TEXT NOT NULL DEFAULT 'DRAFT'")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN source TEXT NOT NULL DEFAULT 'normal'")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN applicant TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN department TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN submitted_by_user_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN submitter_department TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN submitter_name TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN submitter_no TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN reference_no TEXT")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_status TEXT NOT NULL DEFAULT 'PENDING'")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_message TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_checked_at TEXT DEFAULT NULL")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_count INTEGER NOT NULL DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_provider TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_request_id TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_latency_ms INTEGER DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_status_code INTEGER DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN verify_raw_payload TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN approval_stage TEXT NOT NULL DEFAULT 'L1'")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'PENDING'")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN first_approver_id TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN second_approver_id TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN first_approved_at TEXT DEFAULT NULL")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN second_approved_at TEXT DEFAULT NULL")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN sla_due_at TEXT DEFAULT NULL")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN queue_owner_id TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN rule_hit_id TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN rule_explain TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE invoices ADD COLUMN ai_trace_id TEXT DEFAULT ''")

        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN password_hash TEXT")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN department TEXT")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN employee_name TEXT")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN employee_no TEXT")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN role TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN lock_until TEXT")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN password_updated_at TEXT")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN position_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE login_security_locks ADD COLUMN username TEXT")
        _safe_add_column(conn, "ALTER TABLE login_security_locks ADD COLUMN ip_address TEXT")
        _safe_add_column(conn, "ALTER TABLE login_security_locks ADD COLUMN failed_count INTEGER NOT NULL DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE login_security_locks ADD COLUMN window_start TEXT")
        _safe_add_column(conn, "ALTER TABLE login_security_locks ADD COLUMN lock_until TEXT")
        _safe_add_column(conn, "ALTER TABLE login_security_locks ADD COLUMN updated_at TEXT")

        _safe_add_column(conn, "ALTER TABLE bank_transactions ADD COLUMN matched_invoice_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE bank_transactions ADD COLUMN match_score REAL")
        _safe_add_column(conn, "ALTER TABLE bank_transactions ADD COLUMN match_reason TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bank_transactions_txn_id ON bank_transactions(txn_id)")

        _safe_add_column(conn, "ALTER TABLE risk_events ADD COLUMN invoice_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE risk_events ADD COLUMN risk_level TEXT")
        _safe_add_column(conn, "ALTER TABLE risk_events ADD COLUMN risk_score INTEGER")
        _safe_add_column(conn, "ALTER TABLE risk_events ADD COLUMN rule_summary TEXT")
        _safe_add_column(conn, "ALTER TABLE risk_events ADD COLUMN trace_id TEXT")
        _safe_add_column(conn, "ALTER TABLE risk_events ADD COLUMN created_at TEXT")

        _safe_add_column(conn, "ALTER TABLE risk_cases ADD COLUMN event_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE risk_cases ADD COLUMN assigned_to TEXT")
        _safe_add_column(conn, "ALTER TABLE risk_cases ADD COLUMN status TEXT NOT NULL DEFAULT 'OPEN'")
        _safe_add_column(conn, "ALTER TABLE risk_cases ADD COLUMN resolution_note TEXT")
        _safe_add_column(conn, "ALTER TABLE risk_cases ADD COLUMN created_at TEXT")
        _safe_add_column(conn, "ALTER TABLE risk_cases ADD COLUMN closed_at TEXT")

        _safe_add_column(conn, "ALTER TABLE case_actions ADD COLUMN case_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE case_actions ADD COLUMN action_type TEXT")
        _safe_add_column(conn, "ALTER TABLE case_actions ADD COLUMN operator TEXT")
        _safe_add_column(conn, "ALTER TABLE case_actions ADD COLUMN action_note TEXT")
        _safe_add_column(conn, "ALTER TABLE case_actions ADD COLUMN created_at TEXT")

        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN trace_id TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN invoice_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN risk_level TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN risk_score INTEGER")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN prompt_version TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN provider TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN input_json TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN output_json TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN hash_prev TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN hash_curr TEXT")
        _safe_add_column(conn, "ALTER TABLE ai_prompt_ledger ADD COLUMN created_at TEXT")

        _safe_add_column(conn, "ALTER TABLE departments ADD COLUMN name TEXT")
        _safe_add_column(conn, "ALTER TABLE departments ADD COLUMN parent_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE departments ADD COLUMN created_at TEXT")
        _safe_add_column(conn, "ALTER TABLE departments ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
        _safe_add_column(conn, "ALTER TABLE departments ADD COLUMN updated_at TEXT")

        _safe_add_column(conn, "ALTER TABLE roles ADD COLUMN role_name TEXT")
        _safe_add_column(conn, "ALTER TABLE roles ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'DEPT'")
        _safe_add_column(conn, "ALTER TABLE roles ADD COLUMN created_at TEXT")
        _safe_add_column(conn, "ALTER TABLE roles ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
        _safe_add_column(conn, "ALTER TABLE roles ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN role_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN scope_type TEXT NOT NULL DEFAULT 'DEPT'")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN dept_ids TEXT NOT NULL DEFAULT '[]'")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN user_ids TEXT NOT NULL DEFAULT '[]'")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN created_at TEXT")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN updated_at TEXT")
        _safe_add_column(conn, "ALTER TABLE role_data_scopes ADD COLUMN updated_by TEXT")

        _safe_add_column(conn, "ALTER TABLE permissions ADD COLUMN permission_key TEXT")
        _safe_add_column(conn, "ALTER TABLE permissions ADD COLUMN description TEXT")

        _safe_add_column(conn, "ALTER TABLE user_roles ADD COLUMN user_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE user_roles ADD COLUMN role_id INTEGER")

        _safe_add_column(conn, "ALTER TABLE role_permissions ADD COLUMN role_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE role_permissions ADD COLUMN permission_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN action_type TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN operator TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN actor_user_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN target_type TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN target_id INTEGER")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN detail TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_logs ADD COLUMN created_at TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN actor_user_id TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN actor_name TEXT")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN action TEXT NOT NULL DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN target_type TEXT NOT NULL DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN target_id TEXT NOT NULL DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN client_ip TEXT NOT NULL DEFAULT ''")
        _safe_add_column(
            conn,
            "ALTER TABLE audit_log ADD COLUMN change_reason_code TEXT NOT NULL DEFAULT 'SYSTEM_AUTO'",
        )
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN snapshot_before TEXT NOT NULL DEFAULT '{}'")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN snapshot_after TEXT NOT NULL DEFAULT '{}'")
        _safe_add_column(conn, "ALTER TABLE audit_log ADD COLUMN trace_id TEXT DEFAULT ''")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN rule_key TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN rule_name TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN threshold REAL NOT NULL DEFAULT 0")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN threshold_json TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN severity TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN updated_by TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN updated_at TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN rule_type TEXT NOT NULL DEFAULT 'system'")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN status TEXT NOT NULL DEFAULT 'published'")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN publish_reason TEXT")
        _safe_add_column(conn, "ALTER TABLE governance_rules ADD COLUMN published_at TEXT")
        try:
            conn.execute(
                "UPDATE governance_rules SET rule_type = 'system', status = 'published' "
                "WHERE rule_type IS NULL OR rule_type = '' OR status IS NULL OR status = ''"
            )
        except Exception:
            pass
        _safe_add_column(conn, "ALTER TABLE workflow_config ADD COLUMN version INTEGER")
        _safe_add_column(conn, "ALTER TABLE workflow_config ADD COLUMN status TEXT")
        _safe_add_column(conn, "ALTER TABLE workflow_config ADD COLUMN config_json TEXT")
        _safe_add_column(conn, "ALTER TABLE workflow_config ADD COLUMN scope TEXT")
        _safe_add_column(conn, "ALTER TABLE workflow_config ADD COLUMN reason TEXT")
        _safe_add_column(conn, 'ALTER TABLE workflow_config ADD COLUMN "by" TEXT')
        _safe_add_column(conn, "ALTER TABLE workflow_config ADD COLUMN at TEXT")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_invoice_id ON risk_events(invoice_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_created_at ON risk_events(created_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_cases_event_id ON risk_cases(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_cases_status ON risk_cases(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_case_actions_case_id ON case_actions(case_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_prompt_ledger_trace_id ON ai_prompt_ledger(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_prompt_ledger_invoice_id ON ai_prompt_ledger(invoice_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_prompt_ledger_created_at ON ai_prompt_ledger(created_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_departments_name ON departments(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_departments_parent_id ON departments(parent_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_name ON positions(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_roles_name ON roles(role_name)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_role_data_scopes_role_id ON role_data_scopes(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_data_scopes_scope_type ON role_data_scopes(scope_type)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_permissions_key ON permissions(permission_key)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_roles_unique ON user_roles(user_id, role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_role_permissions_unique ON role_permissions(role_id, permission_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_login_security_locks_identity "
            "ON login_security_locks(username, ip_address)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_login_security_locks_lock_until ON login_security_locks(lock_until)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_type, target_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_traces_trace_id ON audit_traces(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_traces_object ON audit_traces(object_type, object_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace_events_trace_id ON audit_trace_events(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace_events_event_time ON audit_trace_events(event_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_evidence_trace_id ON audit_evidence(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_queue_owner ON invoices(queue_owner_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_approval_status ON invoices(approval_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_record_state ON invoices(record_state)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_governance_rules_key ON governance_rules(rule_key)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_db_enterprises_code ON db_enterprises(enterprise_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_departments_enterprise ON db_departments(enterprise_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_departments_parent ON db_departments(parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_integrations_enterprise ON db_integrations(enterprise_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_integrations_type ON db_integrations(integration_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_sync_logs_integration ON db_sync_logs(integration_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_sync_logs_sync_at ON db_sync_logs(sync_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_db_risk_cases_code ON db_risk_cases(case_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_metrics_type_name ON db_metrics(metric_type, metric_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_db_metrics_recorded_at ON db_metrics(recorded_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_config_version ON workflow_config(version)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_config_status_at ON workflow_config(status, at)")

        conn.execute("UPDATE invoices SET status = 'PENDING' WHERE status IS NULL OR TRIM(status) = ''")
        conn.execute(
            "UPDATE invoices SET record_state = CASE "
            "WHEN TRIM(COALESCE(amount, '')) <> '' AND TRIM(COALESCE(invoice_date, '')) <> '' THEN 'LEDGER' "
            "ELSE 'DRAFT' END "
            "WHERE record_state IS NULL OR TRIM(record_state) = ''"
        )
        conn.execute(
            "UPDATE invoices SET record_state = 'DRAFT' "
            "WHERE TRIM(COALESCE(amount, '')) = '' OR TRIM(COALESCE(invoice_date, '')) = ''"
        )
        conn.execute(
            "UPDATE invoices SET record_state = 'DRAFT' "
            "WHERE UPPER(TRIM(COALESCE(record_state, 'DRAFT'))) NOT IN ('DRAFT', 'LEDGER')"
        )
        conn.execute("UPDATE invoices SET source = 'normal' WHERE source IS NULL OR TRIM(source) = ''")
        conn.execute("UPDATE invoices SET verify_status = 'PENDING' WHERE verify_status IS NULL OR TRIM(verify_status) = ''")
        conn.execute("UPDATE invoices SET verify_message = '' WHERE verify_message IS NULL")
        conn.execute("UPDATE invoices SET verify_count = 0 WHERE verify_count IS NULL")
        conn.execute("UPDATE invoices SET verify_provider = '' WHERE verify_provider IS NULL")
        conn.execute("UPDATE invoices SET verify_request_id = '' WHERE verify_request_id IS NULL")
        conn.execute("UPDATE invoices SET verify_latency_ms = 0 WHERE verify_latency_ms IS NULL")
        conn.execute("UPDATE invoices SET verify_status_code = 0 WHERE verify_status_code IS NULL")
        conn.execute("UPDATE invoices SET verify_raw_payload = '' WHERE verify_raw_payload IS NULL")
        conn.execute("UPDATE invoices SET approval_stage = 'L1' WHERE approval_stage IS NULL OR TRIM(approval_stage) = ''")
        conn.execute("UPDATE invoices SET approval_status = status WHERE approval_status IS NULL OR TRIM(approval_status) = ''")
        conn.execute("UPDATE invoices SET approval_status = 'PENDING' WHERE approval_status IS NULL OR TRIM(approval_status) = ''")
        conn.execute("UPDATE invoices SET first_approver_id = '' WHERE first_approver_id IS NULL")
        conn.execute("UPDATE invoices SET second_approver_id = '' WHERE second_approver_id IS NULL")
        conn.execute("UPDATE invoices SET queue_owner_id = '' WHERE queue_owner_id IS NULL")
        conn.execute("UPDATE invoices SET rule_hit_id = '' WHERE rule_hit_id IS NULL")
        conn.execute("UPDATE invoices SET rule_explain = '' WHERE rule_explain IS NULL")
        conn.execute("UPDATE invoices SET ai_trace_id = '' WHERE ai_trace_id IS NULL")
        conn.execute("UPDATE invoices SET applicant = '-' WHERE applicant IS NULL OR TRIM(applicant) = ''")
        conn.execute("UPDATE invoices SET department = '-' WHERE department IS NULL OR TRIM(department) = ''")
        conn.execute("UPDATE users SET status = 'ACTIVE' WHERE status IS NULL OR TRIM(status) = ''")
        conn.execute("UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL")
        conn.execute("UPDATE users SET failed_login_attempts = 0 WHERE failed_login_attempts IS NULL")
        conn.execute(
            "UPDATE audit_log SET created_at = strftime('%Y-%m-%d %H:%M:%S', 'now') "
            "WHERE created_at IS NULL OR TRIM(created_at) = ''"
        )
        conn.execute("UPDATE audit_log SET actor_user_id = '' WHERE actor_user_id IS NULL")
        conn.execute("UPDATE audit_log SET actor_name = '' WHERE actor_name IS NULL")
        conn.execute("UPDATE audit_log SET action = '' WHERE action IS NULL")
        conn.execute("UPDATE audit_log SET target_type = '' WHERE target_type IS NULL")
        conn.execute("UPDATE audit_log SET target_id = '' WHERE target_id IS NULL")
        conn.execute("UPDATE audit_log SET client_ip = '' WHERE client_ip IS NULL")
        conn.execute(
            "UPDATE audit_log SET change_reason_code = 'SYSTEM_AUTO' "
            "WHERE change_reason_code IS NULL OR TRIM(change_reason_code) = ''"
        )
        conn.execute("UPDATE audit_log SET snapshot_before = '{}' WHERE snapshot_before IS NULL")
        conn.execute("UPDATE audit_log SET snapshot_after = '{}' WHERE snapshot_after IS NULL")
        conn.execute("UPDATE audit_log SET trace_id = '' WHERE trace_id IS NULL")
        conn.execute("UPDATE departments SET status = 'ACTIVE' WHERE status IS NULL OR TRIM(status) = ''")
        conn.execute("UPDATE departments SET parent_id = NULL WHERE parent_id IS NOT NULL AND CAST(parent_id AS INTEGER) <= 0")
        conn.execute(
            "UPDATE departments SET updated_at = created_at "
            "WHERE updated_at IS NULL OR TRIM(updated_at) = ''"
        )
        conn.execute(
            "UPDATE role_data_scopes SET scope_type = 'DEPT' "
            "WHERE scope_type IS NULL OR TRIM(scope_type) = ''"
        )
        conn.execute(
            "UPDATE role_data_scopes SET dept_ids = '[]' "
            "WHERE dept_ids IS NULL OR TRIM(dept_ids) = ''"
        )
        conn.execute(
            "UPDATE role_data_scopes SET user_ids = '[]' "
            "WHERE user_ids IS NULL OR TRIM(user_ids) = ''"
        )
        conn.execute(
            "UPDATE role_data_scopes SET created_at = strftime('%Y-%m-%d %H:%M:%S', 'now') "
            "WHERE created_at IS NULL OR TRIM(created_at) = ''"
        )
        conn.execute(
            "UPDATE role_data_scopes SET updated_at = created_at "
            "WHERE updated_at IS NULL OR TRIM(updated_at) = ''"
        )
        _backfill_governance_rule_defaults(conn)
        conn.execute(
            "UPDATE invoices SET submitter_department = department "
            "WHERE submitter_department IS NULL OR TRIM(submitter_department) = ''"
        )
        conn.execute(
            "UPDATE invoices SET submitter_name = applicant "
            "WHERE submitter_name IS NULL OR TRIM(submitter_name) = ''"
        )
        conn.execute(
            "UPDATE invoices SET submitter_no = '-' "
            "WHERE submitter_no IS NULL OR TRIM(submitter_no) = ''"
        )
        _backfill_reference_no(conn)
        _seed_default_users(conn)
        _seed_default_admin_user(conn)
        _backfill_invoice_trace_id(conn)
        _backfill_approval_demo_data(conn)
        _seed_default_iam(conn)
        _backfill_role_data_scopes(conn)
        _seed_default_governance_rules(conn)
        _seed_workflow_config_if_empty(conn)
        _flag_weak_password_accounts(conn)
        conn.commit()


def _seed_default_users(conn: sqlite3.Connection) -> None:
    """
    默认测试账号生成已禁用。
    系统启动时不再自动创建 finance01、staff01、ops01 等测试账号。
    管理员可通过人员管理页面手动创建所需账号。
    """
    # 注释掉测试账号生成逻辑，避免每次启动都创建测试数据
    # bootstrap_password = os.getenv("DEFAULT_BOOTSTRAP_PASSWORD", DEFAULT_RESET_PASSWORD)
    # seed_users = [
    #     {
    #         "username": "finance01",
    #         "password": bootstrap_password,
    #         "department": "财务部",
    #         "employee_name": "李明",
    #         "employee_no": "F0002",
    #         "role": "finance_manager",
    #     },
    #     {
    #         "username": "staff01",
    #         "password": bootstrap_password,
    #         "department": "采购部",
    #         "employee_name": "张三",
    #         "employee_no": "A0001",
    #         "role": "staff",
    #     },
    #     {
    #         "username": "ops01",
    #         "password": bootstrap_password,
    #         "department": "行政部",
    #         "employee_name": "王芳",
    #         "employee_no": "A0003",
    #         "role": "staff",
    #     },
    # ]
    # for item in seed_users:
    #     password_hash = generate_password_hash(str(item["password"]))
    #     conn.execute(
    #         """
    #         INSERT INTO users (username, password_hash, department, employee_name, employee_no, role, must_change_password)
    #         VALUES (?, ?, ?, ?, ?, ?, ?)
    #         ON CONFLICT(username) DO UPDATE SET
    #             department = excluded.department,
    #             employee_name = excluded.employee_name,
    #             employee_no = excluded.employee_no,
    #             role = excluded.role,
    #             password_hash = CASE
    #                 WHEN users.password_hash IS NULL OR TRIM(users.password_hash) = '' THEN excluded.password_hash
    #                 ELSE users.password_hash
    #             END,
    #             must_change_password = CASE
    #                 WHEN users.must_change_password IS NULL THEN excluded.must_change_password
    #                 ELSE users.must_change_password
    #             END
    #         """,
    #         (
    #             item["username"],
    #             password_hash,
    #             item["department"],
    #             item["employee_name"],
    #             item["employee_no"],
    #             item["role"],
    #             1,
    #         ),
    #     )
    pass  # 函数体为空，不再生成测试账号


def _write_initial_admin_secret(username: str, password: str) -> str | None:
    secrets_dir = os.path.join(os.getcwd(), ".secrets")
    secret_path = os.path.join(secrets_dir, "initial_admin.txt")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(secrets_dir, exist_ok=True)
        with open(secret_path, "x", encoding="utf-8") as fh:
            fh.write("DeepAudit Pro Initial Admin Credential\n")
            fh.write(f"generated_at={now}\n")
            fh.write(f"username={username}\n")
            fh.write(f"password={password}\n")
            fh.write("notice=Rotate immediately after first login.\n")
    except FileExistsError:
        pass
    except Exception:
        return None
    return secret_path


def _seed_default_admin_user(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        """
        SELECT id, password_hash
        FROM users
        WHERE username = ?
        LIMIT 1
        """,
        ("admin01",),
    ).fetchone()

    if existing:
        existing_password_hash = str(existing["password_hash"] or "").strip()
        conn.execute(
            """
            UPDATE users
            SET department = ?,
                employee_name = ?,
                employee_no = ?,
                role = ?,
                status = CASE
                    WHEN status IS NULL OR TRIM(status) = '' THEN ?
                    ELSE status
                END,
                must_change_password = CASE
                    WHEN must_change_password IS NULL THEN 1
                    ELSE must_change_password
                END
            WHERE id = ?
            """,
            ("管理部", "系统管理员", "ADM001", "admin", USER_STATUS_ACTIVE, int(existing["id"])),
        )
        if not existing_password_hash:
            bootstrap_password = str(os.getenv("ADMIN_INIT_PASSWORD") or "").strip()
            if not bootstrap_password:
                bootstrap_password = secrets.token_urlsafe(14)
                secret_path = _write_initial_admin_secret("admin01", bootstrap_password)
                if secret_path:
                    print(
                        "[security] admin01 credential repaired. "
                        f"Initial password was written to: {secret_path}"
                    )
                else:
                    print("[security] admin01 credential repaired with random password. Please rotate immediately.")
            else:
                print("[security] admin01 credential repaired from ADMIN_INIT_PASSWORD. Please rotate immediately.")

            conn.execute(
                """
                UPDATE users
                SET password_hash = ?,
                    must_change_password = 1,
                    password_updated_at = ?
                WHERE id = ?
                """,
                (generate_password_hash(bootstrap_password), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(existing["id"])),
            )
        return

    bootstrap_password = str(os.getenv("ADMIN_INIT_PASSWORD") or "").strip()
    if not bootstrap_password:
        bootstrap_password = secrets.token_urlsafe(14)
        secret_path = _write_initial_admin_secret("admin01", bootstrap_password)
        if secret_path:
            print(
                "[security] admin01 initialized. "
                f"Initial password was written to: {secret_path}"
            )
        else:
            print("[security] admin01 initialized with random password. Please rotate immediately.")
    else:
        print("[security] admin01 initialized from ADMIN_INIT_PASSWORD. Please rotate immediately.")

    password_hash = generate_password_hash(bootstrap_password)
    conn.execute(
        """
        INSERT INTO users (username, password_hash, department, employee_name, employee_no, role, status, must_change_password)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("admin01", password_hash, "管理部", "系统管理员", "ADM001", "admin", USER_STATUS_ACTIVE, 1),
    )


def _seed_default_iam(conn: sqlite3.Connection) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row in conn.execute("SELECT DISTINCT department FROM users").fetchall():
        dept_name = str(row["department"] or "").strip()
        if not dept_name:
            continue
        conn.execute(
            """
            INSERT INTO departments (name, status, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                created_at = CASE
                    WHEN departments.created_at IS NULL OR TRIM(departments.created_at) = '' THEN excluded.created_at
                    ELSE departments.created_at
                END,
                updated_at = CASE
                    WHEN departments.updated_at IS NULL OR TRIM(departments.updated_at) = '' THEN excluded.updated_at
                    ELSE departments.updated_at
                END
            """,
            (dept_name, DEPARTMENT_STATUS_ACTIVE, now, now),
        )

    # Backward-compatible role rename (legacy role title -> target role title).
    for role_def in DEFAULT_ROLES:
        role_name = str(role_def.get("role_name") or "").strip()
        for legacy_name in role_def.get("legacy_names") or []:
            legacy = str(legacy_name or "").strip()
            if not role_name or not legacy or legacy == role_name:
                continue
            legacy_row = conn.execute("SELECT id FROM roles WHERE role_name = ? LIMIT 1", (legacy,)).fetchone()
            target_row = conn.execute("SELECT id FROM roles WHERE role_name = ? LIMIT 1", (role_name,)).fetchone()
            if legacy_row and not target_row:
                conn.execute("UPDATE roles SET role_name = ? WHERE id = ?", (role_name, int(legacy_row["id"])))

    permission_id_by_key: dict[str, int] = {}
    for key, desc in DEFAULT_PERMISSIONS:
        normalized_key = str(key).strip().upper()
        conn.execute(
            """
            INSERT INTO permissions (permission_key, description)
            VALUES (?, ?)
            ON CONFLICT(permission_key) DO UPDATE SET description = excluded.description
            """,
            (normalized_key, str(desc)),
        )
        row = conn.execute(
            "SELECT id FROM permissions WHERE permission_key = ? LIMIT 1",
            (normalized_key,),
        ).fetchone()
        if row:
            permission_id_by_key[normalized_key] = int(row["id"])

    role_id_by_name: dict[str, int] = {}
    for role_def in DEFAULT_ROLES:
        role_name = str(role_def.get("role_name") or "").strip()
        if not role_name:
            continue

        raw_scope = str(role_def.get("data_scope") or DATA_SCOPE_DEPT).strip().upper()
        data_scope = _normalize_data_scope(raw_scope)
        conn.execute(
            """
            INSERT INTO roles (role_name, data_scope, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(role_name) DO UPDATE SET
                data_scope = excluded.data_scope,
                created_at = CASE
                    WHEN roles.created_at IS NULL OR TRIM(roles.created_at) = '' THEN excluded.created_at
                    ELSE roles.created_at
                END
            """,
            (role_name, data_scope, now),
        )

        role_row = conn.execute("SELECT id FROM roles WHERE role_name = ? LIMIT 1", (role_name,)).fetchone()
        if not role_row:
            continue
        role_id = int(role_row["id"])
        role_id_by_name[role_name] = role_id

        permission_ids: list[int] = []
        for permission_key in role_def.get("permissions") or []:
            normalized_key = str(permission_key or "").strip().upper()
            permission_id = permission_id_by_key.get(normalized_key)
            if permission_id is not None:
                permission_ids.append(permission_id)
                conn.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (?, ?)
                    ON CONFLICT(role_id, permission_id) DO NOTHING
                    """,
                    (role_id, permission_id),
                )

        # Built-in roles are strict definitions: remove stale permissions.
        if permission_ids:
            placeholders = ",".join(["?"] * len(permission_ids))
            conn.execute(
                f"DELETE FROM role_permissions WHERE role_id = ? AND permission_id NOT IN ({placeholders})",
                (role_id, *permission_ids),
            )
        else:
            conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))

    system_admin_role_id = role_id_by_name.get(ROLE_SYSTEM_ADMIN)
    finance_manager_role_id = role_id_by_name.get(ROLE_FINANCE_MANAGER)
    finance_specialist_role_id = role_id_by_name.get(ROLE_FINANCE_SPECIALIST)
    risk_specialist_role_id = role_id_by_name.get(ROLE_RISK_SPECIALIST)

    manage_system_permission_id = permission_id_by_key.get("MANAGE_SYSTEM")
    if manage_system_permission_id is not None:
        if system_admin_role_id is not None:
            conn.execute(
                "DELETE FROM role_permissions WHERE permission_id = ? AND role_id <> ?",
                (manage_system_permission_id, system_admin_role_id),
            )
            conn.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (?, ?)
                ON CONFLICT(role_id, permission_id) DO NOTHING
                """,
                (system_admin_role_id, manage_system_permission_id),
            )
        else:
            conn.execute(
                "DELETE FROM role_permissions WHERE permission_id = ?",
                (manage_system_permission_id,),
            )
    
    # 确保系统管理员拥有所有权限（虽然代码层面通过 is_system_admin() 检查自动授予所有权限，
    # 但为了审计和权限管理的完整性，在数据库中也记录所有权限）
    if system_admin_role_id is not None:
        all_permission_ids = list(permission_id_by_key.values())
        if all_permission_ids:
            placeholders = ",".join(["?"] * len(all_permission_ids))
            # 为系统管理员添加所有权限
            for perm_id in all_permission_ids:
                conn.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (?, ?)
                    ON CONFLICT(role_id, permission_id) DO NOTHING
                    """,
                    (system_admin_role_id, perm_id),
                )

    users = conn.execute(
        "SELECT id, username, role FROM users WHERE status = ?",
        (USER_STATUS_ACTIVE,),
    ).fetchall()
    for user_row in users:
        user_id = int(user_row["id"])
        username = str(user_row["username"] or "").strip().lower()
        legacy_role = str(user_row["role"] or "").strip().lower()

        target_role_id: int | None = None
        if username == "admin01" or "admin" in legacy_role:
            target_role_id = system_admin_role_id
        elif "manager" in legacy_role or "finance_manager" in legacy_role:
            target_role_id = finance_manager_role_id
        elif "risk" in legacy_role or "control" in legacy_role:
            target_role_id = risk_specialist_role_id
        elif "finance" in legacy_role:
            target_role_id = finance_specialist_role_id

        if target_role_id is None:
            continue
        conn.execute(
            """
            INSERT INTO user_roles (user_id, role_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, role_id) DO NOTHING
            """,
            (user_id, target_role_id),
        )


def _backfill_role_data_scopes(conn: sqlite3.Connection) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    role_rows = conn.execute(
        """
        SELECT id, data_scope
        FROM roles
        ORDER BY id ASC
        """
    ).fetchall()

    for row in role_rows:
        role_id = int(row["id"])
        fallback_scope = _normalize_data_scope(row["data_scope"])
        existing = conn.execute(
            """
            SELECT scope_type, dept_ids, created_at
            FROM role_data_scopes
            WHERE role_id = ?
            LIMIT 1
            """,
            (role_id,),
        ).fetchone()

        if existing:
            scope_type = _normalize_data_scope(existing["scope_type"], fallback=fallback_scope)
            dept_ids = _normalize_dept_ids(existing["dept_ids"])
            created_at = str(existing["created_at"] or "").strip() or now
            conn.execute(
                """
                UPDATE role_data_scopes
                SET scope_type = ?, dept_ids = ?, created_at = ?, updated_at = ?
                WHERE role_id = ?
                """,
                (
                    scope_type,
                    json.dumps(dept_ids, ensure_ascii=False),
                    created_at,
                    now,
                    role_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO role_data_scopes (role_id, scope_type, dept_ids, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    role_id,
                    fallback_scope,
                    "[]",
                    now,
                    now,
                ),
            )

        conn.execute(
            "UPDATE roles SET data_scope = ? WHERE id = ?",
            (_normalize_data_scope(fallback_scope), role_id),
        )


def _backfill_governance_rule_defaults(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, rule_key, threshold, threshold_json, severity
        FROM governance_rules
        """
    ).fetchall()
    for row in rows:
        rule_id = int(row["id"])
        rule_key = str(row["rule_key"] or "").strip().upper()
        current_threshold = row["threshold"]
        threshold_payload = _normalize_threshold_payload(
            rule_key,
            row["threshold_json"],
            fallback_threshold=current_threshold,
        )
        threshold_json_text = json.dumps(threshold_payload, ensure_ascii=False, sort_keys=True)
        threshold_value = _extract_threshold_value(rule_key, threshold_payload, current_threshold)
        severity = _normalize_rule_severity(
            row["severity"],
            fallback=_normalize_rule_severity((DEFAULT_GOVERNANCE_RULES_BY_KEY.get(rule_key) or {}).get("severity")),
        )
        conn.execute(
            """
            UPDATE governance_rules
            SET threshold = ?, threshold_json = ?, severity = ?
            WHERE id = ?
            """,
            (threshold_value, threshold_json_text, severity, rule_id),
        )


def _seed_default_governance_rules(conn: sqlite3.Connection) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in DEFAULT_GOVERNANCE_RULES:
        rule_key = str(item.get("rule_key") or "").strip()
        rule_name = str(item.get("rule_name") or "").strip()
        if not rule_key or not rule_name:
            continue
        try:
            threshold = float(item.get("threshold", 0))
        except Exception:
            threshold = 0.0
        threshold_payload = _normalize_threshold_payload(
            rule_key,
            item.get("threshold_json"),
            fallback_threshold=threshold,
        )
        threshold_json_text = json.dumps(threshold_payload, ensure_ascii=False, sort_keys=True)
        severity = _normalize_rule_severity(item.get("severity"))

        conn.execute(
            """
            INSERT INTO governance_rules (
                rule_key, rule_name, threshold, threshold_json, enabled, severity, version, updated_by, updated_at,
                rule_type, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'system', 'published')
            ON CONFLICT(rule_key) DO UPDATE SET
                rule_name = CASE
                    WHEN governance_rules.rule_name IS NULL OR TRIM(governance_rules.rule_name) = '' THEN excluded.rule_name
                    ELSE governance_rules.rule_name
                END,
                threshold_json = CASE
                    WHEN governance_rules.threshold_json IS NULL OR TRIM(governance_rules.threshold_json) = '' THEN excluded.threshold_json
                    ELSE governance_rules.threshold_json
                END,
                severity = CASE
                    WHEN governance_rules.severity IS NULL OR TRIM(governance_rules.severity) = '' THEN excluded.severity
                    ELSE governance_rules.severity
                END,
                updated_at = CASE
                    WHEN governance_rules.updated_at IS NULL OR TRIM(governance_rules.updated_at) = '' THEN excluded.updated_at
                    ELSE governance_rules.updated_at
                END
            """,
            (rule_key, rule_name, threshold, threshold_json_text, 1, severity, 1, "system", now),
        )


def _flag_weak_password_accounts(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT id, password_hash
        FROM users
        WHERE password_hash IS NOT NULL AND TRIM(password_hash) <> ''
        """
    ).fetchall()
    flagged = 0
    # 只有在设置了弱密码检测值时才进行检查
    if not DEFAULT_WEAK_PASSWORD:
        return flagged
    for row in rows:
        password_hash = str(row["password_hash"] or "").strip()
        if not password_hash:
            continue
        try:
            is_weak = check_password_hash(password_hash, DEFAULT_WEAK_PASSWORD)
        except Exception:
            is_weak = False
        if not is_weak:
            continue
        conn.execute("UPDATE users SET must_change_password = 1 WHERE id = ?", (int(row["id"]),))
        flagged += 1
    return flagged


def _normalize_user_row(row: sqlite3.Row | None) -> Dict[str, Any] | None:
    if row is None:
        return None
    user_id_raw = row["id"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        user_id = int(user_id_raw)
    except Exception:
        return None

    def _safe_str(key: str) -> str:
        try:
            value = row[key] if isinstance(row, sqlite3.Row) else ""
        except Exception:
            value = ""
        return str(value or "").strip()

    def _safe_int(key: str, fallback: int = 0) -> int:
        try:
            value = row[key] if isinstance(row, sqlite3.Row) else fallback
            return int(value)
        except Exception:
            return fallback

    return {
        "id": user_id,
        "username": _safe_str("username"),
        "department": _safe_str("department"),
        "employee_name": _safe_str("employee_name"),
        "employee_no": _safe_str("employee_no"),
        "role": _safe_str("role"),
        "status": _safe_str("status") or USER_STATUS_ACTIVE,
        "must_change_password": bool(_safe_int("must_change_password", 0)),
        "failed_login_attempts": _safe_int("failed_login_attempts", 0),
        "lock_until": _safe_str("lock_until"),
        "email": _safe_str("email"),
        "phone": _safe_str("phone"),
    }


def get_user_by_id(user_id: int | str | None) -> Dict[str, Any] | None:
    if user_id is None:
        return None
    try:
        normalized_id = int(user_id)
    except Exception:
        return None
    if normalized_id <= 0:
        return None

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, department, employee_name, employee_no, role, status,
                   must_change_password, failed_login_attempts, lock_until, email, phone
            FROM users
            WHERE id = ?
            """,
            (normalized_id,),
        ).fetchone()
    return _normalize_user_row(row)


def get_user_by_username(username: str | None) -> Dict[str, Any] | None:
    normalized = str(username or "").strip()
    if not normalized:
        return None

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, department, employee_name, employee_no, role, status,
                   must_change_password, failed_login_attempts, lock_until, email, phone
            FROM users
            WHERE username = ?
            """,
            (normalized,),
        ).fetchone()
    return _normalize_user_row(row)


def get_user_auth_by_username(username: str | None) -> Dict[str, Any] | None:
    normalized = str(username or "").strip()
    if not normalized:
        return None

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, department, employee_name, employee_no, role, status,
                   must_change_password, failed_login_attempts, lock_until, email, phone
            FROM users
            WHERE username = ?
            """,
            (normalized,),
        ).fetchone()

    user = _normalize_user_row(row)
    if user is None:
        return None

    password_hash = str((row["password_hash"] if row else "") or "").strip()
    user["password_hash"] = password_hash
    return user


def get_user_auth_by_id(user_id: int | str | None) -> Dict[str, Any] | None:
    if user_id is None:
        return None
    try:
        normalized_id = int(user_id)
    except Exception:
        return None
    if normalized_id <= 0:
        return None

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, department, employee_name, employee_no, role, status,
                   must_change_password, failed_login_attempts, lock_until, email, phone
            FROM users
            WHERE id = ?
            """,
            (normalized_id,),
        ).fetchone()
    user = _normalize_user_row(row)
    if user is None:
        return None
    password_hash = str((row["password_hash"] if row else "") or "").strip()
    user["password_hash"] = password_hash
    return user


def update_user_profile(
    user_id: int | str | None,
    *,
    email: str | None = None,
    phone: str | None = None,
) -> bool:
    """更新当前用户邮箱、手机号（仅更新传入的非 None 字段）。"""
    if user_id is None:
        return False
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False

    updates: list[str] = []
    params: list[Any] = []
    if email is not None:
        updates.append("email = ?")
        params.append(str(email or "").strip())
    if phone is not None:
        updates.append("phone = ?")
        params.append(str(phone or "").strip())
    if not updates:
        return True

    params.append(normalized_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
    return True


def _parse_lock_until(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _normalize_login_identity(username: Any, ip_address: Any) -> tuple[str, str]:
    normalized_username = str(username or "").strip().lower()
    normalized_ip = str(ip_address or "").strip()
    if not normalized_ip:
        normalized_ip = "-"
    return normalized_username, normalized_ip


def is_login_identity_locked(username: Any, ip_address: Any) -> tuple[bool, str]:
    normalized_username, normalized_ip = _normalize_login_identity(username, ip_address)
    if not normalized_username:
        return False, ""

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT lock_until
            FROM login_security_locks
            WHERE username = ? AND ip_address = ?
            LIMIT 1
            """,
            (normalized_username, normalized_ip),
        ).fetchone()
        if not row:
            return False, ""

        lock_until_dt = _parse_lock_until(row["lock_until"])
        if not lock_until_dt:
            return False, ""
        if lock_until_dt <= datetime.now():
            conn.execute(
                """
                UPDATE login_security_locks
                SET lock_until = NULL,
                    failed_count = 0,
                    window_start = NULL,
                    updated_at = ?
                WHERE username = ? AND ip_address = ?
                """,
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), normalized_username, normalized_ip),
            )
            conn.commit()
            return False, ""
        return True, lock_until_dt.strftime("%Y-%m-%d %H:%M:%S")


def clear_login_identity_failures(username: Any, ip_address: Any) -> None:
    normalized_username, normalized_ip = _normalize_login_identity(username, ip_address)
    if not normalized_username:
        return
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM login_security_locks WHERE username = ? AND ip_address = ?",
            (normalized_username, normalized_ip),
        )
        conn.commit()


def register_login_identity_failure(
    username: Any,
    ip_address: Any,
    *,
    max_failures: int = LOGIN_LOCK_MAX_FAILURES,
    lock_minutes: int = LOGIN_LOCK_MINUTES,
    window_minutes: int = LOGIN_LOCK_WINDOW_MINUTES,
) -> Dict[str, Any]:
    normalized_username, normalized_ip = _normalize_login_identity(username, ip_address)
    if not normalized_username:
        return {"ok": False, "locked": False, "attempts": 0, "remaining": max_failures, "lock_until": ""}

    now_dt = datetime.now()
    now_text = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    safe_max = max(1, int(max_failures))
    safe_lock_minutes = max(1, int(lock_minutes))
    safe_window_minutes = max(1, int(window_minutes))

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT failed_count, window_start, lock_until
            FROM login_security_locks
            WHERE username = ? AND ip_address = ?
            LIMIT 1
            """,
            (normalized_username, normalized_ip),
        ).fetchone()

        attempts = 0
        window_start_dt = now_dt
        lock_until_dt: datetime | None = None

        if row:
            attempts = int(row["failed_count"] or 0)
            parsed_window_start = _parse_lock_until(row["window_start"])
            if parsed_window_start is not None:
                window_start_dt = parsed_window_start

            parsed_lock_until = _parse_lock_until(row["lock_until"])
            if parsed_lock_until and parsed_lock_until > now_dt:
                return {
                    "ok": True,
                    "locked": True,
                    "attempts": attempts,
                    "remaining": 0,
                    "lock_until": parsed_lock_until.strftime("%Y-%m-%d %H:%M:%S"),
                    "username": normalized_username,
                    "ip_address": normalized_ip,
                }

            if now_dt - window_start_dt >= timedelta(minutes=safe_window_minutes):
                attempts = 0
                window_start_dt = now_dt

        attempts += 1
        locked = attempts >= safe_max
        lock_until_text = ""
        if locked:
            lock_until_dt = now_dt + timedelta(minutes=safe_lock_minutes)
            lock_until_text = lock_until_dt.strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            """
            INSERT INTO login_security_locks (username, ip_address, failed_count, window_start, lock_until, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, ip_address) DO UPDATE SET
                failed_count = excluded.failed_count,
                window_start = excluded.window_start,
                lock_until = excluded.lock_until,
                updated_at = excluded.updated_at
            """,
            (
                normalized_username,
                normalized_ip,
                attempts,
                window_start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                lock_until_text or None,
                now_text,
            ),
        )
        conn.commit()

    remaining = max(0, safe_max - attempts)
    return {
        "ok": True,
        "locked": locked,
        "attempts": attempts,
        "remaining": remaining,
        "lock_until": lock_until_text,
        "username": normalized_username,
        "ip_address": normalized_ip,
    }


def is_user_locked(user: Dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(user, dict):
        return False, ""
    lock_until_dt = _parse_lock_until(user.get("lock_until"))
    if lock_until_dt is None:
        return False, ""
    if lock_until_dt <= datetime.now():
        return False, ""
    return True, lock_until_dt.strftime("%Y-%m-%d %H:%M:%S")


def clear_login_failures(user_id: int | str | None) -> None:
    if user_id is None:
        return
    try:
        normalized_id = int(user_id)
    except Exception:
        return
    if normalized_id <= 0:
        return
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET failed_login_attempts = 0,
                lock_until = NULL
            WHERE id = ?
            """,
            (normalized_id,),
        )
        conn.commit()


def register_failed_login_attempt(
    username: str | None,
    *,
    max_failures: int = LOGIN_LOCK_MAX_FAILURES,
    lock_minutes: int = LOGIN_LOCK_MINUTES,
) -> Dict[str, Any]:
    normalized = str(username or "").strip()
    if not normalized:
        return {"ok": False, "locked": False, "attempts": 0, "remaining": max_failures}

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, failed_login_attempts, lock_until
            FROM users
            WHERE username = ?
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        if not row:
            return {"ok": False, "locked": False, "attempts": 0, "remaining": max_failures}

        lock_until_dt = _parse_lock_until(row["lock_until"])
        now = datetime.now()
        already_locked = bool(lock_until_dt and lock_until_dt > now)
        attempts = int(row["failed_login_attempts"] or 0)
        if lock_until_dt and lock_until_dt <= now:
            attempts = 0

        if already_locked:
            remaining = 0
            lock_until_text = lock_until_dt.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "ok": True,
                "user_id": int(row["id"]),
                "username": str(row["username"] or "").strip(),
                "locked": True,
                "attempts": attempts,
                "remaining": remaining,
                "lock_until": lock_until_text,
            }

        attempts += 1
        locked = attempts >= max(1, int(max_failures))
        lock_until_text = ""
        if locked:
            lock_until_dt = now + timedelta(minutes=max(1, int(lock_minutes)))
            lock_until_text = lock_until_dt.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE users
                SET failed_login_attempts = ?,
                    lock_until = ?
                WHERE id = ?
                """,
                (attempts, lock_until_text, int(row["id"])),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET failed_login_attempts = ?,
                    lock_until = NULL
                WHERE id = ?
                """,
                (attempts, int(row["id"])),
            )
        conn.commit()

    remaining = max(0, max(1, int(max_failures)) - attempts)
    return {
        "ok": True,
        "user_id": int(row["id"]),
        "username": str(row["username"] or "").strip(),
        "locked": locked,
        "attempts": attempts,
        "remaining": remaining,
        "lock_until": lock_until_text,
    }


def update_user_password(
    user_id: int | str | None,
    *,
    new_password: str,
    must_change_password: bool = False,
) -> bool:
    if user_id is None:
        return False
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False

    password_text = str(new_password or "").strip()
    if not password_text:
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    password_hash = generate_password_hash(password_text)
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE users
            SET password_hash = ?,
                must_change_password = ?,
                failed_login_attempts = 0,
                lock_until = NULL,
                password_updated_at = ?
            WHERE id = ?
            """,
            (password_hash, 1 if must_change_password else 0, now, normalized_id),
        )
        conn.commit()
    return cur.rowcount > 0


def list_users_with_password(password: str, limit: int = 1000) -> list[Dict[str, Any]]:
    password_text = str(password or "").strip()
    if not password_text:
        return []
    try:
        normalized_limit = max(1, min(int(limit), 5000))
    except Exception:
        normalized_limit = 1000

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE password_hash IS NOT NULL AND TRIM(password_hash) <> ''
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        password_hash = str(row["password_hash"] or "").strip()
        try:
            matched = check_password_hash(password_hash, password_text)
        except Exception:
            matched = False
        if not matched:
            continue
        result.append({"id": int(row["id"]), "username": str(row["username"] or "").strip()})
    return result


def _normalize_data_scope(value: Any, fallback: str = DATA_SCOPE_DEPT) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in DATA_SCOPE_TYPES:
        return normalized
    fallback_scope = str(fallback or DATA_SCOPE_DEPT).strip().upper()
    if fallback_scope in DATA_SCOPE_TYPES:
        return fallback_scope
    return DATA_SCOPE_DEPT


# 策略类型（简化）：全量/本部/本人/自定义
SCOPE_POLICY_TYPE_MAP = {
    DATA_SCOPE_ALL: "全量",
    DATA_SCOPE_DEPT: "本部",
    DATA_SCOPE_DEPT_TREE: "本部",
    DATA_SCOPE_SELF: "本人",
    DATA_SCOPE_SELF_SUB: "本人",
    DATA_SCOPE_DEPT_WHITELIST: "自定义",
    DATA_SCOPE_USER_WHITELIST: "自定义",
}


def _data_scope_effective_scope_label(
    scope_type: str,
    dept_ids: list[int],
    user_ids: list[int],
    dept_names: list[str],
) -> str:
    """生成生效范围展示文案。"""
    st = _normalize_data_scope(scope_type)
    if st == DATA_SCOPE_ALL:
        return "全量"
    if st == DATA_SCOPE_DEPT:
        return "本部门"
    if st == DATA_SCOPE_DEPT_TREE:
        return "本部门+下级"
    if st == DATA_SCOPE_SELF:
        return "本人"
    if st == DATA_SCOPE_SELF_SUB:
        return "本人+下属"
    if st == DATA_SCOPE_DEPT_WHITELIST:
        n = len(dept_ids) or len(dept_names)
        return f"指定{n}个部门" if n else "指定部门"
    if st == DATA_SCOPE_USER_WHITELIST:
        return f"指定{len(user_ids)}人" if user_ids else "指定人员"
    return "本部门"


def _normalize_dept_ids(values: Any) -> list[int]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        text = str(values or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = [part for part in re.split(r"[,;，；\s]+", text) if str(part or "").strip()]
        values = parsed
    elif not isinstance(values, (list, tuple, set)):
        values = [values]

    result: list[int] = []
    seen: set[int] = set()
    for item in values:
        try:
            dept_id = int(item)
        except Exception:
            continue
        if dept_id <= 0 or dept_id in seen:
            continue
        seen.add(dept_id)
        result.append(dept_id)
    return result


def _normalize_user_ids(values: Any) -> list[int]:
    """归一化 user_ids 为不重复正整数列表。"""
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        text = str(values or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = [part for part in re.split(r"[,;，；\s]+", text) if str(part or "").strip()]
        values = parsed
    elif not isinstance(values, (list, tuple, set)):
        values = [values]
    result: list[int] = []
    seen: set[int] = set()
    for item in values:
        try:
            uid = int(item)
        except Exception:
            continue
        if uid <= 0 or uid in seen:
            continue
        seen.add(uid)
        result.append(uid)
    return result


def list_user_ids_by_department_names(
    department_names: list[str],
    *,
    limit: int = 10000,
) -> list[int]:
    """根据部门名称列表返回活跃用户 ID 列表（用于范围预览与过滤）。"""
    if not department_names:
        return []
    names = [str(n or "").strip() for n in department_names if str(n or "").strip()]
    if not names:
        return []
    placeholders = ",".join("?" * len(names))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id FROM users
            WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
              AND TRIM(COALESCE(department, '')) IN ({placeholders})
            ORDER BY id ASC
            LIMIT ?
            """,
            (*names, limit),
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _scope_priority(scope_type: str) -> int:
    normalized = _normalize_data_scope(scope_type)
    priority = {
        DATA_SCOPE_SELF: 0,
        DATA_SCOPE_SELF_SUB: 1,
        DATA_SCOPE_DEPT: 2,
        DATA_SCOPE_DEPT_TREE: 3,
        DATA_SCOPE_DEPT_WHITELIST: 4,
        DATA_SCOPE_USER_WHITELIST: 4,
        DATA_SCOPE_ALL: 5,
    }
    return int(priority.get(normalized, 0))


def list_user_role_data_scopes(user_id: int | str | None) -> list[Dict[str, Any]]:
    if user_id is None:
        return []
    try:
        normalized_id = int(user_id)
    except Exception:
        return []
    if normalized_id <= 0:
        return []

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                ur.role_id,
                r.role_name,
                COALESCE(rds.scope_type, r.data_scope, 'DEPT') AS scope_type,
                COALESCE(rds.dept_ids, '[]') AS dept_ids,
                COALESCE(rds.user_ids, '[]') AS user_ids
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            LEFT JOIN role_data_scopes rds ON rds.role_id = r.id
            WHERE ur.user_id = ?
            ORDER BY ur.role_id ASC
            """,
            (normalized_id,),
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "role_id": int(row["role_id"]),
                "role_name": str(row["role_name"] or "").strip(),
                "scope_type": _normalize_data_scope(row["scope_type"]),
                "dept_ids": _normalize_dept_ids(row["dept_ids"]),
                "user_ids": _normalize_user_ids(row["user_ids"]),
            }
        )
    return result


def get_user_data_scope(user_id: int | str | None) -> str:
    role_scopes = list_user_role_data_scopes(user_id)
    if not role_scopes:
        return DATA_SCOPE_DEPT

    winner = DATA_SCOPE_DEPT
    for role_scope in role_scopes:
        candidate = _normalize_data_scope(role_scope.get("scope_type"))
        if _scope_priority(candidate) > _scope_priority(winner):
            winner = candidate
    return winner


def get_user_role_names(user_id: int | str | None) -> set[str]:
    if user_id is None:
        return set()
    try:
        normalized_id = int(user_id)
    except Exception:
        return set()
    if normalized_id <= 0:
        return set()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.role_name
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = ?
            """,
            (normalized_id,),
        ).fetchall()
    return {str(row["role_name"] or "").strip() for row in rows if str(row["role_name"] or "").strip()}


def get_user_permissions(user_id: int | str | None) -> set[str]:
    if user_id is None:
        return set()
    try:
        normalized_id = int(user_id)
    except Exception:
        return set()
    if normalized_id <= 0:
        return set()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.permission_key
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = ?
            """,
            (normalized_id,),
        ).fetchall()
    return {str(row["permission_key"] or "").strip().upper() for row in rows if str(row["permission_key"] or "").strip()}


def user_has_permission(user_id: int | str | None, permission_key: str) -> bool:
    target = str(permission_key or "").strip().upper()
    if not target:
        return False
    return target in get_user_permissions(user_id)


def list_permissions() -> list[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, permission_key, description
            FROM permissions
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_department_names(limit: int = 500) -> list[str]:
    max_limit = 5000
    try:
        normalized_limit = int(limit)
    except Exception:
        normalized_limit = 500
    if normalized_limit <= 0:
        normalized_limit = 500
    normalized_limit = min(normalized_limit, max_limit)

    names: list[str] = []
    seen: set[str] = set()

    def _append_name(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        if text in seen:
            return
        seen.add(text)
        names.append(text)

    with get_conn() as conn:
        disabled_rows = conn.execute(
            """
            SELECT name
            FROM departments
            WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'DISABLED'
            """
        ).fetchall()
        disabled_names = {str(row["name"] or "").strip() for row in disabled_rows if str(row["name"] or "").strip()}

        dept_rows = conn.execute(
            """
            SELECT name
            FROM departments
            WHERE name IS NOT NULL
              AND TRIM(name) <> ''
              AND UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
            ORDER BY name ASC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()
        for row in dept_rows:
            _append_name(row["name"])

        user_rows = conn.execute(
            """
            SELECT DISTINCT department
            FROM users
            WHERE department IS NOT NULL AND TRIM(department) <> ''
            ORDER BY department ASC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()
        for row in user_rows:
            dept_name = str(row["department"] or "").strip()
            if dept_name in disabled_names:
                continue
            _append_name(dept_name)

    if not names:
        names.append("FINANCE")
    return names


def list_departments(limit: int = 500, *, include_disabled: bool = True) -> list[Dict[str, Any]]:
    max_limit = 5000
    try:
        normalized_limit = int(limit)
    except Exception:
        normalized_limit = 500
    if normalized_limit <= 0:
        normalized_limit = 500
    normalized_limit = min(normalized_limit, max_limit)

    where_clause = ""
    params: list[Any] = []
    if not include_disabled:
        where_clause = "WHERE UPPER(COALESCE(d.status, 'ACTIVE')) = 'ACTIVE'"

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT d.id, d.name, d.parent_id, d.status, d.created_at, d.updated_at
            FROM departments d
            {where_clause}
            ORDER BY d.id ASC
            LIMIT ?
            """,
            (*params, normalized_limit),
        ).fetchall()
        count_rows = conn.execute(
            """
            SELECT department, COUNT(*) AS c
            FROM users
            WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
              AND department IS NOT NULL
              AND TRIM(department) <> ''
            GROUP BY department
            """
        ).fetchall()

    active_user_count_by_department = {
        str(item["department"] or "").strip(): int(item["c"] or 0)
        for item in count_rows
        if str(item["department"] or "").strip()
    }

    result: list[Dict[str, Any]] = []
    for row in rows:
        name = str(row["name"] or "").strip()
        result.append(
            {
                "id": int(row["id"]),
                "name": name,
                "parent_id": int(row["parent_id"]) if row["parent_id"] is not None else None,
                "status": str(row["status"] or DEPARTMENT_STATUS_ACTIVE).strip().upper() or DEPARTMENT_STATUS_ACTIVE,
                "created_at": str(row["created_at"] or "").strip(),
                "updated_at": str(row["updated_at"] or row["created_at"] or "").strip(),
                "active_user_count": int(active_user_count_by_department.get(name, 0)),
            }
        )
    return result


def get_department_names_by_ids(
    dept_ids: list[int] | tuple[int, ...] | set[int] | None,
    *,
    include_disabled: bool = False,
) -> list[str]:
    normalized_ids = _normalize_dept_ids(dept_ids)
    if not normalized_ids:
        return []

    placeholders = ",".join(["?"] * len(normalized_ids))
    sql = [
        f"""
        SELECT id, name, status
        FROM departments
        WHERE id IN ({placeholders})
        """
    ]
    if not include_disabled:
        sql.append("AND UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'")

    with get_conn() as conn:
        rows = conn.execute("\n".join(sql), tuple(normalized_ids)).fetchall()

    name_by_id = {
        int(row["id"]): str(row["name"] or "").strip()
        for row in rows
        if int(row["id"]) > 0 and str(row["name"] or "").strip()
    }
    result: list[str] = []
    seen: set[str] = set()
    for dept_id in normalized_ids:
        name = name_by_id.get(dept_id)
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def get_department_tree_names_by_name(
    department_name: str,
    *,
    include_self: bool = True,
    include_disabled: bool = False,
) -> list[str]:
    base_name = _safe_text(department_name)
    if not base_name:
        return []

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, parent_id, status
            FROM departments
            ORDER BY id ASC
            """
        ).fetchall()

    if not rows:
        return [base_name] if include_self else []

    nodes: list[dict[str, Any]] = []
    for row in rows:
        node_name = _safe_text(row["name"])
        if not node_name:
            continue
        status = _safe_text(row["status"], DEPARTMENT_STATUS_ACTIVE).upper() or DEPARTMENT_STATUS_ACTIVE
        nodes.append(
            {
                "id": int(row["id"]),
                "name": node_name,
                "parent_id": int(row["parent_id"]) if row["parent_id"] is not None else None,
                "status": status,
            }
        )

    target_ids = [
        int(node["id"])
        for node in nodes
        if _safe_text(node.get("name")) == base_name
        and (
            include_disabled
            or _safe_text(node.get("status"), DEPARTMENT_STATUS_ACTIVE).upper() == DEPARTMENT_STATUS_ACTIVE
        )
    ]

    if not target_ids:
        return [base_name] if include_self else []

    child_map: dict[int, list[int]] = {}
    name_by_id: dict[int, str] = {}
    status_by_id: dict[int, str] = {}
    for node in nodes:
        node_id = int(node["id"])
        parent_id = node.get("parent_id")
        if parent_id is not None:
            child_map.setdefault(int(parent_id), []).append(node_id)
        name_by_id[node_id] = _safe_text(node.get("name"))
        status_by_id[node_id] = _safe_text(node.get("status"), DEPARTMENT_STATUS_ACTIVE).upper()

    queue: list[int] = list(target_ids)
    visited: set[int] = set()
    collected_names: list[str] = []
    seen_names: set[str] = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)

        node_name = _safe_text(name_by_id.get(node_id))
        node_status = _safe_text(status_by_id.get(node_id), DEPARTMENT_STATUS_ACTIVE).upper()
        if node_name and (include_disabled or node_status == DEPARTMENT_STATUS_ACTIVE):
            if node_name not in seen_names:
                seen_names.add(node_name)
                collected_names.append(node_name)

        for child_id in child_map.get(node_id, []):
            if child_id not in visited:
                queue.append(child_id)

    if not include_self:
        collected_names = [name for name in collected_names if name != base_name]
    if include_self and base_name not in collected_names:
        collected_names.insert(0, base_name)
    return collected_names


def create_department(name: str, *, parent_id: int | None = None) -> Dict[str, Any] | None:
    department_name = str(name or "").strip()
    if not department_name:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_parent_id: int | None = None
    if parent_id is not None:
        try:
            candidate_parent_id = int(parent_id)
        except Exception:
            candidate_parent_id = 0
        if candidate_parent_id > 0:
            normalized_parent_id = candidate_parent_id

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM departments WHERE name = ? LIMIT 1",
            (department_name,),
        ).fetchone()
        if existing:
            return None
        if normalized_parent_id is not None:
            parent_row = conn.execute(
                "SELECT id FROM departments WHERE id = ? LIMIT 1",
                (normalized_parent_id,),
            ).fetchone()
            if parent_row is None:
                normalized_parent_id = None
        cur = conn.execute(
            """
            INSERT INTO departments (name, parent_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (department_name, normalized_parent_id, DEPARTMENT_STATUS_ACTIVE, now, now),
        )
        department_id = int(cur.lastrowid)
        conn.commit()

    for row in list_departments(limit=5000, include_disabled=True):
        if int(row.get("id", 0)) == department_id:
            return row
    return None


def update_department_name(department_id: int, new_name: str) -> Dict[str, Any] | None:
    try:
        normalized_department_id = int(department_id)
    except Exception:
        return None
    if normalized_department_id <= 0:
        return None

    next_name = str(new_name or "").strip()
    if not next_name:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name FROM departments WHERE id = ? LIMIT 1",
            (normalized_department_id,),
        ).fetchone()
        if not row:
            return None
        current_name = str(row["name"] or "").strip()

        conflict = conn.execute(
            "SELECT id FROM departments WHERE name = ? AND id <> ? LIMIT 1",
            (next_name, normalized_department_id),
        ).fetchone()
        if conflict:
            return None

        conn.execute(
            "UPDATE departments SET name = ?, updated_at = ? WHERE id = ?",
            (next_name, now, normalized_department_id),
        )

        if current_name and current_name != next_name:
            conn.execute("UPDATE users SET department = ? WHERE department = ?", (next_name, current_name))
            conn.execute("UPDATE invoices SET department = ? WHERE department = ?", (next_name, current_name))
            conn.execute(
                "UPDATE invoices SET submitter_department = ? WHERE submitter_department = ?",
                (next_name, current_name),
            )

        conn.commit()

    for item in list_departments(limit=5000, include_disabled=True):
        if int(item.get("id", 0)) == normalized_department_id:
            return item
    return None


def disable_department(department_id: int) -> Dict[str, Any] | None:
    try:
        normalized_department_id = int(department_id)
    except Exception:
        return None
    if normalized_department_id <= 0:
        return None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE departments
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (DEPARTMENT_STATUS_DISABLED, now, normalized_department_id),
        )
        conn.commit()
        if cur.rowcount <= 0:
            return None

    for item in list_departments(limit=5000, include_disabled=True):
        if int(item.get("id", 0)) == normalized_department_id:
            return item
    return None


def enable_department(department_id: int) -> Dict[str, Any] | None:
    """启用部门"""
    try:
        normalized_department_id = int(department_id)
    except Exception:
        return None
    if normalized_department_id <= 0:
        return None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE departments
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (DEPARTMENT_STATUS_ACTIVE, now, normalized_department_id),
        )
        conn.commit()
        if cur.rowcount <= 0:
            return None

    for item in list_departments(limit=5000, include_disabled=True):
        if int(item.get("id", 0)) == normalized_department_id:
            return item
    return None


def delete_department(department_id: int) -> bool:
    """删除部门（仅当部门无在职人员时可删除）"""
    try:
        normalized_department_id = int(department_id)
    except Exception:
        return False
    if normalized_department_id <= 0:
        return False

    # 检查部门是否存在以及是否有在职人员
    departments = list_departments(limit=5000, include_disabled=True)
    target_dept = None
    for dept in departments:
        if int(dept.get("id", 0)) == normalized_department_id:
            target_dept = dept
            break
    
    if target_dept is None:
        return False
    
    # 如果有在职人员，不允许删除
    if int(target_dept.get("active_user_count", 0)) > 0:
        return False

    with get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM departments
            WHERE id = ?
            """,
            (normalized_department_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def list_positions(*, include_disabled: bool = True, limit: int = 500) -> list[Dict[str, Any]]:
    """岗位列表。默认包含已禁用；仅启用时传 include_disabled=False。"""
    try:
        normalized_limit = max(1, min(int(limit), 5000))
    except Exception:
        normalized_limit = 500
    with get_conn() as conn:
        sql = """
            SELECT id, name, status, created_at, updated_at
            FROM positions
            ORDER BY status ASC, name ASC
            LIMIT ?
        """
        rows = conn.execute(sql, (normalized_limit,)).fetchall()
    result: list[Dict[str, Any]] = []
    for row in rows:
        status = str(row["status"] or POSITION_STATUS_ACTIVE).strip().upper() or POSITION_STATUS_ACTIVE
        if not include_disabled and status != POSITION_STATUS_ACTIVE:
            continue
        result.append({
            "id": int(row["id"]),
            "name": str(row["name"] or "").strip(),
            "status": status,
            "created_at": str(row["created_at"] or "").strip(),
            "updated_at": str(row["updated_at"] or row["created_at"] or "").strip(),
        })
    return result


def create_position(name: str) -> Dict[str, Any] | None:
    """新增岗位，默认启用。仅当存在同名且已启用的岗位时返回 None；同名已禁用则重新启用并返回。"""
    normalized_name = str(name or "").strip()
    if not normalized_name:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, status FROM positions WHERE name = ? LIMIT 1",
            (normalized_name,),
        ).fetchone()
        if row:
            current_status = str(row["status"] or "").strip().upper()
            if current_status == POSITION_STATUS_ACTIVE:
                return None  # 同名且已启用，不允许重复
            # 同名且已禁用：重新启用
            conn.execute(
                "UPDATE positions SET status = ?, updated_at = ? WHERE id = ?",
                (POSITION_STATUS_ACTIVE, now, int(row["id"])),
            )
            conn.commit()
        else:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO positions (name, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (normalized_name, POSITION_STATUS_ACTIVE, now, now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return None
    # 返回刚创建或刚启用的那条（按 name 查到的唯一一条）
    for item in list_positions(limit=5000, include_disabled=True):
        if str(item.get("name") or "").strip() == normalized_name:
            return item
    return None


def disable_position(position_id: int) -> Dict[str, Any] | None:
    """禁用岗位。岗位不存在时返回 None。"""
    try:
        pid = int(position_id)
    except Exception:
        return None
    if pid <= 0:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE positions SET status = ?, updated_at = ? WHERE id = ?
            """,
            (POSITION_STATUS_DISABLED, now, pid),
        )
        conn.commit()
        if cur.rowcount <= 0:
            return None
    for item in list_positions(limit=5000, include_disabled=True):
        if int(item.get("id", 0)) == pid:
            return item
    return None


def enable_position(position_id: int) -> Dict[str, Any] | None:
    """启用岗位。岗位不存在时返回 None。"""
    try:
        pid = int(position_id)
    except Exception:
        return None
    if pid <= 0:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE positions SET status = ?, updated_at = ? WHERE id = ?
            """,
            (POSITION_STATUS_ACTIVE, now, pid),
        )
        conn.commit()
        if cur.rowcount <= 0:
            return None
    for item in list_positions(limit=5000, include_disabled=True):
        if int(item.get("id", 0)) == pid:
            return item
    return None


def _department_name_map_by_ids(dept_ids: list[int]) -> dict[int, str]:
    normalized_ids = _normalize_dept_ids(dept_ids)
    if not normalized_ids:
        return {}
    placeholders = ",".join(["?"] * len(normalized_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, name
            FROM departments
            WHERE id IN ({placeholders})
            """,
            tuple(normalized_ids),
        ).fetchall()
    return {
        int(row["id"]): str(row["name"] or "").strip()
        for row in rows
        if int(row["id"]) > 0 and str(row["name"] or "").strip()
    }


def list_roles_with_permissions(search: str | None = None, include_disabled: bool = True) -> list[Dict[str, Any]]:
    with get_conn() as conn:
        q = """
            SELECT
                r.id,
                r.role_name,
                r.data_scope,
                r.created_at,
                COALESCE(r.status, 'ACTIVE') AS status,
                COALESCE(r.is_deleted, 0) AS is_deleted,
                COALESCE(rds.scope_type, r.data_scope, 'DEPT') AS scope_type,
                COALESCE(rds.dept_ids, '[]') AS dept_ids,
                COALESCE(rds.user_ids, '[]') AS user_ids,
                rds.updated_at AS scope_updated_at,
                rds.updated_by AS scope_updated_by
            FROM roles r
            LEFT JOIN role_data_scopes rds ON rds.role_id = r.id
            WHERE COALESCE(r.is_deleted, 0) = 0
        """
        params: list[Any] = []
        if not include_disabled:
            q += " AND COALESCE(r.status, 'ACTIVE') = 'ACTIVE'"
        if search and str(search).strip():
            q += " AND LOWER(TRIM(r.role_name)) LIKE ?"
            params.append("%" + str(search).strip().lower() + "%")
        q += " ORDER BY r.id ASC"
        role_rows = conn.execute(q, tuple(params) if params else ()).fetchall()
        perm_rows = conn.execute(
            """
            SELECT rp.role_id, p.id AS permission_id, p.permission_key, p.description
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            ORDER BY rp.role_id ASC, p.id ASC
            """
        ).fetchall()

    permissions_by_role: dict[int, list[Dict[str, Any]]] = {}
    for row in perm_rows:
        role_id = int(row["role_id"])
        permissions_by_role.setdefault(role_id, []).append(
            {
                "id": int(row["permission_id"]),
                "permission_key": str(row["permission_key"] or "").strip(),
                "description": str(row["description"] or "").strip(),
            }
        )

    all_dept_ids: list[int] = []
    scope_info_by_role_id: dict[int, dict[str, Any]] = {}
    for role_row in role_rows:
        role_id = int(role_row["id"])
        scope_type = _normalize_data_scope(role_row["scope_type"])
        dept_ids = _normalize_dept_ids(role_row["dept_ids"])
        user_ids = _normalize_user_ids(role_row["user_ids"])
        scope_info_by_role_id[role_id] = {
            "scope_type": scope_type,
            "dept_ids": dept_ids,
            "user_ids": user_ids,
        }
        for dept_id in dept_ids:
            if dept_id not in all_dept_ids:
                all_dept_ids.append(dept_id)

    dept_name_map = _department_name_map_by_ids(all_dept_ids)

    result: list[Dict[str, Any]] = []
    for role_row in role_rows:
        role_id = int(role_row["id"])
        scope_info = scope_info_by_role_id.get(role_id) or {}
        scope_type = _normalize_data_scope(scope_info.get("scope_type"))
        dept_ids = _normalize_dept_ids(scope_info.get("dept_ids"))
        user_ids = _normalize_user_ids(scope_info.get("user_ids"))
        dept_names = [dept_name_map.get(dept_id, f"部门#{dept_id}") for dept_id in dept_ids]
        scope_type_cn = SCOPE_POLICY_TYPE_MAP.get(scope_type, "本部")
        effective_scope = _data_scope_effective_scope_label(
            scope_type, dept_ids, user_ids, dept_names
        )
        scope_updated_at = role_row["scope_updated_at"]
        scope_updated_by = role_row["scope_updated_by"]
        result.append(
            {
                "id": role_id,
                "role_name": str(role_row["role_name"] or "").strip(),
                "data_scope": scope_type,
                "scope_type": scope_type,
                "scope_type_cn": scope_type_cn,
                "effective_scope": effective_scope,
                "dept_ids": dept_ids,
                "dept_names": dept_names,
                "user_ids": user_ids,
                "status": str(role_row["status"] or "ACTIVE").strip().upper(),
                "created_at": str(role_row["created_at"] or "").strip(),
                "updated_at": str(scope_updated_at or "").strip(),
                "updated_by": str(scope_updated_by or "").strip(),
                "permissions": permissions_by_role.get(role_id, []),
            }
        )
    return result


def _normalize_permission_ids(permission_ids: list[int] | None) -> list[int]:
    normalized_permission_ids: list[int] = []
    for raw in permission_ids or []:
        try:
            pid = int(raw)
        except Exception:
            continue
        if pid <= 0 or pid in normalized_permission_ids:
            continue
        normalized_permission_ids.append(pid)
    return normalized_permission_ids


def set_role_permissions(
    role_id: int,
    permission_ids: list[int],
    *,
    data_scope: str | None = None,
    dept_ids: list[int] | None = None,
) -> Dict[str, Any] | None:
    try:
        normalized_role_id = int(role_id)
    except Exception:
        return None
    if normalized_role_id <= 0:
        return None

    normalized_permission_ids = _normalize_permission_ids(permission_ids)
    normalized_scope: str | None = None
    if data_scope is not None:
        normalized_scope = _normalize_data_scope(data_scope)
    normalized_dept_ids: list[int] | None = None
    if dept_ids is not None:
        normalized_dept_ids = _normalize_dept_ids(dept_ids)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        role_row = conn.execute(
            "SELECT id, role_name, data_scope, created_at FROM roles WHERE id = ?",
            (normalized_role_id,),
        ).fetchone()
        if not role_row:
            return None

        existing_scope_row = conn.execute(
            """
            SELECT scope_type, dept_ids, created_at
            FROM role_data_scopes
            WHERE role_id = ?
            LIMIT 1
            """,
            (normalized_role_id,),
        ).fetchone()
        resolved_scope = _normalize_data_scope(
            normalized_scope if normalized_scope is not None else (
                existing_scope_row["scope_type"] if existing_scope_row is not None else role_row["data_scope"]
            )
        )
        resolved_dept_ids = _normalize_dept_ids(existing_scope_row["dept_ids"] if existing_scope_row else [])
        if normalized_dept_ids is not None:
            resolved_dept_ids = normalized_dept_ids
        if resolved_scope != DATA_SCOPE_DEPT_WHITELIST:
            resolved_dept_ids = []

        created_at = (
            str(existing_scope_row["created_at"] or "").strip()
            if existing_scope_row is not None
            else ""
        ) or now

        conn.execute(
            "UPDATE roles SET data_scope = ? WHERE id = ?",
            (resolved_scope, normalized_role_id),
        )
        conn.execute(
            """
            INSERT INTO role_data_scopes (role_id, scope_type, dept_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(role_id) DO UPDATE SET
                scope_type = excluded.scope_type,
                dept_ids = excluded.dept_ids,
                updated_at = excluded.updated_at
            """,
            (
                normalized_role_id,
                resolved_scope,
                json.dumps(resolved_dept_ids, ensure_ascii=False),
                created_at,
                now,
            ),
        )

        conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (normalized_role_id,))
        for permission_id in normalized_permission_ids:
            conn.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (?, ?)
                ON CONFLICT(role_id, permission_id) DO NOTHING
                """,
                (normalized_role_id, permission_id),
            )
        conn.commit()

    roles = list_roles_with_permissions()
    for role in roles:
        if int(role.get("id", 0)) == normalized_role_id:
            return role
    return None


def create_role_record(role_name: str, data_scope: str = DATA_SCOPE_SELF) -> Dict[str, Any] | None:
    normalized_name = str(role_name or "").strip()
    if not normalized_name:
        return None
    scope = _normalize_data_scope(data_scope)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        # 检查是否存在同名角色（包括已删除的）
        existing = conn.execute(
            "SELECT id, COALESCE(is_deleted, 0) AS is_deleted, COALESCE(status, 'ACTIVE') AS status FROM roles WHERE role_name = ? LIMIT 1",
            (normalized_name,),
        ).fetchone()
        
        if existing:
            # 如果角色已被软删除，则恢复它
            if int(existing["is_deleted"]) == 1:
                conn.execute(
                    "UPDATE roles SET is_deleted = 0, status = 'ACTIVE', data_scope = ?, created_at = ? WHERE id = ?",
                    (scope, now, int(existing["id"])),
                )
                conn.commit()
            else:
                # 角色存在且未删除，返回 None 表示名称冲突
                return None
        else:
            # 不存在同名角色，创建新角色
            try:
                conn.execute(
                    "INSERT INTO roles (role_name, data_scope, created_at, status, is_deleted) VALUES (?, ?, ?, 'ACTIVE', 0)",
                    (normalized_name, scope, now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return None
    
    roles = list_roles_with_permissions()
    for r in roles:
        if str(r.get("role_name", "")).strip() == normalized_name:
            return r
    return None


def toggle_role_status(role_id: int) -> Dict[str, Any] | None:
    try:
        rid = int(role_id)
    except Exception:
        return None
    if rid <= 0:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, COALESCE(status, 'ACTIVE') AS status, COALESCE(is_deleted, 0) AS is_deleted FROM roles WHERE id = ?",
            (rid,),
        ).fetchone()
        if not row or int(row["is_deleted"]) != 0:
            return None
        current = str(row["status"] or "ACTIVE").strip().upper()
        new_status = "DISABLED" if current == "ACTIVE" else "ACTIVE"
        conn.execute("UPDATE roles SET status = ? WHERE id = ?", (new_status, rid))
        conn.commit()
    for r in list_roles_with_permissions():
        if int(r.get("id", 0)) == rid:
            return r
    return None


def soft_delete_role(role_id: int) -> tuple[bool, str]:
    try:
        rid = int(role_id)
    except Exception:
        return False, "无效的角色 ID"
    if rid <= 0:
        return False, "无效的角色 ID"
    bound = count_users_by_role_id(rid)
    if bound > 0:
        return False, f"该角色仍绑定 {bound} 个用户，请先解绑后再删除（可选择禁用）"
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, COALESCE(is_deleted, 0) AS is_deleted FROM roles WHERE id = ?",
            (rid,),
        ).fetchone()
        if not row:
            return False, "角色不存在"
        if int(row["is_deleted"]) != 0:
            return False, "角色已被删除"
        conn.execute("UPDATE roles SET is_deleted = 1, status = 'DISABLED' WHERE id = ?", (rid,))
        conn.commit()
    return True, ""


def count_users_by_role_id(role_id: int) -> int:
    try:
        rid = int(role_id)
    except Exception:
        return 0
    if rid <= 0:
        return 0
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE ur.role_id = ? AND COALESCE(u.status, 'ACTIVE') != 'OFFBOARDED'
            """,
            (rid,),
        ).fetchone()
    return int(row["cnt"]) if row else 0


def get_role_data_scope_policy(role_id: int | str | None) -> Dict[str, Any] | None:
    if role_id is None:
        return None
    try:
        normalized_role_id = int(role_id)
    except Exception:
        return None
    if normalized_role_id <= 0:
        return None

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                r.id AS role_id,
                r.role_name,
                COALESCE(rds.scope_type, r.data_scope, 'DEPT') AS scope_type,
                COALESCE(rds.dept_ids, '[]') AS dept_ids,
                COALESCE(rds.user_ids, '[]') AS user_ids
            FROM roles r
            LEFT JOIN role_data_scopes rds ON rds.role_id = r.id
            WHERE r.id = ?
            LIMIT 1
            """,
            (normalized_role_id,),
        ).fetchone()

    if not row:
        return None

    dept_ids = _normalize_dept_ids(row["dept_ids"])
    user_ids = _normalize_user_ids(row["user_ids"])
    dept_name_map = _department_name_map_by_ids(dept_ids)
    return {
        "role_id": int(row["role_id"]),
        "role_name": str(row["role_name"] or "").strip(),
        "scope_type": _normalize_data_scope(row["scope_type"]),
        "dept_ids": dept_ids,
        "dept_names": [dept_name_map.get(did, f"部门#{did}") for did in dept_ids],
        "user_ids": user_ids,
    }


def set_role_data_scope_policy(
    role_id: int,
    scope_type: str,
    dept_ids: list[int] | None = None,
    user_ids: list[int] | None = None,
    updated_by: str | None = None,
) -> Dict[str, Any] | None:
    try:
        normalized_role_id = int(role_id)
    except Exception:
        return None
    if normalized_role_id <= 0:
        return None

    normalized_scope = _normalize_data_scope(scope_type)
    normalized_dept_ids = _normalize_dept_ids(dept_ids)
    normalized_user_ids = _normalize_user_ids(user_ids)
    if normalized_scope != DATA_SCOPE_DEPT_WHITELIST:
        normalized_dept_ids = []
    if normalized_scope != DATA_SCOPE_USER_WHITELIST:
        normalized_user_ids = []

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_by_str = str(updated_by or "").strip() or None
    with get_conn() as conn:
        role_row = conn.execute(
            "SELECT id FROM roles WHERE id = ? LIMIT 1",
            (normalized_role_id,),
        ).fetchone()
        if role_row is None:
            return None

        existing = conn.execute(
            """
            SELECT created_at
            FROM role_data_scopes
            WHERE role_id = ?
            LIMIT 1
            """,
            (normalized_role_id,),
        ).fetchone()
        created_at = (str(existing["created_at"] or "").strip() if existing else "") or now

        conn.execute(
            """
            INSERT INTO role_data_scopes (role_id, scope_type, dept_ids, user_ids, created_at, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role_id) DO UPDATE SET
                scope_type = excluded.scope_type,
                dept_ids = excluded.dept_ids,
                user_ids = excluded.user_ids,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (
                normalized_role_id,
                normalized_scope,
                json.dumps(normalized_dept_ids, ensure_ascii=False),
                json.dumps(normalized_user_ids, ensure_ascii=False),
                created_at,
                now,
                updated_by_str,
            ),
        )
        conn.execute(
            "UPDATE roles SET data_scope = ? WHERE id = ?",
            (normalized_scope, normalized_role_id),
        )
        conn.commit()

    for role in list_roles_with_permissions():
        if int(role.get("id", 0)) == normalized_role_id:
            return role
    return None


def set_role_data_scope(role_id: int, data_scope: str) -> Dict[str, Any] | None:
    try:
        normalized_role_id = int(role_id)
    except Exception:
        return None
    if normalized_role_id <= 0:
        return None
    current = get_role_data_scope_policy(role_id)
    existing_dept_ids = _normalize_dept_ids((current or {}).get("dept_ids"))
    existing_user_ids = _normalize_user_ids((current or {}).get("user_ids"))
    return set_role_data_scope_policy(
        role_id=normalized_role_id,
        scope_type=data_scope,
        dept_ids=existing_dept_ids,
        user_ids=existing_user_ids,
    )


def data_scope_preview_user_count_and_sample(
    scope_type: str,
    dept_ids: list[int] | None = None,
    user_ids: list[int] | None = None,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """
    预览数据范围策略覆盖的用户数与示例用户（用于前端「预览覆盖」）。
    仅对 ALL / DEPT_WHITELIST / USER_WHITELIST 可精确计算；
    SELF / SELF_SUB / DEPT / DEPT_TREE 为动态（按当前用户/部门），返回 hint。
    """
    normalized_scope = _normalize_data_scope(scope_type)
    dept_ids = _normalize_dept_ids(dept_ids)
    user_ids = _normalize_user_ids(user_ids)
    sample_size = max(0, min(int(sample_size), 50))

    if normalized_scope == DATA_SCOPE_ALL:
        with get_conn() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*) AS n FROM users
                WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
                """
            ).fetchone()["n"]
            rows = conn.execute(
                """
                SELECT id, username, department, employee_name, employee_no
                FROM users
                WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
                ORDER BY id ASC
                LIMIT ?
                """,
                (sample_size,),
            ).fetchall()
        return {
            "user_count": total,
            "sample_users": [
                {
                    "id": int(r["id"]),
                    "username": str(r["username"] or "").strip(),
                    "department": str(r["department"] or "").strip(),
                    "employee_name": str(r["employee_name"] or "").strip(),
                    "employee_no": str(r["employee_no"] or "").strip(),
                }
                for r in rows
            ],
            "hint": "",
        }

    if normalized_scope == DATA_SCOPE_DEPT_WHITELIST and dept_ids:
        dept_names = get_department_names_by_ids(dept_ids)
        uid_list = list_user_ids_by_department_names(dept_names, limit=10000)
        total = len(uid_list)
        sample_ids = uid_list[:sample_size]
        sample_users = _user_list_by_ids(sample_ids) if sample_ids else []
        return {
            "user_count": total,
            "sample_users": sample_users,
            "hint": "",
        }

    if normalized_scope == DATA_SCOPE_USER_WHITELIST and user_ids:
        total = len(user_ids)
        sample_ids = user_ids[:sample_size]
        sample_users = _user_list_by_ids(sample_ids) if sample_ids else []
        return {
            "user_count": total,
            "sample_users": sample_users,
            "hint": "",
        }

    # 动态范围：无法在不指定当前用户/部门时精确计算
    hint_map = {
        DATA_SCOPE_SELF: "按登录用户动态计算，仅本人",
        DATA_SCOPE_SELF_SUB: "按登录用户所在部门动态计算（本人+同部门）",
        DATA_SCOPE_DEPT: "按登录用户所在部门动态计算",
        DATA_SCOPE_DEPT_TREE: "按登录用户所在部门及下级动态计算",
    }
    return {
        "user_count": 0,
        "sample_users": [],
        "hint": hint_map.get(normalized_scope, "动态计算"),
    }


def _user_list_by_ids(user_ids: list[int], limit: int = 50) -> list[Dict[str, Any]]:
    if not user_ids:
        return []
    ids = user_ids[:limit]
    placeholders = ",".join(["?"] * len(ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, username, department, employee_name, employee_no
            FROM users
            WHERE id IN ({placeholders})
            ORDER BY id ASC
            """,
            tuple(ids),
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "username": str(r["username"] or "").strip(),
            "department": str(r["department"] or "").strip(),
            "employee_name": str(r["employee_name"] or "").strip(),
            "employee_no": str(r["employee_no"] or "").strip(),
        }
        for r in rows
    ]


def list_users_admin(limit: int = 500) -> list[Dict[str, Any]]:
    max_limit = 5000
    try:
        normalized_limit = int(limit)
    except Exception:
        normalized_limit = 500
    if normalized_limit <= 0:
        normalized_limit = 500
    normalized_limit = min(normalized_limit, max_limit)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.username, u.department, u.employee_name, u.employee_no, u.role, u.status,
                   u.must_change_password, u.position_id,
                   p.name AS position_name
            FROM users u
            LEFT JOIN positions p ON p.id = u.position_id AND UPPER(COALESCE(p.status, 'ACTIVE')) = 'ACTIVE'
            ORDER BY u.id ASC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()
        role_rows = conn.execute(
            """
            SELECT
                ur.user_id,
                r.id AS role_id,
                r.role_name,
                COALESCE(rds.scope_type, r.data_scope, 'DEPT') AS data_scope,
                COALESCE(rds.dept_ids, '[]') AS dept_ids
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            LEFT JOIN role_data_scopes rds ON rds.role_id = r.id
            ORDER BY ur.user_id ASC, r.id ASC
            """
        ).fetchall()

    roles_by_user: dict[int, list[Dict[str, Any]]] = {}
    for row in role_rows:
        user_id = int(row["user_id"])
        roles_by_user.setdefault(user_id, []).append(
            {
                "id": int(row["role_id"]),
                "role_name": str(row["role_name"] or "").strip(),
                "data_scope": _normalize_data_scope(row["data_scope"]),
                "dept_ids": _normalize_dept_ids(row["dept_ids"]),
            }
        )

    result: list[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        user_id = int(item["id"])
        item["status"] = str(item.get("status") or USER_STATUS_ACTIVE).strip().upper() or USER_STATUS_ACTIVE
        item["must_change_password"] = bool(int(item.get("must_change_password") or 0))
        item["position_id"] = int(item["position_id"]) if item.get("position_id") is not None else None
        item["position_name"] = str(item.get("position_name") or "").strip() or None
        item["roles"] = roles_by_user.get(user_id, [])
        result.append(item)
    return result


def create_user_account(
    *,
    username: str,
    password: str,
    department: str,
    employee_name: str,
    employee_no: str,
    role_text: str = "",
    role_id: int | None = None,
    position_id: int | None = None,
) -> Dict[str, Any] | None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return None
    password_text = str(password or "").strip()
    if not password_text:
        return None

    password_hash = generate_password_hash(password_text)
    now_status = USER_STATUS_ACTIVE
    department_name = str(department or "-").strip() or "-"
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_position_id: int | None = None
    if position_id is not None:
        try:
            pid = int(position_id)
            if pid > 0:
                normalized_position_id = pid
        except Exception:
            pass

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (
                username, password_hash, department, employee_name, employee_no, role,
                status, must_change_password, failed_login_attempts, lock_until, password_updated_at, position_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_username,
                password_hash,
                department_name,
                str(employee_name or normalized_username).strip() or normalized_username,
                str(employee_no or "-").strip() or "-",
                str(role_text or "").strip(),
                now_status,
                1,
                0,
                None,
                now_text,
                normalized_position_id,
            ),
        )
        user_id = int(cur.lastrowid)
        if department_name and department_name != "-":
            conn.execute(
                """
                INSERT INTO departments (name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO NOTHING
                """,
                (department_name, DEPARTMENT_STATUS_ACTIVE, now_text, now_text),
            )
        if role_id is not None:
            try:
                normalized_role_id = int(role_id)
            except Exception:
                normalized_role_id = 0
            if normalized_role_id > 0:
                conn.execute(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES (?, ?)
                    ON CONFLICT(user_id, role_id) DO NOTHING
                    """,
                    (user_id, normalized_role_id),
                )
        conn.commit()

    for row in list_users_admin(limit=5000):
        if int(row.get("id", 0)) == user_id:
            return row
    return None


def _set_user_status(user_id: int, status: str) -> bool:
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False
    normalized_status = str(status or "").strip().upper()
    if normalized_status not in {USER_STATUS_ACTIVE, USER_STATUS_DISABLED}:
        return False

    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET status = ? WHERE id = ?",
            (normalized_status, normalized_id),
        )
        conn.commit()
    return cur.rowcount > 0


def disable_user_account(user_id: int) -> bool:
    return _set_user_status(user_id, USER_STATUS_DISABLED)


def enable_user_account(user_id: int) -> bool:
    return _set_user_status(user_id, USER_STATUS_ACTIVE)


def offboard_user_account(user_id: int) -> bool:
    """离职/停用：禁用账号并清空角色与数据范围（user_roles + users.role）。"""
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False
    with get_conn() as conn:
        conn.execute("UPDATE users SET status = ?, role = '' WHERE id = ?", (USER_STATUS_DISABLED, normalized_id))
        conn.execute("DELETE FROM user_roles WHERE user_id = ?", (normalized_id,))
        conn.commit()
    return True


def user_can_be_deleted(user_id: int) -> bool:
    """仅当无业务记录、无审计记录（作为被操作对象）时可删除，供测试账号等使用。"""
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False
    with get_conn() as conn:
        # 审计记录：该用户作为 target 的条数
        row = conn.execute(
            "SELECT 1 FROM audit_log WHERE target_type = 'user' AND target_id = ? LIMIT 1",
            (str(normalized_id),),
        ).fetchone()
        if row is not None:
            return False
        row = conn.execute(
            "SELECT 1 FROM audit_logs WHERE target_type = 'user' AND target_id = ? LIMIT 1",
            (normalized_id,),
        ).fetchone()
        if row is not None:
            return False
        # 业务：发票提交人
        row = conn.execute(
            "SELECT 1 FROM invoices WHERE submitted_by_user_id = ? LIMIT 1",
            (normalized_id,),
        ).fetchone()
        if row is not None:
            return False
        # 业务：风险案件经办人（assigned_to 存的是 username）
        user_row = conn.execute("SELECT username FROM users WHERE id = ? LIMIT 1", (normalized_id,)).fetchone()
        if user_row is not None:
            username = (user_row[0] if isinstance(user_row, (tuple, list)) else user_row["username"]) if user_row else ""
            username = str(username or "").strip()
            if username:
                row = conn.execute(
                    "SELECT 1 FROM risk_cases WHERE assigned_to = ? LIMIT 1",
                    (username,),
                ).fetchone()
                if row is not None:
                    return False
    return True


def delete_user_account(user_id: int, *, force: bool = False) -> bool:
    """删除用户（仅应在 user_can_be_deleted 为 True 时调用，或 force=True 时强制删除）。"""
    if not force:
        if not user_can_be_deleted(user_id):
            return False
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False
    with get_conn() as conn:
        conn.execute("DELETE FROM user_roles WHERE user_id = ?", (normalized_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (normalized_id,))
        conn.commit()
    return True


def insert_audit_log(
    *,
    action_type: str,
    operator: str,
    detail: str = "",
    actor_user_id: int | None = None,
    target_type: str = "",
    target_id: int | None = None,
) -> int:
    normalized_action = str(action_type or "").strip().upper()
    normalized_operator = str(operator or "").strip() or "system"
    if not normalized_action:
        return 0

    normalized_actor_user_id: int | None
    try:
        normalized_actor_user_id = int(actor_user_id) if actor_user_id is not None else None
        if normalized_actor_user_id <= 0:
            normalized_actor_user_id = None
    except Exception:
        normalized_actor_user_id = None

    normalized_target_id: int | None
    try:
        normalized_target_id = int(target_id) if target_id is not None else None
        if normalized_target_id <= 0:
            normalized_target_id = None
    except Exception:
        normalized_target_id = None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_logs (action_type, operator, actor_user_id, target_type, target_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_action,
                normalized_operator,
                normalized_actor_user_id,
                str(target_type or "").strip(),
                normalized_target_id,
                str(detail or "").strip(),
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_audit_logs(
    limit: int = 500,
    target_type: str | None = None,
    target_id: str | int | None = None,
    action_type: str | None = None,
) -> list[Dict[str, Any]]:
    max_limit = 5000
    try:
        normalized_limit = int(limit)
    except Exception:
        normalized_limit = 500
    if normalized_limit <= 0:
        normalized_limit = 500
    normalized_limit = min(normalized_limit, max_limit)

    target_type_str = str(target_type or "").strip().lower()
    target_id_str = str(target_id or "").strip()
    action_type_str = str(action_type or "").strip().upper()

    with get_conn() as conn:
        # --- audit_log 表（企业级，有 snapshot / client_ip / trace_id）---
        q1 = """
            SELECT id, created_at, actor_user_id, actor_name AS operator, action AS action_type,
                   target_type, target_id, change_reason_code, client_ip, trace_id,
                   snapshot_before, snapshot_after, '' AS detail
            FROM audit_log
        """
        p1: list[Any] = []
        c1: list[str] = []
        if target_type_str:
            c1.append("LOWER(TRIM(target_type)) = ?")
            p1.append(target_type_str)
        if target_id_str:
            c1.append("TRIM(target_id) = ?")
            p1.append(target_id_str)
        if action_type_str:
            c1.append("UPPER(TRIM(action)) LIKE ?")
            p1.append(f"%{action_type_str}%")
        if c1:
            q1 += " WHERE " + " AND ".join(c1)
        q1 += " ORDER BY id DESC LIMIT ?"
        p1.append(normalized_limit)
        rows1 = conn.execute(q1, tuple(p1)).fetchall()

        # --- audit_logs 表（简单管理日志）---
        q2 = """
            SELECT id, created_at, actor_user_id, operator, action_type,
                   target_type, target_id, '' AS change_reason_code, '' AS client_ip, '' AS trace_id,
                   '' AS snapshot_before, '' AS snapshot_after, detail
            FROM audit_logs
        """
        p2: list[Any] = []
        c2: list[str] = []
        if target_type_str:
            c2.append("LOWER(TRIM(target_type)) = ?")
            p2.append(target_type_str)
        if target_id_str:
            c2.append("CAST(target_id AS TEXT) = ?")
            p2.append(target_id_str)
        if action_type_str:
            c2.append("UPPER(TRIM(action_type)) LIKE ?")
            p2.append(f"%{action_type_str}%")
        if c2:
            q2 += " WHERE " + " AND ".join(c2)
        q2 += " ORDER BY datetime(created_at) DESC, id DESC LIMIT ?"
        p2.append(normalized_limit)
        rows2 = conn.execute(q2, tuple(p2)).fetchall()

    merged = [dict(r) for r in rows1] + [dict(r) for r in rows2]
    merged.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return merged[:normalized_limit]


def _try_insert_admin_audit_log(
    conn: sqlite3.Connection,
    *,
    action_type: str,
    operator: str,
    action_note: str,
) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    candidate_tables = (
        "audit_logs",
        "audit_log",
        "operation_audit",
        "operation_logs",
        "admin_audit_logs",
    )
    for table_name in candidate_tables:
        if not _table_exists(conn, table_name):
            continue

        columns = _get_table_columns(conn, table_name)
        values: dict[str, Any] = {}

        if "action_type" in columns:
            values["action_type"] = action_type
        elif "action" in columns:
            values["action"] = action_type

        if "operator" in columns:
            values["operator"] = operator
        elif "actor" in columns:
            values["actor"] = operator
        elif "username" in columns:
            values["username"] = operator

        if "action_note" in columns:
            values["action_note"] = action_note
        elif "details" in columns:
            values["details"] = action_note
        elif "detail" in columns:
            values["detail"] = action_note
        elif "description" in columns:
            values["description"] = action_note

        if "created_at" in columns:
            values["created_at"] = now
        elif "timestamp" in columns:
            values["timestamp"] = now
        elif "ts" in columns:
            values["ts"] = now

        if not values:
            continue

        cols = ", ".join(values.keys())
        placeholders = ", ".join(["?"] * len(values))
        try:
            conn.execute(
                f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            return True
        except Exception:
            continue
    return False


def list_governance_rules() -> list[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, rule_key, rule_name, threshold, threshold_json, enabled, severity, version, updated_by, updated_at,
                   rule_type, status, publish_reason, published_at
            FROM governance_rules
            ORDER BY id ASC
            """
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        rule_key = str(row["rule_key"] or "").strip().upper()
        try:
            threshold = float(row["threshold"])
        except Exception:
            threshold = 0.0
        threshold_payload = _normalize_threshold_payload(
            rule_key,
            row["threshold_json"],
            fallback_threshold=threshold,
        )
        normalized_threshold = _extract_threshold_value(rule_key, threshold_payload, threshold)
        severity = _normalize_rule_severity(
            row["severity"],
            fallback=_normalize_rule_severity((DEFAULT_GOVERNANCE_RULES_BY_KEY.get(rule_key) or {}).get("severity")),
        )
        rule_type = str(row["rule_type"] or "system").strip().lower()
        if rule_type not in ("system", "custom"):
            rule_type = "system"
        status = str(row["status"] or "published").strip().lower()
        if status not in ("draft", "published"):
            status = "published"
        result.append(
            {
                "id": int(row["id"]),
                "rule_key": rule_key,
                "rule_name": str(row["rule_name"] or "").strip(),
                "threshold": normalized_threshold,
                "threshold_json": json.dumps(threshold_payload, ensure_ascii=False, sort_keys=True),
                "enabled": bool(int(row["enabled"] or 0)),
                "severity": severity,
                "version": int(row["version"] or 1),
                "updated_by": str(row["updated_by"] or "").strip() or "system",
                "updated_at": str(row["updated_at"] or "").strip(),
                "rule_type": rule_type,
                "status": status,
                "publish_reason": str(row["publish_reason"] or "").strip() or None,
                "published_at": str(row["published_at"] or "").strip() or None,
            }
        )
    return result


def get_governance_rules_by_key() -> dict[str, Dict[str, Any]]:
    result: dict[str, Dict[str, Any]] = {}
    for item in list_governance_rules():
        key = str(item.get("rule_key") or "").strip().upper()
        if not key:
            continue
        result[key] = item
    return result


def get_governance_rule(rule_id: int) -> Dict[str, Any] | None:
    try:
        normalized_rule_id = int(rule_id)
    except Exception:
        return None
    if normalized_rule_id <= 0:
        return None

    for item in list_governance_rules():
        if int(item.get("id", 0)) == normalized_rule_id:
            return item
    return None


def update_governance_rule(
    rule_id: int,
    *,
    enabled: bool | None = None,
    threshold: float | None = None,
    threshold_json: dict[str, Any] | str | None = None,
    severity: str | int | float | None = None,
    operator: str = "system",
    status: str | None = None,
    publish_reason: str | None = None,
    published_at: str | None = None,
) -> Dict[str, Any] | None:
    try:
        normalized_rule_id = int(rule_id)
    except Exception:
        return None
    if normalized_rule_id <= 0:
        return None

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, rule_key, enabled, threshold, threshold_json, severity, rule_type, status, publish_reason, published_at
            FROM governance_rules
            WHERE id = ?
            LIMIT 1
            """,
            (normalized_rule_id,),
        ).fetchone()
        if not row:
            return None

        current_enabled = bool(int(row["enabled"] or 0))
        current_rule_key = str(row["rule_key"] or "").strip().upper()
        try:
            current_threshold = float(row["threshold"])
        except Exception:
            current_threshold = 0.0
        current_threshold_payload = _normalize_threshold_payload(
            current_rule_key,
            row["threshold_json"],
            fallback_threshold=current_threshold,
        )
        current_severity = _normalize_rule_severity(
            row["severity"],
            fallback=_normalize_rule_severity((DEFAULT_GOVERNANCE_RULES_BY_KEY.get(current_rule_key) or {}).get("severity")),
        )

        next_enabled = current_enabled if enabled is None else bool(enabled)
        next_threshold_payload = _normalize_threshold_payload(
            current_rule_key,
            current_threshold_payload,
            fallback_threshold=current_threshold,
        )
        if threshold_json is not None:
            next_threshold_payload = _normalize_threshold_payload(
                current_rule_key,
                threshold_json,
                fallback_threshold=current_threshold,
            )

        next_threshold = _extract_threshold_value(current_rule_key, next_threshold_payload, current_threshold)
        if threshold is not None:
            next_threshold = float(threshold)
            next_threshold_payload[_rule_threshold_field(current_rule_key)] = next_threshold

        next_severity = current_severity if severity is None else _normalize_rule_severity(severity, fallback=current_severity)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        normalized_operator = str(operator or "").strip() or "system"
        threshold_json_text = json.dumps(next_threshold_payload, ensure_ascii=False, sort_keys=True)

        next_status = str(status).strip().lower() if status is not None else str(row["status"] or "published").strip().lower()
        if next_status not in ("draft", "published"):
            next_status = str(row["status"] or "published").strip().lower()
        next_publish_reason = str(publish_reason).strip() or None if publish_reason is not None else (str(row["publish_reason"] or "").strip() or None)
        next_published_at = str(published_at).strip() or None if published_at is not None else (str(row["published_at"] or "").strip() or None)

        conn.execute(
            """
            UPDATE governance_rules
            SET enabled = ?, threshold = ?, threshold_json = ?, severity = ?, version = version + 1, updated_by = ?, updated_at = ?,
                status = ?, publish_reason = ?, published_at = ?
            WHERE id = ?
            """,
            (
                1 if next_enabled else 0,
                next_threshold,
                threshold_json_text,
                next_severity,
                normalized_operator,
                now,
                next_status,
                next_publish_reason,
                next_published_at,
                normalized_rule_id,
            ),
        )
        conn.commit()

    return get_governance_rule(normalized_rule_id)


def insert_governance_rule(
    rule_key: str,
    rule_name: str,
    *,
    threshold: float = 0.0,
    threshold_json: dict[str, Any] | str | None = None,
    severity: str = "MEDIUM",
    operator: str = "system",
) -> Dict[str, Any] | None:
    """新增自定义规则（草稿状态）。rule_key 需唯一，建议大写+下划线。"""
    key = str(rule_key or "").strip().upper()
    name = str(rule_name or "").strip()
    if not key or not name:
        return None
    severity = _normalize_rule_severity(severity, fallback="MEDIUM")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    op = str(operator or "").strip() or "system"
    payload = _normalize_threshold_payload(key, threshold_json, fallback_threshold=threshold)
    threshold_value = _extract_threshold_value(key, payload, threshold)
    threshold_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO governance_rules (
                    rule_key, rule_name, threshold, threshold_json, enabled, severity, version, updated_by, updated_at,
                    rule_type, status
                )
                VALUES (?, ?, ?, ?, 1, ?, 1, ?, ?, 'custom', 'draft')
                """,
                (key, name, threshold_value, threshold_text, severity, op, now),
            )
            conn.commit()
            rid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        except Exception:
            return None
    return get_governance_rule(rid)


def is_governance_rule_referenced(rule_id: int) -> bool:
    """规则是否已被业务引用（如发票 rule_hit_id 命中该规则）。"""
    try:
        rid = int(rule_id)
    except Exception:
        return True
    rule = get_governance_rule(rid)
    if not rule:
        return True
    rule_key = str(rule.get("rule_key") or "").strip().upper()
    if not rule_key:
        return True
    with get_conn() as conn:
        n = conn.execute(
            "SELECT 1 FROM invoices WHERE TRIM(COALESCE(rule_hit_id, '')) IN (?, ?) LIMIT 1",
            (rule_key, str(rid)),
        ).fetchone()
        if n:
            return True
    return False


def delete_governance_rule(rule_id: int) -> bool:
    """仅允许删除：自定义规则、未发布、且未被引用。"""
    rule = get_governance_rule(rule_id)
    if not rule:
        return False
    if str(rule.get("rule_type") or "").strip().lower() != "custom":
        return False
    if str(rule.get("status") or "").strip().lower() != "draft":
        return False
    if is_governance_rule_referenced(rule_id):
        return False
    with get_conn() as conn:
        conn.execute("DELETE FROM governance_rules WHERE id = ?", (int(rule_id),))
        conn.commit()
    return True


def get_rule_audit_history(rule_id: int, limit: int = 50) -> list[Dict[str, Any]]:
    """规则审计历史（audit_log），用于历史列表与回滚。"""
    try:
        rid = int(rule_id)
    except Exception:
        return []
    target_id_str = str(rid)
    with get_conn() as conn:
        if not _table_exists(conn, "audit_log"):
            return []
        rows = conn.execute(
            """
            SELECT id, created_at, actor_user_id, actor_name, action, target_type, target_id,
                   change_reason_code, snapshot_before, snapshot_after
            FROM audit_log
            WHERE LOWER(TRIM(target_type)) = 'rule' AND TRIM(target_id) = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (target_id_str, min(int(limit), 200)),
        ).fetchall()
    return [dict(r) for r in rows]


def update_governance_rule_from_snapshot(
    rule_id: int,
    snapshot: dict[str, Any],
    *,
    operator: str = "system",
    rollback_reason: str = "ROLLBACK",
) -> Dict[str, Any] | None:
    """从审计快照恢复规则（回滚到该版本）。"""
    rule = get_governance_rule(rule_id)
    if not rule:
        return None
    rule_key = str(rule.get("rule_key") or "").strip().upper()
    enabled = snapshot.get("enabled")
    if isinstance(enabled, bool):
        pass
    elif isinstance(enabled, (int, float)):
        enabled = bool(int(enabled))
    else:
        enabled = True
    threshold = snapshot.get("threshold")
    try:
        threshold = float(threshold) if threshold is not None else 0.0
    except Exception:
        threshold = 0.0
    severity = str(snapshot.get("severity") or "MEDIUM").strip().upper()
    if severity not in ("LOW", "MEDIUM", "HIGH"):
        severity = "MEDIUM"
    threshold_json = snapshot.get("threshold_json")
    if isinstance(threshold_json, dict):
        payload = _normalize_threshold_payload(rule_key, threshold_json, fallback_threshold=threshold)
    elif isinstance(threshold_json, str):
        try:
            loaded = json.loads(threshold_json)
            payload = _normalize_threshold_payload(rule_key, loaded, fallback_threshold=threshold)
        except Exception:
            payload = _default_threshold_payload(rule_key, threshold)
    else:
        payload = _default_threshold_payload(rule_key, threshold)
    threshold_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    op = str(operator or "").strip() or "system"
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE governance_rules
            SET enabled = ?, threshold = ?, threshold_json = ?, severity = ?, version = version + 1, updated_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if enabled else 0, threshold, threshold_text, severity, op, now, int(rule_id)),
        )
        conn.commit()
    return get_governance_rule(rule_id)


def reset_user_password(
    user_id: int,
    *,
    new_password: str = DEFAULT_RESET_PASSWORD,
    operator: str = "system",
) -> bool:
    try:
        normalized_id = int(user_id)
    except Exception:
        return False
    if normalized_id <= 0:
        return False

    password_text = str(new_password or "").strip()
    if not password_text:
        return False

    updated = update_user_password(
        normalized_id,
        new_password=password_text,
        must_change_password=True,
    )
    if not updated:
        return False

    with get_conn() as conn:
        _try_insert_admin_audit_log(
            conn,
            action_type="RESET_PASSWORD",
            operator=str(operator or "system").strip() or "system",
            action_note=f"user_id={normalized_id}; default_password_reset=true",
        )
        conn.commit()
    return True


def _resolve_default_queue_owner(conn: sqlite3.Connection, department: str) -> str:
    rows = conn.execute(
        """
        SELECT username, department
        FROM users
        WHERE status = ?
        ORDER BY CASE
            WHEN username = 'finance01' THEN 0
            WHEN username = 'staff01' THEN 1
            WHEN username = 'ops01' THEN 2
            WHEN username = 'admin01' THEN 3
            ELSE 10
        END, id ASC
        """,
        (USER_STATUS_ACTIVE,),
    ).fetchall()
    if not rows:
        return ""

    dept_text = str(department or "").strip()
    if dept_text:
        for row in rows:
            user_department = str(row["department"] or "").strip()
            if user_department and user_department == dept_text:
                username = str(row["username"] or "").strip()
                if username:
                    return username

    first = rows[0]
    return str(first["username"] or "").strip()


def insert_invoice(row: Dict[str, Any]) -> int:
    applicant = str(row.get("applicant") or "-").strip() or "-"
    department = str(row.get("department") or "-").strip() or "-"
    source = str(row.get("source") or "normal").strip() or "normal"
    amount_value = str(row.get("amount") or "").strip()
    invoice_date_value = str(row.get("invoice_date") or "").strip()
    record_state = resolve_record_state(
        amount=amount_value,
        invoice_date=invoice_date_value,
        preferred=row.get("record_state"),
    )
    submitter_department = str(row.get("submitter_department") or department).strip() or department
    submitter_name = str(row.get("submitter_name") or applicant).strip() or applicant
    submitter_no = str(row.get("submitter_no") or "-").strip() or "-"
    created_at = str(row.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).strip()
    risk_level = str(row.get("risk_level") or "MEDIUM").strip().upper() or "MEDIUM"
    rule_explain = str(row.get("rule_explain") or row.get("risk_reason") or "").strip()
    rule_hit_id = str(row.get("rule_hit_id") or "").strip() or ("RULE_RISK_LEVEL" if risk_level else "")
    ai_trace_id = str(row.get("ai_trace_id") or "").strip()
    status = str(row.get("status") or row.get("approval_status") or "PENDING").strip().upper() or "PENDING"
    approval_status = str(row.get("approval_status") or status).strip().upper() or "PENDING"
    if approval_status not in {"PENDING", "APPROVED", "REJECTED", "RETURNED"}:
        approval_status = "PENDING"
    if status not in {"PENDING", "APPROVED", "REJECTED", "RETURNED"}:
        status = approval_status
    approval_stage = str(row.get("approval_stage") or "").strip().upper()
    if approval_stage not in {"L1", "L2", "DONE"}:
        approval_stage = "L1" if approval_status == "PENDING" else "DONE"
    first_approver_id = str(row.get("first_approver_id") or "").strip()
    second_approver_id = str(row.get("second_approver_id") or "").strip()
    first_approved_at = str(row.get("first_approved_at") or "").strip() or None
    second_approved_at = str(row.get("second_approved_at") or "").strip() or None
    sla_due_at = str(row.get("sla_due_at") or "").strip()
    if not sla_due_at:
        sla_due_at = _compute_sla_due_at_text(created_at, risk_level)
    queue_owner_id = str(row.get("queue_owner_id") or "").strip()
    if record_state != RECORD_STATE_LEDGER:
        queue_owner_id = ""

    raw_submitted_by_user_id = row.get("submitted_by_user_id")
    submitted_by_user_id: int | None
    try:
        submitted_by_user_id = int(raw_submitted_by_user_id) if raw_submitted_by_user_id is not None else None
        if submitted_by_user_id <= 0:
            submitted_by_user_id = None
    except Exception:
        submitted_by_user_id = None

    with get_conn() as conn:
        reference_no = _next_reference_no(conn, created_at)
        if not queue_owner_id and approval_status == "PENDING" and record_state == RECORD_STATE_LEDGER:
            queue_owner_id = _resolve_default_queue_owner(conn, department)
        placeholders = ", ".join(["?"] * 38)

        cur = conn.execute(
            """
            INSERT INTO invoices (
                reference_no, filename, amount, invoice_date, applicant, department,
                is_canton_fair, hotel_limit, mode, raw_json, created_at,
                risk_level, risk_reason, currency, fx_flag, fx_reason, manual_rate,
                manual_cny_amount, ai_risk_level, ai_analysis_reason, status, record_state, source,
                submitted_by_user_id, submitter_department, submitter_name, submitter_no,
                approval_stage, approval_status, first_approver_id, second_approver_id,
                first_approved_at, second_approved_at, sla_due_at, queue_owner_id,
                rule_hit_id, rule_explain, ai_trace_id
            )
            VALUES ("""
            + placeholders
            + """)
            """,
            (
                reference_no,
                row.get("filename"),
                amount_value,
                invoice_date_value,
                applicant,
                department,
                1 if row.get("is_canton_fair") else 0,
                int(row.get("hotel_limit", 500)),
                row.get("mode"),
                json.dumps(row.get("raw_json"), ensure_ascii=False),
                created_at,
                risk_level,
                row.get("risk_reason"),
                row.get("currency"),
                1 if row.get("fx_flag") else 0,
                row.get("fx_reason") or "",
                str(row.get("manual_rate")) if row.get("manual_rate") is not None else None,
                str(row.get("manual_cny_amount")) if row.get("manual_cny_amount") is not None else None,
                row.get("ai_risk_level"),
                row.get("ai_analysis_reason"),
                status,
                record_state,
                source,
                submitted_by_user_id,
                submitter_department,
                submitter_name,
                submitter_no,
                approval_stage,
                approval_status,
                first_approver_id,
                second_approver_id,
                first_approved_at,
                second_approved_at,
                sla_due_at,
                queue_owner_id,
                rule_hit_id,
                rule_explain,
                ai_trace_id,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _find_first_match(lines: list[str], patterns: list[str]) -> str:
    for line in lines:
        text = str(line or "")
        for p in patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m and m.group(1):
                return m.group(1).strip()
    return ""


def _extract_words_from_raw(raw: dict) -> list[str]:
    mode = raw.get("mode")
    if mode == "general_fallback":
        arr = ((raw.get("general") or {}).get("words_result") or [])
        return [
            (x.get("words") or "").strip()
            for x in arr
            if isinstance(x, dict) and isinstance(x.get("words"), str) and x.get("words").strip()
        ]

    if mode == "vat_invoice":
        wr = ((raw.get("vat") or {}).get("words_result") or {})
        lines: list[str] = []
        if isinstance(wr, dict):
            for v in wr.values():
                if isinstance(v, dict):
                    word = v.get("words")
                    if isinstance(word, str) and word.strip():
                        lines.append(word.strip())
                elif isinstance(v, str) and v.strip():
                    lines.append(v.strip())
        return lines
    return []


_ENTERPRISE_MERCHANT_ALIAS: dict[str, str] = {
    "Demo Hotel Pearl Tower": "华穗会展商务酒店",
    "Demo Dining Center": "粤商接待中心",
    "Demo Office Mart": "合规办公采购中心",
    "Regression Hotel": "穗云商务酒店",
}

_ENTERPRISE_ITEM_ALIAS: dict[str, str] = {
    "Travel": "差旅交通",
    "Office Supplies": "办公用品",
    "Dining": "商务招待",
}


def _enterprise_alias(value: Any, mapping: dict[str, str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return mapping.get(raw, raw)


def _extract_merchant_and_item(raw_json_text: str | None) -> tuple[str, str]:
    if not raw_json_text:
        return "-", "-"
    try:
        raw = json.loads(raw_json_text)
    except Exception:
        return "-", "-"
    if not isinstance(raw, dict):
        return "-", "-"

    meta = raw.get("mock_meta") or {}
    manual_entry = raw.get("manual_entry") or {}
    merchant = ""
    item = ""
    if isinstance(meta, dict):
        merchant = str(meta.get("merchant") or "").strip()
        item = str(meta.get("item") or "").strip()
    if isinstance(manual_entry, dict):
        if not merchant:
            merchant = str(manual_entry.get("seller_name") or "").strip()
        if not item:
            item = str(manual_entry.get("expense_category") or "").strip()
        if not item:
            item = str(manual_entry.get("expense_description") or "").strip()

    words = _extract_words_from_raw(raw)
    if not merchant:
        merchant = _find_first_match(words, [r"(?:merchant|store|seller|vendor)\s*[:锛歖?\s*(.+)$"])
    if not item:
        item = _find_first_match(words, [r"(?:item|service|product|detail)\s*[:锛歖?\s*(.+)$"])

    merchant = _enterprise_alias(merchant, _ENTERPRISE_MERCHANT_ALIAS)
    item = _enterprise_alias(item, _ENTERPRISE_ITEM_ALIAS)
    return merchant or "-", item or "-"


def _normalize_date_filter(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    cleaned = (
        text.replace(".", "-")
        .replace("/", "-")
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
    )[:10]
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date().isoformat()
    except Exception:
        return ""


def _normalize_risk_level(value: Any) -> str:
    raw = _safe_text(value).upper()
    if raw in {"HIGH", "MEDIUM", "LOW"}:
        return raw
    if raw == "NORMAL":
        return "LOW"
    if raw in {"ATTENTION", "MID"}:
        return "MEDIUM"
    return ""


def _normalize_verify_status(value: Any) -> str:
    raw = _safe_text(value).upper()
    if raw in {"PASS", "PASSED"}:
        return "PASS"
    if raw in {"FAIL", "FAILED"}:
        return "FAIL"
    if raw in {"PENDING", "UNVERIFIED", "UNKNOWN"}:
        return "PENDING"
    return ""


def _normalize_owner_identity_values(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        items = [values]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _safe_text(item).lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_department_names(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        items = [values]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _safe_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _resolve_invoice_scope_args(
    *,
    data_scope: dict[str, Any] | None = None,
    department: str | None = None,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[list[str], int, list[str], list[int]]:
    dept_names = _normalize_department_names(department)
    normalized_owner_user_id = 0
    try:
        normalized_owner_user_id = int(owner_user_id) if owner_user_id is not None else 0
    except Exception:
        normalized_owner_user_id = 0
    if normalized_owner_user_id <= 0:
        normalized_owner_user_id = 0
    owner_values = _normalize_owner_identity_values(owner_identity_values)
    allowed_user_ids: list[int] = []

    if isinstance(data_scope, dict):
        scope_departments = _normalize_department_names(
            data_scope.get("department_names")
            or data_scope.get("departments")
            or data_scope.get("department")
        )
        scope_owner_values = _normalize_owner_identity_values(data_scope.get("owner_identity_values"))
        scope_owner_user_id = 0
        try:
            scope_owner_user_id = int(data_scope.get("owner_user_id") or 0)
        except Exception:
            scope_owner_user_id = 0
        if scope_owner_user_id <= 0:
            scope_owner_user_id = 0
        scope_allowed_user_ids = _normalize_user_ids(data_scope.get("allowed_user_ids"))

        if scope_departments:
            dept_names = scope_departments
        if scope_owner_values:
            owner_values = scope_owner_values
        if scope_owner_user_id > 0:
            normalized_owner_user_id = scope_owner_user_id
        if scope_allowed_user_ids:
            allowed_user_ids = scope_allowed_user_ids

        # If scope explicitly requires self only, clear department widening.
        if bool(data_scope.get("self_only")) and not scope_departments:
            dept_names = []

    return (
        _normalize_department_names(dept_names),
        normalized_owner_user_id,
        _normalize_owner_identity_values(owner_values),
        allowed_user_ids,
    )


def append_invoice_scope_sql(
    sql: list[str],
    params: list[Any],
    *,
    data_scope: dict[str, Any] | None = None,
    department: str | None = None,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
    table_alias: str = "",
) -> tuple[list[str], int, list[str], list[int]]:
    (
        normalized_departments,
        normalized_owner_user_id,
        normalized_owner_identity_values,
        allowed_user_ids,
    ) = _resolve_invoice_scope_args(
        data_scope=data_scope,
        department=department,
        owner_user_id=owner_user_id,
        owner_identity_values=owner_identity_values,
    )

    prefix = f"{table_alias}." if _safe_text(table_alias) else ""

    scope_parts: list[str] = []

    if len(normalized_departments) == 1:
        scope_parts.append(f"({prefix}department = ?)")
        params.append(normalized_departments[0])
    elif normalized_departments:
        placeholders = ",".join(["?"] * len(normalized_departments))
        scope_parts.append(f"({prefix}department IN ({placeholders}))")
        params.extend(normalized_departments)

    if normalized_owner_user_id > 0 or normalized_owner_identity_values:
        owner_clauses: list[str] = []
        if normalized_owner_user_id > 0:
            owner_clauses.append(f"{prefix}submitted_by_user_id = ?")
            params.append(normalized_owner_user_id)
        if normalized_owner_identity_values:
            placeholders_no = ",".join(["?"] * len(normalized_owner_identity_values))
            owner_clauses.append(f"LOWER(COALESCE({prefix}submitter_no, '')) IN ({placeholders_no})")
            params.extend(normalized_owner_identity_values)
            placeholders_name = ",".join(["?"] * len(normalized_owner_identity_values))
            owner_clauses.append(f"LOWER(COALESCE({prefix}submitter_name, '')) IN ({placeholders_name})")
            params.extend(normalized_owner_identity_values)
            placeholders_applicant = ",".join(["?"] * len(normalized_owner_identity_values))
            owner_clauses.append(f"LOWER(COALESCE({prefix}applicant, '')) IN ({placeholders_applicant})")
            params.extend(normalized_owner_identity_values)
        if owner_clauses:
            scope_parts.append("(" + " OR ".join(owner_clauses) + ")")

    if allowed_user_ids:
        placeholders_uid = ",".join(["?"] * len(allowed_user_ids))
        scope_parts.append(f"({prefix}submitted_by_user_id IN ({placeholders_uid}))")
        params.extend(allowed_user_ids)

    if scope_parts:
        sql.append("AND (" + " OR ".join(scope_parts) + ") ")

    return normalized_departments, normalized_owner_user_id, normalized_owner_identity_values, allowed_user_ids


def list_invoices(
    limit: int = 50,
    department: str | None = None,
    *,
    offset: int = 0,
    record_state: str | None = RECORD_STATE_LEDGER,
    filters: dict[str, Any] | None = None,
    fetch_limit: int | None = None,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
    data_scope: dict[str, Any] | None = None,
) -> list[Dict[str, Any]]:
    normalized_record_state = (
        normalize_record_state(record_state, fallback=RECORD_STATE_LEDGER)
        if record_state is not None
        else ""
    )

    filters = filters or {}
    keyword = _safe_text(filters.get("keyword")).lower()
    expense_category = _safe_text(filters.get("expense_category"))
    risk_level = _normalize_risk_level(filters.get("risk_level"))
    verify_status = _normalize_verify_status(filters.get("verify_status"))
    ledger_date_start = _normalize_date_filter(filters.get("ledger_date_start"))
    ledger_date_end = _normalize_date_filter(filters.get("ledger_date_end"))
    reference_no = _safe_text(filters.get("reference_no"))
    filter_invoice_id: int | None = None
    try:
        raw_id = filters.get("invoice_id")
        if raw_id is not None and str(raw_id).strip() != "":
            filter_invoice_id = int(raw_id)
            if filter_invoice_id <= 0:
                filter_invoice_id = None
    except (TypeError, ValueError):
        filter_invoice_id = None

    max_candidates = fetch_limit or (
        1 if filter_invoice_id is not None
        else (5000 if (keyword or expense_category or reference_no) else limit)
    )

    sql = [
        "SELECT id, reference_no, filename, amount, invoice_date, applicant, department, "
        "is_canton_fair, hotel_limit, mode, raw_json, created_at, "
        "risk_level, risk_reason, currency, fx_flag, fx_reason, manual_rate, manual_cny_amount, "
        "COALESCE((SELECT re.risk_score FROM risk_events re "
        "WHERE re.invoice_id = invoices.id ORDER BY datetime(re.created_at) DESC, re.id DESC LIMIT 1), "
        "(SELECT apl.risk_score FROM ai_prompt_ledger apl "
        "WHERE apl.invoice_id = invoices.id ORDER BY datetime(apl.created_at) DESC, apl.id DESC LIMIT 1)) AS risk_score, "
        "ai_risk_level, ai_analysis_reason, status, record_state, source, "
        "submitted_by_user_id, submitter_department, submitter_name, submitter_no, "
        "verify_status, verify_message, verify_checked_at, verify_count, verify_provider, "
        "verify_request_id, verify_latency_ms, verify_status_code, "
        "approval_stage, approval_status, first_approver_id, second_approver_id, "
        "first_approved_at, second_approved_at, sla_due_at, queue_owner_id, "
        "rule_hit_id, rule_explain, ai_trace_id "
        "FROM invoices WHERE 1=1 "
    ]
    params: list[Any] = []
    append_invoice_scope_sql(
        sql,
        params,
        data_scope=data_scope,
        department=department,
        owner_user_id=owner_user_id,
        owner_identity_values=owner_identity_values,
        table_alias="",
    )
    # 当有 invoice_id 时，只应用必要的状态筛选，忽略其他筛选条件
    if filter_invoice_id is None:
        # 只有在没有 invoice_id 时才应用这些筛选条件
        if normalized_record_state:
            sql.append("AND UPPER(COALESCE(record_state, 'DRAFT')) = ? ")
            params.append(normalized_record_state)
        # 待补录列表不展示已打回的单据（打回后 approval_status=RETURNED，仍为 DRAFT）
        if normalized_record_state == "DRAFT":
            sql.append("AND UPPER(TRIM(COALESCE(approval_status, ''))) != 'RETURNED' ")
        if risk_level:
            sql.append("AND (UPPER(COALESCE(risk_level, '')) = ? OR UPPER(COALESCE(ai_risk_level, '')) = ?) ")
            params.extend([risk_level, risk_level])
        if verify_status == "PASS":
            sql.append("AND UPPER(COALESCE(verify_status, 'PENDING')) IN ('PASS', 'PASSED') ")
        elif verify_status == "FAIL":
            sql.append("AND UPPER(COALESCE(verify_status, 'PENDING')) IN ('FAIL', 'FAILED') ")
        elif verify_status == "PENDING":
            sql.append(
                "AND UPPER(COALESCE(verify_status, 'PENDING')) NOT IN ('PASS', 'PASSED', 'FAIL', 'FAILED') "
            )
        if ledger_date_start:
            sql.append("AND date(created_at) >= ? ")
            params.append(ledger_date_start)
        if ledger_date_end:
            sql.append("AND date(created_at) <= ? ")
            params.append(ledger_date_end)
    else:
        # 有 invoice_id 时，只应用 record_state 筛选（用于区分 ledger/draft tab）
        if normalized_record_state:
            sql.append("AND UPPER(COALESCE(record_state, 'DRAFT')) = ? ")
            params.append(normalized_record_state)
    # 当有 invoice_id 时，只按 invoice_id 查询，忽略其他筛选条件
    if filter_invoice_id is not None:
        sql.append("AND id = ? ")
        params.append(filter_invoice_id)
    else:
        # 只有在没有 invoice_id 时才应用其他筛选条件
        if reference_no:
            sql.append("AND COALESCE(reference_no, '') = ? ")
            params.append(reference_no)
        if keyword:
            like_param = f"%{keyword}%"
            sql.append(
                "AND (LOWER(COALESCE(reference_no, '')) LIKE ? "
                "OR LOWER(COALESCE(applicant, '')) LIKE ? "
                "OR LOWER(COALESCE(department, '')) LIKE ? "
                "OR LOWER(COALESCE(raw_json, '')) LIKE ?) "
            )
            params.extend([like_param, like_param, like_param, like_param])
    sql.append("ORDER BY datetime(created_at) DESC, id DESC LIMIT ?")
    params.append(max_candidates)
    safe_offset = max(0, int(offset)) if offset else 0
    if safe_offset > 0:
        sql.append(" OFFSET ?")
        params.append(safe_offset)

    with get_conn() as conn:
        rows = conn.execute("".join(sql), tuple(params)).fetchall()

    result: list[Dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        merchant_name, item_name = _extract_merchant_and_item(row.get("raw_json"))
        row["merchant_name"] = merchant_name
        row["item_name"] = item_name
        row["record_state"] = normalize_record_state(row.get("record_state"), fallback=RECORD_STATE_DRAFT)
        row["risk_reason_biz"] = to_business_risk_reason(
            row.get("risk_reason"),
            source=row.get("source"),
            amount=row.get("amount"),
            threshold=row.get("hotel_limit"),
        )
        raw_rule_explain = _safe_text(row.get("rule_explain")) or _safe_text(row.get("risk_reason"))
        row["rule_explain_biz"] = to_business_risk_reason(
            raw_rule_explain,
            source=row.get("source"),
            amount=row.get("amount"),
            threshold=row.get("hotel_limit"),
        )
        if row["record_state"] == RECORD_STATE_DRAFT and not _has_ledger_required_fields(
            row.get("amount"),
            row.get("invoice_date"),
        ):
            row["risk_reason_biz"] = "凭证要素不全（缺：金额/日期），需补录后复核"
            row["rule_explain_biz"] = row["risk_reason_biz"]
        with_cn_status_fields(row)

        # 当有 invoice_id 时，跳过 Python 侧筛选，直接添加结果
        if filter_invoice_id is None:
            # Python 侧补充筛选：费用类别（来自 raw_json）与商户关键词匹配
            if expense_category and _safe_text(item_name) != expense_category:
                continue
            if keyword:
                joined = " ".join(
                    [
                        _safe_text(row.get("reference_no")).lower(),
                        _safe_text(row.get("applicant")).lower(),
                        _safe_text(row.get("department")).lower(),
                        _safe_text(merchant_name).lower(),
                        _safe_text(item_name).lower(),
                    ]
                )
                if keyword not in joined:
                    continue

        row.pop("raw_json", None)
        result.append(row)
        if len(result) >= limit:
            break
    return result


def get_invoice_id_by_risk_case_id(case_id: int) -> int | None:
    """根据风险案件 id 解析出关联的凭证 id（risk_cases -> risk_events -> invoice_id）。"""
    if not case_id or case_id <= 0:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT re.invoice_id
            FROM risk_cases rc
            LEFT JOIN risk_events re ON re.id = rc.event_id
            WHERE rc.id = ?
            LIMIT 1
            """,
            (case_id,),
        ).fetchone()
    if not row:
        return None
    try:
        vid = int(row[0])
        return vid if vid > 0 else None
    except (TypeError, ValueError):
        return None


def list_all_invoices_for_export(
    department: str | None = None,
    *,
    record_state: str | None = RECORD_STATE_LEDGER,
    filters: dict[str, Any] | None = None,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
    data_scope: dict[str, Any] | None = None,
) -> list[Dict[str, Any]]:
    # 复用统一筛选逻辑，导出场景提升拉取上限
    return list_invoices(
        limit=10000,
        department=department,
        record_state=record_state,
        filters=filters,
        fetch_limit=10000,
        owner_user_id=owner_user_id,
        owner_identity_values=owner_identity_values,
        data_scope=data_scope,
    )


def summarize_ledger_stats(
    *,
    department: str | None = None,
    filters: dict[str, Any] | None = None,
    max_rows: int = 10000,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
    data_scope: dict[str, Any] | None = None,
    record_state: str | None = RECORD_STATE_LEDGER,
) -> dict[str, Any]:
    """按筛选条件计算台账关键指标（笔数、金额、异常、未验真）；支持按 record_state 区分已入账/待补录。"""
    normalized_state = (
        normalize_record_state(record_state, fallback=RECORD_STATE_LEDGER)
        if record_state is not None
        else RECORD_STATE_LEDGER
    )
    rows = list_invoices(
        limit=max_rows,
        department=department,
        record_state=normalized_state,
        filters=filters,
        fetch_limit=max_rows,
        owner_user_id=owner_user_id,
        owner_identity_values=owner_identity_values,
        data_scope=data_scope,
    )

    def _to_amount(value: Any) -> float:
        text = _safe_text(value)
        cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
        try:
            return float(cleaned)
        except Exception:
            return 0.0

    total_amount = 0.0
    abnormal_count = 0
    unverified_count = 0
    expense_categories: set[str] = set()

    for row in rows:
        total_amount += _to_amount(row.get("amount"))
        risk_level = _safe_text(row.get("risk_level") or row.get("ai_risk_level")).upper()
        verify_status = _safe_text(row.get("verify_status")).upper()
        if risk_level in {"HIGH", "MEDIUM"}:
            abnormal_count += 1
        if verify_status not in {"PASS", "PASSED"}:
            unverified_count += 1
        if _safe_text(row.get("item_name")):
            expense_categories.add(_safe_text(row.get("item_name")))

    return {
        "rows": rows,
        "total_count": len(rows),
        "total_amount": total_amount,
        "abnormal_count": abnormal_count,
        "unverified_count": unverified_count,
        "expense_categories": sorted(expense_categories),
    }


def update_invoice_status(
    invoice_id: int,
    status: str,
    *,
    ledger_only: bool = True,
) -> bool:
    normalized = str(status or "").strip().upper()
    if normalized not in {"PENDING", "APPROVED", "REJECTED", "RETURNED"}:
        return False

    where_sql = "id = ?"
    if ledger_only:
        where_sql += " AND UPPER(COALESCE(record_state, 'DRAFT')) = 'LEDGER'"

    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE invoices
            SET status = ?,
                approval_status = ?,
                approval_stage = CASE WHEN ? = 'PENDING' THEN 'L1' ELSE 'DONE' END
            WHERE """
            + where_sql,
            (normalized, normalized, normalized, invoice_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_invoices(invoice_ids: list[int]) -> dict[str, Any]:
    normalized_ids: list[int] = []
    for raw in invoice_ids:
        try:
            invoice_id = int(raw)
        except Exception:
            continue
        if invoice_id > 0 and invoice_id not in normalized_ids:
            normalized_ids.append(invoice_id)

    if not normalized_ids:
        return {"deleted_count": 0, "filenames": [], "ids": []}

    placeholders = ",".join(["?"] * len(normalized_ids))
    existing_ids: list[int] = []
    filenames: list[str] = []
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id, filename FROM invoices WHERE id IN ({placeholders})",
            tuple(normalized_ids),
        ).fetchall()
        filenames = [
            str(row["filename"])
            for row in rows
            if isinstance(row["filename"], str) and row["filename"].strip()
        ]
        existing_ids = [int(row["id"]) for row in rows]

        if existing_ids:
            existing_placeholders = ",".join(["?"] * len(existing_ids))
            conn.execute(
                f"DELETE FROM invoices WHERE id IN ({existing_placeholders})",
                tuple(existing_ids),
            )
            conn.commit()

    return {
        "deleted_count": len(existing_ids),
        "filenames": filenames,
        "ids": existing_ids,
    }


def get_system_settings() -> Dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            ("system",),
        ).fetchone()
        stored = _safe_json_loads(row["value"]) if row and row["value"] else {}
        if not isinstance(stored, dict):
            stored = {}
        return _deep_merge(DEFAULT_SYSTEM_SETTINGS, stored)


def save_system_settings(next_settings: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(next_settings, dict):
        next_settings = {}

    current = get_system_settings()
    merged = _deep_merge(current, next_settings)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            ("system", json.dumps(merged, ensure_ascii=False), now),
        )
        conn.commit()
    return merged


def _workflow_row_payload(row: sqlite3.Row | None, *, include_config: bool = True) -> Dict[str, Any] | None:
    if row is None:
        return None

    config_obj = _safe_json_loads(str(row["config_json"] or ""))
    normalized_config = normalize_workflow_config(config_obj if isinstance(config_obj, dict) else {})
    payload: Dict[str, Any] = {
        "id": int(row["id"] or 0),
        "version": int(row["version"] or 0),
        "status": _safe_text(row["status"]).upper(),
        "scope": _safe_text(row["scope"], "ALL"),
        "reason": _safe_text(row["reason"]),
        "by": _safe_text(row["by"], "system"),
        "at": _safe_text(row["at"]),
        "nodes_summary": {
            step: {
                "required_role": _safe_text((normalized_config.get("nodes", {}).get(step, {}) or {}).get("required_role")),
                "conditions": dict(((normalized_config.get("nodes", {}).get(step, {}) or {}).get("conditions") or {})),
            }
            for step in WORKFLOW_STEP_CODES
        },
    }
    if include_config:
        payload["config"] = normalized_config
    return payload


def _next_workflow_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM workflow_config").fetchone()
    current = int(row["v"] or 0) if row else 0
    return current + 1


def get_workflow_current_config() -> Dict[str, Any]:
    with get_conn() as conn:
        _seed_workflow_config_if_empty(conn)
        row = conn.execute(
            """
            SELECT id, version, status, config_json, scope, reason, "by", at
            FROM workflow_config
            WHERE UPPER(COALESCE(status, '')) = ?
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            (WORKFLOW_STATUS_PUBLISHED,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT id, version, status, config_json, scope, reason, "by", at
                FROM workflow_config
                ORDER BY version DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
    payload = _workflow_row_payload(row, include_config=True)
    if isinstance(payload, dict):
        return payload
    return {
        "id": 0,
        "version": 0,
        "status": WORKFLOW_STATUS_PUBLISHED,
        "scope": "ALL",
        "reason": "",
        "by": "system",
        "at": "",
        "config": normalize_workflow_config(DEFAULT_WORKFLOW_CONSOLE_CONFIG),
        "nodes_summary": {},
    }


def list_workflow_versions(*, limit: int = 30, include_config: bool = False) -> list[Dict[str, Any]]:
    try:
        safe_limit = int(limit or 30)
    except Exception:
        safe_limit = 30
    safe_limit = max(1, min(safe_limit, 200))
    with get_conn() as conn:
        _seed_workflow_config_if_empty(conn)
        rows = conn.execute(
            """
            SELECT id, version, status, config_json, scope, reason, "by", at
            FROM workflow_config
            ORDER BY version DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    result: list[Dict[str, Any]] = []
    for row in rows:
        payload = _workflow_row_payload(row, include_config=include_config)
        if isinstance(payload, dict):
            result.append(payload)
    return result


def save_workflow_draft(
    *,
    config: Any,
    scope: Any = "ALL",
    reason: Any = "",
    operator: Any = "system",
) -> Dict[str, Any]:
    normalized_config = normalize_workflow_config(config)
    normalized_scope = _safe_text(scope, "ALL") or "ALL"
    normalized_reason = _safe_text(reason)
    normalized_operator = _safe_text(operator, "system") or "system"

    with get_conn() as conn:
        _seed_workflow_config_if_empty(conn)
        next_version = _next_workflow_version(conn)
        now_text = _workflow_now_text()
        cur = conn.execute(
            """
            INSERT INTO workflow_config (version, status, config_json, scope, reason, "by", at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                next_version,
                WORKFLOW_STATUS_DRAFT,
                json.dumps(normalized_config, ensure_ascii=False),
                normalized_scope,
                normalized_reason,
                normalized_operator,
                now_text,
            ),
        )
        row = conn.execute(
            """
            SELECT id, version, status, config_json, scope, reason, "by", at
            FROM workflow_config
            WHERE id = ?
            LIMIT 1
            """,
            (int(cur.lastrowid),),
        ).fetchone()
        conn.commit()

    payload = _workflow_row_payload(row, include_config=True)
    return payload if isinstance(payload, dict) else get_workflow_current_config()


def publish_workflow_config(
    *,
    config: Any = None,
    scope: Any = "",
    reason: Any = "",
    operator: Any = "system",
) -> Dict[str, Any]:
    normalized_scope = _safe_text(scope)
    normalized_reason = _safe_text(reason)
    normalized_operator = _safe_text(operator, "system") or "system"

    with get_conn() as conn:
        _seed_workflow_config_if_empty(conn)

        if isinstance(config, dict):
            normalized_config = normalize_workflow_config(config)
        else:
            draft_row = conn.execute(
                """
                SELECT id, version, status, config_json, scope, reason, "by", at
                FROM workflow_config
                WHERE UPPER(COALESCE(status, '')) = ?
                ORDER BY version DESC, id DESC
                LIMIT 1
                """,
                (WORKFLOW_STATUS_DRAFT,),
            ).fetchone()
            if draft_row is not None:
                draft_payload = _workflow_row_payload(draft_row, include_config=True) or {}
                normalized_config = normalize_workflow_config(draft_payload.get("config"))
                if not normalized_scope:
                    normalized_scope = _safe_text(draft_row["scope"], "ALL")
            else:
                current_row = conn.execute(
                    """
                    SELECT id, version, status, config_json, scope, reason, "by", at
                    FROM workflow_config
                    WHERE UPPER(COALESCE(status, '')) = ?
                    ORDER BY version DESC, id DESC
                    LIMIT 1
                    """,
                    (WORKFLOW_STATUS_PUBLISHED,),
                ).fetchone()
                if current_row is not None:
                    current_payload = _workflow_row_payload(current_row, include_config=True) or {}
                    normalized_config = normalize_workflow_config(current_payload.get("config"))
                    if not normalized_scope:
                        normalized_scope = _safe_text(current_row["scope"], "ALL")
                else:
                    normalized_config = normalize_workflow_config(DEFAULT_WORKFLOW_CONSOLE_CONFIG)
                    if not normalized_scope:
                        normalized_scope = "ALL"

        if not normalized_scope:
            normalized_scope = "ALL"

        next_version = _next_workflow_version(conn)
        cur = conn.execute(
            """
            INSERT INTO workflow_config (version, status, config_json, scope, reason, "by", at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                next_version,
                WORKFLOW_STATUS_PUBLISHED,
                json.dumps(normalized_config, ensure_ascii=False),
                normalized_scope,
                normalized_reason,
                normalized_operator,
                _workflow_now_text(),
            ),
        )
        row = conn.execute(
            """
            SELECT id, version, status, config_json, scope, reason, "by", at
            FROM workflow_config
            WHERE id = ?
            LIMIT 1
            """,
            (int(cur.lastrowid),),
        ).fetchone()
        conn.commit()

    payload = _workflow_row_payload(row, include_config=True)
    return payload if isinstance(payload, dict) else get_workflow_current_config()


def rollback_workflow_config(
    *,
    target_version: Any,
    reason: Any = "",
    operator: Any = "system",
) -> Dict[str, Any] | None:
    try:
        normalized_target_version = int(target_version)
    except Exception:
        return None
    if normalized_target_version <= 0:
        return None

    normalized_reason = _safe_text(reason)
    normalized_operator = _safe_text(operator, "system") or "system"

    with get_conn() as conn:
        _seed_workflow_config_if_empty(conn)
        target_row = conn.execute(
            """
            SELECT id, version, status, config_json, scope, reason, "by", at
            FROM workflow_config
            WHERE version = ?
            LIMIT 1
            """,
            (normalized_target_version,),
        ).fetchone()
        if target_row is None:
            return None

        config_obj = _safe_json_loads(str(target_row["config_json"] or ""))
        normalized_config = normalize_workflow_config(config_obj if isinstance(config_obj, dict) else {})
        scope = _safe_text(target_row["scope"], "ALL")
        reason_text = normalized_reason or f"ROLLBACK_TO_V{normalized_target_version}"

        next_version = _next_workflow_version(conn)
        cur = conn.execute(
            """
            INSERT INTO workflow_config (version, status, config_json, scope, reason, "by", at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                next_version,
                WORKFLOW_STATUS_PUBLISHED,
                json.dumps(normalized_config, ensure_ascii=False),
                scope,
                reason_text,
                normalized_operator,
                _workflow_now_text(),
            ),
        )
        row = conn.execute(
            """
            SELECT id, version, status, config_json, scope, reason, "by", at
            FROM workflow_config
            WHERE id = ?
            LIMIT 1
            """,
            (int(cur.lastrowid),),
        ).fetchone()
        conn.commit()

    payload = _workflow_row_payload(row, include_config=True)
    if isinstance(payload, dict):
        payload["rolled_back_from_version"] = normalized_target_version
    return payload


def _parse_amount(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def _choose_day(created_at: Any, invoice_date: Any) -> str:
    created = str(created_at or "").strip()
    if len(created) >= 10:
        return created[:10]
    inv_date = str(invoice_date or "").strip()
    if len(inv_date) >= 10:
        return inv_date[:10]
    return date.today().isoformat()


def _resolve_days(range_key: str) -> int | None:
    normalized = str(range_key or "").strip().lower()
    mapping = {
        "1d": 1,
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "180d": 180,
        "365d": 365,
        "1y": 365,
        "today": 1,
        "yesterday": 1,
        "all": None,
    }
    return mapping.get(normalized, 30)


def get_dashboard_stats(
    range_key: str = "30d",
    department: str | None = None,
    *,
    data_scope: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    days = _resolve_days(range_key)
    normalized = str(range_key or "").strip().lower()
    rows = list_invoices(
        limit=10000,
        department=department,
        record_state=RECORD_STATE_LEDGER,
        fetch_limit=10000,
        data_scope=data_scope,
    )

    def _created_date_text(item: dict[str, Any]) -> str:
        created = _safe_text(item.get("created_at"))
        return created[:10] if len(created) >= 10 else ""

    if normalized == "yesterday":
        target = (date.today() - timedelta(days=1)).isoformat()
        rows = [row for row in rows if _created_date_text(row) == target]
    elif normalized in {"1d", "today"}:
        target = date.today().isoformat()
        rows = [row for row in rows if _created_date_text(row) == target]
    elif days is not None:
        cutoff = datetime.now() - timedelta(days=max(days, 1))
        filtered: list[dict[str, Any]] = []
        for row in rows:
            created_dt = _parse_datetime(row.get("created_at"))
            if created_dt is not None and created_dt >= cutoff:
                filtered.append(row)
        rows = filtered

    total = len(rows)
    total_amount = 0.0

    risk_distribution = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    status_distribution = {"PENDING": 0, "APPROVED": 0, "REJECTED": 0, "OTHER": 0}
    department_counts: dict[str, int] = {}
    trend: dict[str, dict[str, Any]] = {}

    for row in rows:
        row_dict = dict(row)

        amount = _parse_amount(row_dict.get("amount"))
        total_amount += amount

        risk = str(row_dict.get("risk_level") or "").strip().upper()
        if risk not in risk_distribution:
            risk = "UNKNOWN"
        risk_distribution[risk] += 1

        status = str(row_dict.get("status") or "PENDING").strip().upper()
        if status not in {"PENDING", "APPROVED", "REJECTED"}:
            status = "OTHER"
        status_distribution[status] += 1

        dept = str(row_dict.get("department") or "-").strip() or "-"
        department_counts[dept] = department_counts.get(dept, 0) + 1

        day_key = _choose_day(row_dict.get("created_at"), row_dict.get("invoice_date"))
        slot = trend.setdefault(day_key, {"date": day_key, "count": 0, "amount": 0.0})
        slot["count"] += 1
        slot["amount"] += amount

    trend_rows = [trend[k] for k in sorted(trend.keys())]
    for item in trend_rows:
        item["amount"] = round(float(item["amount"]), 2)

    dept_rows = [
        {"department": name, "count": count}
        for name, count in sorted(department_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    avg_amount = round(total_amount / total, 2) if total else 0.0
    summary = {
        "total_invoices": total,
        "total_amount": round(total_amount, 2),
        "avg_amount": avg_amount,
        "pending_count": status_distribution["PENDING"],
        "approved_count": status_distribution["APPROVED"],
        "rejected_count": status_distribution["REJECTED"],
        "high_risk_count": risk_distribution["HIGH"],
    }

    if normalized == "yesterday":
        start_date = (date.today() - timedelta(days=1)).isoformat()
    elif normalized in {"1d", "today"}:
        start_date = date.today().isoformat()
    elif days is None:
        start_date = trend_rows[0]["date"] if trend_rows else None
    else:
        start_date = (datetime.now() - timedelta(days=max(days - 1, 0))).date().isoformat()

    return {
        "range": str(range_key or "30d").lower(),
        "time_window": {
            "start_date": start_date,
            "end_date": date.today().isoformat(),
            "days": days,
        },
        "summary": summary,
        "risk_distribution": risk_distribution,
        "status_distribution": status_distribution,
        "department_distribution": dept_rows,
        "daily_trend": trend_rows,
    }


def _parse_day(value: str) -> date:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return date.today()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _resolve_range_window(range_key: str) -> tuple[str, date, date]:
    key = str(range_key or "7d").strip().lower()
    today = date.today()

    if key in {"today", "1d"}:
        return "1d", today, today
    if key == "yesterday":
        yday = today - timedelta(days=1)
        return "yesterday", yday, yday
    if key == "7d":
        return "7d", today - timedelta(days=6), today
    if key == "30d":
        return "30d", today - timedelta(days=29), today
    if key == "90d":
        return "90d", today - timedelta(days=89), today
    if key in {"180d", "365d", "1y"}:
        days = 180 if key == "180d" else 365
        return key, today - timedelta(days=days - 1), today
    return "7d", today - timedelta(days=6), today


def _format_mmdd(day_value: date) -> str:
    return f"{day_value.month:02d}.{day_value.day:02d}"


def _format_relative_time(created_at: Any) -> str:
    created_dt = _parse_datetime(created_at)
    if created_dt is None:
        return "-"

    now = datetime.now()
    diff_seconds = int((now - created_dt).total_seconds())
    if diff_seconds < 0:
        return "刚刚"
    if diff_seconds < 60:
        return "刚刚"
    if diff_seconds < 3600:
        return f"{diff_seconds // 60}分钟前"
    if diff_seconds < 86400:
        return f"{diff_seconds // 3600}小时前"
    return f"{diff_seconds // 86400}天前"


def _expense_category(item: str, merchant: str) -> str:
    text = f"{item} {merchant}".lower()
    if any(k in text for k in ("酒店", "住宿", "宾馆", "hotel")):
        return "住宿"
    if any(k in text for k in ("交通", "差旅", "滴滴", "机票", "火车", "出行", "taxi", "train", "flight")):
        return "差旅交通"
    if any(k in text for k in ("餐", "饭", "咖啡", "饮品", "food", "meal")):
        return "餐饮"
    if any(k in text for k in ("办公", "文具", "耗材", "打印", "office", "stationery")):
        return "办公采购"
    if any(k in text for k in ("通讯", "网络", "话费", "通信", "phone", "network")):
        return "通讯"
    return "其他"


def get_dashboard_data(
    range_key: str = "7d",
    department: str | None = None,
    *,
    data_scope: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_range, start_date, end_date = _resolve_range_window(range_key)
    rows = list_invoices(
        limit=10000,
        department=department,
        record_state=RECORD_STATE_LEDGER,
        fetch_limit=10000,
        data_scope=data_scope,
    )

    trend_bucket: dict[str, dict[str, float]] = {}
    day_cursor = start_date
    while day_cursor <= end_date:
        trend_bucket[day_cursor.isoformat()] = {"apply_amount": 0.0, "intercept_amount": 0.0}
        day_cursor += timedelta(days=1)

    total_count = 0
    high_risk_count = 0
    approved_count = 0
    rejected_count = 0
    saved_money = 0.0

    department_amount: dict[str, float] = {}
    cost_composition: dict[str, int] = {}

    serial_hits = 0
    sensitive_hits = 0
    title_hits = 0
    over_limit_hits = 0

    alerts_candidates: list[dict[str, Any]] = []

    for row in rows:
        row_map = dict(row)
        day_key = _choose_day(row_map.get("created_at"), row_map.get("invoice_date"))
        day_value = _parse_day(day_key)
        if day_value < start_date or day_value > end_date:
            continue

        amount = _parse_amount(row_map.get("amount"))
        risk_level = str(row_map.get("risk_level") or "").strip().upper()
        status = str(row_map.get("status") or "PENDING").strip().upper()
        risk_reason = str(row_map.get("risk_reason") or "").strip()
        risk_reason_display = to_business_risk_reason(
            risk_reason,
            source=row_map.get("source"),
            amount=row_map.get("amount"),
            threshold=row_map.get("hotel_limit"),
        )
        risk_reason_l = risk_reason.lower()

        total_count += 1
        if risk_level == "HIGH":
            high_risk_count += 1
        if status == "APPROVED":
            approved_count += 1
        if status == "REJECTED":
            rejected_count += 1
            saved_money += amount

        slot = trend_bucket.setdefault(day_key, {"apply_amount": 0.0, "intercept_amount": 0.0})
        slot["apply_amount"] += amount
        if status == "REJECTED" or risk_level == "HIGH":
            slot["intercept_amount"] += amount

        department = str(row_map.get("department") or "-").strip() or "-"
        department_amount[department] = department_amount.get(department, 0.0) + amount

        merchant, item = _extract_merchant_and_item(row_map.get("raw_json"))
        category = _expense_category(item, merchant)
        cost_composition[category] = cost_composition.get(category, 0) + 1

        if "duplicate" in risk_reason_l:
            serial_hits += 1
        if "sensitive" in risk_reason_l:
            sensitive_hits += 1
        if "missing" in risk_reason_l:
            title_hits += 1
        if any(flag in risk_reason_l for flag in ("limit", "threshold", "warning", "over")):
            over_limit_hits += 1

        if status == "REJECTED" or risk_level in {"HIGH", "MEDIUM"}:
            level = "HIGH" if status == "REJECTED" or risk_level == "HIGH" else "MEDIUM"
            event_dt = _parse_datetime(row_map.get("created_at"))
            event_ts = event_dt.timestamp() if event_dt else 0.0
            reference_no = str(row_map.get("reference_no") or "").strip() or "-"
            department_text = str(row_map.get("department") or "").strip() or "-"
            seller = merchant if merchant and merchant != "-" else "未知商户"
            expense_type = category if category and category != "-" else "未分类"
            amount_text = str(row_map.get("amount") or "").strip() or "金额未知"
            invoice_date_text = str(row_map.get("invoice_date") or "").strip() or "日期未知"
            filename_text = str(row_map.get("filename") or "").strip() or "-"
            risk_text = risk_reason_display.split(";")[0].strip() if risk_reason_display else "规则引擎告警"
            display_title = f"报销单 {reference_no} | {department_text} | {amount_text} | {invoice_date_text}"
            alerts_candidates.append(
                {
                    "display_title": display_title,
                    "reference_no": reference_no,
                    "department": department_text,
                    "seller": seller,
                    "expense_type": expense_type,
                    "amount": amount_text,
                    "invoice_date": invoice_date_text,
                    "filename": filename_text,
                    "vendor": seller,
                    "risk": risk_text,
                    "risk_reason": risk_text,
                    "time": _format_relative_time(row_map.get("created_at")),
                    "level": level,
                    "_ts": event_ts,
                }
            )

    trend_days = sorted(trend_bucket.keys())
    trend_dates = [_format_mmdd(_parse_day(day_text)) for day_text in trend_days]
    trend_apply = [round(float(trend_bucket[day_text]["apply_amount"]), 2) for day_text in trend_days]
    trend_intercept = [round(float(trend_bucket[day_text]["intercept_amount"]), 2) for day_text in trend_days]

    dept_rows = sorted(department_amount.items(), key=lambda x: (-x[1], x[0]))[:5]
    dept_names = [name for name, _ in dept_rows]
    dept_values = [round(float(value), 2) for _, value in dept_rows]

    comp_rows = sorted(cost_composition.items(), key=lambda x: (-x[1], x[0]))[:5]
    comp_labels = [name for name, _ in comp_rows]
    comp_values = [int(value) for _, value in comp_rows]

    denominator = total_count if total_count > 0 else 1
    radar_data = [
        int(round(serial_hits * 100 / denominator)),
        int(round(sensitive_hits * 100 / denominator)),
        int(round(title_hits * 100 / denominator)),
        int(round(rejected_count * 100 / denominator)),
        int(round(over_limit_hits * 100 / denominator)),
    ]

    alerts_sorted = sorted(alerts_candidates, key=lambda x: -float(x.get("_ts", 0.0)))[:5]
    alerts = []
    for item in alerts_sorted:
        next_item = dict(item)
        next_item.pop("_ts", None)
        alerts.append(next_item)

    auto_pass_rate = round((approved_count * 100.0 / total_count), 1) if total_count else 0.0

    return {
        "range": normalized_range,
        "kpi": {
            "total_count": total_count,
            "high_risk": high_risk_count,
            "saved_money": round(saved_money, 2),
            "auto_pass_rate": auto_pass_rate,
        },
        "trend": {
            "dates": trend_dates,
            "apply_amount": trend_apply,
            "intercept_amount": trend_intercept,
        },
        "dept_ranking": {
            "names": dept_names,
            "values": dept_values,
        },
        "cost_composition": {
            "labels": comp_labels,
            "data": comp_values,
        },
        "radar": {
            "labels": ["连号风险", "敏感消费", "抬头错误", "虚假报销", "超标预警"],
            "data": radar_data,
        },
        "alerts": alerts,
    }


def get_invoice_raw(invoice_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT raw_json FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not row or not row["raw_json"]:
            return None
        return json.loads(row["raw_json"])


def invoice_exists(invoice_id: int) -> bool:
    """仅判断发票是否存在（不做数据范围过滤），用于区分 404 与 403 越权。"""
    try:
        nid = int(invoice_id)
    except Exception:
        return False
    if nid <= 0:
        return False
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM invoices WHERE id = ? LIMIT 1", (nid,)).fetchone()
    return row is not None


def get_invoice_detail(
    invoice_id: int,
    *,
    department: str | None = None,
    include_raw_json: bool = False,
    owner_user_id: int | None = None,
    owner_identity_values: set[str] | list[str] | tuple[str, ...] | None = None,
    data_scope: dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    try:
        normalized_invoice_id = int(invoice_id)
    except Exception:
        return None
    if normalized_invoice_id <= 0:
        return None

    with get_conn() as conn:
        sql = [
            """
            SELECT *
            FROM invoices
            WHERE id = ?
            """
        ]
        params: list[Any] = [normalized_invoice_id]
        append_invoice_scope_sql(
            sql,
            params,
            data_scope=data_scope,
            department=department,
            owner_user_id=owner_user_id,
            owner_identity_values=owner_identity_values,
            table_alias="",
        )

        sql.append("LIMIT 1")
        row = conn.execute("\n".join(sql), tuple(params)).fetchone()
    if row is None:
        return None

    data = dict(row)
    merchant_name, item_name = _extract_merchant_and_item(data.get("raw_json"))
    data["merchant_name"] = merchant_name
    data["item_name"] = item_name
    data["record_state"] = normalize_record_state(data.get("record_state"), fallback=RECORD_STATE_DRAFT)
    data["risk_reason_biz"] = to_business_risk_reason(
        data.get("risk_reason"),
        source=data.get("source"),
        amount=data.get("amount"),
        threshold=data.get("hotel_limit"),
    )
    raw_rule_explain = _safe_text(data.get("rule_explain")) or _safe_text(data.get("risk_reason"))
    data["rule_explain_biz"] = to_business_risk_reason(
        raw_rule_explain,
        source=data.get("source"),
        amount=data.get("amount"),
        threshold=data.get("hotel_limit"),
    )
    if data["record_state"] == RECORD_STATE_DRAFT and not _has_ledger_required_fields(
        data.get("amount"),
        data.get("invoice_date"),
    ):
        data["risk_reason_biz"] = "凭证要素不全（缺：金额/日期），需补录后复核"
        data["rule_explain_biz"] = data["risk_reason_biz"]
    with_cn_status_fields(data)

    if not include_raw_json:
        data.pop("raw_json", None)
    return data


def list_invoice_audit_trail(invoice_id: int, *, limit: int = 20) -> list[Dict[str, Any]]:
    try:
        normalized_invoice_id = int(invoice_id)
    except Exception:
        return []
    if normalized_invoice_id <= 0:
        return []
    try:
        normalized_limit = int(limit)
    except Exception:
        normalized_limit = 20
    if normalized_limit <= 0:
        normalized_limit = 20
    normalized_limit = min(normalized_limit, 200)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                created_at,
                actor_user_id,
                actor_name,
                action,
                target_type,
                target_id,
                client_ip,
                change_reason_code,
                snapshot_before,
                snapshot_after,
                trace_id
            FROM audit_log
            WHERE target_id = ?
              AND target_type IN ('invoice', 'approval')
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(normalized_invoice_id), normalized_limit),
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        before_obj = _safe_json_loads(str(row["snapshot_before"] or "")) or {}
        after_obj = _safe_json_loads(str(row["snapshot_after"] or "")) or {}
        if not isinstance(before_obj, dict):
            before_obj = {"value": before_obj}
        if not isinstance(after_obj, dict):
            after_obj = {"value": after_obj}
        action_raw = _safe_text(row["action"], "-").upper()
        reason_raw = _safe_text(row["change_reason_code"], "-").upper()
        result.append(
            {
                "id": int(row["id"] or 0),
                "created_at": _safe_text(row["created_at"], "-"),
                "actor_user_id": _safe_text(row["actor_user_id"]),
                "actor_name": _safe_text(row["actor_name"], "-"),
                "action": action_raw,
                "action_cn": to_cn_ledger_action(action_raw),
                "target_type": _safe_text(row["target_type"], "-"),
                "target_id": _safe_text(row["target_id"]),
                "client_ip": _safe_text(row["client_ip"], "-"),
                "change_reason_code": reason_raw,
                "change_reason_code_cn": to_cn_reason_code(reason_raw),
                "before": localize_status_snapshot(before_obj),
                "after": localize_status_snapshot(after_obj),
                "trace_id": _safe_text(row["trace_id"]),
            }
        )
    return result


def get_or_create_audit_trace(object_type: str, object_id: str | int) -> tuple[str, int]:
    """
    获取或创建审计链根记录。返回 (trace_id, audit_trace_id)。
    """
    obj_type = str(object_type or "").strip().lower()
    obj_id = str(object_id or "").strip()
    if not obj_type or not obj_id:
        raise ValueError("object_type and object_id are required")
    if obj_type not in ("invoice", "risk_event", "risk_case", "approval"):
        raise ValueError(f"object_type must be one of: invoice, risk_event, risk_case, approval")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, trace_id FROM audit_traces
            WHERE object_type = ? AND object_id = ?
            LIMIT 1
            """,
            (obj_type, obj_id),
        ).fetchone()
        if row:
            return str(row["trace_id"]), int(row["id"])

        trace_id = str(uuid.uuid4())
        cur = conn.execute(
            """
            INSERT INTO audit_traces (object_type, object_id, trace_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (obj_type, obj_id, trace_id, now),
        )
        conn.commit()
        return trace_id, int(cur.lastrowid)


def get_audit_trace_by_object(object_type: str, object_id: str | int) -> Dict[str, Any] | None:
    """根据 object_type + object_id 获取审计链根记录。"""
    obj_type = str(object_type or "").strip().lower()
    obj_id = str(object_id or "").strip()
    if not obj_type or not obj_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, object_type, object_id, trace_id, created_at
            FROM audit_traces WHERE object_type = ? AND object_id = ?
            LIMIT 1
            """,
            (obj_type, obj_id),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "object_type": _safe_text(row["object_type"]),
        "object_id": _safe_text(row["object_id"]),
        "trace_id": _safe_text(row["trace_id"]),
        "created_at": _safe_text(row["created_at"]),
    }


def append_audit_trace_event(
    trace_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    actor_user_id: str = "",
    actor_name: str = "",
) -> int:
    """追加审计链事件，返回事件 id。"""
    tid = str(trace_id or "").strip()
    etype = str(event_type or "").strip().upper()
    if not tid or not etype:
        raise ValueError("trace_id and event_type are required")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload_text = json.dumps(payload or {}, ensure_ascii=False, default=str)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_trace_events
            (trace_id, event_type, event_time, payload_json, actor_user_id, actor_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, etype, now, payload_text, str(actor_user_id or ""), str(actor_name or ""), now),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_audit_trace_events(trace_id: str, *, limit: int = 100) -> list[Dict[str, Any]]:
    """按时间升序列出审计链事件。"""
    tid = str(trace_id or "").strip()
    if not tid:
        return []
    limit = max(1, min(int(limit or 100), 500))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, trace_id, event_type, event_time, payload_json, actor_user_id, actor_name, created_at
            FROM audit_trace_events WHERE trace_id = ?
            ORDER BY event_time ASC, id ASC LIMIT ?
            """,
            (tid, limit),
        ).fetchall()
    result: list[Dict[str, Any]] = []
    for row in rows:
        payload_raw = row["payload_json"] or "{}"
        try:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else (payload_raw or {})
        except Exception:
            payload = {}
        result.append({
            "id": int(row["id"]),
            "trace_id": _safe_text(row["trace_id"]),
            "event_type": _safe_text(row["event_type"]),
            "event_time": _safe_text(row["event_time"]),
            "payload": payload if isinstance(payload, dict) else {},
            "actor_user_id": _safe_text(row["actor_user_id"]),
            "actor_name": _safe_text(row["actor_name"]),
            "created_at": _safe_text(row["created_at"]),
        })
    return result


def link_audit_evidence(
    trace_id: str,
    file_path: str,
    *,
    object_type: str = "invoice",
    object_id: str = "",
    evidence_type: str = "file",
) -> int:
    """关联审计证据，返回证据 id。"""
    tid = str(trace_id or "").strip()
    path = str(file_path or "").strip()
    if not tid or not path:
        raise ValueError("trace_id and file_path are required")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    obj_type = str(object_type or "invoice").strip().lower()
    obj_id = str(object_id or "").strip()
    etype = str(evidence_type or "file").strip().lower()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_evidence (trace_id, object_type, object_id, file_path, evidence_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tid, obj_type, obj_id, path, etype, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_audit_evidence(trace_id: str, *, limit: int = 50) -> list[Dict[str, Any]]:
    """列出审计链关联的证据。"""
    tid = str(trace_id or "").strip()
    if not tid:
        return []
    limit = max(1, min(int(limit or 50), 200))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, trace_id, object_type, object_id, file_path, evidence_type, created_at
            FROM audit_evidence WHERE trace_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (tid, limit),
        ).fetchall()
    result: list[Dict[str, Any]] = []
    for row in rows:
        result.append({
            "id": int(row["id"]),
            "trace_id": _safe_text(row["trace_id"]),
            "object_type": _safe_text(row["object_type"]),
            "object_id": _safe_text(row["object_id"]),
            "file_path": _safe_text(row["file_path"]),
            "evidence_type": _safe_text(row["evidence_type"]),
            "created_at": _safe_text(row["created_at"]),
        })
    return result


def get_invoice_for_verify(invoice_id: int) -> Dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                reference_no,
                amount,
                invoice_date,
                applicant,
                department,
                raw_json,
                verify_status,
                verify_message,
                verify_checked_at,
                verify_count,
                verify_provider,
                verify_request_id,
                verify_latency_ms,
                verify_status_code,
                verify_raw_payload
            FROM invoices
            WHERE id = ?
            """,
            (invoice_id,),
        ).fetchone()
    return dict(row) if row else None


def update_invoice_verification(
    invoice_id: int,
    *,
    verify_status: str,
    verify_message: str,
    verify_checked_at: str,
    verify_provider: str,
    verify_request_id: str,
    verify_latency_ms: int,
    verify_status_code: int,
    verify_raw_payload: dict[str, Any] | str | None,
) -> Dict[str, Any] | None:
    status = str(verify_status or "PENDING").strip().upper() or "PENDING"
    if status not in {"PENDING", "PASSED", "FAILED"}:
        status = "PENDING"

    message = str(verify_message or "").strip()
    checked_at = str(verify_checked_at or "").strip()
    provider = str(verify_provider or "").strip()
    request_id = str(verify_request_id or "").strip()

    try:
        latency_ms = int(verify_latency_ms)
    except Exception:
        latency_ms = 0
    try:
        status_code = int(verify_status_code)
    except Exception:
        status_code = 0

    if isinstance(verify_raw_payload, str):
        raw_payload_text = verify_raw_payload
    else:
        try:
            raw_payload_text = json.dumps(verify_raw_payload or {}, ensure_ascii=False)
        except Exception:
            raw_payload_text = "{}"

    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE invoices
            SET
                verify_status = ?,
                verify_message = ?,
                verify_checked_at = ?,
                verify_count = COALESCE(verify_count, 0) + 1,
                verify_provider = ?,
                verify_request_id = ?,
                verify_latency_ms = ?,
                verify_status_code = ?,
                verify_raw_payload = ?
            WHERE id = ?
            """,
            (
                status,
                message,
                checked_at,
                provider,
                request_id,
                latency_ms,
                status_code,
                raw_payload_text,
                int(invoice_id),
            ),
        )
        if cur.rowcount <= 0:
            return None
        row = conn.execute(
            """
            SELECT
                id,
                verify_status,
                verify_message,
                verify_checked_at,
                verify_count,
                verify_provider,
                verify_request_id,
                verify_latency_ms,
                verify_status_code,
                verify_raw_payload
            FROM invoices
            WHERE id = ?
            """,
            (int(invoice_id),),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None



