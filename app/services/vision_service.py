import asyncio
import json
import re
from time import perf_counter

from azure.ai.projects import AIProjectClient

from app.config import get_settings
from app.exceptions import DemoAppError
from app.services.azure_auth import get_foundry_credential
from app.services.trace_store import record_trace


def _extract_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _parse_vision_json(text: str) -> dict:
    json_text = re.sub(r"^```json\s*|^```\s*|```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return {
            "summary": text.strip(),
            "suggested_reply": f"我观察到：{text.strip()}",
            "objects": [],
        }

    summary = str(parsed.get("summary") or "我看到了前方环境，但还需要你进一步确认细节。").strip()
    suggested_reply = str(parsed.get("suggested_reply") or parsed.get("suggestedReply") or f"我观察到：{summary}").strip()
    objects = parsed.get("objects") if isinstance(parsed.get("objects"), list) else []
    return {
        "summary": summary,
        "suggested_reply": suggested_reply,
        "objects": [str(item) for item in objects[:8]],
    }


async def analyze_camera_frame(image_base64: str, question: str, user_id: str = "demo-user") -> dict:
    settings = get_settings()
    if not image_base64.startswith("data:image/"):
        raise DemoAppError("Camera frame must be a data:image URL.", status_code=400)
    if not settings.foundry_project_endpoint:
        raise DemoAppError("FOUNDRY_PROJECT_ENDPOINT is not configured.", status_code=400)

    model = settings.foundry_vision_deployment or settings.foundry_model_name or "gpt-5.4"
    started_at = perf_counter()
    prompt = (
        "你是机器人助手，面向家庭陪伴、创客教育、编程学习和产品演示。\n"
        "请观察这张机器人摄像头截图，回答用户问题。\n"
        "重点描述前方环境里可见的主要物体，回答要适合语音播报。\n"
        "请严格返回 JSON："
        '{"summary":"一句话画面描述","objects":["物体1","物体2"],"suggested_reply":"机器人可以对用户说的话"}\n'
        f"用户问题：{question}"
    )

    def call_foundry_vision() -> object:
        project_client = AIProjectClient(
            endpoint=settings.foundry_project_endpoint,
            credential=get_foundry_credential(),
            allow_preview=True,
        )
        try:
            openai_client = project_client.get_openai_client()
            return openai_client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": image_base64, "detail": "low"},
                        ],
                    }
                ],
                max_output_tokens=400,
            )
        finally:
            project_client.close()

    try:
        response = await asyncio.to_thread(call_foundry_vision)
    except Exception as exc:  # pragma: no cover - external service branch
        raise DemoAppError(f"Foundry vision request failed: {exc}", status_code=502) from exc

    duration_ms = round((perf_counter() - started_at) * 1000)

    raw_text = _extract_output_text(response)
    if not raw_text:
        raise DemoAppError("Foundry vision response did not include output text.", status_code=502)

    parsed = _parse_vision_json(raw_text)
    result = {
        "ok": True,
        "tool": "scan_environment",
        "model": model,
        "user_id": user_id,
        "question": question,
        "summary": parsed["summary"],
        "objects": parsed["objects"],
        "suggested_reply": parsed["suggested_reply"],
        "actions": [
            {
                "name": "scan_environment",
                "target": "front_area",
                "status": "completed",
            }
        ],
        "duration_ms": duration_ms,
        "raw_model_text": raw_text,
    }
    record_trace(
        channel="grounding",
        kind="custom_tool",
        title="Vision tool scan_environment",
        message=parsed["summary"],
        payload=result,
    )
    return result
