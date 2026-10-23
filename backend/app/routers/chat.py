"""Chat routes: POST /api/chat (proxy to the AI engine, P7: ai-service
unreachable → 503) plus the durable session history reads (multi-session chat)."""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.chat import ChatMessageOut, ChatRequest, ChatResponse, ChatSessionOut
from app.services import chat_history_service, ai_client

router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        data = await ai_client.chat(payload.model_dump())
        response = ChatResponse(**data)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}") from exc
    except (httpx.HTTPStatusError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"AI service returned an error: {exc}") from exc
    # Persist only after a successful upstream turn; a failure here must not
    # fail the turn (a retry would double-book) — degrade to a logged gap.
    try:
        chat_history_service.record_turn(
            db,
            session_id=payload.session_id,
            patient_id=payload.patient_id,
            user_message=payload.message,
            response=response,
        )
    except Exception:
        logger.exception("chat history persistence failed for session %s", payload.session_id)
        db.rollback()
    return response


@router.get("/chat/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db)) -> list[ChatSessionOut]:
    return [ChatSessionOut.model_validate(s) for s in chat_history_service.list_sessions(db)]


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(session_id: str, db: Session = Depends(get_db)) -> list[ChatMessageOut]:
    rows = chat_history_service.get_messages(db, session_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return [
        ChatMessageOut(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            booking=json.loads(m.booking_json) if m.booking_json else None,
            created_at=m.created_at,
        )
        for m in rows
    ]
