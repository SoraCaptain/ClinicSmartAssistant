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

QA_SYSTEM = """You are ClinicPilot, a clinic assistant answering patient questions \
about treatments, doctors and clinics. Use ONLY the patient context and retrieved \
catalog rows provided — never invent clinics, doctors, treatments or prices.
- Cite the row ID in parentheses right after each claim, e.g. (T005), (D104).
- Weigh the patient's context (history, allergies, upcoming bookings) when \
recommending; mention price, duration or preparation from the rows when relevant.
- If the retrieved rows cannot answer the question, say so plainly and list what \
you can help with: treatments, doctors, clinics, existing bookings, new bookings.
Be concise and warm."""

QA_USER = """Conversation so far:
{history}

Patient context:
{patient_context}

Retrieved clinic catalog:
{catalog}

Latest message: {message}"""

BOOKINGS_SYSTEM = """You answer questions about the patient's own bookings using \
ONLY the booking rows provided; upcoming bookings are listed first. Cite the \
booking ID for anything you state, e.g. (B1004); for "next appointment" use the \
earliest upcoming row. Be concise and warm."""

BOOKINGS_USER = """Conversation so far:
{history}

Patient bookings:
{bookings}

Latest message: {message}"""


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


def render_catalog(treatments: list[dict], doctors: list[dict], clinics: list[dict]) -> str:
    """Retrieved rows as grounding blocks; '(none)' sections keep the LLM honest
    about what is absent rather than guessing."""

    def section(title: str, rows: list[dict], render) -> str:
        if not rows:
            return f"{title}:\n(none)"
        return title + ":\n" + "\n".join(f"- {render(r)}" for r in rows)

    return "\n\n".join((
        section(
            "Treatments",
            treatments,
            lambda t: (
                f"[{t['treatment_id']}] {t['treatment_name']} | {t['category']} | "
                f"{t['duration_minutes']} min | ${t['price_usd']} | "
                f"preparation: {t['pre_treatment_instructions']}"
            ),
        ),
        section(
            "Doctors",
            doctors,
            lambda d: (
                f"[{d['doctor_id']}] {d['full_name']} | {d['specialty']} | "
                f"${d['consultation_fee_usd']} | languages: {d['languages_spoken']} | {d['bio']}"
            ),
        ),
        section(
            "Clinics",
            clinics,
            lambda c: (
                f"[{c['clinic_id']}] {c['clinic_name']} | {c['address']} | {c['phone']} | "
                f"hours: {c['operating_hours']}"
            ),
        ),
    ))


def render_patient_context(ctx: dict | None) -> str:
    """P8 payload compacted for prompts; '(unavailable)' when the run carries none."""
    if not ctx:
        return "(unavailable)"
    profile = ctx.get("profile", {})
    lines = [
        f"{profile.get('first_name', '?')} {profile.get('last_name', '?')} "
        f"({profile.get('patient_id', '?')}) | allergies: {profile.get('known_allergies') or 'None'}"
    ]
    if ctx.get("treatment_history"):
        lines.append("Treatment history:")
        lines += [
            f"- {h['visit_date']} {h['chief_complaint']} — {h['diagnosis']} ({h['doctor_id']})"
            for h in ctx["treatment_history"]
        ]
    if ctx.get("upcoming_bookings"):
        lines.append("Upcoming bookings:")
        lines += [
            f"- {b['booking_id']} {b['booking_date']} {b['treatment_name']} with {b['doctor_name']}"
            for b in ctx["upcoming_bookings"]
        ]
    return "\n".join(lines)


def render_bookings(bookings: list[dict], today: str) -> str:
    """BookingJoined rows, upcoming (date >= today) first — ISO dates sort lexically."""

    def row(b: dict) -> str:
        notes = f" | notes: {b['notes']}" if b.get("notes") else ""
        return (
            f"- {b['booking_id']} | {b['booking_date']} {str(b['booking_time'])[:5]} | "
            f"{b['treatment_name']} with {b['doctor_name']} at {b['clinic_name']} | "
            f"{b['status']}{notes}"
        )

    ordered = sorted(bookings, key=lambda b: (b["booking_date"], str(b["booking_time"])))
    upcoming = [b for b in ordered if b["booking_date"] >= today]
    earlier = [b for b in ordered if b["booking_date"] < today]
    parts = []
    if upcoming:
        parts.append("Upcoming:\n" + "\n".join(row(b) for b in upcoming))
    if earlier:
        parts.append("Earlier:\n" + "\n".join(row(b) for b in earlier))
    return "\n\n".join(parts)
