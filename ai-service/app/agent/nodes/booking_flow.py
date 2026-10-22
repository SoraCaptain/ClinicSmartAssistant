"""Booking flow nodes (DESIGN §5.2): extract_slots resolves the latest message into
draft slots (all catalog/booking data via REST tools, P3), ask_missing renders the
next question (with unique-match auto-applied statements, catalog enumeration and
date complaints), clarify_mismatch renders an inconsistent doctor↔treatment pair,
confirm_summary renders doctor+treatment+date+time+fee behind
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
    render_history,
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


def _identity_rows(rows: list[dict], needle: str) -> list[dict]:
    """Rows whose identity fields (treatment_name, category) case-insensitively
    contain the needle. The backend search also matches pre_treatment_instructions
    — that is QA-retrieval aid, not entity identity: without this filter an unknown
    mention's token silently substitutes whichever treatment its words happen to
    hit in the instructions."""
    folded = needle.casefold()
    return [
        row
        for row in rows
        if folded in row["treatment_name"].casefold() or folded in row["category"].casefold()
    ]


def _resolve_treatment(raw: str) -> dict | None:
    """Identity-fields-only resolution: a row is accepted only when the mention
    (full string first, then its significant tokens in order of appearance —
    'joint pain consultation' → 'joint') contains-matches its treatment_name or
    category, so multi-word mentions survive the backend's substring search over
    names like 'Joint & Pain Consultation' while unknown mentions stay
    unresolved instead of grabbing an instructions-only match."""
    rows = _identity_rows(search_treatments(raw), raw)
    if rows:
        return rows[0]
    tokens = (t for t in re.split(r"\W+", raw.lower()) if len(t) >= 4)
    for token in tokens:
        rows = _identity_rows(search_treatments(token), token)
        if rows:
            return rows[0]
    return None


def _apply_treatment(draft: dict, row: dict) -> None:
    draft.update(
        treatment_id=row["treatment_id"],
        treatment_name=row["treatment_name"],
        category=row["category"],
        duration_minutes=row["duration_minutes"],
        price_usd=row["price_usd"],
    )
    draft.pop("treatment_raw", None)
    draft.pop("treatment_options", None)


def _apply_doctor(draft: dict, row: dict) -> None:
    draft.update(
        doctor_id=row["doctor_id"],
        doctor_name=row["full_name"],
        doctor_specialty=row["specialty"],
    )
    draft.pop("doctor_raw", None)
    draft.pop("doctor_options", None)


def _category_doctor_matches(category: str) -> list[dict]:
    """Doctors matching a treatment's category: the specialty filter first, then a
generic search bridging through name/specialty/languages/bio (a 'Preventative
Care' category reaches the General Practice doctor only through her bio)."""
    return search_doctors(specialty=category) or search_doctors(search=category)


def _specialty_treatment_candidates(specialty: str) -> list[dict]:
    """Treatments matching a doctor's specialty: the catalog search plus a two-way
category⊂⊃specialty containment pass (the search needle alone is one-directional)."""
    rows = search_treatments(search=specialty)
    seen = {row["treatment_id"] for row in rows}
    needle = specialty.casefold()
    for row in search_treatments():
        category = row["category"].casefold()
        if (needle in category or category in needle) and row["treatment_id"] not in seen:
            seen.add(row["treatment_id"])
            rows.append(row)
    return rows


def _date_issue(value: str) -> str | None:
    """Why `value` cannot be booked, or None when it is a valid future date."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return f'"{value}" is not a valid date'
    return f"{value} is in the past" if parsed < date.today() else None


def extract_slots(state: ClinicGraphState) -> dict:
    draft = dict(state.get("booking_draft") or {})
    # Derived per turn — dropped up front so a later correction can never resurrect
    # a stale auto-applied note, mismatch verdict, or date complaint.
    for key in ("doctor_auto", "treatment_auto", "mismatch", "date_issue"):
        draft.pop(key, None)
    extracted = get_slot_extractor().invoke(
        f"{SLOT_EXTRACTION_SYSTEM.format(today=date.today().isoformat(), history=render_history(state.get('messages', [])), draft=render_booking_draft(draft))}"
        f"\n\n{SLOT_EXTRACTION_USER.format(message=state['user_message'])}"
    )
    draft["awaiting_confirmation"] = False  # new or corrected details re-open the draft
    if extracted.treatment:
        row = _resolve_treatment(extracted.treatment)
        if row:
            _apply_treatment(draft, row)
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
            draft["treatment_options"] = search_treatments()  # ask_missing enumerates these
    if extracted.doctor:
        match = _match_doctor(extracted.doctor, search_doctors())
        if match:
            _apply_doctor(draft, match)
        else:
            draft.update(
                doctor_id=None,
                doctor_name=None,
                doctor_specialty=None,
                doctor_raw=extracted.doctor,
            )
            draft["doctor_options"] = search_doctors()  # ask_missing enumerates these
    if extracted.booking_date:
        issue = _date_issue(extracted.booking_date)
        if issue:
            draft["booking_date"] = None  # an invalid/past date never books, even over a good one
            draft["date_issue"] = issue
        else:
            draft["booking_date"] = extracted.booking_date
    if extracted.booking_time:
        draft["booking_time"] = extracted.booking_time
    # Unique-match auto-fill: don't ask an open-ended question a single catalog row
    # already answers. An explicit-but-unresolved mention (…_raw set) is the
    # patient's own choice — never overridden by an auto-fill.
    if draft.get("treatment_id") and not draft.get("doctor_id") and not draft.get("doctor_raw"):
        candidates = _category_doctor_matches(draft["category"])
        if len(candidates) == 1:
            _apply_doctor(draft, candidates[0])
            draft["doctor_auto"] = True
    if draft.get("doctor_id") and not draft.get("treatment_id") and not draft.get("treatment_raw"):
        candidates = _specialty_treatment_candidates(draft["doctor_specialty"])
        if len(candidates) == 1:
            _apply_treatment(draft, candidates[0])
            draft["treatment_auto"] = True
    # Treatment chosen but no doctor yet → recommend specialty/category matches (§5.2);
    # fall back to all doctors when no specialty matches the treatment's category.
    if draft.get("treatment_id") and not draft.get("doctor_id"):
        draft["doctor_options"] = search_doctors(specialty=draft["category"]) or search_doctors()
    # Both resolved but inconsistent → clarify instead of confirming; only when a
    # better-matching doctor exists (a category no doctor covers is not a mismatch).
    if draft.get("treatment_id") and draft.get("doctor_id"):
        matches = _category_doctor_matches(draft["category"])
        if matches and draft["doctor_id"] not in {d["doctor_id"] for d in matches}:
            draft["mismatch"] = {
                "doctors": [
                    {"doctor_id": d["doctor_id"], "full_name": d["full_name"], "specialty": d["specialty"]}
                    for d in matches
                ],
                "treatments": [
                    {"treatment_id": t["treatment_id"], "treatment_name": t["treatment_name"]}
                    for t in _specialty_treatment_candidates(draft["doctor_specialty"])
                ],
            }
    return {"booking_draft": draft}


def _doctor_listing(options: list[dict]) -> str:
    return "\n".join(
        f"- {o['full_name']} ({o['specialty']}, ${o['consultation_fee_usd']})" for o in options
    )


def _raw_mention_complaints(draft: dict) -> list[str]:
    """Every unresolved raw mention renders a complaint — even when its slot is
    not the first missing one: an unsurfaced complaint is dropped for good at the
    next extract turn, so swallowing it here would lose it silently."""
    complaints = []
    if draft.get("treatment_raw"):
        complaint = (
            f'I couldn\'t find a treatment matching "{draft["treatment_raw"]}" — '
            "it is not offered at this clinic."
        )
        names = ", ".join(t["treatment_name"] for t in draft.get("treatment_options") or [])
        if names:
            complaint += f" Available treatments: {names}."
        complaints.append(complaint)
    if draft.get("doctor_raw"):
        complaint = (
            f'I couldn\'t find a doctor matching "{draft["doctor_raw"]}" — '
            "that doctor is not available at this clinic."
        )
        options = draft.get("doctor_options") or []
        if options:
            complaint += f" Available doctors:\n{_doctor_listing(options)}"
        complaints.append(complaint)
    return complaints


def ask_missing(state: ClinicGraphState) -> dict:
    """Pure rendering of the first missing slot — no tool calls. Unresolved raw
    mentions complain up front whatever the first missing slot is (each complaint
    carries the options enumeration already in the draft)."""
    draft = state.get("booking_draft") or {}
    first = missing_slots(draft)[0]
    if first == "treatment":
        reply = "Which treatment would you like to book?"
    elif first == "doctor":
        options = draft.get("doctor_options") or []
        if draft.get("doctor_raw"):
            reply = "Which one would you like?"  # the complaint above already enumerated
        elif options:
            reply = (
                f"For {draft['treatment_name']}, I'd recommend:\n{_doctor_listing(options)}\n"
                "Which doctor would you like?"
            )
        else:
            reply = "Which doctor would you like to see?"
    elif first == "date":
        if draft.get("date_issue"):
            reply = f"{draft['date_issue']}. Please choose a valid future date."
        else:
            reply = "Which date would you like for the appointment? (YYYY-MM-DD)"
    else:
        reply = f"What time on {draft.get('booking_date')}? (e.g. 09:30)"
    # Auto-applied unique matches are stated up front, not asked about (TEST §8).
    notes = []
    if draft.get("doctor_auto"):
        notes.append(f"{draft['doctor_name']} is the matching {draft['doctor_specialty']} specialist.")
    if draft.get("treatment_auto"):
        notes.append(f"The matching {draft['doctor_specialty']} service is {draft['treatment_name']}.")
    return {"reply": "\n".join([*notes, *_raw_mention_complaints(draft), reply])}


def confirm_summary(state: ClinicGraphState) -> dict:
    draft = dict(state.get("booking_draft") or {})
    draft["awaiting_confirmation"] = True
    lines = (
        f"- Treatment: {draft['treatment_name']} (${draft['price_usd']}, {draft['duration_minutes']} min)",
        f"- Doctor: {draft['doctor_name']} ({draft['doctor_specialty']})",
        f"- Date: {draft['booking_date']}",
        f"- Time: {draft['booking_time']}",
    )
    if draft.get("doctor_auto"):
        lines += (f"- Note: {draft['doctor_name']} auto-matched as the only {draft['doctor_specialty']} specialist for this treatment.",)
    if draft.get("treatment_auto"):
        lines += (f"- Note: {draft['treatment_name']} auto-matched as the only {draft['doctor_specialty']} service for this doctor.",)
    reply = (
        "Here's your booking summary:\n"
        + "\n".join(lines)
        + "\nShall I go ahead and book it? (yes / no)"
    )
    return {"booking_draft": draft, "reply": reply}


def clarify_mismatch(state: ClinicGraphState) -> dict:
    """Pure rendering of a doctor↔treatment inconsistency (extract_slots stashed the
    alternatives): the pair is clarified, never silently confirmed or booked."""
    draft = state["booking_draft"]
    mismatch = draft["mismatch"]
    doctors = ", ".join(f"{d['full_name']} ({d['specialty']})" for d in mismatch["doctors"])
    services = ", ".join(t["treatment_name"] for t in mismatch["treatments"])
    reply = (
        f"{draft['treatment_name']} matches {doctors}, while {draft['doctor_name']} "
        f"specializes in {draft['doctor_specialty']}"
    )
    if services:
        reply += f" ({services})"
    reply += ". Which would you like?"
    return {"reply": reply}


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
