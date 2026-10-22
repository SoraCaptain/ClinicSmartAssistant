"""Slice-4 done-when regressions: 'knee pain' retrieves T005 (token 'pain') plus
D104 via its Orthopedics category and grounds a cited answer; 'my next
appointment' pulls the patient's joined booking rows with B1004 surfaced. P8
context rides in the state here; the runtime fetch is covered in test_chat_api.py."""

import uuid

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph
from app.agent.prompts import render_bookings
from tests.conftest import BOOKINGS, PATIENT_CONTEXT


def _invoke(graph, message: str, thread_id: str) -> dict:
    return graph.invoke(
        {
            "patient_id": "P001",
            "patient_context": PATIENT_CONTEXT,  # what runtime injects each turn (P8)
            "user_message": message,
            "messages": [{"role": "user", "content": message}],
        },
        {"configurable": {"thread_id": thread_id}},
    )


def test_knee_pain_cites_t005_and_d104(fake_chains):
    """Slice-4 done-when: the full phrase matches no row; token 'pain' → T005, whose
    Orthopedics category recommends D104 — both grounded in the prompt and cited."""
    fakes = fake_chains(
        "qa",
        qa_reply="For knee pain: Joint & Pain Consultation (T005) with Dr. James Wilson (D104).",
    )
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "I have knee pain, what do you recommend?", uuid.uuid4().hex)

    assert result["intent"] == "qa"
    assert "(T005)" in result["reply"] and "(D104)" in result["reply"]
    prompt = fakes["qa"].prompts[-1]
    assert "[T005] Joint & Pain Consultation" in prompt
    assert "[D104] Dr. James Wilson" in prompt
    assert "Penicillin, Peanuts" in prompt  # P8 context rides into the answer prompt
    ids = {
        row.get("treatment_id") or row.get("doctor_id") or row.get("clinic_id")
        for row in result["retrieved"]
    }
    assert {"T005", "D104", "C001"} <= ids


def test_specialty_question_grounds_doctor_directly(fake_chains):
    fakes = fake_chains("qa", qa_reply="Dr. Elena Rostova (D103) covers dermatology.")
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "which doctor should I see for dermatology?", uuid.uuid4().hex)

    assert "[D103] Dr. Elena Rostova" in fakes["qa"].prompts[-1]
    assert result["reply"] == "Dr. Elena Rostova (D103) covers dermatology."


def test_no_catalog_match_renders_none_and_stays_grounded(fake_chains):
    fakes = fake_chains("qa", qa_reply="I don't have that treatment in the catalog.")
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "do you offer aromatherapy massage?", uuid.uuid4().hex)

    assert "(none)" in fakes["qa"].prompts[-1]
    assert result["retrieved"] == []
    assert result["reply"] == "I don't have that treatment in the catalog."


def test_catalog_unreachable_is_readable_without_llm(fake_chains, catalog_fakes):
    fakes = fake_chains("qa", qa_reply="must not be used")
    catalog_fakes(catalog_error=RuntimeError("backend unreachable at http://localhost:8000: boom"))
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "what treatments do you have?", uuid.uuid4().hex)

    assert "couldn't reach the clinic catalog" in result["reply"]
    assert "boom" in result["reply"]
    assert fakes["qa"].prompts == []  # a broken data path never reaches the LLM


def test_next_appointment_surfaces_b1004(fake_chains):
    """Slice-4 done-when: the patient's joined rows (B1001 + B1004) ground the
    answer; the reply surfaces B1004 (the knee follow-up)."""
    fakes = fake_chains(
        "check_bookings",
        bookings_reply=(
            "Your next appointment is B1004: Joint & Pain Consultation with "
            "Dr. James Wilson on 2026-11-15 at 11:00."
        ),
    )
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "when is my next appointment?", uuid.uuid4().hex)

    assert fakes["bookings_tool"].calls == [{"patient_id": "P001"}]
    prompt = fakes["bookings"].prompts[-1]
    for fragment in ("B1001", "B1004", "Joint & Pain Consultation", "Dr. James Wilson", "Follow up on knee pain."):
        assert fragment in prompt
    assert result["reply"].startswith("Your next appointment is B1004")


def test_no_bookings_answers_deterministically(fake_chains, catalog_fakes):
    fakes = fake_chains("check_bookings", bookings_reply="must not be used")
    catalog_fakes(bookings=[])
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "do I have any appointments?", uuid.uuid4().hex)

    assert result["reply"] == "You have no bookings yet. Would you like to book an appointment?"
    assert fakes["bookings"].prompts == []


def test_bookings_tool_failure_is_readable(fake_chains, catalog_fakes):
    fakes = fake_chains("check_bookings", bookings_reply="must not be used")
    catalog_fakes(bookings_error=RuntimeError("backend GET /api/bookings failed: 500 boom"))
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "when is my next appointment?", uuid.uuid4().hex)

    assert "couldn't read your bookings" in result["reply"] and "500 boom" in result["reply"]
    assert fakes["bookings"].prompts == []


def test_render_bookings_orders_upcoming_first():
    """Ordering regression for the fail-silent class membership asserts can't catch:
    a reversed sort key or a flipped today-split still passes fragment checks."""
    earlier = {**BOOKINGS[0], "booking_id": "B1000", "booking_date": "2026-10-01"}
    rows = [BOOKINGS[1], earlier, BOOKINGS[0]]  # shuffled input

    rendered = render_bookings(rows, today="2026-11-01")

    upcoming_block, earlier_block = rendered.split("Earlier:")
    assert "Upcoming:" in upcoming_block
    assert "B1000" not in upcoming_block
    assert upcoming_block.index("B1001") < upcoming_block.index("B1004")  # date order
    assert "B1000" in earlier_block
