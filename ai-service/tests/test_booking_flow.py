"""Booking flow contract (slice-3 done-when): a multi-turn conversation books via the
mocked create_booking POST exactly once per explicit confirmation (P2); turns without
confirmation never call it. Slots accumulate across turns (P1); a pending draft
neither traps non-booking turns nor leaks into them."""

import uuid

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph

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
    """Slot-by-slot across 5 turns → ask, ask, ask, confirm, book (slice-3 done-when);
    a post-success "yes" cannot re-fire the booking (P2 exactly-once)."""
    fake_chains([BOOK_INTENT] * 4 + [(BOOK_INTENT, True)] * 2)
    fakes = booking_fakes(
        slots=[
            {"treatment": "joint pain consultation"},
            {"doctor": "Dr. Wilson"},
            {"booking_date": "2026-11-21"},
            {"booking_time": "09:30"},
            {},
            {},
        ]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "I'd like to book a joint pain consultation", thread)
    assert "recommend" in r1["reply"] and "Dr. James Wilson" in r1["reply"]

    r2 = _invoke(graph, "Dr. Wilson please", thread)
    assert "Which date" in r2["reply"]

    r3 = _invoke(graph, "November 21st", thread)
    assert "What time" in r3["reply"]

    r4 = _invoke(graph, "9:30 in the morning", thread)
    assert "booking summary" in r4["reply"]
    for fragment in ("Joint & Pain Consultation", "$230.00", "Dr. James Wilson", "2026-11-21", "09:30"):
        assert fragment in r4["reply"]
    assert r4["booking_draft"]["awaiting_confirmation"] is True
    assert fakes["create"].calls == []  # no confirmation yet → no POST

    r5 = _invoke(graph, "yes, book it", thread)
    assert "B9f2a1" in r5["reply"]
    assert r5["booking_created"]["booking_id"] == "B9f2a1"
    assert r5["booking_draft"] == {}
    assert fakes["create"].calls == [FULL_PAYLOAD]  # exactly once, correct payload

    r6 = _invoke(graph, "yes", thread)  # draft cleared → fresh flow, no re-fire
    assert r6["reply"] == "Which treatment would you like to book?"
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
    resolution falls back to significant tokens ('joint' → T005)."""
    fake_chains(BOOK_INTENT)
    booking_fakes(slots=[{"treatment": "joint pain consultation"}])
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "I'd like to book a joint pain consultation", uuid.uuid4().hex)

    assert result["booking_draft"]["treatment_id"] == "T005"
    assert "recommend" in result["reply"]


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
