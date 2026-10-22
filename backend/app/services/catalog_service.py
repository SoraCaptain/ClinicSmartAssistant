"""Catalog reads with case-insensitive contains-match (§5.3) — exact recall on an 11-row corpus."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Clinic, Doctor, Treatment


def get_clinics(db: Session, clinic_id: str | None = None) -> list[Clinic]:
    stmt = select(Clinic)
    if clinic_id:
        stmt = stmt.where(Clinic.clinic_id == clinic_id)
    return list(db.scalars(stmt.order_by(Clinic.clinic_id)))


def get_doctors(db: Session, specialty: str | None = None) -> list[Doctor]:
    stmt = select(Doctor)
    if specialty:
        stmt = stmt.where(Doctor.specialty.icontains(specialty, autoescape=True))
    return list(db.scalars(stmt.order_by(Doctor.doctor_id)))


def search_treatments(db: Session, search: str | None = None) -> list[Treatment]:
    stmt = select(Treatment)
    if search:
        stmt = stmt.where(
            or_(
                Treatment.treatment_name.icontains(search, autoescape=True),
                Treatment.category.icontains(search, autoescape=True),
                Treatment.pre_treatment_instructions.icontains(search, autoescape=True),
            )
        )
    return list(db.scalars(stmt.order_by(Treatment.treatment_id)))
