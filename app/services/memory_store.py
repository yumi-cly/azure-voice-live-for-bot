from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
import re

from azure.cosmos import CosmosClient, exceptions

from app.config import get_settings
from app.exceptions import ConfigurationError, ExternalServiceError
from app.services.azure_auth import get_azure_credential


@lru_cache
def _cosmos_client() -> CosmosClient:
    settings = get_settings()
    if settings.resolved_cosmos_endpoint:
        credential = settings.cosmos_db_key or get_azure_credential()
        return CosmosClient(settings.resolved_cosmos_endpoint, credential=credential)
    raise ConfigurationError("COSMOS_DB_ENDPOINT or COSMOS_DB_KEY is not configured.")


def _container_client():
    settings = get_settings()
    client = _cosmos_client()
    database = client.get_database_client(settings.cosmos_db_database)
    return database.get_container_client(settings.cosmos_db_container)


def load_summary(user_id: str) -> dict[str, str]:
    try:
        item = _container_client().read_item(item=user_id, partition_key=user_id)
        return {
            "summary": item.get("summary", ""),
            "updated_at": item.get("updatedAt", datetime.now(UTC).isoformat()),
        }
    except exceptions.CosmosResourceNotFoundError:
        return {"summary": "", "updated_at": datetime.now(UTC).isoformat()}
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Cosmos DB read failed: {exc}") from exc


def save_summary(
    user_id: str,
    summary: str,
    *,
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, str]:
    record = {
        "id": user_id,
        "userId": user_id,
        "type": "conversation-summary",
        "summary": summary,
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    if session_id:
        record["lastSessionId"] = session_id
    if conversation_id:
        record["lastConversationId"] = conversation_id
    try:
        _container_client().upsert_item(record)
        return {"summary": record["summary"], "updated_at": record["updatedAt"]}
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Cosmos DB write failed: {exc}") from exc


def save_memory_event(
    user_id: str,
    *,
    session_id: str | None,
    conversation_id: str | None,
    facts: list[str],
    turn_count: int,
) -> dict | None:
    if not session_id:
        return None
    record = {
        "id": f"{user_id}:session:{session_id}",
        "userId": user_id,
        "type": "conversation-memory-event",
        "sessionId": session_id,
        "conversationId": conversation_id,
        "facts": facts,
        "turnCount": turn_count,
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    try:
        _container_client().upsert_item(record)
        return {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "facts": facts,
            "turn_count": turn_count,
            "updated_at": record["updatedAt"],
        }
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Cosmos DB memory event write failed: {exc}") from exc


def _clean_memory_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" \uff1a:\uff0c,\u3002.!?\uff01\uff1f;\uff1b")
    text = re.sub(r"^(\u6211|\u672c\u4eba)", "\u7528\u6237", text)
    if text.startswith("\u6211\u7684"):
        text = text.replace("\u6211\u7684", "\u7528\u6237\u7684", 1)
    if text and not re.search(r"[\u3002.!?\uff01\uff1f]$", text):
        text += "\u3002"
    return text


def extract_memory_facts(turns: list[dict]) -> list[str]:
    facts: list[str] = []
    patterns = [
        re.compile(r"(?:\u8bf7|\u5e2e\u6211|\u9ebb\u70e6\u4f60)?\u8bb0\u4f4f[\uff1a:\s]*(.+)", re.IGNORECASE),
        re.compile(r"(?:\u4ee5\u540e|\u4e4b\u540e).{0,8}(?:\u90fd|\u8bf7)?(.{0,20}(?:\u7528|\u56de\u7b54|\u79f0\u547c).+)", re.IGNORECASE),
        re.compile(r"(\u6211\u559c\u6b22.+)", re.IGNORECASE),
        re.compile(r"(\u6211\u7684(?:\u540d\u5b57|\u59d3\u540d|\u79f0\u547c|\u56de\u7b54\u504f\u597d|\u504f\u597d).+)", re.IGNORECASE),
        re.compile(r"(\u6211\u53eb.+)", re.IGNORECASE),
    ]
    for turn in turns:
        if str(turn.get("role") or "").lower() != "user":
            continue
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            fact = _clean_memory_text(match.group(1))
            if fact and fact not in facts:
                facts.append(fact)
            break
    return facts


def auto_save_summary(
    user_id: str,
    turns: list[dict],
    *,
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    current = load_summary(user_id)
    existing_summary = current.get("summary", "")
    facts = extract_memory_facts(turns)
    if not facts:
        return {
            "ok": True,
            "saved": False,
            "reason": "no_stable_memory_detected",
            "summary": current,
            "facts": [],
        }

    existing_items = [
        item.strip()
        for item in re.split(r"[\n]+|(?<=[\u3002.!?\uff01\uff1f])\s*", existing_summary)
        if item.strip()
    ]
    merged = existing_items[:]
    for fact in facts:
        if fact not in merged:
            merged.append(fact)

    saved = save_summary(
        user_id,
        "\n".join(merged),
        session_id=session_id,
        conversation_id=conversation_id,
    )
    memory_event = save_memory_event(
        user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        facts=facts,
        turn_count=len(turns),
    )
    return {
        "ok": True,
        "saved": True,
        "summary": saved,
        "facts": facts,
        "memory_event": memory_event,
    }
