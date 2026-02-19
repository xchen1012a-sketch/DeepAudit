PAYMENT_IMPORTED = "PAYMENT_IMPORTED"
INVOICE_VERIFIED = "INVOICE_VERIFIED"
RISK_UPDATED = "RISK_UPDATED"
BANK_TXN_SAVED = "BANK_TXN_SAVED"
PAYMENT_MATCHED = "PAYMENT_MATCHED"
PAYMENT_UNMATCHED = "PAYMENT_UNMATCHED"
RISK_STAGE = "RISK_STAGE"

STAGE_INGEST = "INGEST"
STAGE_RULE_HIT = "RULE_HIT"
STAGE_AI_EXPLAIN = "AI_EXPLAIN"
STAGE_RISK_EVENT_CREATED = "RISK_EVENT_CREATED"
STAGE_CASE_CREATED = "CASE_CREATED"
STAGE_CASE_ASSIGNED = "CASE_ASSIGNED"
STAGE_CASE_CLOSED = "CASE_CLOSED"

RISK_STAGE_SEQUENCE = (
    STAGE_INGEST,
    STAGE_RULE_HIT,
    STAGE_AI_EXPLAIN,
    STAGE_RISK_EVENT_CREATED,
    STAGE_CASE_CREATED,
    STAGE_CASE_ASSIGNED,
    STAGE_CASE_CLOSED,
)

# Unified stage labels used by dashboard event stream payloads.
RISK_STAGE_LABELS: dict[str, str] = {
    STAGE_INGEST: "数据已入湖",
    STAGE_RULE_HIT: "规则已命中",
    STAGE_AI_EXPLAIN: "AI 解释完成",
    STAGE_RISK_EVENT_CREATED: "风险事件已生成",
    STAGE_CASE_CREATED: "风险案件已创建",
    STAGE_CASE_ASSIGNED: "案件已分派",
    STAGE_CASE_CLOSED: "案件已结案",
}

RISK_STAGE_CATEGORIES: dict[str, str] = {
    STAGE_INGEST: "数据入湖",
    STAGE_RULE_HIT: "规则命中",
    STAGE_AI_EXPLAIN: "AI解释",
    STAGE_RISK_EVENT_CREATED: "风险事件",
    STAGE_CASE_CREATED: "风险案件",
    STAGE_CASE_ASSIGNED: "案件分派",
    STAGE_CASE_CLOSED: "案件结案",
}

EVENT_TYPE_LABELS: dict[str, str] = {
    INVOICE_VERIFIED: "发票验真完成",
}

EVENT_TYPE_CATEGORIES: dict[str, str] = {
    INVOICE_VERIFIED: "发票验真",
}


def risk_stage_message(stage: str) -> str:
    normalized = str(stage or "").strip().upper()
    if not normalized:
        return "风险流水线事件"
    return RISK_STAGE_LABELS.get(normalized, normalized)


def risk_stage_category(stage: str) -> str:
    normalized = str(stage or "").strip().upper()
    if not normalized:
        return "风险流水线"
    return RISK_STAGE_CATEGORIES.get(normalized, "风险流水线")


def event_type_message(event_type: str) -> str:
    normalized = str(event_type or "").strip().upper()
    if not normalized:
        return "流水线事件"
    return EVENT_TYPE_LABELS.get(normalized, normalized)


def event_type_category(event_type: str) -> str:
    normalized = str(event_type or "").strip().upper()
    if not normalized:
        return "流水线"
    return EVENT_TYPE_CATEGORIES.get(normalized, "流水线")
