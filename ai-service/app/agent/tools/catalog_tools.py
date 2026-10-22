"""Catalog reads for the booking flow (DESIGN §5.3–5.4). Plain functions: nodes call
them deterministically — the @tool form earns its keep only when an LLM loop or
Langfuse spans appear (slice 6). get_clinics lands with its consumer (slice 4)."""

from app.agent.tools.client import _get


def search_doctors(specialty: str | None = None) -> list[dict]:
    """Doctors, optionally filtered by case-insensitive specialty contains-match."""
    params = {"specialty": specialty} if specialty else None
    return _get("/api/doctors", params=params)


def search_treatments(search: str | None = None) -> list[dict]:
    """Treatments matching `search` against name/category/instructions (server-side)."""
    params = {"search": search} if search else None
    return _get("/api/treatments", params=params)
