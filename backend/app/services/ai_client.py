"""HTTP client for the AI engine (DESIGN §2: backend is the BFF; ai owns LLM work).

Raises httpx.RequestError when ai-service is unreachable (router maps to 503, P7)
and httpx.HTTPStatusError on non-2xx (router maps to 502).
"""

import httpx

from app.core.config import settings


async def chat(payload: dict) -> dict:
    """POST /chat on ai-service; returns the parsed JSON body."""
    async with httpx.AsyncClient(timeout=settings.ai_service_timeout) as client:
        resp = await client.post(f"{settings.ai_service_url}/chat", json=payload)
        resp.raise_for_status()
        return resp.json()


async def summarize(payload: dict) -> dict:
    """POST /summarize on ai-service; returns the parsed JSON body."""
    async with httpx.AsyncClient(timeout=settings.ai_service_timeout) as client:
        resp = await client.post(f"{settings.ai_service_url}/summarize", json=payload)
        resp.raise_for_status()
        return resp.json()
