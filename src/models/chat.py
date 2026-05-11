from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "tool"
    content: str
    created_at: datetime | None = None


class ChatRequest(BaseModel):
    message: str
    telegram_id: int | None = None
    web_session_id: str | None = None
    channel: str = "web"  # "telegram" | "web"


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID
    stage: str
    lead_id: UUID | None = None
