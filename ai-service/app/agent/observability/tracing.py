"""Langfuse tracing (Python SDK v4, OpenTelemetry-based) — DESIGN §5.5, P6.

LedgerMind-proven shape, simplified for this codebase. One global client
(singleton per public key) owns the OTel span exporter and its background
threads. Each /chat wraps ``graph.ainvoke`` in an enclosing observation +
``propagate_attributes()`` — the v4-blessed root — so every observation created
inside (LangChain handler runs: classifier, node chains, cost-bearing
generations) inherits the trace's user_id/session_id.

P6 contract: absent keys → tracing off, ``/chat`` unaffected. Every entry point
here is fail-soft — a Langfuse failure degrades to an untraced turn, never an
error response. ``shutdown_tracing()`` (fastapi lifespan) flushes pending spans;
the v4 client cannot be revived after shutdown, so the latch keeps tracing off
for the rest of the process lifetime.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack, contextmanager
from typing import Iterator, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

TRACE_NAME = "clinic-chat"

_client_ready = False
# One-way latch: the v4 client's resource manager is a singleton per public key
# and cannot be revived after shutdown — once shut down, tracing stays off.
_client_dead = False


def _tracing_ready() -> bool:
    return (
        not _client_dead
        and bool(settings.langfuse_public_key)
        and bool(settings.langfuse_secret_key)
    )


def _ensure_client() -> None:
    """Initialize the global Langfuse client from settings, once."""
    global _client_ready
    if _client_ready or _client_dead:
        return
    from langfuse import Langfuse

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_host or None,
    )
    _client_ready = True


class ChatTrace:
    """What the chat runtime needs from one traced turn.

    ``apply`` merges the LangChain callback handler + langfuse_* metadata into
    the ainvoke config (passthrough when tracing is off); ``tag`` stamps the
    resolved intent on the trace after the run (P6 intent tag).
    """

    def __init__(
        self,
        callbacks: Optional[list] = None,
        metadata: Optional[dict] = None,
    ):
        self.callbacks = callbacks
        self.metadata = metadata

    def apply(self, config: dict) -> dict:
        if self.callbacks is None:
            return config
        return {**config, "callbacks": self.callbacks, "metadata": self.metadata}

    def tag(self, intent: str) -> None:
        """Tag the trace with the resolved intent. Must be called inside the
        trace_chat with-block: tags are trace-level (v4 Span.update has no tags),
        and propagate_attributes attaches to the currently-active root span."""
        if self.callbacks is None:
            return
        try:
            from langfuse import propagate_attributes

            with propagate_attributes(tags=[intent]):
                pass
        except Exception as exc:
            logger.warning("langfuse_intent_tag_failed error=%s", exc)


@contextmanager
def trace_chat(
    user_id: str | None = None,
    session_id: str | None = None,
    name: str = TRACE_NAME,
) -> Iterator[ChatTrace]:
    """Wrap one LLM run (graph turn or standalone call) in the v4 tracing root.

    Enters the enclosing observation + ``propagate_attributes()`` BEFORE the
    ainvoke call (context copies taken inside langchain/langgraph inherit the
    propagated attributes). Yields a ChatTrace whose ``apply`` returns the
    config to ainvoke with; a disabled trace (keys absent, client failure) is a
    passthrough. Never raises into the chat path — a setup failure degrades to
    an untraced turn with a warning.
    """
    if not _tracing_ready():
        yield ChatTrace()
        return
    stack = ExitStack()
    handler = None
    try:
        _ensure_client()
        from langfuse import get_client, propagate_attributes
        from langfuse.langchain import CallbackHandler

        client = get_client()
        stack.enter_context(
            client.start_as_current_observation(as_type="span", name=name)
        )
        stack.enter_context(
            propagate_attributes(
                user_id=user_id,
                session_id=session_id,
                trace_name=name,
            )
        )
        handler = CallbackHandler()
    except Exception as exc:
        stack.close()
        logger.warning("langfuse_trace_chat_failed error=%s", exc)
        yield ChatTrace()
        return
    # setup succeeded — exceptions from the caller's ainvoke propagate
    # through the with-statement untouched
    with stack:
        yield ChatTrace(
            callbacks=[handler],
            metadata={
                "langfuse_trace_name": name,
                "langfuse_user_id": user_id,
                "langfuse_session_id": session_id,
            },
        )


def shutdown_tracing() -> None:
    """Flush pending spans and shut the global client down (one-way).

    Called from the fastapi lifespan shutdown path; a no-op when tracing was
    never initialized. Fail-soft — shutdown must not raise.
    """
    global _client_ready, _client_dead
    _client_dead = True
    if not _client_ready:
        return
    try:
        from langfuse import get_client

        get_client().shutdown()
    except Exception as exc:
        logger.warning("langfuse_shutdown_failed error=%s", exc)
    finally:
        _client_ready = False
