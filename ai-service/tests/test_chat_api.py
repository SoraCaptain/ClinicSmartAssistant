"""POST /chat and GET /health with scripted chains (no network, no API key)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health_ok():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_general_roundtrip(fake_chains):
    fake_chains("general", general_reply="Hello!")
    session_id = uuid.uuid4().hex
    with TestClient(app) as client:
        resp = client.post("/chat", json={"session_id": session_id, "message": "hi"})
    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "Hello!",
        "intent": "general",
        "booking_created": None,
        "session_id": session_id,
    }


def test_chat_booking_flow_returns_then_clears_booking_created(fake_chains, booking_fakes):
    """Full booking through POST /chat: confirmation turn returns booking_created;
    the next (non-booking) turn must not re-emit it."""
    fake_chains(["book_appointment", ("book_appointment", True), "general"])
    booking_fakes(
        slots=[
            {"treatment": "joint pain consultation", "doctor": "Dr. Wilson",
             "booking_date": "2026-11-21", "booking_time": "09:30"},
            {}, {},
        ],
        create_result={"booking_id": "B7x", "status": "Confirmed"},
    )
    session_id = uuid.uuid4().hex
    with TestClient(app) as client:
        r1 = client.post("/chat", json={"session_id": session_id, "message": "book joint pain with Dr. Wilson on the 21st at 9:30"})
        r2 = client.post("/chat", json={"session_id": session_id, "message": "yes"})
        r3 = client.post("/chat", json={"session_id": session_id, "message": "thanks!"})

    assert r1.json()["booking_created"] is None  # confirmation turn: summary, no booking yet
    assert r2.json()["booking_created"] == {"booking_id": "B7x", "status": "Confirmed"}
    assert r3.json()["booking_created"] is None  # per-turn reset
    assert r3.json()["intent"] == "general"


def test_chat_rejects_empty_message():
    with TestClient(app) as client:
        resp = client.post("/chat", json={"session_id": "s1", "message": ""})
    assert resp.status_code == 422


def test_chat_fetches_patient_context_per_turn_and_injects_it(fake_chains):
    """P8: every /chat fetches context for the resolved patient (default P001) and
    the qa prompt carries it (allergies)."""
    fakes = fake_chains("qa", qa_reply="Cited (T005).")
    with TestClient(app) as client:
        resp = client.post(
            "/chat", json={"session_id": uuid.uuid4().hex, "message": "knee pain advice"}
        )

    assert resp.status_code == 200
    assert fakes["context"].calls == [{"patient_id": "P001"}]
    assert "Penicillin, Peanuts" in fakes["qa"].prompts[-1]


def test_chat_explicit_patient_id_drives_context_fetch(fake_chains):
    fakes = fake_chains("qa", qa_reply="ok")
    with TestClient(app) as client:
        resp = client.post(
            "/chat",
            json={"session_id": uuid.uuid4().hex, "message": "hello there", "patient_id": "P002"},
        )
    assert resp.status_code == 200
    assert fakes["context"].calls == [{"patient_id": "P002"}]


def test_chat_context_fetch_failure_fails_loud(fake_chains, catalog_fakes):
    """A failing context fetch breaks the turn loudly (honest P8 path) — never a
    canned reply or a context-less answer."""
    fake_chains("general", general_reply="Hi!")
    catalog_fakes(context_error=RuntimeError("backend unreachable at http://localhost:8000: refused"))
    with TestClient(app) as client, pytest.raises(RuntimeError, match="backend unreachable"):
        client.post("/chat", json={"session_id": uuid.uuid4().hex, "message": "hi"})


def test_chat_without_api_key_fails_fast(monkeypatch, catalog_fakes):
    """No key + real (unpatched) chains → loud RuntimeError, never a canned reply.
    The P8 context fetch is faked so the key check is what fires."""
    monkeypatch.setattr("app.core.config.settings.openai_api_key", "")
    catalog_fakes()
    with TestClient(app) as client, pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        client.post("/chat", json={"session_id": uuid.uuid4().hex, "message": "hi"})
