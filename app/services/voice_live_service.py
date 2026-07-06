from __future__ import annotations

import asyncio
import time
from typing import Any

from azure.ai.voicelive.aio import connect
from azure.core.credentials import AzureKeyCredential

from app.config import get_settings
from app.exceptions import ConfigurationError, ExternalServiceError
from app.services.azure_auth import get_foundry_credential


def _serialize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "as_dict"):
        return event.as_dict()
    if isinstance(event, dict):
        return event
    return {"value": str(event)}


async def create_voice_live_session(conversation_id: str | None = None) -> dict:
    started_at = time.perf_counter()
    settings = get_settings()
    if not settings.voice_live_endpoint:
        raise ConfigurationError("VOICE_LIVE_ENDPOINT 还没有配置，当前无法创建真实 Voice Live 会话。")

    connect_kwargs: dict[str, Any] = {
        "endpoint": settings.voice_live_endpoint,
        "api_version": settings.voice_live_api_version,
        "connection_options": {"receive_timeout": 10, "handshake_timeout": 10},
    }

    if settings.resolved_voice_agent_name and settings.foundry_project_name:
        credential = get_foundry_credential()
        connect_kwargs.update(
            {
                "credential": credential,
                "agent_name": settings.resolved_voice_agent_name,
                "project_name": settings.foundry_project_name,
            }
        )
        if conversation_id:
            connect_kwargs["conversation_id"] = conversation_id
        session_mode = "agent"
    elif settings.foundry_model_name:
        if settings.voice_live_api_key:
            credential = AzureKeyCredential(settings.voice_live_api_key)
        else:
            credential = get_foundry_credential()
        connect_kwargs["credential"] = credential
        connect_kwargs["model"] = settings.foundry_model_name
        session_mode = "model"
    else:
        raise ConfigurationError(
            "Voice Live 需要 FOUNDRY_AGENT_NAME + FOUNDRY_PROJECT_NAME，或至少 FOUNDRY_MODEL_NAME。"
        )

    try:
        async with connect(**connect_kwargs) as connection:
            first_event = await asyncio.wait_for(connection.recv(), timeout=10)
            event_data = _serialize_event(first_event)
            if event_data.get("type") == "error":
                error_message = event_data.get("error", {}).get("message", "Voice Live 返回错误事件。")
                raise ExternalServiceError(f"Voice Live 会话创建失败: {error_message}")
            session_id = (
                event_data.get("session", {}).get("id")
                if isinstance(event_data.get("session"), dict)
                else event_data.get("id")
            )
            return {
                "ok": True,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "event_type": event_data.get("type", "session.connected"),
                "message": f"Voice Live 已通过 {session_mode} 模式建立会话。",
                "agent_tools_enabled": bool(settings.resolved_voice_agent_name),
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
                "event": event_data,
            }
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Voice Live 会话创建失败: {exc}") from exc
