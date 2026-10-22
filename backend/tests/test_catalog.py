"""Catalog contains-match (§5.3): case-insensitive, deterministic recall on the tiny corpus."""


def test_clinics_list_and_by_id(client):
    assert len(client.get("/api/clinics").json()) == 2
    one = client.get("/api/clinics", params={"clinic_id": "C002"}).json()
    assert [c["clinic_name"] for c in one] == ["Sunset Wellness Center"]


def test_doctors_specialty_contains_case_insensitive(client):
    ortho = client.get("/api/doctors", params={"specialty": "ortho"}).json()
    assert [d["doctor_id"] for d in ortho] == ["D104"]
    ped = client.get("/api/doctors", params={"specialty": "PEDIAT"}).json()
    assert [d["doctor_id"] for d in ped] == ["D102"]


def test_doctors_unmatched_specialty_empty(client):
    assert client.get("/api/doctors", params={"specialty": "cardiology"}).json() == []


def test_treatments_search_matches_name_case_insensitive(client):
    pain = client.get("/api/treatments", params={"search": "PAIN"}).json()
    assert [t["treatment_id"] for t in pain] == ["T005"]


def test_treatments_search_matches_instructions(client):
    skin = client.get("/api/treatments", params={"search": "skin"}).json()
    assert [t["treatment_id"] for t in skin] == ["T003"]


def test_treatments_no_search_returns_all(client):
    assert len(client.get("/api/treatments").json()) == 5


def test_search_escapes_like_wildcards(client):
    """% and _ are literal contains-match text, not SQL wildcards (§5.3)."""
    assert client.get("/api/doctors", params={"specialty": "%"}).json() == []
    assert client.get("/api/treatments", params={"search": "_"}).json() == []
