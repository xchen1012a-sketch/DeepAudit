(() => {
  if (typeof window.TomSelect === "undefined") {
    console.warn("[enterprise-select] TomSelect not loaded.");
    return;
  }

  const instances = new Map();
  const optionTexts = {
    noResults: "未找到匹配项",
    loading: "加载中...",
    placeholder: "请选择",
  };

  const isElement = (node) => node && node.nodeType === 1;
  const countSelectableOptions = (select) =>
    Array.from(select.options || []).filter((option) => String(option.value || "").trim() !== "").length;

  const initSelect = (select) => {
    if (!isElement(select) || instances.has(select) || select.tomselect) return;

    // Keep native select when there is only one selectable option.
    if (countSelectableOptions(select) <= 1 && String(select.dataset.enhanceSingle || "") !== "1") {
      return;
    }

    const placeholder =
      select.getAttribute("placeholder") ||
      (select.querySelector("option[value='']") || {}).textContent ||
      optionTexts.placeholder;

    /* 默认不显示清除按钮（小 x），避免下拉框旁多余图标；仅当 data-clear-button="1" 时显示 */
    const clearButtonEnabled = String(select.dataset.clearButton || "0") === "1";
    const plugins = ["dropdown_input"];
    if (clearButtonEnabled) {
      plugins.push("clear_button");
    }

    const config = {
      maxOptions: Number(select.dataset.maxOptions || 200),
      allowEmptyOption: true,
      placeholder,
      create: false,
      closeAfterSelect: true,
      sortField: [{ field: "$order" }, { field: "text", direction: "asc" }],
      plugins,
      render: {
        no_results: () => `<div class="no-results py-2 px-3 text-muted">${optionTexts.noResults}</div>`,
        loading: () => `<div class="py-2 px-3 text-muted">${optionTexts.loading}</div>`,
      },
    };

    const instance = new window.TomSelect(select, config);

    const syncInvalid = () => {
      const invalid = select.classList.contains("is-invalid");
      if (instance.control) {
        instance.control.classList.toggle("is-invalid", invalid);
      }
    };
    const observer = new MutationObserver(syncInvalid);
    observer.observe(select, { attributes: true, attributeFilter: ["class"] });
    syncInvalid();

    instances.set(select, instance);
  };

  const initAll = (root = document) => {
    const scope = isElement(root) ? root : document;
    scope.querySelectorAll("select.enterprise-select").forEach(initSelect);
  };

  const refreshDropdowns = () => {
    instances.forEach((instance) => {
      if (instance && typeof instance.positionDropdown === "function") {
        instance.positionDropdown();
      }
    });
  };

  document.addEventListener("DOMContentLoaded", () => {
    initAll();
    refreshDropdowns();
  });

  if (window.jQuery) {
    window.jQuery(document).on("shown.bs.modal", ".modal", (event) => {
      initAll(event.target || document);
      refreshDropdowns();
    });
  }

  window.initEnterpriseSelect = initAll;
})();
