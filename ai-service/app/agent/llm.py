"""Single ChatOpenAI factory: one model for everything (DESIGN §5.5).

Nodes import get_chat_model from here; tests patch it (or the chain getters
built on it) at the consumer module — never re-export.
"""

from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_chat_model(**kwargs) -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured — set it in .env or the environment")
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        **kwargs,
    )
