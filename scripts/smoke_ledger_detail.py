"""
冒烟验证：台账详情/证据中心接口可正常返回。
运行方式：python scripts/smoke_ledger_detail.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from utils.db import list_invoices
from utils.security import SESSION_USER_ID_KEY


def main() -> None:
    rows = list_invoices(limit=1, record_state="LEDGER")
    assert rows, "未找到已入账单据，无法验证"
    invoice_id = int(rows[0]["id"])

    with app.test_client() as client:
        # 模拟已登录用户
        with client.session_transaction() as sess:
            # 使用有全局可见权限的管理员账户
            sess[SESSION_USER_ID_KEY] = 257

        resp = client.get(f"/api/ledger/{invoice_id}/evidence")
        assert resp.status_code == 200, f"接口返回 {resp.status_code}"
        data = resp.get_json(force=True)
        assert data and data.get("ok") is True, "响应体缺少 ok=true"
        assert data.get("invoice_id") == invoice_id, "返回的 invoice_id 不匹配"
        evidence = data.get("evidence") or {}
        for key in ("structured_data", "verification_receipt", "rule_evidence"):
            assert key in evidence, f"evidence 缺少 {key}"

    print(f"[OK] /api/ledger/{invoice_id}/evidence 返回正常，包含核心字段")


if __name__ == "__main__":
    main()
