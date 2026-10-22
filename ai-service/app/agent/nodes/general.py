"""General node: small talk + out-of-scope refusal (DESIGN §5.2)."""

from app.agent.llm import get_chat_model
from app.agent.prompts import GENERAL_SYSTEM, GENERAL_USER, render_history
from app.agent.state import ClinicGraphState


def get_general_chain():
    """Built per call so tests can patch this symbol at this module."""
    return get_chat_model()


def general_reply(state: ClinicGraphState) -> dict:
    prompt = (
        f"{GENERAL_SYSTEM}\n\n"
        + GENERAL_USER.format(
            history=render_history(state.get("messages", [])),
            message=state["user_message"],
        )
    )
    return {"reply": get_general_chain().invoke(prompt).content}
