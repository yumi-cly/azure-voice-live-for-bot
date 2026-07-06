from __future__ import annotations

import time

from app.models import AgentChatRequest
from app.services.agent_service import ask_foundry_agent
from app.services.tool_service import get_demo_status, mock_robot_action


def _maybe_invoke_demo_tool(question: str) -> dict | None:
    normalized = question.lower()

    if any(keyword in normalized for keyword in ["wave", "hello", "hi", "挥手", "招呼"]):
        return mock_robot_action({"action": "wave", "target": "user"})

    if any(keyword in normalized for keyword in ["light on", "turn on", "开灯"]):
        return mock_robot_action({"action": "light_on", "target": "room_light"})

    if any(keyword in normalized for keyword in ["light off", "turn off", "关灯"]):
        return mock_robot_action({"action": "light_off", "target": "room_light"})

    if any(keyword in normalized for keyword in ["brightness", "亮度"]):
        return mock_robot_action({"action": "set_brightness", "target": "room_light", "brightness": 70})

    if any(keyword in normalized for keyword in ["status", "ready", "state", "状态", "就绪"]):
        return get_demo_status({"device": "embodied-robot", "topic": question})

    return None


def run_demo_chat(request: AgentChatRequest) -> dict:
    total_started_at = time.perf_counter()
    timings_ms: dict[str, int] = {}

    step_started_at = time.perf_counter()
    tool_payload = _maybe_invoke_demo_tool(request.question)
    timings_ms["tool"] = round((time.perf_counter() - step_started_at) * 1000)

    context_sections: list[str] = []
    if tool_payload:
        context_sections.append(f"Action result:\n{tool_payload}")

    composed_question = (
        "You are an embodied robot voice assistant. Answer in concise Chinese. "
        "Use the hosted Foundry Agent Knowledge configuration for private documents when relevant. "
        "For current public information, use the Foundry Agent web tool configured on the hosted agent.\n\n"
        + ("\n\n".join(context_sections) + "\n\n" if context_sections else "")
        + f"User question:\n{request.question}"
    )

    step_started_at = time.perf_counter()
    agent_result = ask_foundry_agent(
        composed_question,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
    )
    timings_ms["agent"] = round((time.perf_counter() - step_started_at) * 1000)
    timings_ms["total"] = round((time.perf_counter() - total_started_at) * 1000)

    return {
        "ok": True,
        "answer": agent_result["answer"],
        "agent": agent_result,
        "search": [],
        "tool": tool_payload,
        "timings_ms": timings_ms,
        "duration_ms": timings_ms["total"],
    }
