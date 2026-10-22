"""Graph runtime: compiled graph + in-process checkpointer, one thread per session
(DESIGN §5.2). Single-instance demo grade; upgrade path: Postgres checkpointer."""

from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph
from app.agent.observability.tracing import trace_chat
from app.agent.tools.patient_tools import get_patient_context
from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse


@lru_cache(maxsize=1)
def get_graph():
    return build_clinic_graph(InMemorySaver())


async def handle_chat(req: ChatRequest) -> ChatResponse:
    graph = get_graph()
    patient_id = req.patient_id or settings.default_patient_id
    state = {
        "session_id": req.session_id,
        "patient_id": patient_id,
        # P8: fetched over REST for every run; a failing backend fails the turn
        # loudly rather than degrading into context-less answers
        "patient_context": get_patient_context(patient_id=patient_id),
        "user_message": req.message,
        "messages": [{"role": "user", "content": req.message}],
        # clear last turn's booking so the response never re-emits a stale one
        "booking_created": None,
    }
    result = await _invoke_traced(graph, state, req.session_id, patient_id)
    return ChatResponse(
        reply=result["reply"],
        intent=result["intent"],
        booking_created=result.get("booking_created"),
        session_id=req.session_id,
    )


async def _invoke_traced(graph, state: dict, session_id: str, patient_id: str) -> dict:
    """ainvoke inside the optional Langfuse root (P6): tracing off → plain ainvoke;
    on success the resolved intent is tagged on the root observation."""
    config = {"configurable": {"thread_id": session_id}}
    with trace_chat(user_id=patient_id, session_id=session_id) as trace:
        result = await graph.ainvoke(state, trace.apply(config))
        trace.tag(result["intent"])
    return result
