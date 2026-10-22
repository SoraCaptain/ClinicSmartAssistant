"""QA node (DESIGN §5.3): retrieval over the tiny catalog is deterministic —
full-string contains-match first, token fallback second ('knee pain' → token
'pain' → T005; embeddings are the §5.3 upgrade path). Retrieved rows plus patient
context (P8) ground a cited LLM answer; tool failures surface as readable text."""

import re

from app.agent.llm import get_chat_model
from app.agent.prompts import (
    QA_SYSTEM,
    QA_USER,
    render_catalog,
    render_history,
    render_patient_context,
)
from app.agent.state import ClinicGraphState
from app.agent.tools.catalog_tools import get_clinics, search_doctors, search_treatments


def get_qa_chain():
    """Built per call so tests can patch this symbol at this module."""
    return get_chat_model()


def _tokens(query: str) -> list[str]:
    # >=4 chars drops grammar noise ("have", "with"); short-hand like "flu" is the cost
    return [t for t in re.split(r"\W+", query.lower()) if len(t) >= 4]


def _match_all(search, query: str, id_key: str) -> list[dict]:
    """Full-string contains-match first; otherwise the deduped union of per-token
    matches in first-seen order (the full phrase 'knee pain' matches no row, but
    its token 'pain' does)."""
    rows = search(query)
    if rows:
        return rows
    matched: list[dict] = []
    seen: set[str] = set()
    for token in _tokens(query):
        for row in search(token):
            if row[id_key] not in seen:
                seen.add(row[id_key])
                matched.append(row)
    return matched


def retrieve_catalog(message: str) -> dict:
    """Treatments matched on the message; doctors matched by generic search
    (name/specialty/languages/bio) directly or via a matched treatment's category
    (T001 'Preventative Care' → D101 via bio); clinics matched directly on the
    message, unioned with the sites the retrieved doctors practice at (dedup by
    clinic_id). When nothing matches at all, the full catalog is returned so the
    LLM can enumerate it and honestly deny absent services — a designed retrieval
    strategy for an 11-row corpus, not an error path."""
    treatments = _match_all(search_treatments, message, "treatment_id")
    doctors = _match_all(lambda q: search_doctors(search=q), message, "doctor_id")
    clinics = _match_all(lambda q: get_clinics(search=q), message, "clinic_id")
    if treatments:
        by_id = {d["doctor_id"]: d for d in doctors}
        for treatment in treatments:
            for doctor in search_doctors(search=treatment["category"]):
                by_id.setdefault(doctor["doctor_id"], doctor)
        doctors = list(by_id.values())
    if doctors:
        clinic_ids = {d["clinic_id"] for d in doctors}
        by_id = {c["clinic_id"]: c for c in clinics}
        for clinic in get_clinics():
            if clinic["clinic_id"] in clinic_ids:
                by_id.setdefault(clinic["clinic_id"], clinic)
        clinics = list(by_id.values())
    if not (treatments or doctors or clinics):
        treatments = search_treatments()
        doctors = search_doctors()
        clinics = get_clinics()
    return {"treatments": treatments, "doctors": doctors, "clinics": clinics}


def qa_answer(state: ClinicGraphState) -> dict:
    try:
        catalog = retrieve_catalog(state["user_message"])
    except RuntimeError as e:
        # readable text over a broken turn (§5.4) — same shape as execute_booking
        return {"reply": f"I couldn't reach the clinic catalog: {e} Please try again in a moment."}
    prompt = (
        f"{QA_SYSTEM}\n\n"
        + QA_USER.format(
            history=render_history(state.get("messages", [])),
            patient_context=render_patient_context(state.get("patient_context")),
            catalog=render_catalog(**catalog),
            message=state["user_message"],
        )
    )
    return {
        "reply": get_qa_chain().invoke(prompt).content,
        "retrieved": [*catalog["treatments"], *catalog["doctors"], *catalog["clinics"]],
    }
