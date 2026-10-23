"""Durable chat history (multi-session chat). Backend owns the transcript tables;
ai-service keeps owning agent memory (thread checkpointer). Failed turns are never
recorded — a session row appears only after its first successful turn."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession

DEFAULT_PATIENT_ID = "P001"
TITLE_MAX = 60

logger = logging.getLogger(__name__)


def record_turn(
    db: Session, *, session_id: str, patient_id: str | None, user_message: str, response
) -> ChatSession:
    """Persist one successful turn: get-or-create the session (title = first user
    message), then append the user text and the assistant reply. `response` is the
    validated ChatResponse from ai-service."""
    session = db.get(ChatSession, session_id)
    if session is None:
        session = ChatSession(
            session_id=session_id,
            patient_id=patient_id or DEFAULT_PATIENT_ID,
            title=user_message.strip()[:TITLE_MAX] or "(empty message)",
        )
        db.add(session)
        db.flush()  # chat_messages FK needs the parent row visible
    else:
        # explicit bump: message INSERTs alone never touch the session row
        session.updated_at = datetime.now(timezone.utc)

    db.add_all(
        [
            ChatMessage(session_id=session_id, role="user", content=user_message),
            ChatMessage(
                session_id=session_id,
                role="assistant",
                content=response.reply,
                intent=response.intent,
                booking_json=(
                    json.dumps(response.booking_created) if response.booking_created else None
                ),
            ),
        ]
    )
    db.commit()
    return session


def list_sessions(db: Session) -> list[ChatSession]:
    """All chat sessions, most recently active first (deterministic tiebreak)."""
    return list(
        db.scalars(
            select(ChatSession).order_by(
                ChatSession.updated_at.desc(), ChatSession.created_at.desc(), ChatSession.session_id
            )
        )
    )


def get_messages(db: Session, session_id: str) -> list[ChatMessage] | None:
    """Full transcript in order; None when the session id is unknown."""
    if db.get(ChatSession, session_id) is None:
        return None
    return list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        )
    )
