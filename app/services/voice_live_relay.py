from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any
from urllib.parse import quote

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.exceptions import ConfigurationError
from app.services.azure_auth import get_foundry_credential
from app.services.trace_store import record_trace


VOICE_LIVE_PRIMARY_SCOPE = "https://ai.azure.com/.default"
VOICE_LIVE_LEGACY_SCOPE = "https://cognitiveservices.azure.com/.default"
SUPPORTED_ASR_MODELS = {"azure-speech", "mai-transcribe-1"}


def _voice_live_host(endpoint: str) -> str:
    host = endpoint.strip().rstrip("/")
    for prefix in ("https://", "http://", "wss://", "ws://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    host = host.split("/", 1)[0]
    if ".services.ai.azure.com" in host:
        host = host.replace(".services.ai.azure.com", ".cognitiveservices.azure.com")
    return host


def _agent_identifier() -> str:
    settings = get_settings()
    return settings.resolved_voice_agent_name


def voice_live_session_update(
    *,
    voice: str = "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
    asr_model: str = "azure-speech",
    agent_model: str = "gpt-5.4",
    language: str = "zh-CN",
    vad_threshold: float = 0.26,
    prefix_padding_ms: int = 300,
    silence_duration_ms: int = 180,
) -> dict[str, Any]:
    vad_threshold = max(0.0, min(1.0, float(vad_threshold)))
    prefix_padding_ms = max(0, min(1000, int(prefix_padding_ms)))
    silence_duration_ms = max(100, min(1200, int(silence_duration_ms)))
    normalized_asr_model = asr_model if asr_model in SUPPORTED_ASR_MODELS else "azure-speech"
    normalized_language = language or ("zh-CN" if voice.startswith("zh-") else "en-US")
    settings = get_settings()

    return {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "voice": {
                "name": voice,
                "type": "azure-standard",
            },
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_sampling_rate": 24000,
            "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
            "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
            "input_audio_transcription": {"model": normalized_asr_model, "language": normalized_language},
            "turn_detection": {
                "type": "azure_semantic_vad",
                "threshold": vad_threshold,
                "prefix_padding_ms": prefix_padding_ms,
                "silence_duration_ms": silence_duration_ms,
            },
        },
    }


def _build_voice_live_agent_url(access_token: str = "") -> str:
    settings = get_settings()
    endpoint = settings.voice_live_endpoint
    if not endpoint:
        raise ConfigurationError("VOICE_LIVE_ENDPOINT is required for Voice Live Agent Mode.")
    if not settings.foundry_project_name:
        raise ConfigurationError("FOUNDRY_PROJECT_NAME is required for Voice Live Agent Mode.")

    agent_name = _agent_identifier()
    if not agent_name:
        raise ConfigurationError(
            "FOUNDRY_AGENT_NAME is required for Voice Live Agent Mode."
        )

    host = _voice_live_host(endpoint)
    request_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:10]}"
    query = [
        "trafficType=FoundryPortal",
        f"agent-name={quote(agent_name, safe='')}",
        f"agent-version={quote(settings.resolved_voice_agent_version, safe='')}",
        f"agent-project-name={quote(settings.foundry_project_name, safe='')}",
        f"api-version={quote(settings.voice_live_api_version, safe='')}",
        f"model={quote(agent_name, safe='')}",
        f"client-request-id={request_id}",
    ]
    if access_token:
        query.append(f"authorization=Bearer+{quote(access_token, safe='')}")
    return f"wss://{host}/voice-live/realtime?{'&'.join(query)}"


def _get_voice_live_token() -> str:
    credential = get_foundry_credential()
    try:
        return credential.get_token(VOICE_LIVE_PRIMARY_SCOPE).token
    except Exception:
        return credential.get_token(VOICE_LIVE_LEGACY_SCOPE).token


def _record_voice_frame(event: dict[str, Any]) -> None:
    event_type = str(event.get("type") or "voice_live.event")
    if event_type in {"response.audio.delta", "response.audio_transcript.delta"}:
        return

    if event_type == "error":
        message = str(event.get("error", {}).get("message") or "Voice Live returned an error event.")
        record_trace(
            channel="event",
            kind="voice_live_error",
            level="error",
            title="Voice Live error",
            message=message,
            payload=event,
        )
        return

    if "function" in event_type or "tool" in event_type:
        record_trace(
            channel="grounding",
            kind="agent_tool_event",
            title=f"Agent tool event: {event_type}",
            message=event.get("name") or event.get("tool_name") or event_type,
            payload=event,
        )
        return

    if event_type in {
        "session.created",
        "session.updated",
        "response.created",
        "response.done",
        "conversation.item.input_audio_transcription.completed",
    }:
        message = event.get("transcript") or event.get("response", {}).get("id") or event_type
        record_trace(
            channel="event",
            kind="voice_live_session",
            title=f"Voice Live: {event_type}",
            message=str(message),
            payload=event,
        )


async def relay_voice_live_agent(client_ws: WebSocket) -> None:
    await client_ws.accept()
    await client_ws.send_json({"type": "broker.connecting", "message": "Connecting to Voice Live Agent Mode."})
    record_trace(
        channel="event",
        kind="voice_live_broker",
        title="Voice Live broker connecting",
        message="Connecting to Voice Live Agent Mode.",
    )
    try:
        settings = get_settings()
        agent_mode = bool(_agent_identifier() and settings.foundry_project_name)
        api_key = "" if agent_mode else settings.voice_live_api_key
        if agent_mode and settings.voice_live_api_key:
            record_trace(
                channel="event",
                kind="voice_live_auth",
                title="Voice Live Agent Mode uses Entra auth",
                message="API key was ignored because key authentication is not supported in Foundry Agent mode.",
                payload={"agent_mode": True},
            )
        access_token = "" if api_key else await asyncio.to_thread(_get_voice_live_token)
        upstream_url = _build_voice_live_agent_url(access_token)
    except Exception as exc:
        record_trace(
            channel="event",
            kind="voice_live_error",
            level="error",
            title="Voice Live broker configuration failed",
            message=str(exc),
            payload={"error": str(exc), "type": type(exc).__name__},
        )
        await client_ws.send_json({"type": "error", "error": {"message": str(exc)}})
        await client_ws.close(code=1011)
        return

    try:
        connect_options: dict[str, Any] = {"max_size": None, "ping_interval": 20}
        if api_key:
            connect_options["additional_headers"] = {"api-key": api_key}
        async with websockets.connect(upstream_url, **connect_options) as upstream:
            await client_ws.send_json({"type": "broker.upstream_connected", "message": "Connected to Voice Live."})
            record_trace(
                channel="event",
                kind="voice_live_broker",
                title="Voice Live upstream connected",
                message="Connected to Voice Live Agent Mode upstream.",
            )
            await _pump(client_ws, upstream)
    except Exception as exc:
        record_trace(
            channel="event",
            kind="voice_live_error",
            level="error",
            title="Voice Live websocket closed",
            message=str(exc),
            payload={"error": str(exc), "type": type(exc).__name__},
        )
        try:
            await client_ws.send_json({"type": "error", "error": {"message": str(exc)}})
            await client_ws.close(code=1011)
        except Exception:
            pass


async def _pump(client_ws: WebSocket, upstream: Any) -> None:
    session_configured = asyncio.Event()

    async def client_to_upstream() -> None:
        try:
            while True:
                message = await client_ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if text := message.get("text"):
                    if "input_audio_buffer.append" in text and not session_configured.is_set():
                        continue
                    if "input_audio_buffer.append" not in text:
                        try:
                            event = json.loads(text)
                            if isinstance(event, dict) and event.get("type") == "session.update":
                                record_trace(
                                    channel="event",
                                    kind="voice_live_session",
                                    title="Voice Live: session.update sent",
                                    message="Browser sent session configuration to Voice Live.",
                                    payload=event,
                                )
                        except json.JSONDecodeError:
                            pass
                    await upstream.send(text)
                elif data := message.get("bytes"):
                    await upstream.send(data)
        except WebSocketDisconnect:
            return

    async def upstream_to_client() -> None:
        async for frame in upstream:
            if isinstance(frame, (bytes, bytearray)):
                await client_ws.send_bytes(bytes(frame))
            else:
                try:
                    event = json.loads(str(frame))
                    if isinstance(event, dict):
                        if event.get("type") == "session.updated":
                            session_configured.set()
                        _record_voice_frame(event)
                except json.JSONDecodeError:
                    pass
                await client_ws.send_text(str(frame))

    tasks = {
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    }
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        task.result()
