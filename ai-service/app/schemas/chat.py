"""Wire schemas for POST /chat (DESIGN §6)."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    patient_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    booking_created: dict | None = None  # booking payload when a turn completes one
    session_id: str
