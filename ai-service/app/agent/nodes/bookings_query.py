"""Bookings lookup node: reads the patient's bookings via the REST tool (P3) and
composes the answer from the rendered rows only (booking IDs citable, e.g. B1004).
An empty list answers deterministically; so do cancel/reschedule requests — the
write scope is view+create only, so they get a fixed refusal citing the clinics'
phone numbers and cancellation policies. Tool failures surface as readable text."""

import re
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
from app.agent.tools.catalog_tools import get_clinics

# Stem 'reschedul' covers reschedule/rescheduling/rescheduled; requests to modify a
# booking get the deterministic refusal below — the write path is view+create only.
_CANCEL_RE = re.compile(r"\b(?:cancel|reschedul)", re.IGNORECASE)


def _render_cancel_refusal(bookings: list[dict], clinics: dict[str, dict]) -> str:
    """Deterministic refusal (cancellation/rescheduling is outside the write scope):
    the clinics of the patient's own bookings, dedup by clinic_id in row order, each
    with phone and cancellation policy verbatim from the catalog."""
    lines = [
        "I'm sorry — I can't cancel or reschedule bookings from this chat. I can view "
        "your bookings and make new ones, but changes must be made with the clinic directly:"
    ]
    seen: set[str] = set()
    for booking in bookings:
        clinic = clinics.get(booking["clinic_id"])
        if clinic is None or clinic["clinic_id"] in seen:
            continue
        seen.add(clinic["clinic_id"])
        lines.append(f"- {clinic['clinic_name']} ({clinic['phone']}): {clinic['cancellation_policy']}")
    return "\n".join(lines)


def get_bookings_chain():
    """Built per call so tests can patch this symbol at this module."""
    return get_chat_model()


def bookings_answer(state: ClinicGraphState) -> dict:
    cancel_request = _CANCEL_RE.search(state["user_message"]) is not None
    try:
        bookings = get_my_bookings(patient_id=state["patient_id"])
        # only the refusal cites clinic phone + cancellation policy; other turns skip the read
        clinics = {c["clinic_id"]: c for c in get_clinics()} if cancel_request else {}
    except RuntimeError as e:
        return {"reply": f"I couldn't read your bookings or clinic details: {e} Please try again in a moment."}
    if not bookings:
        return {"reply": "You have no bookings yet. Would you like to book an appointment?"}
    if cancel_request:
        return {"reply": _render_cancel_refusal(bookings, clinics)}
    prompt = (
        f"{BOOKINGS_SYSTEM}\n\n"
        + BOOKINGS_USER.format(
            history=render_history(state.get("messages", [])),
            bookings=render_bookings(bookings, today=date.today().isoformat()),
            message=state["user_message"],
        )
    )
    return {"reply": get_bookings_chain().invoke(prompt).content}
