"""Slice-4 done-when regressions: 'knee pain' retrieves T005 (token 'pain') plus
D104 via its Orthopedics category and grounds a cited answer; 'my next
appointment' pulls the patient's joined booking rows with B1004 surfaced. P8
context rides in the state here; the runtime fetch is covered in test_chat_api.py."""

import uuid

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph
from app.agent.nodes.qa import retrieve_catalog
from app.agent.prompts import render_bookings, render_catalog, render_patient_context
from tests.conftest import BOOKINGS, CLINICS, DOCTORS, PATIENT_CONTEXT, TREATMENTS


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


def test_no_match_still_grounds_full_roster(fake_chains):
    """Full-roster-always (not an empty-fallback): nothing matched → the whole
corpus grounds the prompt in roster order, so the LLM can enumerate offerings
and deny the absent service honestly."""
    fakes = fake_chains("qa", qa_reply="I don't have that treatment in the catalog.")
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "do you offer aromatherapy massage?", uuid.uuid4().hex)

    assert result["retrieved"] == [*TREATMENTS, *DOCTORS, *CLINICS]
    prompt = fakes["qa"].prompts[-1]
    for row_id in ("[T001]", "[T005]", "[D101]", "[D104]", "[C001]", "[C002]"):
        assert row_id in prompt
    assert result["reply"] == "I don't have that treatment in the catalog."


def test_catalog_unreachable_is_readable_without_llm(fake_chains, catalog_fakes):
    fakes = fake_chains("qa", qa_reply="must not be used")
    catalog_fakes(catalog_error=RuntimeError("backend unreachable at http://localhost:8000: boom"))
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "what treatments do you have?", uuid.uuid4().hex)

    assert "couldn't reach the clinic catalog" in result["reply"]
    assert "boom" in result["reply"]
    assert fakes["qa"].prompts == []  # a broken data path never reaches the LLM


def test_retrieve_matches_clinic_directly_by_name_token(catalog_fakes):
    """Clinics are matched on the message itself (not only derived from doctors):
    token 'sunset' hits Sunset Wellness Center directly — ordered first, with the
    rest of the roster still grounded."""
    catalog_fakes()

    result = retrieve_catalog("how do I get to Sunset Wellness?")

    assert [c["clinic_id"] for c in result["clinics"]] == ["C002", "C001"]
    assert [t["treatment_id"] for t in result["treatments"]] == [t["treatment_id"] for t in TREATMENTS]
    assert [d["doctor_id"] for d in result["doctors"]] == [d["doctor_id"] for d in DOCTORS]


def test_retrieve_matches_doctor_via_language(catalog_fakes):
    """Generic doctor search spans languages_spoken: token 'spanish' → D101."""
    catalog_fakes()

    result = retrieve_catalog("is there a doctor who speaks Spanish?")

    assert [d["doctor_id"] for d in result["doctors"]] == ["D101", "D102", "D103", "D104"]  # D101 leads
    assert [c["clinic_id"] for c in result["clinics"]] == ["C001", "C002"]  # C001 derived from D101


def test_retrieve_matches_doctor_via_bio(catalog_fakes):
    """Generic doctor search spans bio: tokens 'sports'/'injuries' → D104."""
    catalog_fakes()

    result = retrieve_catalog("who treats sports injuries?")

    assert result["doctors"][0]["doctor_id"] == "D104"
    assert [d["doctor_id"] for d in result["doctors"]] == ["D104", "D101", "D102", "D103"]


def test_treatment_category_bridges_to_doctor_via_bio(catalog_fakes):
    """T001's 'Preventative Care' category bridges to D101 through its bio — the
    specialty-only bridge found nothing here (no doctor carries that specialty)."""
    catalog_fakes()

    result = retrieve_catalog("just a routine checkup please")

    assert result["treatments"][0]["treatment_id"] == "T001"
    assert [t["treatment_id"] for t in result["treatments"]] == [t["treatment_id"] for t in TREATMENTS]
    assert result["doctors"][0]["doctor_id"] == "D101"  # bridge-only: no direct match
    assert result["clinics"][0]["clinic_id"] == "C001"


def test_partial_match_still_grounds_every_roster_row(catalog_fakes):
    """A subset match must not hide unmatched rows: comparison and enumeration
    questions need rows the message words never matched, so every roster row
    rides along with the matches leading the order."""
    catalog_fakes()

    result = retrieve_catalog("who should I see about my knee pain?")

    assert result["treatments"][0]["treatment_id"] == "T005"  # the match leads
    assert result["doctors"][0]["doctor_id"] == "D104"
    assert [t["treatment_id"] for t in result["treatments"]] == ["T005", "T001", "T002", "T003", "T004"]
    assert [d["doctor_id"] for d in result["doctors"]] == ["D104", "D101", "D102", "D103"]
    assert [c["clinic_id"] for c in result["clinics"]] == ["C001", "C002"]


def test_render_catalog_carries_cancellation_and_emergency():
    rendered = render_catalog([], [], CLINICS)

    assert "cancellation: 24 hours" in rendered
    assert "emergency: Dial 911." in rendered


def test_render_patient_context_carries_medication_notes_doctor_name():
    rendered = render_patient_context(PATIENT_CONTEXT)

    assert "(Dr. Sarah Jenkins)" in rendered
    assert "medication: Multivitamins" in rendered
    assert "notes: Blood pressure normal." in rendered

    # rows predating the doctor_name join render the doctor_id fallback, and omit
    # absent medication/notes instead of printing nulls
    bare = {k: v for k, v in PATIENT_CONTEXT["treatment_history"][0].items() if k not in ("doctor_name", "prescribed_medication", "doctor_notes")}
    no_optional = render_patient_context({**PATIENT_CONTEXT, "treatment_history": [bare]})

    assert "(D101)" in no_optional
    assert "medication:" not in no_optional and "notes:" not in no_optional


def test_classifier_prompt_covers_patient_record_questions(fake_chains):
    """Own-record questions (allergies, history, profile) must stay in the qa
    intent bucket — otherwise they fall through to general small talk."""
    fakes = fake_chains("qa")
    graph = build_clinic_graph(InMemorySaver())

    _invoke(graph, "hello", uuid.uuid4().hex)

    prompt = fakes["classifier"].prompts[-1]
    assert "the patient's own record" in prompt
    assert "allergies" in prompt


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


def test_cancel_request_refused_deterministically(fake_chains):
    """Fix-A regression: a cancel request must never reach the free-text bookings
    LLM (it improvised "I've noted your request to cancel"); the refusal cites the
    clinics behind the patient's own bookings, with phone + policy verbatim."""
    fakes = fake_chains("check_bookings", bookings_reply="must not be used")
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "Please cancel my booking on November 5", uuid.uuid4().hex)

    assert "can't cancel or reschedule" in result["reply"]
    assert "+1-555-019-2831" in result["reply"]  # Metro Care phone (both seed bookings are C001)
    assert "24 hours" in result["reply"]  # cancellation policy verbatim from the catalog
    assert result["reply"].count("Metro Care") == 1  # two C001 bookings dedup to one clinic line
    assert "Sunset Wellness" not in result["reply"]  # clinics the patient has no booking at
    assert fakes["bookings"].prompts == []  # the refusal is code, not LLM output


def test_reschedule_request_refused_too(fake_chains):
    fakes = fake_chains("check_bookings", bookings_reply="must not be used")
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "can we reschedule my November 15 appointment?", uuid.uuid4().hex)

    assert "can't cancel or reschedule" in result["reply"]
    assert fakes["bookings"].prompts == []


def test_cancel_with_no_bookings_keeps_empty_answer(fake_chains, catalog_fakes):
    """Nothing to cancel: the empty-list answer wins over the refusal."""
    fakes = fake_chains("check_bookings", bookings_reply="must not be used")
    catalog_fakes(bookings=[])
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "cancel my appointment please", uuid.uuid4().hex)

    assert result["reply"] == "You have no bookings yet. Would you like to book an appointment?"
    assert fakes["bookings"].prompts == []


def test_cancel_refusal_survives_clinic_read_failure(fake_chains, catalog_fakes):
    """The cancel path's extra clinic read fails readable (module pattern), not as a 500."""
    fakes = fake_chains("check_bookings", bookings_reply="must not be used")
    catalog_fakes(catalog_error=RuntimeError("backend GET /api/clinics failed: 500 boom"))
    graph = build_clinic_graph(InMemorySaver())

    result = _invoke(graph, "cancel my appointment please", uuid.uuid4().hex)

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
