from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from flask import Flask, g, jsonify, render_template_string, request, session

from core.extensions import init_extensions
from core.logging import configure_logging
from core.settings import Settings
from routes import register_blueprints
from tasks.scheduler import start_scheduler
from utils.db import DB_PATH, DEFAULT_WEAK_PASSWORD, init_db, list_users_with_password
from utils.permission_meta import permission_label_cn
from utils.security import (
    access_level,
    access_level_cn,
    can_access_approval_console,
    can_governance,
    can_manage_workflow,
    current_data_scope,
    current_user,
    current_user_permissions,
    ensure_csrf_token,
    has_permission,
    get_csrf_token,
    validate_csrf_request,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_CURRENCY_SYMBOLS = {
    "CNY": "¥",
    "RMB": "¥",
    "USD": "$",
    "HKD": "HK$",
}
_DASHSCOPE_PLACEHOLDERS = {"", "sk-...", "your_dashscope_api_key", "replace_me"}
_SECRET_KEY_PLACEHOLDERS = {"", "dev-secret-key", "replace-with-a-random-secret-key", "change-me", "your-secret-key"}


def _clean_value(value: Any) -> Any:
    if value is None:
        return "-"
    if isinstance(value, str):
        text = value.strip()
        if not text or "?" in text:
            return "-"
        return text
    return value


def _parse_amount(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def _format_amount(value: Any, currency: Any) -> str:
    num = _parse_amount(value)
    if num is None:
        return "-"

    cur = str(currency or "").strip().upper()
    if not cur or cur == "-":
        cur = "CNY"

    symbol = _CURRENCY_SYMBOLS.get(cur, cur)
    formatted = "{:,.2f}".format(num)
    if symbol in {"¥", "$", "HK$"}:
        return f"{symbol}{formatted}"
    if symbol:
        return f"{symbol} {formatted}"
    return formatted


def clean_invoice_rows(rows: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not rows:
        return []

    cleaned_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for key, value in dict(row).items():
            normalized[key] = _clean_value(value)

        normalized["amount"] = _format_amount(
            normalized.get("amount"),
            normalized.get("currency"),
        )
        cleaned_rows.append(normalized)
    return cleaned_rows


def _should_start_scheduler(app: Flask) -> bool:
    if not bool(app.config.get("ENABLE_SCHEDULER", False)):
        return False

    # In debug reloader mode, only start from the reloader child process.
    debug_env = str(os.getenv("FLASK_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}
    debug_enabled = bool(app.config.get("DEBUG", False)) or debug_env
    if debug_enabled:
        return os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    return True


def _register_template_context(app: Flask) -> None:
    def _safe_nav_context() -> dict[str, Any]:
        try:
            user = current_user() or {}
        except Exception:
            user = {}
        try:
            raw_permissions = current_user_permissions(user)
        except Exception:
            raw_permissions = set()
        permissions = set()
        for item in raw_permissions:
            try:
                key = str(item or "").strip().upper()
                if key and has_permission(key, user):
                    permissions.add(key)
            except Exception:
                pass

        def nav_has_permission(permission_key: str) -> bool:
            try:
                key = str(permission_key or "").strip().upper()
                if not key:
                    return False
                return has_permission(key, user)
            except Exception:
                return False

        def nav_has_any_permission(permission_keys: list[str] | tuple[str, ...] | set[str]) -> bool:
            for item in permission_keys or []:
                if nav_has_permission(str(item)):
                    return True
            return False

        def _safe_data_scope() -> str:
            try:
                return current_data_scope(user) if user else "DEPT"
            except Exception:
                return "DEPT"

        def _safe_access_level() -> str:
            try:
                return access_level(user) if user else "A"
            except Exception:
                return "A"

        def _safe_access_level_cn() -> str:
            try:
                return access_level_cn(user) if user else "普通员工"
            except Exception:
                return "普通员工"

        def _safe_bool(fn, default: bool = False) -> bool:
            try:
                return bool(fn(user)) if user else default
            except Exception:
                return default

        out = {
            "nav_user": user,
            "nav_permissions": permissions,
            "nav_data_scope": _safe_data_scope(),
            "nav_access_level": _safe_access_level(),
            "nav_access_level_cn": _safe_access_level_cn(),
            "nav_can_approval_console": _safe_bool(can_access_approval_console),
            "nav_can_workflow_manage": _safe_bool(can_manage_workflow),
            "nav_can_governance": _safe_bool(can_governance),
            "nav_has_permission": nav_has_permission,
            "nav_has_any_permission": nav_has_any_permission,
            "permission_label_cn": permission_label_cn,
            "csrf_token": "",
            "app_version": str(app.config.get("APP_VERSION") or ""),
            "static_version": str(app.config.get("STATIC_VERSION") or ""),
        }
        try:
            out["csrf_token"] = get_csrf_token()
        except Exception:
            pass
        return out

    @app.context_processor
    def _inject_nav_context() -> dict[str, Any]:
        try:
            return _safe_nav_context()
        except Exception as e:
            app.logger.exception("nav context failed: %s", e)
            try:
                csrf = get_csrf_token()
            except Exception:
                csrf = ""
            return {
                "nav_user": {},
                "nav_permissions": set(),
                "nav_data_scope": "DEPT",
                "nav_access_level": "A",
                "nav_access_level_cn": "普通员工",
                "nav_can_approval_console": False,
                "nav_can_workflow_manage": False,
                "nav_can_governance": False,
                "nav_has_permission": lambda _: False,
                "nav_has_any_permission": lambda _: False,
                "permission_label_cn": permission_label_cn,
                "csrf_token": csrf,
                "app_version": str(app.config.get("APP_VERSION") or ""),
                "static_version": str(app.config.get("STATIC_VERSION") or ""),
            }


def _wants_json_response() -> bool:
    if request.path.startswith("/api/") or request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _log_dashscope_key_status(app: Flask) -> None:
    raw_key = str(app.config.get("DASHSCOPE_API_KEY") or "").strip()
    lowered = raw_key.lower()
    if lowered in _DASHSCOPE_PLACEHOLDERS:
        app.logger.warning("SECURITY_BASELINE: DASHSCOPE_API_KEY missing or placeholder; please configure and rotate.")
        return

    if raw_key.startswith("sk-") and len(raw_key) < 24:
        app.logger.warning("SECURITY_BASELINE: DASHSCOPE_API_KEY format looks abnormal; please validate and rotate.")
        return

    app.logger.info("SECURITY_BASELINE: DASHSCOPE_API_KEY loaded.")


_ERROR_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>系统暂时不可用</title>
<style>body{font-family:system-ui,sans-serif;max-width:520px;margin:80px auto;padding:24px;color:#333;}
h1{font-size:1.25rem;margin-bottom:12px;}p{line-height:1.6;}code{background:#f0f0f0;padding:2px 6px;border-radius:4px;}
a{color:#0066cc;}</style></head>
<body>
<h1>系统暂时不可用</h1>
<p>服务器内部错误，请稍后重试。若问题持续，请联系管理员。</p>
<p><a href="/">返回首页</a></p>
</body></html>"""


def _register_error_handlers(app: Flask) -> None:
    def _wants_json() -> bool:
        if request.path.startswith("/api/") or (request.is_json if hasattr(request, "is_json") else False):
            return True
        best = request.accept_mimetypes.best_match(["application/json", "text/html"]) if request.accept_mimetypes else None
        return best == "application/json"

    @app.errorhandler(500)
    def _handle_500(err: Exception) -> tuple[str | Any, int]:
        path = request.path if request else "?"
        app.logger.exception("Internal Server Error: %s (path=%s)", err, path)
        try:
            _p = PROJECT_ROOT / "debug_500_path.txt"
            with open(_p, "w", encoding="utf-8") as _f:
                _f.write(path + "\n" + str(err)[:500])
        except Exception:
            pass
        if _wants_json():
            return jsonify({"ok": False, "msg": "internal_error", "error": "Internal Server Error"}), 500
        return render_template_string(_ERROR_PAGE_HTML), 500


def create_app(config_object: str | object = "config") -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
        static_url_path="/static",
    )

    app.config.from_object(Settings)
    if config_object:
        app.config.from_object(config_object)

    app_version = str(app.config.get("APP_VERSION") or "").strip()
    if not app_version:
        app_version = "20260216_05"
    app.config["APP_VERSION"] = app_version

    static_version = str(app.config.get("STATIC_VERSION") or "").strip()
    if not static_version:
        static_version = app_version
    app.config["STATIC_VERSION"] = static_version

    debug_env = str(os.getenv("FLASK_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}
    debug_enabled = bool(app.config.get("DEBUG", False)) or debug_env
    if debug_enabled:
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    secret_key = str(app.config.get("SECRET_KEY") or "").strip()
    allow_insecure = bool(app.config.get("DEV_ALLOW_INSECURE", False))
    is_placeholder = not secret_key or secret_key.lower() in {p.lower() for p in _SECRET_KEY_PLACEHOLDERS}
    if is_placeholder:
        if allow_insecure or debug_enabled:
            import secrets
            fallback = secrets.token_hex(32)
            app.config["SECRET_KEY"] = fallback
            app.logger.warning(
                "SECURITY_BASELINE: SECRET_KEY was missing or placeholder; using temporary key. "
                "Set SECRET_KEY in .env for production. (DEV_ALLOW_INSECURE=1 or FLASK_DEBUG=1 enabled fallback)"
            )
        else:
            raise RuntimeError(
                "SECURITY_BASELINE: SECRET_KEY must be explicitly configured. "
                "Set SECRET_KEY in .env or DEV_ALLOW_INSECURE=1 for local development."
            )

    app.config["CLEAN_INVOICE_ROWS"] = clean_invoice_rows
    app.json.ensure_ascii = False

    # SQLAlchemy 配置
    app.config["SQLALCHEMY_DATABASE_URI"] = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "sqlite:///database.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"pool_pre_ping": True, "pool_recycle": 3600})

    configure_logging(app)
    app.logger.info("DATA_PROVIDER=%s", app.config.get("DATA_PROVIDER", "mock"))
    
    # 【关键】打印数据库路径，确保可见
    sqlalchemy_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    app.logger.info("=" * 80)
    app.logger.info("数据库配置信息")
    app.logger.info("=" * 80)
    app.logger.info("SQLALCHEMY_DATABASE_URI=%s", sqlalchemy_uri)
    app.logger.info("utils.db.DB_PATH=%s", DB_PATH)
    
    # 解析并显示实际的数据库文件绝对路径
    if sqlalchemy_uri.startswith("sqlite:///"):
        db_file = sqlalchemy_uri[10:]
        if not os.path.isabs(db_file):
            db_abs_path = os.path.abspath(str(PROJECT_ROOT / db_file))
        else:
            db_abs_path = os.path.abspath(db_file)
        app.logger.info("数据库文件绝对路径=%s", db_abs_path)
        app.logger.info("数据库文件是否存在=%s", os.path.exists(db_abs_path))
        if os.path.exists(db_abs_path):
            size_kb = os.path.getsize(db_abs_path) / 1024
            app.logger.info("数据库文件大小=%.2f KB", size_kb)
    app.logger.info("=" * 80)
    
    if allow_insecure and (not secret_key or secret_key == "dev-secret-key"):
        app.logger.warning("SECURITY_BASELINE: DEV_ALLOW_INSECURE=1 enabled, running with insecure session secret.")
    _log_dashscope_key_status(app)
    init_extensions(app)
    
    # 配置 Flask-Login user_loader
    try:
        from core.extensions import login_manager
        from utils.db import get_user_by_id
        
        @login_manager.user_loader
        def load_user(user_id):
            try:
                user = get_user_by_id(int(user_id))
                return user if user else None
            except Exception:
                return None
    except Exception as e:
        app.logger.warning("Flask-Login user_loader setup failed: %s", e)
    
    # 初始化 Flask-Migrate
    try:
        from flask_migrate import Migrate
        from core.extensions import db
        migrate = Migrate(app, db)
        app.logger.info("Flask-Migrate initialized")
    except Exception as e:
        app.logger.warning("Flask-Migrate init failed: %s", e)
    
    _register_template_context(app)
    try:
        init_db()
    except Exception as e:  # noqa: BLE001
        app.logger.exception("Database init failed: %s. App will start but DB operations may fail.", e)
        app.config["_DB_INIT_FAILED"] = True

    # 只有在设置了弱密码检测值时才进行检查和日志记录
    if DEFAULT_WEAK_PASSWORD:
        weak_users = list_users_with_password(DEFAULT_WEAK_PASSWORD, limit=5000)
        if weak_users:
            # 敏感信息脱敏：只显示用户名前3个字符，其余用*替代
            def _mask_username(username: str) -> str:
                if not username or len(username) <= 3:
                    return "*" * len(username) if username else ""
                return username[:3] + "*" * (len(username) - 3)
            
            masked_usernames = ",".join([
                _mask_username(str(item.get("username") or ""))
                for item in weak_users[:20]
                if str(item.get("username") or "")
            ])
            app.logger.warning(
                "WARNING SECURITY_BASELINE: detected %s weak-password account(s). masked_users=%s",
                len(weak_users),
                masked_usernames,
            )

    @app.before_request
    def _before_request_hooks():
        # 生成 request_id
        g.request_id = str(uuid.uuid4())
        g.session_id = session.get("_id") or ""
        
        # CSRF 检查
        ensure_csrf_token()
        if not bool(app.config.get("ENABLE_CSRF_PROTECTION", True)):
            return None
        methods = app.config.get("CSRF_PROTECT_METHODS", {"POST", "PUT", "PATCH", "DELETE"})
        if not isinstance(methods, (set, list, tuple)):
            methods = {"POST", "PUT", "PATCH", "DELETE"}
        protected_methods = {str(item or "").strip().upper() for item in methods if str(item or "").strip()}
        if request.method.upper() not in protected_methods:
            return None
        if request.path.startswith("/static/") or request.endpoint == "static":
            return None
        # 匿名 API 调用绕过 CSRF 检查：这些端点应该有自己的认证和授权检查
        # 例如登录接口、公开 API 等，它们通过 login_required/permission 装饰器进行保护
        # 注意：所有匿名 API 端点必须实现适当的认证机制，不能依赖 CSRF token 作为唯一的安全措施
        if request.path.startswith("/api/") and current_user() is None:
            # Let login_required/permission guards return unauthorized for anonymous API calls.
            return None
        if validate_csrf_request():
            return None
        # #region agent log
        try:
            _log_path = PROJECT_ROOT / "debug-b60ee0.log"
            with open(_log_path, "a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "b60ee0",
                            "location": "app_factory.py:_csrf_guard",
                            "message": "csrf_rejected",
                            "data": {"path": request.path, "method": request.method},
                            "hypothesisId": "H3",
                            "timestamp": time.time_ns() // 1_000_000,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        payload = {"ok": False, "msg": "csrf_invalid"}
        if _wants_json_response():
            return jsonify(payload), 403
        return "csrf_invalid", 403
        # 添加 X-Request-ID 响应头
        if hasattr(g, "request_id"):
            response.headers["X-Request-ID"] = g.request_id
        
        # 强制 UTF-8
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if content_type.startswith("text/html") and "charset=" not in content_type:
            response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response

    register_blueprints(app)
    _register_error_handlers(app)
    scheduler_enabled = bool(app.config.get("ENABLE_SCHEDULER", False))
    scheduler_mode = str(app.config.get("SCHEDULER_MODE", "off")).strip().lower() or "off"
    if not scheduler_enabled:
        app.logger.info("scheduler disabled (ENABLE_SCHEDULER=False)")
    else:
        app.logger.info("scheduler enabled")
        if _should_start_scheduler(app):
            start_scheduler(app)
        else:
            app.logger.info("scheduler skipped for current process mode=%s", scheduler_mode)

    return app
