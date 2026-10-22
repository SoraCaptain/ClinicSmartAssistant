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


def test_chat_routes_book_appointment_stub(fake_chains):
    from app.agent.nodes import booking_flow as booking_flow_mod

    fake_chains("book_appointment")
    with TestClient(app) as client:
        resp = client.post(
            "/chat",
            json={"session_id": uuid.uuid4().hex, "message": "book a massage please"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "book_appointment"
    assert body["reply"] == booking_flow_mod.REPLY


def test_chat_rejects_empty_message():
    with TestClient(app) as client:
        resp = client.post("/chat", json={"session_id": "s1", "message": ""})
    assert resp.status_code == 422


def test_chat_without_api_key_fails_fast(monkeypatch):
    """No key + real (unpatched) chains → loud RuntimeError, never a canned reply."""
    monkeypatch.setattr("app.core.config.settings.openai_api_key", "")
    with TestClient(app) as client, pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        client.post("/chat", json={"session_id": uuid.uuid4().hex, "message": "hi"})
