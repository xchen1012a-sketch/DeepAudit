from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any

_CACHE_LOCK = Lock()
_JSONL_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _copy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in rows]


def read_jsonl(path: str) -> list[dict[str, Any]]:
    normalized_path = os.path.abspath(str(path))
    if not os.path.exists(normalized_path):
        raise FileNotFoundError(f"JSONL file not found: {normalized_path}")

    try:
        current_mtime = os.path.getmtime(normalized_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to stat JSONL file: {normalized_path}; error={exc}") from exc

    with _CACHE_LOCK:
        cached = _JSONL_CACHE.get(normalized_path)
        if cached and cached[0] == current_mtime:
            return _copy_rows(cached[1])

    rows: list[dict[str, Any]] = []
    try:
        with open(normalized_path, "r", encoding="utf-8-sig") as fh:
            for line_no, line in enumerate(fh, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except Exception as exc:
                    raise ValueError(
                        f"Invalid JSON in {normalized_path} at line {line_no}: {exc}"
                    ) from exc

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Invalid JSONL record in {normalized_path} at line {line_no}: expected object"
                    )
                rows.append(record)
    except Exception as exc:
        if isinstance(exc, (FileNotFoundError, ValueError, RuntimeError)):
            raise
        raise RuntimeError(f"Failed to read JSONL file: {normalized_path}; error={exc}") from exc

    with _CACHE_LOCK:
        _JSONL_CACHE[normalized_path] = (current_mtime, rows)
    return _copy_rows(rows)
