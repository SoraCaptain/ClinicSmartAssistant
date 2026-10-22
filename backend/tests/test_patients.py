"""P8 payload: profile + allergies + treatment history + upcoming bookings."""

from datetime import date

# Seeded P001 dates (demo anchor) — expectation derived from the clock, not hardcoded
P001_BOOKINGS = {"B1001": date(2026, 11, 5), "B1004": date(2026, 11, 15)}


def test_patient_context_p001(client):
    resp = client.get("/api/patients/P001/context")
    assert resp.status_code == 200
    ctx = resp.json()
    assert ctx["profile"]["first_name"] == "John"
    assert ctx["profile"]["known_allergies"] == "Penicillin, Peanuts"
    assert [h["record_id"] for h in ctx["treatment_history"]] == ["H9002"]
    expected_upcoming = {bid for bid, d in P001_BOOKINGS.items() if d >= date.today()}
    assert {b["booking_id"] for b in ctx["upcoming_bookings"]} == expected_upcoming


def test_patient_context_history_joins_doctor_name(client):
    """History rows carry the joined doctor identity + clinical fields (§5.3 widening)."""
    history = client.get("/api/patients/P001/context").json()["treatment_history"]
    h9002 = history[0]
    assert h9002["doctor_id"] == "D101"
    assert h9002["doctor_name"] == "Dr. Sarah Jenkins"
    assert h9002["prescribed_medication"] == "Multivitamins"
    assert "Recommended light exercise" in h9002["doctor_notes"]


def test_patient_context_unknown_404(client):
    assert client.get("/api/patients/P999/context").status_code == 404
