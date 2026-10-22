"""P6: Langfuse tracing — off without keys (chat unaffected), on with fakes
(root + propagated user/session, intent tag after the run), fail-soft, one-way
shutdown. No network: everything langfuse is monkeypatched at the package."""

import uuid
from contextlib import contextmanager

import langfuse
import langfuse.langchain
import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import BaseCallbackHandler

from app.agent.observability import tracing
from app.core.config import settings
from app.main import app


class FakeRootObservation:
    """Root observation stand-in; only its context-manager role matters now
    (tags ride propagate_attributes instead — v4 has no Span.update(tags))."""

    def update(self, **kwargs):
        raise AssertionError("Span.update must not be used for tags (v4 drops them)")


class FakeClient:
    def __init__(self):
        self.root = FakeRootObservation()
        self.started = None
        self.shutdown_calls = 0

    def start_as_current_observation(self, *, as_type, name):
        self.started = (as_type, name)

        @contextmanager
        def cm():
            yield self.root

        return cm()

    def shutdown(self):
        self.shutdown_calls += 1


class FakeHandler(BaseCallbackHandler):
    """No-op stand-in for the Langfuse CallbackHandler (langchain calls its
    event methods during the run; BaseCallbackHandler provides no-ops)."""

    instances = []

    def __init__(self, *args, **kwargs):
        FakeHandler.instances.append(self)


@pytest.fixture()
def langfuse_fakes(monkeypatch):
    """Install fake langfuse surface + keys + fresh latches; returns handles.

    tracing.py imports lazily inside its functions, so patching the package
    attributes is enough — no real OTel provider is ever registered."""
    monkeypatch.setattr(tracing, "_client_ready", False)
    monkeypatch.setattr(tracing, "_client_dead", False)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(settings, "langfuse_host", "")

    client = FakeClient()
    propagated = {}
    constructor_kwargs = {}

    def fake_langfuse(**kwargs):
        constructor_kwargs.update(kwargs)
        return None

    @contextmanager
    def fake_propagate_attributes(**kwargs):
        propagated.update(kwargs)
        yield

    monkeypatch.setattr(langfuse, "Langfuse", fake_langfuse)
    monkeypatch.setattr(langfuse, "get_client", lambda: client)
    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate_attributes)
    monkeypatch.setattr(langfuse.langchain, "CallbackHandler", FakeHandler)
    FakeHandler.instances.clear()

    return {
        "client": client,
        "propagated": propagated,
        "constructor": constructor_kwargs,
    }


def test_disabled_without_keys(monkeypatch):
    """Absent keys → passthrough trace: no callbacks, config unchanged, tag no-op."""
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    monkeypatch.setattr(tracing, "_client_dead", False)
    assert not tracing._tracing_ready()
    config = {"configurable": {"thread_id": "s1"}}
    with tracing.trace_chat(user_id="P001", session_id="s1") as trace:
        assert trace.callbacks is None
        assert trace.apply(config) == config
        trace.tag("qa")  # must not raise


def test_trace_chat_builds_root_and_config(langfuse_fakes):
    """With keys: client init carries keys, root observation + propagate wrap the
    turn, the handler and langfuse_* metadata ride the ainvoke config, and the
    intent lands on the trace as a tag (P6)."""
    config = {"configurable": {"thread_id": "s1"}}
    with tracing.trace_chat(user_id="P001", session_id="sess-1") as trace:
        assert langfuse_fakes["constructor"] == {
            "public_key": "pk-test",
            "secret_key": "sk-test",
            "base_url": None,
        }
        assert langfuse_fakes["client"].started == ("span", "clinic-chat")
        assert len(trace.callbacks) == 1
        merged = trace.apply(config)
        assert merged["configurable"] == {"thread_id": "s1"}
        assert merged["callbacks"] == trace.callbacks
        assert merged["metadata"] == {
            "langfuse_trace_name": "clinic-chat",
            "langfuse_user_id": "P001",
            "langfuse_session_id": "sess-1",
        }
        trace.tag("qa")
    base = {k: v for k, v in langfuse_fakes["propagated"].items() if k != "tags"}
    assert langfuse_fakes["propagated"]["tags"] == ["qa"]
    assert base == {
        "user_id": "P001",
        "session_id": "sess-1",
        "trace_name": "clinic-chat",
    }


def test_trace_chat_fail_soft_on_client_error(monkeypatch, langfuse_fakes):
    """A Langfuse setup failure degrades to an untraced turn — never raises."""

    def boom(**kwargs):
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(langfuse, "Langfuse", boom)
    with tracing.trace_chat(user_id="P001", session_id="s1") as trace:
        assert trace.callbacks is None
        assert trace.apply({"configurable": {}}) == {"configurable": {}}


def test_tag_rides_propagate_attributes(langfuse_fakes):
    """tag() must go through propagate_attributes(tags=...) while the root span
    is still the active span — Span.update has no tags param in SDK v4 (they
    silently vanish into **kwargs)."""
    with tracing.trace_chat(user_id="P001", session_id="sess-1") as trace:
        trace.tag("qa")
    assert langfuse_fakes["propagated"].get("tags") == ["qa"]


def test_shutdown_flushes_once_and_is_one_way(langfuse_fakes):
    """Shutdown calls the client once; a second call is a no-op; afterwards
    trace_chat stays disabled for the process lifetime (v4 client latch)."""
    with tracing.trace_chat(user_id="P001", session_id="s1"):
        pass  # client becomes ready
    tracing.shutdown_tracing()
    assert langfuse_fakes["client"].shutdown_calls == 1
    tracing.shutdown_tracing()
    assert langfuse_fakes["client"].shutdown_calls == 1
    with tracing.trace_chat(user_id="P001", session_id="s1") as trace:
        assert trace.callbacks is None


def test_chat_endpoint_tags_intent_on_trace(fake_chains, langfuse_fakes):
    """End-to-end P6 with fakes: POST /chat under tracing keys tags the root
    observation with the resolved intent and propagates user/session."""
    fake_chains("general", general_reply="Hello!")
    session_id = uuid.uuid4().hex
    with TestClient(app) as client:
        resp = client.post("/chat", json={"session_id": session_id, "message": "hi"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "general"
    assert langfuse_fakes["propagated"].get("tags") == ["general"]
    assert langfuse_fakes["propagated"]["session_id"] == session_id
    assert langfuse_fakes["propagated"]["user_id"] == "P001"
