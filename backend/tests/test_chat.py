"""POST /api/chat proxy contract: passthrough, P7 (ai down → 503), upstream errors → 502."""

import httpx


def test_chat_proxies_to_ai_service(client, monkeypatch):
    async def fake_chat(payload):
        assert payload == {"session_id": "s1", "message": "hi", "patient_id": None}
        return {"reply": "Hello!", "intent": "general", "booking_created": None, "session_id": "s1"}

    monkeypatch.setattr("app.routers.chat.ai_client.chat", fake_chat)
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "Hello!",
        "intent": "general",
        "booking_created": None,
        "session_id": "s1",
    }


def test_chat_ai_service_down_returns_503(client, monkeypatch):
    """P7: refused connect (port 1, nothing listens) → 503 with a clear detail."""
    monkeypatch.setattr("app.core.config.settings.ai_service_url", "http://127.0.0.1:1")
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 503
    assert resp.json()["detail"].startswith("AI service unavailable")


def test_chat_ai_service_error_returns_502(client, monkeypatch):
    def fake_chat(payload):
        request = httpx.Request("POST", "http://ai/chat")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    monkeypatch.setattr("app.routers.chat.ai_client.chat", fake_chat)
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("AI service returned an error")


def test_chat_ai_service_malformed_body_returns_502(client, monkeypatch):
    async def fake_chat(payload):
        return {"unexpected": True}

    monkeypatch.setattr("app.routers.chat.ai_client.chat", fake_chat)
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 502


def test_chat_ai_service_missing_fields_returns_502(client, monkeypatch):
    """ai-service 200 with a body missing required fields (no intent) → 502."""

    async def fake_chat(payload):
        return {"reply": "x", "session_id": "s1"}

    monkeypatch.setattr("app.routers.chat.ai_client.chat", fake_chat)
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 502


def test_chat_rejects_empty_message(client):
    resp = client.post("/api/chat", json={"session_id": "s1", "message": ""})
    assert resp.status_code == 422
