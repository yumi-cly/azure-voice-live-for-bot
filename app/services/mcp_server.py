from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.services.camera_frame_store import get_latest_frame
from app.services.tool_service import mock_robot_action
from app.services.trace_store import record_trace
from app.services.vision_service import analyze_camera_frame


mcp = FastMCP(
    "azure-voice-live-robot-demo",
    instructions=(
        "Robot demo tools. Use scan_environment only when the user explicitly asks "
        "to inspect the live camera view, the current physical scene, or objects "
        "in front of the robot. Do not use scan_environment for documents, policies, "
        "knowledge-base questions, web search, or questions about written content "
        "unless the user clearly asks to inspect the camera view. Use run_robot_action "
        "for simulated robot actions."
    ),
)


@mcp.tool()
async def scan_environment(
    question: str = "看看当前画面里有什么？",
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Analyze the latest browser camera frame for explicit live-vision requests."""
    frame = get_latest_frame()
    if not frame:
        result = {
            "ok": False,
            "tool": "scan_environment",
            "error": "No recent camera frame is available.",
            "suggested_reply": "我还没有拿到实时摄像头画面，请先打开摄像头后再让我观察。",
            "actions": [
                {
                    "name": "scan_environment",
                    "target": "front_area",
                    "status": "missing_camera_frame",
                }
            ],
        }
        record_trace(
            channel="grounding",
            kind="custom_tool",
            level="warning",
            title="MCP scan_environment",
            message=result["error"],
            payload=result,
        )
        return result

    result = await analyze_camera_frame(
        image_base64=frame["image_base64"],
        question=question,
        user_id=user_id or frame.get("user_id") or "demo-user",
    )
    result["source"] = "mcp"
    result["camera_frame_age_seconds"] = frame.get("age_seconds")
    return result


@mcp.tool()
def run_robot_action(
    action: str = "wave",
    target: str = "user",
    brightness: int | None = None,
    location: str = "front",
) -> dict[str, Any]:
    """Execute a simulated robot action and return state for the demo UI."""
    return mock_robot_action(
        {
            "action": action,
            "target": target,
            "brightness": brightness,
            "location": location,
            "source": "mcp",
        }
    )


def create_mcp_app():
    return mcp.streamable_http_app()
