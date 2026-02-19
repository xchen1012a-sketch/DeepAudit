from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TaxProvider(ABC):
    @abstractmethod
    def verify_invoice(self, invoice: dict[str, Any]) -> dict[str, Any]:
        """
        Return shape:
        {
            "ok": bool,
            "status": "valid|void|red|abnormal|unknown",
            "message": str,
            "provider": str,
            "latency_ms": int,
            "raw": dict,
        }
        """


class BankProvider(ABC):
    @abstractmethod
    def pull_transactions(self, cursor: str | None, limit: int = 50) -> dict[str, Any]:
        """
        Return shape:
        {
            "ok": bool,
            "next_cursor": str | None,
            "items": [
                {
                    "txn_id": str,
                    "amount": str | int | float,
                    "ts": str,
                    "counterparty": str,
                    "memo": str,
                }
            ],
            "provider": str,
            "latency_ms": int,
            "message": str,
        }
        """


class ErpProvider(ABC):
    @abstractmethod
    def search_orders(self, keyword: str, limit: int = 20) -> dict[str, Any]:
        """Search ERP orders by keyword."""

    @abstractmethod
    def get_employee(self, employee_id: str) -> dict[str, Any]:
        """Get one employee profile from ERP."""
