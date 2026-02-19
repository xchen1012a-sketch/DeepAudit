(() => {
  const root = document.getElementById("risk-center-v2");
  const modalEl = document.getElementById("riskActionModal");
  if (!root || !modalEl || !window.jQuery) return;

  const modal = window.jQuery(modalEl);
  const titleNode = document.getElementById("riskActionTitle");
  const hintNode = document.getElementById("riskActionHint");
  const caseIdNode = document.getElementById("riskActionCaseId");
  const typeNode = document.getElementById("riskActionType");
  const reasonNode = document.getElementById("riskActionReason");
  const reasonErrorNode = document.getElementById("riskActionReasonError");
  const assignWrap = document.getElementById("riskActionAssignWrap");
  const assignNode = document.getElementById("riskActionAssignTo");
  const noteNode = document.getElementById("riskActionNote");
  const submitBtn = document.getElementById("riskActionSubmit");
  const errorNode = document.getElementById("riskActionError");

  if (
    !titleNode ||
    !hintNode ||
    !caseIdNode ||
    !typeNode ||
    !reasonNode ||
    !reasonErrorNode ||
    !assignWrap ||
    !assignNode ||
    !noteNode ||
    !submitBtn ||
    !errorNode
  ) {
    return;
  }

  const currentOperator = text(root.getAttribute("data-current-operator"));
  let activeRow = null;
  let activeAction = "";

  const STATUS_TEXT_MAP = {
    OPEN: "\u5f85\u5206\u6d3e",
    ASSIGNED: "\u5df2\u5206\u6d3e",
    PROCESSING: "\u5904\u7406\u4e2d",
    CLOSED: "\u5df2\u7ed3\u6848",
  };

  const STATUS_BADGE_CLASS_MAP = {
    OPEN: "badge-danger",
    ASSIGNED: "badge-info",
    PROCESSING: "badge-light",
    CLOSED: "badge-secondary",
  };

  const ACTION_MAP = {
    CLAIM: {
      title: "\u7b7e\u6536\u6848\u4ef6",
      hint: "\u7b7e\u6536\u540e\u4f1a\u5c06\u6848\u4ef6\u5206\u6d3e\u7ed9\u5f53\u524d\u64cd\u4f5c\u4eba\u3002",
      submitText: "\u786e\u8ba4\u7b7e\u6536",
      needAssignTo: false,
      progressText: "\u7b7e\u6536",
      latestEventCode: "ASSIGN",
      endpoint(caseId) {
        return `/risk/cases/${encodeURIComponent(caseId)}/assign`;
      },
      buildPayload(data) {
        const note = text(data.note);
        return {
          assigned_to: data.assignedTo,
          action_note: note ? `risk_center_claim: ${note}` : "risk_center_claim",
          change_reason_code: data.reasonCode,
          change_reason_note: note,
        };
      },
    },
    TRANSFER: {
      title: "\u8f6c\u6d3e\u6848\u4ef6",
      hint: "\u8f6c\u6d3e\u4f1a\u66f4\u65b0\u5f53\u524d\u5904\u7406\u4eba\u5e76\u4fdd\u6301\u6848\u4ef6\u5728\u5904\u7406\u4e2d\u3002",
      submitText: "\u786e\u8ba4\u8f6c\u6d3e",
      needAssignTo: true,
      progressText: "\u8f6c\u6d3e",
      latestEventCode: "ASSIGN",
      endpoint(caseId) {
        return `/risk/cases/${encodeURIComponent(caseId)}/assign`;
      },
      buildPayload(data) {
        const note = text(data.note);
        return {
          assigned_to: data.assignedTo,
          action_note: note ? `risk_center_transfer: ${note}` : "risk_center_transfer",
          change_reason_code: data.reasonCode,
          change_reason_note: note,
        };
      },
    },
    CLOSE: {
      title: "\u7ed3\u6848",
      hint: "\u7ed3\u6848\u540e\u6848\u4ef6\u72b6\u6001\u5c06\u66f4\u65b0\u4e3a\u201c\u5df2\u7ed3\u6848\u201d\u3002",
      submitText: "\u786e\u8ba4\u7ed3\u6848",
      needAssignTo: false,
      progressText: "\u7ed3\u6848",
      latestEventCode: "CLOSE",
      endpoint(caseId) {
        return `/risk/cases/${encodeURIComponent(caseId)}/close`;
      },
      buildPayload(data) {
        const note = text(data.note);
        return {
          resolution_note: note || "\u98ce\u9669\u5904\u7f6e\u5b8c\u6210\uff0c\u6848\u4ef6\u7ed3\u6848",
          action_note: note ? `risk_center_close: ${note}` : "risk_center_close",
          change_reason_code: data.reasonCode,
          change_reason_note: note,
        };
      },
    },
    FALSE_POSITIVE: {
      title: "\u8bef\u62a5\u5904\u7406",
      hint: "\u8bef\u62a5\u5c06\u6309\u7ed3\u6848\u5904\u7406\uff0c\u5e76\u8bb0\u5f55\u4e3a\u8bef\u62a5\u8bf4\u660e\u3002",
      submitText: "\u786e\u8ba4\u8bef\u62a5",
      needAssignTo: false,
      progressText: "\u8bef\u62a5\u7ed3\u6848",
      latestEventCode: "CLOSE",
      endpoint(caseId) {
        return `/risk/cases/${encodeURIComponent(caseId)}/close`;
      },
      buildPayload(data) {
        const note = text(data.note);
        return {
          resolution_note: note || "\u5224\u5b9a\u4e3a\u8bef\u62a5\u5e76\u7ed3\u6848",
          action_note: note
            ? `risk_center_false_positive_close: ${note}`
            : "risk_center_false_positive_close",
          change_reason_code: data.reasonCode,
          change_reason_note: note,
        };
      },
    },
  };

  function text(value) {
    return String(value ?? "").trim();
  }

  function normalize(value) {
    return text(value).toUpperCase();
  }

  function getSelectValue(node) {
    if (!node) return "";
    if (node.tomselect && typeof node.tomselect.getValue === "function") {
      return text(node.tomselect.getValue());
    }
    return text(node.value);
  }

  function setSelectValue(node, value = "") {
    if (!node) return;
    const next = text(value);
    if (node.tomselect && typeof node.tomselect.setValue === "function") {
      node.tomselect.setValue(next, true);
      return;
    }
    node.value = next;
  }

  function setNodeText(node, value, fallback = "-") {
    if (!node) return;
    const raw = text(value);
    node.textContent = raw || fallback;
  }

  function formatNow() {
    const now = new Date();
    const yyyy = String(now.getFullYear());
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const hh = String(now.getHours()).padStart(2, "0");
    const mi = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  function cnStatus(statusCode) {
    const api = window.DeepAuditStatusI18N;
    if (api && typeof api.toCnRiskCaseStatus === "function") {
      return api.toCnRiskCaseStatus(statusCode, "\u5904\u7406\u4e2d");
    }
    return STATUS_TEXT_MAP[normalize(statusCode)] || "\u5904\u7406\u4e2d";
  }

  function cnEvent(eventCode, actionNote, fallback) {
    const code = normalize(eventCode);
    const noteLower = text(actionNote).toLowerCase();

    if (code === "ASSIGN") {
      if (noteLower.includes("risk_center_claim")) return "\u7b7e\u6536";
      if (noteLower.includes("risk_center_transfer")) return "\u8f6c\u6d3e";
    }
    if (code === "CLOSE") {
      if (noteLower.includes("false_positive") || noteLower.includes("\u8bef\u62a5")) {
        return "\u8bef\u62a5\u7ed3\u6848";
      }
      return "\u7ed3\u6848";
    }

    const api = window.DeepAuditStatusI18N;
    if (api && typeof api.toCnRiskCaseEvent === "function") {
      return api.toCnRiskCaseEvent(code, text(fallback) || "\u5df2\u66f4\u65b0");
    }
    return text(fallback) || "\u5df2\u66f4\u65b0";
  }

  function showModalError(message) {
    const msg = text(message);
    if (!msg) {
      errorNode.textContent = "";
      errorNode.classList.add("d-none");
      return;
    }
    errorNode.textContent = msg;
    errorNode.classList.remove("d-none");
  }

  function setReasonInvalid(invalid) {
    reasonNode.classList.toggle("is-invalid", !!invalid);
    reasonErrorNode.classList.toggle("d-none", !invalid);
  }

  function clearFormState() {
    showModalError("");
    setReasonInvalid(false);
    assignNode.classList.remove("is-invalid");
    setSelectValue(reasonNode, "");
    setSelectValue(assignNode, "");
    noteNode.value = "";
  }

  function openActionModal(action, row) {
    const config = ACTION_MAP[action];
    const caseId = Number(row.getAttribute("data-case-id") || 0);
    if (!config || caseId <= 0) return;

    activeRow = row;
    activeAction = action;
    titleNode.textContent = config.title;
    (hintNode.querySelector(".alert-body") || hintNode).textContent = config.hint;
    submitBtn.textContent = config.submitText;
    caseIdNode.value = String(caseId);
    typeNode.value = action;
    clearFormState();

    assignWrap.classList.toggle("d-none", !config.needAssignTo);
    if (config.needAssignTo) {
      setSelectValue(assignNode, text(row.getAttribute("data-owner")));
    }

    modal.modal("show");
  }

  function buildSubmitContext(config, row) {
    const reasonCode = normalize(getSelectValue(reasonNode));
    if (!reasonCode) {
      setReasonInvalid(true);
      showModalError("\u8bf7\u9009\u62e9\u5904\u7406\u539f\u56e0\u540e\u518d\u63d0\u4ea4\u3002");
      return null;
    }

    const note = text(noteNode.value);
    let assignedTo = "";
    if (config.needAssignTo) {
      assignedTo = getSelectValue(assignNode);
      if (!assignedTo) {
        assignNode.classList.add("is-invalid");
        showModalError("\u8bf7\u9009\u62e9\u8f6c\u6d3e\u63a5\u6536\u4eba\u3002");
        return null;
      }
    } else if (normalize(activeAction) === "CLAIM") {
      assignedTo = currentOperator || text(row.getAttribute("data-owner"));
      if (!assignedTo) {
        showModalError(
          "\u672a\u8bc6\u522b\u5f53\u524d\u64cd\u4f5c\u4eba\uff0c\u8bf7\u6539\u7528\u201c\u8f6c\u6d3e\u201d\u64cd\u4f5c\u3002",
        );
        return null;
      }
    }

    return {
      reasonCode,
      note,
      assignedTo,
    };
  }

  async function requestJson(url, payload) {
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

  function setClosedState(row, isClosed) {
    row.querySelectorAll(".js-risk-action").forEach((btn) => {
      if (!(btn instanceof HTMLButtonElement)) return;
      btn.disabled = !!isClosed;
      if (isClosed) {
        btn.title = "\u5df2\u7ed3\u6848";
      } else {
        btn.removeAttribute("title");
      }
    });
  }

  function updateStatusCell(row, statusCode) {
    const cell = row.querySelector(".risk-status-cell");
    if (!cell) return;

    let badge = cell.querySelector(".badge");
    if (!badge) {
      badge = document.createElement("span");
      cell.textContent = "";
      cell.appendChild(badge);
    }
    badge.className = `badge ${STATUS_BADGE_CLASS_MAP[statusCode] || "badge-light"}`;
    badge.textContent = cnStatus(statusCode);
  }

  function updateRowAfterSuccess(row, config, payload, responseCase) {
    const resultCase = responseCase && typeof responseCase === "object" ? responseCase : {};
    const statusCode =
      normalize(resultCase.status) || (config.latestEventCode === "CLOSE" ? "CLOSED" : "ASSIGNED");
    const previousOwner = text(row.getAttribute("data-owner"));
    const ownerRaw =
      text(resultCase.assigned_to) || text(payload.assigned_to) || text(row.getAttribute("data-owner"));
    const ownerDisplay = ownerRaw || "\u672a\u5206\u914d";
    const eventCode = config.latestEventCode;
    const progressTime = text(resultCase.closed_at) || text(resultCase.updated_at) || formatNow();
    const actionNote = text(payload.action_note);
    const eventCn = cnEvent(eventCode, actionNote, config.progressText);
    const progressText = `${eventCn} \u00b7 ${progressTime}`;

    row.setAttribute("data-status", statusCode);
    row.setAttribute("data-owner", ownerRaw);
    row.setAttribute("data-latest-event", eventCode);
    row.setAttribute("data-latest-note", actionNote);
    row.setAttribute("data-updated-at", progressTime);

    updateStatusCell(row, statusCode);
    setNodeText(row.querySelector(".risk-owner-name"), ownerDisplay, "\u672a\u5206\u914d");
    if (previousOwner !== ownerRaw) {
      setNodeText(
        row.querySelector(".risk-owner-dept"),
        ownerRaw ? "\u90e8\u95e8\uff1a\u5f85\u8bc6\u522b" : "\u90e8\u95e8\uff1a\u672a\u6807\u6ce8",
        "\u90e8\u95e8\uff1a\u672a\u6807\u6ce8",
      );
    }
    setNodeText(row.querySelector(".risk-latest-cell"), progressText, "-");

    setNodeText(row.querySelector(".js-tech-status-cn"), cnStatus(statusCode), "-");
    setNodeText(row.querySelector(".js-tech-owner"), ownerDisplay || "-", "-");
    setNodeText(row.querySelector(".js-tech-owner-account"), ownerRaw || "-", "-");
    setNodeText(row.querySelector(".js-tech-updated-at"), progressTime, "-");
    setNodeText(row.querySelector(".js-tech-latest-event-cn"), eventCn, "-");
    setNodeText(row.querySelector(".js-tech-latest-note"), actionNote || "-", "-");

    setClosedState(row, statusCode === "CLOSED");
  }

  function toastSuccess(message) {
    const msg = text(message) || "\u5904\u7406\u6210\u529f";
    if (typeof window.showToast === "function") {
      window.showToast(msg, "success", 1800);
      return;
    }
    window.alert(msg);
  }

  reasonNode.addEventListener("change", () => {
    if (normalize(getSelectValue(reasonNode))) {
      setReasonInvalid(false);
      showModalError("");
    }
  });

  const clearAssignError = () => {
    if (getSelectValue(assignNode)) {
      assignNode.classList.remove("is-invalid");
      showModalError("");
    }
  };
  assignNode.addEventListener("input", clearAssignError);
  assignNode.addEventListener("change", clearAssignError);

  document.addEventListener("click", (event) => {
    const trigger = event.target instanceof Element ? event.target.closest(".js-risk-action") : null;
    if (!(trigger instanceof HTMLButtonElement)) return;

    const row = trigger.closest("[data-case-id]");
    if (!row) return;
    openActionModal(normalize(trigger.getAttribute("data-action")), row);
  });

  submitBtn.addEventListener("click", async () => {
    const action = normalize(typeNode.value);
    const caseId = Number(caseIdNode.value || 0);
    const config = ACTION_MAP[action];
    if (!config || caseId <= 0 || !activeRow) return;

    const submitCtx = buildSubmitContext(config, activeRow);
    if (!submitCtx) return;

    const payload = config.buildPayload(submitCtx);
    submitBtn.disabled = true;
    showModalError("");
    try {
      const result = await requestJson(config.endpoint(caseId), payload);
      updateRowAfterSuccess(activeRow, config, payload, result.case);
      modal.modal("hide");
      toastSuccess(result.message || `${config.progressText}\u5df2\u5b8c\u6210`);
    } catch (error) {
      showModalError(`\u63d0\u4ea4\u5931\u8d25\uff1a${error.message || error}`);
    } finally {
      submitBtn.disabled = false;
    }
  });

  modal.on("hidden.bs.modal", () => {
    clearFormState();
    activeRow = null;
    activeAction = "";
    caseIdNode.value = "";
    typeNode.value = "";
    assignWrap.classList.add("d-none");
  });

  if (typeof window.initEnterpriseSelect === "function") {
    window.initEnterpriseSelect(modalEl);
  }
})();
