"""FastAPI app: POST /chat (graph runtime), POST /summarize (bonus), GET /health
(probes backend reachability — k8s readiness signal, DESIGN §9); lifespan
flushes Langfuse."""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.agent.observability.tracing import shutdown_tracing
from app.core.config import settings
from app.runtime import handle_chat
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.summarize import SummarizeRequest, SummarizeResponse
from app.summarizer import handle_summarize

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    shutdown_tracing()  # P6: flush pending spans at shutdown; no-op when off


app = FastAPI(title="ClinicPilot AI Service", version="0.1.0", lifespan=lifespan)


def probe_backend() -> bool:
    """Readiness signal: every tool the graph uses lives behind the backend (P3),
    so an unreachable backend means this instance cannot serve /chat usefully."""
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{settings.backend_url}/api/health")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


@app.get("/health")
def health():
    backend_up = probe_backend()
    body = {
        "status": "ok" if backend_up else "degraded",
        "backend": "up" if backend_up else "down",
    }
    if backend_up:
        return body
    return JSONResponse(status_code=503, content=body)


@app.get("/livez")
def livez():
    """Process liveness only: a backend outage must degrade readiness (/health)
    without restarting this pod — a restart would wipe the in-process
    conversation checkpointer mid-session."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return await handle_chat(req)


@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest) -> SummarizeResponse:
    return await handle_summarize(req)
