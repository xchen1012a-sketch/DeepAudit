(() => {
  const root = document.getElementById("admin-roles-page");
  const initNode = document.getElementById("adminRolesInitPayload");
  if (!root || !initNode || !window.jQuery) return;

  let initPayload = {};
  try {
    initPayload = JSON.parse(initNode.textContent || "{}");
  } catch (_) {
    initPayload = {};
  }

  const refs = {
    feedback: document.getElementById("rolesFeedback"),
    roleCountBadge: document.getElementById("roleCountBadge"),
    rolesTableBody: document.getElementById("rolesTableBody"),
    reloadBtn: document.getElementById("reloadRolesBtn"),
    toggleAdvancedBtn: document.getElementById("toggleAdvancedInfoBtn"),
    openCreateRoleBtn: document.getElementById("openCreateRoleBtn"),

    roleEditorTitle: document.getElementById("roleEditorTitle"),
    editorRoleName: document.getElementById("editorRoleName"),
    editorDataScope: document.getElementById("editorDataScope"),
    pendingSummary: document.getElementById("rolePendingSummary"),
    permissionGroupContainer: document.getElementById("permissionGroupContainer"),
    resetDefaultsBtn: document.getElementById("resetRoleDefaultsBtn"),
    saveBtn: document.getElementById("saveRoleBtn"),

    menuPreviewContainer: document.getElementById("menuPreviewContainer"),
    actionPreviewContainer: document.getElementById("actionPreviewContainer"),
    roleAuditTableBody: document.getElementById("roleAuditTableBody"),

    saveModalEl: document.getElementById("roleSaveModal"),
    saveChangeSummary: document.getElementById("saveChangeSummary"),
    saveReasonCode: document.getElementById("saveReasonCode"),
    saveReasonCodeError: document.getElementById("saveReasonCodeError"),
    saveReasonNote: document.getElementById("saveReasonNote"),
    saveModalError: document.getElementById("saveModalError"),
    saveRoleSubmitBtn: document.getElementById("saveRoleSubmitBtn"),

    createRoleModalEl: document.getElementById("createRoleModal"),
    createRoleForm: document.getElementById("createRoleForm"),
    createRoleSubmitBtn: document.getElementById("createRoleSubmitBtn"),
    createRoleError: document.getElementById("createRoleError"),
    newRoleName: document.getElementById("newRoleName"),
  };

  if (
    !refs.feedback ||
    !refs.roleCountBadge ||
    !refs.rolesTableBody ||
    !refs.reloadBtn ||
    !refs.toggleAdvancedBtn ||
    !refs.roleEditorTitle ||
    !refs.editorRoleName ||
    !refs.editorDataScope ||
    !refs.pendingSummary ||
    !refs.permissionGroupContainer ||
    !refs.resetDefaultsBtn ||
    !refs.saveBtn ||
    !refs.menuPreviewContainer ||
    !refs.actionPreviewContainer ||
    !refs.roleAuditTableBody ||
    !refs.saveModalEl ||
    !refs.saveChangeSummary ||
    !refs.saveReasonCode ||
    !refs.saveReasonCodeError ||
    !refs.saveReasonNote ||
    !refs.saveModalError ||
    !refs.saveRoleSubmitBtn ||
    !refs.createRoleModalEl ||
    !refs.createRoleForm ||
    !refs.createRoleSubmitBtn ||
    !refs.createRoleError ||
    !refs.newRoleName
  ) {
    return;
  }

  const saveModal = window.jQuery(refs.saveModalEl);
  const createRoleModal = window.jQuery(refs.createRoleModalEl);

  const state = {
    roles: Array.isArray(initPayload.roles) ? initPayload.roles : [],
    permissions: Array.isArray(initPayload.permissions) ? initPayload.permissions : [],
    permissionGroups: Array.isArray(initPayload.permission_groups) ? initPayload.permission_groups : [],
    menuRules: Array.isArray(initPayload.menu_rules) ? initPayload.menu_rules : [],
    actionRules: Array.isArray(initPayload.action_rules) ? initPayload.action_rules : [],
    changeReasonOptions: Array.isArray(initPayload.change_reason_options) ? initPayload.change_reason_options : [],
    selectedRoleId: 0,
    showAdvanced: false,
  };

  function text(value) {
    return String(value ?? "").trim();
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

  function displayText(value, fallback = "-") {
    const output = text(value);
    return output || fallback;
  }

  function scopeLabel(value) {
    return normalize(value) === "ALL" ? "全量数据" : "本部门数据";
  }

  function permissionById(permissionId) {
    const targetId = Number(permissionId || 0);
    if (targetId <= 0) return null;
    return state.permissions.find((item) => Number(item && item.id || 0) === targetId) || null;
  }

  function permissionNameByKey(permissionKey) {
    const key = normalize(permissionKey);
    if (!key) return "未映射权限";
    const found = state.permissions.find((item) => normalize(item && item.permission_key) === key);
    return text(found && found.name_cn) || "未映射权限";
  }

  function roleById(roleId) {
    const id = Number(roleId || 0);
    if (id <= 0) return null;
    return state.roles.find((item) => Number(item && item.id || 0) === id) || null;
  }

  function getRolePermissionKeySet(role) {
    const set = new Set();
    const permissions = Array.isArray(role && role.permissions) ? role.permissions : [];
    permissions.forEach((item) => {
      const key = normalize(item && item.permission_key);
      if (key) set.add(key);
    });
    return set;
  }

  function getRolePermissionIdSet(role) {
    const set = new Set();
    const permissions = Array.isArray(role && role.permissions) ? role.permissions : [];
    permissions.forEach((item) => {
      const id = Number(item && item.id || 0);
      if (id > 0) set.add(id);
    });
    return set;
  }

  function roleDefaultTemplate(role) {
    const defaultKeySet = new Set(
      (Array.isArray(role && role.default_permission_keys) ? role.default_permission_keys : [])
        .map((item) => normalize(item))
        .filter(Boolean),
    );
    if (!defaultKeySet.size) {
      const permissionIds = Array.isArray(role && role.default_permission_ids) ? role.default_permission_ids : [];
      permissionIds.forEach((permissionId) => {
        const permission = permissionById(permissionId);
        const key = normalize(permission && permission.permission_key);
        if (key) defaultKeySet.add(key);
      });
    }
    if (!defaultKeySet.size) {
      getRolePermissionKeySet(role).forEach((key) => defaultKeySet.add(key));
    }
    const rawScope = normalize(role && role.default_data_scope);
    const dataScope = rawScope === "ALL" ? "ALL" : "DEPT";
    return {
      keySet: defaultKeySet,
      dataScope,
      sourceRoleName: displayText(role && role.default_source_role_name, "通用员工"),
      isBuiltin: !!(role && role.default_is_builtin),
    };
  }

  function collectCurrentPermissionIds() {
    const ids = Array.from(refs.permissionGroupContainer.querySelectorAll(".js-role-permission"))
      .filter((node) => node instanceof HTMLInputElement && node.checked)
      .map((node) => Number(node.value))
      .filter((id) => Number.isInteger(id) && id > 0);
    return Array.from(new Set(ids)).sort((a, b) => a - b);
  }

  function collectCurrentPermissionKeySet() {
    const keys = new Set();
    collectCurrentPermissionIds().forEach((permissionId) => {
      const permission = permissionById(permissionId);
      const key = normalize(permission && permission.permission_key);
      if (key) keys.add(key);
    });
    return keys;
  }

  function currentEditorState() {
    return {
      data_scope: normalize(refs.editorDataScope.value) === "ALL" ? "ALL" : "DEPT",
      permission_ids: collectCurrentPermissionIds(),
      permission_keys: collectCurrentPermissionKeySet(),
    };
  }

  function summarizePermissionNames(keys, limit = 4) {
    const list = Array.from(new Set(Array.from(keys || []).map((item) => normalize(item)).filter(Boolean)));
    if (!list.length) return "无";
    const labels = list.map((key) => permissionNameByKey(key));
    if (labels.length <= limit) return labels.join("、");
    return `${labels.slice(0, limit).join("、")} 等 ${labels.length} 项`;
  }

  function changeSummary(role, editorState) {
    if (!role || !editorState) return "未检测到变更";
    const beforeScope = normalize(role.data_scope) === "ALL" ? "ALL" : "DEPT";
    const afterScope = normalize(editorState.data_scope) === "ALL" ? "ALL" : "DEPT";
    const beforeSet = getRolePermissionKeySet(role);
    const afterSet = editorState.permission_keys instanceof Set ? editorState.permission_keys : new Set();

    const added = Array.from(afterSet).filter((key) => !beforeSet.has(key));
    const removed = Array.from(beforeSet).filter((key) => !afterSet.has(key));

    const parts = [];
    if (beforeScope !== afterScope) {
      parts.push(`数据范围：${scopeLabel(beforeScope)} \u2192 ${scopeLabel(afterScope)}`);
    }
    if (added.length) {
      parts.push(`新增权限：${summarizePermissionNames(added)}`);
    }
    if (removed.length) {
      parts.push(`移除权限：${summarizePermissionNames(removed)}`);
    }
    if (!parts.length) {
      return "权限与数据范围无变化";
    }
    return parts.join("；");
  }

  function hasPendingChanges(role, editorState) {
    if (!role || !editorState) return false;
    const beforeScope = normalize(role.data_scope) === "ALL" ? "ALL" : "DEPT";
    const afterScope = normalize(editorState.data_scope) === "ALL" ? "ALL" : "DEPT";
    if (beforeScope !== afterScope) return true;

    const beforeIds = getRolePermissionIdSet(role);
    const afterIds = new Set((editorState.permission_ids || []).map((item) => Number(item || 0)).filter((item) => item > 0));
    if (beforeIds.size !== afterIds.size) return true;
    for (const id of beforeIds) {
      if (!afterIds.has(id)) return true;
    }
    return false;
  }

  const ALERT_ICONS = {
    success: "ri-checkbox-circle-line",
    info: "ri-information-line",
    warning: "ri-error-warning-line",
    danger: "ri-close-circle-line",
  };

  function showFeedback(type, message, duration = 3200) {
    const tone = text(type) || "info";
    const msg = text(message) || "操作完成";
    const icon = ALERT_ICONS[tone] || ALERT_ICONS.info;
    refs.feedback.className = `alert alert-${tone} py-2 px-3 mb-3`;
    refs.feedback.style.borderRadius = "8px";
    refs.feedback.innerHTML =
      `<span class="alert-icon"><i class="${icon}"></i></span>` +
      `<span class="alert-body">${msg}</span>`;
    refs.feedback.classList.remove("d-none");
    clearTimeout(showFeedback._timer);
    showFeedback._timer = window.setTimeout(() => {
      refs.feedback.classList.add("d-none");
    }, Math.max(1200, Number(duration) || 3200));
  }

  function showSaveError(message = "") {
    const msg = text(message);
    refs.saveModalError.textContent = msg;
    refs.saveModalError.classList.toggle("d-none", !msg);
  }

  function setSaveReasonInvalid(invalid) {
    refs.saveReasonCode.classList.toggle("is-invalid", !!invalid);
    refs.saveReasonCodeError.classList.toggle("d-none", !invalid);
  }

  function getSelectValue(node) {
    if (!node) return "";
    if (node.tomselect && typeof node.tomselect.getValue === "function") {
      return text(node.tomselect.getValue());
    }
    return text(node.value);
  }

  function setSelectValue(node, value) {
    if (!node) return;
    const next = text(value);
    if (node.tomselect && typeof node.tomselect.setValue === "function") {
      node.tomselect.setValue(next, true);
      return;
    }
    node.value = next;
  }

  function rebuildSelect(node, options, selectedValue) {
    if (!node) return;
    const list = Array.isArray(options) ? options : [];
    const selected = text(selectedValue);

    if (node.tomselect && typeof node.tomselect.clearOptions === "function") {
      const instance = node.tomselect;
      instance.clear(true);
      instance.clearOptions();
      list.forEach((item) => {
        instance.addOption({
          value: text(item.value),
          text: text(item.label),
        });
      });
      instance.refreshOptions(false);
      instance.setValue(selected, true);
      return;
    }

    node.innerHTML = list
      .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
      .join("");
    node.value = selected;
  }

  function applyEditorTitle(role) {
    refs.roleEditorTitle.textContent = role ? `当前角色：${displayText(role.role_name)}` : "请选择角色";
    refs.editorRoleName.value = role ? displayText(role.role_name) : "";
    refs.editorDataScope.value = role && normalize(role.data_scope) === "ALL" ? "ALL" : "DEPT";
  }

  function renderRolesTable() {
    const rows = (Array.isArray(state.roles) ? state.roles : [])
      .filter((role) => role && typeof role === "object")
      .sort((a, b) => Number(a.id || 0) - Number(b.id || 0));

    refs.roleCountBadge.textContent = String(rows.length);
    if (!rows.length) {
      refs.rolesTableBody.innerHTML = '<div class="ra-empty">暂无角色数据</div>';
      return;
    }

    refs.rolesTableBody.innerHTML = rows
      .map((role) => {
        const roleId = Number(role.id || 0);
        const active = roleId > 0 && roleId === Number(state.selectedRoleId || 0);
        const permissionCount = Array.isArray(role.permissions) ? role.permissions.length : 0;
        const roleStatus = normalize(role.status) || "ACTIVE";
        const isDisabled = roleStatus === "DISABLED";
        const toggleLabel = isDisabled ? "启用" : "禁用";
        const boundCount = Number(role.user_bound_count || 0);
        const canDelete = boundCount === 0;
        const deleteDisabled = canDelete ? "" : "disabled";
        const deleteTitle = canDelete ? "删除该角色" : `已绑定 ${boundCount} 个用户，请先解绑`;
        return (
          `<div class="ra-role-item ${active ? "is-selected" : ""}" data-role-id="${roleId}">` +
            '<div class="ra-role-item-header">' +
              `<span class="ra-role-name">${escapeHtml(displayText(role.role_name))}</span>` +
              `<span class="ra-role-status"><span class="ra-status-dot ${isDisabled ? "is-disabled" : "is-active"}"></span>${isDisabled ? "已禁用" : "启用"}</span>` +
            '</div>' +
            '<div class="ra-role-meta">' +
              `<span>${permissionCount} 项权限</span>` +
              `<span>${escapeHtml(scopeLabel(role.data_scope))}</span>` +
            '</div>' +
            '<div class="ra-role-actions">' +
              `<button type="button" class="ra-act-btn js-toggle-role-status" data-role-id="${roleId}">${toggleLabel}</button>` +
              `<button type="button" class="ra-act-btn is-danger js-delete-role" data-role-id="${roleId}" ${deleteDisabled} title="${escapeHtml(deleteTitle)}">删除</button>` +
            '</div>' +
          "</div>"
        );
      })
      .join("");
  }

  function renderPermissionGroups(role, selectedKeySet = null) {
    if (!role) {
      refs.permissionGroupContainer.innerHTML = '<div class="ra-empty">请选择角色后编辑权限</div>';
      return;
    }

    const selectedKeys = selectedKeySet instanceof Set ? selectedKeySet : getRolePermissionKeySet(role);
    const groups = Array.isArray(state.permissionGroups) ? state.permissionGroups : [];

    refs.permissionGroupContainer.innerHTML = groups
      .map((group) => {
        const groupKey = normalize(group && group.key);
        const groupName = displayText(group && group.name_cn, "未分组");
        const groupDesc = displayText(group && group.description_cn, "");
        const permissions = (Array.isArray(state.permissions) ? state.permissions : [])
          .filter((item) => normalize(item && item.group_key) === groupKey)
          .sort((a, b) => Number(a && a.id || 0) - Number(b && b.id || 0));

        const permissionHtml = permissions.length
          ? permissions
              .map((permission) => {
                const id = Number(permission && permission.id || 0);
                const key = normalize(permission && permission.permission_key);
                const checked = selectedKeys.has(key) ? "checked" : "";
                return (
                  '<div class="ra-perm-item">' +
                    '<label class="ra-checkbox">' +
                      `<input type="checkbox" class="js-role-permission" data-group-key="${escapeHtml(groupKey)}" value="${id}" ${checked}>` +
                      '<span class="ra-checkbox-mark"></span>' +
                    '</label>' +
                    '<div class="ra-perm-content">' +
                      `<div class="ra-perm-name">${escapeHtml(displayText(permission && permission.name_cn, "未映射权限"))}</div>` +
                      `<div class="ra-perm-desc">${escapeHtml(displayText(permission && permission.description_cn, "暂无说明"))}</div>` +
                      '<div class="ra-perm-advanced">' +
                        `<div>权限标识：<code>${escapeHtml(key || "-")}</code></div>` +
                        `<div>内部编号：${id > 0 ? id : "-"}</div>` +
                      '</div>' +
                    '</div>' +
                  '</div>'
                );
              })
              .join("")
          : '<div class="ra-perm-item"><div class="ra-perm-content"><div class="ra-perm-desc">该分组暂无可配置权限点</div></div></div>';

        return (
          '<div class="ra-perm-group">' +
            '<div class="ra-perm-group-head">' +
              '<svg class="ra-collapse-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>' +
              '<div class="ra-perm-group-info">' +
                `<div class="ra-perm-group-name">${escapeHtml(groupName)}</div>` +
                `<div class="ra-perm-group-desc">${escapeHtml(groupDesc)}</div>` +
              '</div>' +
              '<div class="ra-perm-group-actions">' +
                `<button type="button" class="ra-grp-btn js-group-select-all" data-group-key="${escapeHtml(groupKey)}">全选</button>` +
                `<button type="button" class="ra-grp-btn js-group-select-none" data-group-key="${escapeHtml(groupKey)}">清空</button>` +
              '</div>' +
            '</div>' +
            `<div class="ra-perm-group-body">${permissionHtml}</div>` +
          '</div>'
        );
      })
      .join("");
  }

  function evaluateRule(rule, permissionKeySet) {
    const keys = Array.isArray(rule && rule.permissions)
      ? rule.permissions.map((item) => normalize(item)).filter(Boolean)
      : [];
    if (!keys.length) return true;
    if (normalize(rule && rule.mode) === "ALL") {
      return keys.every((key) => permissionKeySet.has(key));
    }
    return keys.some((key) => permissionKeySet.has(key));
  }

  function renderPreviewItems(container, rules, permissionKeySet, successText, failText) {
    const list = Array.isArray(rules) ? rules : [];
    if (!list.length) {
      container.innerHTML = '<div class="ra-empty">暂无预览规则</div>';
      return;
    }

    container.innerHTML = list
      .map((rule) => {
        const allowed = evaluateRule(rule, permissionKeySet);
        const name = displayText(rule && rule.name_cn, "未命名项");
        const groupName = displayText(rule && rule.group_cn, "");
        const fullName = groupName ? `${groupName} / ${name}` : name;
        return (
          '<div class="ra-preview-item">' +
            `<span class="ra-preview-name">${escapeHtml(fullName)}</span>` +
            `<span class="ra-preview-badge ${allowed ? "is-allowed" : "is-denied"}">${allowed ? successText : failText}</span>` +
          "</div>"
        );
      })
      .join("");
  }

  function renderAuditTrail(logs) {
    const list = Array.isArray(logs) ? logs : [];
    if (!list.length) {
      refs.roleAuditTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">暂无角色变更留痕</td></tr>';
      return;
    }

    refs.roleAuditTableBody.innerHTML = list
      .map((item) => {
        const createdAt = displayText(item && item.created_at);
        const operator = displayText(item && item.operator);
        const reason = displayText(item && item.change_reason_code_cn, "未标注");
        const summary = displayText(item && item.summary);
        const note = displayText(item && item.note);
        return (
          "<tr>" +
            `<td>${escapeHtml(createdAt)}</td>` +
            `<td>${escapeHtml(operator)}</td>` +
            `<td>${escapeHtml(reason)}</td>` +
            `<td><span class="audit-summary">${escapeHtml(summary)}</span></td>` +
            `<td>${escapeHtml(note)}</td>` +
          "</tr>"
        );
      })
      .join("");
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload || payload.ok !== true) {
      const message = text(payload.message) || text(payload.msg) || `请求失败（状态码 ${response.status}）`;
      throw new Error(message);
    }
    return payload;
  }

  async function loadRoleAuditTrail(roleId) {
    const id = Number(roleId || 0);
    if (id <= 0) {
      renderAuditTrail([]);
      return;
    }
    refs.roleAuditTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">留痕加载中...</td></tr>';
    try {
      const payload = await requestJson(`/api/admin/roles/${encodeURIComponent(id)}/audit_trail?limit=30`, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      renderAuditTrail(payload.logs);
    } catch (error) {
      refs.roleAuditTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger py-3">留痕加载失败：${escapeHtml(error.message || error)}</td></tr>`;
    }
  }

  function renderReasonOptions() {
    const options = [{ value: "", label: "请选择变更原因" }]
      .concat(
        (Array.isArray(state.changeReasonOptions) ? state.changeReasonOptions : []).map((item) => ({
          value: text(item && item.value),
          label: text(item && item.label),
        })),
      );
    rebuildSelect(refs.saveReasonCode, options, getSelectValue(refs.saveReasonCode));
    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(refs.saveModalEl);
    }
  }

  function refreshEditorMeta() {
    const role = roleById(state.selectedRoleId);
    const editorState = currentEditorState();
    const pending = role ? changeSummary(role, editorState) : "请先选择角色";
    refs.pendingSummary.textContent = pending;

    const dirty = role ? hasPendingChanges(role, editorState) : false;
    refs.saveBtn.disabled = !dirty;
    refs.resetDefaultsBtn.disabled = !role;
    refs.pendingSummary.classList.toggle("has-changes", dirty);

    const permissionKeySet = editorState.permission_keys instanceof Set ? editorState.permission_keys : new Set();
    renderPreviewItems(refs.menuPreviewContainer, state.menuRules, permissionKeySet, "可见", "隐藏/置灰");
    renderPreviewItems(refs.actionPreviewContainer, state.actionRules, permissionKeySet, "可执行", "不可执行");
  }

  function openRole(roleId) {
    const role = roleById(roleId);
    if (!role) return;
    state.selectedRoleId = Number(role.id || 0);
    setSelectValue(refs.editorDataScope, normalize(role.data_scope) === "ALL" ? "ALL" : "DEPT");
    applyEditorTitle(role);
    renderPermissionGroups(role, getRolePermissionKeySet(role));
    renderRolesTable();
    refreshEditorMeta();
    loadRoleAuditTrail(state.selectedRoleId);
  }

  async function loadRoles(showLoadFeedback = true) {
    try {
      const payload = await requestJson("/api/admin/roles", {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      state.roles = Array.isArray(payload.roles) ? payload.roles : [];
      state.permissions = Array.isArray(payload.permissions) ? payload.permissions : state.permissions;
      state.permissionGroups = Array.isArray(payload.permission_groups) ? payload.permission_groups : state.permissionGroups;
      state.menuRules = Array.isArray(payload.menu_rules) ? payload.menu_rules : state.menuRules;
      state.actionRules = Array.isArray(payload.action_rules) ? payload.action_rules : state.actionRules;
      state.changeReasonOptions = Array.isArray(payload.change_reason_options) ? payload.change_reason_options : state.changeReasonOptions;

      renderRolesTable();
      renderReasonOptions();
      if (!state.roles.length) {
        state.selectedRoleId = 0;
        applyEditorTitle(null);
        renderPermissionGroups(null);
        refreshEditorMeta();
        renderAuditTrail([]);
        return;
      }

      const currentExists = !!roleById(state.selectedRoleId);
      if (!currentExists) {
        state.selectedRoleId = Number(state.roles[0].id || 0);
      }
      openRole(state.selectedRoleId);
      if (showLoadFeedback) {
        showFeedback("success", `已加载 ${state.roles.length} 个角色`);
      }
    } catch (error) {
      showFeedback("danger", `加载失败：${error.message || error}`);
    }
  }

  function clearSaveModalState() {
    (refs.saveChangeSummary.querySelector(".alert-body") || refs.saveChangeSummary).textContent = "暂无变更";
    refs.saveReasonNote.value = "";
    setSelectValue(refs.saveReasonCode, "");
    setSaveReasonInvalid(false);
    showSaveError("");
    refs.saveRoleSubmitBtn.disabled = false;
    refs.saveRoleSubmitBtn.textContent = "确认保存";
  }

  function openSaveModal() {
    const role = roleById(state.selectedRoleId);
    if (!role) {
      showFeedback("danger", "请先选择角色");
      return;
    }

    const editorState = currentEditorState();
    if (!hasPendingChanges(role, editorState)) {
      showFeedback("info", "当前未检测到需要保存的变更");
      return;
    }

    (refs.saveChangeSummary.querySelector(".alert-body") || refs.saveChangeSummary).textContent = changeSummary(role, editorState);
    setSelectValue(refs.saveReasonCode, "");
    refs.saveReasonNote.value = "";
    setSaveReasonInvalid(false);
    showSaveError("");

    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(refs.saveModalEl);
    }
    saveModal.modal("show");
  }

  async function submitSave() {
    const role = roleById(state.selectedRoleId);
    if (!role) return;

    const editorState = currentEditorState();
    if (!hasPendingChanges(role, editorState)) {
      saveModal.modal("hide");
      showFeedback("info", "当前未检测到需要保存的变更");
      return;
    }

    const reasonCode = normalize(getSelectValue(refs.saveReasonCode));
    const reasonNote = text(refs.saveReasonNote.value);
    setSaveReasonInvalid(false);
    showSaveError("");

    if (!reasonCode) {
      setSaveReasonInvalid(true);
      showSaveError("请选择变更原因码后再提交。");
      return;
    }

    refs.saveRoleSubmitBtn.disabled = true;
    refs.saveRoleSubmitBtn.textContent = "保存中...";

    try {
      const payload = await requestJson(`/api/admin/roles/${encodeURIComponent(role.id)}/permissions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          data_scope: editorState.data_scope,
          permission_ids: editorState.permission_ids,
          change_reason_code: reasonCode,
          change_reason_note: reasonNote,
        }),
      });

      const summary = text(payload.change_summary) || "角色权限已更新";
      saveModal.modal("hide");
      showFeedback("success", `保存成功：${summary}`);
      await loadRoles(false);
      await loadRoleAuditTrail(state.selectedRoleId);
      
      // 刷新当前用户的权限信息（如果修改的是当前用户的角色）
      refreshCurrentUserPermissions();
    } catch (error) {
      showSaveError(`保存失败：${error.message || error}`);
    } finally {
      refs.saveRoleSubmitBtn.disabled = false;
      refs.saveRoleSubmitBtn.textContent = "确认保存";
    }
  }

  refs.reloadBtn.addEventListener("click", loadRoles);

  refs.toggleAdvancedBtn.addEventListener("click", () => {
    state.showAdvanced = !state.showAdvanced;
    root.classList.toggle("show-advanced", state.showAdvanced);
    refs.toggleAdvancedBtn.textContent = state.showAdvanced ? "隐藏高级信息" : "高级信息";
  });

  refs.rolesTableBody.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const toggleBtn = target.closest(".js-toggle-role-status");
    if (toggleBtn instanceof HTMLButtonElement) {
      const roleId = Number(toggleBtn.getAttribute("data-role-id") || 0);
      if (roleId <= 0) return;
      const role = roleById(roleId);
      const currentStatus = normalize(role && role.status) || "ACTIVE";
      const actionCn = currentStatus === "ACTIVE" ? "禁用" : "启用";
      if (!window.confirm(`确定要${actionCn}该角色吗？`)) return;
      toggleBtn.disabled = true;
      (async () => {
        try {
          await requestJson(`/api/admin/roles/${encodeURIComponent(roleId)}/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: "{}",
          });
          showFeedback("success", `${actionCn}成功`);
          await loadRoles(false);
        } catch (err) {
          showFeedback("warning", text(err && err.message) || `${actionCn}失败`);
        } finally {
          toggleBtn.disabled = false;
        }
      })();
      return;
    }

    const deleteBtn = target.closest(".js-delete-role");
    if (deleteBtn instanceof HTMLButtonElement) {
      const roleId = Number(deleteBtn.getAttribute("data-role-id") || 0);
      if (roleId <= 0) return;
      if (!window.confirm("确定要删除该角色吗？此操作不可恢复。")) return;
      deleteBtn.disabled = true;
      (async () => {
        try {
          await requestJson(`/api/admin/roles/${encodeURIComponent(roleId)}`, {
            method: "DELETE",
            headers: { Accept: "application/json" },
          });
          showFeedback("success", "角色已删除");
          await loadRoles(false);
        } catch (err) {
          showFeedback("warning", text(err && err.message) || "删除失败");
        } finally {
          deleteBtn.disabled = false;
        }
      })();
      return;
    }

    const roleItem = target.closest(".ra-role-item");
    if (roleItem) {
      const roleId = Number(roleItem.getAttribute("data-role-id") || 0);
      if (roleId > 0) openRole(roleId);
    }
  });

  refs.permissionGroupContainer.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const allBtn = target.closest(".js-group-select-all");
    if (allBtn instanceof HTMLButtonElement) {
      const groupKey = normalize(allBtn.getAttribute("data-group-key"));
      refs.permissionGroupContainer.querySelectorAll(`.js-role-permission[data-group-key="${groupKey}"]`).forEach((node) => {
        if (node instanceof HTMLInputElement) node.checked = true;
      });
      refreshEditorMeta();
      return;
    }

    const noneBtn = target.closest(".js-group-select-none");
    if (noneBtn instanceof HTMLButtonElement) {
      const groupKey = normalize(noneBtn.getAttribute("data-group-key"));
      refs.permissionGroupContainer.querySelectorAll(`.js-role-permission[data-group-key="${groupKey}"]`).forEach((node) => {
        if (node instanceof HTMLInputElement) node.checked = false;
      });
      refreshEditorMeta();
      return;
    }

    const groupHead = target.closest(".ra-perm-group-head");
    if (groupHead && !target.closest(".ra-grp-btn")) {
      const group = groupHead.closest(".ra-perm-group");
      if (group) group.classList.toggle("is-collapsed");
    }
  });

  refs.permissionGroupContainer.addEventListener("change", (event) => {
    if (event.target instanceof HTMLInputElement && event.target.classList.contains("js-role-permission")) {
      refreshEditorMeta();
    }
  });

  refs.editorDataScope.addEventListener("change", refreshEditorMeta);
  refs.resetDefaultsBtn.addEventListener("click", () => {
    const role = roleById(state.selectedRoleId);
    if (!role) {
      showFeedback("danger", "请先选择角色");
      return;
    }
    const defaults = roleDefaultTemplate(role);
    setSelectValue(refs.editorDataScope, defaults.dataScope);
    renderPermissionGroups(role, defaults.keySet);
    refreshEditorMeta();
    const sourceText = defaults.isBuiltin || text(defaults.sourceRoleName) === text(role.role_name)
      ? "已重置为该角色的出厂默认权限，请点击保存生效"
      : `已按「${defaults.sourceRoleName}」模板重置默认权限，请点击保存生效`;
    showFeedback("info", sourceText);
  });
  refs.saveBtn.addEventListener("click", openSaveModal);
  refs.saveRoleSubmitBtn.addEventListener("click", submitSave);

  refs.saveReasonCode.addEventListener("change", () => {
    if (normalize(getSelectValue(refs.saveReasonCode))) {
      setSaveReasonInvalid(false);
      showSaveError("");
    }
  });

  saveModal.on("hidden.bs.modal", clearSaveModalState);

  function showCreateRoleError(message) {
    const msg = text(message);
    refs.createRoleError.textContent = msg;
    refs.createRoleError.classList.toggle("d-none", !msg);
  }

  if (refs.openCreateRoleBtn) {
    refs.openCreateRoleBtn.addEventListener("click", () => {
      refs.newRoleName.value = "";
      showCreateRoleError("");
      refs.createRoleSubmitBtn.disabled = false;
      refs.createRoleSubmitBtn.textContent = "创建角色";
      createRoleModal.modal("show");
    });
  }

  refs.createRoleForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    showCreateRoleError("");
    const roleName = text(refs.newRoleName.value);
    if (!roleName) {
      showCreateRoleError("角色名称不能为空");
      return;
    }
    refs.createRoleSubmitBtn.disabled = true;
    refs.createRoleSubmitBtn.textContent = "创建中...";
    try {
      await requestJson("/api/admin/roles/create", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ role_name: roleName }),
      });
      createRoleModal.modal("hide");
      showFeedback("success", `角色「${roleName}」创建成功`);
      await loadRoles(false);
    } catch (err) {
      showCreateRoleError(text(err && err.message) || "创建失败");
    } finally {
      refs.createRoleSubmitBtn.disabled = false;
      refs.createRoleSubmitBtn.textContent = "创建角色";
    }
  });

  createRoleModal.on("hidden.bs.modal", () => {
    showCreateRoleError("");
    refs.createRoleSubmitBtn.disabled = false;
    refs.createRoleSubmitBtn.textContent = "创建角色";
  });

  const tabsCard = root.querySelector(".ra-tabs-card");
  if (tabsCard) {
    tabsCard.addEventListener("click", (e) => {
      const tab = e.target.closest(".ra-tab");
      if (!tab) return;
      const key = tab.dataset.tab;
      if (!key) return;
      tabsCard.querySelectorAll(".ra-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === key));
      tabsCard.querySelectorAll(".ra-tab-panel").forEach((p) => p.classList.toggle("active", p.dataset.tabPanel === key));
    });
  }

  // 刷新当前用户权限的函数
  function refreshCurrentUserPermissions() {
    if (typeof window.fetch !== 'function') return;
    
    fetch('/api/auth/refresh_permissions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    })
    .then(response => response.json())
    .then(data => {
      if (data && data.ok) {
        console.log('[权限刷新] 当前用户权限已刷新');
      }
    })
    .catch(err => {
      console.warn('[权限刷新] 刷新失败:', err);
    });
  }

  if (typeof window.initEnterpriseSelect === "function") {
    window.initEnterpriseSelect(root);
  }
  renderReasonOptions();
  renderRolesTable();
  applyEditorTitle(null);
  renderPermissionGroups(null);
  refreshEditorMeta();
  loadRoles();
})();
