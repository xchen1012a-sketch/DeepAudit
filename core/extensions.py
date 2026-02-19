from __future__ import annotations

from typing import Any

from flask import Flask


class _NoopExtension:
    """Fallback hook when optional Flask extension packages are unavailable."""

    def __init__(self, name: str) -> None:
        self.name = name

    def init_app(self, app: Flask) -> None:  # pragma: no cover - tiny hook
        app.extensions.setdefault(self.name, self)


def _build_db_extension() -> Any:
    try:
        from flask_sqlalchemy import SQLAlchemy

        return SQLAlchemy()
    except Exception:
        return _NoopExtension("db")


def _build_login_extension() -> Any:
    try:
        from flask_login import LoginManager

        manager = LoginManager()
        manager.login_view = "auth.login"
        return manager
    except Exception:
        return _NoopExtension("login_manager")


def _build_cache_extension() -> Any:
    try:
        from flask_caching import Cache

        return Cache(config={"CACHE_TYPE": "SimpleCache"})
    except Exception:
        return _NoopExtension("cache")


db = _build_db_extension()
login_manager = _build_login_extension()
cache = _build_cache_extension()


def init_extensions(app: Flask) -> None:
    for name, ext in (
        ("db", db),
        ("login_manager", login_manager),
        ("cache", cache),
    ):
        init_app = getattr(ext, "init_app", None)
        if callable(init_app):
            init_app(app)
        app.extensions.setdefault(name, ext)
