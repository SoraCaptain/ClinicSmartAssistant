"""Booking flow nodes — slot extraction, confirm gate and create_booking land in slice 3
(DESIGN §5.2). Placeholder keeps the book_appointment route honest in the meantime."""

from app.agent.state import ClinicGraphState

REPLY = "Booking an appointment is not implemented yet."


def booking_flow(state: ClinicGraphState) -> dict:
    return {"reply": REPLY}
