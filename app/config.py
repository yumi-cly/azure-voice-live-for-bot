from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    azure_resource_group: str = Field(default="")
    azure_client_id: str = Field(default="")
    foundry_resource_name: str = Field(default="")
    foundry_region: str = Field(default="")
    foundry_resource_key: str = Field(default="")
    azure_storage_account_name: str = Field(default="")
    azure_storage_account_key: str = Field(default="")
    azure_storage_blob_service_url: str = Field(default="")
    azure_storage_container_name: str = Field(default="kb-docs")
    azure_ai_search_service_name: str = Field(default="")
    azure_cosmos_account_name: str = Field(default="")
    azure_container_apps_environment_name: str = Field(default="")
    azure_key_vault_name: str = Field(default="")
    azure_tenant_id: str = Field(default="")

    voice_live_endpoint: str = Field(default="")
    voice_live_api_key: str = Field(default="")
    voice_live_api_version: str = Field(default="2026-04-10")

    foundry_project_endpoint: str = Field(default="")
    foundry_api_key: str = Field(default="")
    foundry_project_name: str = Field(default="")
    foundry_agent_name: str = Field(default="")
    foundry_agent_id: str = Field(default="")
    foundry_agent_version: str = Field(default="")
    foundry_web_agent_name: str = Field(default="")
    foundry_web_agent_id: str = Field(default="")
    foundry_web_agent_version: str = Field(default="")
    foundry_model_name: str = Field(default="")
    foundry_vision_deployment: str = Field(default="gpt-5.4")
    foundry_project_resource_id: str = Field(default="")
    foundry_iq_search_endpoint: str = Field(default="")
    foundry_iq_knowledge_base: str = Field(default="")
    foundry_iq_connection_name: str = Field(default="foundry-iq-kb")
    mcp_server_url: str = Field(default="")

    azure_ai_search_endpoint: str = Field(default="")
    azure_ai_search_index: str = Field(default="bot-knowledge-index")
    azure_ai_search_semantic_config: str = Field(default="kb-semantic-config")
    azure_ai_search_api_key: str = Field(default="")

    cosmos_db_endpoint: str = Field(default="")
    cosmos_db_database: str = Field(default="voicebot")
    cosmos_db_container: str = Field(default="memory")
    cosmos_db_key: str = Field(default="")

    default_knowledge_file: str = Field(default="")
    web_allowed_origins: str = Field(default="http://127.0.0.1:8000")

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.web_allowed_origins.split(",") if item.strip()]

    @property
    def resolved_search_endpoint(self) -> str:
        if self.azure_ai_search_endpoint:
            return self.azure_ai_search_endpoint.rstrip("/")
        if self.azure_ai_search_service_name:
            return f"https://{self.azure_ai_search_service_name}.search.windows.net"
        return ""

    @property
    def resolved_foundry_iq_search_endpoint(self) -> str:
        if self.foundry_iq_search_endpoint:
            return self.foundry_iq_search_endpoint.rstrip("/")
        return self.resolved_search_endpoint

    @property
    def resolved_cosmos_endpoint(self) -> str:
        if self.cosmos_db_endpoint:
            return self.cosmos_db_endpoint.rstrip("/")
        if self.azure_cosmos_account_name:
            return f"https://{self.azure_cosmos_account_name}.documents.azure.com:443/"
        return ""

    @property
    def resolved_blob_service_url(self) -> str:
        if self.azure_storage_blob_service_url:
            return self.azure_storage_blob_service_url.rstrip("/")
        if self.azure_storage_account_name:
            return f"https://{self.azure_storage_account_name}.blob.core.windows.net"
        return ""

    @property
    def resolved_foundry_agent_name(self) -> str:
        return self.foundry_agent_name or self.foundry_agent_id

    @property
    def resolved_foundry_web_agent_name(self) -> str:
        return self.foundry_web_agent_name or self.foundry_web_agent_id

    @property
    def resolved_voice_agent_name(self) -> str:
        return self.resolved_foundry_web_agent_name or self.resolved_foundry_agent_name

    @property
    def resolved_voice_agent_version(self) -> str:
        return self.foundry_web_agent_version or self.foundry_agent_version


@lru_cache
def get_settings() -> Settings:
    return Settings()
