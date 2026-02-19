(() => {
  function normalize(value) {
    return String(value ?? "").trim().toUpperCase();
  }

  const APPROVAL_STATUS_MAP = {
    PENDING: "待审核",
    APPROVED: "已通过",
    REJECTED: "已驳回",
    ESCALATED: "已升级",
    ON_HOLD: "已挂起",
    RETURNED: "已打回",
    DONE: "已完成",
  };

  const LEDGER_STATE_MAP = {
    DRAFT: "待补录",
    LEDGER: "已入账",
    ARCHIVED: "已归档",
  };

  const VERIFY_STATUS_MAP = {
    PENDING: "待验真",
    PASS: "验真通过",
    PASSED: "验真通过",
    FAIL: "验真不通过",
    FAILED: "验真不通过",
    UNKNOWN: "验真未知",
  };

  const APPROVAL_STAGE_MAP = {
    L1: "一级审批",
    L2: "二级复核",
    DONE: "已完成",
  };

  const RISK_LEVEL_MAP = {
    HIGH: "高风险",
    MEDIUM: "中风险",
    LOW: "低风险",
    UNKNOWN: "未知",
  };

  const RISK_CASE_STATUS_MAP = {
    OPEN: "待分派",
    ASSIGNED: "已分派",
    PROCESSING: "处理中",
    CLOSED: "已结案",
  };

  const RISK_CASE_EVENT_MAP = {
    CASE_CREATED: "案件创建",
    CASE_ASSIGNED: "案件分派",
    CASE_CLOSED: "案件结案",
    RULE_HIT: "规则命中",
    AI_EXPLAIN: "智能解释完成",
    ASSIGN: "案件分派",
    CLOSE: "案件结案",
    SCORE_ADJUST: "评分调整",
    CREATE: "案件创建",
  };

  const ACTION_MAP = {
    SUBMIT_REVIEW: "提交复核",
    RETURN_TO_DRAFT: "打回补录",
    POST_LEDGER: "入账",
    RERUN_AI_RISK: "重跑识别/重算风险",
    SUPPLEMENT: "补录",
    BATCH_RETURN_TO_DRAFT: "批量打回补录",
    BATCH_SUPPLEMENT: "批量补录",
    LEDGER_STRUCTURED_EDIT: "更新凭证要素",
    STRUCTURED_EDIT: "要素校正",
    EVIDENCE_CENTER: "证据中心",
    UI_ACTION_BLOCKED: "界面动作拦截",
    UNKNOWN_ACTION: "未知动作",
  };

  function toCnStatus(value, map, fallback = "—") {
    const raw = String(value ?? "").trim();
    if (!raw) return fallback;
    return map[normalize(raw)] || raw;
  }

  const api = {
    maps: {
      APPROVAL_STATUS_MAP,
      LEDGER_STATE_MAP,
      VERIFY_STATUS_MAP,
      APPROVAL_STAGE_MAP,
      ACTION_MAP,
      RISK_LEVEL_MAP,
      RISK_CASE_STATUS_MAP,
      RISK_CASE_EVENT_MAP,
    },
    normalize,
    toCnStatus,
    toCnApprovalStatus(value, fallback = "—") {
      return toCnStatus(value, APPROVAL_STATUS_MAP, fallback);
    },
    toCnLedgerState(value, fallback = "—") {
      return toCnStatus(value, LEDGER_STATE_MAP, fallback);
    },
    toCnVerifyStatus(value, fallback = "—") {
      return toCnStatus(value, VERIFY_STATUS_MAP, fallback);
    },
    toCnApprovalStage(value, fallback = "—") {
      return toCnStatus(value, APPROVAL_STAGE_MAP, fallback);
    },
    toCnAction(value, fallback = "—") {
      return toCnStatus(value, ACTION_MAP, fallback);
    },
    toCnRiskLevel(value, fallback = "未知") {
      return toCnStatus(value, RISK_LEVEL_MAP, fallback);
    },
    toCnRiskCaseStatus(value, fallback = "处理中") {
      return toCnStatus(value, RISK_CASE_STATUS_MAP, fallback);
    },
    toCnRiskCaseEvent(value, fallback = "已更新") {
      return toCnStatus(value, RISK_CASE_EVENT_MAP, fallback);
    },
  };

  window.DeepAuditStatusI18N = api;
})();
