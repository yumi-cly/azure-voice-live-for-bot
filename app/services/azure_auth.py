from __future__ import annotations

import os
from functools import lru_cache

from azure.identity import (
    AzureCliCredential,
    AzureDeveloperCliCredential,
    AzurePowerShellCredential,
    ChainedTokenCredential,
    EnvironmentCredential,
    InteractiveBrowserCredential,
    ManagedIdentityCredential,
    TokenCachePersistenceOptions,
)

from app.config import get_settings


def _persistent_cache() -> TokenCachePersistenceOptions:
    return TokenCachePersistenceOptions(name="azure-voice-live-for-bot")


def _interactive_browser_credential() -> InteractiveBrowserCredential:
    settings = get_settings()
    kwargs: dict[str, object] = {
        "cache_persistence_options": _persistent_cache(),
        "timeout": 120,
    }
    if settings.azure_tenant_id:
        kwargs["tenant_id"] = settings.azure_tenant_id
    return InteractiveBrowserCredential(**kwargs)


def _ensure_azure_cli_on_path() -> None:
    cli_dir = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin"
    if os.name != "nt" or not os.path.exists(os.path.join(cli_dir, "az.cmd")):
        return
    path_items = os.environ.get("PATH", "").split(os.pathsep)
    if cli_dir not in path_items:
        os.environ["PATH"] = os.pathsep.join([cli_dir, *path_items])


@lru_cache
def get_azure_credential() -> ChainedTokenCredential:
    settings = get_settings()
    _ensure_azure_cli_on_path()
    managed_identity_kwargs: dict[str, str] = {}
    credentials: list[object] = []
    developer_credentials = [
        AzureCliCredential(process_timeout=15),
        AzurePowerShellCredential(process_timeout=15),
        AzureDeveloperCliCredential(process_timeout=15),
        _interactive_browser_credential(),
    ]

    has_service_principal = all(
        os.getenv(key)
        for key in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID")
    ) and any(
        os.getenv(key)
        for key in ("AZURE_CLIENT_SECRET", "AZURE_CLIENT_CERTIFICATE_PATH", "AZURE_FEDERATED_TOKEN_FILE")
    )

    if has_service_principal:
        credentials.append(EnvironmentCredential())

    if settings.azure_client_id:
        managed_identity_kwargs["client_id"] = settings.azure_client_id

    managed_identity = ManagedIdentityCredential(**managed_identity_kwargs)
    running_with_managed_identity = any(
        os.getenv(key)
        for key in ("IDENTITY_ENDPOINT", "IDENTITY_HEADER", "MSI_ENDPOINT", "MSI_SECRET", "IMDS_ENDPOINT")
    )

    if running_with_managed_identity:
        credentials.append(managed_identity)
        credentials.extend(developer_credentials)
    else:
        credentials.extend(developer_credentials)
        credentials.append(managed_identity)

    return ChainedTokenCredential(*credentials)


def get_foundry_credential() -> ChainedTokenCredential:
    return get_azure_credential()


def get_blob_credential() -> tuple[object, str]:
    settings = get_settings()
    if settings.azure_storage_account_key:
        return settings.azure_storage_account_key, "account_key"
    return get_azure_credential(), "entra"
