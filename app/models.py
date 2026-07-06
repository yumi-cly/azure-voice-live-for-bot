from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str | None = None
    message: str
    agent_tools_enabled: bool = False
    event_type: str | None = None
    conversation_id: str | None = None


class ToolRequest(BaseModel):
    action: str | None = None
    target: str | None = None
    location: str | None = None
    brightness: int | None = None
    device: str | None = None
    topic: str | None = None


class MediaToolRequest(BaseModel):
    media_type: str = "Radio"
    volume: int = 70
    station: str | None = None
    state: str = "playing"


class NavigationToolRequest(BaseModel):
    destination: str = "inspection-zone-a"
    active: bool = True
    mode: str = "guided"


class VoiceSessionRequest(BaseModel):
    conversation_id: str | None = None


class VisionFrameRequest(BaseModel):
    image_base64: str
    question: str = "看看桌上有什么？"
    user_id: str = "demo-user"
    conversation_id: str | None = None


class VisionLatestFrameRequest(BaseModel):
    image_base64: str
    user_id: str = "demo-user"
    conversation_id: str | None = None


class AgentChatRequest(BaseModel):
    user_id: str = "demo-user"
    question: str
    conversation_id: str | None = None
