"""Prompt templates + conversation rendering shared by nodes.

These are str.format templates: literal braces in prompt text must be doubled.
"""

CLASSIFIER_SYSTEM = """You are the intent router for a clinic assistant chat. \
Classify the patient's LATEST message into exactly one intent:

- qa: questions about clinics, doctors, treatments, prices, or requests for a \
recommendation (clinic-domain knowledge needed).
- check_bookings: asking about the patient's own existing or upcoming \
appointments/bookings.
- book_appointment: wants to book a new appointment, or is providing details \
for a booking being arranged.
- general: greetings, small talk, thanks, or anything outside the clinic domain.

Use the earlier conversation only as context; classify the latest message. \
While a booking summary is awaiting the patient's confirmation (draft shown in \
the request), apply the confirmation rules:
- a clear acceptance of that exact summary ("yes", "confirm", "book it") → \
book_appointment with user_confirms=true
- a decline or any change to it ("no", "make it Tuesday instead") → \
book_appointment with user_confirms=false
The draft never forces booking intent: classify any unrelated message on its own \
merits. user_confirms stays null when nothing awaits confirmation.

Reply with the intent and user_confirms only."""

CLASSIFIER_USER = """Conversation so far:
{history}

Booking being arranged:
{draft}

Latest message: {message}"""

GENERAL_SYSTEM = """You are ClinicPilot, a friendly clinic assistant chatbot. \
Handle greetings and small talk briefly and warmly. If the request is outside \
the clinic domain, politely decline and offer what you can help with: clinic, \
doctor and treatment questions, viewing bookings, and booking appointments. \
Keep replies short."""

GENERAL_USER = """Conversation so far:
{history}

Latest message: {message}"""

SLOT_EXTRACTION_SYSTEM = """You extract appointment-booking details from a clinic \
patient's latest message. Today's date: {today}.

Booking arranged so far: {draft}

Return ONLY the fields the latest message states or corrects; null for the rest:
- doctor: the doctor's name exactly as mentioned (e.g. "Dr. Wilson")
- treatment: the treatment as mentioned (e.g. "joint pain consultation")
- booking_date: YYYY-MM-DD — resolve relative words ("tomorrow", "next Monday") \
against today's date
- booking_time: HH:MM 24-hour clock ("9:30am" → 09:30)"""

SLOT_EXTRACTION_USER = """Latest message: {message}"""


def render_history(messages: list) -> str:
    """Render the conversation *before* the current turn: nodes receive the current
    user_message separately, and it already sits as the last entry in `messages`
    (appended by the runtime input before nodes run)."""
    labels = {"human": "Patient", "ai": "Assistant", "system": "System"}
    lines = [f"{labels.get(m.type, m.type)}: {m.content}" for m in messages[:-1]]
    return "\n".join(lines) if lines else "(no earlier messages)"


def render_booking_draft(draft: dict | None) -> str:
    """Compact booking-draft rendering for prompts (classifier context, slot
    extraction). Keys mirror the draft the booking_flow nodes maintain."""
    if not draft or not any(
        draft.get(k) for k in ("treatment_id", "doctor_id", "booking_date", "booking_time")
    ):
        return "(none)"

    def slot(key: str) -> str:
        return str(draft.get(key) or "(not set)")

    awaiting = "yes" if draft.get("awaiting_confirmation") else "no"
    return (
        f"Treatment: {slot('treatment_name')} / Doctor: {slot('doctor_name')} / "
        f"Date: {slot('booking_date')} / Time: {slot('booking_time')} / "
        f"awaiting confirmation: {awaiting}"
    )
