"""Routing contract (slice 2): each single-node intent reaches its own node, and
conversation history persists across turns on the same thread (P1 context). The
booking fan-out is covered in test_booking_flow.py."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph
from app.agent.nodes import bookings_query as bookings_query_mod
from app.agent.nodes import qa as qa_mod

INTENT_EXPECTED_REPLY = {
    "qa": qa_mod.REPLY,
    "check_bookings": bookings_query_mod.REPLY,
    "general": "Hi there!",
}


def _invoke(graph, message: str, thread_id: str) -> dict:
    return graph.invoke(
        {"user_message": message, "messages": [{"role": "user", "content": message}]},
        {"configurable": {"thread_id": thread_id}},
    )


@pytest.mark.parametrize("intent,expected_reply", INTENT_EXPECTED_REPLY.items())
def test_routes_each_intent_to_its_node(fake_chains, intent, expected_reply):
    fake_chains(intent, general_reply="Hi there!")
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
