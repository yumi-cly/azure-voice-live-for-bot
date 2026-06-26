from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any


_MAX_TRACES = 300
_lock = threading.Lock()
_next_id = 1
_traces: deque[dict[str, Any]] = deque(maxlen=_MAX_TRACES)


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except Exception:
        return {"repr": repr(value)}


def record_trace(
    *,
    channel: str,
    kind: str,
    title: str,
    message: str = "",
    level: str = "info",
    payload: Any = None,
) -> dict[str, Any]:
    global _next_id
    with _lock:
        trace = {
            "id": _next_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "channel": channel,
            "kind": kind,
            "level": level,
            "title": title,
            "message": message,
            "payload": _json_safe(payload or {}),
        }
        _next_id += 1
        _traces.append(trace)
        return trace


def snapshot_traces(since_id: int = 0) -> dict[str, Any]:
    with _lock:
        records = [trace for trace in _traces if trace["id"] > since_id]
        latest_id = _traces[-1]["id"] if _traces else since_id

    return {
        "ok": True,
        "latest_id": latest_id,
        "events": [trace for trace in records if trace["channel"] == "event"],
        "grounding": [trace for trace in records if trace["channel"] == "grounding"],
    }
