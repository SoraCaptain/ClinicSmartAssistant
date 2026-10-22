"""POST /api/summarize/transcript — bonus proxy to the AI engine (P7 pattern:
ai-service unreachable → 503; upstream error → 502)."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas.summarize import SummarizeRequest, SummarizeResponse
from app.services import ai_client

router = APIRouter(prefix="/api/summarize", tags=["summarize"])


@router.post("/transcript", response_model=SummarizeResponse)
async def summarize_transcript(payload: SummarizeRequest) -> SummarizeResponse:
    try:
        data = await ai_client.summarize(payload.model_dump())
        return SummarizeResponse(**data)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}") from exc
    except (httpx.HTTPStatusError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"AI service returned an error: {exc}") from exc
