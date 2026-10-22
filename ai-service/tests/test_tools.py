"""REST tools against an httpx.MockTransport: exact request payloads/params, and
readable RuntimeError wrapping for backend failures (fail loud, no silent fallbacks)."""

import httpx
import pytest
import json

from app.agent.tools import client as client_mod
from app.agent.tools.booking_tools import create_booking, get_my_bookings
from app.agent.tools.catalog_tools import get_clinics, search_doctors, search_treatments
from app.agent.tools.patient_tools import get_patient_context


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


def test_get_clinics_passes_clinic_id(mock_transport):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=[])

    mock_transport(handler)
    assert get_clinics() == []
    assert get_clinics(clinic_id="C001") == []
    assert captured == [("/api/clinics", {}), ("/api/clinics", {"clinic_id": "C001"})]


def test_get_my_bookings_queries_patient_id(mock_transport):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[{"booking_id": "B1004"}])

    mock_transport(handler)
    assert get_my_bookings("P001") == [{"booking_id": "B1004"}]
    assert captured["url"] == "http://localhost:8000/api/bookings?patient_id=P001"


def test_get_patient_context_hits_context_endpoint(mock_transport):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"profile": {"patient_id": "P001"}})

    mock_transport(handler)
    assert get_patient_context("P001") == {"profile": {"patient_id": "P001"}}
    assert captured["url"] == "http://localhost:8000/api/patients/P001/context"
