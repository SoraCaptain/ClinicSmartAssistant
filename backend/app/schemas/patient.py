"""GET /api/patients/{id}/context payload — injected into every graph run (P8)."""

from pydantic import BaseModel

from app.schemas.booking import BookingJoined
from app.schemas.catalog import HistoryOut, PatientProfileOut


class PatientContextOut(BaseModel):
    profile: PatientProfileOut
    treatment_history: list[HistoryOut]
    upcoming_bookings: list[BookingJoined]
