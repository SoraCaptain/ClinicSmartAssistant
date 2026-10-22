"""FastAPI app: POST /chat (graph runtime), GET /health."""

import logging

from fastapi import FastAPI

from app.runtime import handle_chat
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="ClinicPilot AI Service", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return await handle_chat(req)
