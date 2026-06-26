from __future__ import annotations

import time
from threading import Lock
from typing import Any


_lock = Lock()
_latest_frame: dict[str, Any] | None = None


def save_latest_frame(
    *,
    image_base64: str,
    user_id: str = "demo-user",
    conversation_id: str | None = None,
) -> dict[str, Any]:
    global _latest_frame
    captured_at = time.time()
    frame = {
        "image_base64": image_base64,
        "user_id": user_id or "demo-user",
        "conversation_id": conversation_id,
        "captured_at": captured_at,
    }
    with _lock:
        _latest_frame = frame
    return {
        "ok": True,
        "user_id": frame["user_id"],
        "conversation_id": conversation_id,
        "captured_at": captured_at,
    }


def get_latest_frame(max_age_seconds: float = 30) -> dict[str, Any] | None:
    with _lock:
        frame = _latest_frame.copy() if _latest_frame else None
    if not frame:
        return None
    age_seconds = time.time() - float(frame.get("captured_at") or 0)
    if age_seconds > max_age_seconds:
        return None
    frame["age_seconds"] = round(age_seconds, 2)
    return frame
