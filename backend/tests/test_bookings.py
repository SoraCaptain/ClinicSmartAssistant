"""Bookings: seeded read model (4 rows), POST creates the 5th (P5), validation → 422."""



def test_get_bookings_seeded_returns_four(client):
    resp = client.get("/api/bookings")
    assert resp.status_code == 200
    bookings = resp.json()
    assert len(bookings) == 4
    by_id = {b["booking_id"]: b for b in bookings}
    # joined read model fields (B1004 = P001 knee consult)
    b1004 = by_id["B1004"]
    assert b1004["doctor_name"] == "Dr. James Wilson"
    assert b1004["doctor_specialty"] == "Orthopedics"
    assert b1004["treatment_name"] == "Joint & Pain Consultation"
    assert b1004["clinic_name"] == "Metro Care Health Clinic"
    assert b1004["patient_id"] == "P001"
    assert b1004["status"] == "Confirmed"


def test_get_bookings_patient_filter(client):
    resp = client.get("/api/bookings", params={"patient_id": "P001"})
    assert resp.status_code == 200
    assert {b["booking_id"] for b in resp.json()} == {"B1001", "B1004"}


def test_post_booking_creates_fifth_visible_immediately(client):
    payload = {
        "patient_id": "P001",
        "doctor_id": "D104",
        "treatment_id": "T005",
        "booking_date": "2026-12-01",
        "booking_time": "10:30",
        "notes": "Knee pain follow-up via chatbot.",
    }
    resp = client.post("/api/bookings", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["booking_id"].startswith("B")
    assert len(created["booking_id"]) > 1
    suffix = created["booking_id"][1:]
    int(suffix, 16)  # server-generated hex suffix
    assert 8 <= len(suffix) <= 16
    assert created["status"] == "Confirmed"
    assert created["source"] == "chatbot"
    assert created["booking_time"].startswith("10:30")

    all_bookings = client.get("/api/bookings").json()  # P5: immediately visible
    assert len(all_bookings) == 5
    mine = client.get("/api/bookings", params={"patient_id": "P001"}).json()
    assert len(mine) == 3
    assert created["booking_id"] in {b["booking_id"] for b in mine}


def test_post_booking_unknown_doctor_422(client):
    payload = {
        "patient_id": "P001",
        "doctor_id": "D999",
        "treatment_id": "T005",
        "booking_date": "2026-12-01",
        "booking_time": "10:30",
    }
    resp = client.post("/api/bookings", json=payload)
    assert resp.status_code == 422
    assert "doctor_id" in resp.json()["detail"]


def test_post_booking_unknown_patient_422(client):
    payload = {
        "patient_id": "P999",
        "doctor_id": "D104",
        "treatment_id": "T005",
        "booking_date": "2026-12-01",
        "booking_time": "10:30",
    }
    resp = client.post("/api/bookings", json=payload)
    assert resp.status_code == 422
    assert "patient_id" in resp.json()["detail"]


def test_post_booking_bad_date_422(client):
    payload = {
        "patient_id": "P001",
        "doctor_id": "D104",
        "treatment_id": "T005",
        "booking_date": "2026-13-45",
        "booking_time": "10:30",
    }
    assert client.post("/api/bookings", json=payload).status_code == 422


def test_post_booking_bad_time_422(client):
    payload = {
        "patient_id": "P001",
        "doctor_id": "D104",
        "treatment_id": "T005",
        "booking_date": "2026-12-01",
        "booking_time": "25:99",
    }
    assert client.post("/api/bookings", json=payload).status_code == 422


def test_post_booking_missing_field_422(client):
    payload = {
        "patient_id": "P001",
        "doctor_id": "D104",
        "treatment_id": "T005",
        "booking_time": "10:30",
    }
    assert client.post("/api/bookings", json=payload).status_code == 422
