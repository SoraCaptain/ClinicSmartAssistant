"""Intent classification node (P1: every turn re-classified against full history)."""

from typing import Literal

from pydantic import BaseModel

from app.agent.llm import get_chat_model
from app.agent.prompts import (
    CLASSIFIER_SYSTEM,
    CLASSIFIER_USER,
    render_booking_draft,
    render_history,
)
from app.agent.state import ClinicGraphState

INTENTS = ("qa", "check_bookings", "book_appointment", "general")


class ClassifierOutput(BaseModel):
    intent: Literal[INTENTS]
    # set only while a booking summary awaits confirmation (prompt rules above)
    user_confirms: bool | None = None


def get_classifier_chain():
    """Built per call so tests can patch this symbol at this module.
    method="function_calling": json_schema response_format (the langchain default)
    is unsupported by several OpenAI-compatible providers (e.g. DeepSeek)."""
    return get_chat_model().with_structured_output(ClassifierOutput, method="function_calling")


def classify_intent(state: ClinicGraphState) -> dict:
    prompt = (
        f"{CLASSIFIER_SYSTEM}\n\n"
        + CLASSIFIER_USER.format(
            history=render_history(state.get("messages", [])),
            draft=render_booking_draft(state.get("booking_draft")),
            message=state["user_message"],
        )
    )
    result = get_classifier_chain().invoke(prompt)
    return {"intent": result.intent, "user_confirms": result.user_confirms}
