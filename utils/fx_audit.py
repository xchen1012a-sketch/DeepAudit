# -*- coding: utf-8 -*-

import re
from typing import Any

import config

EXCHANGE_RATES = getattr(
    config,
    "EXCHANGE_RATES",
    {
        "CNY": 1.0,
        "USD": 7.2,
        "HKD": 0.92,
    },
)

ALLOWED_CURRENCIES = set(
    getattr(config, "ALLOWED_CURRENCIES", {"CNY", "USD", "HKD"})
)

ARBITRAGE_DEVIATION_RATIO = float(
    getattr(config, "ARBITRAGE_DEVIATION_RATIO", 0.05)
)

ARBITRAGE_DEVIATION_CNY = float(
    getattr(config, "ARBITRAGE_DEVIATION_CNY", 50.0)
)

_money_re = re.compile(r"(HK\$|\$|¥|￥)\s*([0-9][0-9,]*(?:\.[0-9]+)?)")


def _to_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", "")
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def detect_currency(text: str | None) -> str | None:
    if not text:
        return None
    t = text.upper()
    if "HK$" in t or "HKD" in t:
        return "HKD"
    if "USD" in t:
        return "USD"
    if "$" in t:
        return "USD"
    if "¥" in t or "￥" in t or "CNY" in t or "RMB" in t:
        return "CNY"
    return None


def parse_amount_from_text(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    m = _money_re.search(text)
    if not m:
        return None

    symbol = m.group(1)
    amt = _to_float(m.group(2))
    if amt is None:
        return None

    if symbol in ("¥", "￥"):
        cur = "CNY"
    elif symbol == "HK$":
        cur = "HKD"
    elif symbol == "$":
        cur = "USD"
    else:
        cur = detect_currency(text)

    return {"amount": amt, "currency": cur, "raw": m.group(0)}


def convert_to_cny(amount: float, currency: str | None) -> float | None:
    currency = (currency or "").upper().strip()
    if currency not in ALLOWED_CURRENCIES:
        return None
    rate = EXCHANGE_RATES.get(currency)
    if rate is None:
        return None
    return float(amount) * float(rate)


def audit_manual_rate_arbitrage(
    amount: float | int | str | None,
    currency: str | None,
    manual_rate: float | int | str | None = None,
    manual_cny_amount: float | int | str | None = None,
) -> dict[str, Any]:
    currency = (currency or "").upper().strip()

    if amount is None or not currency:
        return {
            "ok": True,
            "flag": False,
            "reason": "缺少金额或币种，跳过汇率套利检查",
            "details": {},
        }

    if currency not in ALLOWED_CURRENCIES:
        return {
            "ok": True,
            "flag": True,
            "reason": f"币种不在白名单：{currency}",
            "details": {"currency": currency},
        }

    cfg_rate = EXCHANGE_RATES.get(currency)
    if cfg_rate is None:
        return {
            "ok": True,
            "flag": True,
            "reason": f"缺少配置汇率：{currency}",
            "details": {"currency": currency},
        }

    details = {
        "currency": currency,
        "amount": float(amount),
        "config_rate": float(cfg_rate),
    }

    mr = _to_float(manual_rate)
    if mr is not None:
        details["manual_rate"] = mr
        deviation_ratio = abs(mr - cfg_rate) / cfg_rate
        details["manual_rate_deviation_ratio"] = deviation_ratio
        if deviation_ratio > ARBITRAGE_DEVIATION_RATIO:
            return {
                "ok": True,
                "flag": True,
                "reason": (
                    "手工汇率偏离配置汇率超过阈值（>"
                    f"{ARBITRAGE_DEVIATION_RATIO:.0%}）"
                ),
                "details": details,
            }

    mca = _to_float(manual_cny_amount)
    calc_cny = convert_to_cny(float(amount), currency)
    if mca is not None and calc_cny is not None:
        details["manual_cny_amount"] = mca
        details["calc_cny_amount"] = calc_cny
        diff = abs(mca - calc_cny)
        details["cny_diff"] = diff
        if diff > ARBITRAGE_DEVIATION_CNY:
            return {
                "ok": True,
                "flag": True,
                "reason": (
                    "手工CNY金额与配置折算差异过大（>"
                    f"{ARBITRAGE_DEVIATION_CNY:g}）"
                ),
                "details": details,
            }

    return {
        "ok": True,
        "flag": False,
        "reason": "未发现明显汇率套利特征",
        "details": details,
    }
