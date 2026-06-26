from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str | None = None
    message: str
    agent_web_tool_enabled: bool = False
    event_type: str | None = None
    conversation_id: str | None = None


class ContextLoadRequest(BaseModel):
    user_id: str = "anonymous"


class ContextSaveRequest(BaseModel):
    user_id: str = "anonymous"
    summary: str


class MemoryTurn(BaseModel):
    role: str = "user"
    text: str = ""


class ContextAutoSaveRequest(BaseModel):
    user_id: str = "anonymous"
    session_id: str | None = None
    conversation_id: str | None = None
    turns: list[MemoryTurn] = []


class ContextRecord(BaseModel):
    summary: str
    updated_at: str


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


class SearchRequest(BaseModel):
    query: str
    top: int = 5


class VoiceSessionRequest(BaseModel):
    conversation_id: str | None = None


class TtsRequest(BaseModel):
    text: str
    voice: str = "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"


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
    include_memory: bool = True
    include_search: bool = True
    top: int = 3


class KnowledgeIngestRequest(BaseModel):
    file_path: str = ""
    title: str | None = None
