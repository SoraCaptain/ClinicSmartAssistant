"""Bookings lookup node — reads the patient's bookings via the REST tool in a later slice."""

from app.agent.state import ClinicGraphState

REPLY = "Viewing your bookings is not implemented yet."


def bookings_answer(state: ClinicGraphState) -> dict:
    return {"reply": REPLY}
