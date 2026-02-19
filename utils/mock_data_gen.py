# -*- coding: utf-8 -*-
"""Generate enterprise-style mock reimbursement data and insert into SQLite."""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

# Ensure "python utils/mock_data_gen.py" works from any cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from utils.db import get_conn, init_db, insert_invoice

TOTAL_RECORDS = 50
FAIR_OVER_LIMIT_COUNT = 10  # 20%
AI_SEMANTIC_RISK_COUNT = 5  # 10%

APPLICANTS = [
    "王伟",
    "李芳",
    "张敏",
    "刘洋",
    "陈工",
    "赵婷",
    "周强",
    "黄璐",
    "吴鹏",
    "徐娜",
    "孙涛",
    "朱琳",
    "高磊",
    "林雪",
    "何健",
]

DEPARTMENTS = [
    "研发部",
    "市场部",
    "财务部",
    "行政部",
    "采购部",
    "法务合规部",
    "信息安全部",
    "运营管理部",
    "人力资源部",
]

BENIGN_MERCHANT_ITEMS = [
    ("广州天河希尔顿酒店", "豪华大床房 1 晚"),
    ("深圳福田香格里拉大酒店", "行政客房住宿费"),
    ("广州白云国际会议中心", "会议室租赁及茶歇"),
    ("广州琶洲会展商务酒店", "标准间住宿费"),
    ("南方航空电子客票", "广州-上海往返机票"),
    ("中国铁路12306", "广州南-深圳北高铁票"),
    ("滴滴出行", "出差市内交通费"),
    ("京东商城", "办公耗材采购"),
    ("晨光文具旗舰店", "签字笔与文件夹"),
    ("顺丰速运", "合同资料寄送"),
    ("美团企业版", "项目加班工作餐"),
    ("广州天河城餐饮管理有限公司", "商务简餐"),
    ("华住会-全季酒店", "商务住宿费"),
    ("广州琶洲展馆停车场", "展会期间停车费"),
    ("携程商旅", "差旅预订服务费"),
]

AI_RISK_MERCHANTS = [
    "皇朝KTV",
    "澳门娱乐城",
    "星彩娱乐会所",
    "金钻夜总会",
]

AI_RISK_ITEMS = [
    "包厢服务费",
    "酒水及娱乐消费",
    "夜场商务招待费用",
    "娱乐项目综合服务费",
]


def _daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _is_canton_fair_day(value: date) -> bool:
    for start_mmdd, end_mmdd in config.CANTON_FAIR_WINDOWS:
        start_d = datetime.strptime(f"{value.year}-{start_mmdd}", "%Y-%m-%d").date()
        end_d = datetime.strptime(f"{value.year}-{end_mmdd}", "%Y-%m-%d").date()
        if start_d <= value <= end_d:
            return True
    return False


def _recent_three_month_days() -> list[date]:
    end = date.today()
    start = end - timedelta(days=90)
    return list(_daterange(start, end))


def _latest_fair_window_days(today: date) -> list[date]:
    windows: list[tuple[date, date]] = []
    for year in (today.year, today.year - 1):
        for start_mmdd, end_mmdd in config.CANTON_FAIR_WINDOWS:
            start_d = datetime.strptime(f"{year}-{start_mmdd}", "%Y-%m-%d").date()
            end_d = datetime.strptime(f"{year}-{end_mmdd}", "%Y-%m-%d").date()
            if end_d <= today:
                windows.append((start_d, end_d))
    if not windows:
        return []
    start_d, end_d = max(windows, key=lambda x: x[1])
    return list(_daterange(start_d, end_d))


def _pick_dates_for_fair_risk() -> list[date]:
    recent_days = _recent_three_month_days()
    fair_days = [d for d in recent_days if _is_canton_fair_day(d)]
    if fair_days:
        return fair_days
    # If last 90 days do not include fair dates, fall back to the latest fair window.
    return _latest_fair_window_days(date.today())


def _random_amount(min_value: float = 100.0, max_value: float = 3000.0) -> float:
    return round(random.uniform(min_value, max_value), 2)


def _build_risk(amount: float, limit: int, is_canton_fair: bool) -> tuple[str, str]:
    if is_canton_fair and amount > limit:
        return "HIGH", f"广交会限额超标：金额 {amount:.2f} > 限额 {limit}"
    if amount > limit:
        return "HIGH", f"住宿限额超标：金额 {amount:.2f} > 限额 {limit}"
    if amount >= 0.9 * limit:
        return "MEDIUM", f"接近限额：金额 {amount:.2f} 接近限额 {limit}"
    return "LOW", "金额在限额内，未触发规则风险"


def _pick_status() -> str:
    return random.choices(
        population=["PENDING", "APPROVED", "REJECTED"],
        weights=[0.58, 0.34, 0.08],
        k=1,
    )[0]


def reset_invoice_table() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM invoices")
        try:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'invoices'")
        except Exception:
            pass
        conn.commit()


def generate_mock_invoices(total: int = TOTAL_RECORDS, purge_existing: bool = True) -> list[int]:
    init_db()
    if purge_existing:
        reset_invoice_table()

    fair_days = _pick_dates_for_fair_risk()
    recent_days = _recent_three_month_days()
    normal_days = [d for d in recent_days if not _is_canton_fair_day(d)] or recent_days

    indices = list(range(total))
    random.shuffle(indices)
    fair_risk_indices = set(indices[:FAIR_OVER_LIMIT_COUNT])
    ai_risk_indices = set(indices[FAIR_OVER_LIMIT_COUNT:FAIR_OVER_LIMIT_COUNT + AI_SEMANTIC_RISK_COUNT])

    inserted_ids: list[int] = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i in range(total):
        if i in fair_risk_indices and fair_days:
            invoice_day = random.choice(fair_days)
            is_canton_fair = True
            hotel_limit = int(config.HOTEL_LIMIT_CANTON_FAIR)
            amount = _random_amount(hotel_limit + 20, 3000.0)
            merchant, item = random.choice(BENIGN_MERCHANT_ITEMS)
        else:
            invoice_day = random.choice(normal_days)
            is_canton_fair = _is_canton_fair_day(invoice_day)
            hotel_limit = int(config.HOTEL_LIMIT_CANTON_FAIR if is_canton_fair else config.HOTEL_LIMIT_NORMAL)
            amount = _random_amount(100.0, 3000.0)

            if i in ai_risk_indices:
                merchant = random.choice(AI_RISK_MERCHANTS)
                item = random.choice(AI_RISK_ITEMS)
            else:
                merchant, item = random.choice(BENIGN_MERCHANT_ITEMS)

        applicant = random.choice(APPLICANTS)
        department = random.choice(DEPARTMENTS)
        status = _pick_status()
        risk_level, risk_reason = _build_risk(amount, hotel_limit, is_canton_fair)

        if i in ai_risk_indices:
            ai_risk_level = "HIGH"
            ai_analysis_reason = f"商户语义风险：检测到高风险商户“{merchant}”，与常规报销场景不匹配"
        else:
            ai_risk_level = "LOW"
            ai_analysis_reason = "未发现明显语义冲突"

        amount_str = f"{amount:.2f}"
        invoice_date_str = invoice_day.strftime("%Y-%m-%d")
        filename = f"mock_invoice_{invoice_day.strftime('%Y%m%d')}_{i + 1:03d}.jpg"

        raw_json = {
            "mode": "general_fallback",
            "general": {
                "words_result": [
                    {"words": f"商户: {merchant}"},
                    {"words": f"项目: {item}"},
                    {"words": f"金额: ￥{amount_str}"},
                    {"words": f"日期: {invoice_date_str}"},
                    {"words": f"场景: {'广交会差旅' if is_canton_fair else '常规出差'}"},
                    {"words": f"报销人: {applicant}"},
                    {"words": f"部门: {department}"},
                ]
            },
            "mock_meta": {
                "merchant": merchant,
                "item": item,
                "applicant": applicant,
                "department": department,
                "seed_tag": "mock_data_gen_enterprise",
            },
        }

        invoice_id = insert_invoice(
            {
                "filename": filename,
                "amount": amount_str,
                "invoice_date": invoice_date_str,
                "applicant": applicant,
                "department": department,
                "is_canton_fair": is_canton_fair,
                "hotel_limit": hotel_limit,
                "mode": "general_fallback",
                "raw_json": raw_json,
                "created_at": now_str,
                "risk_level": risk_level,
                "risk_reason": risk_reason,
                "currency": "CNY",
                "fx_flag": False,
                "fx_reason": "",
                "manual_rate": None,
                "manual_cny_amount": None,
                "ai_risk_level": ai_risk_level,
                "ai_analysis_reason": ai_analysis_reason,
                "status": status,
                "record_state": "LEDGER",
            }
        )
        inserted_ids.append(invoice_id)

    return inserted_ids


if __name__ == "__main__":
    random.seed()
    ids = generate_mock_invoices(TOTAL_RECORDS, purge_existing=True)
    print(f"[OK] 已重建并写入 {len(ids)} 条企业化模拟数据。")
    print(f"[ID范围] {min(ids)} - {max(ids)}")
