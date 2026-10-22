"""Health probe: status + db connectivity."""

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


def test_health_db_up(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "up"


class _BrokenDB:
    def execute(self, *args, **kwargs):
        raise RuntimeError("connection refused")


def test_health_db_down_reports_degraded():
    app.dependency_overrides[get_db] = lambda: _BrokenDB()
    try:
        with TestClient(app) as c:
            resp = c.get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200  # §6 pins the body shape; probe semantics land in slice 6
    assert resp.json() == {"status": "degraded", "db": "down"}
