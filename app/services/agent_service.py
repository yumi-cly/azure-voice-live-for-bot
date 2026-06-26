from __future__ import annotations

import time
from typing import Any

from azure.ai.projects import AIProjectClient
from openai import OpenAI

from app.config import get_settings
from app.exceptions import ConfigurationError, ExternalServiceError
from app.services.azure_auth import get_foundry_credential


def _extract_conversation_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value and hasattr(value, "id"):
        return getattr(value, "id")
    return None


def _dump_optional_model(value: Any) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return None


def ask_foundry_agent(
    question: str,
    *,
    user_id: str = "demo-user",
    conversation_id: str | None = None,
    instructions: str | None = None,
) -> dict:
    settings = get_settings()
    project_endpoint = settings.foundry_project_endpoint
    api_key = settings.foundry_api_key
    if not project_endpoint:
        raise ConfigurationError(
            "FOUNDRY_PROJECT_ENDPOINT 还没有配置，当前无法调用真实 Foundry Agent。"
        )

    agent_name = settings.resolved_voice_agent_name
    mode = "agent" if agent_name else "model"
    if mode == "model" and not settings.foundry_model_name:
        raise ConfigurationError(
            "请至少配置 FOUNDRY_AGENT_NAME 或 FOUNDRY_MODEL_NAME，才能调用 Foundry。"
        )

    if api_key and mode == "model":
        try:
            openai_client = OpenAI(
                api_key=api_key,
                base_url=f"{project_endpoint}/openai/v1",
            )
            request_payload: dict[str, Any] = {
                "input": question,
                "user": user_id,
                "store": True,
                "model": settings.foundry_model_name,
            }
            if conversation_id:
                request_payload["conversation"] = conversation_id
            if instructions:
                request_payload["instructions"] = instructions

            started_at = time.perf_counter()
            response = openai_client.responses.create(**request_payload)
            answer = (response.output_text or "").strip()
            return {
                "ok": True,
                "mode": mode,
                "answer": answer or "Foundry 返回成功，但当前响应没有可展示的文本内容。",
                "response_id": response.id,
                "conversation_id": _extract_conversation_id(response.conversation),
                "status": response.status,
                "model": response.model,
                "usage": _dump_optional_model(getattr(response, "usage", None)),
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            }
        except Exception as exc:  # pragma: no cover - external service branch
            raise ExternalServiceError(f"Foundry Agent 调用失败: {exc}") from exc

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=get_foundry_credential(),
        allow_preview=mode == "agent",
    )

    try:
        openai_client = (
            project_client.get_openai_client(agent_name=agent_name)
            if mode == "agent"
            else project_client.get_openai_client()
        )

        request_payload: dict[str, Any] = {
            "input": question,
            "user": user_id,
            "store": True,
        }
        if conversation_id:
            request_payload["conversation"] = conversation_id
        if mode == "model":
            request_payload["model"] = settings.foundry_model_name
            if instructions:
                request_payload["instructions"] = instructions

        started_at = time.perf_counter()
        response = openai_client.responses.create(**request_payload)
        answer = (response.output_text or "").strip()

        return {
            "ok": True,
            "mode": mode,
            "answer": answer or "Foundry 返回成功，但当前响应没有可展示的文本内容。",
            "response_id": response.id,
            "conversation_id": _extract_conversation_id(response.conversation),
            "status": response.status,
            "model": response.model,
            "usage": _dump_optional_model(getattr(response, "usage", None)),
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
        }
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Foundry Agent 调用失败: {exc}") from exc
    finally:
        project_client.close()
