#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Iterable

import requests

import config


@dataclass
class CheckResult:
    name: str
    status: str  # PASS / FAIL / SKIP
    detail: str


def _fmt(status: str) -> str:
    if status == "PASS":
        return "[PASS]"
    if status == "FAIL":
        return "[FAIL]"
    return "[SKIP]"


def _safe_json(resp: requests.Response) -> dict[str, Any] | None:
    try:
        value = resp.json()
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _run_http_check(
    session: requests.Session,
    name: str,
    method: str,
    url: str,
    timeout: float,
    expected_codes: Iterable[int],
    **kwargs: Any,
) -> CheckResult:
    try:
        resp = session.request(method=method, url=url, timeout=timeout, **kwargs)
    except Exception as exc:
        return CheckResult(name=name, status="FAIL", detail=f"request failed: {exc}")

    if resp.status_code not in set(expected_codes):
        return CheckResult(
            name=name,
            status="FAIL",
            detail=f"unexpected status {resp.status_code}, body={resp.text[:200]}",
        )

    return CheckResult(name=name, status="PASS", detail=f"status={resp.status_code}")


def check_http(base_url: str, timeout: float) -> list[CheckResult]:
    session = requests.Session()
    out: list[CheckResult] = []

    out.append(
        _run_http_check(
            session,
            name="index",
            method="GET",
            url=f"{base_url}/",
            timeout=timeout,
            expected_codes={200},
        )
    )

    invoices_result = _run_http_check(
        session,
        name="invoices_list",
        method="GET",
        url=f"{base_url}/invoices",
        timeout=timeout,
        expected_codes={200},
        headers={"Accept": "application/json"},
    )
    out.append(invoices_result)

    if invoices_result.status == "PASS":
        try:
            resp = session.get(f"{base_url}/invoices", timeout=timeout, headers={"Accept": "application/json"})
            payload = _safe_json(resp) or {}
            if payload.get("ok") is not True or not isinstance(payload.get("data"), list):
                out.append(CheckResult("invoices_payload", "FAIL", "payload schema invalid"))
            else:
                out.append(CheckResult("invoices_payload", "PASS", f"rows={len(payload.get('data') or [])}"))
        except Exception as exc:
            out.append(CheckResult("invoices_payload", "FAIL", f"parse error: {exc}"))

    out.append(
        _run_http_check(
            session,
            name="dashboard_stats",
            method="GET",
            url=f"{base_url}/api/dashboard/stats",
            timeout=timeout,
            expected_codes={200},
            params={"range": "30d"},
            headers={"Accept": "application/json"},
        )
    )

    try:
        resp = session.get(
            f"{base_url}/api/dashboard/stats",
            params={"range": "30d"},
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        payload = _safe_json(resp) or {}
        data = payload.get("data") if isinstance(payload, dict) else None
        required = {"summary", "risk_distribution", "status_distribution", "daily_trend"}
        if payload.get("ok") is True and isinstance(data, dict) and required.issubset(set(data.keys())):
            out.append(CheckResult("dashboard_payload", "PASS", "schema ok"))
        else:
            out.append(CheckResult("dashboard_payload", "FAIL", "schema missing required fields"))
    except Exception as exc:
        out.append(CheckResult("dashboard_payload", "FAIL", f"parse error: {exc}"))

    out.append(
        _run_http_check(
            session,
            name="status_update_invalid",
            method="POST",
            url=f"{base_url}/api/invoice/0/status",
            timeout=timeout,
            expected_codes={400},
            json={"status": "INVALID"},
            headers={"Accept": "application/json"},
        )
    )

    out.append(
        _run_http_check(
            session,
            name="status_update_not_found",
            method="POST",
            url=f"{base_url}/api/invoice/0/status",
            timeout=timeout,
            expected_codes={404},
            json={"status": "APPROVED"},
            headers={"Accept": "application/json"},
        )
    )

    export_result = _run_http_check(
        session,
        name="export_excel",
        method="GET",
        url=f"{base_url}/export",
        timeout=timeout,
        expected_codes={200},
    )
    out.append(export_result)

    if export_result.status == "PASS":
        try:
            resp = session.get(f"{base_url}/export", timeout=timeout)
            content_type = resp.headers.get("Content-Type", "")
            if "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content_type:
                out.append(CheckResult("export_content_type", "PASS", content_type))
            else:
                out.append(CheckResult("export_content_type", "FAIL", f"unexpected content-type: {content_type}"))
        except Exception as exc:
            out.append(CheckResult("export_content_type", "FAIL", f"check failed: {exc}"))

    return out


def check_dashscope() -> CheckResult:
    api_key = os.getenv("DASHSCOPE_API_KEY") or getattr(config, "DASHSCOPE_API_KEY", "")
    if not api_key or str(api_key).strip() in {"", "sk-..."}:
        return CheckResult("dashscope_api", "SKIP", "DASHSCOPE_API_KEY is placeholder or missing")

    try:
        import dashscope
        from dashscope import Generation

        dashscope.api_key = api_key
        model_name = os.getenv("LLM_MODEL_NAME") or getattr(config, "LLM_MODEL_NAME", "qwen-turbo")
        resp = Generation.call(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": 'Output strict JSON only: {"risk_level":"LOW","reason":"ok"}',
                },
                {"role": "user", "content": "health check"},
            ],
            temperature=0.1,
            result_format="message",
        )

        text = ""
        to_dict = getattr(resp, "to_dict", None)
        if callable(to_dict):
            data = to_dict()
        elif isinstance(resp, dict):
            data = resp
        else:
            data = {"raw": str(resp)}

        output = data.get("output", {})
        choices = output.get("choices", []) if isinstance(output, dict) else []
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message", {}) if isinstance(first, dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                chunks = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        chunks.append(item["text"])
                text = "\n".join(chunks).strip()

        if not text:
            text = json.dumps(data, ensure_ascii=False)[:240]

        return CheckResult("dashscope_api", "PASS", f"response={text[:120]}")
    except Exception as exc:
        return CheckResult("dashscope_api", "FAIL", f"{exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepAudit_Pro API diagnose tool")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Flask service base URL")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"Diagnose target: {args.base_url}")
    print("-" * 60)

    results = check_http(base_url=args.base_url.rstrip("/"), timeout=args.timeout)
    results.append(check_dashscope())

    fail_count = 0
    for item in results:
        print(f"{_fmt(item.status)} {item.name:<24} {item.detail}")
        if item.status == "FAIL":
            fail_count += 1

    print("-" * 60)
    if fail_count:
        print(f"Result: FAILED ({fail_count} checks failed)")
        return 1

    print("Result: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
