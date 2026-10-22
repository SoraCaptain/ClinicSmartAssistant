"""Graph assembly (DESIGN §5.2): every turn starts at classify_intent (P1 — no sticky
intent). Booking turns fan out into the slot-filling nodes; execute_booking sits
behind the explicit-confirmation gate (P2). finalize_reply persists the assistant turn."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.booking_flow import (
    ask_missing,
    confirm_summary,
    execute_booking,
    extract_slots,
    missing_slots,
)
from app.agent.nodes.bookings_query import bookings_answer
from app.agent.nodes.classifier import classify_intent
from app.agent.nodes.general import general_reply
from app.agent.nodes.qa import qa_answer
from app.agent.state import ClinicGraphState

# Intent → node for the single-node intents; book_appointment fans out in route_intent
INTENT_NODES = {
    "qa": "qa_answer",
    "check_bookings": "bookings_answer",
    "general": "general_reply",
}


def route_intent(state: ClinicGraphState) -> str:
    """Booking turns: only an explicit confirmation of a rendered summary reaches
    execute_booking; every other booking turn re-enters slot extraction. An unknown
    intent raises KeyError — fail loud, never fall back."""
    intent = state["intent"]
    if intent != "book_appointment":
        return intent
    draft = state.get("booking_draft") or {}
    if draft.get("awaiting_confirmation") and state.get("user_confirms") is True:
        return "execute_booking"
    return "extract_slots"


def route_after_extract(state: ClinicGraphState) -> str:
    draft = state.get("booking_draft") or {}
    return "ask_missing" if missing_slots(draft) else "confirm_summary"


def finalize_reply(state: ClinicGraphState) -> dict:
    """Single place where the turn's reply enters the persisted conversation."""
    return {"messages": [{"role": "assistant", "content": state["reply"]}]}


def build_clinic_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(ClinicGraphState)
    graph.add_node("classify_intent", classify_intent)
    for name, node in (
        ("qa_answer", qa_answer),
        ("bookings_answer", bookings_answer),
        ("general_reply", general_reply),
        ("extract_slots", extract_slots),
        ("ask_missing", ask_missing),
        ("confirm_summary", confirm_summary),
        ("execute_booking", execute_booking),
    ):
        graph.add_node(name, node)
    graph.add_node("finalize_reply", finalize_reply)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_intent,
        {**INTENT_NODES, "extract_slots": "extract_slots", "execute_booking": "execute_booking"},
    )
    graph.add_conditional_edges(
        "extract_slots",
        route_after_extract,
        {"ask_missing": "ask_missing", "confirm_summary": "confirm_summary"},
    )
    for name in (*INTENT_NODES.values(), "ask_missing", "confirm_summary", "execute_booking"):
        graph.add_edge(name, "finalize_reply")
    graph.add_edge("finalize_reply", END)
    return graph.compile(checkpointer=checkpointer)
