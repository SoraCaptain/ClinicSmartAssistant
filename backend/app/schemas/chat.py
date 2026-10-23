"""Wire schemas for the chat proxy (mirrors ai-service; services stay independent)
plus the session-history read models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    patient_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    booking_created: dict | None = None
    session_id: str


class ChatSessionOut(BaseModel):
    """GET /api/chat/sessions row (sidebar list)."""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(BaseModel):
    """GET /api/chat/sessions/{id}/messages row; `booking` is the replayed
    booking_created dict (confirmation card) parsed from storage."""

    id: int
    session_id: str
    role: str  # user | assistant
    content: str
    intent: str | None = None
    booking: dict | None = None
    created_at: datetime
