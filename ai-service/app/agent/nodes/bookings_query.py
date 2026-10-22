"""Bookings lookup node: reads the patient's bookings via the REST tool (P3) and
composes the answer from the rendered rows only (booking IDs citable, e.g. B1004).
An empty list answers deterministically; tool failures surface as readable text."""

from datetime import date

from app.agent.llm import get_chat_model
from app.agent.prompts import (
    BOOKINGS_SYSTEM,
    BOOKINGS_USER,
    render_bookings,
    render_history,
)
from app.agent.state import ClinicGraphState
from app.agent.tools.booking_tools import get_my_bookings


def get_bookings_chain():
    """Built per call so tests can patch this symbol at this module."""
    return get_chat_model()


def bookings_answer(state: ClinicGraphState) -> dict:
    try:
        bookings = get_my_bookings(patient_id=state["patient_id"])
    except RuntimeError as e:
        return {"reply": f"I couldn't read your bookings: {e} Please try again in a moment."}
    if not bookings:
        return {"reply": "You have no bookings yet. Would you like to book an appointment?"}
    prompt = (
        f"{BOOKINGS_SYSTEM}\n\n"
        + BOOKINGS_USER.format(
            history=render_history(state.get("messages", [])),
            bookings=render_bookings(bookings, today=date.today().isoformat()),
            message=state["user_message"],
        )
    )
    return {"reply": get_bookings_chain().invoke(prompt).content}
