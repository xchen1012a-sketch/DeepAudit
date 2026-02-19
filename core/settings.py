from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_choice(name: str, allowed: set[str], default: str) -> str:
    raw = str(os.getenv(name, default)).strip().lower()
    if raw in allowed:
        return raw
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(str(raw).strip())
    except Exception:
        return default


def _env_csv_set(name: str, default: set[str]) -> set[str]:
    raw = os.getenv(name)
    if raw is None:
        return set(default)
    values = {str(item or "").strip().upper() for item in str(raw).split(",")}
    values = {item for item in values if item}
    return values or set(default)


ALLOWED_DATA_PROVIDERS = {"mock", "real"}
ALLOWED_VERIFY_MODES = {"replay", "mock"}
ALLOWED_SCHEDULER_MODES = {"off", "dev", "prod"}


class Settings:
    SECRET_KEY = str(os.getenv("SECRET_KEY", "")).strip()
    DEV_ALLOW_INSECURE = _env_bool("DEV_ALLOW_INSECURE", default=False)

    # Database
    SQLALCHEMY_DATABASE_URI = str(os.getenv("DATABASE_URL", "sqlite:///database.db")).strip()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    # Runtime flags
    DATA_PROVIDER = _env_choice("DATA_PROVIDER", ALLOWED_DATA_PROVIDERS, "mock")
    ENABLE_EVENTS = _env_bool("ENABLE_EVENTS", default=True)
    ENABLE_SCHEDULER = _env_bool("ENABLE_SCHEDULER", default=False)
    SCHEDULER_MODE = _env_choice("SCHEDULER_MODE", ALLOWED_SCHEDULER_MODES, "off")
    ENABLE_CSRF_PROTECTION = _env_bool("ENABLE_CSRF_PROTECTION", default=True)
    CSRF_PROTECT_METHODS = _env_csv_set("CSRF_PROTECT_METHODS", {"POST", "PUT", "PATCH", "DELETE"})
    AUDIT_LOG_LEVEL = str(os.getenv("AUDIT_LOG_LEVEL", "INFO")).strip().upper() or "INFO"
    MOCK_FAILURE_RATE = _env_float("MOCK_FAILURE_RATE", 0.05)
    MOCK_LATENCY_MS_RANGE = str(os.getenv("MOCK_LATENCY_MS_RANGE", "200,1200")).strip() or "200,1200"
    MOCK_DATA_DIR = str(os.getenv("MOCK_DATA_DIR", "data")).strip() or "data"
    VERIFY_MODE = _env_choice("VERIFY_MODE", ALLOWED_VERIFY_MODES, "replay")
    TAX_PROVIDER_NAME = str(os.getenv("TAX_PROVIDER_NAME", "GD_TAX_REPLAY")).strip() or "GD_TAX_REPLAY"

    # LLM
    DASHSCOPE_API_KEY = str(os.getenv("DASHSCOPE_API_KEY", "")).strip()
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen-turbo")

    # Business rules
    CANTON_FAIR_WINDOWS = [
        ("04-15", "05-05"),
        ("10-15", "11-04"),
    ]
    HOTEL_LIMIT_NORMAL = _env_int("HOTEL_LIMIT_NORMAL", 500)
    HOTEL_LIMIT_CANTON_FAIR = _env_int("HOTEL_LIMIT_CANTON_FAIR", 1000)


# Backward-compatible module-level constants for existing imports.
SECRET_KEY: str = Settings.SECRET_KEY
DEV_ALLOW_INSECURE: bool = Settings.DEV_ALLOW_INSECURE
SQLALCHEMY_DATABASE_URI: str = Settings.SQLALCHEMY_DATABASE_URI
SQLALCHEMY_TRACK_MODIFICATIONS: bool = Settings.SQLALCHEMY_TRACK_MODIFICATIONS
DATA_PROVIDER: str = Settings.DATA_PROVIDER
ENABLE_EVENTS: bool = Settings.ENABLE_EVENTS
ENABLE_SCHEDULER: bool = Settings.ENABLE_SCHEDULER
SCHEDULER_MODE: str = Settings.SCHEDULER_MODE
ENABLE_CSRF_PROTECTION: bool = Settings.ENABLE_CSRF_PROTECTION
CSRF_PROTECT_METHODS: set[str] = Settings.CSRF_PROTECT_METHODS
AUDIT_LOG_LEVEL: str = Settings.AUDIT_LOG_LEVEL
MOCK_FAILURE_RATE: float = Settings.MOCK_FAILURE_RATE
MOCK_LATENCY_MS_RANGE: str = Settings.MOCK_LATENCY_MS_RANGE
MOCK_DATA_DIR: str = Settings.MOCK_DATA_DIR
VERIFY_MODE: str = Settings.VERIFY_MODE
TAX_PROVIDER_NAME: str = Settings.TAX_PROVIDER_NAME
DASHSCOPE_API_KEY: str = Settings.DASHSCOPE_API_KEY
LLM_MODEL_NAME: str = Settings.LLM_MODEL_NAME
CANTON_FAIR_WINDOWS: list[tuple[str, str]] = Settings.CANTON_FAIR_WINDOWS
HOTEL_LIMIT_NORMAL: int = Settings.HOTEL_LIMIT_NORMAL
HOTEL_LIMIT_CANTON_FAIR: int = Settings.HOTEL_LIMIT_CANTON_FAIR


def _mask_secret(value: str, keep: int = 3) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= keep * 2:
        return "*" * len(text)
    return f"{text[:keep]}***{text[-keep:]}"


def as_dict() -> dict[str, Any]:
    return {
        "SECRET_KEY": _mask_secret(SECRET_KEY),
        "DEV_ALLOW_INSECURE": DEV_ALLOW_INSECURE,
        "DATA_PROVIDER": DATA_PROVIDER,
        "ENABLE_EVENTS": ENABLE_EVENTS,
        "ENABLE_SCHEDULER": ENABLE_SCHEDULER,
        "SCHEDULER_MODE": SCHEDULER_MODE,
        "ENABLE_CSRF_PROTECTION": ENABLE_CSRF_PROTECTION,
        "CSRF_PROTECT_METHODS": sorted(CSRF_PROTECT_METHODS),
        "AUDIT_LOG_LEVEL": AUDIT_LOG_LEVEL,
        "MOCK_FAILURE_RATE": MOCK_FAILURE_RATE,
        "MOCK_LATENCY_MS_RANGE": MOCK_LATENCY_MS_RANGE,
        "MOCK_DATA_DIR": MOCK_DATA_DIR,
        "VERIFY_MODE": VERIFY_MODE,
        "TAX_PROVIDER_NAME": TAX_PROVIDER_NAME,
        "DASHSCOPE_API_KEY": _mask_secret(DASHSCOPE_API_KEY),
        "LLM_MODEL_NAME": LLM_MODEL_NAME,
        "CANTON_FAIR_WINDOWS": CANTON_FAIR_WINDOWS,
        "HOTEL_LIMIT_NORMAL": HOTEL_LIMIT_NORMAL,
        "HOTEL_LIMIT_CANTON_FAIR": HOTEL_LIMIT_CANTON_FAIR,
    }
