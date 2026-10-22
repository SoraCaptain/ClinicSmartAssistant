"""Idempotent CSV seed (P4): per-table skip-if-populated, upsert-by-PK on insert.

Reads the actual mock-data/*.csv with stdlib csv (files have no trailing newline —
never line-split).
"""

import csv
import logging
from collections.abc import Callable, Iterator
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, Clinic, Doctor, Patient, Treatment, TreatmentHistory

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "mock-data"


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _as_date(value: str) -> date:
    return date.fromisoformat(value)


def _as_time(value: str) -> time:
    return time.fromisoformat(value)


def _as_decimal(value: str) -> Decimal:
    return Decimal(value)


def _as_int(value: str) -> int:
    return int(value)


_TABLES: list[tuple[type, str, Callable[[dict[str, str]], dict[str, Any]]]] = [
    (Clinic, "clinics.csv", lambda r: dict(r)),
    (Doctor, "doctors.csv", lambda r: {**r, "consultation_fee_usd": _as_decimal(r["consultation_fee_usd"])}),
    (
        Treatment,
        "treatments.csv",
        lambda r: {**r, "duration_minutes": _as_int(r["duration_minutes"]), "price_usd": _as_decimal(r["price_usd"])},
    ),
    (Patient, "patients.csv", lambda r: {**r, "dob": _as_date(r["dob"])}),
    (
        Booking,
        "patient_bookings.csv",
        lambda r: {**r, "booking_date": _as_date(r["booking_date"]), "booking_time": _as_time(r["booking_time"])},
    ),
    (TreatmentHistory, "patient_treatment_history.csv", lambda r: {**r, "visit_date": _as_date(r["visit_date"])}),
]


def seed(db: Session, data_dir: Path | None = None) -> dict[str, int]:
    """Seed all tables; returns inserted row counts per table. Re-runs never duplicate (P4)."""
    data_dir = data_dir or _DEFAULT_DATA_DIR
    inserted: dict[str, int] = {}
    for model, filename, coerce in _TABLES:
        existing = db.scalar(select(func.count()).select_from(model)) or 0
        if existing:
            logger.info("seed: %s already populated (%d rows) — skipping", model.__tablename__, existing)
            inserted[model.__tablename__] = 0
            continue
        count = 0
        for row in _rows(data_dir / filename):
            db.merge(model(**coerce(row)))  # upsert by PK
            count += 1
        # flush per table: parents become visible in-transaction when the next
        # table's FKs are checked. The commit-time unit-of-work batch order is
        # arbitrary without ORM relationships — postgres caught an FK violation
        # (history before doctors); sqlite never did (FKs off by default)
        db.flush()
        inserted[model.__tablename__] = count
        logger.info("seed: %s <- %s (%d rows)", model.__tablename__, filename, count)
    db.commit()
    return inserted
