#!/usr/bin/env python
# -*- coding: utf-8 -*-

import importlib
import os
import socket
import sys
from dataclasses import dataclass
from importlib import metadata
from typing import Any


@dataclass
class CheckResult:
    name: str
    status: str  # PASS / WARN / FAIL
    detail: str


def _emit(result: CheckResult) -> None:
    print(f"[{result.status}] {result.name:<24} {result.detail}")


def _check_python() -> CheckResult:
    version = sys.version.split()[0]
    exe = sys.executable
    if sys.version_info < (3, 10):
        return CheckResult("python", "FAIL", f"version={version}, require>=3.10, exe={exe}")
    return CheckResult("python", "PASS", f"version={version}, exe={exe}")


def _check_package(import_name: str, package_name: str | None = None) -> CheckResult:
    pkg = package_name or import_name
    try:
        importlib.import_module(import_name)
    except Exception as exc:
        return CheckResult(f"package:{pkg}", "FAIL", f"import failed: {exc}")

    try:
        ver = metadata.version(pkg)
    except Exception:
        ver = "unknown"
    return CheckResult(f"package:{pkg}", "PASS", f"installed, version={ver}")


def _check_dashscope_key() -> CheckResult:
    try:
        import config
    except Exception as exc:
        return CheckResult("config", "FAIL", f"import failed: {exc}")

    env_key = str(os.getenv("DASHSCOPE_API_KEY") or "").strip()
    cfg_key = str(getattr(config, "DASHSCOPE_API_KEY", "") or "").strip()
    key = env_key or cfg_key
    if not key or key == "sk-...":
        return CheckResult("dashscope_api_key", "WARN", "placeholder or empty")
    source = "env" if env_key else "config"
    return CheckResult("dashscope_api_key", "PASS", f"configured ({source})")


def _check_app_import() -> CheckResult:
    try:
        import app as app_module  # noqa: F401

        flask_app = getattr(app_module, "app", None)
        if flask_app is None:
            return CheckResult("app_import", "FAIL", "module loaded but `app` object missing")
        return CheckResult("app_import", "PASS", "import ok")
    except Exception as exc:
        return CheckResult("app_import", "FAIL", f"import failed: {exc}")


def _check_database() -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        from utils.db import DB_PATH, get_conn, init_db

        init_db()
        out.append(CheckResult("db_init", "PASS", f"init ok, path={DB_PATH}"))
    except Exception as exc:
        return [CheckResult("db_init", "FAIL", f"init failed: {exc}")]

    try:
        from utils.db import get_conn

        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
            row = conn.execute("SELECT COUNT(*) AS c FROM invoices").fetchone()
            total = int(row["c"]) if row else 0
            out.append(CheckResult("db_connect", "PASS", f"query ok, invoices={total}"))

            cols_rows = conn.execute("PRAGMA table_info(invoices)").fetchall()
            cols = set()
            for r in cols_rows:
                name = r["name"] if isinstance(r, dict) or hasattr(r, "keys") else r[1]
                cols.add(str(name))
            required = {"status", "applicant", "department"}
            missing = sorted(required - cols)
            if missing:
                out.append(CheckResult("db_schema", "FAIL", f"missing columns: {', '.join(missing)}"))
            else:
                out.append(CheckResult("db_schema", "PASS", "required columns exist"))
    except Exception as exc:
        out.append(CheckResult("db_connect", "FAIL", f"db check failed: {exc}"))
    return out


def _check_port(host: str = "127.0.0.1", port: int = 5000, timeout: float = 1.0) -> CheckResult:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return CheckResult("server_port_5000", "PASS", "listening")
    except Exception:
        return CheckResult("server_port_5000", "WARN", "not listening (app may not be running)")
    finally:
        try:
            s.close()
        except Exception:
            pass


def main() -> int:
    results: list[CheckResult] = []

    results.append(_check_python())
    results.append(_check_package("flask", "Flask"))
    results.append(_check_package("requests", "requests"))
    results.append(_check_package("pandas", "pandas"))
    results.append(_check_package("openpyxl", "openpyxl"))
    results.append(_check_package("dashscope", "dashscope"))
    results.append(_check_dashscope_key())
    results.append(_check_app_import())
    results.extend(_check_database())
    results.append(_check_port())

    print("=== DeepAudit_Pro Environment Check ===")
    fail_count = 0
    warn_count = 0
    for item in results:
        _emit(item)
        if item.status == "FAIL":
            fail_count += 1
        elif item.status == "WARN":
            warn_count += 1

    print("---------------------------------------")
    print(f"Summary: FAIL={fail_count}, WARN={warn_count}, TOTAL={len(results)}")
    if fail_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
