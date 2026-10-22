"""Wire schemas for the summarize proxy (mirrors ai-service; services stay independent)."""

from pydantic import BaseModel, Field


class SummarizeRequest(BaseModel):
    transcript: str = Field(min_length=1)


class SummarizeResponse(BaseModel):
    chief_complaint: str
    diagnosis: str
    medication: str
    doctor_instructions: str
