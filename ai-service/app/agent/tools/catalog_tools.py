"""Catalog reads (DESIGN §5.3–5.4). Plain functions: nodes call them deterministically —
the @tool form earns its keep only when an LLM loop or Langfuse spans appear (slice 6)."""

from app.agent.tools.client import _get


def search_doctors(specialty: str | None = None, search: str | None = None) -> list[dict]:
    """Doctors, optionally filtered by specialty contains-match and/or a generic
    search over name/specialty/languages/bio (server-side)."""
    params = {k: v for k, v in (("specialty", specialty), ("search", search)) if v}
    return _get("/api/doctors", params=params or None)


def search_treatments(search: str | None = None) -> list[dict]:
    """Treatments matching `search` against name/category/instructions (server-side)."""
    params = {"search": search} if search else None
    return _get("/api/treatments", params=params)


def get_clinics(clinic_id: str | None = None, search: str | None = None) -> list[dict]:
    """Clinics, optionally narrowed to one clinic_id and/or matched by a generic
    search over name/address/hours/policies (server-side)."""
    params = {k: v for k, v in (("clinic_id", clinic_id), ("search", search)) if v}
    return _get("/api/clinics", params=params or None)
