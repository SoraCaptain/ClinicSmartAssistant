"""POST /api/summarize/transcript proxy contract: passthrough, P7 (ai down →
503), upstream errors → 502, empty transcript → 422."""

import httpx

SUMMARY_BODY = {
    "chief_complaint": "Left knee pain for two weeks.",
    "diagnosis": "Patellofemoral pain syndrome.",
    "medication": "Ibuprofen 400mg twice daily for 5 days.",
    "doctor_instructions": "Avoid running for one week.",
}


def test_summarize_proxies_to_ai_service(client, monkeypatch):
    async def fake_summarize(payload):
        assert payload == {"transcript": "Patient: knee pain. Doctor: rest."}
        return dict(SUMMARY_BODY)

    monkeypatch.setattr("app.routers.summarize.ai_client.summarize", fake_summarize)
    resp = client.post("/api/summarize/transcript", json={"transcript": "Patient: knee pain. Doctor: rest."})
    assert resp.status_code == 200
    assert resp.json() == SUMMARY_BODY


def test_summarize_ai_service_down_returns_503(client, monkeypatch):
    """P7 pattern: refused connect (port 1, nothing listens) → 503."""
    monkeypatch.setattr("app.core.config.settings.ai_service_url", "http://127.0.0.1:1")
    resp = client.post("/api/summarize/transcript", json={"transcript": "anything"})
    assert resp.status_code == 503
    assert resp.json()["detail"].startswith("AI service unavailable")


def test_summarize_ai_service_error_returns_502(client, monkeypatch):
    def fake_summarize(payload):
        request = httpx.Request("POST", "http://ai/summarize")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    monkeypatch.setattr("app.routers.summarize.ai_client.summarize", fake_summarize)
    resp = client.post("/api/summarize/transcript", json={"transcript": "anything"})
    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("AI service returned an error")


def test_summarize_ai_service_malformed_body_returns_502(client, monkeypatch):
    async def fake_summarize(payload):
        return {"unexpected": True}

    monkeypatch.setattr("app.routers.summarize.ai_client.summarize", fake_summarize)
    resp = client.post("/api/summarize/transcript", json={"transcript": "anything"})
    assert resp.status_code == 502


def test_summarize_rejects_empty_transcript(client):
    resp = client.post("/api/summarize/transcript", json={"transcript": ""})
    assert resp.status_code == 422
