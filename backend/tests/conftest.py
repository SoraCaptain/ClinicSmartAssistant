"""Test bootstrap: sqlite DATABASE_URL must be set before app.database is first imported."""

import os
import shutil
import tempfile

_TEST_DIR = tempfile.mkdtemp(prefix="clinicpilot-backend-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.services.seed_service import seed


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_dir():
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


@pytest.fixture()
def db():
    """Fresh schema + seeded data per test (lifespan seed then skips: populated tables, P4)."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c
