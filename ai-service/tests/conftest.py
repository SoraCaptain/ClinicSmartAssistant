"""Shared fakes: scripted chains patched at their consumer modules (LedgerMind lesson —
patching the underlying LLM factory leaves stale chains). Booking fakes patch the
tool symbols at the booking_flow module for the same reason."""

import pytest
from langchain_core.messages import AIMessage

from app.agent.nodes.booking_flow import ExtractedSlots
from app.agent.nodes.classifier import ClassifierOutput

# Canned catalog mirroring the seed rows (fields the booking flow reads)
DOCTORS = [
    {"doctor_id": "D101", "clinic_id": "C001", "full_name": "Dr. Sarah Jenkins", "specialty": "General Practice", "consultation_fee_usd": "150.00"},
    {"doctor_id": "D102", "clinic_id": "C001", "full_name": "Dr. Michael Chang", "specialty": "Pediatrics", "consultation_fee_usd": "180.00"},
    {"doctor_id": "D103", "clinic_id": "C002", "full_name": "Dr. Elena Rostova", "specialty": "Dermatology", "consultation_fee_usd": "220.00"},
    {"doctor_id": "D104", "clinic_id": "C001", "full_name": "Dr. James Wilson", "specialty": "Orthopedics", "consultation_fee_usd": "250.00"},
]
TREATMENTS = [
    {"treatment_id": "T001", "treatment_name": "General Health Checkup", "category": "Preventative Care", "duration_minutes": 30, "price_usd": "150.00"},
    {"treatment_id": "T005", "treatment_name": "Joint & Pain Consultation", "category": "Orthopedics", "duration_minutes": 45, "price_usd": "230.00"},
]


def _normalize_script(script) -> list[tuple[str, bool | None]]:
    """Accept "intent", ["i1", "i2"] or [("i", True), ("i", None)]; last entry repeats."""
    if isinstance(script, str):
        script = [script]
    out = []
    for item in script:
        out.append((item, None) if isinstance(item, str) else tuple(item))
    return out


class FakeClassifierChain:
    def __init__(self, script):
        self.script = _normalize_script(script)
        self.prompts: list[str] = []

    def invoke(self, prompt: str, config=None) -> ClassifierOutput:
        self.prompts.append(prompt)
        intent, user_confirms = self.script[min(len(self.prompts) - 1, len(self.script) - 1)]
        return ClassifierOutput(intent=intent, user_confirms=user_confirms)


class FakeGeneralChain:
    def __init__(self, reply: str):
        self.reply = reply

    def invoke(self, prompt: str, config=None) -> AIMessage:
        return AIMessage(content=self.reply)


class FakeSlotChain:
    """Scripted extraction results, one per invoke; the last repeats."""

    def __init__(self, results: list[dict]):
        self.results = [ExtractedSlots(**r) for r in results]
        self.prompts: list[str] = []

    def invoke(self, prompt: str, config=None) -> ExtractedSlots:
        self.prompts.append(prompt)
        return self.results[min(len(self.prompts) - 1, len(self.results) - 1)]


class FakeTool:
    """Records every call; raises `error` (or pops `errors` per call) before returning `result`."""

    def __init__(self, result=None, error: Exception | None = None, errors: list | None = None):
        self.result = result
        self.error = error
        self.errors = list(errors or [])
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture()
def fake_chains(monkeypatch):
    """install(script, general_reply=...) → patches classifier + general chains,
    returns the installed fakes (classifier records every prompt it sees). The
    script is an intent, a list of intents, or (intent, user_confirms) tuples."""

    def install(script, general_reply: str = "General reply."):
        classifier = FakeClassifierChain(script)
        general = FakeGeneralChain(general_reply)
        monkeypatch.setattr(
            "app.agent.nodes.classifier.get_classifier_chain", lambda: classifier
        )
        monkeypatch.setattr("app.agent.nodes.general.get_general_chain", lambda: general)
        return {"classifier": classifier, "general": general}

    return install


@pytest.fixture()
def booking_fakes(monkeypatch):
    """install(slots=[...], create_result=..., create_errors=[...]) → patches the
    slot extractor and the tool symbols at the booking_flow module; returns the
    fakes (slot chain records prompts; create tool records calls)."""

    def install(
        slots: list[dict],
        create_result: dict | None = None,
        create_errors: list | None = None,
    ):
        slot_chain = FakeSlotChain(slots)
        create = FakeTool(
            result=create_result
            if create_result is not None
            else {"booking_id": "B9f2a1", "status": "Confirmed", "source": "chatbot"},
            errors=create_errors,
        )

        def fake_search_doctors(specialty: str | None = None) -> list[dict]:
            if specialty:
                needle = specialty.casefold()
                return [d for d in DOCTORS if needle in d["specialty"].casefold()]
            return list(DOCTORS)

        def fake_search_treatments(search: str | None = None) -> list[dict]:
            # mirrors the backend's case-insensitive contains-match on name/category
            if search is None:
                return list(TREATMENTS)
            needle = search.casefold()
            return [
                t
                for t in TREATMENTS
                if needle in t["treatment_name"].casefold() or needle in t["category"].casefold()
            ]

        monkeypatch.setattr(
            "app.agent.nodes.booking_flow.get_slot_extractor", lambda: slot_chain
        )
        monkeypatch.setattr("app.agent.nodes.booking_flow.search_doctors", fake_search_doctors)
        monkeypatch.setattr("app.agent.nodes.booking_flow.search_treatments", fake_search_treatments)
        monkeypatch.setattr("app.agent.nodes.booking_flow.create_booking", create)
        return {"slots": slot_chain, "create": create}

    return install
