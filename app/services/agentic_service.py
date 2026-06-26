from __future__ import annotations

import json
import time
from typing import Any

from azure.ai.projects import AIProjectClient
from openai import OpenAI

from app.config import get_settings
from app.exceptions import ConfigurationError, ExternalServiceError
from app.models import AgentChatRequest
from app.services.agent_service import _dump_optional_model, _extract_conversation_id
from app.services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    decode_tool_arguments,
    execute_agent_tool,
)
from app.services.azure_auth import get_foundry_credential
from app.services.search_service import search_knowledge


AGENTIC_INSTRUCTIONS = """
You are an robot voice agent.
Use the available tools to decide what evidence or action is needed before answering.
For company or uploaded-document questions, call search_knowledge before answering.
Call read_memory when user preferences, prior context, or cross-session continuity may matter.
Call run_robot_action for wave, light on/off, and brightness requests.
Answer in concise Chinese by default. Use plain text only: no Markdown headings, no bold markers,
no code fences, no tables, and no Markdown bullet syntax. Prefer short paragraphs or simple numbered
sentences when structure is needed. Do not invent facts when tools return insufficient evidence.
""".strip()


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                parts.append(str(value))
    return "\n".join(parts).strip()


def _response_tool_calls(response: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None)
        if item_type != "function_call":
            continue
        calls.append(
            {
                "call_id": getattr(item, "call_id", None),
                "name": getattr(item, "name", None),
                "arguments": decode_tool_arguments(getattr(item, "arguments", None)),
            }
        )
    return [call for call in calls if call["call_id"] and call["name"]]


def _openai_client_for_agentic() -> tuple[Any, AIProjectClient | None, str]:
    settings = get_settings()
    project_endpoint = settings.foundry_project_endpoint
    api_key = settings.foundry_api_key
    if not project_endpoint:
        raise ConfigurationError("FOUNDRY_PROJECT_ENDPOINT is not configured.")

    agent_name = settings.resolved_voice_agent_name
    hosted_agent_configured = bool(agent_name)
    mode = "hosted-agent" if hosted_agent_configured else "model-tools"
    if not settings.foundry_model_name and not hosted_agent_configured:
        raise ConfigurationError("Configure FOUNDRY_AGENT_NAME or FOUNDRY_MODEL_NAME before calling Foundry.")

    if not hosted_agent_configured and api_key and settings.foundry_model_name:
        base_url = f"{project_endpoint}/openai/v1"
        return OpenAI(api_key=api_key, base_url=base_url), None, "model-tools"

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=get_foundry_credential(),
        allow_preview=mode == "hosted-agent",
    )
    openai_client = (
        project_client.get_openai_client(agent_name=agent_name)
        if mode == "hosted-agent"
        else project_client.get_openai_client()
    )
    return openai_client, project_client, mode


def _summarize_tool_result(name: str, result: dict[str, Any]) -> dict[str, Any] | None:
    if name in {"search_knowledge", "search_knowledge_base"}:
        return {"kind": "knowledge", "results": result.get("results", [])}
    if name == "read_memory":
        return {"kind": "memory", **result}
    if name in {"get_robot_status", "run_robot_action"}:
        return {"kind": "custom_tool", **result}
    return None


def _format_knowledge_evidence(results: list[dict[str, Any]]) -> str:
    evidence_blocks: list[str] = []
    for index, item in enumerate(results, start=1):
        title = item.get("title") or item.get("source_file") or "knowledge"
        source_file = item.get("source_file") or ""
        page_number = item.get("page_number")
        page_label = f", page {page_number}" if page_number else ""
        preview = str(item.get("content_preview") or "").strip()
        if not preview:
            continue
        source_label = f"{title}"
        if source_file and source_file != title:
            source_label = f"{title} / {source_file}"
        evidence_blocks.append(f"[{index}] {source_label}{page_label}\n{preview}")
    return "\n\n".join(evidence_blocks)


def _build_grounded_agent_input(
    question: str,
    knowledge_results: list[dict[str, Any]],
) -> str:
    knowledge_evidence = _format_knowledge_evidence(knowledge_results)

    context_sections: list[str] = []
    if knowledge_evidence:
        context_sections.append(
            "Private knowledge base evidence from Azure AI Search. Prefer this for company or uploaded-document questions:\n"
            f"{knowledge_evidence}"
        )
    if not context_sections:
        context_sections.append("No broker-provided evidence was found for this turn.")

    return f"""
User question:
{question}

Policy:
- Use private knowledge base evidence when it is relevant.
- For current public information, rely on the hosted Foundry Agent's configured web tool instead of broker-side web search.

Grounding context prepared by the broker:

{chr(10).join(context_sections)}

Answer requirements: respond in concise Chinese plain text. Do not use Markdown headings,
bold markers, code fences, or tables. If evidence is insufficient, say what is missing.
""".strip()


def run_agentic_chat(request: AgentChatRequest) -> dict:
    total_started_at = time.perf_counter()
    settings = get_settings()
    openai_client, project_client, mode = _openai_client_for_agentic()
    tool_events: list[dict[str, Any]] = []
    tool_results_by_kind: dict[str, Any] = {
        "knowledge": [],
        "memory": None,
        "custom_tool": None,
    }
    timings_ms: dict[str, int] = {
        "memory": 0,
        "ai_search": 0,
        "tool": 0,
    }

    agent_input = request.question
    knowledge_results: list[dict[str, Any]] = []
    if request.include_search:
        search_top = max(1, min(int(request.top or 3), 8))
        started_at = time.perf_counter()
        knowledge_result = search_knowledge(request.question, top=search_top)
        elapsed = round((time.perf_counter() - started_at) * 1000)
        timings_ms["ai_search"] += elapsed

        knowledge_results = knowledge_result.get("results", [])
        tool_results_by_kind["knowledge"].extend(knowledge_results)
        tool_events.append(
            {
                "name": "search_knowledge",
                "arguments": {"query": request.question, "top": search_top, "stage": "pre_agent"},
                "result": knowledge_result,
                "duration_ms": elapsed,
            }
        )

    agent_input = _build_grounded_agent_input(
        request.question,
        knowledge_results,
    )

    request_payload: dict[str, Any] = {
        "input": agent_input,
        "user": request.user_id,
        "store": True,
    }
    if mode == "model-tools":
        request_payload["model"] = settings.foundry_model_name
        request_payload["instructions"] = AGENTIC_INSTRUCTIONS
        request_payload["tools"] = AGENT_TOOL_DEFINITIONS
        request_payload["parallel_tool_calls"] = True
    if request.conversation_id:
        request_payload["conversation"] = request.conversation_id

    try:
        agent_started_at = time.perf_counter()
        response = openai_client.responses.create(**request_payload)
        agent_duration = round((time.perf_counter() - agent_started_at) * 1000)
        response_count = 1

        while response_count <= 8:
            tool_calls = _response_tool_calls(response)
            if not tool_calls:
                break

            tool_outputs: list[dict[str, str]] = []
            for tool_call in tool_calls:
                name = tool_call["name"]
                started_at = time.perf_counter()
                result = execute_agent_tool(
                    name,
                    tool_call["arguments"],
                    default_user_id=request.user_id,
                )
                elapsed = round((time.perf_counter() - started_at) * 1000)
                tool_events.append(
                    {
                        "name": name,
                        "arguments": tool_call["arguments"],
                        "result": result,
                        "duration_ms": elapsed,
                    }
                )

                if name == "read_memory":
                    timings_ms["memory"] += elapsed
                elif name in {"search_knowledge", "search_knowledge_base"}:
                    timings_ms["ai_search"] += elapsed
                else:
                    timings_ms["tool"] += elapsed

                summary = _summarize_tool_result(name, result)
                if summary:
                    kind = summary.pop("kind")
                    if kind == "knowledge":
                        tool_results_by_kind["knowledge"].extend(summary.get("results", []))
                    else:
                        tool_results_by_kind[kind] = summary

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call["call_id"],
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            agent_started_at = time.perf_counter()
            follow_up_payload: dict[str, Any] = {
                "input": tool_outputs,
                "previous_response_id": response.id,
                "store": True,
            }
            if mode == "model-tools":
                follow_up_payload["model"] = settings.foundry_model_name
                follow_up_payload["tools"] = AGENT_TOOL_DEFINITIONS
                follow_up_payload["parallel_tool_calls"] = True
            response = openai_client.responses.create(**follow_up_payload)
            agent_duration += round((time.perf_counter() - agent_started_at) * 1000)
            response_count += 1

        answer = _response_text(response)
        timings_ms["agent"] = agent_duration
        timings_ms["total"] = round((time.perf_counter() - total_started_at) * 1000)

        return {
            "ok": True,
            "answer": answer or "Agent completed, but no displayable text was returned.",
            "agent": {
                "ok": True,
                "mode": f"{mode}-tool-orchestration",
                "answer": answer,
                "response_id": response.id,
                "conversation_id": _extract_conversation_id(getattr(response, "conversation", None)),
                "status": getattr(response, "status", None),
                "model": getattr(response, "model", None),
                "usage": _dump_optional_model(getattr(response, "usage", None)),
                "duration_ms": agent_duration,
            },
            "memory": tool_results_by_kind["memory"],
            "search": tool_results_by_kind["knowledge"],
            "tool": tool_results_by_kind["custom_tool"],
            "tool_calls": tool_events,
            "timings_ms": timings_ms,
            "duration_ms": timings_ms["total"],
            "orchestration": "foundry-agent-tool-calling",
        }
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Agentic Foundry orchestration failed: {exc}") from exc
    finally:
        if project_client:
            project_client.close()
