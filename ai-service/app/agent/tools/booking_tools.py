"""Booking REST tools. get_my_bookings lands with its consumer (slice 4)."""

from app.agent.tools.client import _post


def create_booking(
    patient_id: str,
    doctor_id: str,
    treatment_id: str,
    booking_date: str,
    booking_time: str,
    notes: str | None = None,
) -> dict:
    """POST /api/bookings → persisted booking (flat BookingOut dict). Raises
    RuntimeError with the backend's status/body on failure (422 validation, etc.)."""
    return _post(
        "/api/bookings",
        {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "treatment_id": treatment_id,
            "booking_date": booking_date,
            "booking_time": booking_time,
            "notes": notes,
        },
    )
