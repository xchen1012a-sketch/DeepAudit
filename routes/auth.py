from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from utils.db import (
    clear_login_identity_failures,
    clear_login_failures,
    get_user_auth_by_id,
    get_user_auth_by_username,
    is_login_identity_locked,
    register_login_identity_failure,
    update_user_password,
    update_user_profile,
)
from utils.audit_logger import write_audit_log
from utils.security import (
    SESSION_USER_ID_KEY,
    can_access_approval_console,
    can_approve,
    can_governance,
    current_user,
    current_user_role_keys,
    is_finance,
    login_required,
)

bp = Blueprint("auth", __name__)

# #region agent log
def _agent_log(msg: str, data: dict, hypothesis_id: str) -> None:
    try:
        log_path = Path(__file__).resolve().parent.parent / "debug-b60ee0.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "b60ee0",
                        "location": "auth.py:login",
                        "message": msg,
                        "data": data,
                        "hypothesisId": hypothesis_id,
                        "timestamp": time.time_ns() // 1_000_000,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
# #endregion


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _wants_json_response() -> bool:
    if request.path.startswith("/api/") or request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _build_me_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(user["id"]),
        "username": str(user.get("username") or ""),
        "department": str(user.get("department") or ""),
        "employee_name": str(user.get("employee_name") or ""),
        "employee_no": str(user.get("employee_no") or ""),
        "role": str(user.get("role") or ""),
        "role_keys": sorted(current_user_role_keys(user)),
        "can_approve": bool(can_approve(user)),
        "can_access_approval_console": bool(can_access_approval_console(user)),
        "can_governance": bool(can_governance(user)),
        "is_finance": bool(is_finance(user)),
        "must_change_password": bool(user.get("must_change_password")),
        "email": str(user.get("email") or ""),
        "phone": str(user.get("phone") or ""),
    }


def _default_after_login_path() -> str:
    for endpoint in ("dashboard.dashboard_page", "ledger.invoices_page", "auth.login"):
        if endpoint not in current_app.view_functions:
            continue
        try:
            return url_for(endpoint)
        except Exception:
            continue
    return "/login"


def _safe_next_path() -> str:
    next_path = str(request.args.get("next") or request.form.get("next") or "").strip()
    if not next_path.startswith("/"):
        return _default_after_login_path()
    if next_path in {"/login", "/logout", "/api/me"}:
        return _default_after_login_path()
    return next_path


def _client_ip() -> str:
    forwarded = _safe_text(request.headers.get("X-Forwarded-For"))
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = _safe_text(request.headers.get("X-Real-IP"))
    if real_ip:
        return real_ip
    return _safe_text(request.remote_addr, "-")


def _audit_login_event(
    *,
    action_type: str,
    username: str,
    detail: str,
    actor_user_id: int | None = None,
) -> None:
    try:
        write_audit_log(
            action=action_type,
            actor_user_id=actor_user_id,
            actor_name=username or "anonymous",
            target_type="auth",
            target_id=str(actor_user_id) if actor_user_id else "",
            detail=detail,
        )
    except Exception:
        return


def _verify_user_credentials(username: str, password: str, client_ip: str) -> tuple[dict[str, Any] | None, str | None]:
    normalized_username = _safe_text(username).lower()
    # #region agent log
    _agent_log("verify_step", {"step": "before_is_locked"}, "H_verify")
    # #endregion
    locked, lock_until = is_login_identity_locked(normalized_username, client_ip)
    # #region agent log
    _agent_log("verify_step", {"step": "after_is_locked", "locked": locked}, "H_verify")
    # #endregion
    if locked:
        _audit_login_event(
            action_type="LOGIN_LOCK",
            username=normalized_username or username,
            detail=(
                f"username={normalized_username or username}; "
                f"ip={client_ip}; lock_until={lock_until}; reason=rate_limit_precheck"
            ),
        )
        return None, f"ACCOUNT_LOCKED:{lock_until}"

    # #region agent log
    _agent_log("verify_step", {"step": "before_get_user"}, "H_verify")
    # #endregion
    user = get_user_auth_by_username(normalized_username)
    # #region agent log
    _agent_log("verify_step", {"step": "after_get_user", "user_is_none": user is None}, "H_verify")
    # #endregion
    if user is None or _safe_text(user.get("status")).upper() not in {"", "ACTIVE"}:
        fail_result = register_login_identity_failure(normalized_username, client_ip)
        user_id = int(user.get("id") or 0) if isinstance(user, dict) else 0
        user_id = user_id or None
        if fail_result.get("locked"):
            lock_until_text = _safe_text(fail_result.get("lock_until"))
            _audit_login_event(
                action_type="LOGIN_LOCK",
                username=normalized_username or username,
                actor_user_id=user_id,
                detail=(
                    f"username={normalized_username or username}; "
                    f"ip={client_ip}; lock_until={lock_until_text}; reason=max_failed_attempts"
                ),
            )
            return None, f"ACCOUNT_LOCKED:{lock_until_text}"

        _audit_login_event(
            action_type="LOGIN_FAIL",
            username=normalized_username or username,
            actor_user_id=user_id,
            detail=(
                f"username={normalized_username or username}; "
                f"ip={client_ip}; reason=invalid_credentials"
            ),
        )
        return None, "INVALID_CREDENTIALS"

    password_hash = _safe_text(user.get("password_hash"))
    # #region agent log
    _agent_log("verify_step", {"step": "before_check_password"}, "H_verify")
    # #endregion
    if not password_hash or not check_password_hash(password_hash, password):
        fail_result = register_login_identity_failure(normalized_username, client_ip)
        user_id = int(user.get("id") or 0) if isinstance(user, dict) else 0
        user_id = user_id or None
        if fail_result.get("locked"):
            lock_until_text = _safe_text(fail_result.get("lock_until"))
            _audit_login_event(
                action_type="LOGIN_LOCK",
                username=normalized_username or username,
                actor_user_id=user_id,
                detail=(
                    f"username={normalized_username or username}; "
                    f"ip={client_ip}; lock_until={lock_until_text}; reason=max_failed_attempts"
                ),
            )
            return None, f"ACCOUNT_LOCKED:{lock_until_text}"

        _audit_login_event(
            action_type="LOGIN_FAIL",
            username=normalized_username or username,
            actor_user_id=user_id,
            detail=(
                f"username={normalized_username or username}; "
                f"ip={client_ip}; reason=invalid_credentials"
            ),
        )
        return None, "INVALID_CREDENTIALS"

    # #region agent log
    _agent_log("verify_step", {"step": "after_check_password_ok"}, "H_verify")
    # #endregion
    clear_login_identity_failures(normalized_username, client_ip)
    clear_login_failures(user.get("id"))
    return user, None


def _validate_new_password_strength(password: str) -> str | None:
    value = _safe_text(password)
    if len(value) < 8:
        return "new_password must be at least 8 characters"
    has_letter = any(ch.isalpha() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    if not has_letter or not has_digit:
        return "new_password must contain both letters and numbers"
    return None


@bp.get("/")
def home():
    if current_user() is None:
        return redirect(url_for("auth.login"))
    return redirect(_default_after_login_path())


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if current_user() is not None:
            return redirect(_default_after_login_path())
        return render_template("login.html", error=None, next_path=_safe_next_path())

    # #region agent log
    _agent_log("login_post_start", {"method": request.method}, "H1")
    # #endregion
    try:
        payload = request.get_json(silent=True) if request.is_json else request.form
        payload = payload or {}
        username = _safe_text(payload.get("username"))
        password = _safe_text(payload.get("password"))

        if not username or not password:
            # #region agent log
            _agent_log("login_empty_creds", {"has_username": bool(username)}, "H4")
            # #endregion
            msg = "username and password are required"
            if _wants_json_response():
                return jsonify({"ok": False, "msg": msg}), 400
            return render_template("login.html", error="请输入账号和密码", next_path=_safe_next_path()), 400

        client_ip = _client_ip()
        user, reason = _verify_user_credentials(username, password, client_ip)
        # #region agent log
        _agent_log("verify_done", {"user_is_none": user is None, "reason": (reason or "")[:80]}, "H2,H4")
        # #endregion
        if user is None:
            is_locked = str(reason or "").startswith("ACCOUNT_LOCKED")
            msg = "login temporarily locked, please retry later" if is_locked else "invalid username or password"
            status_code = 423 if is_locked else 401
            error_code = "ACCOUNT_LOCKED" if is_locked else "INVALID_CREDENTIALS"

            if _wants_json_response():
                return jsonify({"ok": False, "msg": msg, "error_code": error_code}), status_code

            error_text = "登录受限，请 10 分钟后重试" if is_locked else "账号或密码错误"
            # #region agent log
            _agent_log("login_return_error", {"status_code": status_code}, "H4")
            # #endregion
            return render_template("login.html", error=error_text, next_path=_safe_next_path()), status_code

        session[SESSION_USER_ID_KEY] = int(user["id"])
        must_change_password = bool(user.get("must_change_password"))
        redirect_to = "/profile?force_password=1" if must_change_password else _safe_next_path()

        _audit_login_event(
            action_type="LOGIN_SUCCESS",
            username=_safe_text(user.get("username"), username),
            actor_user_id=int(user.get("id") or 0) or None,
            detail=f"username={_safe_text(user.get('username'), username)}; ip={client_ip}",
        )

        if _wants_json_response():
            return jsonify(
                {
                    "ok": True,
                    "user": _build_me_payload(user),
                    "redirect_to": redirect_to,
                    "must_change_password": must_change_password,
                }
            )
        # #region agent log
        _agent_log("login_redirect", {"redirect_to": redirect_to}, "H1,H5")
        # #endregion
        return redirect(redirect_to)
    except Exception as e:
        # #region agent log
        _agent_log("login_exception", {"type": type(e).__name__, "msg": str(e)[:200]}, "H2")
        # #endregion
        raise


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.pop(SESSION_USER_ID_KEY, None)
    if _wants_json_response():
        return jsonify({"ok": True})
    return redirect(url_for("auth.login"))


@bp.get("/api/me")
@login_required
def api_me():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "msg": "unauthorized"}), 401
    return jsonify(_build_me_payload(user))


@bp.post("/api/auth/refresh_permissions")
@login_required
def refresh_permissions_api():
    """强制刷新当前用户的权限信息（用于角色权限配置后立即生效）"""
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "msg": "unauthorized"}), 401
    
    # 重新构建用户信息（会重新查询数据库权限）
    payload = _build_me_payload(user)
    
    return jsonify({
        "ok": True,
        "msg": "权限已刷新",
        "user": payload
    })


@bp.post("/api/auth/change_password")
@login_required
def change_password_api():
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload or {}

    old_password = _safe_text(payload.get("old_password"))
    new_password = _safe_text(payload.get("new_password"))
    if not old_password or not new_password:
        return jsonify({"ok": False, "msg": "old_password and new_password are required"}), 400

    strength_error = _validate_new_password_strength(new_password)
    if strength_error:
        return jsonify({"ok": False, "msg": strength_error}), 400

    me = current_user() or {}
    user_id = int(me.get("id") or 0)
    auth_user = get_user_auth_by_id(user_id)
    if auth_user is None:
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    password_hash = _safe_text(auth_user.get("password_hash"))
    if not password_hash or not check_password_hash(password_hash, old_password):
        return jsonify({"ok": False, "msg": "old_password is incorrect"}), 400

    if check_password_hash(password_hash, new_password):
        return jsonify({"ok": False, "msg": "new_password must be different from old_password"}), 400

    updated = update_user_password(user_id, new_password=new_password, must_change_password=False)
    if not updated:
        return jsonify({"ok": False, "msg": "password update failed"}), 500

    _audit_login_event(
        action_type="PASSWORD_CHANGE",
        username=_safe_text(auth_user.get("username"), "user"),
        actor_user_id=user_id,
        detail=f"username={_safe_text(auth_user.get('username'))}; source=self_service",
    )

    return jsonify({"ok": True, "msg": "password updated"})


@bp.post("/api/auth/update_profile")
@login_required
def update_profile_api():
    """个人中心修改邮箱、手机号。"""
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload or {}

    email = _safe_text(payload.get("email"))
    phone = _safe_text(payload.get("phone"))

    if len(email) > 128:
        return jsonify({"ok": False, "msg": "邮箱长度不能超过 128 个字符"}), 400
    if len(phone) > 32:
        return jsonify({"ok": False, "msg": "手机号长度不能超过 32 个字符"}), 400
    if email and "@" not in email:
        return jsonify({"ok": False, "msg": "请输入有效的邮箱地址"}), 400

    me = current_user() or {}
    user_id = int(me.get("id") or 0)
    if user_id <= 0:
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    updated = update_user_profile(user_id, email=email, phone=phone)
    if not updated:
        return jsonify({"ok": False, "msg": "更新失败"}), 500

    return jsonify({"ok": True, "msg": "保存成功"})


@bp.get("/auth/health")
def health():
    return jsonify({"ok": True, "module": "auth"})
