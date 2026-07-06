from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import BASE_DIR, get_settings
from app.services.azure_auth import get_foundry_credential


INSTRUCTIONS = "\n".join(
    [
        "\u4f60\u662f\u4e00\u4e2a\u9762\u5411\u5177\u8eab\u673a\u5668\u4eba\u6f14\u793a\u573a\u666f\u7684\u4e2d\u6587\u8bed\u97f3\u52a9\u624b\u3002",
        "\u573a\u666f\uff1a\u5bb6\u5ead\u966a\u4f34\u3001\u521b\u5ba2\u6559\u80b2\u3001\u7f16\u7a0b\u5b66\u4e60\u3001\u4ea7\u54c1\u6f14\u793a\u3002",
        "\u8bf7\u7528\u81ea\u7136\u3001\u7b80\u6d01\u3001\u4e13\u4e1a\u7684\u4e2d\u6587\u56de\u7b54\uff0c\u56de\u7b54\u8981\u9002\u5408\u8bed\u97f3\u64ad\u62a5\u3002",
        "\u5982\u679c\u4fe1\u606f\u4e0d\u8db3\uff0c\u8bf7\u660e\u786e\u8bf4\u660e\u7f3a\u53e3\uff0c\u4e0d\u8981\u7f16\u9020\u3002",
        "",
        "\u5de5\u5177\u8c03\u7528\u89c4\u5219\uff1a",
        "- \u5f53\u7528\u6237\u8be2\u95ee\u516c\u53f8\u5236\u5ea6\u3001\u4e0a\u4f20\u6587\u6863\u3001\u5185\u90e8\u8d44\u6599\u3001\u77e5\u8bc6\u5e93\u6216\u6570\u636e\u5e93\u5185\u5bb9\u65f6\uff0c\u4f18\u5148\u4f7f\u7528 Foundry Agent \u5df2\u914d\u7f6e\u7684 Knowledge / Foundry IQ \u77e5\u8bc6\u5e93\u8fdb\u884c\u56de\u7b54\u3002",
        "- \u4f7f\u7528 Foundry IQ \u7ed3\u679c\u56de\u7b54\u65f6\uff0c\u4f18\u5148\u4fdd\u7559\u6765\u6e90\u4fe1\u606f\uff1b\u5982\u679c\u77e5\u8bc6\u5e93\u6ca1\u6709\u627e\u5230\u4f9d\u636e\uff0c\u8bf7\u660e\u786e\u8bf4\u6ca1\u6709\u627e\u5230\u5185\u90e8\u8d44\u6599\u4f9d\u636e\u3002",
        "- \u53ea\u6709\u5f53\u7528\u6237\u660e\u786e\u8981\u6c42\u67e5\u770b\u5b9e\u65f6\u6444\u50cf\u5934\u3001\u955c\u5934\u753b\u9762\u3001\u773c\u524d/\u524d\u65b9\u73af\u5883\u3001\u684c\u4e0a\u5b9e\u7269\u6216\u673a\u5668\u4eba\u5f53\u524d\u770b\u5230\u7684\u7269\u4f53\u65f6\uff0c\u624d\u8c03\u7528 scan_environment\u3002\u4e0d\u8981\u56e0\u4e3a\u201c\u770b\u4e00\u4e0b\u5236\u5ea6/\u8d44\u6599/\u6587\u4ef6/\u9875\u9762/\u5185\u5bb9/\u8fd9\u4e2a\u95ee\u9898\u201d\u7b49\u6cdb\u5316\u8868\u8fbe\u8c03\u7528\u6444\u50cf\u5934\u3002",
        "- \u5982\u679c scan_environment \u8fd4\u56de\u6ca1\u6709\u6700\u65b0\u753b\u9762\uff0c\u518d\u63d0\u9192\u7528\u6237\u5148\u6253\u5f00\u6444\u50cf\u5934\u3002",
        "- \u4f1a\u8bdd\u5f00\u59cb\u7684\u9996\u6b21\u95ee\u5019\u3001\u7528\u6237\u95ee\u597d\u3001\u7528\u6237\u8981\u6c42\u6253\u62db\u547c\u6216\u6325\u624b\u65f6\uff0c\u8c03\u7528 run_robot_action\uff0c\u4f7f\u7528 action=wave\u3002",
        "- \u5f53\u7528\u6237\u8981\u6c42\u5f00\u706f\u3001\u5173\u706f\u6216\u8c03\u8282\u4eae\u5ea6\u65f6\uff0c\u8c03\u7528 run_robot_action\u3002",
        "- \u52a8\u4f5c\u6267\u884c\u540e\u4e0d\u8981\u628a\u52a8\u4f5c\u8fc7\u7a0b\u8bf4\u51fa\u6765\uff0c\u4f8b\u5982\u4e0d\u8981\u8bf4\u201c\u6211\u5411\u4f60\u6325\u624b\u4e86\u201d\u3002\u53ea\u9700\u81ea\u7136\u56de\u590d\u7528\u6237\uff0c\u52a8\u4f5c\u72b6\u6001\u4f1a\u7531\u754c\u9762\u5c55\u793a\u3002",
        "- \u5f53\u7528\u6237\u8be2\u95ee\u5b9e\u65f6\u3001\u6700\u65b0\u6216\u516c\u5f00\u7f51\u7edc\u4fe1\u606f\u65f6\uff0c\u53ef\u4ee5\u4f7f\u7528 web_search \u5de5\u5177\u3002",
    ]
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _replace_env_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text)
    suffix = "" if text.endswith("\n") else "\n"
    return f"{text}{suffix}{line}\n"


def _update_env(*, mcp_server_url: str, agent_name: str, agent_version: str) -> None:
    env_path = BASE_DIR / ".env"
    text = env_path.read_text(encoding="utf-8")
    text = _replace_env_value(text, "MCP_SERVER_URL", mcp_server_url)
    text = _replace_env_value(text, "FOUNDRY_AGENT_NAME", agent_name)
    text = _replace_env_value(text, "FOUNDRY_AGENT_VERSION", agent_version)
    env_path.write_text(text, encoding="utf-8")


def _normalize_agent_version(version: str) -> str:
    value = version.strip()
    if len(value) > 1 and value[0].lower() == "v" and value[1:].isdigit():
        return value[1:]
    return value


def _version_sort_key(version: dict[str, Any]) -> tuple[int, int, str]:
    created_at = version.get("created_at") or 0
    raw_version = str(version.get("version") or "")
    numeric_version = int(raw_version) if raw_version.isdigit() else 0
    return (int(created_at), numeric_version, raw_version)


def _latest_active_agent_version(project_client: AIProjectClient, agent_name: str) -> str:
    versions = []
    for item in project_client.agents.list_versions(agent_name):
        data = _as_dict(item)
        if str(data.get("status") or "").lower() == "active":
            versions.append(data)

    if not versions:
        raise SystemExit(f"No active versions found for Foundry Agent '{agent_name}'. Publish the agent in Foundry first.")

    latest = sorted(versions, key=_version_sort_key, reverse=True)[0]
    version = str(latest.get("version") or "")
    if not version:
        raise SystemExit(f"Latest active version for Foundry Agent '{agent_name}' did not include a version value.")
    return version


def _tool_text(tool: dict[str, Any], key: str) -> str:
    return str(tool.get(key) or "")


def _is_robot_demo_tool(tool: dict[str, Any]) -> bool:
    if _tool_text(tool, "type") != "mcp":
        return False
    return _tool_text(tool, "server_label") == "robot_demo"


def _is_foundry_iq_mcp_tool(tool: dict[str, Any]) -> bool:
    if _tool_text(tool, "type") != "mcp":
        return False
    server_label = _tool_text(tool, "server_label")
    if server_label.startswith("kb-"):
        return False
    allowed_tools = tool.get("allowed_tools") or []
    server_url = _tool_text(tool, "server_url")
    return (
        server_label in {"knowledge-base", "foundry-iq-kb"}
        or _tool_text(tool, "project_connection_id") == "foundry-iq-kb"
    )


def _merge_tools(existing_tools: list[dict[str, Any]], mcp_url: str) -> list[dict[str, Any]]:
    tools = [
        tool
        for tool in existing_tools
        if not _is_robot_demo_tool(tool) and not _is_foundry_iq_mcp_tool(tool)
    ]
    if not any(_tool_text(tool, "type") == "web_search" for tool in tools):
        tools.append({"type": "web_search", "search_context_size": "medium"})
    tools.append(
        {
            "type": "mcp",
            "server_label": "robot_demo",
            "server_url": mcp_url,
            "server_description": "Robot demo MCP server for camera vision and simulated actions.",
            "allowed_tools": [
                "scan_environment",
                "run_robot_action",
            ],
            "require_approval": "never",
        }
    )
    return tools


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Foundry Agent version that uses MCP tools.")
    parser.add_argument("--mcp-url", required=True, help="Public HTTPS MCP endpoint, for example https://your-container-app.azurecontainerapps.io/mcp")
    parser.add_argument("--agent-name", default="", help="Foundry agent name. Defaults to FOUNDRY_AGENT_NAME.")
    parser.add_argument("--base-version", default="", help="Optional existing version to copy metadata/RAI config from. Defaults to the latest active Foundry Agent version.")
    parser.add_argument("--model", default="", help="Agent model deployment name. Defaults to FOUNDRY_MODEL_NAME.")
    parser.add_argument("--update-env", action="store_true", help="Write MCP_SERVER_URL and new version back to .env.")
    args = parser.parse_args()

    settings = get_settings()
    agent_name = args.agent_name or settings.resolved_voice_agent_name
    requested_base_version = _normalize_agent_version(args.base_version)
    model_deployment = args.model or settings.foundry_model_name
    if not settings.foundry_project_endpoint:
        raise SystemExit("FOUNDRY_PROJECT_ENDPOINT is required.")
    if not agent_name:
        raise SystemExit("FOUNDRY_AGENT_NAME is required.")
    if not model_deployment:
        raise SystemExit("FOUNDRY_MODEL_NAME or --model is required. Use the actual Foundry model deployment name.")

    mcp_url = args.mcp_url.rstrip("/")
    if not mcp_url.startswith("https://"):
        raise SystemExit("MCP URL must be public HTTPS for Foundry Agent Service.")

    credential = get_foundry_credential()
    project_client = AIProjectClient(
        endpoint=settings.foundry_project_endpoint,
        credential=credential,
        allow_preview=True,
    )
    try:
        base_version = requested_base_version or _latest_active_agent_version(project_client, agent_name)
        base = project_client.agents.get_version(agent_name, base_version)
        base_dict = _as_dict(base)
        definition = _as_dict(base.definition)

        definition["kind"] = definition.get("kind") or "prompt"
        definition["model"] = model_deployment
        definition["instructions"] = INSTRUCTIONS
        definition["tools"] = _merge_tools(list(definition.get("tools") or []), mcp_url)

        metadata = dict(base_dict.get("metadata") or {})
        metadata["tool_transport"] = "mcp"
        metadata["mcp_server_url"] = mcp_url[:512]
        metadata["demo_scope"] = "voice-camera-action"

        created = project_client.agents.create_version(
            agent_name,
            definition=definition,
            metadata=metadata,
            description=f"Voice Live demo agent using {model_deployment}, web_search, Agent Knowledge, camera vision, and robot actions.",
        )
        created_dict = _as_dict(created)
        version = str(created_dict.get("version") or created.version)

        if args.update_env:
            _update_env(mcp_server_url=mcp_url, agent_name=agent_name, agent_version=version)

        print(
            json.dumps(
                {
                    "ok": True,
                    "agent_name": agent_name,
                    "base_agent_version": base_version,
                    "agent_version": version,
                    "model": model_deployment,
                    "mcp_server_url": mcp_url,
                    "env_updated": bool(args.update_env),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        project_client.close()


if __name__ == "__main__":
    main()
