"""FastAPI app: POST /chat (graph runtime), GET /health; lifespan flushes Langfuse."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.observability.tracing import shutdown_tracing
from app.runtime import handle_chat
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    shutdown_tracing()  # P6: flush pending spans at shutdown; no-op when off


app = FastAPI(title="ClinicPilot AI Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return await handle_chat(req)
