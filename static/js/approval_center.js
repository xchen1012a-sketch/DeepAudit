(() => {
  const root = document.getElementById("approval-workbench");
  const modalEl = document.getElementById("approvalActionModal");
  if (!root || !modalEl || !window.jQuery) return;

  const initNode = document.getElementById("approvalWorkbenchInit");
  let initPayload = {};
  if (initNode) {
    try {
      initPayload = JSON.parse(initNode.textContent || "{}");
    } catch (_) {
      initPayload = {};
    }
  }

  const identities = new Set(
    (Array.isArray(initPayload.identities) ? initPayload.identities : [])
      .map((item) => String(item ?? "").trim())
      .filter(Boolean),
  );

  const currentOperator =
    text(root.getAttribute("data-current-operator")) || "当前操作人";
  const modal = window.jQuery(modalEl);

  const refs = {
    list: document.getElementById("approvalList"),
    empty: document.getElementById("approvalEmpty"),
    feedback: document.getElementById("approvalFeedback"),
    riskFilter: document.getElementById("riskFilter"),
    statusFilter: document.getElementById("statusFilter"),
    keywordFilter: document.getElementById("keywordFilter"),
    filterToggle: document.getElementById("filterToggle"),
    filtersPanel: document.getElementById("filtersPanel"),
    kpiPending: document.getElementById("kpiPending"),
    kpiHigh: document.getElementById("kpiHigh"),
    kpiSla: document.getElementById("kpiSla"),
    kpiOver: document.getElementById("kpiOver"),
    rowId: document.getElementById("workRowId"),
    contextHint: document.getElementById("workContextHint"),
    actionType: document.getElementById("workActionType"),
    reasonCode: document.getElementById("workReasonCode"),
    reasonError: document.getElementById("workReasonError"),
    assignWrap: document.getElementById("workAssignWrap"),
    assignTo: document.getElementById("workAssignTo"),
    assignError: document.getElementById("workAssignError"),
    needSupplement: document.getElementById("workNeedSupplement"),
    reasonNote: document.getElementById("workReasonNote"),
    actionError: document.getElementById("workActionError"),
    latestProgress: document.getElementById("workLatestProgress"),
    trailList: document.getElementById("workTrailList"),
    trailToggle: document.getElementById("workTrailToggle"),
    submitBtn: document.getElementById("workSubmitBtn"),
    inboxTabs: Array.from(document.querySelectorAll(".js-inbox-tab")),
  };

  const STATUS_TEXT = {
    PENDING: "待处理",
    APPROVED: "已通过",
    REJECTED: "已驳回",
    RETURNED: "已退回",
  };
  const STAGE_TEXT = { L1: "一级审批", L2: "二级复核", DONE: "流程完成" };
  const RISK_TEXT = { HIGH: "高风险", MEDIUM: "中风险", LOW: "低风险" };
  const ACTION_TEXT = { APPROVE: "通过", RETURN: "退回", ASSIGN: "转派" };
  const STEP_CODES = new Set(["A", "B", "C", "END"]);

  let inbox = "my_pending";
  let activeItem = null;
  let trailExpanded = false;
  let stepFilter = "";

  const trailStore = new Map();
  const riskCaseByInvoice = new Map();

  function text(v) {
    return String(v ?? "").trim();
  }
  function normalize(v) {
    return text(v).toUpperCase();
  }
  function escapeHtml(v) {
    return text(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function display(v, fb) {
    return text(v) || (fb ?? "-");
  }
  function stageCn(c) {
    return STAGE_TEXT[normalize(c)] || "待处理";
  }
  function statusCn(c) {
    return STATUS_TEXT[normalize(c)] || "待处理";
  }
  function riskCn(c) {
    return RISK_TEXT[normalize(c)] || "低风险";
  }
  function actionCn(c) {
    return ACTION_TEXT[normalize(c)] || "已更新";
  }

  function nowMinute() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function csrfToken() {
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m && text(m.content)) return text(m.content);
    const h = document.querySelector('input[name="csrf_token"]');
    return h ? text(h.value) : "";
  }

  function items() {
    return Array.from(refs.list.querySelectorAll(".aw-item[data-id]"));
  }

  function getSelectValue(node) {
    if (!node) return "";
    if (node.tomselect && typeof node.tomselect.getValue === "function")
      return text(node.tomselect.getValue());
    return text(node.value);
  }

  function setSelectValue(node, v) {
    if (!node) return;
    const val = text(v);
    if (node.tomselect && typeof node.tomselect.setValue === "function") {
      node.tomselect.setValue(val, true);
      return;
    }
    node.value = val;
  }

  /* ── Feedback ── */
  function showFeedback(tone, msg) {
    const t = text(tone) || "info";
    const m = text(msg) || "操作完成";
    refs.feedback.className = `aw-feedback is-visible tone-${t}`;
    refs.feedback.innerHTML = `<i class="ri-${t === "success" ? "checkbox-circle" : t === "danger" ? "close-circle" : t === "warning" ? "error-warning" : "information"}-line"></i><span>${m}</span>`;
    clearTimeout(showFeedback._t);
    showFeedback._t = setTimeout(() => {
      refs.feedback.classList.remove("is-visible");
    }, 3200);
  }

  function showModalError(msg) {
    const m = text(msg);
    if (!m) {
      refs.actionError.textContent = "";
      refs.actionError.classList.add("d-none");
      return;
    }
    refs.actionError.textContent = m;
    refs.actionError.classList.remove("d-none");
  }

  function setReasonInvalid(f) {
    refs.reasonCode.classList.toggle("is-invalid", !!f);
    refs.reasonError.classList.toggle("d-none", !f);
  }
  function setAssignInvalid(f) {
    refs.assignTo.classList.toggle("is-invalid", !!f);
    refs.assignError.classList.toggle("d-none", !f);
  }

  /* ── Identity helpers ── */
  function queueMatches(el) {
    const o = text(el.getAttribute("data-owner"));
    return o ? identities.has(o) : false;
  }
  function processedByMe(el) {
    return (
      identities.has(text(el.getAttribute("data-first"))) ||
      identities.has(text(el.getAttribute("data-second")))
    );
  }
  function matchesKeyword(el, kw) {
    if (!kw) return true;
    return [
      el.getAttribute("data-reference"),
      el.getAttribute("data-applicant"),
      el.getAttribute("data-dept"),
      el.getAttribute("data-vendor"),
    ]
      .map((v) => text(v).toLowerCase())
      .join(" ")
      .includes(kw);
  }

  /* ── Filter logic ── */
  function isVisible(el) {
    const st = normalize(el.getAttribute("data-status"));
    if (inbox === "my_pending") {
      if (st !== "PENDING" || !queueMatches(el)) return false;
    } else if (inbox === "all_pending") {
      if (st !== "PENDING") return false;
    } else if (inbox === "my_processed") {
      if (!processedByMe(el)) return false;
    }
    const rf = normalize(refs.riskFilter.value);
    if (rf && normalize(el.getAttribute("data-risk")) !== rf) return false;
    const sf = normalize(refs.statusFilter.value);
    if (sf && st !== sf) return false;
    if (stepFilter && normalize(el.getAttribute("data-step")) !== stepFilter)
      return false;
    const kw = text(refs.keywordFilter.value).toLowerCase();
    return matchesKeyword(el, kw);
  }

  function applyFilters() {
    let visCount = 0;
    items().forEach((el) => {
      const vis = isVisible(el);
      el.classList.toggle("d-none", !vis);
      if (vis) visCount++;
    });
    refs.empty.classList.toggle("d-none", visCount > 0);
  }

  function recalcMetrics() {
    let pending = 0,
      high = 0,
      sla4 = 0,
      over = 0;
    items().forEach((el) => {
      if (normalize(el.getAttribute("data-status")) !== "PENDING") return;
      pending++;
      if (normalize(el.getAttribute("data-risk")) === "HIGH") high++;
      const s = Number(el.getAttribute("data-sla") || 0);
      if (Number.isFinite(s) && s <= 240) sla4++;
      if (
        (Number.isFinite(s) && s < 0) ||
        normalize(el.getAttribute("data-over")) === "1"
      )
        over++;
    });
    refs.kpiPending.textContent = String(pending);
    refs.kpiHigh.textContent = String(high);
    refs.kpiSla.textContent = String(sla4);
    refs.kpiOver.textContent = String(over);
  }

  /* ── Card rendering ── */
  function renderItem(el) {
    const st = normalize(el.getAttribute("data-status"));
    const sg = normalize(el.getAttribute("data-stage"));
    const rk = normalize(el.getAttribute("data-risk"));
    const scoreRaw = text(el.getAttribute("data-risk-score"));
    const ruleCount = Number(el.getAttribute("data-rule-count") || 0);

    el.className = el.className
      .replace(/risk-(high|medium|low)/g, "")
      .trim();
    el.classList.add(`risk-${rk.toLowerCase()}`);

    const statusBadge = el.querySelector(".js-status-badge");
    if (statusBadge) {
      statusBadge.className = `aw-status-badge st-${st.toLowerCase()} js-status-badge`;
      statusBadge.textContent = statusCn(st);
    }

    const stageNode = el.querySelector(".js-stage");
    if (stageNode) stageNode.textContent = stageCn(sg);

    const ownerNode = el.querySelector(".js-owner");
    if (ownerNode)
      ownerNode.textContent = display(el.getAttribute("data-owner"));

    const ruleNode = el.querySelector(".js-rule-count");
    if (ruleNode)
      ruleNode.textContent =
        Number.isFinite(ruleCount) && ruleCount > 0
          ? String(ruleCount)
          : "-";

    const progNode = el.querySelector(".js-progress");
    if (progNode)
      progNode.textContent = display(
        el.getAttribute("data-latest-progress"),
      );

    const chipNode = el.querySelector(".aw-chip");
    if (chipNode) {
      chipNode.className = `aw-chip chip-${rk.toLowerCase()}`;
      chipNode.textContent =
        riskCn(rk) + (scoreRaw ? ` (${scoreRaw})` : "");
    }

    updateLinks(el);

    const quickBtn = el.querySelector(".aw-action-quick");
    if (quickBtn) {
      if (st === "PENDING") {
        quickBtn.classList.remove("d-none");
      } else {
        quickBtn.classList.add("d-none");
      }
    }
  }

  function updateLinks(el) {
    const id = Number(el.getAttribute("data-id") || 0);
    const ref = text(
      el.getAttribute("data-reference") || el.getAttribute("data-id"),
    );
    const trace = text(el.getAttribute("data-trace"));
    const caseId = Number(el.getAttribute("data-case-id") || 0);
    const st = normalize(el.getAttribute("data-status"));

    const upLink = el.querySelector(".js-link-upload");
    if (upLink) {
      let href = `/invoices_page?tab=ledger&open_evidence=${encodeURIComponent(id || 0)}`;
      if (ref) href += `&reference_no=${encodeURIComponent(ref)}`;
      upLink.setAttribute("href", href);
    }

    const riskLink = el.querySelector(".js-link-risk");
    if (riskLink) {
      if (caseId > 0) riskLink.setAttribute("href", `/risk/cases/${encodeURIComponent(caseId)}/detail`);
      else if (trace) riskLink.setAttribute("href", `/api/ai/ledger/${encodeURIComponent(trace)}`);
      else riskLink.setAttribute("href", "/risk-center");
    }

    const evLink = el.querySelector(".js-link-evidence");
    if (evLink) {
      evLink.setAttribute(
        "href",
        `/invoices_page?tab=ledger&reference_no=${encodeURIComponent(ref || String(id || ""))}`,
      );
      evLink.classList.toggle("is-disabled", st !== "APPROVED");
    }
  }

  /* ── Trail ── */
  function ensureTrail(el) {
    const rowId = text(el.getAttribute("data-id"));
    if (!rowId || trailStore.has(rowId)) return;
    trailStore.set(rowId, [
      {
        action: "提交",
        operator: display(el.getAttribute("data-applicant")),
        reason_code: "-",
        reason_note: display(el.getAttribute("data-latest-progress")),
        time: display(el.getAttribute("data-submitted")),
      },
    ]);
  }

  function appendTrail(el, entry) {
    const rowId = text(el.getAttribute("data-id"));
    if (!rowId) return;
    ensureTrail(el);
    const list = trailStore.get(rowId) || [];
    list.unshift(entry);
    trailStore.set(rowId, list);
  }

  function renderTrail(el) {
    if (!el) {
      refs.trailList.innerHTML = "";
      refs.trailToggle.classList.add("d-none");
      return;
    }
    ensureTrail(el);
    const rowId = text(el.getAttribute("data-id"));
    const entries = trailStore.get(rowId) || [];
    const visible = trailExpanded ? entries : entries.slice(0, 5);
    refs.trailList.innerHTML = visible
      .map(
        (e) =>
          `<li><div class="trail-main">${escapeHtml(display(e.action))} · ${escapeHtml(display(e.time))}</div>` +
          `<div class="trail-line">操作者：${escapeHtml(display(e.operator))}</div>` +
          `<div class="trail-line">原因码：${escapeHtml(display(e.reason_code))}</div>` +
          `<div class="trail-line">说明：${escapeHtml(display(e.reason_note))}</div></li>`,
      )
      .join("");
    if (entries.length > 5) {
      refs.trailToggle.classList.remove("d-none");
      refs.trailToggle.textContent = trailExpanded ? "收起" : "展开全部";
    } else {
      refs.trailToggle.classList.add("d-none");
    }
  }

  /* ── Modal helpers ── */
  function syncContextHint() {
    if (!activeItem) return;
    const ac = normalize(refs.actionType.value);
    const ref = display(activeItem.getAttribute("data-reference"));
    const stg = stageCn(activeItem.getAttribute("data-stage"));
    const ow = display(activeItem.getAttribute("data-owner"));
    let h = `单据 ${ref} · ${stg} · 处理人 ${ow}`;
    if (ac === "APPROVE") h += " — 通过后按风险等级自动推进。";
    else if (ac === "RETURN") h += " — 退回将结束当前审批。";
    else if (ac === "ASSIGN") h += " — 转派仅调整处理人，状态不变。";
    refs.contextHint.textContent = h;
  }

  function setAssignVisible(vis) {
    refs.assignWrap.classList.toggle("d-none", !vis);
    if (!vis) {
      refs.assignTo.value = "";
      setAssignInvalid(false);
    }
  }

  function clearActionForm() {
    setSelectValue(refs.reasonCode, "");
    refs.reasonNote.value = "";
    refs.needSupplement.checked = false;
    refs.assignTo.value = "";
    setReasonInvalid(false);
    setAssignInvalid(false);
    showModalError("");
  }

  function openWorkbench(el) {
    activeItem = el;
    trailExpanded = false;
    refs.rowId.value = text(el.getAttribute("data-id"));
    refs.actionType.value = "APPROVE";
    clearActionForm();
    setAssignVisible(false);
    refs.latestProgress.textContent = display(
      el.getAttribute("data-latest-progress"),
    );
    syncContextHint();
    renderTrail(el);
    if (typeof window.initEnterpriseSelect === "function")
      window.initEnterpriseSelect(modalEl);
    modal.modal("show");
  }

  function buildComment(ac, el, note, supp) {
    let n = text(note);
    const rk = normalize(el.getAttribute("data-risk"));
    const sg = normalize(el.getAttribute("data-stage"));
    if (!n) {
      if (ac === "RETURN") n = "审批工作台退回";
      else if (ac === "ASSIGN") n = "审批工作台转派";
      else if (ac === "APPROVE" && rk === "HIGH" && sg === "L2")
        n = "高风险二级复核通过";
    }
    if (supp) {
      if (n) {
        if (!n.includes("补充材料")) n = `${n}（需补充材料）`;
      } else n = "需补充材料";
    }
    return n;
  }

  async function requestJson(url, payload) {
    const tok = csrfToken();
    const body = { ...(payload || {}), csrf_token: tok };
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Api-Version": "APPROVAL_API_V2",
        "X-CSRF-Token": tok,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data || data.ok !== true)
      throw new Error(
        text(data.msg) || text(data.message) || `HTTP ${res.status}`,
      );
    return data;
  }

  function progressActionText(ac, nextStage, nextStatus) {
    if (
      normalize(ac) === "APPROVE" &&
      nextStage === "L2" &&
      nextStatus === "PENDING"
    )
      return "通过并提交复核";
    return actionCn(ac);
  }

  function applyActionResult(el, ac, reasonCode, noteRaw, supp, result) {
    const ns =
      normalize(result.status) ||
      normalize(el.getAttribute("data-status")) ||
      "PENDING";
    const nsg =
      normalize(result.stage) ||
      normalize(el.getAttribute("data-stage")) ||
      "L1";
    const no = text(result.queue_owner_id);
    const acText = progressActionText(ac, nsg, ns);
    const t = nowMinute();
    const prog = `${acText} · ${t}`;

    el.setAttribute("data-status", ns);
    el.setAttribute("data-stage", nsg);
    el.setAttribute("data-owner", no || "-");
    el.setAttribute("data-latest-progress", prog);
    if (ns !== "PENDING") el.setAttribute("data-step", "END");
    else if (nsg === "L2") el.setAttribute("data-step", "C");

    renderItem(el);
    appendTrail(el, {
      action: acText,
      operator: currentOperator,
      reason_code: reasonCode,
      reason_note: buildComment(ac, el, noteRaw, supp) || "-",
      time: t,
    });

    if (activeItem === el) {
      refs.latestProgress.textContent = prog;
      renderTrail(el);
      syncContextHint();
    }
    recalcMetrics();
    applyFilters();
  }

  /* ── Preload risk case links ── */
  async function preloadRiskCases() {
    try {
      const res = await fetch("/api/risk/cases?limit=1000", {
        headers: { Accept: "application/json" },
      });
      const p = await res.json().catch(() => ({}));
      if (!res.ok || !p || p.ok !== true || !Array.isArray(p.cases)) return;
      p.cases.forEach((c) => {
        const iid = Number(c.invoice_id || 0);
        const cid = Number(c.id || 0);
        if (iid > 0 && cid > 0 && !riskCaseByInvoice.has(iid))
          riskCaseByInvoice.set(iid, cid);
      });
      items().forEach((el) => {
        const iid = Number(el.getAttribute("data-id") || 0);
        const cid = riskCaseByInvoice.get(iid);
        if (cid) el.setAttribute("data-case-id", String(cid));
        updateLinks(el);
      });
    } catch (_) {
      /* link enhancement is non-critical */
    }
  }

  function applyReferenceDeepLink() {
    const p = new URLSearchParams(window.location.search);
    const ref = text(p.get("ref"));
    if (!ref) return;
    refs.keywordFilter.value = ref;
    applyFilters();
    const target = items().find(
      (el) => text(el.getAttribute("data-reference")) === ref,
    );
    if (!target) return;
    target.classList.add("is-highlighted");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function applyStepDeepLink() {
    const p = new URLSearchParams(window.location.search);
    const raw = normalize(p.get("step"));
    if (!STEP_CODES.has(raw)) {
      stepFilter = "";
      return;
    }
    stepFilter = raw;
    inbox = "all_pending";
    refs.inboxTabs.forEach((btn) => {
      btn.classList.toggle(
        "is-active",
        text(btn.getAttribute("data-inbox")) === "all_pending",
      );
    });
    showFeedback("info", `已按流程节点 ${raw} 过滤审批队列。`);
  }

  /* ── Event bindings ── */

  refs.inboxTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      inbox = text(btn.getAttribute("data-inbox")) || "my_pending";
      refs.inboxTabs.forEach((n) => n.classList.remove("is-active"));
      btn.classList.add("is-active");
      applyFilters();
    });
  });

  refs.filterToggle.addEventListener("click", () => {
    const open = refs.filtersPanel.classList.toggle("is-visible");
    refs.filterToggle.classList.toggle("is-open", open);
  });

  refs.riskFilter.addEventListener("change", applyFilters);
  refs.statusFilter.addEventListener("change", applyFilters);
  refs.keywordFilter.addEventListener("input", applyFilters);

  refs.actionType.addEventListener("change", () => {
    setAssignVisible(normalize(refs.actionType.value) === "ASSIGN");
    showModalError("");
    syncContextHint();
  });

  refs.reasonCode.addEventListener("change", () => {
    if (normalize(getSelectValue(refs.reasonCode))) {
      setReasonInvalid(false);
      showModalError("");
    }
  });

  refs.assignTo.addEventListener("input", () => {
    if (text(refs.assignTo.value)) {
      setAssignInvalid(false);
      showModalError("");
    }
  });

  refs.trailToggle.addEventListener("click", () => {
    trailExpanded = !trailExpanded;
    renderTrail(activeItem);
  });

  /* Card expand / collapse + quick approval button */
  refs.list.addEventListener("click", (e) => {
    const trigger =
      e.target instanceof Element
        ? e.target.closest(".js-open-workbench")
        : null;
    if (trigger) {
      const el = trigger.closest(".aw-item[data-id]");
      if (el) openWorkbench(el);
      return;
    }

    const toggle =
      e.target instanceof Element
        ? e.target.closest(".js-toggle-detail")
        : null;
    if (!toggle) return;
    const el = toggle.closest(".aw-item[data-id]");
    if (!el) return;
    el.classList.toggle("is-expanded");
  });

  /* Submit action */
  refs.submitBtn.addEventListener("click", async () => {
    if (!activeItem) return;
    const rowId = Number(refs.rowId.value || 0);
    if (rowId <= 0) return;

    const ac = normalize(refs.actionType.value);
    const rc = normalize(getSelectValue(refs.reasonCode));
    const noteRaw = text(refs.reasonNote.value);
    const assignTo = text(refs.assignTo.value);
    const supp = !!refs.needSupplement.checked;

    setReasonInvalid(false);
    setAssignInvalid(false);
    showModalError("");

    if (!rc) {
      setReasonInvalid(true);
      showModalError("请选择处理原因后再提交。");
      return;
    }
    if (ac === "ASSIGN" && !assignTo) {
      setAssignInvalid(true);
      showModalError("转派动作必须填写接收人。");
      return;
    }

    const comment = buildComment(ac, activeItem, noteRaw, supp);
    const payload = {
      action: ac,
      change_reason_code: rc,
      change_reason_note: noteRaw,
      comment,
      assign_to: ac === "ASSIGN" ? assignTo : "",
    };

    refs.submitBtn.disabled = true;
    const origText = refs.submitBtn.textContent;
    refs.submitBtn.textContent = "提交中…";

    try {
      const result = await requestJson(
        `/api/approvals/${encodeURIComponent(rowId)}/action`,
        payload,
      );
      applyActionResult(activeItem, ac, rc, noteRaw, supp, result);
      modal.modal("hide");
      showFeedback("success", text(result.message) || "审批动作已完成。");
    } catch (err) {
      const msg = text(err && err.message) || "审批动作失败";
      showModalError(`提交失败：${msg}`);
      showFeedback("danger", `审批失败：${msg}`);
    } finally {
      refs.submitBtn.disabled = false;
      refs.submitBtn.textContent = origText || "确认提交";
    }
  });

  modal.on("hidden.bs.modal", () => {
    activeItem = null;
    trailExpanded = false;
    refs.rowId.value = "";
    clearActionForm();
    setAssignVisible(false);
    refs.latestProgress.textContent = "-";
    refs.contextHint.textContent = "请选择动作并提交。";
    refs.trailList.innerHTML = "";
    refs.trailToggle.classList.add("d-none");
  });

  /* ── Init ── */
  items().forEach((el) => {
    ensureTrail(el);
    renderItem(el);
  });

  recalcMetrics();
  applyStepDeepLink();
  applyFilters();
  preloadRiskCases();
  applyReferenceDeepLink();

  if (typeof window.initEnterpriseSelect === "function")
    window.initEnterpriseSelect(modalEl);
})();
