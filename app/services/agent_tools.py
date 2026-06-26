from __future__ import annotations

import json
from typing import Any

from app.services.memory_store import load_summary, save_summary
from app.services.search_service import search_knowledge
from app.services.tool_service import (
    get_demo_status,
    mock_robot_action,
)
from app.services.trace_store import record_trace


AGENT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "read_memory",
        "description": "Read the user's long-term cross-session memory summary from Cosmos DB.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID, for example demo-user."}
            },
            "required": ["user_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "write_memory",
        "description": "Save an updated long-term memory summary for the user into Cosmos DB.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "summary": {"type": "string", "description": "Concise durable memory summary."},
            },
            "required": ["user_id", "summary"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_knowledge",
        "description": "Search the private enterprise knowledge base in Azure AI Search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "top": {"type": "integer", "description": "Number of snippets to retrieve.", "default": 3},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
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
    if name == "read_memory":
        user_id = arguments.get("user_id") or default_user_id
        result = {"ok": True, "user_id": user_id, "summary": load_summary(user_id)}
        record_trace(
            channel="grounding",
            kind="memory_tool",
            title="Cosmos DB memory read",
            message=f"Loaded memory summary for {user_id}.",
            payload=result,
        )
        return result

    if name == "write_memory":
        user_id = arguments.get("user_id") or default_user_id
        summary = str(arguments.get("summary") or "")
        save_summary(user_id, summary)
        result = {"ok": True, "user_id": user_id, "saved": True}
        record_trace(
            channel="grounding",
            kind="memory_tool",
            title="Cosmos DB memory write",
            message=f"Saved memory summary for {user_id}.",
            payload={**result, "summary_preview": summary[:240]},
        )
        return result

    if name in {"search_knowledge", "search_knowledge_base"}:
        return search_knowledge(str(arguments.get("query") or ""), top=int(arguments.get("top") or 3))

    if name == "get_robot_status":
        return get_demo_status(arguments)

    if name == "run_robot_action":
        return mock_robot_action(arguments)

    return {"ok": False, "error": f"Unknown agent tool: {name}"}
