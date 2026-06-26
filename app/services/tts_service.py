from __future__ import annotations

from html import escape

import httpx

from app.config import get_settings
from app.exceptions import ConfigurationError
from app.services.azure_auth import get_azure_credential


SPEECH_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_TTS_VOICE = "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"


def _speech_region() -> str:
    settings = get_settings()
    if settings.foundry_region:
        return settings.foundry_region
    if "eus2" in settings.foundry_resource_name.lower():
        return "eastus2"
    if "eus" in settings.foundry_resource_name.lower():
        return "eastus"
    raise ConfigurationError("FOUNDRY_REGION is required for TTS fallback.")


async def synthesize_speech(text: str, voice: str = DEFAULT_TTS_VOICE) -> bytes:
    clean_text = text.strip()
    if not clean_text:
        raise ConfigurationError("TTS text cannot be empty.")

    settings = get_settings()
    region = _speech_region()
    endpoint = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    ssml = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='zh-CN'>"
        f"<voice name='{escape(voice, quote=True)}'>{escape(clean_text)}</voice>"
        "</speak>"
    )
    headers = {
        "Content-Type": "application/ssml+xml; charset=utf-8",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "azure-voice-live-for-bot",
    }
    if settings.foundry_resource_key:
        headers["Ocp-Apim-Subscription-Key"] = settings.foundry_resource_key
    else:
        token = get_azure_credential().get_token(SPEECH_SCOPE).token
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(endpoint, content=ssml.encode("utf-8"), headers=headers)
    if response.status_code >= 400:
        raise ConfigurationError(f"Azure TTS failed: HTTP {response.status_code} {response.text[:240]}")
    return response.content
