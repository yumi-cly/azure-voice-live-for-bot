from __future__ import annotations

from app.services.trace_store import record_trace


MEDIA_DEFAULTS = {
    "Radio": "FM 101.5",
    "Music": "Robot Ops Playlist",
    "Podcast": "AI Factory Briefing",
    "Audiobook": "Autonomous Systems 101",
}

ACTION_STATE = {
    "wave": "idle",
    "light_on": False,
    "brightness": 55,
    "last_action": "none",
}


def _record_tool_result(result: dict) -> dict:
    record_trace(
        channel="grounding",
        kind="custom_tool",
        title=f"Custom tool: {result.get('tool', 'unknown')}",
        message=result.get("message") or result.get("status") or "Custom tool returned.",
        payload=result,
    )
    return result


def mock_robot_action(payload: dict) -> dict:
    action = str(payload.get("action") or "wave").lower().strip()
    target = payload.get("target") or "user"
    location = payload.get("location") or "front"
    brightness = payload.get("brightness")

    if action in {"turn_on_light", "light_on", "open_light"}:
        action = "light_on"
        ACTION_STATE["light_on"] = True
    elif action in {"turn_off_light", "light_off", "close_light"}:
        action = "light_off"
        ACTION_STATE["light_on"] = False
    elif action in {"set_brightness", "brightness"}:
        action = "set_brightness"
        if brightness is None:
            brightness = payload.get("value", ACTION_STATE["brightness"])
        ACTION_STATE["brightness"] = max(0, min(100, int(brightness)))
        ACTION_STATE["light_on"] = ACTION_STATE["brightness"] > 0
    elif action in {"wave", "greet"}:
        action = "wave"
        ACTION_STATE["wave"] = "completed"
    else:
        action = action or "wave"

    ACTION_STATE["last_action"] = action
    if action != "wave":
        ACTION_STATE["wave"] = "idle"

    result = {
        "ok": True,
        "tool": "run_robot_action",
        "action": action,
        "target": target,
        "location": location,
        "status": "completed",
        "state": ACTION_STATE.copy(),
        "message": (
            f"Action completed: {action}. "
            f"Light={'on' if ACTION_STATE['light_on'] else 'off'}, brightness={ACTION_STATE['brightness']}%."
        ),
    }
    _record_tool_result(result)

    if action == "wave":
        ACTION_STATE["wave"] = "idle"

    return result


def get_demo_status(payload: dict) -> dict:
    device = payload.get("device") or "robot"
    topic = payload.get("topic") or "overview"
    return _record_tool_result({
        "ok": True,
        "tool": "get_demo_status",
        "device": device,
        "topic": topic,
        "status": "ready",
        "source": "demo",
        "action_state": ACTION_STATE.copy(),
    })


def control_media(payload: dict) -> dict:
    media_type = payload.get("media_type") or "Radio"
    volume = max(0, min(100, int(payload.get("volume", 70))))
    station = payload.get("station") or MEDIA_DEFAULTS.get(media_type, "Default media source")
    state = payload.get("state") or "playing"
    return _record_tool_result({
        "ok": True,
        "tool": "media_control",
        "media_type": media_type,
        "volume": volume,
        "station": station,
        "state": state,
        "message": f"{media_type} is now {state} on {station} at volume {volume}%.",
    })


def control_navigation(payload: dict) -> dict:
    destination = payload.get("destination") or payload.get("location") or "inspection-zone-a"
    active = bool(payload.get("active", True))
    mode = payload.get("mode") or "guided"
    eta_minutes = max(3, min(25, len(destination) % 18 + 4))
    return _record_tool_result({
        "ok": True,
        "tool": "navigation_service",
        "destination": destination,
        "active": active,
        "mode": mode,
        "eta_minutes": eta_minutes,
        "message": (
            f"Navigation {'activated' if active else 'paused'} for {destination}. "
            f"Estimated arrival in {eta_minutes} minutes."
        ),
    })
