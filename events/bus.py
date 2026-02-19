from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any


class EventBus:
    def __init__(self, max_events: int = 500) -> None:
        self._events: list[dict[str, Any]] = []
        self._lock = Lock()
        self._max_events = max(1, int(max_events))
        self._next_id = 1

    def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "id": 0,
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": str(event_type),
            "payload": dict(payload or {}),
        }
        with self._lock:
            event["id"] = self._next_id
            self._next_id += 1
            self._events.append(event)
            if len(self._events) > self._max_events:
                overflow = len(self._events) - self._max_events
                if overflow > 0:
                    del self._events[:overflow]
        return dict(event)

    def get_since(self, cursor: int) -> tuple[list[dict[str, Any]], int]:
        try:
            normalized_cursor = int(cursor)
        except Exception:
            normalized_cursor = 0
        if normalized_cursor < 0:
            normalized_cursor = 0

        with self._lock:
            events = [dict(item) for item in self._events if int(item.get("id", 0)) > normalized_cursor]
            if events:
                new_cursor = int(events[-1]["id"])
            elif self._events:
                new_cursor = max(normalized_cursor, int(self._events[-1].get("id", normalized_cursor)))
            else:
                new_cursor = normalized_cursor
        return events, new_cursor
