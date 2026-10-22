"""REST tools against an httpx.MockTransport: exact request payloads/params, and
readable RuntimeError wrapping for backend failures (fail loud, no silent fallbacks)."""

import httpx
import pytest
import json

from app.agent.tools import client as client_mod
from app.agent.tools.booking_tools import create_booking
from app.agent.tools.catalog_tools import search_doctors, search_treatments


@pytest.fixture()
def mock_transport(monkeypatch):
    def install(handler):
        monkeypatch.setattr(client_mod, "_transport", httpx.MockTransport(handler))
    return install


def test_create_booking_posts_exact_payload(mock_transport):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"booking_id": "B7x", "status": "Confirmed"})

    mock_transport(handler)
    result = create_booking(
        patient_id="P001", doctor_id="D104", treatment_id="T005",
        booking_date="2026-11-21", booking_time="09:30",
    )
    assert result == {"booking_id": "B7x", "status": "Confirmed"}
    assert captured["url"] == "http://localhost:8000/api/bookings"
    assert captured["json"] == {
        "patient_id": "P001", "doctor_id": "D104", "treatment_id": "T005",
        "booking_date": "2026-11-21", "booking_time": "09:30", "notes": None,
    }


def test_create_booking_backend_error_is_readable(mock_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "Doctor not found"})

    mock_transport(handler)
    with pytest.raises(RuntimeError) as exc:
        create_booking("P001", "D999", "T005", "2026-11-21", "09:30")
    assert "422" in str(exc.value) and "Doctor not found" in str(exc.value)


def test_backend_unreachable_is_readable(mock_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    mock_transport(handler)
    with pytest.raises(RuntimeError, match="backend unreachable"):
        create_booking("P001", "D104", "T005", "2026-11-21", "09:30")


def test_catalog_tools_pass_query_params(mock_transport):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=[])

    mock_transport(handler)
    assert search_doctors(specialty="Ortho") == []
    assert search_treatments(search="joint pain") == []
    assert search_doctors() == []
    assert captured == [
        ("/api/doctors", {"specialty": "Ortho"}),
        ("/api/treatments", {"search": "joint pain"}),
        ("/api/doctors", {}),
    ]
