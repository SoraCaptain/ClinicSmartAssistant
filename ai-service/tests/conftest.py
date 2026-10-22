"""Shared fakes: scripted chains patched at their consumer modules (LedgerMind lesson —
patching the underlying LLM factory leaves stale chains). fake_chains makes EVERY node
network-safe (any scripted intent can route anywhere); catalog_fakes overrides the
default catalog/patient/booking tool data — call it AFTER fake_chains so its patches
win. Booking fakes patch the tool symbols at the booking_flow module for the same reason."""

from contextlib import contextmanager

import langfuse
import langfuse.langchain
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage

from app.agent.nodes.booking_flow import ExtractedSlots
from app.agent.nodes.classifier import ClassifierOutput
from app.agent.observability import tracing
from app.core.config import settings

# Canned catalog mirroring the seed rows (fields the nodes read)
DOCTORS = [
    {"doctor_id": "D101", "clinic_id": "C001", "full_name": "Dr. Sarah Jenkins", "specialty": "General Practice", "languages_spoken": "English, Spanish", "consultation_fee_usd": "150.00", "bio": "Board-certified family physician with over 12 years of experience in preventative care and chronic disease management."},
    {"doctor_id": "D102", "clinic_id": "C001", "full_name": "Dr. Michael Chang", "specialty": "Pediatrics", "languages_spoken": "English, Mandarin", "consultation_fee_usd": "180.00", "bio": "Pediatric specialist."},
    {"doctor_id": "D103", "clinic_id": "C002", "full_name": "Dr. Elena Rostova", "specialty": "Dermatology", "languages_spoken": "English, Russian", "consultation_fee_usd": "220.00", "bio": "Dermatologist specializing in eczema and acne treatments."},
    {"doctor_id": "D104", "clinic_id": "C001", "full_name": "Dr. James Wilson", "specialty": "Orthopedics", "languages_spoken": "English", "consultation_fee_usd": "250.00", "bio": "Orthopedic specialist focusing on joint pain and sports injuries."},
]
TREATMENTS = [
    {"treatment_id": "T001", "treatment_name": "General Health Checkup", "category": "Preventative Care", "duration_minutes": 30, "price_usd": "150.00", "pre_treatment_instructions": "Fast for at least 8 hours prior to your visit if blood tests are scheduled."},
    {"treatment_id": "T002", "treatment_name": "Pediatric Vaccination", "category": "Pediatrics", "duration_minutes": 15, "price_usd": "80.00", "pre_treatment_instructions": "Please bring the child's official vaccination record booklet."},
    {"treatment_id": "T003", "treatment_name": "Dermatology Consultation", "category": "Dermatology", "duration_minutes": 30, "price_usd": "200.00", "pre_treatment_instructions": "Ensure skin is clean and free of makeup or heavy lotions on the area being evaluated."},
    {"treatment_id": "T004", "treatment_name": "Flu Shot Injection", "category": "Immunization", "duration_minutes": 15, "price_usd": "40.00", "pre_treatment_instructions": "No prior preparation required. Inform doctor if you currently have a fever."},
    {"treatment_id": "T005", "treatment_name": "Joint & Pain Consultation", "category": "Orthopedics", "duration_minutes": 45, "price_usd": "230.00", "pre_treatment_instructions": "Wear loose-fitting clothing."},
]
CLINICS = [
    {"clinic_id": "C001", "clinic_name": "Metro Care Health Clinic", "address": "123 Medical Center Way, New York", "phone": "+1-555-019-2831", "operating_hours": "Mon-Fri: 8:00 AM - 6:00 PM", "cancellation_policy": "24 hours", "emergency_instructions": "Dial 911."},
    {"clinic_id": "C002", "clinic_name": "Sunset Wellness Center", "address": "456 Ocean Ave, Santa Monica", "phone": "+1-555-014-9922", "operating_hours": "Mon-Fri: 9:00 AM - 5:00 PM", "cancellation_policy": "12 hours", "emergency_instructions": "Call the hotline."},
]
# Joined booking rows (BookingJoined shape) mirroring the seed: P001 owns both
BOOKINGS = [
    {"booking_id": "B1001", "patient_id": "P001", "doctor_id": "D101", "treatment_id": "T001",
     "booking_date": "2026-11-05", "booking_time": "09:00:00", "status": "Confirmed",
     "notes": "Routine annual checkup.", "created_at": "2026-10-01T10:00:00", "source": "seed",
     "doctor_name": "Dr. Sarah Jenkins", "doctor_specialty": "General Practice",
     "treatment_name": "General Health Checkup", "clinic_id": "C001", "clinic_name": "Metro Care Health Clinic"},
    {"booking_id": "B1004", "patient_id": "P001", "doctor_id": "D104", "treatment_id": "T005",
     "booking_date": "2026-11-15", "booking_time": "11:00:00", "status": "Confirmed",
     "notes": "Follow up on knee pain.", "created_at": "2026-10-01T10:00:00", "source": "seed",
     "doctor_name": "Dr. James Wilson", "doctor_specialty": "Orthopedics",
     "treatment_name": "Joint & Pain Consultation", "clinic_id": "C001", "clinic_name": "Metro Care Health Clinic"},
]
# PatientContextOut shape for P001 (the P8 payload)
PATIENT_CONTEXT = {
    "profile": {
        "patient_id": "P001", "first_name": "John", "last_name": "Doe", "dob": "1988-05-14",
        "gender": "Male", "phone": "+1-555-018-3311", "email": "john.doe@example.com",
        "known_allergies": "Penicillin, Peanuts", "emergency_contact": "Jane Doe (Spouse) - +1-555-018-3312",
    },
    "treatment_history": [
        {"record_id": "H9002", "patient_id": "P001", "doctor_id": "D101", "doctor_name": "Dr. Sarah Jenkins", "visit_date": "2026-04-12",
         "chief_complaint": "Annual routine health checkup.", "diagnosis": "Healthy / Normal Range",
         "prescribed_medication": "Multivitamins", "doctor_notes": "Blood pressure normal."},
    ],
    "upcoming_bookings": BOOKINGS,
}


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


class FakeChatChain:
    """Scripted plain-chat chain; records every prompt it sees."""

    def __init__(self, reply: str):
        self.reply = reply
        self.prompts: list[str] = []

    def invoke(self, prompt: str, config=None) -> AIMessage:
        self.prompts.append(prompt)
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
def catalog_fakes(monkeypatch):
    """install(...) → patches the catalog/patient/booking tool symbols at their
    consumer modules (qa, bookings_query, runtime) with seed-shaped data. Mirrors
    the backend's contains-match (treatments: name/category/instructions; doctors:
    specialty + name/languages/bio via search; clinics: id + name/address/hours/policies
    via search). Returns the FakeTool handles for call assertions."""

    def install(
        treatments: list = TREATMENTS,
        doctors: list = DOCTORS,
        clinics: list = CLINICS,
        patient_context: dict | None = PATIENT_CONTEXT,
        bookings: list = BOOKINGS,
        catalog_error: Exception | None = None,
        bookings_error: Exception | None = None,
        context_error: Exception | None = None,
    ):
        def fake_search_doctors(specialty: str | None = None, search: str | None = None) -> list[dict]:
            # mirrors the backend: specialty filter OR-folded with a generic search
            # over name/specialty/languages/bio
            if catalog_error:
                raise catalog_error
            rows = doctors
            if specialty:
                needle = specialty.casefold()
                rows = [d for d in rows if needle in d["specialty"].casefold()]
            if search:
                needle = search.casefold()
                rows = [
                    d
                    for d in rows
                    if any(needle in str(d[f]).casefold() for f in ("full_name", "specialty", "languages_spoken", "bio"))
                ]
            return list(rows)

        def fake_search_treatments(search: str | None = None) -> list[dict]:
            if catalog_error:
                raise catalog_error
            if search is None:
                return list(treatments)
            needle = search.casefold()
            return [
                t
                for t in treatments
                if needle in t["treatment_name"].casefold()
                or needle in t["category"].casefold()
                or needle in t["pre_treatment_instructions"].casefold()
            ]

        def fake_get_clinics(clinic_id: str | None = None, search: str | None = None) -> list[dict]:
            # mirrors the backend: clinic_id filter OR-folded with a generic search
            # over name/address/hours/cancellation/emergency
            if catalog_error:
                raise catalog_error
            rows = clinics
            if clinic_id:
                rows = [c for c in rows if c["clinic_id"] == clinic_id]
            if search:
                needle = search.casefold()
                rows = [
                    c
                    for c in rows
                    if any(needle in str(c[f]).casefold() for f in ("clinic_name", "address", "operating_hours", "cancellation_policy", "emergency_instructions"))
                ]
            return list(rows)

        context_tool = FakeTool(result=patient_context, error=context_error)
        bookings_tool = FakeTool(result=bookings, error=bookings_error)
        monkeypatch.setattr("app.agent.nodes.qa.search_doctors", fake_search_doctors)
        monkeypatch.setattr("app.agent.nodes.qa.search_treatments", fake_search_treatments)
        monkeypatch.setattr("app.agent.nodes.qa.get_clinics", fake_get_clinics)
        monkeypatch.setattr("app.agent.nodes.bookings_query.get_my_bookings", bookings_tool)
        monkeypatch.setattr("app.runtime.get_patient_context", context_tool)
        return {"context": context_tool, "bookings_tool": bookings_tool}

    return install


@pytest.fixture()
def fake_chains(monkeypatch, catalog_fakes):
    """install(script, general_reply=..., qa_reply=..., bookings_reply=...) → patches
    all four node chains AND default tool data (every scripted intent is network-safe),
    returns the installed fakes (chains record prompts; tool handles under
    context/bookings_tool). The script is an intent, a list of intents, or
    (intent, user_confirms) tuples. Override tools by calling catalog_fakes afterwards."""

    def install(
        script,
        general_reply: str = "General reply.",
        qa_reply: str = "QA reply.",
        bookings_reply: str = "Bookings reply.",
    ):
        classifier = FakeClassifierChain(script)
        chains = {
            "classifier": classifier,
            "general": FakeChatChain(general_reply),
            "qa": FakeChatChain(qa_reply),
            "bookings": FakeChatChain(bookings_reply),
        }
        monkeypatch.setattr(
            "app.agent.nodes.classifier.get_classifier_chain", lambda: classifier
        )
        monkeypatch.setattr(
            "app.agent.nodes.general.get_general_chain", lambda: chains["general"]
        )
        monkeypatch.setattr("app.agent.nodes.qa.get_qa_chain", lambda: chains["qa"])
        monkeypatch.setattr(
            "app.agent.nodes.bookings_query.get_bookings_chain", lambda: chains["bookings"]
        )
        return {**chains, **catalog_fakes()}

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

        def fake_search_doctors(specialty: str | None = None, search: str | None = None) -> list[dict]:
            # mirrors the backend: specialty contains-filter AND-folded with a
            # generic search over name/specialty/languages/bio
            rows = DOCTORS
            if specialty:
                needle = specialty.casefold()
                rows = [d for d in rows if needle in d["specialty"].casefold()]
            if search:
                needle = search.casefold()
                rows = [
                    d
                    for d in rows
                    if any(needle in str(d[f]).casefold() for f in ("full_name", "specialty", "languages_spoken", "bio"))
                ]
            return list(rows)

        def fake_search_treatments(search: str | None = None) -> list[dict]:
            # mirrors the backend's case-insensitive contains-match on
            # name/category/instructions (resolution post-filters these to
            # identity fields — see _identity_rows in booking_flow)
            if search is None:
                return list(TREATMENTS)
            needle = search.casefold()
            return [
                t
                for t in TREATMENTS
                if needle in t["treatment_name"].casefold()
                or needle in t["category"].casefold()
                or needle in t["pre_treatment_instructions"].casefold()
            ]

        monkeypatch.setattr(
            "app.agent.nodes.booking_flow.get_slot_extractor", lambda: slot_chain
        )
        monkeypatch.setattr("app.agent.nodes.booking_flow.search_doctors", fake_search_doctors)
        monkeypatch.setattr("app.agent.nodes.booking_flow.search_treatments", fake_search_treatments)
        monkeypatch.setattr("app.agent.nodes.booking_flow.create_booking", create)
        return {"slots": slot_chain, "create": create}

    return install


class FakeRootObservation:
    """Root observation stand-in; only its context-manager role matters now
    (tags ride propagate_attributes instead — v4 has no Span.update(tags))."""

    def update(self, **kwargs):
        raise AssertionError("Span.update must not be used for tags (v4 drops them)")


class FakeClient:
    def __init__(self):
        self.root = FakeRootObservation()
        self.started = None
        self.shutdown_calls = 0

    def start_as_current_observation(self, *, as_type, name):
        self.started = (as_type, name)

        @contextmanager
        def cm():
            yield self.root

        return cm()

    def shutdown(self):
        self.shutdown_calls += 1


class FakeHandler(BaseCallbackHandler):
    """No-op stand-in for the Langfuse CallbackHandler (langchain calls its
    event methods during the run; BaseCallbackHandler provides no-ops)."""

    instances = []

    def __init__(self, *args, **kwargs):
        FakeHandler.instances.append(self)


@pytest.fixture()
def langfuse_fakes(monkeypatch):
    """Install fake langfuse surface + keys + fresh latches; returns handles.

    tracing.py imports lazily inside its functions, so patching the package
    attributes is enough — no real OTel provider is ever registered."""
    monkeypatch.setattr(tracing, "_client_ready", False)
    monkeypatch.setattr(tracing, "_client_dead", False)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(settings, "langfuse_host", "")

    client = FakeClient()
    propagated = {}
    constructor_kwargs = {}

    def fake_langfuse(**kwargs):
        constructor_kwargs.update(kwargs)
        return None

    @contextmanager
    def fake_propagate_attributes(**kwargs):
        propagated.update(kwargs)
        yield

    monkeypatch.setattr(langfuse, "Langfuse", fake_langfuse)
    monkeypatch.setattr(langfuse, "get_client", lambda: client)
    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate_attributes)
    monkeypatch.setattr(langfuse.langchain, "CallbackHandler", FakeHandler)
    FakeHandler.instances.clear()

    return {
        "client": client,
        "propagated": propagated,
        "constructor": constructor_kwargs,
    }
