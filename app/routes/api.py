from fastapi import APIRouter, Response, WebSocket

from app.models import (
    AgentChatRequest,
    ContextAutoSaveRequest,
    ContextLoadRequest,
    ContextSaveRequest,
    MediaToolRequest,
    NavigationToolRequest,
    ToolRequest,
    TtsRequest,
    VisionFrameRequest,
    VisionLatestFrameRequest,
    VoiceSessionRequest,
)
from app.services.agent_service import ask_foundry_agent
from app.services.camera_frame_store import save_latest_frame
from app.services.memory_store import auto_save_summary, load_summary, save_summary
from app.services.resource_profile import get_resource_profile
from app.services.tool_service import control_media, control_navigation, get_demo_status, mock_robot_action
from app.services.trace_store import record_trace, snapshot_traces
from app.services.tts_service import synthesize_speech
from app.services.vision_service import analyze_camera_frame
from app.services.voice_live_relay import relay_voice_live_agent, voice_live_session_update
from app.services.voice_live_service import create_voice_live_session


router = APIRouter()


@router.get("/config")
def config() -> dict:
    return get_resource_profile()


@router.get("/traces")
def traces(since_id: int = 0) -> dict:
    return snapshot_traces(since_id)


@router.post("/session")
async def session(request: VoiceSessionRequest | None = None) -> dict:
    payload = request or VoiceSessionRequest()
    result = await create_voice_live_session(payload.conversation_id)
    record_trace(
        channel="event",
        kind="voice_live_session",
        title="Voice Live session created",
        message=result.get("message", "Voice Live session created."),
        payload=result,
    )
    return result


@router.get("/voice/config")
def voice_config(
    voice: str = "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
    language: str = "zh",
    vad_threshold: float = 0.26,
    prefix_padding_ms: int = 300,
    silence_duration_ms: int = 220,
) -> dict:
    return voice_live_session_update(
        voice=voice,
        language=language,
        vad_threshold=vad_threshold,
        prefix_padding_ms=prefix_padding_ms,
        silence_duration_ms=silence_duration_ms,
    )


@router.websocket("/voice/ws")
async def voice_ws(websocket: WebSocket) -> None:
    await relay_voice_live_agent(websocket)


@router.post("/tts/synthesize")
async def tts_synthesize(request: TtsRequest) -> Response:
    audio = await synthesize_speech(request.text, request.voice)
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/vision/analyze-frame")
async def vision_analyze_frame(request: VisionFrameRequest) -> dict:
    return await analyze_camera_frame(
        image_base64=request.image_base64,
        question=request.question,
        user_id=request.user_id,
    )


@router.post("/vision/latest-frame")
async def vision_latest_frame(request: VisionLatestFrameRequest) -> dict:
    return save_latest_frame(
        image_base64=request.image_base64,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
    )


@router.post("/context/load")
def context_load(request: ContextLoadRequest) -> dict:
    result = {"user_id": request.user_id, "summary": load_summary(request.user_id)}
    record_trace(
        channel="grounding",
        kind="memory_tool",
        title="Cosmos DB memory read",
        message=f"Loaded memory summary for {request.user_id}.",
        payload=result,
    )
    return result


@router.post("/context/save")
def context_save(request: ContextSaveRequest) -> dict:
    save_summary(request.user_id, request.summary)
    record_trace(
        channel="grounding",
        kind="memory_tool",
        title="Cosmos DB memory write",
        message=f"Saved memory summary for {request.user_id}.",
        payload={"user_id": request.user_id, "saved": True, "summary_preview": request.summary[:240]},
    )
    return {"ok": True}


@router.post("/context/auto-save")
def context_auto_save(request: ContextAutoSaveRequest) -> dict:
    turns = [turn.model_dump() for turn in request.turns]
    result = auto_save_summary(
        request.user_id,
        turns,
        session_id=request.session_id,
        conversation_id=request.conversation_id,
    )
    payload = {
        **result,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "conversation_id": request.conversation_id,
        "turn_count": len(turns),
    }
    record_trace(
        channel="grounding",
        kind="memory_tool",
        title="Cosmos DB memory auto-save",
        message=(
            f"Auto-saved memory for {request.user_id}."
            if result.get("saved")
            else f"No stable memory detected for {request.user_id}."
        ),
        payload=payload,
    )
    return payload


@router.post("/tools/mock-robot-action")
def tool_robot_action(request: ToolRequest) -> dict:
    return mock_robot_action(request.model_dump())


@router.post("/tools/get-demo-status")
def tool_status(request: ToolRequest) -> dict:
    return get_demo_status(request.model_dump())


@router.post("/tools/media-control")
def tool_media_control(request: MediaToolRequest) -> dict:
    return control_media(request.model_dump())


@router.post("/tools/navigation")
def tool_navigation(request: NavigationToolRequest) -> dict:
    return control_navigation(request.model_dump())


@router.post("/agent/chat")
def agent_chat(request: AgentChatRequest) -> dict:
    return ask_foundry_agent(
        question=request.question,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
    )
