"""Booking request/response contracts (§6: FK existence + format validation, no conflict check)."""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict


class BookingCreate(BaseModel):
    patient_id: str
    doctor_id: str
    treatment_id: str
    booking_date: date  # YYYY-MM-DD, enforced by pydantic
    booking_time: time  # HH:MM[:SS], enforced by pydantic
    notes: str | None = None


class BookingOut(BaseModel):
    """Persisted booking as returned by POST (flat; joined fields come via GET)."""

    model_config = ConfigDict(from_attributes=True)

    booking_id: str
    patient_id: str
    doctor_id: str
    treatment_id: str
    booking_date: date
    booking_time: time
    status: str
    notes: str | None
    created_at: datetime
    source: str


class BookingJoined(BaseModel):
    """Joined read model for the UI and the get_my_bookings tool (P5)."""

    model_config = ConfigDict(from_attributes=True)

    booking_id: str
    patient_id: str
    doctor_id: str
    treatment_id: str
    booking_date: date
    booking_time: time
    status: str
    notes: str | None
    created_at: datetime
    source: str
    doctor_name: str
    doctor_specialty: str
    treatment_name: str
    clinic_id: str
    clinic_name: str
