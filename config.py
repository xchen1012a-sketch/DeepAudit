# -*- coding: utf-8 -*-
"""
Backward-compatible config module.

Existing modules import `config`, so we keep this shim and source values from
`core.settings`.
"""

from core.settings import (
    AUDIT_LOG_LEVEL,
    CANTON_FAIR_WINDOWS,
    CSRF_PROTECT_METHODS,
    DASHSCOPE_API_KEY,
    DATA_PROVIDER,
    DEV_ALLOW_INSECURE,
    ENABLE_CSRF_PROTECTION,
    ENABLE_EVENTS,
    ENABLE_SCHEDULER,
    SCHEDULER_MODE,
    HOTEL_LIMIT_CANTON_FAIR,
    HOTEL_LIMIT_NORMAL,
    LLM_MODEL_NAME,
    MOCK_DATA_DIR,
    MOCK_FAILURE_RATE,
    MOCK_LATENCY_MS_RANGE,
    Settings,
    TAX_PROVIDER_NAME,
    VERIFY_MODE,
)

__all__ = [
    "Settings",
    "AUDIT_LOG_LEVEL",
    "CANTON_FAIR_WINDOWS",
    "CSRF_PROTECT_METHODS",
    "DASHSCOPE_API_KEY",
    "DATA_PROVIDER",
    "DEV_ALLOW_INSECURE",
    "ENABLE_CSRF_PROTECTION",
    "ENABLE_EVENTS",
    "ENABLE_SCHEDULER",
    "SCHEDULER_MODE",
    "HOTEL_LIMIT_CANTON_FAIR",
    "HOTEL_LIMIT_NORMAL",
    "LLM_MODEL_NAME",
    "MOCK_FAILURE_RATE",
    "MOCK_LATENCY_MS_RANGE",
    "MOCK_DATA_DIR",
    "VERIFY_MODE",
    "TAX_PROVIDER_NAME",
]
