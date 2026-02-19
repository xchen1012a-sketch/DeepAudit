from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, g, has_request_context, request, session

REQUEST_ID_HEADER = "X-Request-Id"
TRACE_ID_HEADER = "X-Trace-Id"
SESSION_USER_ID_KEY = "user_id"
_ANSI_RE = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")


def _normalize_log_level(raw: object) -> int:
    if isinstance(raw, int):
        return raw
    level_name = str(raw or "INFO").strip().upper()
    return getattr(logging, level_name, logging.INFO)


def _get_request_id() -> str:
    if not has_request_context():
        return "-"
    return str(getattr(g, "request_id", "-") or "-")


def _get_trace_id() -> str:
    if not has_request_context():
        return "-"
    return str(getattr(g, "trace_id", "-") or "-")


def _get_user_id() -> str:
    if not has_request_context():
        return "-"
    raw = session.get(SESSION_USER_ID_KEY)
    if raw is None:
        return "-"
    return str(raw)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _get_request_id()
        record.trace_id = _get_trace_id()
        record.user_id = _get_user_id()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        raw_message = record.getMessage()
        clean_message = _ANSI_RE.sub("", raw_message)
        clean_message = " ".join(part.strip() for part in clean_message.splitlines() if part.strip())

        # Keep Werkzeug startup/runtime lines human-readable in console.
        if record.name == "werkzeug":
            return clean_message

        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": clean_message,
            "request_id": getattr(record, "request_id", "-"),
            "trace_id": getattr(record, "trace_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(app: Flask) -> None:
    level = _normalize_log_level(app.config.get("AUDIT_LOG_LEVEL", "INFO"))
    context_filter = RequestContextFilter()

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.addFilter(context_filter)
    handler.setFormatter(JsonLogFormatter())

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(level)
    app.logger.propagate = False

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers.clear()
    werkzeug_logger.addHandler(handler)
    werkzeug_logger.setLevel(level)
    werkzeug_logger.propagate = False

    @app.before_request
    def _attach_request_meta() -> None:
        inbound_request_id = str(request.headers.get(REQUEST_ID_HEADER, "")).strip()
        inbound_trace_id = str(request.headers.get(TRACE_ID_HEADER, "")).strip()
        g.request_id = inbound_request_id or uuid4().hex
        g.trace_id = inbound_trace_id or g.request_id
        g._request_start = time.perf_counter()

    @app.after_request
    def _append_request_headers(response):  # type: ignore[no-untyped-def]
        started = getattr(g, "_request_start", None)
        duration_ms = 0.0
        if isinstance(started, (int, float)):
            duration_ms = max(0.0, (time.perf_counter() - started) * 1000.0)

        app.logger.info(
            "request completed: %s %s -> %s (%.1fms)",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        response.headers.setdefault(REQUEST_ID_HEADER, _get_request_id())
        response.headers.setdefault(TRACE_ID_HEADER, _get_trace_id())
        return response
