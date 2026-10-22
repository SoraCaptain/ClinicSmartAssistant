"""Booking flow contract (slice-3 done-when): a multi-turn conversation books via the
mocked create_booking POST exactly once per explicit confirmation (P2); turns without
confirmation never call it. Slots accumulate across turns (P1); a pending draft
neither traps non-booking turns nor leaks into them."""

import uuid
from datetime import date, timedelta

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph
from app.agent.nodes.booking_flow import _resolve_treatment
from tests.conftest import TREATMENTS

BOOK_INTENT = "book_appointment"
FULL_PAYLOAD = {
    "patient_id": "P001",
    "doctor_id": "D104",
    "treatment_id": "T005",
    "booking_date": "2026-11-21",
    "booking_time": "09:30",
}
ALL_SLOTS = {
    "treatment": "joint pain consultation",
    "doctor": "Dr. Wilson",
    "booking_date": "2026-11-21",
    "booking_time": "09:30",
}


def _invoke(graph, message: str, thread_id: str) -> dict:
    return graph.invoke(
        {
            "patient_id": "P001",
            "user_message": message,
            "messages": [{"role": "user", "content": message}],
        },
        {"configurable": {"thread_id": thread_id}},
    )


def test_full_booking_books_exactly_once_via_post(fake_chains, booking_fakes):
    """Slot-by-slot across turns → auto-filled doctor + ask date, ask time, confirm,
    book (slice-3 done-when; Wilson is the unique Orthopedics match, so turn 1
    auto-applies him instead of asking); a post-success "yes" cannot re-fire the
    booking (P2 exactly-once)."""
    fake_chains([BOOK_INTENT] * 3 + [(BOOK_INTENT, True)] * 2)
    fakes = booking_fakes(
        slots=[
            {"treatment": "joint pain consultation"},
            {"booking_date": "2026-11-21"},
            {"booking_time": "09:30"},
            {},
            {},
        ]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "I'd like to book a joint pain consultation", thread)
    assert "Dr. James Wilson is the matching Orthopedics specialist" in r1["reply"]
    assert r1["booking_draft"]["doctor_id"] == "D104" and r1["booking_draft"]["doctor_auto"] is True
    assert "Which date" in r1["reply"]

    r2 = _invoke(graph, "November 21st", thread)
    assert "What time" in r2["reply"]

    r3 = _invoke(graph, "9:30 in the morning", thread)
    assert "booking summary" in r3["reply"]
    for fragment in ("Joint & Pain Consultation", "$230.00", "Dr. James Wilson", "2026-11-21", "09:30"):
        assert fragment in r3["reply"]
    assert r3["booking_draft"]["awaiting_confirmation"] is True
    assert fakes["create"].calls == []  # no confirmation yet → no POST

    r4 = _invoke(graph, "yes, book it", thread)
    assert "B9f2a1" in r4["reply"]
    assert r4["booking_created"]["booking_id"] == "B9f2a1"
    assert r4["booking_draft"] == {}
    assert fakes["create"].calls == [FULL_PAYLOAD]  # exactly once, correct payload

    r5 = _invoke(graph, "yes", thread)  # draft cleared → fresh flow, no re-fire
    assert r5["reply"] == "Which treatment would you like to book?"
    assert fakes["create"].calls == [FULL_PAYLOAD]


def test_complete_draft_without_confirmation_never_posts(fake_chains, booking_fakes):
    """All slots in one message → summary only; a later non-booking turn keeps the
    draft (P1) and still never calls create_booking."""
    fake_chains([BOOK_INTENT, "qa", (BOOK_INTENT, True)])
    fakes = booking_fakes(slots=[dict(ALL_SLOTS), {}, {}])
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "book joint pain with Dr. Wilson on 2026-11-21 at 09:30", thread)
    assert "yes / no" in r1["reply"]
    assert fakes["create"].calls == []

    r2 = _invoke(graph, "actually, what treatments do you offer?", thread)
    assert r2["intent"] == "qa"  # pending draft does not trap the turn (P1)
    assert r2["booking_draft"]["awaiting_confirmation"] is True
    assert fakes["create"].calls == []

    r3 = _invoke(graph, "ok yes please", thread)
    assert r3["booking_created"] is not None
    assert len(fakes["create"].calls) == 1


def test_denial_with_correction_reconfirms_then_books(fake_chains, booking_fakes):
    """"no, the 22nd" re-enters extraction with corrections; only the later yes posts."""
    fake_chains([BOOK_INTENT, (BOOK_INTENT, False), (BOOK_INTENT, True)])
    fakes = booking_fakes(slots=[dict(ALL_SLOTS), {"booking_date": "2026-11-22"}, {}])
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    _invoke(graph, "book joint pain with Dr. Wilson on 2026-11-21 at 09:30", thread)
    r2 = _invoke(graph, "no, make it the 22nd instead", thread)
    assert "2026-11-22" in r2["reply"] and "yes / no" in r2["reply"]
    assert fakes["create"].calls == []

    r3 = _invoke(graph, "yes", thread)
    assert {**FULL_PAYLOAD, "booking_date": "2026-11-22"} == fakes["create"].calls[0]


def test_slots_accumulate_across_turns(fake_chains, booking_fakes):
    fake_chains([BOOK_INTENT] * 3)
    booking_fakes(
        slots=[
            {"treatment": "joint pain consultation"},
            {"doctor": "Dr. Wilson"},
            {"booking_date": "2026-11-21", "booking_time": "14:00"},
        ]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    _invoke(graph, "I want a joint pain consultation", thread)
    r2 = _invoke(graph, "Dr. Wilson", thread)
    assert r2["booking_draft"]["doctor_id"] == "D104"  # turn-1 treatment survived
    assert "Which date" in r2["reply"]

    r3 = _invoke(graph, "Nov 21 at 2pm", thread)
    assert r3["booking_draft"]["booking_time"] == "14:00"


def test_unresolvable_entities_ask_for_clarification(fake_chains, booking_fakes):
    fake_chains([BOOK_INTENT, BOOK_INTENT])
    booking_fakes(
        slots=[
            {"treatment": "aromatherapy massage"},
            {"treatment": "health checkup", "doctor": "Dr. Who"},
        ]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "book an aromatherapy massage", thread)
    assert "couldn't find a treatment matching \"aromatherapy massage\"" in r1["reply"]

    r2 = _invoke(graph, "a health checkup with Dr. Who", thread)
    assert "couldn't find a doctor matching \"Dr. Who\"" in r2["reply"]
    assert "Available doctors:" in r2["reply"]


def test_multiword_mention_resolves_via_token_fallback(fake_chains, booking_fakes):
    """'joint pain consultation' is not a substring of 'Joint & Pain Consultation';
    resolution falls back to significant tokens ('joint' → T005); the unique
    Orthopedics match is then auto-applied and stated."""
    fake_chains(BOOK_INTENT)
    booking_fakes(slots=[{"treatment": "joint pain consultation"}])
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "I'd like to book a joint pain consultation", uuid.uuid4().hex)

    assert result["booking_draft"]["treatment_id"] == "T005"
    assert "matching Orthopedics specialist" in result["reply"]


def test_instructions_only_match_never_resolves(booking_fakes):
    """Regression: resolution is identity-fields (treatment_name/category) only.
    The backend search also matches pre_treatment_instructions, so a token of an
    unknown mention (here hitting the '…blood tests are scheduled' row) used to
    resolve it to that unrelated treatment — unknown mentions must stay
    unresolved."""
    booking_fakes(slots=[{}])

    assert _resolve_treatment("blood test") is None


def test_identity_field_mentions_still_resolve(booking_fakes):
    """The identity rule keeps every legitimate mention resolving: a full name,
    a category, and a multi-word name via token fallback."""
    booking_fakes(slots=[{}])

    assert _resolve_treatment("General Health Checkup")["treatment_id"] == "T001"
    assert _resolve_treatment("preventative care")["treatment_id"] == "T001"
    assert _resolve_treatment("joint pain consultation")["treatment_id"] == "T005"


def test_unknown_mention_hitting_instructions_stays_unresolved(fake_chains, booking_fakes):
    """End-to-end regression for the same class: the mention sets treatment_raw
    and renders the complaint — no silent substitution, no doctor auto-match, no
    booking summary riding on the wrongly grabbed row."""
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(slots=[{"treatment": "blood test"}])
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, "book a blood test", uuid.uuid4().hex)

    draft = r["booking_draft"]
    assert draft["treatment_id"] is None and draft["treatment_name"] is None
    assert draft.get("doctor_id") is None  # no auto-match off a substituted row
    assert draft["treatment_raw"] == "blood test"
    assert 'couldn\'t find a treatment matching "blood test"' in r["reply"]
    assert fakes["create"].calls == []


def test_failed_remention_clears_stale_display_fields(fake_chains, booking_fakes):
    """A resolved slot re-mentioned unresolvably drops the old row's name/price:
    prompts render those fields, so stale values would mislead the LLM."""
    fake_chains([BOOK_INTENT, BOOK_INTENT])
    booking_fakes(
        slots=[{"treatment": "joint pain consultation"}, {"treatment": "aromatherapy massage"}]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "joint pain consultation please", thread)
    assert r1["booking_draft"]["treatment_id"] == "T005"

    r2 = _invoke(graph, "actually, make it an aromatherapy massage", thread)
    draft = r2["booking_draft"]
    assert draft["treatment_id"] is None
    assert draft["treatment_name"] is None and draft["price_usd"] is None
    assert "couldn't find a treatment matching \"aromatherapy massage\"" in r2["reply"]


def test_execute_failure_is_readable_and_retryable(fake_chains, booking_fakes):
    """Backend failure → readable reply, draft still awaiting so "yes" retries (P2 data
    path survives errors; the error is never swallowed silently)."""
    fake_chains([BOOK_INTENT, (BOOK_INTENT, True), (BOOK_INTENT, True)])
    fakes = booking_fakes(
        slots=[dict(ALL_SLOTS), {}, {}],
        create_errors=[RuntimeError("backend POST /api/bookings failed: 500 boom")],
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    _invoke(graph, "book joint pain with Dr. Wilson on 2026-11-21 at 09:30", thread)
    r2 = _invoke(graph, "yes", thread)
    assert "couldn't complete the booking" in r2["reply"] and "500 boom" in r2["reply"]
    assert r2["booking_draft"]["awaiting_confirmation"] is True
    assert r2.get("booking_created") is None

    r3 = _invoke(graph, "yes, try again", thread)
    assert r3["booking_created"]["booking_id"] == "B9f2a1"
    assert len(fakes["create"].calls) == 2


def test_classifier_prompt_carries_pending_draft(fake_chains, booking_fakes):
    installed = fake_chains([BOOK_INTENT, BOOK_INTENT])
    booking_fakes(slots=[dict(ALL_SLOTS), {}])
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    _invoke(graph, "book joint pain with Dr. Wilson on 2026-11-21 at 09:30", thread)
    _invoke(graph, "hmm", thread)

    prompt = installed["classifier"].prompts[-1]
    assert "Booking being arranged" in prompt
    assert "awaiting confirmation: yes" in prompt
    assert "Joint & Pain Consultation" in prompt


def test_extraction_prompt_carries_conversation_history(fake_chains, booking_fakes):
    """Extraction must see earlier turns so references ('it', 'the recommended
    option') can resolve to the entity the conversation established."""
    fake_chains([BOOK_INTENT] * 2)
    fakes = booking_fakes(
        slots=[{"treatment": "joint pain consultation"}, {"booking_date": "2026-11-28"}]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "I'd like to book a joint pain consultation", thread)
    _invoke(graph, "the 28th of November", thread)

    prompt = fakes["slots"].prompts[1]
    assert "Conversation so far:" in prompt
    assert "Patient: I'd like to book a joint pain consultation" in prompt
    assert f"Assistant: {r1['reply']}" in prompt
    assert "Latest message: the 28th of November" in prompt


def test_unique_doctor_autofill_reaches_confirm_with_note(fake_chains, booking_fakes):
    """T003's Dermatology category has exactly one doctor → auto-applied and stated
    in the confirm summary (no open-ended doctor question, no booking yet)."""
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(
        slots=[{"treatment": "dermatology consultation", "booking_date": "2026-11-20", "booking_time": "14:30"}]
    )
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, "book a dermatology consultation on 2026-11-20 at 2:30pm", uuid.uuid4().hex)

    draft = r["booking_draft"]
    assert draft["doctor_id"] == "D103" and draft["doctor_auto"] is True
    assert "booking summary" in r["reply"]
    assert "Dr. Elena Rostova" in r["reply"]
    assert "auto-matched" in r["reply"]
    assert fakes["create"].calls == []


def test_unique_treatment_autofill_for_doctor_specialty(fake_chains, booking_fakes):
    """D104's Orthopedics specialty matches exactly one treatment → auto-applied
    and stated in the confirm summary."""
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(
        slots=[{"doctor": "Dr. Wilson", "booking_date": "2026-11-21", "booking_time": "10:00"}]
    )
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, "book Dr. Wilson on 2026-11-21 at 10am", uuid.uuid4().hex)

    draft = r["booking_draft"]
    assert draft["treatment_id"] == "T005" and draft["treatment_auto"] is True
    assert "Joint & Pain Consultation" in r["reply"]
    assert "auto-matched" in r["reply"]
    assert fakes["create"].calls == []


def test_unresolved_doctor_complaint_rides_with_next_question(fake_chains, booking_fakes):
    """Complaints are never silently swallowed: an unresolved doctor mention
    renders its complaint (with the doctor list) even though treatment is the
    first missing slot — one reply carries both; nothing books."""
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(
        slots=[{"doctor": "Dr. Nobody", "booking_date": "2026-11-21", "booking_time": "10:00"}]
    )
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, "book with Dr. Nobody on 2026-11-21 at 10am", uuid.uuid4().hex)

    assert "couldn't find a doctor matching \"Dr. Nobody\"" in r["reply"]
    assert "not available" in r["reply"]
    assert "Available doctors:" in r["reply"] and "Dr. Sarah Jenkins" in r["reply"]
    assert "Which treatment would you like to book?" in r["reply"]
    assert fakes["create"].calls == []


def test_unresolved_treatment_lists_available_treatments(fake_chains, booking_fakes):
    """An unresolvable treatment mention enumerates the catalog instead of asking
    an empty open-ended question."""
    fake_chains(BOOK_INTENT)
    booking_fakes(slots=[{"treatment": "aromatherapy massage"}])
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, "book an aromatherapy massage", uuid.uuid4().hex)

    assert "couldn't find a treatment matching \"aromatherapy massage\"" in r["reply"]
    for row in TREATMENTS:
        assert row["treatment_name"] in r["reply"]


def test_extraction_prompt_demands_verbatim_mentions_and_dates(fake_chains, booking_fakes):
    """Live-extraction regressions: the model substituted catalog items for
    unknown mentions and silently dropped impossible dates. The prompt now
    demands both be returned as stated, leaving rejection to the flow."""
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(slots=[{"treatment": "joint pain consultation"}])
    graph = build_clinic_graph(InMemorySaver())

    _invoke(graph, "book a joint pain consultation", uuid.uuid4().hex)

    prompt = fakes["slots"].prompts[0]
    assert "return the mention verbatim" in prompt
    assert "never substitute the nearest catalog" in prompt
    assert "impossible calendar date" in prompt
    assert "never correct it" in prompt


def test_invalid_calendar_date_is_rejected_then_reasked(fake_chains, booking_fakes):
    """An impossible calendar date never fills the slot nor books; a later valid
    date completes the draft and clears the complaint (no stale resurrection)."""
    fake_chains([BOOK_INTENT, BOOK_INTENT, (BOOK_INTENT, True)])
    fakes = booking_fakes(
        slots=[
            {"treatment": "joint pain consultation", "doctor": "Dr. Wilson",
             "booking_date": "2027-02-30", "booking_time": "10:00"},
            {"booking_date": "2027-03-01"},
            {},
        ]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "book joint pain with Dr. Wilson on Feb 30 2027 at 10am", thread)
    draft = r1["booking_draft"]
    assert draft["treatment_id"] == "T005" and draft["doctor_id"] == "D104"  # other slots kept
    assert draft["booking_date"] is None
    assert "2027-02-30" in r1["reply"] and "is not a valid date" in r1["reply"]
    assert fakes["create"].calls == []

    r2 = _invoke(graph, "March 1st then", thread)
    assert r2["booking_draft"]["booking_date"] == "2027-03-01"
    assert "date_issue" not in r2["booking_draft"]
    assert "booking summary" in r2["reply"] and "2027-03-01" in r2["reply"]
    assert fakes["create"].calls == []

    r3 = _invoke(graph, "yes", thread)
    assert fakes["create"].calls == [{**FULL_PAYLOAD, "booking_date": "2027-03-01", "booking_time": "10:00"}]


def test_past_date_is_rejected(fake_chains, booking_fakes):
    """A date before today never fills the slot nor books."""
    past = (date.today() - timedelta(days=2)).isoformat()
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(
        slots=[{"treatment": "joint pain consultation", "booking_date": past, "booking_time": "10:00"}]
    )
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, f"book joint pain on {past} at 10am", uuid.uuid4().hex)

    assert r["booking_draft"]["booking_date"] is None
    assert f"{past} is in the past" in r["reply"]
    assert "valid future date" in r["reply"]
    assert fakes["create"].calls == []
