"""Patient context read (P8): profile + allergies + treatment history + upcoming
bookings, fetched over REST (P3) and injected into every graph run by the runtime."""

from app.agent.tools.client import _get


def get_patient_context(patient_id: str) -> dict:
    """GET /api/patients/{id}/context → PatientContextOut dict. Raises RuntimeError
    with the backend's status/body on failure (fail loud, no silent fallbacks)."""
    return _get(f"/api/patients/{patient_id}/context")
