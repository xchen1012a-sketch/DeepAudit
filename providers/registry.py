from __future__ import annotations

import os

from core.settings import DATA_PROVIDER as DEFAULT_DATA_PROVIDER
from providers.base import BankProvider, ErpProvider, TaxProvider
from providers.mock_bank import MockBankProvider
from providers.mock_erp import MockErpProvider
from providers.mock_tax import MockTaxProvider

_tax_provider_singleton: TaxProvider | None = None
_bank_provider_singleton: BankProvider | None = None
_erp_provider_singleton: ErpProvider | None = None


def _get_config_value(key: str, fallback: str) -> str:
    # Prefer Flask app config when available.
    try:
        from flask import current_app

        if current_app:
            value = current_app.config.get(key)
            if value is not None:
                return str(value)
    except Exception:
        pass
    return str(os.getenv(key, fallback))


def _provider_mode() -> str:
    mode = _get_config_value("DATA_PROVIDER", DEFAULT_DATA_PROVIDER).strip().lower()
    if mode in {"mock", "real"}:
        return mode
    return "mock"


def get_tax_provider() -> TaxProvider:
    global _tax_provider_singleton

    mode = _provider_mode()
    if mode == "real":
        raise NotImplementedError("Real provider not implemented")

    if _tax_provider_singleton is None:
        _tax_provider_singleton = MockTaxProvider()
    return _tax_provider_singleton


def get_bank_provider() -> BankProvider:
    global _bank_provider_singleton

    mode = _provider_mode()
    if mode == "real":
        raise NotImplementedError("Real provider not implemented")

    if _bank_provider_singleton is None:
        _bank_provider_singleton = MockBankProvider()
    return _bank_provider_singleton


def get_erp_provider() -> ErpProvider:
    global _erp_provider_singleton

    mode = _provider_mode()
    if mode == "real":
        raise NotImplementedError("Real provider not implemented")

    if _erp_provider_singleton is None:
        _erp_provider_singleton = MockErpProvider()
    return _erp_provider_singleton
