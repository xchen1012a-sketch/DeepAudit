(() => {
  const LEDGER_API_VERSION = "LEDGER_API_V2";
  const i18n = window.DeepAuditStatusI18N || {
    toCnApprovalStatus: (v, f = "—") => (String(v || "").trim() || f),
    toCnLedgerState: (v, f = "—") => (String(v || "").trim() || f),
    toCnVerifyStatus: (v, f = "—") => (String(v || "").trim() || f),
    toCnApprovalStage: (v, f = "—") => (String(v || "").trim() || f),
    toCnAction: (v, f = "—") => (String(v || "").trim() || f),
  };

  function text(v, fallback = "-") {
    const s = String(v ?? "").trim();
    return s || fallback;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const FIELD_LABELS = {
    amount: "金额",
    invoice_date: "开票日期",
    created_at: "入账日期",
    expense_type: "费用类别",
    expense_category: "费用类别",
    department: "部门",
    approval_status: "审批状态",
    approval_stage: "审批环节",
    applicant: "报销人",
    merchant_name: "供应商",
    item_name: "费用类别",
    record_state: "台账状态",
    verify_status: "验真状态",
    reference_no: "单据编号",
    invoice_code: "发票代码",
    invoice_number: "发票号码",
    trace_id: "追踪编号",
    risk_level: "风险研判",
    ai_risk_level: "风险研判",
  };

  const badgePalette = {
    success: "status-badge success",
    warning: "status-badge warning",
    danger: "status-badge danger",
    info: "status-badge info",
    neutral: "status-badge neutral",
  };

  const DEBUG_CHANGE_REASON = false;

  function debugLog(...args) {
    if (DEBUG_CHANGE_REASON) {
      // eslint-disable-next-line no-console
      console.log("[change-reason-debug]", ...args);
    }
  }

  function setSelectValue(select, value = "") {
    if (!select) return;
    if (select.tomselect) {
      select.tomselect.setValue(String(value || ""), true);
    } else {
      select.value = String(value || "");
    }
  }

  function markSelectInvalid(select, hintNode, invalid) {
    if (!select) return;
    select.classList.toggle("is-invalid", !!invalid);
    if (hintNode) {
      hintNode.style.display = invalid ? "" : "none";
    }
  }

  function getSelectValue(select) {
    if (!select) return "";
    if (select.tomselect && typeof select.tomselect.getValue === "function") {
      return String(select.tomselect.getValue() || "").trim();
    }
    return String(select.value || "").trim();
  }

  function safeNumber(value) {
    const raw = String(value ?? "").trim();
    if (!raw) return null;
    const normalized = raw
      .replace(/[¥￥,\s]/g, "")
      .replace(/，/g, "")
      .replace(/[^\d.-]/g, "");
    if (!normalized || normalized === "-" || normalized === "." || normalized === "-.") return null;
    const num = Number(normalized);
    return Number.isFinite(num) ? num : null;
  }

  function formatAmount(value) {
    const num = safeNumber(value);
    if (num === null) return "—";
    return `¥${num.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function formatDate(value) {
    const textValue = text(value, "");
    if (!textValue) return "—";
    const date = new Date(textValue);
    if (Number.isNaN(date.getTime())) return textValue;
    const y = date.getFullYear();
    const m = `${date.getMonth() + 1}`.padStart(2, "0");
    const d = `${date.getDate()}`.padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function computeStatusMeta(key, value) {
    const upper = text(value, "").toUpperCase();
    let label = upper || "—";
    if (key === "approval_status") {
      label = i18n.toCnApprovalStatus(upper, label);
    } else if (key === "approval_stage") {
      label = i18n.toCnApprovalStage(upper, label);
    } else if (key === "record_state") {
      label = i18n.toCnLedgerState(upper, label);
    } else if (key === "verify_status") {
      label = i18n.toCnVerifyStatus(upper, label);
    }
    let tone = "neutral";
    if (["APPROVED", "LEDGER", "SUCCESS", "VALID", "PASS"].includes(upper)) tone = "success";
    else if (["PENDING", "IN_PROGRESS", "PROCESSING"].includes(upper)) tone = "warning";
    else if (["REJECTED", "FAILED", "DRAFT", "INVALID"].includes(upper)) tone = "danger";
    else if (upper) tone = "info";
    return { label, tone };
  }

  function formatStatus(key, value) {
    const meta = computeStatusMeta(key, value);
    return `<span class="${badgePalette[meta.tone] || badgePalette.neutral}">${escapeHtml(meta.label)}</span>`;
  }

  function formatValue(key, value) {
    if (value === undefined || value === null || value === "") return "—";
    const lowerKey = String(key || "").toLowerCase();
    if (["amount", "tax_amount", "total_amount", "total"].includes(lowerKey)) {
      return formatAmount(value);
    }
    if (lowerKey.includes("date")) {
      return formatDate(value);
    }
    if (lowerKey.includes("status") || lowerKey.includes("state")) {
      return formatStatus(lowerKey, value);
    }
    return escapeHtml(String(value));
  }

  function setBadge(id, key, value) {
    const node = document.getElementById(id);
    if (!node) return;
    const meta = computeStatusMeta(key, value);
    node.className = `${badgePalette[meta.tone] || badgePalette.neutral}`;
    node.textContent = meta.label;
  }

  function computeDiff(before = {}, after = {}) {
    const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
    const changes = [];
    keys.forEach((key) => {
      const prev = before ? before[key] : undefined;
      const next = after ? after[key] : undefined;
      if (JSON.stringify(prev) === JSON.stringify(next)) return;
      changes.push({
        key,
        label: FIELD_LABELS[key] || key,
        before: prev,
        after: next,
      });
    });
    return changes;
  }

  function setupRequiredSelect(selectId, hintId, submitId) {
    const select = document.getElementById(selectId);
    const hint = hintId ? document.getElementById(hintId) : null;
    const submit = submitId ? document.getElementById(submitId) : null;
    if (!select) return null;

    const update = () => {
      const hasValue = !!getSelectValue(select);
      markSelectInvalid(select, hint, !hasValue);
      if (submit) submit.disabled = !hasValue;
    };

    select.addEventListener("change", update);
    update();
    return update;
  }

  function showMsg(type, msg) {
    if (typeof window.showToast === "function") {
      window.showToast(msg, type, 2400);
      return;
    }

    let host = document.getElementById("ledgerInlineToastHost");
    if (!host) {
      host = document.createElement("div");
      host.id = "ledgerInlineToastHost";
      host.style.position = "fixed";
      host.style.top = "16px";
      host.style.right = "16px";
      host.style.zIndex = "20000";
      host.style.maxWidth = "360px";
      host.style.display = "flex";
      host.style.flexDirection = "column";
      host.style.gap = "8px";
      document.body.appendChild(host);
    }

    const palette = {
      success: { bg: "#e8f6ec", fg: "#1f6f3d", border: "#b8e3c7" },
      warning: { bg: "#fff8e6", fg: "#8a5b00", border: "#ffe1a3" },
      danger: { bg: "#fdebec", fg: "#9f1f1f", border: "#f6c6cb" },
      info: { bg: "#e8f2ff", fg: "#1d4ed8", border: "#bcd5ff" },
    };
    const style = palette[type] || palette.info;

    const toast = document.createElement("div");
    toast.style.padding = "10px 12px";
    toast.style.borderRadius = "8px";
    toast.style.border = `1px solid ${style.border}`;
    toast.style.background = style.bg;
    toast.style.color = style.fg;
    toast.style.fontSize = "13px";
    toast.style.fontWeight = "600";
    toast.style.boxShadow = "0 8px 20px rgba(15, 23, 42, 0.08)";
    toast.textContent = String(msg || "");
    host.appendChild(toast);
    window.setTimeout(() => {
      if (toast && toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 2600);
  }

  async function apiJson(url, options = {}) {
    const res = await fetch(url, {
      headers: {
        Accept: "application/json",
        "X-Api-Version": LEDGER_API_VERSION,
        ...(options.headers || {}),
      },
      ...options,
    });

    const raw = await res.text();
    let payload = {};
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch (_err) {
        payload = { ok: false, msg: raw };
      }
    }

    if (!res.ok || !payload || payload.ok !== true) {
      const error = new Error((payload && (payload.msg || payload.message)) || `请求失败（HTTP ${res.status}）`);
      error.status = res.status;
      error.payload = payload;
      throw error;
    }

    if (payload.debug_marker && payload.debug_marker !== LEDGER_API_VERSION) {
      console.warn("Unexpected API marker:", payload.debug_marker);
    }

    return payload;
  }

  function isApiNotWired(error) {
    const status = Number(error && error.status);
    return [404, 405, 501].includes(status);
  }

  async function logUiBlocked(action, invoiceId, reason = "API_NOT_WIRED") {
    try {
      await apiJson("/api/ledger/ui-action-blocked", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          invoice_id: Number(invoiceId || 0),
          reason,
          trace_id: text(document.getElementById("evRequestId")?.textContent, "-"),
        }),
      });
    } catch (_err) {
      // best effort only
    }
  }

  function openSandboxNotice(action, invoiceId, messageText) {
    const mappedAction = i18n.toCnAction(action, "");
    const actionCn = mappedAction && mappedAction !== action ? mappedAction : "业务动作";
    const notice = [
      `动作：${actionCn}`,
      "状态：功能待接入（沙箱模式）",
      "影响：仅展示交互反馈，不会影响真实业务数据。",
      `说明：${text(messageText, "当前接口未接入。")}`,
    ].join("\n");

    const noticeNode = document.getElementById("sandboxNoticeText");
    if (noticeNode) {
      noticeNode.textContent = notice;
    }
    showMsg("warning", `${actionCn}功能待接入（沙箱模式）`);
    logUiBlocked(action, invoiceId);
    if (window.jQuery) {
      window.jQuery("#sandboxNoticeModal").modal("show");
    }
  }

  function selectedIds() {
    return Array.from(document.querySelectorAll(".row-check:checked"))
      .map((n) => Number(n.value || 0))
      .filter((id) => Number.isFinite(id) && id > 0);
  }

  function bindPageSize() {
    const pageSize = document.getElementById("ledgerPageSize");
    if (!pageSize) return;
    pageSize.addEventListener("change", () => {
      const nextLimit = Number(pageSize.value || 20);
      if (!nextLimit || nextLimit <= 0) return;
      const url = new URL(window.location.href);
      url.searchParams.set("limit", String(nextLimit));
      if (!url.searchParams.get("tab")) {
        url.searchParams.set("tab", "ledger");
      }
      window.location.assign(url.toString());
    });
  }

  function bindSelectAll() {
    const selectAll = document.getElementById("selectAll");
    if (!selectAll) return;
    selectAll.addEventListener("change", () => {
      const checked = !!selectAll.checked;
      document.querySelectorAll(".row-check").forEach((n) => {
        n.checked = checked;
      });
    });
  }

  function updateTableRowState(invoiceId, payload = {}) {
    const row = document.querySelector(`#ledgerTable tr[data-id="${String(invoiceId)}"]`);
    if (!row) return;

    const recordState = text(payload.record_state, "").toUpperCase();
    const recordStateCn = text(
      payload.record_state_cn,
      i18n.toCnLedgerState(recordState, row.getAttribute("data-state") === "DRAFT" ? "待补录" : "已入账")
    );
    const approvalCn = text(
      payload.approval_status_cn,
      i18n.toCnApprovalStatus(payload.approval_status, "待审核")
    );

    if (recordState) {
      row.setAttribute("data-state", recordState);
      row.classList.toggle("ledger-row-draft", recordState === "DRAFT");
      const stateNode = row.querySelector(".state-pill");
      if (stateNode) {
        stateNode.textContent = recordStateCn;
        stateNode.classList.toggle("state-ledger", recordState === "LEDGER");
        stateNode.classList.toggle("state-draft", recordState !== "LEDGER");
      }
    }

    const approvalNode = row.querySelector(".approval-status-cell");
    if (approvalNode) {
      approvalNode.textContent = approvalCn;
    }
  }

  const actionTitle = document.getElementById("ledgerActionTitle");
  const actionId = document.getElementById("ledgerActionId");
  const actionType = document.getElementById("ledgerActionType");
  const actionSource = document.getElementById("ledgerActionSource");
  const actionReason = document.getElementById("ledgerActionReason");
  const actionComment = document.getElementById("ledgerActionComment");
  const actionHint = document.getElementById("ledgerActionHint");
  const actionSubmit = document.getElementById("ledgerActionSubmit");
  const managedModalIds = ["#evidenceModal"];
  const evidenceModalId = "#evidenceModal";
  const actionModalId = "#ledgerActionModal";
  const modalClassWhitelist = `${evidenceModalId}`;

  function ensureModalOnBody(selector) {
    const modal = document.querySelector(selector);
    if (modal && modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  function ensureManagedModalsOnBody() {
    managedModalIds.forEach((selector) => ensureModalOnBody(selector));
  }

  function normalizeBackdropStack() {
    const backdrops = Array.from(document.querySelectorAll(".modal-backdrop"));
    if (!backdrops.length) return;
    backdrops.slice(0, -1).forEach((node) => {
      if (node && node.parentNode) {
        node.parentNode.removeChild(node);
      }
    });
    const latest = backdrops[backdrops.length - 1];
    if (latest) {
      latest.style.zIndex = "1040";
    }
  }

  function normalizeBodyModalClass() {
    if (document && document.body) {
      document.body.classList.remove("evidence-modal-open");
      document.body.classList.remove("settings-modal-open");
      if (!document.querySelector(".modal.show")) {
        document.querySelectorAll(".modal-backdrop").forEach((node) => {
          if (node && node.parentNode) {
            node.parentNode.removeChild(node);
          }
        });
        document.body.classList.remove("modal-open");
        document.body.style.removeProperty("padding-right");
      }
    }
  }

  function showActionModal() {
    if (window.jQuery) {
      ensureModalOnBody(actionModalId);
      window.jQuery(actionModalId).modal("show");
    }
  }

  function openActionModal(id, action, source = "table") {
    if (!actionTitle || !actionId || !actionType || !actionReason || !actionComment || !actionHint || !actionSource) return;
    const actionCn = i18n.toCnAction(action, action);
    actionTitle.textContent = `${actionCn}确认`;
    actionId.value = String(id || "");
    actionType.value = String(action || "").toUpperCase();
    actionSource.value = source;
    setSelectValue(actionReason, "");
    markSelectInvalid(actionReason, document.getElementById("ledgerActionReasonHint"), true);
    if (typeof refreshActionReasonState === "function") refreshActionReasonState();
    actionComment.value = "";
    actionHint.textContent = action === "RETURN_TO_DRAFT" ? "打回补录必须填写补充说明。" : "请选择变更原因并确认提交。";

    // Avoid modal stacking conflict:
    // evidence modal sits later in DOM than action modal and can cover it.
    // Hide evidence first, then show action modal.
    if (source === "evidence" && window.jQuery) {
      const evModal = window.jQuery(evidenceModalId);
      if (evModal.length && evModal.hasClass("show")) {
        evModal.one("hidden.bs.modal", () => {
          showActionModal();
        });
        evModal.modal("hide");
        return;
      }
    }
    showActionModal();
  }

  async function submitSingleAction() {
    const id = Number(actionId?.value || 0);
    const action = text(actionType?.value, "").toUpperCase();
    const source = text(actionSource?.value, "table").toLowerCase();
    const changeReasonCode = text(getSelectValue(actionReason), "").toUpperCase();
    const comment = text(actionComment?.value, "");

    if (!id || !action) return;
    if (!changeReasonCode) {
      markSelectInvalid(actionReason, document.getElementById("ledgerActionReasonHint"), true);
      showMsg("warning", "请选择变更原因。");
      return;
    }
    markSelectInvalid(actionReason, document.getElementById("ledgerActionReasonHint"), false);
    if (action === "RETURN_TO_DRAFT" && !comment) {
      showMsg("warning", "打回补录必须填写补充说明。");
      return;
    }

    await executeAction({
      id,
      action,
      source,
      changeReasonCode,
      comment,
      disableNode: actionSubmit,
    });
  }

  async function executeAction({
    id,
    action,
    source = "table",
    changeReasonCode,
    comment = "",
    disableNode = null,
  }) {
    if (!id || !action || !changeReasonCode) return;
    if (disableNode) disableNode.disabled = true;
    try {
      debugLog("action-submit payload", {
        id,
        action,
        source,
        change_reason_code: changeReasonCode,
        comment,
      });
      const result = await apiJson(`/api/ledger/${encodeURIComponent(id)}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, change_reason_code: changeReasonCode, comment }),
      });
      updateTableRowState(id, result);
      showMsg("success", text(result.message, "操作已完成"));
      if (window.jQuery) {
        const modal = window.jQuery(actionModalId);
        if (modal.length && modal.hasClass("show")) {
          modal.modal("hide");
        }
      }
      if (source === "evidence") {
        await openEvidence(id);
      }
      window.setTimeout(() => window.location.reload(), 280);
    } catch (error) {
      if (isApiNotWired(error)) {
        openSandboxNotice(action, id, error.message);
      } else {
        showMsg("danger", `操作失败：${error.message}`);
      }
    } finally {
      if (disableNode) disableNode.disabled = false;
    }
  }

  function bindActionButtons() {
    document.addEventListener("click", (event) => {
      const actionBtn = event.target.closest(".js-action");
      if (!actionBtn) return;
      const id = Number(actionBtn.getAttribute("data-id") || 0);
      const action = text(actionBtn.getAttribute("data-action"), "").toUpperCase();
      if (!id || !action) return;
      openActionModal(id, action, "table");
    });

    if (actionSubmit) {
      actionSubmit.addEventListener("click", submitSingleAction);
    }
  }

  async function submitBatchReturn() {
    const ids = selectedIds();
    if (!ids.length) {
      showMsg("warning", "请先勾选记录。");
      return;
    }

    const reasonSelect = document.getElementById("batchReturnReason");
    const reason = text(reasonSelect?.value, "").toUpperCase();
    const comment = text(document.getElementById("batchReturnComment")?.value, "");
    if (!reason) {
      markSelectInvalid(reasonSelect, document.getElementById("batchReturnReasonHint"), true);
      showMsg("warning", "请选择变更原因。");
      return;
    }
    markSelectInvalid(reasonSelect, document.getElementById("batchReturnReasonHint"), false);
    if (!comment) {
      showMsg("warning", "批量打回说明不能为空。");
      return;
    }

    const batchReturnSubmit = document.getElementById("batchReturnSubmit");
    if (batchReturnSubmit) batchReturnSubmit.disabled = true;
    try {
      const result = await apiJson("/api/ledger/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "RETURN_TO_DRAFT",
          ids,
          change_reason_code: String(reason).trim().toUpperCase(),
          comment,
        }),
      });
      showMsg("success", `批量完成：成功 ${result.success_count} 条，失败 ${result.failed_count} 条`);
      if (window.jQuery) {
        window.jQuery("#batchReturnModal").modal("hide");
      }
      window.setTimeout(() => window.location.reload(), 280);
    } catch (error) {
      if (isApiNotWired(error)) {
        openSandboxNotice("BATCH_RETURN_TO_DRAFT", 0, error.message);
      } else {
        showMsg("danger", `批量失败：${error.message}`);
      }
    } finally {
      if (batchReturnSubmit) batchReturnSubmit.disabled = false;
    }
  }

  function bindBatchButtons() {
    const btnBatchReturn = document.getElementById("btnBatchReturn");
    if (btnBatchReturn) {
      btnBatchReturn.addEventListener("click", () => {
        const ids = selectedIds();
        if (!ids.length) {
          showMsg("warning", "请先勾选记录。");
          return;
        }
        const hint = document.getElementById("batchReturnHint");
        if (hint) {
          hint.textContent = `已选择 ${ids.length} 条单据，确认后将统一打回补录并写入审计日志。`;
        }
        const reason = document.getElementById("batchReturnReason");
        const comment = document.getElementById("batchReturnComment");
        if (reason) {
          setSelectValue(reason, "RETURN_FOR_COMPLETION");
          markSelectInvalid(reason, document.getElementById("batchReturnReasonHint"), false);
          if (typeof refreshBatchReturnReasonState === "function") refreshBatchReturnReasonState();
        }
        if (comment) comment.value = "";
        if (window.jQuery) {
          window.jQuery("#batchReturnModal").modal("show");
        }
      });
    }

    const btnBatchSupplement = document.getElementById("btnBatchSupplement");
    if (btnBatchSupplement) {
      btnBatchSupplement.addEventListener("click", () => {
        const ids = selectedIds();
        if (!ids.length) {
          showMsg("warning", "请先勾选记录。");
          return;
        }
        if (window.jQuery) {
          window.jQuery("#batchSupplementModal").modal("show");
        }
      });
    }

    const batchSupplementSubmit = document.getElementById("batchSupplementSubmit");
    if (batchSupplementSubmit) {
      batchSupplementSubmit.addEventListener("click", async () => {
        const ids = selectedIds();
        if (!ids.length) {
          showMsg("warning", "请先勾选记录。");
          return;
        }

        const amount = text(document.getElementById("batchSupplementAmount")?.value, "");
        const invoiceDate = text(document.getElementById("batchSupplementDate")?.value, "");
        const reasonSelect = document.getElementById("batchSupplementReason");
        const reason = text(reasonSelect?.value, "").toUpperCase();
        const comment = text(document.getElementById("batchSupplementComment")?.value, "");
        const postLedger = !!document.getElementById("batchSupplementPostLedger")?.checked;

        if (!reason) {
          markSelectInvalid(reasonSelect, document.getElementById("batchSupplementReasonHint"), true);
          showMsg("warning", "批量补录必须选择变更原因。");
          return;
        }
        markSelectInvalid(reasonSelect, document.getElementById("batchSupplementReasonHint"), false);
        if (!amount && !invoiceDate) {
          showMsg("warning", "请至少填写一个补录字段（金额或开票日期）。");
          return;
        }

        batchSupplementSubmit.disabled = true;
        try {
          const result = await apiJson("/api/ledger/batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: "SUPPLEMENT",
              ids,
              change_reason_code: reason,
              comment,
              post_ledger: postLedger,
              fields: {
                amount,
                invoice_date: invoiceDate,
              },
            }),
          });
          showMsg("success", `批量补录完成：成功 ${result.success_count} 条，失败 ${result.failed_count} 条`);
          if (window.jQuery) {
            window.jQuery("#batchSupplementModal").modal("hide");
          }
          window.setTimeout(() => window.location.reload(), 280);
        } catch (error) {
          if (isApiNotWired(error)) {
            openSandboxNotice("BATCH_SUPPLEMENT", 0, error.message);
          } else {
            showMsg("danger", `批量补录失败：${error.message}`);
          }
        } finally {
          batchSupplementSubmit.disabled = false;
        }
      });
    }

    const batchReturnSubmit = document.getElementById("batchReturnSubmit");
    if (batchReturnSubmit) {
      batchReturnSubmit.addEventListener("click", submitBatchReturn);
    }
  }

  function formatAmountNodes() {
    document.querySelectorAll(".js-amount").forEach((node) => {
      const raw = safeNumber(node?.getAttribute("data-amount") || node?.textContent);
      node.textContent = raw === null ? "—" : formatAmount(raw);
    });
    const kpiAmount = document.getElementById("kpiAmount");
    if (kpiAmount) {
      const kpiRaw = safeNumber(kpiAmount.getAttribute("data-amount"));
      kpiAmount.textContent = kpiRaw === null ? "¥0.00" : formatAmount(kpiRaw);
    }
  }

  function bindCopyButtons() {
    document.addEventListener("click", async (event) => {
      const copyBtn = event.target.closest(".js-copy-ref");
      if (!copyBtn) return;
      const ref = text(copyBtn.getAttribute("data-ref"), "");
      if (!ref) return;
      try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          await navigator.clipboard.writeText(ref);
        } else {
          const temp = document.createElement("textarea");
          temp.value = ref;
          document.body.appendChild(temp);
          temp.select();
          document.execCommand("copy");
          document.body.removeChild(temp);
        }
        showMsg("success", `已复制：${ref}`);
      } catch (error) {
        showMsg("danger", `复制失败：${error.message}`);
      }
    });
  }

  function setNodeText(id, value, fallback = "-") {
    const node = document.getElementById(id);
    if (!node) return;
    node.textContent = text(value, fallback);
  }

  function showOrHide(id, visible) {
    const node = document.getElementById(id);
    if (!node) return;
    node.classList.toggle("d-none", !visible);
  }

  function renderAuditTrail(rows) {
    const body = document.getElementById("evAuditBody");
    if (!body) return;
    const items = Array.isArray(rows) ? rows : [];
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="7" class="text-center text-muted">暂无</td></tr>';
      return;
    }

    body.innerHTML = items
      .map((item, idx) => {
        let beforeObj = item.before;
        let afterObj = item.after;
        try {
          if (typeof beforeObj === "string") beforeObj = JSON.parse(beforeObj);
        } catch (_err) {
          // ignore
        }
        try {
          if (typeof afterObj === "string") afterObj = JSON.parse(afterObj);
        } catch (_err) {
          // ignore
        }

        const rawBefore = JSON.stringify(beforeObj || {}, null, 2);
        const rawAfter = JSON.stringify(afterObj || {}, null, 2);
        const actionCode = text(item.action, "").toUpperCase();
        const actionCn = text(item.action_cn, i18n.toCnAction(item.action, "-"));
        const reasonCn = text(item.change_reason_code_cn, item.change_reason_code || "-");
        let actionTone = "info";
        if (actionCode.includes("APPROVE") || actionCode.includes("PASS")) actionTone = "success";
        else if (actionCode.includes("REJECT") || actionCode.includes("RETURN") || actionCode.includes("BLOCK")) actionTone = "danger";
        else if (actionCode.includes("PENDING") || actionCode.includes("SUBMIT")) actionTone = "warning";
        const actionHtml = `<span class="${badgePalette[actionTone] || badgePalette.info}">${escapeHtml(actionCn)}</span>`;
        const reasonHtml = `<span class="audit-reason-chip">${escapeHtml(reasonCn)}</span>`;
        let diffRows = [];
        let parseFailed = false;
        try {
          diffRows = computeDiff(beforeObj || {}, afterObj || {});
        } catch (_err) {
          parseFailed = true;
        }

        const remark = escapeHtml(text(item.source || item.comment || "-", "-"));
        const diffHtml = parseFailed
          ? '<div class="text-muted small">数据解析失败，点击查看原始数据</div>'
          : diffRows.length
              ? `
                <div class="table-responsive">
                  <table class="table table-sm table-bordered audit-diff-table mb-1">
                    <thead>
                      <tr>
                        <th style="width:140px;">字段名</th>
                        <th>修改前</th>
                        <th>修改后</th>
                        <th style="width:140px;">来源/备注</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${diffRows
                        .map(
                          (row) => `
                            <tr>
                              <td class="audit-field-name">${escapeHtml(row.label)}</td>
                              <td class="audit-before-value">${formatValue(row.key, row.before)}</td>
                              <td class="audit-after-value">${formatValue(row.key, row.after)}</td>
                              <td class="audit-remark">${remark}</td>
                            </tr>`
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
              : '<div class="text-muted small">无字段变更</div>';

        const rawId = `auditRaw${idx}`;
        return `
          <tr>
            <td class="audit-time">${escapeHtml(text(item.created_at, "-"))}</td>
            <td>${actionHtml}</td>
            <td class="audit-actor">${escapeHtml(text(item.actor_name, "-"))}</td>
            <td>${reasonHtml}</td>
            <td><code class="audit-ip">${escapeHtml(text(item.client_ip, "-"))}</code></td>
            <td><code class="audit-trace">${escapeHtml(text(item.trace_id, "-"))}</code></td>
            <td>
              ${diffHtml}
              <button class="btn btn-link btn-sm px-0 audit-raw-toggle" data-toggle="collapse" data-target="#${rawId}" aria-expanded="false">查看原始数据</button>
              <div class="collapse mt-2" id="${rawId}">
                <div class="audit-raw">
                  <div class="audit-raw-title">修改前</div>
                  <pre>${escapeHtml(rawBefore)}</pre>
                  <div class="audit-raw-title">修改后</div>
                  <pre>${escapeHtml(rawAfter)}</pre>
                </div>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  function renderInvoiceInfo(meta = {}, raw = {}) {
    const summary = document.getElementById("evInvoiceSummary");
    const empty = document.getElementById("evInvoiceEmpty");
    const preview = document.getElementById("evInvoicePreview");
    const badge = document.getElementById("evInvoiceStatusBadge");

    if (!summary || !preview) return;

    const hasData =
      text(meta.invoice_code, "") ||
      text(meta.invoice_number, "") ||
      text(meta.total_amount || meta.amount, "") ||
      text(meta.tax_amount, "") ||
      text(meta.seller_name, "") ||
      text(meta.buyer_name, "") ||
      text(meta.preview_url, "") ||
      text(raw.filename, "");

    const setText = (id, value, fallback = "-") => {
      const node = document.getElementById(id);
      if (node) node.textContent = text(value, fallback);
    };

    if (!hasData) {
      summary.classList.remove("d-none");
      if (empty) empty.classList.remove("d-none");
      preview.innerHTML = '<div class="empty-state">暂无预览</div>';
      if (badge) {
        badge.className = badgePalette.neutral;
        badge.textContent = "待验真";
      }
      setText("evInvoiceVerify", "-", "-");
      return;
    }

    if (empty) empty.classList.add("d-none");
    summary.classList.remove("d-none");

    setText("evInvoiceCode", meta.invoice_code || raw.invoice_code, "-");
    setText("evInvoiceNo", meta.invoice_number || raw.invoice_number, "-");
    setText("evInvoiceDateText", meta.invoice_date || raw.invoice_date, "-");
    setText("evSellerName", meta.seller_name || meta.vendor || raw.seller_name || raw.vendor, "-");
    setText("evBuyerName", meta.buyer_name || raw.buyer_name, "-");
    setText("evInvoiceTotal", formatAmount(meta.total_amount || meta.amount || raw.amount));
    setText("evInvoiceTax", formatAmount(meta.tax_amount || raw.tax_amount));

    const verifyStatusText = text(meta.verify_status_cn || meta.verify_status || raw.verify_status, "-");
    setText("evInvoiceVerify", verifyStatusText, "-");

    if (badge) {
      const statusCode = text(meta.verify_status || raw.verify_status, "").toUpperCase();
      let tone = "neutral";
      if (["VALID", "SUCCESS", "PASS"].includes(statusCode)) tone = "success";
      else if (["INVALID", "FAIL", "FAILED"].includes(statusCode)) tone = "danger";
      else if (["PENDING", "PROCESSING"].includes(statusCode)) tone = "warning";
      badge.className = badgePalette[tone] || badgePalette.neutral;
      badge.textContent = verifyStatusText || "待验真";
    }

    const previewUrl = text(meta.preview_url, "") || (raw.filename ? `/uploads/${encodeURIComponent(raw.filename)}` : "");
    const sourceName = text(meta.filename || raw.filename, "");
    const explicitType = text(meta.file_type || raw.file_type, "").replace(/^\./, "").toLowerCase();
    const inferredTypeFromName = (sourceName.match(/\.([a-zA-Z0-9]+)$/) || [])[1] || "";
    const inferredTypeFromUrl = (previewUrl.match(/\.([a-zA-Z0-9]+)(?:\?|$)/) || [])[1] || "";
    const fileType = (explicitType || inferredTypeFromName || inferredTypeFromUrl || "").toLowerCase();
    const previewAvailable = (() => {
      const flag = meta.preview_available;
      if (flag === undefined || flag === null || flag === "") return true;
      if (typeof flag === "boolean") return flag;
      return !["0", "false", "no", "off"].includes(String(flag).trim().toLowerCase());
    })();
    const isImage = ["jpg", "jpeg", "png", "bmp", "gif", "webp", "tif", "tiff", "svg", "avif"].includes(fileType);
    const isPdf = fileType === "pdf";

    if (!previewUrl) {
      preview.innerHTML = '<div class="empty-state">暂无预览</div>';
      return;
    }

    if (!previewAvailable) {
      preview.innerHTML = `
        <div class="invoice-file-card is-missing">
          <div class="invoice-file-icon"><i class="fas fa-exclamation-triangle"></i></div>
          <div class="invoice-file-title">附件文件缺失</div>
          <div class="invoice-file-hint">${escapeHtml(sourceName || "未找到附件文件，请联系管理员补传。")}</div>
          <button class="btn btn-sm btn-secondary evidence-open-btn" type="button" disabled>附件不可用</button>
        </div>
      `;
      return;
    }

    if (isImage) {
      preview.innerHTML = `
        <img src="${previewUrl}" alt="票据预览" class="invoice-thumb">
        <div class="preview-actions">
          <a class="btn btn-sm btn-primary evidence-open-btn" href="${previewUrl}" target="_blank" rel="noopener"><i class="fas fa-external-link-alt mr-1"></i>查看原件</a>
        </div>
      `;
      return;
    }

    const icon = isPdf ? '<i class="far fa-file-pdf"></i>' : '<i class="far fa-file-alt"></i>';
    const fileLabel = fileType ? `${fileType.toUpperCase()} 文件` : "附件文件";
    preview.innerHTML = `
      <div class="invoice-file-card">
        <div class="invoice-file-icon">${icon}</div>
        <div class="invoice-file-title">${escapeHtml(fileLabel)}</div>
        <div class="invoice-file-hint">${escapeHtml(sourceName || "点击在新窗口查看附件原件")}</div>
        <div class="preview-actions justify-content-center">
          <a class="btn btn-sm btn-primary evidence-open-btn" href="${previewUrl}" target="_blank" rel="noopener"><i class="fas fa-external-link-alt mr-1"></i>打开附件</a>
        </div>
      </div>
    `;
  }

  function renderEvidence(payload) {
    const evidence = (payload && payload.evidence) || {};
    const raw = evidence.raw_voucher || {};
    const st = evidence.structured_data || {};
    const verify = evidence.verification_receipt || {};
    const rule = evidence.rule_evidence || {};
    const approval = evidence.approval_chain || {};

    setNodeText("evFilename", raw.filename, "-");
    setNodeText("evFileType", raw.file_type, "-");
    setNodeText("evPageCount", raw.page_count, "-");
    setNodeText("evUploadedAt", raw.uploaded_at, "-");
    setNodeText("evUploadedBy", raw.uploaded_by, "-");
    const hasHash = text(raw.file_hash, "-") !== "-";
    setNodeText("evFileHash", hasHash ? raw.file_hash : "");
    showOrHide("evFileHashRow", hasHash);
    setBadge("evRecordStateBadge", "record_state", payload.record_state || st.record_state);
    setBadge("evApprovalStatusBadge", "approval_status", approval.approval_status || st.approval_status);
    setNodeText("evAmountKpi", formatAmount(st.amount));
    setNodeText("evInvoiceDateKpi", formatDate(st.invoice_date));
    setNodeText("evApplicantKpi", st.applicant, "-");
    setNodeText("evDepartmentKpi", st.department, "-");
    const gotoBtn = document.getElementById("evGotoApproval");
    if (gotoBtn) {
      const ref = text(st.reference_no, "");
      const approvalStatus = text(approval.approval_status, "").toUpperCase();
      const showApproval = ref && !["APPROVED", "DONE"].includes(approvalStatus);
      gotoBtn.classList.toggle("d-none", !showApproval);
      gotoBtn.setAttribute("href", showApproval ? `/approval_center?ref=${encodeURIComponent(ref)}` : "#");
    }

    const amountNode = document.getElementById("evAmount");
    const dateNode = document.getElementById("evInvoiceDate");
    const applicantNode = document.getElementById("evApplicant");
    const departmentNode = document.getElementById("evDepartment");
    if (amountNode) amountNode.value = text(st.amount, "");
    if (dateNode) dateNode.value = text(st.invoice_date, "");
    if (applicantNode) applicantNode.value = text(st.applicant, "");
    if (departmentNode) departmentNode.value = text(st.department, "");

    setNodeText("evVerifyStatus", verify.verify_status_cn || i18n.toCnVerifyStatus(verify.verify_status), "暂无");
    setNodeText("evCheckedAt", verify.checked_at, "暂无");
    setNodeText("evCheckCount", verify.check_count, "0");
    setNodeText("evRequestId", verify.request_id, "暂无");

    setNodeText("evRuleName", rule.rule_name, "-");
    setNodeText("evRuleVersion", rule.rule_version, "-");
    setNodeText("evThreshold", rule.threshold, "-");
    setNodeText("evActual", rule.actual, "-");
    setNodeText("evRatio", rule.ratio, "-");
    setNodeText("evSuggestion", rule.suggestion, "-");
    setNodeText("evRuleSummary", rule.summary, "-");

    setNodeText("evApprovalStage", approval.approval_stage_cn || i18n.toCnApprovalStage(approval.approval_stage), "暂无");
    setNodeText("evApprovalStatus", approval.approval_status_cn || i18n.toCnApprovalStatus(approval.approval_status), "暂无");
    setNodeText("evFirstApprover", approval.first_approver, "暂无");
    setNodeText("evFirstTime", approval.first_approved_at, "暂无");
    setNodeText("evSecondApprover", approval.second_approver, "暂无");
    setNodeText("evSecondTime", approval.second_approved_at, "暂无");

    renderInvoiceInfo(evidence.invoice_meta || {}, raw);
    renderAuditTrail(evidence.audit_trail || []);
  }

  async function openEvidence(invoiceId) {
    const payload = await apiJson(`/api/ledger/${encodeURIComponent(invoiceId)}/evidence`);
    const evidenceInvoiceId = document.getElementById("evidenceInvoiceId");
    const reasonNode = document.getElementById("evStructuredReason");
    if (evidenceInvoiceId) evidenceInvoiceId.value = String(invoiceId);
    const auditChainLink = document.getElementById("evAuditChainLink");
    if (auditChainLink) {
      auditChainLink.href = "/audit_chain/invoice/" + invoiceId;
      auditChainLink.style.display = invoiceId ? "inline-block" : "none";
    }
    if (reasonNode) {
      const preset = (payload && payload.evidence && payload.evidence.structured_data && payload.evidence.structured_data.change_reason_code) || "";
      setSelectValue(reasonNode, preset);
      markSelectInvalid(reasonNode, document.getElementById("evStructuredReasonHint"), !getSelectValue(reasonNode));
      if (typeof refreshStructuredReasonState === "function") refreshStructuredReasonState();
    }
    renderEvidence(payload);
    if (window.jQuery) {
      ensureModalOnBody(evidenceModalId);
      window.jQuery("#evidenceModal").modal("show");
    }
  }

  function bindEvidenceOpen() {
    document.addEventListener("click", async (event) => {
      const evBtn = event.target.closest(".js-evidence");
      if (!evBtn) return;
      const id = Number(evBtn.getAttribute("data-id") || 0);
      if (!id) {
        showMsg("warning", "单据标识缺失，无法打开详情。");
        return;
      }
      try {
        await openEvidence(id);
      } catch (error) {
        if (isApiNotWired(error)) {
          openSandboxNotice("EVIDENCE_CENTER", id, error.message);
        } else {
          showMsg("danger", `加载证据中心失败：${error.message}`);
        }
      }
    });
  }

  async function autoOpenEvidenceFromQuery() {
    let invoiceId = 0;
    try {
      const params = new URLSearchParams(window.location.search || "");
      const parsed = Number(params.get("open_evidence") || 0);
      invoiceId = Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : 0;
    } catch (_) {
      invoiceId = 0;
    }
    if (!invoiceId) return;

    try {
      await openEvidence(invoiceId);
    } catch (error) {
      if (isApiNotWired(error)) {
        openSandboxNotice("EVIDENCE_CENTER", invoiceId, error.message);
      } else {
        showMsg("warning", `未能自动打开单据详情：${error.message}`);
      }
    }
  }

  function bindEvidenceActions() {
    const evStructuredSave = document.getElementById("evStructuredSave");
    if (!evStructuredSave) return;

    evStructuredSave.addEventListener("click", async () => {
      const invoiceId = Number(document.getElementById("evidenceInvoiceId")?.value || 0);
      if (!invoiceId) {
        showMsg("warning", "未找到当前单据。请重新打开证据中心。");
        return;
      }

      const reasonSelect = document.getElementById("evStructuredReason");
      const reason = text(getSelectValue(reasonSelect), "").toUpperCase();
      if (!reason) {
        markSelectInvalid(reasonSelect, document.getElementById("evStructuredReasonHint"), true);
        showMsg("warning", "要素校正必须选择变更原因。");
        return;
      }
      markSelectInvalid(reasonSelect, document.getElementById("evStructuredReasonHint"), false);

      const fields = {
        amount: text(document.getElementById("evAmount")?.value, ""),
        invoice_date: text(document.getElementById("evInvoiceDate")?.value, ""),
        applicant: text(document.getElementById("evApplicant")?.value, ""),
        department: text(document.getElementById("evDepartment")?.value, ""),
      };

      evStructuredSave.disabled = true;
      try {
        debugLog("structured-save payload", {
          invoiceId,
          change_reason_code: reason,
          fields,
        });
        const result = await apiJson(`/api/ledger/${encodeURIComponent(invoiceId)}/structured`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fields, change_reason_code: reason }),
        });
        updateTableRowState(invoiceId, result);
        showMsg("success", "凭证要素已保存并写入审计日志。");
        await openEvidence(invoiceId);
      } catch (error) {
        if (isApiNotWired(error)) {
          openSandboxNotice("STRUCTURED_EDIT", invoiceId, error.message);
        } else {
          showMsg("danger", `保存失败：${error.message}`);
        }
      } finally {
        evStructuredSave.disabled = false;
      }
    });
  }

  const refreshActionReasonState = setupRequiredSelect("ledgerActionReason", "ledgerActionReasonHint", "ledgerActionSubmit");
  const refreshBatchSupplementReasonState = setupRequiredSelect("batchSupplementReason", "batchSupplementReasonHint", "batchSupplementSubmit");
  const refreshBatchReturnReasonState = setupRequiredSelect("batchReturnReason", "batchReturnReasonHint", "batchReturnSubmit");
  const refreshStructuredReasonState = setupRequiredSelect("evStructuredReason", "evStructuredReasonHint", "evStructuredSave");

  bindPageSize();
  bindSelectAll();
  bindEvidenceOpen();
  bindEvidenceActions();
  bindActionButtons();
  bindBatchButtons();
  void autoOpenEvidenceFromQuery();
  bindCopyButtons();
  formatAmountNodes();
  ensureManagedModalsOnBody();
  normalizeBodyModalClass();
  if (window.jQuery) {
    window.jQuery(document).on("show.bs.modal", modalClassWhitelist, (event) => {
      const id = event && event.target && event.target.id ? `#${event.target.id}` : "";
      if (id) {
        ensureModalOnBody(id);
      }
      normalizeBackdropStack();
    });
    window.jQuery(document).on("shown.bs.modal", modalClassWhitelist, normalizeBackdropStack);
    window.jQuery(document).on("shown.bs.modal hidden.bs.modal", modalClassWhitelist, normalizeBodyModalClass);
  }
})();
