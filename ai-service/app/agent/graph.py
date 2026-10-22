"""Graph assembly (DESIGN §5.2): every turn starts at classify_intent (P1 — no sticky
intent), routes to the intent's node, then finalize_reply persists the assistant turn."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.booking_flow import booking_flow
from app.agent.nodes.bookings_query import bookings_answer
from app.agent.nodes.classifier import classify_intent
from app.agent.nodes.general import general_reply
from app.agent.nodes.qa import qa_answer
from app.agent.state import ClinicGraphState

# Single source of truth: intent → node (LedgerMind NODE_SPECS pattern)
INTENT_NODES = {
    "qa": "qa_answer",
    "check_bookings": "bookings_answer",
    "book_appointment": "booking_flow",
    "general": "general_reply",
}


def route_intent(state: ClinicGraphState) -> str:
    """Return the raw intent; INTENT_NODES (path_map) translates to the node.
    An unknown intent raises KeyError — fail loud, never fall back."""
    return state["intent"]


def finalize_reply(state: ClinicGraphState) -> dict:
    """Single place where the turn's reply enters the persisted conversation."""
    return {"messages": [{"role": "assistant", "content": state["reply"]}]}


def build_clinic_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(ClinicGraphState)
    graph.add_node("classify_intent", classify_intent)
    for name, node in (
        ("qa_answer", qa_answer),
        ("bookings_answer", bookings_answer),
        ("booking_flow", booking_flow),
        ("general_reply", general_reply),
    ):
        graph.add_node(name, node)
    graph.add_node("finalize_reply", finalize_reply)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges("classify_intent", route_intent, INTENT_NODES)
    for name in INTENT_NODES.values():
        graph.add_edge(name, "finalize_reply")
    graph.add_edge("finalize_reply", END)
    return graph.compile(checkpointer=checkpointer)
