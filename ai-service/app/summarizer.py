"""Transcript summarizer (bonus): one structured-output LLM call extracts the
four clinical fields. Not a graph node — a standalone endpoint handler."""

from pydantic import BaseModel

from app.agent.llm import get_chat_model
from app.agent.observability.tracing import trace_chat
from app.schemas.summarize import SummarizeRequest, SummarizeResponse

SUMMARIZE_TRACE_NAME = "clinic-summarize"

ABSENT = "Not mentioned in the transcript."

SUMMARIZE_SYSTEM = f"""You extract a structured summary from a doctor-patient \
transcript. Fill each field only from what the transcript states, staying close \
to its wording; use exactly "{ABSENT}" for anything the transcript does not \
mention.
- chief_complaint: why the patient sought care
- diagnosis: the diagnosis stated or discussed
- medication: medications prescribed or discussed
- doctor_instructions: follow-up instructions given by the doctor"""


class MedicalSummary(BaseModel):
    chief_complaint: str
    diagnosis: str
    medication: str
    doctor_instructions: str


def get_summary_chain():
    """Built per call so tests can patch this symbol at this module.
    method="function_calling": the langchain-default json_schema response_format
    is unsupported by several OpenAI-compatible providers (e.g. DeepSeek)."""
    return get_chat_model().with_structured_output(MedicalSummary, method="function_calling")


async def handle_summarize(req: SummarizeRequest) -> SummarizeResponse:
    # ainvoke: a sync LLM call here would block the event loop for the whole
    # LLM turn, serializing concurrent /chat and /summarize requests
    with trace_chat(name=SUMMARIZE_TRACE_NAME) as trace:  # tokens/cost ride the optional root
        summary: MedicalSummary = await get_summary_chain().ainvoke(
            f"{SUMMARIZE_SYSTEM}\n\nTranscript:\n{req.transcript}", trace.apply({})
        )
    return SummarizeResponse(**summary.model_dump())
