"""P4: seed reads the real mock-data CSVs and re-runs never duplicate rows."""

from sqlalchemy import func, select

from app.models import Booking, Clinic, Doctor, Patient, Treatment, TreatmentHistory
from app.services.seed_service import seed

# Demo data anchor (DESIGN §7)
EXPECTED_COUNTS = {
    Clinic: 2,
    Doctor: 4,
    Treatment: 5,
    Patient: 3,
    Booking: 4,
    TreatmentHistory: 2,
}


def _counts(session) -> dict[type, int]:
    return {model: (session.scalar(select(func.count()).select_from(model)) or 0) for model in EXPECTED_COUNTS}


def test_seed_matches_demo_anchor(db):
    counts = _counts(db)
    for model, expected in EXPECTED_COUNTS.items():
        assert counts[model] == expected, f"{model.__tablename__}: {counts[model]} != {expected}"


def test_seed_idempotent_rerun_inserts_nothing(db):
    before = _counts(db)
    inserted = seed(db)  # second run against populated tables
    assert all(n == 0 for n in inserted.values()), inserted
    assert _counts(db) == before


def test_seed_skips_populated_table_even_if_partial(db):
    """Populated tables are skipped wholesale (DESIGN P4); partial tables are not healed."""
    db.query(Booking).filter(Booking.booking_id == "B1001").delete()
    db.commit()
    seed(db)
    assert (db.scalar(select(func.count()).select_from(Booking)) or 0) == 3


def test_seed_insert_order_respects_fks_on_fresh_schema():
    """Regression (slice 6, postgres): with autoflush=False and no ORM relationships
    the commit-time unit-of-work flushes tables in arbitrary order — on
    FK-enforcing databases the seed hit 'patient_treatment_history before doctors'
    (compose first boot). sqlite skips FK checks by default, so this test enables
    them and replays a fresh-container seed: create_all → seed → commit."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enforce_fks(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        inserted = seed(session)
    assert sum(inserted.values()) == sum(EXPECTED_COUNTS.values())
