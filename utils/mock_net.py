from __future__ import annotations

import random
import time
from typing import Any


def simulate_latency(min_ms: int, max_ms: int) -> int:
    low = int(min_ms)
    high = int(max_ms)
    if low < 0:
        low = 0
    if high < 0:
        high = 0
    if high < low:
        low, high = high, low

    latency_ms = random.randint(low, high)
    time.sleep(latency_ms / 1000.0)
    return latency_ms


def should_fail(rate: float) -> bool:
    normalized_rate = max(0.0, min(1.0, float(rate)))
    return random.random() < normalized_rate


def pick_failure() -> dict[str, Any]:
    failures = [
        {
            "ok": False,
            "error_code": "timeout",
            "message": "外部服务超时，已进入待复核",
        },
        {
            "ok": False,
            "error_code": "http_500",
            "message": "外部服务异常，已进入待复核",
        },
    ]
    return dict(random.choice(failures))
