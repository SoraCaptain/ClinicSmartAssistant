"""POST /api/chat — proxy to the AI engine (P7: ai-service unreachable → 503)."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, ChatResponse
from app.services import ai_client

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        data = await ai_client.chat(payload.model_dump())
        return ChatResponse(**data)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}") from exc
    except (httpx.HTTPStatusError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"AI service returned an error: {exc}") from exc
