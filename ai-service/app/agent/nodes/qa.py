"""RAG answer node — retrieval + cited recommendation lands in slice 4 (DESIGN §5.3)."""

from app.agent.state import ClinicGraphState

REPLY = "Clinic Q&A with treatment and doctor recommendations is not implemented yet."


def qa_answer(state: ClinicGraphState) -> dict:
    return {"reply": REPLY}
