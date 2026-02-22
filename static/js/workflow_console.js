(() => {
  const root = document.getElementById("workflowConsole");
  if (!root) return;

  const STEPS = ["A", "B", "C"];
  const NEXT_MAP_KEYS = ["approve", "return", "assign", "false_positive", "close"];
  const NEXT_MAP_SUFFIX = {
    approve: "Approve",
    return: "Return",
    assign: "Assign",
    false_positive: "FalsePositive",
    close: "Close",
  };
  const NEXT_TARGET_OPTIONS = new Set(["A", "B", "C", "END"]);
  const VALID_REQUIRED_ROLES = new Set(["AI_SENTINEL", "MANAGER", "CFO"]);

  const DEFAULT_REASON_CODES = [
    "POLICY_MATCH",
    "POLICY_EXCEPTION",
    "NEED_MORE_INFO",
    "DUPLICATE_SUSPECT",
    "MANUAL_OVERRIDE",
  ];
  const DEFAULT_CONFIG = {
    chain: ["START", "A", "B", "C", "END"],
    nodes: {
      A: {
        required_role: "AI_SENTINEL",
        conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 0 },
        next_map: { approve: "B", return: "END", assign: "B", false_positive: "END", close: "END" },
      },
      B: {
        required_role: "MANAGER",
        conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 0 },
        next_map: { approve: "C", return: "A", assign: "B", false_positive: "END", close: "END" },
      },
      C: {
        required_role: "CFO",
        conditions: { amount_gte: 5000, risk_levels: ["HIGH"], rule_hit_count_gte: 2 },
        next_map: { approve: "END", return: "B", assign: "C", false_positive: "END", close: "END" },
      },
    },
  };

  // 预设模板配置
  const PRESET_TEMPLATES = {
    standard: {
      chain: ["START", "A", "B", "C", "END"],
      nodes: {
        A: {
          required_role: "AI_SENTINEL",
          conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 0 },
          next_map: { approve: "B", return: "END", assign: "B", false_positive: "END", close: "END" },
        },
        B: {
          required_role: "MANAGER",
          conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 0 },
          next_map: { approve: "C", return: "A", assign: "B", false_positive: "END", close: "END" },
        },
        C: {
          required_role: "CFO",
          conditions: { amount_gte: 5000, risk_levels: ["HIGH"], rule_hit_count_gte: 2 },
          next_map: { approve: "END", return: "B", assign: "C", false_positive: "END", close: "END" },
        },
      },
    },
    strict: {
      chain: ["START", "A", "B", "C", "END"],
      nodes: {
        A: {
          required_role: "AI_SENTINEL",
          conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 1 },
          next_map: { approve: "B", return: "END", assign: "B", false_positive: "END", close: "END" },
        },
        B: {
          required_role: "MANAGER",
          conditions: { amount_gte: 1000, risk_levels: ["MEDIUM", "HIGH"], rule_hit_count_gte: 1 },
          next_map: { approve: "C", return: "A", assign: "B", false_positive: "END", close: "END" },
        },
        C: {
          required_role: "CFO",
          conditions: { amount_gte: 10000, risk_levels: ["HIGH"], rule_hit_count_gte: 3 },
          next_map: { approve: "END", return: "B", assign: "C", false_positive: "END", close: "END" },
        },
      },
    },
    loose: {
      chain: ["START", "A", "B", "C", "END"],
      nodes: {
        A: {
          required_role: "AI_SENTINEL",
          conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 0 },
          next_map: { approve: "B", return: "END", assign: "B", false_positive: "END", close: "END" },
        },
        B: {
          required_role: "MANAGER",
          conditions: { amount_gte: 0, risk_levels: ["LOW", "MEDIUM", "HIGH"], rule_hit_count_gte: 0 },
          next_map: { approve: "C", return: "A", assign: "B", false_positive: "END", close: "END" },
        },
        C: {
          required_role: "CFO",
          conditions: { amount_gte: 20000, risk_levels: ["HIGH"], rule_hit_count_gte: 1 },
          next_map: { approve: "END", return: "B", assign: "C", false_positive: "END", close: "END" },
        },
      },
    },
  };
  const PRESET_LABELS = {
    standard: "标准配置",
    strict: "严格审批",
    loose: "宽松审批",
    custom: "自定义配置",
  };
  const ROLE_LABELS = {
    ADMIN: "管理员",
    AI_SENTINEL: "AI哨兵",
    MANAGER: "财务主管/经理",
    CFO: "财务总监(CFO)",
  };
  const STEP_LABELS = {
    A: "AI哨兵",
    B: "财务主管/经理",
    C: "财务总监(CFO)",
    END: "结束流程",
  };
  const RISK_LABELS = {
    LOW: "低风险",
    MEDIUM: "中风险",
    HIGH: "高风险",
  };
  const ACTION_LABELS = {
    approve: "通过",
    return: "退回",
    assign: "转派",
    false_positive: "误报",
    close: "结案",
  };
  const STATUS_LABELS = {
    PUBLISHED: "已发布",
    DRAFT: "草稿",
    ROLLBACK: "回滚",
    ROLLED_BACK: "已回滚",
  };
  const REASON_LABELS = {
    POLICY_MATCH: "符合策略",
    POLICY_EXCEPTION: "策略例外",
    NEED_MORE_INFO: "需补充信息",
    DUPLICATE_SUSPECT: "疑似重复",
    MANUAL_OVERRIDE: "人工覆盖",
  };
  const SCOPE_VALUE_ALIASES = {
    ALL: "ALL",
    NEW_ONLY: "NEW_ONLY",
    INFLIGHT_AND_NEW: "INFLIGHT_AND_NEW",
    INFLIGHT_NEW: "INFLIGHT_AND_NEW",
    IN_FLIGHT_AND_NEW: "INFLIGHT_AND_NEW",
    "INFLIGHT+NEW": "INFLIGHT_AND_NEW",
  };
  const SCOPE_LABELS = {
    ALL: "全部",
    NEW_ONLY: "仅新单据",
    INFLIGHT_AND_NEW: "在途+新单据",
  };
  const QUEUE_BUTTON_LABELS = {
    A: "查看待办队列（节点A：AI哨兵）",
    B: "查看待办队列（节点B：财务主管/经理）",
    C: "查看待办队列（节点C：财务总监(CFO)）",
  };

  const refs = {
    feedback: document.getElementById("wfFeedback"),
    currentVersion: document.getElementById("wfCurrentVersion"),
    currentPublisher: document.getElementById("wfCurrentPublisher"),
    currentPublishedAt: document.getElementById("wfCurrentPublishedAt"),
    currentScope: document.getElementById("wfCurrentScope"),
    scopeInput: document.getElementById("wfScopeInput"),
    scopeError: document.getElementById("wfScopeError"),
    saveDraftBtn: document.getElementById("wfSaveDraftBtn"),
    publishBtn: document.getElementById("wfPublishBtn"),
    historyBtn: document.getElementById("wfHistoryBtn"),
    rollbackBtn: document.getElementById("wfRollbackBtn"),
    previewRole: document.getElementById("wfPreviewRole"),
    previewList: document.getElementById("wfRolePreviewList"),
    previewLinks: document.getElementById("wfRoleJumpLinks"),
    publishReason: document.getElementById("wfPublishReason"),
    publishReasonError: document.getElementById("wfPublishReasonError"),
    publishNote: document.getElementById("wfPublishNote"),
    publishConfirmBtn: document.getElementById("wfPublishConfirmBtn"),
    historyBody: document.getElementById("wfHistoryBody"),
    rollbackTargetVersion: document.getElementById("wfRollbackTargetVersion"),
    rollbackVersionError: document.getElementById("wfRollbackVersionError"),
    rollbackReason: document.getElementById("wfRollbackReason"),
    rollbackReasonError: document.getElementById("wfRollbackReasonError"),
    rollbackNote: document.getElementById("wfRollbackNote"),
    rollbackConfirmBtn: document.getElementById("wfRollbackConfirmBtn"),
    presetStandard: document.getElementById("wfPresetStandard"),
    presetStrict: document.getElementById("wfPresetStrict"),
    presetLoose: document.getElementById("wfPresetLoose"),
    presetReset: document.getElementById("wfPresetReset"),
    presetCurrentBadge: document.getElementById("wfPresetCurrentBadge"),
    presetCurrentLabel: document.getElementById("wfPresetCurrentLabel"),
  };

  const hasMissingRefs = Object.values(refs).some((node) => !node);
  if (hasMissingRefs) return;

  let currentRecord = null;
  let reasonCodes = DEFAULT_REASON_CODES.slice();

  function text(value, fallback = "") {
    const normalized = String(value ?? "").trim();
    return normalized || fallback;
  }

  function normalize(value) {
    return text(value).toUpperCase();
  }

  function escapeHtml(value) {
    return text(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function asNumber(value, fallback = 0) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function formatAmount(value) {
    const numeric = asNumber(value, 0);
    if (Number.isInteger(numeric)) return String(numeric);
    return numeric.toFixed(2).replace(/\.?0+$/, "");
  }

  function roleLabel(role) {
    const key = normalize(role);
    return ROLE_LABELS[key] || "未知角色";
  }

  function stepLabel(step) {
    const key = normalize(step);
    return STEP_LABELS[key] || "未知节点";
  }

  function riskLabel(level) {
    const key = normalize(level);
    return RISK_LABELS[key] || "未知风险";
  }

  function statusLabel(status) {
    const key = normalize(status);
    return STATUS_LABELS[key] || "未知状态";
  }

  function reasonLabel(reasonCode) {
    const key = normalize(reasonCode);
    return REASON_LABELS[key] || "其他原因";
  }

  function normalizeScope(scope) {
    const raw = normalize(scope);
    return SCOPE_VALUE_ALIASES[raw] || "";
  }

  function scopeLabel(scope) {
    const key = normalizeScope(scope);
    return SCOPE_LABELS[key] || "未配置";
  }

  function readScopeFromForm() {
    return normalizeScope(getSelectValue(refs.scopeInput));
  }

  function reasonText(reason) {
    const raw = text(reason, "-");
    if (raw === "-") return raw;
    const chunks = raw.split(":");
    const code = normalize(chunks.shift() || "");
    const note = text(chunks.join(":"), "");
    const label = reasonLabel(code);
    return note ? `${label}：${note}` : label;
  }

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && text(meta.content)) return text(meta.content);
    const hidden = document.querySelector('input[name="csrf_token"]');
    return hidden ? text(hidden.value) : "";
  }

  async function apiJson(url, options = {}) {
    const headers = Object.assign({ Accept: "application/json" }, options.headers || {});
    if (options.method && options.method.toUpperCase() !== "GET") {
      headers["Content-Type"] = "application/json";
      const token = csrfToken();
      if (token) headers["X-CSRF-Token"] = token;
    }
    const response = await fetch(url, Object.assign({}, options, { headers }));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload || payload.ok !== true) {
      throw new Error(text(payload.msg) || text(payload.message) || `HTTP ${response.status}`);
    }
    return payload;
  }

  const ALERT_ICONS = {
    success: "ri-checkbox-circle-line",
    info: "ri-information-line",
    warning: "ri-error-warning-line",
    danger: "ri-close-circle-line",
  };

  function showFeedback(type, message) {
    const tone = type || "info";
    const msg = text(message, "操作完成");
    const icon = ALERT_ICONS[tone] || ALERT_ICONS.info;
    refs.feedback.className = `alert alert-${tone} py-2 px-3 mt-3 mb-0`;
    refs.feedback.innerHTML =
      `<span class="alert-icon"><i class="${icon}"></i></span>` +
      `<span class="alert-body">${msg}</span>`;
    refs.feedback.classList.remove("d-none");
    clearTimeout(showFeedback._timer);
    showFeedback._timer = setTimeout(() => refs.feedback.classList.add("d-none"), 3500);
  }

  function setNodeText(node, value, fallback = "-") {
    if (!node) return;
    node.textContent = text(value, fallback);
  }

  function getSelectValue(select) {
    if (!select) return "";
    if (select.tomselect && typeof select.tomselect.getValue === "function") {
      return text(select.tomselect.getValue());
    }
    return text(select.value);
  }

  function setSelectValue(select, value = "") {
    if (!select) return;
    const next = text(value);
    if (select.tomselect && typeof select.tomselect.setValue === "function") {
      select.tomselect.setValue(next, true);
      return;
    }
    select.value = next;
  }

  function getMultiSelectValues(select) {
    if (!select) return [];
    if (select.tomselect && typeof select.tomselect.getValue === "function") {
      const value = select.tomselect.getValue();
      if (Array.isArray(value)) return value.map((item) => normalize(item)).filter(Boolean);
      return text(value)
        .split(",")
        .map((item) => normalize(item))
        .filter(Boolean);
    }
    return Array.from(select.selectedOptions || [])
      .map((option) => normalize(option.value))
      .filter(Boolean);
  }

  function setMultiSelectValues(select, values) {
    if (!select) return;
    const list = Array.isArray(values) ? values.map((item) => normalize(item)).filter(Boolean) : [];
    if (select.tomselect && typeof select.tomselect.setValue === "function") {
      select.tomselect.setValue(list, true);
      return;
    }
    Array.from(select.options || []).forEach((option) => {
      option.selected = list.includes(normalize(option.value));
    });
  }

  function setFieldInvalid(field, errorNode, invalid, message) {
    if (!field || !errorNode) return;
    const isInvalid = !!invalid;
    field.classList.toggle("is-invalid", isInvalid);
    if (field.tomselect && field.tomselect.control) {
      field.tomselect.control.classList.toggle("is-invalid", isInvalid);
    }
    if (message) errorNode.textContent = message;
    errorNode.classList.toggle("d-none", !isInvalid);
  }

  function setSelectInvalid(select, errorNode, invalid, message) {
    setFieldInvalid(select, errorNode, invalid, message);
  }

  function scrollToField(field) {
    if (!field) return;
    const target = field.tomselect && field.tomselect.control ? field.tomselect.control : field;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    if (typeof target.focus === "function") {
      setTimeout(() => target.focus({ preventScroll: true }), 80);
    }
  }

  function openModal(id) {
    if (!window.jQuery) return;
    window.jQuery(id).modal("show");
  }

  function closeModal(id) {
    if (!window.jQuery) return;
    window.jQuery(id).modal("hide");
  }

  function resetSelectOptions(select, options, placeholder = "请选择") {
    if (!select) return;
    const safeOptions = Array.isArray(options) ? options : [];
    if (select.tomselect) {
      const ts = select.tomselect;
      ts.clear(true);
      ts.clearOptions();
      ts.addOption({ value: "", text: placeholder });
      safeOptions.forEach((item) => {
        ts.addOption({ value: text(item.value), text: text(item.label) });
      });
      ts.refreshOptions(false);
      ts.setValue("", true);
      return;
    }
    const html = [`<option value="">${escapeHtml(placeholder)}</option>`]
      .concat(
        safeOptions.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`),
      )
      .join("");
    select.innerHTML = html;
  }

  function nodeEl(step, suffix) {
    return document.getElementById(`wfNode${step}${suffix}`);
  }

  function nodeErrorEl(step, suffix) {
    return document.getElementById(`wfNode${step}${suffix}Error`);
  }

  function clearNodeValidation(step) {
    [
      "RequiredRole",
      "AmountGte",
      "RiskLevels",
      "RuleHitCount",
      "NextApprove",
      "NextReturn",
      "NextAssign",
      "NextFalsePositive",
      "NextClose",
    ].forEach((suffix) => {
      setFieldInvalid(nodeEl(step, suffix), nodeErrorEl(step, suffix), false, "");
    });
  }

  function clearConfigValidation() {
    setFieldInvalid(refs.scopeInput, refs.scopeError, false, "");
    STEPS.forEach((step) => clearNodeValidation(step));
  }

  function readNodeConfig(step) {
    const requiredRole = normalize(getSelectValue(nodeEl(step, "RequiredRole")));
    const amountRaw = Number(nodeEl(step, "AmountGte")?.value);
    const hitCountRaw = Number(nodeEl(step, "RuleHitCount")?.value);
    const nextMap = {};
    NEXT_MAP_KEYS.forEach((key) => {
      const suffix = NEXT_MAP_SUFFIX[key];
      nextMap[key] = normalize(getSelectValue(nodeEl(step, `Next${suffix}`)));
    });
    return {
      required_role: requiredRole,
      conditions: {
        amount_gte: Number.isFinite(amountRaw) && amountRaw >= 0 ? amountRaw : 0,
        risk_levels: getMultiSelectValues(nodeEl(step, "RiskLevels")),
        rule_hit_count_gte: Number.isFinite(hitCountRaw) && hitCountRaw >= 0 ? Math.trunc(hitCountRaw) : 0,
      },
      next_map: nextMap,
    };
  }

  function readConfigFromForm() {
    return {
      chain: ["START", "A", "B", "C", "END"],
      nodes: {
        A: readNodeConfig("A"),
        B: readNodeConfig("B"),
        C: readNodeConfig("C"),
      },
    };
  }

  function normalizeChain(chain) {
    const source = Array.isArray(chain) && chain.length ? chain : DEFAULT_CONFIG.chain;
    return source.map((item) => normalize(item)).filter(Boolean);
  }

  function normalizeRiskLevels(levels) {
    return (Array.isArray(levels) ? levels : [])
      .map((item) => normalize(item))
      .filter(Boolean)
      .sort();
  }

  function normalizeNodeForCompare(node) {
    const source = node && typeof node === "object" ? node : {};
    const conditions = source.conditions && typeof source.conditions === "object" ? source.conditions : {};
    const nextMap = source.next_map && typeof source.next_map === "object" ? source.next_map : {};
    return {
      required_role: normalize(source.required_role),
      conditions: {
        amount_gte: asNumber(conditions.amount_gte, 0),
        risk_levels: normalizeRiskLevels(conditions.risk_levels),
        rule_hit_count_gte: Math.max(0, Math.trunc(asNumber(conditions.rule_hit_count_gte, 0))),
      },
      next_map: NEXT_MAP_KEYS.reduce((acc, key) => {
        acc[key] = normalize(nextMap[key]);
        return acc;
      }, {}),
    };
  }

  function createConfigSignature(config) {
    const source = config && typeof config === "object" ? config : {};
    const nodes = source.nodes && typeof source.nodes === "object" ? source.nodes : {};
    return JSON.stringify({
      chain: normalizeChain(source.chain),
      nodes: STEPS.reduce((acc, step) => {
        acc[step] = normalizeNodeForCompare(nodes[step]);
        return acc;
      }, {}),
    });
  }

  const PRESET_SIGNATURES = Object.entries(PRESET_TEMPLATES).reduce((acc, [name, template]) => {
    acc[name] = createConfigSignature(template);
    return acc;
  }, {});

  function detectPresetName(config) {
    const signature = createConfigSignature(config);
    return Object.keys(PRESET_SIGNATURES).find((name) => PRESET_SIGNATURES[name] === signature) || "custom";
  }

  function setPresetButtonActiveState(presetName) {
    const buttonMap = {
      standard: refs.presetStandard,
      strict: refs.presetStrict,
      loose: refs.presetLoose,
    };
    Object.entries(buttonMap).forEach(([name, button]) => {
      if (!button) return;
      const isActive = name === presetName;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function syncCurrentPresetBadge(config) {
    const presetName = detectPresetName(config);
    const label = PRESET_LABELS[presetName] || PRESET_LABELS.custom;
    setNodeText(refs.presetCurrentLabel, label, PRESET_LABELS.custom);
    if (refs.presetCurrentBadge) refs.presetCurrentBadge.dataset.preset = presetName;
    setPresetButtonActiveState(presetName);
  }

  function validateConfig(config) {
    clearConfigValidation();
    let valid = true;
    let firstInvalidField = null;
    const markInvalid = (field, errorNode, message) => {
      setFieldInvalid(field, errorNode, true, message);
      valid = false;
      if (!firstInvalidField) firstInvalidField = field;
    };

    const scopeValue = readScopeFromForm();
    if (!scopeValue) {
      markInvalid(refs.scopeInput, refs.scopeError, "请选择发布范围");
    }

    const nodes = (config && config.nodes) || {};
    STEPS.forEach((step) => {
      const node = nodes[step] || {};
      const conditions = (node && node.conditions) || {};
      const nextMap = (node && node.next_map) || {};

      const requiredRole = normalize(node.required_role);
      const requiredRoleValid = VALID_REQUIRED_ROLES.has(requiredRole);
      if (!requiredRoleValid) {
        markInvalid(nodeEl(step, "RequiredRole"), nodeErrorEl(step, "RequiredRole"), "请选择处理角色");
      }

      const amountRawText = text(nodeEl(step, "AmountGte")?.value);
      const amountNumeric = Number(amountRawText);
      const amountValid = amountRawText !== "" && Number.isFinite(amountNumeric) && amountNumeric >= 0;
      if (!amountValid) {
        markInvalid(nodeEl(step, "AmountGte"), nodeErrorEl(step, "AmountGte"), "请输入大于等于 0 的金额");
      }

      const riskLevels = Array.isArray(conditions.risk_levels)
        ? conditions.risk_levels.map((item) => normalize(item)).filter(Boolean)
        : [];
      const riskValid = riskLevels.length > 0;
      if (!riskValid) {
        markInvalid(nodeEl(step, "RiskLevels"), nodeErrorEl(step, "RiskLevels"), "请至少选择一个风险等级");
      }

      const hitCountRawText = text(nodeEl(step, "RuleHitCount")?.value);
      const hitCountNumeric = Number(hitCountRawText);
      const hitCountValid =
        hitCountRawText !== "" &&
        Number.isFinite(hitCountNumeric) &&
        hitCountNumeric >= 0 &&
        Number.isInteger(hitCountNumeric);
      if (!hitCountValid) {
        markInvalid(nodeEl(step, "RuleHitCount"), nodeErrorEl(step, "RuleHitCount"), "请输入大于等于 0 的整数");
      }

      NEXT_MAP_KEYS.forEach((key) => {
        const suffix = NEXT_MAP_SUFFIX[key];
        const target = normalize(nextMap[key]);
        let message = `请选择“${ACTION_LABELS[key]}”的流转目标`;
        let targetValid = false;
        if (!target) {
          targetValid = false;
        } else if (!NEXT_TARGET_OPTIONS.has(target)) {
          targetValid = false;
          message = `“${ACTION_LABELS[key]}”的流转目标必须是节点A、节点B、节点C或结束流程`;
        } else {
          targetValid = true;
        }
        if (!targetValid) {
          markInvalid(nodeEl(step, `Next${suffix}`), nodeErrorEl(step, `Next${suffix}`), message);
        }
      });
    });

    if (firstInvalidField) {
      scrollToField(firstInvalidField);
    }

    return {
      ok: valid,
      message: valid
        ? ""
        : !scopeValue
          ? "请选择发布范围后再继续。"
          : "请根据下方提示补全必填项后再继续。",
    };
  }

  function renderNodeConfig(step, node) {
    const fallback = (DEFAULT_CONFIG.nodes || {})[step] || {};
    const source = typeof node === "object" && node ? node : fallback;
    const conditions = typeof source.conditions === "object" && source.conditions ? source.conditions : {};
    const nextMap = typeof source.next_map === "object" && source.next_map ? source.next_map : {};

    const rawRole = normalize(source.required_role || fallback.required_role || "");
    setSelectValue(nodeEl(step, "RequiredRole"), VALID_REQUIRED_ROLES.has(rawRole) ? rawRole : "");
    nodeEl(step, "AmountGte").value = Number(conditions.amount_gte ?? fallback.conditions?.amount_gte ?? 0);
    nodeEl(step, "RuleHitCount").value = Number(conditions.rule_hit_count_gte ?? fallback.conditions?.rule_hit_count_gte ?? 0);
    setMultiSelectValues(nodeEl(step, "RiskLevels"), conditions.risk_levels || fallback.conditions?.risk_levels || []);

    NEXT_MAP_KEYS.forEach((key) => {
      const suffix = NEXT_MAP_SUFFIX[key];
      const rawTarget = normalize(nextMap[key]);
      const fallbackTarget = normalize(fallback.next_map?.[key] || "END");
      const value = rawTarget ? rawTarget : fallbackTarget;
      setSelectValue(nodeEl(step, `Next${suffix}`), NEXT_TARGET_OPTIONS.has(value) ? value : "");
    });

    clearNodeValidation(step);
  }

  function renderConfig(config) {
    const source = config && typeof config === "object" ? config : {};
    const nodes = source.nodes || {};
    STEPS.forEach((step) => renderNodeConfig(step, nodes[step]));
    clearConfigValidation();
    renderRolePreview();
    syncCurrentPresetBadge(source);
  }

  function applyPresetTemplate(templateName) {
    const template = PRESET_TEMPLATES[templateName];
    if (!template) {
      showFeedback("warning", "预设模板不存在");
      return;
    }
    renderConfig(template);
    showFeedback("success", `已应用${templateName === "standard" ? "标准" : templateName === "strict" ? "严格" : "宽松"}配置模板`);
  }

  function resetToDefault() {
    renderConfig(DEFAULT_CONFIG);
    showFeedback("info", "已重置为默认配置");
  }

  function renderCurrentMeta(record) {
    currentRecord = record && typeof record === "object" ? record : null;
    setNodeText(refs.currentVersion, currentRecord ? `v${text(currentRecord.version, "0")}` : "-", "-");
    setNodeText(refs.currentPublisher, currentRecord ? currentRecord.by : "-", "-");
    setNodeText(refs.currentPublishedAt, currentRecord ? currentRecord.at : "-", "-");
    setNodeText(refs.currentScope, scopeLabel(currentRecord ? currentRecord.scope : ""), "-");
    setSelectValue(refs.scopeInput, normalizeScope(currentRecord ? currentRecord.scope : ""));
  }

  function renderRolePreview() {
    const role = normalize(getSelectValue(refs.previewRole)) || "ADMIN";
    const config = readConfigFromForm();
    const nodes = (config && config.nodes) || {};

    const cards = STEPS.map((step) => {
      const node = nodes[step] || {};
      const requiredRole = normalize(node.required_role) || "MANAGER";
      const canHandle = role === "ADMIN" || role === requiredRole;
      const amount = formatAmount(node.conditions?.amount_gte ?? 0);
      const hitCount = Math.max(0, Math.trunc(asNumber(node.conditions?.rule_hit_count_gte, 0)));
      const rawRiskLevels = Array.isArray(node.conditions?.risk_levels) ? node.conditions.risk_levels : [];
      const riskLevels = rawRiskLevels.length ? rawRiskLevels.map((item) => riskLabel(item)).join("、") : "未设置";
      return (
        `<div class="col-12 col-md-4 mb-2">` +
        `<div class="preview-item">` +
        `<div class="k">节点 ${step}：${escapeHtml(stepLabel(step))}</div>` +
        `<div class="v">${canHandle ? "可处理节点" : "当前角色不可处理"}</div>` +
        `<div class="small text-muted mt-1">处理角色：${escapeHtml(roleLabel(requiredRole))}</div>` +
        `<div class="small summary mt-1">规则摘要：金额≥${escapeHtml(amount)}元；风险等级：${escapeHtml(riskLevels)}；命中数≥${escapeHtml(String(hitCount))}条</div>` +
        `</div>` +
        `</div>`
      );
    }).join("");
    refs.previewList.innerHTML = cards;

    const links = STEPS.map((step) => {
      const label = QUEUE_BUTTON_LABELS[step] || `查看${step}节点待办`;
      return (
        `<a class="btn btn-sm btn-outline-primary" href="/approval_center?step=${encodeURIComponent(step)}" ` +
        `target="_blank" rel="noopener">${escapeHtml(label)}</a>`
      );
    });
    refs.previewLinks.innerHTML = links.join("");
  }

  function renderVersionsTable(rows) {
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      refs.historyBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-3">暂无历史版本</td></tr>`;
      return;
    }
    refs.historyBody.innerHTML = list
      .map(
        (item) =>
          `<tr>` +
          `<td>v${escapeHtml(String(item.version || "-"))}</td>` +
          `<td>${escapeHtml(statusLabel(item.status))}</td>` +
          `<td>${escapeHtml(text(item.by, "-"))}</td>` +
          `<td>${escapeHtml(text(item.at, "-"))}</td>` +
          `<td>${escapeHtml(scopeLabel(item.scope))}</td>` +
          `<td>${escapeHtml(reasonText(item.reason))}</td>` +
          `</tr>`,
      )
      .join("");
  }

  function refreshRollbackVersionOptions(rows) {
    const options = (Array.isArray(rows) ? rows : [])
      .filter((item) => Number(item.version || 0) > 0)
      .map((item) => ({
        value: String(item.version),
        label: `v${item.version} | ${statusLabel(item.status)} | ${text(item.at, "-")}`,
      }));
    resetSelectOptions(refs.rollbackTargetVersion, options, "请选择版本");
  }

  async function loadCurrent() {
    const payload = await apiJson("/api/workflow/current");
    reasonCodes = Array.isArray(payload.reason_code_options) && payload.reason_code_options.length
      ? payload.reason_code_options.map((item) => normalize(item)).filter(Boolean)
      : DEFAULT_REASON_CODES.slice();

    const reasonOptions = reasonCodes.map((code) => ({
      value: code,
      label: reasonLabel(code),
    }));
    resetSelectOptions(refs.publishReason, reasonOptions, "请选择");
    resetSelectOptions(refs.rollbackReason, reasonOptions, "请选择");

    const current = payload.current || {};
    renderCurrentMeta(current);
    renderConfig(current.config || DEFAULT_CONFIG);
    return current;
  }

  async function loadVersions() {
    const payload = await apiJson("/api/workflow/versions?limit=50");
    const list = Array.isArray(payload.versions) ? payload.versions : [];
    renderVersionsTable(list);
    refreshRollbackVersionOptions(list);
    return list;
  }

  async function saveDraft() {
    const config = readConfigFromForm();
    const check = validateConfig(config);
    if (!check.ok) {
      showFeedback("warning", check.message);
      return;
    }

    const button = refs.saveDraftBtn;
    button.disabled = true;
    const originText = button.textContent;
    button.textContent = "保存中...";
    try {
      const payload = await apiJson("/api/workflow/draft", {
        method: "POST",
        body: JSON.stringify({
          config,
          scope: readScopeFromForm(),
        }),
      });
      const draft = payload.draft || {};
      showFeedback("success", `草稿已保存：v${text(draft.version, "-")}`);
      await loadVersions();
    } catch (error) {
      showFeedback("danger", `保存草稿失败：${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = originText;
    }
  }

  async function publishCurrentConfig() {
    setSelectInvalid(refs.publishReason, refs.publishReasonError, false, "");
    const reason = normalize(getSelectValue(refs.publishReason));
    if (!reason) {
      setSelectInvalid(refs.publishReason, refs.publishReasonError, true, "请选择处理原因");
      return;
    }

    const config = readConfigFromForm();
    const check = validateConfig(config);
    if (!check.ok) {
      showFeedback("warning", "存在缺失或无效配置，已拦截发布。");
      return;
    }

    const button = refs.publishConfirmBtn;
    button.disabled = true;
    const originText = button.textContent;
    button.textContent = "发布中...";
    try {
      const payload = await apiJson("/api/workflow/publish", {
        method: "POST",
        body: JSON.stringify({
          config,
          scope: readScopeFromForm(),
          change_reason_code: reason,
          change_reason_note: text(refs.publishNote.value, ""),
        }),
      });
      renderCurrentMeta(payload.current || {});
      showFeedback("success", `流程已发布生效：v${text((payload.current || {}).version, "-")}`);
      closeModal("#wfPublishModal");
      await loadVersions();
    } catch (error) {
      showFeedback("danger", `发布失败：${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = originText;
    }
  }

  async function rollbackVersion() {
    setSelectInvalid(refs.rollbackTargetVersion, refs.rollbackVersionError, false, "");
    setSelectInvalid(refs.rollbackReason, refs.rollbackReasonError, false, "");

    const targetVersion = Number(getSelectValue(refs.rollbackTargetVersion) || 0);
    if (!Number.isFinite(targetVersion) || targetVersion <= 0) {
      setSelectInvalid(refs.rollbackTargetVersion, refs.rollbackVersionError, true, "请选择目标版本");
      return;
    }

    const reason = normalize(getSelectValue(refs.rollbackReason));
    if (!reason) {
      setSelectInvalid(refs.rollbackReason, refs.rollbackReasonError, true, "请选择处理原因");
      return;
    }

    const button = refs.rollbackConfirmBtn;
    button.disabled = true;
    const originText = button.textContent;
    button.textContent = "回滚中...";
    try {
      const payload = await apiJson("/api/workflow/rollback", {
        method: "POST",
        body: JSON.stringify({
          target_version: targetVersion,
          change_reason_code: reason,
          change_reason_note: text(refs.rollbackNote.value, ""),
        }),
      });
      renderCurrentMeta(payload.current || {});
      renderConfig((payload.current || {}).config || readConfigFromForm());
      showFeedback("success", `已回滚并生效：v${text((payload.current || {}).version, "-")}`);
      closeModal("#wfRollbackModal");
      await loadVersions();
    } catch (error) {
      showFeedback("danger", `回滚失败：${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = originText;
    }
  }

  function bindEvents() {
    refs.saveDraftBtn.addEventListener("click", saveDraft);
    refs.publishBtn.addEventListener("click", () => {
      refs.publishNote.value = "";
      setSelectValue(refs.publishReason, "");
      setSelectInvalid(refs.publishReason, refs.publishReasonError, false, "");
      openModal("#wfPublishModal");
    });
    refs.historyBtn.addEventListener("click", async () => {
      try {
        await loadVersions();
      } catch (error) {
        showFeedback("warning", `加载历史版本失败：${error.message}`);
      }
      openModal("#wfHistoryModal");
    });
    refs.rollbackBtn.addEventListener("click", async () => {
      refs.rollbackNote.value = "";
      setSelectValue(refs.rollbackReason, "");
      setSelectValue(refs.rollbackTargetVersion, "");
      setSelectInvalid(refs.rollbackTargetVersion, refs.rollbackVersionError, false, "");
      setSelectInvalid(refs.rollbackReason, refs.rollbackReasonError, false, "");
      try {
        await loadVersions();
      } catch (error) {
        showFeedback("warning", `加载版本列表失败：${error.message}`);
      }
      openModal("#wfRollbackModal");
    });

    // 预设模板按钮事件
    if (refs.presetStandard) {
      refs.presetStandard.addEventListener("click", () => applyPresetTemplate("standard"));
    }
    if (refs.presetStrict) {
      refs.presetStrict.addEventListener("click", () => applyPresetTemplate("strict"));
    }
    if (refs.presetLoose) {
      refs.presetLoose.addEventListener("click", () => applyPresetTemplate("loose"));
    }
    if (refs.presetReset) {
      refs.presetReset.addEventListener("click", resetToDefault);
    }

    refs.publishConfirmBtn.addEventListener("click", publishCurrentConfig);
    refs.rollbackConfirmBtn.addEventListener("click", rollbackVersion);
    refs.previewRole.addEventListener("change", renderRolePreview);
    refs.scopeInput.addEventListener("change", () => setFieldInvalid(refs.scopeInput, refs.scopeError, false, ""));

    root.querySelectorAll(".js-wf-field").forEach((field) => {
      const clearInvalid = () => {
        const errorNode = document.getElementById(`${field.id}Error`);
        if (errorNode) setFieldInvalid(field, errorNode, false, "");
        renderRolePreview();
        syncCurrentPresetBadge(readConfigFromForm());
      };
      field.addEventListener("change", clearInvalid);
      if (field.tagName === "INPUT") {
        field.addEventListener("input", clearInvalid);
      }
    });
  }

  async function init() {
    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(root);
    }
    bindEvents();

    try {
      await loadCurrent();
      await loadVersions();
      renderRolePreview();
    } catch (error) {
      renderConfig(DEFAULT_CONFIG);
      showFeedback("warning", `初始化失败，已加载本地默认配置：${error.message}`);
    }
  }

  void init();
})();
