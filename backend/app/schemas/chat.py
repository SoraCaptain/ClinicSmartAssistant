"""Wire schemas for the chat proxy (mirrors ai-service; services stay independent)."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    patient_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    booking_created: dict | None = None
    session_id: str
