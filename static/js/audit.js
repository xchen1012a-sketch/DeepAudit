(function (global) {
  "use strict";

  const I18N_ZH = {
    title: "AI 哨兵解读报告",
    headlineTag: "DeepAudit Copilot",
    loading: "正在生成 AI 风控解读，请稍候...",
    moduleMissing: "AI 模块加载失败，请刷新页面后重试。",
    requestFailed: "AI 请求失败，请稍后重试。",
    invalidResponse: "AI 返回结果格式异常，请转人工复核。",
    riskScoreLabel: "风险评分",
    modelLabel: "模型",
    traceIdLabel: "追踪 ID",
    evidenceLabel: "关键证据字段",
    summaryLabel: "综合结论",
    detailsLabel: "判定说明",
    suggestionLabel: "建议动作",
    suggestionPrefix: "下一步建议：",
    noEvidence: "暂无可追溯证据字段，建议结合原始影像进行人工核验。",
    detailsFallback: "暂无详细解释，请人工复核。",
    summaryFallback: "当前单据需要人工复核。",
    suggestionFallback: "建议补充业务凭证并由审计人员二次确认。",
    unknownValue: "-",
    levelText: {
      HIGH: "高风险",
      MEDIUM: "中风险",
      LOW: "低风险",
      UNKNOWN: "待复核",
    },
    levelIcon: {
      HIGH: "ri-error-warning-line",
      MEDIUM: "ri-alert-line",
      LOW: "ri-shield-check-line",
      UNKNOWN: "ri-information-line",
    },
    levelBadgeClass: {
      HIGH: "audit-risk-badge-high",
      MEDIUM: "audit-risk-badge-medium",
      LOW: "audit-risk-badge-low",
      UNKNOWN: "audit-risk-badge-medium",
    },
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toText(value, fallback = I18N_ZH.unknownValue) {
    const text = String(value ?? "").trim();
    return text || fallback;
  }

  function normalizeLevel(value) {
    const level = String(value ?? "").trim().toUpperCase();
    if (level === "HIGH" || level === "MEDIUM" || level === "LOW") {
      return level;
    }
    return "UNKNOWN";
  }

  function defaultRiskScore(level) {
    if (level === "HIGH") return 88;
    if (level === "LOW") return 25;
    return 60;
  }

  function clampRiskScore(value, level) {
    const raw = Number(value);
    if (!Number.isFinite(raw)) {
      return defaultRiskScore(level);
    }
    return Math.max(0, Math.min(100, Math.round(raw)));
  }

  function normalizeEvidence(evidence) {
    if (!Array.isArray(evidence)) {
      return [];
    }
    return evidence
      .map(function (item) {
        if (!item || typeof item !== "object") {
          return null;
        }
        const key = toText(item.key, "");
        const value = toText(item.value, "");
        if (!key && !value) {
          return null;
        }
        return {
          type: toText(item.type, "field"),
          key: key || I18N_ZH.unknownValue,
          value: value || I18N_ZH.unknownValue,
        };
      })
      .filter(Boolean);
  }

  function normalizeProtocolPayload(payload) {
    if (payload && payload.status === "success" && payload.data && typeof payload.data === "object") {
      const data = payload.data;
      const level = normalizeLevel(data.risk_level);
      return {
        risk_level: level,
        risk_score: clampRiskScore(data.risk_score, level),
        summary: toText(data.summary, I18N_ZH.summaryFallback),
        details: toText(data.details, I18N_ZH.detailsFallback),
        suggestion: toText(data.suggestion, I18N_ZH.suggestionFallback),
        evidence: normalizeEvidence(data.evidence),
        model: toText(data.model, "mock_sentinel_v1"),
        trace_id: toText(data.trace_id, I18N_ZH.unknownValue),
      };
    }

    if (payload && typeof payload === "object") {
      const level = normalizeLevel(payload.risk_level);
      return {
        risk_level: level,
        risk_score: clampRiskScore(payload.risk_score, level),
        summary: toText(payload.summary || payload.message, I18N_ZH.summaryFallback),
        details: toText(payload.details || payload.message, I18N_ZH.detailsFallback),
        suggestion: toText(payload.suggestion, I18N_ZH.suggestionFallback),
        evidence: normalizeEvidence(payload.evidence),
        model: toText(payload.model, "mock_sentinel_v1"),
        trace_id: toText(payload.trace_id, I18N_ZH.unknownValue),
      };
    }

    throw new Error(I18N_ZH.invalidResponse);
  }

  function renderLoadingCard(container) {
    container.innerHTML = `
      <div class="skeleton-loader fade-in" aria-live="polite">
        <div class="skeleton-line skeleton-title"></div>
        <div class="skeleton-line skeleton-badge"></div>
        <div class="skeleton-line skeleton-paragraph"></div>
        <div class="skeleton-line skeleton-paragraph short"></div>
        <div class="skeleton-line skeleton-block"></div>
      </div>
      <div class="text-muted small mt-2">${escapeHtml(I18N_ZH.loading)}</div>
    `;
  }

  function renderErrorCard(container, message) {
    container.innerHTML = `
      <div class="audit-error-card fade-in">
        <div class="audit-error-icon"><i class="ri-error-warning-line"></i></div>
        <div class="audit-error-text">${escapeHtml(toText(message, I18N_ZH.requestFailed))}</div>
      </div>
    `;
  }

  function renderEvidencePanel(evidence) {
    if (!Array.isArray(evidence) || !evidence.length) {
      return `
        <section class="audit-section audit-evidence-section">
          <h6 class="audit-section-title">${escapeHtml(I18N_ZH.evidenceLabel)}</h6>
          <div class="audit-evidence-empty">${escapeHtml(I18N_ZH.noEvidence)}</div>
        </section>
      `;
    }

    const rows = evidence
      .map(function (item) {
        return `
          <div class="audit-evidence-row">
            <div class="audit-evidence-key">${escapeHtml(item.key)}</div>
            <div class="audit-evidence-value">${escapeHtml(item.value)}</div>
          </div>
        `;
      })
      .join("");

    return `
      <section class="audit-section audit-evidence-section">
        <h6 class="audit-section-title">${escapeHtml(I18N_ZH.evidenceLabel)}</h6>
        <div class="audit-evidence-grid">${rows}</div>
      </section>
    `;
  }

  function renderAuditCard(container, data) {
    const level = normalizeLevel(data.risk_level);
    const levelText = I18N_ZH.levelText[level] || I18N_ZH.levelText.UNKNOWN;
    const iconClass = I18N_ZH.levelIcon[level] || I18N_ZH.levelIcon.UNKNOWN;
    const badgeClass = I18N_ZH.levelBadgeClass[level] || I18N_ZH.levelBadgeClass.UNKNOWN;
    const detailsHtml = escapeHtml(data.details).replace(/\n/g, "<br>");
    const scoreText = String(clampRiskScore(data.risk_score, level));

    container.innerHTML = `
      <section class="audit-card fade-in">
        <header class="audit-card-head">
          <div class="audit-head-main">
            <span class="audit-head-icon"><i class="ri-shield-star-line"></i></span>
            <div>
              <div class="audit-head-kicker">${escapeHtml(I18N_ZH.headlineTag)}</div>
              <h6 class="audit-engine-title">${escapeHtml(I18N_ZH.title)}</h6>
            </div>
          </div>
          <div class="audit-head-score">
            <span class="audit-risk-badge ${escapeHtml(badgeClass)}">
              <i class="${escapeHtml(iconClass)}"></i>${escapeHtml(levelText)}
            </span>
            <div class="audit-score-ring">
              <strong>${escapeHtml(scoreText)}</strong>
              <small>/100</small>
            </div>
          </div>
        </header>

        <div class="audit-meta-row">
          <div class="audit-meta-chip">
            <span>${escapeHtml(I18N_ZH.modelLabel)}</span>
            <strong>${escapeHtml(data.model)}</strong>
          </div>
          <div class="audit-meta-chip">
            <span>${escapeHtml(I18N_ZH.traceIdLabel)}</span>
            <strong>${escapeHtml(data.trace_id)}</strong>
          </div>
          <div class="audit-meta-chip">
            <span>${escapeHtml(I18N_ZH.riskScoreLabel)}</span>
            <strong>${escapeHtml(scoreText)}</strong>
          </div>
        </div>

        <div class="audit-card-body">
          <section class="audit-section">
            <h6 class="audit-section-title">${escapeHtml(I18N_ZH.summaryLabel)}</h6>
            <div class="audit-summary">${escapeHtml(data.summary)}</div>
          </section>

          <section class="audit-section">
            <h6 class="audit-section-title">${escapeHtml(I18N_ZH.detailsLabel)}</h6>
            <div class="audit-details">${detailsHtml}</div>
          </section>

          <section class="audit-section">
            <h6 class="audit-section-title">${escapeHtml(I18N_ZH.suggestionLabel)}</h6>
            <div class="audit-suggestion">
              <span class="audit-suggestion-icon"><i class="ri-lightbulb-flash-line"></i></span>
              <span>${escapeHtml(I18N_ZH.suggestionPrefix)}${escapeHtml(data.suggestion)}</span>
            </div>
          </section>

          ${renderEvidencePanel(data.evidence)}
        </div>
      </section>
    `;
  }

  function resolveContainer(options) {
    const containerId = toText(options && options.containerId, "ai-audit-container");
    return document.getElementById(containerId);
  }

  async function fetchAiPayload(invoiceId, options) {
    const requestBody = {
      claim_category: (options && options.claimCategory) || "",
      extra_context: (options && options.extraContext) || {},
    };
    const response = await fetch(`/invoice/${encodeURIComponent(invoiceId)}/ai`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(requestBody),
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error(I18N_ZH.invalidResponse);
    }

    if (!response.ok || (payload && payload.status === "error")) {
      throw new Error(toText(payload && payload.message, I18N_ZH.requestFailed));
    }
    return payload;
  }

  async function openInvoiceAudit(invoiceId, options = {}) {
    const container = resolveContainer(options);
    if (!container) {
      throw new Error(I18N_ZH.moduleMissing);
    }

    renderLoadingCard(container);
    try {
      const payload = await fetchAiPayload(invoiceId, options);
      const normalizedData = normalizeProtocolPayload(payload);
      renderAuditCard(container, normalizedData);
      return normalizedData;
    } catch (error) {
      renderErrorCard(container, error && error.message);
      return null;
    }
  }

  global.DeepAuditAudit = {
    I18N_ZH: I18N_ZH,
    openInvoiceAudit: openInvoiceAudit,
  };
})(window);
