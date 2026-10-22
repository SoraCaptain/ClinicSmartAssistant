"""Graph state (DESIGN §5.1). `messages` carries the add_messages reducer so the
checkpointer accumulates the conversation across turns — every turn is
re-classified against the full history (P1). Keys for later slices are part of
the contract and declared up front."""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class ClinicGraphState(TypedDict, total=False):
    session_id: str
    patient_id: str
    patient_context: dict  # profile, allergies, history (tool-fetched, slice 4 / P8)
    messages: Annotated[list, add_messages]
    user_message: str
    intent: str  # qa | check_bookings | book_appointment | general
    user_confirms: bool | None  # classifier's confirmation verdict while a draft awaits
    retrieved: list  # rows pulled by catalog tools (slice 4)
    booking_draft: dict  # slot-filling state (slice 3)
    booking_created: dict | None  # persisted booking (slice 3)
    reply: str  # final assistant text for this turn
