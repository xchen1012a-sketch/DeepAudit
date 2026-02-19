(() => {
  const btn = document.getElementById("viewLedgerBtn");
  if (!btn) return;

  const errBox = document.getElementById("ledgerError");
  const riskLevelBadge = document.getElementById("ledgerRiskLevelBadge");
  const modalEl = document.getElementById("ledgerModal");
  const modal = window.jQuery ? window.jQuery(modalEl) : null;

  function text(value) {
    return String(value ?? "").trim();
  }

  function normalize(value) {
    return text(value).toUpperCase();
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (!node) return;
    node.textContent = text(value) || "-";
  }

  function copyToClipboard(id) {
    const node = document.getElementById(id);
    if (!node) return;
    const val = text(node.textContent);
    if (!val || val === "-") return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(val).then(() => {
        if (typeof window.showToast === "function") {
          window.showToast("已复制", "success", 1200);
        }
      }).catch(() => {});
    }
  }

  function cnRiskLevel(levelCode) {
    const api = window.DeepAuditStatusI18N;
    if (api && typeof api.toCnRiskLevel === "function") {
      return api.toCnRiskLevel(levelCode, "\u672a\u77e5");
    }
    const code = normalize(levelCode);
    if (code === "HIGH") return "\u9ad8\u98ce\u9669";
    if (code === "MEDIUM") return "\u4e2d\u98ce\u9669";
    if (code === "LOW") return "\u4f4e\u98ce\u9669";
    return "\u672a\u77e5";
  }

  function toCnProvider(value) {
    const v = String(value ?? "").trim().toLowerCase();
    if (v === "abnormal") return "\u5f02\u5e38";
    if (v === "mock") return "\u6a21\u62df";
    if (v === "unknown") return "\u672a\u77e5";
    if (v === "valid") return "\u6709\u6548";
    if (v === "void") return "\u4f5c\u5e9f";
    return value ? String(value).trim() : "-";
  }

  function toCnPromptVersion(value) {
    const v = String(value ?? "").trim();
    if (!v) return "-";
    return v;
  }

  function riskBadgeClass(levelCode) {
    const code = normalize(levelCode);
    if (code === "HIGH") return "is-high";
    if (code === "MEDIUM") return "is-medium";
    if (code === "LOW") return "is-low";
    return "is-unknown";
  }

  function setRiskLevel(levelCode) {
    const code = normalize(levelCode) || "UNKNOWN";
    const cn = cnRiskLevel(code);
    const codeEl = document.getElementById("ledgerRiskLevelCode");
    if (codeEl) codeEl.textContent = code ? `${cn}（${code}）` : "-";

    if (!riskLevelBadge) return;
    riskLevelBadge.className = `risk-ledger-level-badge ${riskBadgeClass(code)}`;
    riskLevelBadge.textContent = "\u98ce\u9669\u7b49\u7ea7\uff1a" + (cn || "\u672a\u77e5");
  }

  function showError(message) {
    if (!errBox) return;
    const msg = text(message) || "\u52a0\u8f7d\u5931\u8d25";
    errBox.innerHTML = '<span class="alert-icon"><i class="ri-close-circle-line"></i></span><span class="alert-body">' + msg + '</span>';
    errBox.classList.remove("d-none");
  }

  function hideError() {
    if (!errBox) return;
    errBox.innerHTML = "";
    errBox.classList.add("d-none");
  }

  function renderRulesHit(evidence) {
    const listEl = document.getElementById("ledgerRulesHit");
    if (!listEl) return;
    listEl.innerHTML = "";
    if (!Array.isArray(evidence) || evidence.length === 0) {
      const li = document.createElement("li");
      li.className = "risk-ledger-rule-item risk-ledger-rule-item-empty";
      li.textContent = "\u65e0";
      listEl.appendChild(li);
      return;
    }
    evidence.forEach(function (item) {
      if (!item || typeof item !== "object") return;
      const ruleName = text(item.rule_name || item.key || "\u2014");
      const hitElement = text(item.value || item.key || "\u2014");
      const triggerReason = text(item.summary || item.reason || "\u2014");
      const li = document.createElement("li");
      li.className = "risk-ledger-rule-item";
      li.innerHTML = "<span class=\"risk-ledger-rule-name\">" + escapeHtml(ruleName) + "</span>" +
        "<span class=\"risk-ledger-rule-meta\"><b>\u547d\u4e2d\u8981\u7d20\uff1a</b>" + escapeHtml(hitElement) + "</span>" +
        "<span class=\"risk-ledger-rule-meta\"><b>\u89e6\u53d1\u539f\u56e0\uff1a</b>" + escapeHtml(triggerReason) + "</span>";
      listEl.appendChild(li);
    });
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  async function loadLedger(traceId) {
    hideError();
    setText("ledgerTraceId", traceId || "-");
    setText("ledgerCreatedAt", "-");
    setRiskLevel("");
    setText("ledgerRiskScore", "-");
    setText("ledgerInvoiceId", "-");
    setText("ledgerHashPrev", "-");
    setText("ledgerHashCurr", "-");
    setText("ledgerConclusion", "-");
    setText("ledgerSuggestion", "-");
    renderRulesHit([]);
    const providerEl = document.getElementById("ledgerProvider");
    const versionEl = document.getElementById("ledgerPromptVersion");
    if (providerEl) providerEl.textContent = "-";
    if (versionEl) versionEl.textContent = "-";

    if (!traceId) {
      showError("\u7f3a\u5c11 trace_id");
      return;
    }

    try {
      const response = await fetch(`/api/ai/ledger/${encodeURIComponent(traceId)}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!payload || payload.ok !== true) {
        showError("\u672a\u627e\u5230\u5ba1\u8ba1\u94fe\u8bb0\u5f55");
        return;
      }

      const output = payload.output_json && typeof payload.output_json === "object" ? payload.output_json : {};
      setText("ledgerTraceId", payload.trace_id);
      setText("ledgerCreatedAt", payload.created_at);
      setRiskLevel(payload.risk_level);
      setText("ledgerRiskScore", payload.risk_score);
      setText("ledgerInvoiceId", payload.invoice_id);
      setText("ledgerHashPrev", payload.hash_prev);
      setText("ledgerHashCurr", payload.hash_curr);
      setText("ledgerConclusion", output.summary || "-");
      setText("ledgerSuggestion", output.suggestion || "-");
      const providerEl = document.getElementById("ledgerProvider");
      const versionEl = document.getElementById("ledgerPromptVersion");
      if (providerEl) providerEl.textContent = toCnProvider(payload.provider) || "-";
      if (versionEl) versionEl.textContent = toCnPromptVersion(payload.prompt_version) || "-";
      const evidence = Array.isArray(output.evidence) ? output.evidence : [];
      renderRulesHit(evidence.length ? evidence : (output.rule_summary ? [{ rule_name: "\u89c4\u5219\u6458\u8981", value: output.rule_summary, summary: "-" }] : []));
    } catch (error) {
      showError(`\u52a0\u8f7d\u5931\u8d25\uff1a${error.message || error}`);
    }
  }

  btn.addEventListener("click", async () => {
    const traceId = text(btn.getAttribute("data-trace-id"));
    await loadLedger(traceId);
    if (modal) {
      modal.modal("show");
    }
  });

  document.querySelectorAll(".risk-copy-btn").forEach(function (copyBtn) {
    copyBtn.addEventListener("click", function () {
      const targetId = this.getAttribute("data-copy-target");
      if (targetId) copyToClipboard(targetId);
    });
  });
})();

(() => {
  const page = document.getElementById("risk-case-detail-page");
  const initNode = document.getElementById("riskCaseDetailInit");
  if (!page || !initNode) return;

  function text(value) {
    return String(value ?? "").trim();
  }

  function normalize(value) {
    return text(value).toUpperCase();
  }

  function parseInitData() {
    try {
      const raw = text(initNode.textContent);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function parseDate(value) {
    const raw = text(value);
    if (!raw) return null;

    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (m) {
      const year = Number(m[1]);
      const month = Number(m[2]) - 1;
      const day = Number(m[3]);
      const hour = Number(m[4]);
      const minute = Number(m[5]);
      const second = Number(m[6] || "0");
      const dt = new Date(year, month, day, hour, minute, second);
      return Number.isFinite(dt.getTime()) ? dt : null;
    }

    const fallback = new Date(raw);
    return Number.isFinite(fallback.getTime()) ? fallback : null;
  }

  function formatDateTime(value, withSecond = false) {
    const dt = parseDate(value);
    if (!dt) {
      const raw = text(value);
      if (!raw) return "-";
      return withSecond ? raw.slice(0, 19) : raw.slice(0, 16);
    }

    const yyyy = String(dt.getFullYear());
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    const hh = String(dt.getHours()).padStart(2, "0");
    const mi = String(dt.getMinutes()).padStart(2, "0");
    if (!withSecond) {
      return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
    }
    const ss = String(dt.getSeconds()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  function nowText(withSecond = true) {
    const now = new Date();
    const yyyy = String(now.getFullYear());
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const hh = String(now.getHours()).padStart(2, "0");
    const mi = String(now.getMinutes()).padStart(2, "0");
    if (!withSecond) {
      return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
    }
    const ss = String(now.getSeconds()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  const initData = parseInitData();
  const state = {
    case: initData.case && typeof initData.case === "object" ? { ...initData.case } : {},
    actions: Array.isArray(initData.actions) ? initData.actions.slice() : [],
    operator: text(initData.operator) || text(page.getAttribute("data-current-operator")) || "-",
    showAll: false,
    isSubmitting: false,
  };

  state.case.status = normalize(state.case.status || "OPEN");
  state.case.risk_level = normalize(state.case.risk_level || "UNKNOWN");

  const refs = {
    summaryRiskBadge: document.getElementById("summaryRiskBadge"),
    summaryRiskCode: document.getElementById("summaryRiskCode"),
    summaryRiskScore: document.getElementById("summaryRiskScore"),
    summaryInvoiceId: document.getElementById("summaryInvoiceId"),
    summaryStatusBadge: document.getElementById("summaryStatusBadge"),
    summaryStatusCode: document.getElementById("summaryStatusCode"),
    summaryAssignee: document.getElementById("summaryAssignee"),
    summaryLatestProgress: document.getElementById("summaryLatestProgress"),
    summaryClosedAt: document.getElementById("summaryClosedAt"),
    summaryResolution: document.getElementById("summaryResolution"),

    caseClosedNotice: document.getElementById("caseClosedNotice"),
    reviewActionBody: document.getElementById("reviewActionBody"),
    msg: document.getElementById("caseActionMsg"),
    actionType: document.getElementById("reviewActionType"),
    assignWrap: document.getElementById("reviewAssignWrap"),
    assignInput: document.getElementById("reviewAssignTo"),
    assignError: document.getElementById("reviewAssignError"),
    scoreWrap: document.getElementById("reviewScoreWrap"),
    scoreInput: document.getElementById("reviewTargetScore"),
    scoreError: document.getElementById("reviewScoreError"),
    closeWrap: document.getElementById("reviewCloseWrap"),
    closeInput: document.getElementById("reviewResolutionNote"),
    closeError: document.getElementById("reviewCloseError"),
    reasonSelect: document.getElementById("reviewReasonCode"),
    reasonError: document.getElementById("reviewReasonError"),
    reasonNote: document.getElementById("reviewReasonNote"),
    actionHint: document.getElementById("reviewActionHint"),
    submitBtn: document.getElementById("reviewSubmitBtn"),

    toggleActionsBtn: document.getElementById("toggleAllActionsBtn"),
    actionTableBody: document.getElementById("caseActionTableBody"),
  };

  if (!refs.actionType || !refs.reasonSelect || !refs.submitBtn || !refs.actionTableBody) {
    return;
  }

  const RISK_META = {
    HIGH: { label: "高风险", badge: "badge-danger" },
    MEDIUM: { label: "中风险", badge: "badge-warning" },
    LOW: { label: "低风险", badge: "badge-secondary" },
    UNKNOWN: { label: "未知", badge: "badge-light" },
  };

  const STATUS_META = {
    OPEN: { label: "进行中", badge: "badge-info" },
    CLOSED: { label: "已结案", badge: "badge-secondary" },
  };

  const ACTION_HINTS = {
    CLAIM: "签收将把案件分配给当前操作人。",
    TRANSFER: "转派会更新指派人并记录留痕。",
    FALSE_POSITIVE: "误报会标记为误报动作，并将风险分调整为 0。",
    CLOSE: "结案需要填写结案说明，提交后状态变为 CLOSED。",
    ADJUST_SCORE: "调分会修改风险分并生成审计记录。",
  };

  function isClosedCase() {
    return normalize(state.case.status) === "CLOSED";
  }

  function summaryStatusCode(status) {
    return normalize(status) === "CLOSED" ? "CLOSED" : "OPEN";
  }

  function actionLabel(actionType, actionNote) {
    const typeCode = normalize(actionType);
    const noteLower = text(actionNote).toLowerCase();

    if (typeCode === "ASSIGN" || typeCode === "CASE_ASSIGNED") {
      if (noteLower.includes("claim")) return "签收";
      if (noteLower.includes("transfer")) return "转派";
      return "案件分派";
    }

    if (typeCode === "CLOSE" || typeCode === "CASE_CLOSED") {
      if (noteLower.includes("false_positive") || noteLower.includes("误报")) return "误报结案";
      return "结案";
    }

    if (typeCode === "SCORE_ADJUST") {
      if (noteLower.includes("false_positive") || noteLower.includes("误报")) return "误报";
      return "调分";
    }

    if (typeCode === "CREATE" || typeCode === "CASE_CREATED") return "案件创建";
    if (typeCode === "RULE_HIT") return "规则命中";
    if (typeCode === "AI_EXPLAIN") return "智能解释完成";

    return "已更新";
  }

  function sortedActions() {
    return state.actions
      .slice()
      .sort((a, b) => {
        const ta = parseDate(a && a.created_at);
        const tb = parseDate(b && b.created_at);
        const ma = ta ? ta.getTime() : 0;
        const mb = tb ? tb.getTime() : 0;
        if (ma !== mb) return mb - ma;
        const ia = Number(a && a.id) || 0;
        const ib = Number(b && b.id) || 0;
        return ib - ia;
      });
  }

  function setMsg(message, isError = false) {
    if (!refs.msg) return;
    refs.msg.textContent = text(message);
    refs.msg.className = isError ? "small text-danger mb-2" : "small text-muted mb-2";
  }

  function setInvalid(node, errorNode, invalid, message = "") {
    if (node) {
      node.classList.toggle("is-invalid", !!invalid);
    }
    if (errorNode) {
      if (invalid) {
        if (message) {
          errorNode.textContent = message;
        }
        errorNode.classList.remove("d-none");
      } else {
        errorNode.classList.add("d-none");
      }
    }
  }

  function renderSummary() {
    const riskCode = normalize(state.case.risk_level || "UNKNOWN");
    const riskMeta = RISK_META[riskCode] || RISK_META.UNKNOWN;
    if (refs.summaryRiskBadge) {
      refs.summaryRiskBadge.className = `badge ${riskMeta.badge}`;
      refs.summaryRiskBadge.textContent = riskMeta.label;
    }
    if (refs.summaryRiskCode) {
      refs.summaryRiskCode.textContent = `(${riskCode})`;
    }

    if (refs.summaryRiskScore) {
      refs.summaryRiskScore.textContent = text(state.case.risk_score) || "-";
    }
    if (refs.summaryInvoiceId) {
      refs.summaryInvoiceId.textContent = text(state.case.invoice_id) || "-";
    }

    const statusCode = summaryStatusCode(state.case.status);
    const statusMeta = STATUS_META[statusCode] || STATUS_META.OPEN;
    if (refs.summaryStatusBadge) {
      refs.summaryStatusBadge.className = `badge ${statusMeta.badge}`;
      refs.summaryStatusBadge.textContent = statusMeta.label;
    }
    if (refs.summaryStatusCode) {
      refs.summaryStatusCode.textContent = `(${statusCode})`;
    }

    if (refs.summaryAssignee) {
      refs.summaryAssignee.textContent = text(state.case.assigned_to) || "-";
    }

    if (refs.summaryClosedAt) {
      refs.summaryClosedAt.textContent = text(state.case.closed_at) || "-";
    }
    if (refs.summaryResolution) {
      refs.summaryResolution.textContent = text(state.case.resolution_note) || "-";
    }

    const latest = sortedActions()[0];
    const latestText = latest
      ? `${actionLabel(latest.action_type, latest.action_note)} · ${formatDateTime(latest.created_at, false)}`
      : "-";
    if (refs.summaryLatestProgress) {
      refs.summaryLatestProgress.textContent = latestText;
    }
  }

  function renderActionsTable() {
    const tbody = refs.actionTableBody;
    if (!tbody) return;

    tbody.innerHTML = "";
    const list = sortedActions();
    const visible = state.showAll ? list : list.slice(0, 5);

    if (!visible.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.className = "text-center text-muted py-3";
      td.textContent = "暂无操作记录";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      visible.forEach((item) => {
        const tr = document.createElement("tr");

        const tdId = document.createElement("td");
        tdId.textContent = text(item.id) || "-";

        const tdAction = document.createElement("td");
        const actionCn = actionLabel(item.action_type, item.action_note);
        const actionCode = normalize(item.action_type) || "-";
        const main = document.createElement("span");
        main.textContent = actionCn;
        main.title = actionCode;
        const code = document.createElement("span");
        code.className = "small text-muted ml-1";
        code.textContent = `(${actionCode})`;
        tdAction.appendChild(main);
        tdAction.appendChild(code);

        const tdOperator = document.createElement("td");
        tdOperator.textContent = text(item.operator) || "-";

        const tdNote = document.createElement("td");
        tdNote.textContent = text(item.action_note) || "-";

        const tdTime = document.createElement("td");
        tdTime.textContent = formatDateTime(item.created_at, false);

        tr.appendChild(tdId);
        tr.appendChild(tdAction);
        tr.appendChild(tdOperator);
        tr.appendChild(tdNote);
        tr.appendChild(tdTime);
        tbody.appendChild(tr);
      });
    }

    if (refs.toggleActionsBtn) {
      if (list.length > 5) {
        refs.toggleActionsBtn.classList.remove("d-none");
        refs.toggleActionsBtn.textContent = state.showAll ? "收起" : `展开全部（${list.length} 条）`;
      } else {
        refs.toggleActionsBtn.classList.add("d-none");
      }
    }
  }

  function renderAll() {
    renderSummary();
    renderActionsTable();
    syncActionAvailability();
  }

  function syncActionForm() {
    const action = normalize(refs.actionType.value || "CLAIM");
    const showAssign = action === "TRANSFER";
    const showScore = action === "ADJUST_SCORE";
    const showClose = action === "CLOSE";

    refs.assignWrap.classList.toggle("d-none", !showAssign);
    refs.scoreWrap.classList.toggle("d-none", !showScore);
    refs.closeWrap.classList.toggle("d-none", !showClose);

    setInvalid(refs.assignInput, refs.assignError, false);
    setInvalid(refs.scoreInput, refs.scoreError, false);
    setInvalid(refs.closeInput, refs.closeError, false);
    if (refs.actionHint) {
      refs.actionHint.textContent = ACTION_HINTS[action] || "请选择动作并提交。";
    }
  }

  function syncActionAvailability() {
    const closed = isClosedCase();
    if (refs.caseClosedNotice) {
      refs.caseClosedNotice.classList.toggle("d-none", !closed);
    }
    if (refs.reviewActionBody) {
      refs.reviewActionBody.classList.toggle("d-none", !!closed);
    }
    if (!refs.submitBtn) return;
    refs.submitBtn.disabled = state.isSubmitting || closed;
    if (closed && !state.isSubmitting) {
      setMsg("已结案仅可查看", false);
    }
  }

  function clearReasonInvalid() {
    setInvalid(refs.reasonSelect, refs.reasonError, false);
  }

  function validateAndBuildRequest() {
    const action = normalize(refs.actionType.value || "CLAIM");
    const reasonCode = normalize(refs.reasonSelect.value);
    const reasonNote = text(refs.reasonNote.value);

    clearReasonInvalid();
    setInvalid(refs.assignInput, refs.assignError, false);
    setInvalid(refs.scoreInput, refs.scoreError, false);
    setInvalid(refs.closeInput, refs.closeError, false);

    if (!reasonCode) {
      setInvalid(refs.reasonSelect, refs.reasonError, true, "请选择处理原因");
      setMsg("未选择处理原因，无法提交。", true);
      return null;
    }

    const id = Number(state.case.id) || 0;
    if (id <= 0) {
      setMsg("案件ID无效，无法提交。", true);
      return null;
    }

    const suffix = reasonNote ? `: ${reasonNote}` : "";
    const common = {
      change_reason_code: reasonCode,
      change_reason_note: reasonNote,
    };

    if (action === "CLAIM") {
      const assignedTo = state.operator || text(state.case.assigned_to);
      if (!assignedTo) {
        setMsg("未识别当前操作人，请改用“转派”并填写指派人。", true);
        return null;
      }
      return {
        url: `/risk/cases/${id}/assign`,
        payload: {
          assigned_to: assignedTo,
          action_note: `risk_case_detail_claim${suffix}`,
          ...common,
        },
        auditType: "ASSIGN",
        actionLabel: "签收",
        expectedCase: { status: "ASSIGNED", assigned_to: assignedTo },
      };
    }

    if (action === "TRANSFER") {
      const assignedTo = text(refs.assignInput.value);
      if (!assignedTo) {
        setInvalid(refs.assignInput, refs.assignError, true, "请填写指派人");
        setMsg("未填写指派人，无法转派。", true);
        return null;
      }
      return {
        url: `/risk/cases/${id}/assign`,
        payload: {
          assigned_to: assignedTo,
          action_note: `risk_case_detail_transfer${suffix}`,
          ...common,
        },
        auditType: "ASSIGN",
        actionLabel: "转派",
        expectedCase: { status: "ASSIGNED", assigned_to: assignedTo },
      };
    }

    if (action === "FALSE_POSITIVE") {
      return {
        url: `/api/risk/cases/${id}/score`,
        payload: {
          risk_score: 0,
          action_note: `risk_case_detail_false_positive${suffix}`,
          ...common,
        },
        auditType: "SCORE_ADJUST",
        actionLabel: "误报",
        expectedCase: { risk_score: 0 },
      };
    }

    if (action === "CLOSE") {
      const resolution = text(refs.closeInput.value);
      if (!resolution) {
        setInvalid(refs.closeInput, refs.closeError, true, "请填写结案说明");
        setMsg("结案说明必填。", true);
        return null;
      }
      return {
        url: `/risk/cases/${id}/close`,
        payload: {
          resolution_note: resolution,
          action_note: `risk_case_detail_close${suffix}`,
          ...common,
        },
        auditType: "CLOSE",
        actionLabel: "结案",
        expectedCase: { status: "CLOSED", resolution_note: resolution },
      };
    }

    if (action === "ADJUST_SCORE") {
      const score = Number(refs.scoreInput.value);
      if (!Number.isFinite(score) || score < 0 || score > 100) {
        setInvalid(refs.scoreInput, refs.scoreError, true, "目标分需在 0-100 之间");
        setMsg("目标分不合法。", true);
        return null;
      }
      return {
        url: `/api/risk/cases/${id}/score`,
        payload: {
          risk_score: Math.round(score),
          action_note: `risk_case_detail_adjust_score${suffix}`,
          ...common,
        },
        auditType: "SCORE_ADJUST",
        actionLabel: "调分",
        expectedCase: { risk_score: Math.round(score) },
      };
    }

    setMsg("不支持的动作类型。", true);
    return null;
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data || data.ok !== true) {
      throw new Error(text(data.message) || text(data.msg) || `HTTP ${response.status}`);
    }
    return data;
  }

  function nextActionId() {
    let maxId = 0;
    state.actions.forEach((item) => {
      const num = Number(item && item.id);
      if (Number.isFinite(num)) {
        maxId = Math.max(maxId, num);
      }
    });
    return maxId > 0 ? maxId + 1 : state.actions.length + 1;
  }

  function mergeCaseState(fromApi, expected) {
    const apiCase = fromApi && typeof fromApi === "object" ? fromApi : {};
    const next = { ...state.case };

    const mergeField = (key, transform) => {
      if (Object.prototype.hasOwnProperty.call(apiCase, key)) {
        next[key] = transform ? transform(apiCase[key]) : apiCase[key];
        return;
      }
      if (expected && Object.prototype.hasOwnProperty.call(expected, key)) {
        next[key] = expected[key];
      }
    };

    mergeField("status", (v) => normalize(v || next.status));
    mergeField("assigned_to", (v) => text(v));
    mergeField("risk_score", (v) => text(v));
    mergeField("resolution_note", (v) => text(v));
    mergeField("closed_at", (v) => text(v));

    state.case = next;
  }

  function appendAuditRecord(auditType, actionNote, timestamp) {
    state.actions.push({
      id: nextActionId(),
      action_type: auditType,
      operator: state.operator || "-",
      action_note: text(actionNote) || "-",
      created_at: text(timestamp) || nowText(true),
    });
  }

  async function handleSubmit() {
    const request = validateAndBuildRequest();
    if (!request) return;

    state.isSubmitting = true;
    syncActionAvailability();

    try {
      const result = await postJson(request.url, request.payload);
      const apiCase = result && result.case && typeof result.case === "object" ? result.case : {};
      mergeCaseState(apiCase, request.expectedCase);

      const actionTime = text(apiCase.closed_at) || nowText(true);
      appendAuditRecord(request.auditType, request.payload.action_note, actionTime);

      if (request.auditType === "CLOSE") {
        state.case.closed_at = text(apiCase.closed_at) || actionTime;
        if (!text(state.case.resolution_note)) {
          state.case.resolution_note = text(request.payload.resolution_note);
        }
      }

      renderAll();
      setMsg(`${request.actionLabel}成功：${formatDateTime(actionTime, false)}`, false);
      if (typeof window.showToast === "function") {
        window.showToast(`${request.actionLabel}成功`, "success", 1600);
      }
    } catch (error) {
      setMsg(`提交失败：${error.message || error}`, true);
    } finally {
      state.isSubmitting = false;
      syncActionAvailability();
    }
  }

  refs.actionType.addEventListener("change", () => {
    syncActionForm();
  });

  refs.reasonSelect.addEventListener("change", () => {
    if (normalize(refs.reasonSelect.value)) {
      clearReasonInvalid();
    }
  });

  if (refs.assignInput) {
    refs.assignInput.addEventListener("input", () => {
      if (text(refs.assignInput.value)) {
        setInvalid(refs.assignInput, refs.assignError, false);
      }
    });
  }

  if (refs.scoreInput) {
    refs.scoreInput.addEventListener("input", () => {
      const score = Number(refs.scoreInput.value);
      if (Number.isFinite(score) && score >= 0 && score <= 100) {
        setInvalid(refs.scoreInput, refs.scoreError, false);
      }
    });
  }

  if (refs.closeInput) {
    refs.closeInput.addEventListener("input", () => {
      if (text(refs.closeInput.value)) {
        setInvalid(refs.closeInput, refs.closeError, false);
      }
    });
  }

  refs.submitBtn.addEventListener("click", handleSubmit);

  if (refs.toggleActionsBtn) {
    refs.toggleActionsBtn.addEventListener("click", () => {
      state.showAll = !state.showAll;
      renderActionsTable();
    });
  }

  if (typeof window.initEnterpriseSelect === "function") {
    window.initEnterpriseSelect(page);
  }

  syncActionForm();
  renderAll();
})();

