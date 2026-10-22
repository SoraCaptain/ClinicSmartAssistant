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


def test_doctors_search_matches_name(client):
    hits = client.get("/api/doctors", params={"search": "rostova"}).json()
    assert [d["doctor_id"] for d in hits] == ["D103"]


def test_doctors_search_matches_bio(client):
    hits = client.get("/api/doctors", params={"search": "eczema"}).json()
    assert [d["doctor_id"] for d in hits] == ["D103"]


def test_doctors_search_matches_language(client):
    hits = client.get("/api/doctors", params={"search": "Mandarin"}).json()
    assert [d["doctor_id"] for d in hits] == ["D102"]


def test_doctors_search_unmatched_empty(client):
    assert client.get("/api/doctors", params={"search": "oncology"}).json() == []


def test_doctors_specialty_still_filters_alongside_search_param(client):
    """`specialty` keeps its §5.3 behavior after the generic `search` widening."""
    ortho = client.get("/api/doctors", params={"specialty": "ortho"}).json()
    assert [d["doctor_id"] for d in ortho] == ["D104"]


def test_clinics_search_matches_name(client):
    hits = client.get("/api/clinics", params={"search": "metro"}).json()
    assert [c["clinic_id"] for c in hits] == ["C001"]


def test_clinics_search_matches_cancellation_policy(client):
    hits = client.get("/api/clinics", params={"search": "24 hours"}).json()
    assert [c["clinic_id"] for c in hits] == ["C001"]


def test_clinics_search_matches_emergency_instructions(client):
    hits = client.get("/api/clinics", params={"search": "911"}).json()
    assert [c["clinic_id"] for c in hits] == ["C001"]


def test_clinics_clinic_id_still_filters(client):
    one = client.get("/api/clinics", params={"clinic_id": "C002"}).json()
    assert [c["clinic_id"] for c in one] == ["C002"]
