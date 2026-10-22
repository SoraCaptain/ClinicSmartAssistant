"""Booking flow nodes (DESIGN §5.2): extract_slots resolves the latest message into
draft slots (all catalog/booking data via REST tools, P3), ask_missing renders the
next question, confirm_summary renders doctor+treatment+date+time+fee behind
awaiting_confirmation, execute_booking fires create_booking only past the explicit
confirmation gate (P2 — the gate itself lives in graph routing)."""

import re
from datetime import date

from pydantic import BaseModel, Field

from app.agent.llm import get_chat_model
from app.agent.prompts import (
    SLOT_EXTRACTION_SYSTEM,
    SLOT_EXTRACTION_USER,
    render_booking_draft,
)
from app.agent.state import ClinicGraphState
from app.agent.tools.booking_tools import create_booking
from app.agent.tools.catalog_tools import search_doctors, search_treatments

# Ask order: the first missing slot drives ask_missing and graph routing
REQUIRED_SLOTS = ("treatment", "doctor", "date", "time")
_SLOT_KEYS = {"treatment": "treatment_id", "doctor": "doctor_id", "date": "booking_date", "time": "booking_time"}


class ExtractedSlots(BaseModel):
    """Raw entities from ONE user message; date/time ISO-normalized by the LLM."""

    doctor: str | None = Field(default=None, description="Doctor name as mentioned, e.g. 'Dr. Wilson'")
    treatment: str | None = Field(default=None, description="Treatment as mentioned, e.g. 'joint pain consultation'")
    booking_date: str | None = Field(default=None, description="YYYY-MM-DD, relative words resolved against today")
    booking_time: str | None = Field(default=None, description="HH:MM 24-hour clock, e.g. '9:30am' -> 09:30")


def get_slot_extractor():
    """Built per call so tests can patch this symbol at this module.
    method='function_calling': json_schema response_format is unsupported by several
    OpenAI-compatible providers (e.g. DeepSeek)."""
    return get_chat_model().with_structured_output(ExtractedSlots, method="function_calling")


def missing_slots(draft: dict) -> list[str]:
    """REQUIRED_SLOTS order, keeping only slots without a resolved value
    (an unresolved raw mention counts as missing)."""
    return [slot for slot in REQUIRED_SLOTS if not draft.get(_SLOT_KEYS[slot])]


_HONORIFICS = {"dr", "doctor", "mr", "ms", "mrs"}


def _name_tokens(value: str) -> list[str]:
    return [t.strip(".") for t in value.lower().split()]


def _match_doctor(raw: str, doctors: list[dict]) -> dict | None:
    """Case-insensitive token match: every meaningful token of the mention
    (honorifics stripped) must appear in the doctor's name."""
    tokens = [t for t in _name_tokens(raw) if t and t not in _HONORIFICS]
    for doctor in doctors:
        name_tokens = set(_name_tokens(doctor["full_name"]))
        if tokens and all(t in name_tokens for t in tokens):
            return doctor
    return None


def _resolve_treatment(raw: str) -> dict | None:
    """Contains-match on the full mention, falling back to its significant tokens
    in order of appearance ('joint pain consultation' → 'joint') so multi-word
    mentions survive the backend's substring search over names like
    'Joint & Pain Consultation'."""
    rows = search_treatments(raw)
    if rows:
        return rows[0]
    tokens = (t for t in re.split(r"\W+", raw.lower()) if len(t) >= 4)
    for token in tokens:
        rows = search_treatments(token)
        if rows:
            return rows[0]
    return None


def extract_slots(state: ClinicGraphState) -> dict:
    draft = dict(state.get("booking_draft") or {})
    extracted = get_slot_extractor().invoke(
        f"{SLOT_EXTRACTION_SYSTEM.format(today=date.today().isoformat(), draft=render_booking_draft(draft))}"
        f"\n\n{SLOT_EXTRACTION_USER.format(message=state['user_message'])}"
    )
    draft["awaiting_confirmation"] = False  # new or corrected details re-open the draft
    if extracted.treatment:
        row = _resolve_treatment(extracted.treatment)
        if row:
            draft.update(
                treatment_id=row["treatment_id"],
                treatment_name=row["treatment_name"],
                category=row["category"],
                duration_minutes=row["duration_minutes"],
                price_usd=row["price_usd"],
            )
            draft.pop("treatment_raw", None)
        else:
            # a failed re-resolution must also clear the old row's display fields:
            # prompts and ask/confirm rendering read name/category from the draft
            draft.update(
                treatment_id=None,
                treatment_name=None,
                category=None,
                price_usd=None,
                duration_minutes=None,
                doctor_options=None,
                treatment_raw=extracted.treatment,
            )
    if extracted.doctor:
        match = _match_doctor(extracted.doctor, search_doctors())
        if match:
            draft.update(
                doctor_id=match["doctor_id"],
                doctor_name=match["full_name"],
                doctor_specialty=match["specialty"],
            )
            draft.pop("doctor_raw", None)
        else:
            draft.update(
                doctor_id=None,
                doctor_name=None,
                doctor_specialty=None,
                doctor_raw=extracted.doctor,
            )
    if extracted.booking_date:
        draft["booking_date"] = extracted.booking_date
    if extracted.booking_time:
        draft["booking_time"] = extracted.booking_time
    # Treatment chosen but no doctor yet → recommend specialty/category matches (§5.2);
    # fall back to all doctors when no specialty matches the treatment's category.
    if draft.get("treatment_id") and not draft.get("doctor_id"):
        draft["doctor_options"] = search_doctors(specialty=draft["category"]) or search_doctors()
    return {"booking_draft": draft}


def ask_missing(state: ClinicGraphState) -> dict:
    """Pure rendering of the first missing slot — no tool calls."""
    draft = state.get("booking_draft") or {}
    first = missing_slots(draft)[0]
    if first == "treatment":
        if draft.get("treatment_raw"):
            reply = (
                f"I couldn't find a treatment matching \"{draft['treatment_raw']}\". "
                "Which treatment would you like?"
            )
        else:
            reply = "Which treatment would you like to book?"
    elif first == "doctor":
        options = draft.get("doctor_options") or []
        listing = "\n".join(
            f"- {o['full_name']} ({o['specialty']}, ${o['consultation_fee_usd']})" for o in options
        )
        if draft.get("doctor_raw"):
            reply = f"I couldn't find a doctor matching \"{draft['doctor_raw']}\"."
            if options:
                reply += f" Available doctors:\n{listing}\nWhich one would you like?"
            else:
                reply += " Which doctor would you like?"
        elif options:
            reply = (
                f"For {draft['treatment_name']}, I'd recommend:\n{listing}\n"
                "Which doctor would you like?"
            )
        else:
            reply = "Which doctor would you like to see?"
    elif first == "date":
        reply = "Which date would you like for the appointment? (e.g. 2026-11-21)"
    else:
        reply = f"What time on {draft.get('booking_date')}? (e.g. 09:30)"
    return {"reply": reply}


def confirm_summary(state: ClinicGraphState) -> dict:
    draft = dict(state.get("booking_draft") or {})
    draft["awaiting_confirmation"] = True
    lines = (
        f"- Treatment: {draft['treatment_name']} (${draft['price_usd']}, {draft['duration_minutes']} min)",
        f"- Doctor: {draft['doctor_name']} ({draft['doctor_specialty']})",
        f"- Date: {draft['booking_date']}",
        f"- Time: {draft['booking_time']}",
    )
    reply = (
        "Here's your booking summary:\n"
        + "\n".join(lines)
        + "\nShall I go ahead and book it? (yes / no)"
    )
    return {"booking_draft": draft, "reply": reply}


def execute_booking(state: ClinicGraphState) -> dict:
    draft = state["booking_draft"]
    try:
        booking = create_booking(
            patient_id=state["patient_id"],
            doctor_id=draft["doctor_id"],
            treatment_id=draft["treatment_id"],
            booking_date=draft["booking_date"],
            booking_time=draft["booking_time"],
        )
    except RuntimeError as e:
        # Tool errors surface as readable text (DESIGN §5.4); draft keeps
        # awaiting_confirmation so the patient can retry with "yes".
        return {"reply": f"I couldn't complete the booking: {e} Say \"yes\" to try again."}
    return {
        "booking_created": booking,
        "booking_draft": {},
        "reply": (
            f"You're booked! {draft['treatment_name']} with {draft['doctor_name']} "
            f"on {draft['booking_date']} at {draft['booking_time']}. "
            f"Your booking reference is {booking['booking_id']}."
        ),
    }
