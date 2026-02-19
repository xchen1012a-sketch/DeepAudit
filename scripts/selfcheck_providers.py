from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure "python scripts/selfcheck_providers.py" works from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Avoid flaky checks caused by random failure in mock network simulation.
os.environ.setdefault("DATA_PROVIDER", "mock")
os.environ["MOCK_FAILURE_RATE"] = "0"

from providers.registry import get_bank_provider, get_erp_provider, get_tax_provider


def _dump(label: str, payload: dict) -> None:
    print(f"[{label}] {json.dumps(payload, ensure_ascii=False)}")


def main() -> int:
    tax = get_tax_provider()
    bank = get_bank_provider()
    erp = get_erp_provider()

    tax_hit = tax.verify_invoice({"invoice_number": "INV-TAX-0001"})
    tax_miss = tax.verify_invoice({"invoice_number": "INV-TAX-9999"})

    bank_page_1 = bank.pull_transactions(cursor=None, limit=5)
    bank_page_2 = bank.pull_transactions(cursor=bank_page_1.get("next_cursor"), limit=5)

    erp_search = erp.search_orders(keyword="Vendor Alpha", limit=5)
    erp_employee = erp.get_employee("E1001")

    _dump("tax_hit", tax_hit)
    _dump("tax_miss", tax_miss)
    _dump(
        "bank_page_1_summary",
        {
            "ok": bank_page_1.get("ok"),
            "provider": bank_page_1.get("provider"),
            "latency_ms": bank_page_1.get("latency_ms"),
            "count": len(bank_page_1.get("items") or []),
            "next_cursor": bank_page_1.get("next_cursor"),
        },
    )
    _dump(
        "bank_page_2_summary",
        {
            "ok": bank_page_2.get("ok"),
            "provider": bank_page_2.get("provider"),
            "latency_ms": bank_page_2.get("latency_ms"),
            "count": len(bank_page_2.get("items") or []),
            "next_cursor": bank_page_2.get("next_cursor"),
        },
    )
    _dump(
        "erp_search_summary",
        {
            "ok": erp_search.get("ok"),
            "provider": erp_search.get("provider"),
            "latency_ms": erp_search.get("latency_ms"),
            "count": len(erp_search.get("items") or []),
            "message": erp_search.get("message"),
        },
    )
    _dump("erp_employee", erp_employee)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
