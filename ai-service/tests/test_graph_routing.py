"""Routing contract (slice 2): each single-node intent reaches its own node, and
conversation history persists across turns on the same thread (P1 context). The
booking fan-out is covered in test_booking_flow.py; qa/bookings node behavior in
test_qa_bookings.py."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph

INTENT_FAKE_REPLY = {
    "qa": "Cited answer (T005) (D104).",
    "check_bookings": "Your next appointment is (B1004).",
    "general": "Hi there!",
}
BOOK_INTENT = "book_appointment"


def _invoke(graph, message: str, thread_id: str) -> dict:
    return graph.invoke(
        {
            "patient_id": "P001",
            "user_message": message,
            "messages": [{"role": "user", "content": message}],
        },
        {"configurable": {"thread_id": thread_id}},
    )


@pytest.mark.parametrize("intent,expected_reply", INTENT_FAKE_REPLY.items())
def test_routes_each_intent_to_its_node(fake_chains, intent, expected_reply):
    fake_chains(
        intent,
        general_reply=INTENT_FAKE_REPLY["general"],
        qa_reply=INTENT_FAKE_REPLY["qa"],
        bookings_reply=INTENT_FAKE_REPLY["check_bookings"],
    )
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "hello", uuid.uuid4().hex)

    assert result["intent"] == intent
    assert result["reply"] == expected_reply


def test_book_appointment_enters_slot_filling(fake_chains, booking_fakes):
    """The booking intent routes into extract_slots → ask_missing (no LLM beyond
    the scripted extractor; create_booking untouched)."""
    fake_chains("book_appointment")
    fakes = booking_fakes(slots=[{}])
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "I want to book something", uuid.uuid4().hex)

    assert result["intent"] == "book_appointment"
    assert result["reply"] == "Which treatment would you like to book?"
    assert len(fakes["slots"].prompts) == 1
    assert fakes["create"].calls == []


def test_history_persists_across_turns_on_same_thread(fake_chains):
    """Turn 2's classifier prompt contains turn 1's user and assistant messages (P1)."""
    fakes = fake_chains("general", general_reply="First reply.")
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    _invoke(graph, "hi", thread)
    _invoke(graph, "thanks", thread)

    second_prompt = fakes["classifier"].prompts[-1]
    assert "Patient: hi" in second_prompt
    assert "Assistant: First reply." in second_prompt
    assert "Latest message: thanks" in second_prompt


def test_threads_are_isolated(fake_chains):
    fake_chains("general", general_reply="R.")
    graph = build_clinic_graph(InMemorySaver())

    _invoke(graph, "hi", uuid.uuid4().hex)
    other = _invoke(graph, "hello", uuid.uuid4().hex)

    assert [m.content for m in other["messages"]] == ["hello", "R."]


def test_classifier_prompt_carries_latest_message(fake_chains):
    fakes = fake_chains("qa")
    graph = build_clinic_graph(InMemorySaver())

    _invoke(graph, "which doctor treats knee pain?", uuid.uuid4().hex)

    prompt = fakes["classifier"].prompts[-1]
    assert "which doctor treats knee pain?" in prompt
    assert "(no earlier messages)" in prompt


def test_mismatch_routes_to_clarify_and_never_books(fake_chains, booking_fakes):
    """A treatment whose category clearly matches a DIFFERENT doctor routes to
    clarify_mismatch instead of confirm: both alternatives are rendered and
    create_booking never fires; the patient's correction re-enters extraction and
    only then reaches the confirm → book path."""
    fake_chains([BOOK_INTENT, BOOK_INTENT, (BOOK_INTENT, True)])
    fakes = booking_fakes(
        slots=[
            {"treatment": "dermatology consultation", "doctor": "Dr. Wilson",
             "booking_date": "2026-11-30", "booking_time": "10:00"},
            {"doctor": "Dr. Elena Rostova"},
            {},
        ]
    )
    graph = build_clinic_graph(InMemorySaver())
    thread = uuid.uuid4().hex

    r1 = _invoke(graph, "book a dermatology consultation with Dr. Wilson on 2026-11-30 at 10am", thread)
    assert "Dermatology Consultation matches Dr. Elena Rostova (Dermatology)" in r1["reply"]
    assert "Dr. James Wilson specializes in Orthopedics (Joint & Pain Consultation)" in r1["reply"]
    assert "Which would you like?" in r1["reply"]
    assert r1["booking_draft"]["awaiting_confirmation"] is False
    assert fakes["create"].calls == []

    r2 = _invoke(graph, "Dr. Rostova then, please", thread)
    assert r2["booking_draft"]["doctor_id"] == "D103"
    assert "mismatch" not in r2["booking_draft"]
    assert "booking summary" in r2["reply"] and "yes / no" in r2["reply"]
    assert fakes["create"].calls == []

    r3 = _invoke(graph, "yes", thread)
    assert fakes["create"].calls == [
        {"patient_id": "P001", "doctor_id": "D103", "treatment_id": "T003",
         "booking_date": "2026-11-30", "booking_time": "10:00"}
    ]


def test_no_false_mismatch_without_matching_doctor(fake_chains, booking_fakes):
    """Positive-evidence-only rule: when NO doctor matches the treatment's
    category (T004 Immunization), the patient's chosen doctor is not flagged —
    the pair goes straight to the confirmation gate."""
    fake_chains(BOOK_INTENT)
    fakes = booking_fakes(
        slots=[{"treatment": "flu shot", "doctor": "Dr. Jenkins",
                "booking_date": "2026-12-03", "booking_time": "10:00"}]
    )
    graph = build_clinic_graph(InMemorySaver())

    r = _invoke(graph, "book a flu shot with Dr. Jenkins on 2026-12-03 at 10am", uuid.uuid4().hex)

    assert "booking summary" in r["reply"]
    assert "Flu Shot Injection" in r["reply"] and "Dr. Sarah Jenkins" in r["reply"]
    assert r["booking_draft"]["awaiting_confirmation"] is True
    assert "mismatch" not in r["booking_draft"]
    assert fakes["create"].calls == []
