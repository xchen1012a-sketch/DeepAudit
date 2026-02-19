from __future__ import annotations

import importlib
from typing import Any

from flask import Flask


def _register_blueprint_module(
    app: Flask,
    module_name: str,
    *,
    attr_name: str = "bp",
    required: bool = True,
) -> bool:
    try:
        module = importlib.import_module(module_name)
        blueprint = getattr(module, attr_name)
        app.register_blueprint(blueprint)
        return True
    except Exception as exc:  # pragma: no cover - defensive boot guard
        app.logger.exception("Failed to register blueprint %s: %s", module_name, exc)
        errors: dict[str, str] = app.config.setdefault("BLUEPRINT_LOAD_ERRORS", {})
        errors[module_name] = str(exc)
        if required:
            raise
        return False


def register_blueprints(app: Flask) -> None:
    # Core auth route: keep login available whenever possible.
    _register_blueprint_module(app, "routes.auth", required=True)

    # Feature routes: best-effort. Failure should not block login/startup.
    _register_blueprint_module(app, "routes.dashboard", required=False)
    _register_blueprint_module(app, "routes.ledger", required=False)
    _register_blueprint_module(app, "routes.risk", required=False)
    _register_blueprint_module(app, "routes.approval", required=False)
    _register_blueprint_module(app, "routes.invoices", required=False)
    _register_blueprint_module(app, "routes.approvals", required=False)
    _register_blueprint_module(app, "routes.bank_api", required=False)
    _register_blueprint_module(app, "routes.events_api", required=False)
    _register_blueprint_module(app, "routes.risk_api", required=False)
    _register_blueprint_module(app, "routes.admin_iam", required=False)
    _register_blueprint_module(app, "routes.governance", required=False)
    _register_blueprint_module(app, "routes.audit_chain", required=False)
    _register_blueprint_module(app, "routes.enterprise", required=False)
    _register_blueprint_module(app, "routes.integrations", required=False)
    _register_blueprint_module(app, "routes.monitoring", required=False)
    _register_blueprint_module(app, "routes.knowledge", required=False)
    _register_blueprint_module(app, "routes.search", required=False)
    _register_blueprint_module(app, "routes.audit_log", required=False)
    _register_blueprint_module(app, "routes.pbi_api", required=False)
