"""Multi-session chat history: POST /api/chat persists turns; sessions/messages reads."""

from app.models import ChatMessage, ChatSession


def fake_ai(reply="Hello!", intent="general", booking=None):
    """Patch target as a plain async fn factory (monkeypatched like test_chat.py)."""

    async def _chat(payload):
        return {
            "reply": reply,
            "intent": intent,
            "booking_created": booking,
            "session_id": payload["session_id"],
        }

    return _chat


def post_turn(client, session_id, message, monkeypatch, **ai_kwargs):
    monkeypatch.setattr("app.routers.chat.ai_client.chat", fake_ai(**ai_kwargs))
    return client.post("/api/chat", json={"session_id": session_id, "message": message})


def test_turn_persists_user_and_assistant_messages(client, monkeypatch):
    resp = post_turn(client, "s1", "What treatments do you offer?", monkeypatch)
    assert resp.status_code == 200

    sessions = client.get("/api/chat/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "s1"
    assert sessions[0]["title"] == "What treatments do you offer?"  # title = first user message

    msgs = client.get("/api/chat/sessions/s1/messages").json()
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("user", "What treatments do you offer?"),
        ("assistant", "Hello!"),
    ]
    assert msgs[1]["intent"] == "general"
    assert msgs[1]["booking"] is None


def test_failed_turn_persists_nothing(client, monkeypatch):
    """P7: ai-service down → 503 and no session/message rows (fail loud, no trace)."""
    monkeypatch.setattr("app.core.config.settings.ai_service_url", "http://127.0.0.1:1")
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 503

    assert client.get("/api/chat/sessions").json() == []
    assert client.get("/api/chat/sessions/s1/messages").status_code == 404


def test_second_turn_updates_session_no_duplicate(client, monkeypatch):
    post_turn(client, "s1", "first", monkeypatch)
    post_turn(client, "s1", "second", monkeypatch, reply="Answer two")

    sessions = client.get("/api/chat/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "first"  # title pinned by first message
    assert sessions[0]["updated_at"] >= sessions[0]["created_at"]

    msgs = client.get("/api/chat/sessions/s1/messages").json()
    assert len(msgs) == 4  # two turns × two rows
    assert msgs[3]["content"] == "Answer two"


def test_sessions_ordered_most_recently_active_first(client, monkeypatch):
    post_turn(client, "s-old", "old question", monkeypatch)
    post_turn(client, "s-new", "new question", monkeypatch)
    post_turn(client, "s-old", "old again", monkeypatch)  # s-old becomes most recent

    ids = [s["session_id"] for s in client.get("/api/chat/sessions").json()]
    assert ids == ["s-old", "s-new"]


def test_unknown_session_messages_returns_404(client):
    assert client.get("/api/chat/sessions/nope/messages").status_code == 404


def test_booking_created_round_trips_as_booking_dict(client, monkeypatch):
    booking = {"booking_id": "B-ab12", "booking_date": "2026-11-20", "booking_time": "14:00"}
    post_turn(client, "s1", "book a checkup", monkeypatch, reply="Booked!", intent="book_appointment", booking=booking)

    msgs = client.get("/api/chat/sessions/s1/messages").json()
    assert msgs[1]["booking"] == booking  # replayed confirmation card payload


def test_long_first_message_title_is_truncated(client, monkeypatch):
    post_turn(client, "s1", "x" * 100, monkeypatch)
    title = client.get("/api/chat/sessions").json()[0]["title"]
    assert len(title) == 60


def test_patient_id_defaults_to_p001(client, db, monkeypatch):
    post_turn(client, "s1", "hi", monkeypatch)
    assert db.get(ChatSession, "s1").patient_id == "P001"
    assert db.query(ChatMessage).count() == 2


def test_persistence_failure_does_not_fail_the_turn(client, monkeypatch, caplog):
    """The AI side effects (e.g. booking) already happened upstream — a history
    write failure must not 500 the turn and invite a double-booking retry."""
    monkeypatch.setattr("app.routers.chat.ai_client.chat", fake_ai())
    monkeypatch.setattr(
        "app.routers.chat.chat_history_service.record_turn",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})

    assert resp.status_code == 200
    assert resp.json()["reply"] == "Hello!"
    assert client.get("/api/chat/sessions").json() == []  # degraded: no rows, turn still served
