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
            "storageAuthMode": "account_key" if settings.azure_storage_account_key else "entra",
            "foundryIqSearchEndpoint": settings.resolved_foundry_iq_search_endpoint,
            "foundryIqKnowledgeBase": settings.foundry_iq_knowledge_base,
            "foundryIqConnectionName": settings.foundry_iq_connection_name,
            "containerAppsEnvironmentName": settings.azure_container_apps_environment_name,
            "keyVaultName": settings.azure_key_vault_name,
            "foundryProjectName": settings.foundry_project_name,
            "foundryAgentName": settings.resolved_foundry_agent_name,
            "foundryWebAgentName": settings.resolved_foundry_web_agent_name,
            "foundryVoiceAgentName": settings.resolved_voice_agent_name,
            "foundryVoiceAgentVersion": settings.resolved_voice_agent_version,
            "foundryModelName": settings.foundry_model_name,
            "foundryVisionDeployment": settings.foundry_vision_deployment,
            "mcpServerUrl": settings.mcp_server_url,
        },
        "serviceStatus": {
            "foundryIqConfigured": bool(
                settings.resolved_foundry_iq_search_endpoint
                and settings.foundry_iq_knowledge_base
            ),
            "blobUploadConfigured": bool(
                settings.resolved_blob_service_url and settings.azure_storage_container_name
            ),
            "foundryConfigured": bool(settings.foundry_project_endpoint),
            "foundryAgentConfigured": bool(settings.resolved_voice_agent_name),
            "foundryWebAgentConfigured": bool(settings.resolved_foundry_web_agent_name),
            "agentWebToolConfigured": bool(settings.resolved_foundry_web_agent_name),
            "visionConfigured": bool(settings.foundry_project_endpoint and settings.foundry_api_key),
            "voiceLiveConfigured": bool(settings.voice_live_endpoint),
            "mcpServerConfigured": bool(settings.mcp_server_url),
        },
        "features": {
            "agentWebToolEnabled": bool(settings.resolved_foundry_web_agent_name),
            "browserSeesSecrets": False,
            "voiceAuthMode": "entra-managed-identity",
            "toolTransport": "mcp",
        },
    }
