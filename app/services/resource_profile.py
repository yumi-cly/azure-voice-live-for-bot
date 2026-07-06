from app.config import get_settings


def get_resource_profile() -> dict:
    settings = get_settings()
    return {
        "resources": {
            "resourceGroup": settings.azure_resource_group,
            "azureClientId": settings.azure_client_id,
            "foundryResourceName": settings.foundry_resource_name,
            "storageAccountName": settings.azure_storage_account_name,
            "storageContainerName": settings.azure_storage_container_name,
            "foundryIqSearchEndpoint": settings.resolved_foundry_iq_search_endpoint,
            "foundryIqKnowledgeBase": settings.foundry_iq_knowledge_base,
            "containerAppsEnvironmentName": settings.azure_container_apps_environment_name,
            "keyVaultName": settings.azure_key_vault_name,
            "foundryProjectName": settings.foundry_project_name,
            "foundryAgentName": settings.resolved_foundry_agent_name,
            "foundryAgentVersion": settings.resolved_voice_agent_version,
            "foundryModelName": settings.foundry_model_name,
            "voiceLiveAsrModel": settings.voice_live_asr_model,
            "voiceLiveAgentModel": settings.voice_live_agent_model,
            "voiceLiveTtsVoice": settings.voice_live_tts_voice,
            "foundryVisionDeployment": settings.foundry_vision_deployment,
            "mcpServerUrl": settings.mcp_server_url,
        },
        "serviceStatus": {
            "foundryIqConfigured": bool(
                settings.foundry_iq_knowledge_base
            ),
            "blobUploadConfigured": bool(
                settings.resolved_blob_service_url and settings.azure_storage_container_name
            ),
            "foundryConfigured": bool(settings.foundry_project_endpoint),
            "foundryAgentConfigured": bool(settings.resolved_voice_agent_name),
            "visionConfigured": bool(
                settings.foundry_project_endpoint
                and (settings.foundry_vision_deployment or settings.foundry_model_name)
            ),
            "voiceLiveConfigured": bool(settings.voice_live_endpoint),
            "mcpServerConfigured": bool(settings.mcp_server_url),
        },
        "features": {
            "agentToolsEnabled": bool(settings.resolved_voice_agent_name),
            "browserSeesSecrets": False,
            "voiceAuthMode": "entra-managed-identity",
            "toolTransport": "mcp",
            "asrOptions": ["azure-speech", "mai-transcribe-1"],
            "agentModelOptions": ["gpt-5.4"],
            "ttsVoiceOptions": [
                "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
                "zh-CN-XiaoxiaoNeural",
                "zh-CN-XiaoyiNeural",
                "zh-CN-YunxiNeural",
                "zh-CN-YunyangNeural",
                "en-US-Ava:DragonHDLatestNeural",
            ],
        },
    }
