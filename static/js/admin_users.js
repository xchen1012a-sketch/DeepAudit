(() => {
  const root = document.getElementById("admin-users-page");
  const initNode = document.getElementById("adminUsersInitPayload");
  if (!root || !initNode || !window.jQuery) return;

  let initPayload = {};
  try {
    initPayload = JSON.parse(initNode.textContent || "{}");
  } catch (_) {
    initPayload = {};
  }

  const refs = {
    feedback: document.getElementById("usersFeedback"),
    userCountBadge: document.getElementById("userCountBadge"),
    reloadBtn: document.getElementById("reloadUsersBtn"),
    batchDeleteBtn: document.getElementById("batchDeleteUsersBtn"),
    selectAllCheckbox: document.getElementById("usersSelectAll"),
    resetFiltersBtn: document.getElementById("resetFiltersBtn"),
    filterDepartment: document.getElementById("filterDepartment"),
    filterRole: document.getElementById("filterRole"),
    filterStatus: document.getElementById("filterStatus"),
    filterKeyword: document.getElementById("filterKeyword"),
    tableBody: document.getElementById("usersTableBody"),
    openCreateBtn: document.getElementById("openCreateUserBtn"),

    createModalEl: document.getElementById("createUserModal"),
    createForm: document.getElementById("createUserForm"),
    createSubmitBtn: document.getElementById("createUserSubmitBtn"),
    createError: document.getElementById("createUserError"),
    newUsername: document.getElementById("newUsername"),
    newPassword: document.getElementById("newPassword"),
    newDepartment: document.getElementById("newDepartment"),
    newRoleId: document.getElementById("newRoleId"),
    newPositionId: document.getElementById("newPositionId"),
    newPositionAddBtn: document.getElementById("newPositionAddBtn"),
    newEmployeeName: document.getElementById("newEmployeeName"),
    newEmployeeNo: document.getElementById("newEmployeeNo"),

    actionModalEl: document.getElementById("userActionModal"),
    actionTitle: document.getElementById("userActionTitle"),
    actionUserId: document.getElementById("actionUserId"),
    actionType: document.getElementById("actionType"),
    actionContextHint: document.getElementById("actionContextHint"),
    actionRoleWrap: document.getElementById("actionRoleWrap"),
    actionRoleId: document.getElementById("actionRoleId"),
    actionRoleError: document.getElementById("actionRoleError"),
    actionPositionWrap: document.getElementById("actionPositionWrap"),
    actionPositionId: document.getElementById("actionPositionId"),
    actionPositionError: document.getElementById("actionPositionError"),
    actionDepartmentWrap: document.getElementById("actionDepartmentWrap"),
    actionDepartment: document.getElementById("actionDepartment"),
    actionDepartmentError: document.getElementById("actionDepartmentError"),
    actionReasonCode: document.getElementById("actionReasonCode"),
    actionReasonError: document.getElementById("actionReasonError"),
    actionReasonNote: document.getElementById("actionReasonNote"),
    actionModalError: document.getElementById("actionModalError"),
    actionSubmitBtn: document.getElementById("actionSubmitBtn"),
  };

  if (
    !refs.feedback ||
    !refs.userCountBadge ||
    !refs.reloadBtn ||
    !refs.batchDeleteBtn ||
    !refs.selectAllCheckbox ||
    !refs.resetFiltersBtn ||
    !refs.filterDepartment ||
    !refs.filterRole ||
    !refs.filterStatus ||
    !refs.filterKeyword ||
    !refs.tableBody ||
    !refs.openCreateBtn ||
    !refs.createModalEl ||
    !refs.createForm ||
    !refs.createSubmitBtn ||
    !refs.createError ||
    !refs.newUsername ||
    !refs.newPassword ||
    !refs.newDepartment ||
    !refs.newRoleId ||
    !refs.newPositionId ||
    !refs.newEmployeeName ||
    !refs.newEmployeeNo ||
    !refs.actionModalEl ||
    !refs.actionTitle ||
    !refs.actionUserId ||
    !refs.actionType ||
    !refs.actionContextHint ||
    !refs.actionRoleWrap ||
    !refs.actionRoleId ||
    !refs.actionRoleError ||
    !refs.actionPositionWrap ||
    !refs.actionPositionId ||
    !refs.actionPositionError ||
    !refs.actionDepartmentWrap ||
    !refs.actionDepartment ||
    !refs.actionDepartmentError ||
    !refs.actionReasonCode ||
    !refs.actionReasonError ||
    !refs.actionReasonNote ||
    !refs.actionModalError ||
    !refs.actionSubmitBtn
  ) {
    return;
  }

  const STATUS_CN = {
    ACTIVE: "启用",
    DISABLED: "禁用",
  };

  const ACTION_CN = {
    USER_ENABLE: "启用",
    USER_DISABLE: "禁用",
    USER_RESET_PASSWORD: "重置密码",
    USER_ROLE_CHANGE: "改角色",
    USER_POSITION_CHANGE: "设置岗位",
    USER_DEPARTMENT_CHANGE: "改部门",
    USER_OFFBOARD: "离职/停用",
    DELETE_USER: "删除",
  };

  const ACTION_CONFIG = {
    disable: {
      title: "禁用用户",
      submitText: "确认禁用",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/disable`;
      },
      actionCode: "USER_DISABLE",
      roleRequired: false,
      positionRequired: false,
      departmentRequired: false,
      reasonNoteRequired: false,
    },
    enable: {
      title: "启用用户",
      submitText: "确认启用",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/enable`;
      },
      actionCode: "USER_ENABLE",
      roleRequired: false,
      positionRequired: false,
      departmentRequired: false,
      reasonNoteRequired: false,
    },
    reset_password: {
      title: "重置密码",
      submitText: "确认重置",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/reset_password`;
      },
      actionCode: "USER_RESET_PASSWORD",
      roleRequired: false,
      positionRequired: false,
      departmentRequired: false,
      reasonNoteRequired: false,
    },
    change_role: {
      title: "修改角色",
      submitText: "确认改角色",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/role`;
      },
      actionCode: "USER_ROLE_CHANGE",
      roleRequired: true,
      positionRequired: false,
      departmentRequired: false,
      reasonNoteRequired: false,
    },
    change_position: {
      title: "设置岗位",
      submitText: "确认设置",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/position`;
      },
      actionCode: "USER_POSITION_CHANGE",
      roleRequired: false,
      positionRequired: true,
      departmentRequired: false,
      reasonNoteRequired: false,
    },
    change_department: {
      title: "修改部门",
      submitText: "确认改部门",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/department`;
      },
      actionCode: "USER_DEPARTMENT_CHANGE",
      roleRequired: false,
      positionRequired: false,
      departmentRequired: true,
      reasonNoteRequired: false,
    },
    offboard: {
      title: "离职/停用",
      submitText: "确认离职/停用",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}/offboard`;
      },
      actionCode: "USER_OFFBOARD",
      roleRequired: false,
      positionRequired: false,
      departmentRequired: false,
      reasonNoteRequired: true,
    },
    delete_user: {
      title: "删除用户",
      submitText: "确认删除",
      endpoint(userId) {
        return `/api/admin/users/${encodeURIComponent(userId)}`;
      },
      method: "DELETE",
      actionCode: "DELETE_USER",
      roleRequired: false,
      positionRequired: false,
      departmentRequired: false,
      reasonNoteRequired: false,
    },
  };

  const state = {
    users: Array.isArray(initPayload.users) ? initPayload.users : [],
    roles: Array.isArray(initPayload.roles) ? initPayload.roles : [],
    activeRoles: Array.isArray(initPayload.active_roles) ? initPayload.active_roles : [],
    departments: Array.isArray(initPayload.departments) ? initPayload.departments : [],
    positions: Array.isArray(initPayload.positions) ? initPayload.positions : [],
    currentUserId: Number(initPayload.current_user_id || 0) || 0,
    latestActionByUser: new Map(),
    trailByUser: new Map(),
    trailOpen: new Set(),
    selectedUserIds: new Set(),
    filters: {
      department: "",
      roleId: "",
      status: "",
      keyword: "",
    },
  };

  const createModal = window.jQuery(refs.createModalEl);
  const actionModal = window.jQuery(refs.actionModalEl);

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

  function statusText(status) {
    return STATUS_CN[normalize(status)] || displayText(status);
  }

  function actionText(actionCode) {
    return ACTION_CN[normalize(actionCode)] || displayText(actionCode);
  }

  function roleScopeLabel(_scope) {
    return normalize(_scope) === "ALL" ? "全量数据" : "本部门数据";
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
    const optionList = Array.isArray(options) ? options : [];
    const selected = text(selectedValue);

    if (node.tomselect && typeof node.tomselect.clearOptions === "function") {
      const instance = node.tomselect;
      instance.clear(true);
      instance.clearOptions();
      optionList.forEach((item) => {
        instance.addOption({
          value: text(item.value),
          text: text(item.label),
        });
      });
      instance.refreshOptions(false);
      instance.setValue(selected, true);
      return;
    }

    node.innerHTML = optionList
      .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
      .join("");
    node.value = selected;
  }

  const ALERT_ICONS = {
    success: "ri-checkbox-circle-line",
    info: "ri-information-line",
    warning: "ri-error-warning-line",
    danger: "ri-close-circle-line",
  };

  function showFeedback(type, message, duration = 3000) {
    const tone = text(type) || "info";
    const msg = text(message) || "已完成操作";
    const icon = ALERT_ICONS[tone] || ALERT_ICONS.info;
    refs.feedback.className = `alert alert-${tone} py-2 px-3 mb-3`;
    refs.feedback.innerHTML =
      `<span class="alert-icon"><i class="${icon}"></i></span>` +
      `<span class="alert-body">${msg}</span>`;
    refs.feedback.classList.remove("d-none");

    clearTimeout(showFeedback._timer);
    showFeedback._timer = setTimeout(() => {
      refs.feedback.classList.add("d-none");
    }, Math.max(1200, Number(duration) || 3000));
  }

  function showCreateError(message = "") {
    const msg = text(message);
    refs.createError.textContent = msg;
    refs.createError.classList.toggle("d-none", !msg);
  }

  function showActionError(message = "") {
    const msg = text(message);
    refs.actionModalError.textContent = msg;
    refs.actionModalError.classList.toggle("d-none", !msg);
  }

  function setReasonInvalid(invalid) {
    refs.actionReasonCode.classList.toggle("is-invalid", !!invalid);
    refs.actionReasonError.classList.toggle("d-none", !invalid);
  }

  function setRoleInvalid(invalid) {
    refs.actionRoleId.classList.toggle("is-invalid", !!invalid);
    refs.actionRoleError.classList.toggle("d-none", !invalid);
  }

  function setPositionInvalid(invalid) {
    refs.actionPositionId.classList.toggle("is-invalid", !!invalid);
    refs.actionPositionError.classList.toggle("d-none", !invalid);
  }

  function setDepartmentInvalid(invalid) {
    refs.actionDepartment.classList.toggle("is-invalid", !!invalid);
    refs.actionDepartmentError.classList.toggle("d-none", !invalid);
  }

  function roleNames(user) {
    const roles = Array.isArray(user && user.roles) ? user.roles : [];
    const names = [];
    roles.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const name = text(item.role_name);
      if (name) names.push(name);
    });
    return names;
  }

  function roleIds(user) {
    const roles = Array.isArray(user && user.roles) ? user.roles : [];
    const ids = [];
    roles.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const id = Number(item.id || 0);
      if (id > 0) ids.push(id);
    });
    return ids;
  }

  function buildPositionOptions(includeEmpty = true) {
    const list = includeEmpty ? [{ value: "", label: "请选择或新增" }] : [];
    const sorted = (Array.isArray(state.positions) ? state.positions.slice() : []).sort((a, b) => {
      return text(a && a.name).localeCompare(text(b && b.name), "zh-CN");
    });
    sorted.forEach((pos) => {
      const id = Number(pos && pos.id || 0);
      if (id <= 0) return;
      list.push({ value: String(id), label: displayText(pos && pos.name) });
    });
    return list;
  }

  function buildDepartmentOptions() {
    const set = new Set();
    (Array.isArray(state.departments) ? state.departments : []).forEach((item) => {
      const value = text(item);
      if (value) set.add(value);
    });
    (Array.isArray(state.users) ? state.users : []).forEach((user) => {
      const value = text(user && user.department);
      if (value && value !== "-") set.add(value);
    });
    const options = Array.from(set).sort((a, b) => a.localeCompare(b, "zh-CN"));
    if (!options.length) {
      options.push("-");
    }
    return options;
  }

  function roleOptions(withAll = true) {
    const list = [];
    if (withAll) {
      list.push({ value: "", label: "全部角色" });
    }
    const sorted = (Array.isArray(state.roles) ? state.roles.slice() : []).sort((a, b) => {
      return text(a && a.role_name).localeCompare(text(b && b.role_name), "zh-CN");
    });
    sorted.forEach((role) => {
      const roleId = Number(role && role.id || 0);
      if (roleId <= 0) return;
      const roleName = displayText(role && role.role_name);
      const status = normalize(role && role.status);
      const suffix = status === "DISABLED" ? " (已禁用)" : "";
      list.push({ value: String(roleId), label: roleName + suffix });
    });
    return list;
  }

  function activeRoleOptions() {
    const list = [];
    const sorted = (Array.isArray(state.activeRoles) ? state.activeRoles.slice() : []).sort((a, b) => {
      return text(a && a.role_name).localeCompare(text(b && b.role_name), "zh-CN");
    });
    sorted.forEach((role) => {
      const roleId = Number(role && role.id || 0);
      if (roleId <= 0) return;
      list.push({ value: String(roleId), label: displayText(role && role.role_name) });
    });
    return list;
  }

  function renderFilterOptions() {
    const deptSelected = state.filters.department;
    const roleSelected = state.filters.roleId;
    const statusSelected = state.filters.status;

    const deptOptions = [{ value: "", label: "全部部门" }].concat(
      buildDepartmentOptions().map((name) => ({ value: name, label: name })),
    );
    rebuildSelect(refs.filterDepartment, deptOptions, deptSelected);
    rebuildSelect(refs.filterRole, roleOptions(true), roleSelected);
    rebuildSelect(
      refs.filterStatus,
      [
        { value: "", label: "全部状态" },
        { value: "ACTIVE", label: "启用" },
        { value: "DISABLED", label: "禁用" },
      ],
      statusSelected,
    );

    refs.filterKeyword.value = text(state.filters.keyword);
    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(root);
    }
  }

  function renderCreateFormOptions() {
    const departmentOptions = [{ value: "", label: "请选择部门" }].concat(
      buildDepartmentOptions().map((name) => ({ value: name, label: name })),
    );
    rebuildSelect(refs.newDepartment, departmentOptions, getSelectValue(refs.newDepartment));

    const createRoleList = activeRoleOptions().map((item) => {
      if (text(item.label) === "通用员工") {
        return { value: item.value, label: "通用员工(跨部门可用)" };
      }
      return item;
    });
    const createRoles = [{ value: "", label: "不分配角色" }].concat(createRoleList);
    rebuildSelect(refs.newRoleId, createRoles, getSelectValue(refs.newRoleId));

    const positionOptions = buildPositionOptions(true);
    rebuildSelect(refs.newPositionId, positionOptions, getSelectValue(refs.newPositionId));

    const actionRoles = [{ value: "", label: "请选择角色" }].concat(activeRoleOptions());
    rebuildSelect(refs.actionRoleId, actionRoles, getSelectValue(refs.actionRoleId));

    const actionPositions = [{ value: "", label: "请选择岗位" }].concat(buildPositionOptions(false));
    rebuildSelect(refs.actionPositionId, actionPositions, getSelectValue(refs.actionPositionId));

    const actionDepartments = [{ value: "", label: "请选择部门" }].concat(
      buildDepartmentOptions().map((name) => ({ value: name, label: name })),
    );
    rebuildSelect(refs.actionDepartment, actionDepartments, getSelectValue(refs.actionDepartment));

    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(document);
    }
  }

  function getLatestAction(userId, fallbackLatestAction) {
    const id = Number(userId || 0);
    if (id > 0 && state.latestActionByUser.has(id)) {
      return state.latestActionByUser.get(id);
    }
    if (fallbackLatestAction && typeof fallbackLatestAction === "object") {
      return fallbackLatestAction;
    }
    return null;
  }

  function latestActionText(user) {
    const latest = getLatestAction(user && user.id, user && user.latest_action);
    if (!latest) return "-";
    const actionCn = text(latest.action_cn) || actionText(latest.action);
    const createdAt = displayText(latest.created_at);
    if (!actionCn || actionCn === "-") return "-";
    return `${actionCn} · ${createdAt}`;
  }

  function renderRoleBadges(roles) {
    const list = Array.isArray(roles) ? roles : [];
    if (!list.length) return '<span class="text-muted" style="font-size:13px">-</span>';
    return `<div class="role-badges">${list
      .map((item) => {
        const roleName = displayText(item && item.role_name);
        return `<span class="badge badge-info">${escapeHtml(roleName)}</span>`;
      })
      .join("")}</div>`;
  }

  function statusHtml(status) {
    const code = normalize(status);
    if (code === "ACTIVE") {
      return '<span class="badge badge-success status-chip"><i class="ri-checkbox-circle-fill" style="margin-right:3px;font-size:12px;vertical-align:-1px;"></i>启用</span>';
    }
    return '<span class="badge badge-secondary status-chip">禁用</span>';
  }

  function matchesFilters(user) {
    const department = text(state.filters.department);
    if (department && text(user && user.department) !== department) {
      return false;
    }

    const status = normalize(state.filters.status);
    if (status && normalize(user && user.status) !== status) {
      return false;
    }

    const roleIdFilter = Number(state.filters.roleId || 0);
    if (roleIdFilter > 0) {
      const ids = roleIds(user);
      if (!ids.includes(roleIdFilter)) {
        return false;
      }
    }

    const keyword = text(state.filters.keyword).toLowerCase();
    if (!keyword) return true;

    const blob = [
      user && user.username,
      user && user.employee_name,
      user && user.employee_no,
      user && user.department,
      roleNames(user).join(" "),
      statusText(user && user.status),
    ]
      .map((item) => text(item).toLowerCase())
      .join(" ");
    return blob.includes(keyword);
  }

  function canSelectForDelete(user) {
    const userId = Number(user && user.id || 0);
    if (userId <= 0) return false;
    if (userId === state.currentUserId) return false;
    return Boolean(user && user.can_delete === true);
  }

  function filteredUsers() {
    return (Array.isArray(state.users) ? state.users : [])
      .filter((user) => user && typeof user === "object")
      .filter(matchesFilters)
      .sort((a, b) => Number(a.id || 0) - Number(b.id || 0));
  }

  function syncSelectedUserIds() {
    const allowed = new Set(
      (Array.isArray(state.users) ? state.users : [])
        .filter((user) => canSelectForDelete(user))
        .map((user) => Number(user && user.id || 0))
        .filter((id) => id > 0),
    );
    state.selectedUserIds.forEach((id) => {
      if (!allowed.has(id)) state.selectedUserIds.delete(id);
    });
  }

  function updateBatchDeleteControls(rows) {
    const visibleRows = Array.isArray(rows) ? rows : [];
    const selectableVisibleIds = visibleRows
      .filter((user) => canSelectForDelete(user))
      .map((user) => Number(user && user.id || 0))
      .filter((id) => id > 0);

    const totalSelected = state.selectedUserIds.size;
    refs.batchDeleteBtn.disabled = totalSelected <= 0;
    refs.batchDeleteBtn.textContent = totalSelected > 0 ? `批量删除（${totalSelected}）` : "批量删除";

    const selectedVisibleCount = selectableVisibleIds.reduce(
      (count, id) => count + (state.selectedUserIds.has(id) ? 1 : 0),
      0,
    );
    refs.selectAllCheckbox.disabled = selectableVisibleIds.length <= 0;
    refs.selectAllCheckbox.checked =
      selectableVisibleIds.length > 0 && selectedVisibleCount === selectableVisibleIds.length;
    refs.selectAllCheckbox.indeterminate =
      selectedVisibleCount > 0 && selectedVisibleCount < selectableVisibleIds.length;
  }

  function currentRoleId(user) {
    const ids = roleIds(user);
    return ids.length ? String(ids[0]) : "";
  }

  function assigneeValue(user) {
    return text(user && user.username);
  }

  function rowLinksHtml(user) {
    const assignee = assigneeValue(user);
    const approvalHref = assignee
      ? `/approval_center?assignee=${encodeURIComponent(assignee)}`
      : "/approval_center";
    const riskHref = assignee
      ? `/risk-center?assignee=${encodeURIComponent(assignee)}`
      : "/risk-center";

    return (
      '<div class="row-links">' +
      `<a href="${approvalHref}" target="_blank" rel="noopener"><i class="ri-file-list-3-line" style="margin-right:3px;font-size:13px;vertical-align:-1px;"></i>待办</a>` +
      `<a href="${riskHref}" target="_blank" rel="noopener"><i class="ri-shield-check-line" style="margin-right:3px;font-size:13px;vertical-align:-1px;"></i>风险案件</a>` +
      "</div>"
    );
  }

  function actionButtonsHtml(user) {
    const userId = Number(user && user.id || 0);
    if (userId <= 0) return '<span class="text-muted">-</span>';

    const status = normalize(user && user.status);
    const isCurrent = userId === state.currentUserId;
    const canDelete = Boolean(user && user.can_delete === true);

    const toggleLabel = status === "ACTIVE" ? "禁用" : "启用";
    const toggleAction = status === "ACTIVE" ? "disable" : "enable";
    const toggleClass = status === "ACTIVE" ? "btn-outline-danger" : "btn-outline-success";
    const toggleDisabled = isCurrent && status === "ACTIVE";
    const toggleTitle = toggleDisabled ? "当前账号不可禁用" : "";

    const offboardDisabled = status !== "ACTIVE" || isCurrent;
    const offboardTitle = offboardDisabled ? (isCurrent ? "当前账号不可操作" : "仅启用状态可离职/停用") : "禁用并清空角色与数据范围，必填原因";

    const deleteTitle = isCurrent ? "不能删除当前登录的账号" : (canDelete ? "删除该用户，删除后不可恢复" : "仅无业务/无审计记录的测试账号可删除，或需要DELETE_ANY_USER权限");
    const deleteDisabled = (!canDelete || isCurrent) ? "disabled" : "";

    const buttons = [
      `<button type="button" class="btn ${toggleClass} js-open-action" data-action="${toggleAction}" data-user-id="${userId}" ${toggleDisabled ? "disabled" : ""} title="${escapeHtml(toggleTitle)}">${toggleLabel}</button>`,
      `<div class="btn-group">
        <button type="button" class="btn btn-outline-secondary dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
          更多操作
        </button>
        <div class="dropdown-menu dropdown-menu-right">
          <a class="dropdown-item js-open-action" href="javascript:void(0)" data-action="change_role" data-user-id="${userId}">
            <i class="ri-shield-user-line" style="margin-right:6px;"></i>改角色
          </a>
          <a class="dropdown-item js-open-action" href="javascript:void(0)" data-action="change_department" data-user-id="${userId}">
            <i class="ri-building-line" style="margin-right:6px;"></i>改部门
          </a>
          <a class="dropdown-item js-open-action" href="javascript:void(0)" data-action="change_position" data-user-id="${userId}">
            <i class="ri-briefcase-line" style="margin-right:6px;"></i>设置岗位
          </a>
          <a class="dropdown-item js-open-action" href="javascript:void(0)" data-action="reset_password" data-user-id="${userId}">
            <i class="ri-lock-password-line" style="margin-right:6px;"></i>重置密码
          </a>
          <div class="dropdown-divider"></div>
          <a class="dropdown-item js-open-action ${offboardDisabled ? 'disabled text-muted' : ''}" href="javascript:void(0)" data-action="offboard" data-user-id="${userId}" title="${escapeHtml(offboardTitle)}">
            <i class="ri-user-unfollow-line" style="margin-right:6px;"></i>离职/停用
          </a>
          <a class="dropdown-item js-open-action ${deleteDisabled ? 'disabled text-muted' : 'text-danger'}" href="javascript:void(0)" data-action="delete_user" data-user-id="${userId}" title="${escapeHtml(deleteTitle)}">
            <i class="ri-delete-bin-line" style="margin-right:6px;"></i>删除
          </a>
        </div>
      </div>`,
      `<button type="button" class="btn btn-outline-secondary js-toggle-trail" data-user-id="${userId}">${state.trailOpen.has(userId) ? "收起留痕" : "查看留痕"}</button>`,
    ];
    return '<div class="action-group">' + buttons.join("") + '</div>';
  }

  function renderTrailRow(userId) {
    const trailState = state.trailByUser.get(userId);
    let contentHtml = '<div class="small text-muted">暂无留痕</div>';

    if (trailState && trailState.loading) {
      contentHtml = '<div class="small text-muted">留痕加载中...</div>';
    } else if (trailState && trailState.error) {
      contentHtml = `<div class="small text-danger">${escapeHtml(trailState.error)}</div>`;
    } else if (trailState && Array.isArray(trailState.logs) && trailState.logs.length > 0) {
      const listHtml = trailState.logs
        .map((item) => {
          const actionCn = text(item.action_cn) || actionText(item.action);
          const operator = displayText(item.operator);
          const reasonCn = text(item.change_reason_code_cn) || displayText(item.change_reason_code);
          const reasonRaw = displayText(item.change_reason_code);
          const note = displayText(item.note);
          const createdAt = displayText(item.created_at);

          return (
            "<li>" +
            `<div class="trail-main">${escapeHtml(actionCn)} · ${escapeHtml(createdAt)}</div>` +
            `<div class="trail-sub">操作者：${escapeHtml(operator)}</div>` +
            `<div class="trail-sub">原因码：${escapeHtml(reasonCn)} (${escapeHtml(reasonRaw)})</div>` +
            `<div class="trail-sub">说明：${escapeHtml(note)}</div>` +
            "</li>"
          );
        })
        .join("");

      contentHtml = `<ol class="trail-list">${listHtml}</ol>`;
    }

    return `
      <tr class="table-light" data-trail-row-for="${userId}">
        <td colspan="10">
          <div class="trail-card">${contentHtml}</div>
        </td>
      </tr>
    `;
  }

  function renderUsers() {
    syncSelectedUserIds();
    const rows = filteredUsers();

    refs.userCountBadge.textContent = `${rows.length} / ${state.users.length}`;

    if (!rows.length) {
      refs.tableBody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4" style="font-size:14px">暂无数据</td></tr>';
      updateBatchDeleteControls(rows);
      return;
    }

    const html = [];
    rows.forEach((user) => {
      const userId = Number(user.id || 0);
      const canSelectDelete = canSelectForDelete(user);
      const selected = state.selectedUserIds.has(userId);
      const username = displayText(user.username);
      const employeeName = displayText(user.employee_name);
      const employeeNo = displayText(user.employee_no);
      const department = displayText(user.department);

      const positionName = displayText(user.position_name);
      html.push(
        "<tr data-user-id=\"" + userId + "\">" +
          `<td class="select-cell"><input type="checkbox" class="js-user-select" data-user-id="${userId}" ${selected ? "checked" : ""} ${canSelectDelete ? "" : "disabled"}></td>` +
          `<td><span style="font-weight:500">${escapeHtml(username)}</span></td>` +
          `<td><div style="font-weight:500">${escapeHtml(employeeName)}</div><div class="user-meta-sub">工号：${escapeHtml(employeeNo)}</div></td>` +
          `<td>${escapeHtml(department)}</td>` +
          `<td>${escapeHtml(positionName)}</td>` +
          `<td>${renderRoleBadges(user.roles)}</td>` +
          `<td>${statusHtml(user.status)}</td>` +
          `<td>${rowLinksHtml(user)}</td>` +
          `<td class="latest-action">${escapeHtml(latestActionText(user))}</td>` +
          `<td>${actionButtonsHtml(user)}</td>` +
        "</tr>",
      );

      if (state.trailOpen.has(userId)) {
        html.push(renderTrailRow(userId));
      }
    });

    refs.tableBody.innerHTML = html.join("");
    updateBatchDeleteControls(rows);
  }

  function mergeUser(user) {
    if (!user || typeof user !== "object") return;
    const id = Number(user.id || 0);
    if (id <= 0) return;

    const idx = state.users.findIndex((item) => Number(item && item.id || 0) === id);
    if (idx >= 0) {
      state.users[idx] = user;
      return;
    }
    state.users.push(user);
  }

  function attachLatestAction(userId, latestAction) {
    const id = Number(userId || 0);
    if (id <= 0 || !latestAction || typeof latestAction !== "object") return;
    state.latestActionByUser.set(id, latestAction);

    const trailState = state.trailByUser.get(id);
    if (trailState && Array.isArray(trailState.logs)) {
      trailState.logs.unshift({
        action: text(latestAction.action),
        action_cn: text(latestAction.action_cn) || actionText(latestAction.action),
        operator: displayText(latestAction.operator),
        change_reason_code: displayText(latestAction.change_reason_code),
        change_reason_code_cn: displayText(latestAction.change_reason_code_cn),
        note: displayText(latestAction.note),
        created_at: displayText(latestAction.created_at),
      });
      state.trailByUser.set(id, trailState);
    }
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload || payload.ok !== true) {
      throw new Error(text(payload.message) || text(payload.msg) || `HTTP ${response.status}`);
    }
    return payload;
  }

  async function deleteUserById(userId) {
    const normalizedId = Number(userId || 0);
    if (normalizedId <= 0) return;
    await requestJson(`/api/admin/users/${encodeURIComponent(normalizedId)}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    state.users = state.users.filter((u) => Number(u && u.id || 0) !== normalizedId);
    state.latestActionByUser.delete(normalizedId);
    state.trailByUser.delete(normalizedId);
    state.trailOpen.delete(normalizedId);
    state.selectedUserIds.delete(normalizedId);
  }

  async function batchDeleteSelectedUsers() {
    const ids = Array.from(state.selectedUserIds).filter((id) => id > 0);
    if (!ids.length) {
      showFeedback("warning", "请先选择要删除的员工");
      return;
    }
    if (!window.confirm(`确定要批量删除选中的 ${ids.length} 名员工吗？删除后不可恢复。`)) {
      return;
    }

    refs.batchDeleteBtn.disabled = true;
    const originalText = refs.batchDeleteBtn.textContent;
    refs.batchDeleteBtn.textContent = "删除中...";

    let successCount = 0;
    let failedCount = 0;
    for (const userId of ids) {
      const user = state.users.find((item) => Number(item && item.id || 0) === userId);
      if (!canSelectForDelete(user)) {
        failedCount += 1;
        continue;
      }
      try {
        await deleteUserById(userId);
        successCount += 1;
      } catch (_) {
        failedCount += 1;
      }
    }

    renderUsers();
    if (failedCount > 0) {
      const tone = successCount > 0 ? "warning" : "danger";
      showFeedback(tone, `批量删除完成：成功 ${successCount} 人，失败 ${failedCount} 人`);
    } else {
      showFeedback("success", `批量删除成功：共删除 ${successCount} 人`);
    }

    refs.batchDeleteBtn.disabled = false;
    refs.batchDeleteBtn.textContent = originalText || "批量删除";
  }

  async function loadUsers() {
    try {
      const payload = await requestJson("/api/admin/users", {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });

      state.users = Array.isArray(payload.users) ? payload.users : [];
      state.roles = Array.isArray(payload.roles) ? payload.roles : state.roles;
      state.activeRoles = Array.isArray(payload.active_roles) ? payload.active_roles : state.activeRoles;
      state.departments = Array.isArray(payload.departments) ? payload.departments : state.departments;
      state.positions = Array.isArray(payload.positions) ? payload.positions : state.positions;
      state.currentUserId = Number(payload.current_user_id || state.currentUserId || 0);

      renderFilterOptions();
      renderCreateFormOptions();
      renderUsers();
    } catch (error) {
      showFeedback("danger", `加载失败：${error.message || error}`);
    }
  }

  function activeActionConfig() {
    const key = text(refs.actionType.value);
    return ACTION_CONFIG[key] || null;
  }

  function clearActionModalState() {
    refs.actionUserId.value = "0";
    refs.actionType.value = "";
    refs.actionTitle.textContent = "敏感操作";
    (refs.actionContextHint.querySelector(".alert-body") || refs.actionContextHint).textContent = "请选择处理原因后提交。";
    refs.actionReasonNote.value = "";
    const noteLabel = document.getElementById("actionReasonNoteLabel");
    if (noteLabel) noteLabel.textContent = "补充说明（可选）";
    setSelectValue(refs.actionReasonCode, "");
    setSelectValue(refs.actionRoleId, "");
    setSelectValue(refs.actionPositionId, "");
    setSelectValue(refs.actionDepartment, "");
    refs.actionSubmitBtn.textContent = "确认提交";
    refs.actionSubmitBtn.disabled = false;
    refs.actionRoleWrap.classList.add("d-none");
    refs.actionPositionWrap.classList.add("d-none");
    refs.actionDepartmentWrap.classList.add("d-none");
    setReasonInvalid(false);
    setRoleInvalid(false);
    setPositionInvalid(false);
    setDepartmentInvalid(false);
    showActionError("");
  }

  function openActionModal(actionKey, userId) {
    const config = ACTION_CONFIG[actionKey];
    const id = Number(userId || 0);
    if (!config || id <= 0) return;

    const user = state.users.find((item) => Number(item && item.id || 0) === id);
    if (!user) return;

    refs.actionUserId.value = String(id);
    refs.actionType.value = actionKey;
    refs.actionTitle.textContent = config.title;
    refs.actionSubmitBtn.textContent = config.submitText;

    const roleSummary = roleNames(user).join("、") || "-";
    const positionName = displayText(user.position_name);
    const hintBody = refs.actionContextHint.querySelector(".alert-body") || refs.actionContextHint;
    hintBody.textContent = `用户：${displayText(user.username)} | 角色：${roleSummary} | 岗位：${positionName} | 状态：${statusText(user.status)}`;
    if (actionKey === "offboard") {
      hintBody.textContent += "（将禁用并清空角色与数据范围，原因说明必填）";
    }

    refs.actionRoleWrap.classList.toggle("d-none", !config.roleRequired);
    if (config.roleRequired) {
      setSelectValue(refs.actionRoleId, currentRoleId(user));
    } else {
      setSelectValue(refs.actionRoleId, "");
    }

    refs.actionPositionWrap.classList.toggle("d-none", !config.positionRequired);
    if (config.positionRequired) {
      const currentPositionId = user.position_id ? String(user.position_id) : "";
      setSelectValue(refs.actionPositionId, currentPositionId);
    } else {
      setSelectValue(refs.actionPositionId, "");
    }

    refs.actionDepartmentWrap.classList.toggle("d-none", !config.departmentRequired);
    if (config.departmentRequired) {
      setSelectValue(refs.actionDepartment, text(user.department));
    } else {
      setSelectValue(refs.actionDepartment, "");
    }

    const noteLabel = document.getElementById("actionReasonNoteLabel");
    if (noteLabel) {
      noteLabel.textContent = config.reasonNoteRequired ? "补充说明（必填）" : "补充说明（可选）";
    }
    setSelectValue(refs.actionReasonCode, "");
    refs.actionReasonNote.value = "";
    setReasonInvalid(false);
    setRoleInvalid(false);
    setPositionInvalid(false);
    setDepartmentInvalid(false);
    showActionError("");

    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(refs.actionModalEl);
    }
    actionModal.modal("show");
  }

  async function submitAction() {
    const config = activeActionConfig();
    const userId = Number(refs.actionUserId.value || 0);
    if (!config || userId <= 0) return;

    const reasonCode = normalize(getSelectValue(refs.actionReasonCode));
    const reasonNote = text(refs.actionReasonNote.value);

    setReasonInvalid(false);
    setRoleInvalid(false);
    setPositionInvalid(false);
    setDepartmentInvalid(false);
    showActionError("");

    if (!reasonCode) {
      setReasonInvalid(true);
      showActionError("请选择处理原因码后再提交。");
      return;
    }
    if (config.reasonNoteRequired && !reasonNote) {
      setReasonInvalid(true);
      showActionError("离职/停用必须填写原因说明。");
      return;
    }

    const payload = {
      change_reason_code: reasonCode,
      change_reason_note: reasonNote,
    };

    if (config.roleRequired) {
      const roleId = Number(getSelectValue(refs.actionRoleId) || 0);
      if (roleId <= 0) {
        setRoleInvalid(true);
        showActionError("请选择目标角色后再提交。");
        return;
      }
      payload.role_id = roleId;
    }

    if (config.positionRequired) {
      const positionId = Number(getSelectValue(refs.actionPositionId) || 0);
      if (positionId <= 0) {
        setPositionInvalid(true);
        showActionError("请选择目标岗位后再提交。");
        return;
      }
      payload.position_id = positionId;
    }

    if (config.departmentRequired) {
      const department = text(getSelectValue(refs.actionDepartment));
      if (!department) {
        setDepartmentInvalid(true);
        showActionError("请选择目标部门后再提交。");
        return;
      }
      payload.department = department;
    }

    refs.actionSubmitBtn.disabled = true;
    const originalText = refs.actionSubmitBtn.textContent;
    refs.actionSubmitBtn.textContent = "提交中...";

    try {
      const response = await requestJson(config.endpoint(userId), {
        method: config.method || "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (response.user && typeof response.user === "object") {
        mergeUser(response.user);
      }
      if (text(config.actionCode) === "DELETE_USER") {
        const normalizedId = Number(userId || 0);
        if (normalizedId > 0) {
          state.users = state.users.filter((item) => Number(item && item.id || 0) !== normalizedId);
          state.latestActionByUser.delete(normalizedId);
          state.trailByUser.delete(normalizedId);
          state.trailOpen.delete(normalizedId);
          state.selectedUserIds.delete(normalizedId);
        }
      } else if (response.latest_action && typeof response.latest_action === "object") {
        attachLatestAction(userId, response.latest_action);
      } else {
        attachLatestAction(userId, {
          action: config.actionCode,
          action_cn: actionText(config.actionCode),
          operator: "当前操作人",
          change_reason_code: reasonCode,
          change_reason_code_cn: reasonCode,
          note: reasonNote || "-",
          created_at: new Date().toISOString().slice(0, 19).replace("T", " "),
        });
      }

      renderUsers();
      actionModal.modal("hide");

      if (text(config.actionCode) === "USER_RESET_PASSWORD") {
        const pwd = text(response.default_password) || "默认强口令";
        showFeedback("success", `重置密码成功，默认密码：${pwd}`);
      } else {
        showFeedback("success", `${actionText(config.actionCode)}成功`);
      }
      
      // 如果是修改角色操作，刷新当前用户的权限信息
      if (config.roleRequired && typeof window.refreshCurrentUserPermissions === 'function') {
        window.refreshCurrentUserPermissions().catch(() => {
          // 忽略刷新失败
        });
      }
    } catch (error) {
      showActionError(`提交失败：${error.message || error}`);
    } finally {
      refs.actionSubmitBtn.disabled = false;
      refs.actionSubmitBtn.textContent = originalText || "确认提交";
    }
  }

  async function submitCreateUser(event) {
    event.preventDefault();
    showCreateError("");

    const roleId = Number(getSelectValue(refs.newRoleId) || 0);
    const positionIdRaw = getSelectValue(refs.newPositionId);
    const positionId = positionIdRaw ? Number(positionIdRaw) : null;

    const payload = {
      username: text(refs.newUsername.value),
      password: text(refs.newPassword.value),
      department: text(getSelectValue(refs.newDepartment)),
      role_id: roleId,
      employee_name: text(refs.newEmployeeName.value),
      employee_no: text(refs.newEmployeeNo.value),
    };
    if (positionId != null && positionId > 0) {
      payload.position_id = positionId;
    }

    if (!payload.username || !payload.password || !payload.department) {
      showCreateError("请完整填写用户名、密码和部门。");
      return;
    }

    refs.createSubmitBtn.disabled = true;
    const originalText = refs.createSubmitBtn.textContent;
    refs.createSubmitBtn.textContent = "创建中...";

    try {
      const result = await requestJson("/api/admin/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (result.user && typeof result.user === "object") {
        mergeUser(result.user);
      }

      const dept = text(payload.department);
      if (dept && dept !== "-" && !state.departments.includes(dept)) {
        state.departments.push(dept);
      }

      renderFilterOptions();
      renderCreateFormOptions();
      renderUsers();

      refs.createForm.reset();
      setSelectValue(refs.newDepartment, "");
      setSelectValue(refs.newRoleId, "");
      setSelectValue(refs.newPositionId, "");
      createModal.modal("hide");
      showFeedback("success", "新增用户成功");
    } catch (error) {
      showCreateError(`创建失败：${error.message || error}`);
    } finally {
      refs.createSubmitBtn.disabled = false;
      refs.createSubmitBtn.textContent = originalText || "创建用户";
    }
  }

  async function loadUserTrail(userId) {
    const id = Number(userId || 0);
    if (id <= 0) return;

    const current = state.trailByUser.get(id);
    if (current && current.loading) return;

    state.trailByUser.set(id, { loading: true, error: "", logs: [] });
    renderUsers();

    try {
      const result = await requestJson(`/api/admin/users/${encodeURIComponent(id)}/audit_trail?limit=50`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      state.trailByUser.set(id, {
        loading: false,
        error: "",
        logs: Array.isArray(result.logs) ? result.logs : [],
      });
    } catch (error) {
      state.trailByUser.set(id, {
        loading: false,
        error: text(error && error.message) || "加载失败",
        logs: [],
      });
    }
    renderUsers();
  }

  function toggleTrail(userId) {
    const id = Number(userId || 0);
    if (id <= 0) return;
    if (state.trailOpen.has(id)) {
      state.trailOpen.delete(id);
      renderUsers();
      return;
    }
    state.trailOpen.add(id);
    renderUsers();
    loadUserTrail(id);
  }

  function updateFiltersFromUI() {
    state.filters.department = text(getSelectValue(refs.filterDepartment));
    state.filters.roleId = text(getSelectValue(refs.filterRole));
    state.filters.status = text(getSelectValue(refs.filterStatus));
    state.filters.keyword = text(refs.filterKeyword.value);
    renderUsers();
  }

  function resetFilters() {
    state.filters.department = "";
    state.filters.roleId = "";
    state.filters.status = "";
    state.filters.keyword = "";
    setSelectValue(refs.filterDepartment, "");
    setSelectValue(refs.filterRole, "");
    setSelectValue(refs.filterStatus, "");
    refs.filterKeyword.value = "";
    renderUsers();
  }

  refs.openCreateBtn.addEventListener("click", () => {
    showCreateError("");
    refs.createForm.reset();
    setSelectValue(refs.newDepartment, "");
    setSelectValue(refs.newRoleId, "");
    setSelectValue(refs.newPositionId, "");
    renderCreateFormOptions();
    if (typeof window.initEnterpriseSelect === "function") {
      window.initEnterpriseSelect(refs.createModalEl);
    }
    createModal.modal("show");
  });

  refs.newPositionAddBtn.addEventListener("click", async () => {
    const name = window.prompt("请输入新岗位名称");
    const trimmed = text(name);
    if (!trimmed) return;
    try {
      const result = await requestJson("/api/admin/positions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (result.position && result.position.id) {
        state.positions = state.positions || [];
        if (!state.positions.some((p) => Number(p && p.id) === result.position.id)) {
          state.positions.push(result.position);
        }
        renderCreateFormOptions();
        setSelectValue(refs.newPositionId, String(result.position.id));
        showFeedback("success", "岗位已新增，已自动选中");
      }
    } catch (err) {
      showCreateError(text(err && err.message) || "新增岗位失败");
    }
  });

  refs.createForm.addEventListener("submit", submitCreateUser);

  refs.reloadBtn.addEventListener("click", loadUsers);
  refs.batchDeleteBtn.addEventListener("click", batchDeleteSelectedUsers);
  refs.resetFiltersBtn.addEventListener("click", resetFilters);

  refs.filterDepartment.addEventListener("change", updateFiltersFromUI);
  refs.filterRole.addEventListener("change", updateFiltersFromUI);
  refs.filterStatus.addEventListener("change", updateFiltersFromUI);
  refs.filterKeyword.addEventListener("input", () => {
    state.filters.keyword = text(refs.filterKeyword.value);
    renderUsers();
  });

  refs.selectAllCheckbox.addEventListener("change", () => {
    const rows = filteredUsers();
    const ids = rows
      .filter((user) => canSelectForDelete(user))
      .map((user) => Number(user && user.id || 0))
      .filter((id) => id > 0);
    if (refs.selectAllCheckbox.checked) {
      ids.forEach((id) => state.selectedUserIds.add(id));
    } else {
      ids.forEach((id) => state.selectedUserIds.delete(id));
    }
    renderUsers();
  });

  refs.tableBody.addEventListener("change", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const checkbox = target.closest(".js-user-select");
    if (!(checkbox instanceof HTMLInputElement)) return;
    const userId = Number(checkbox.getAttribute("data-user-id") || 0);
    if (userId <= 0) return;
    if (checkbox.checked) state.selectedUserIds.add(userId);
    else state.selectedUserIds.delete(userId);
    updateBatchDeleteControls(filteredUsers());
  });

  refs.tableBody.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const actionBtn = target.closest(".js-open-action");
    if (actionBtn && !actionBtn.classList.contains('disabled')) {
      const action = text(actionBtn.getAttribute("data-action"));
      const userId = Number(actionBtn.getAttribute("data-user-id") || 0);
      openActionModal(action, userId);
      return;
    }

    const trailBtn = target.closest(".js-toggle-trail");
    if (trailBtn instanceof HTMLButtonElement) {
      const userId = Number(trailBtn.getAttribute("data-user-id") || 0);
      toggleTrail(userId);
      return;
    }

  });

  refs.actionReasonCode.addEventListener("change", () => {
    if (normalize(getSelectValue(refs.actionReasonCode))) {
      setReasonInvalid(false);
      showActionError("");
    }
  });

  refs.actionRoleId.addEventListener("change", () => {
    if (Number(getSelectValue(refs.actionRoleId) || 0) > 0) {
      setRoleInvalid(false);
      showActionError("");
    }
  });

  refs.actionDepartment.addEventListener("change", () => {
    if (text(getSelectValue(refs.actionDepartment))) {
      setDepartmentInvalid(false);
      showActionError("");
    }
  });

  refs.actionSubmitBtn.addEventListener("click", submitAction);

  actionModal.on("hidden.bs.modal", () => {
    clearActionModalState();
  });

  createModal.on("hidden.bs.modal", () => {
    showCreateError("");
    refs.createSubmitBtn.disabled = false;
    refs.createSubmitBtn.textContent = "创建用户";
  });

  renderFilterOptions();
  renderCreateFormOptions();
  renderUsers();
  loadUsers();
})();
