(function () {
  "use strict";
  if (window.DeepAuditAudit) {
    return;
  }
  const script = document.createElement("script");
  script.src = "/static/js/audit.js";
  script.async = false;
  document.head.appendChild(script);
})();
