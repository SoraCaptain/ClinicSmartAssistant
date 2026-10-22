"""POST /summarize: four clinical fields from a transcript (bonus slice); the
chain is faked at its consumer module; tracing rides the same fail-soft root."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.summarizer import MedicalSummary

SUMMARY = MedicalSummary(
    chief_complaint="Left knee pain for two weeks.",
    diagnosis="Patellofemoral pain syndrome.",
    medication="Ibuprofen 400mg twice daily for 5 days.",
    doctor_instructions="Avoid running for one week; return if swelling worsens.",
)


@pytest.fixture()
def summary_chain(monkeypatch):
    def install(result: MedicalSummary = SUMMARY):
        calls = []

        class FakeChain:
            async def ainvoke(self, prompt: str, config=None):
                calls.append({"prompt": prompt, "config": config})
                return result

        monkeypatch.setattr("app.summarizer.get_summary_chain", lambda: FakeChain())
        return calls

    return install


def test_summarize_returns_four_fields(summary_chain):
    calls = summary_chain()
    with TestClient(app) as client:
        resp = client.post("/summarize", json={"transcript": "Patient: my left knee hurts. Doctor: take ibuprofen."})
    assert resp.status_code == 200
    assert resp.json() == {
        "chief_complaint": "Left knee pain for two weeks.",
        "diagnosis": "Patellofemoral pain syndrome.",
        "medication": "Ibuprofen 400mg twice daily for 5 days.",
        "doctor_instructions": "Avoid running for one week; return if swelling worsens.",
    }
    assert "my left knee hurts" in calls[0]["prompt"]  # transcript carried into the call


def test_summarize_rejects_empty_transcript():
    with TestClient(app) as client:
        resp = client.post("/summarize", json={"transcript": ""})
    assert resp.status_code == 422


def test_summarize_traced_under_langfuse_root(summary_chain, langfuse_fakes):
    """P6 spirit: with keys present the call is wrapped in a named root and the
    callback handler rides the invoke config (tokens/cost)."""
    calls = summary_chain()
    with TestClient(app) as client:
        resp = client.post("/summarize", json={"transcript": "Doctor: how are you?"})
    assert resp.status_code == 200
    assert langfuse_fakes["client"].started == ("span", "clinic-summarize")
    assert calls[0]["config"]["callbacks"] is not None
