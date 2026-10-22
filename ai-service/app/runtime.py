"""Graph runtime: compiled graph + in-process checkpointer, one thread per session
(DESIGN §5.2). Single-instance demo grade; upgrade path: Postgres checkpointer."""

from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_clinic_graph
from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse


@lru_cache(maxsize=1)
def get_graph():
    return build_clinic_graph(InMemorySaver())


async def handle_chat(req: ChatRequest) -> ChatResponse:
    graph = get_graph()
    config = {"configurable": {"thread_id": req.session_id}}
    state = {
        "session_id": req.session_id,
        "patient_id": req.patient_id or settings.default_patient_id,  # P8 default
        "user_message": req.message,
        "messages": [{"role": "user", "content": req.message}],
    }
    result = await graph.ainvoke(state, config)
    return ChatResponse(
        reply=result["reply"],
        intent=result["intent"],
        booking_created=result.get("booking_created"),
        session_id=req.session_id,
    )
