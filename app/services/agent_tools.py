from __future__ import annotations

import json
from typing import Any

from app.services.tool_service import (
    get_demo_status,
    mock_robot_action,
)


AGENT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_robot_status",
        "description": "Get current robot or subsystem status for the demo.",
        "parameters": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "topic": {"type": "string"},
            },
            "required": ["device"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "run_robot_action",
        "description": "Execute a demo robot action such as wave, turn a light on/off, or set brightness.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["wave", "light_on", "light_off", "set_brightness"]},
                "target": {"type": "string", "description": "For example user or room_light."},
                "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
                "location": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
]


def decode_tool_arguments(raw_arguments: str | dict | None) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    try:
        value = json.loads(raw_arguments)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def execute_agent_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    default_user_id: str,
) -> dict[str, Any]:
    if name == "get_robot_status":
        return get_demo_status(arguments)

    if name == "run_robot_action":
        return mock_robot_action(arguments)

    return {"ok": False, "error": f"Unknown agent tool: {name}"}
