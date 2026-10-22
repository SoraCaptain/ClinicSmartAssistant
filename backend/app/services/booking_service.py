"""Booking creation (FK existence + server-generated id; no conflict check by design) and joined reads (P5)."""

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Clinic, Doctor, Patient, Treatment, TreatmentHistory
from app.schemas.booking import BookingCreate, BookingJoined
from app.schemas.catalog import HistoryOut


def _new_booking_id() -> str:
    return "B" + uuid.uuid4().hex[:10]


def list_bookings(db: Session, patient_id: str | None = None) -> list[BookingJoined]:
    stmt = (
        select(Booking, Doctor, Treatment, Clinic)
        .join(Doctor, Booking.doctor_id == Doctor.doctor_id)
        .join(Treatment, Booking.treatment_id == Treatment.treatment_id)
        .join(Clinic, Doctor.clinic_id == Clinic.clinic_id)
        .order_by(Booking.booking_date, Booking.booking_time)
    )
    if patient_id:
        stmt = stmt.where(Booking.patient_id == patient_id)
    return [
        BookingJoined(
            booking_id=b.booking_id,
            patient_id=b.patient_id,
            doctor_id=b.doctor_id,
            treatment_id=b.treatment_id,
            booking_date=b.booking_date,
            booking_time=b.booking_time,
            status=b.status,
            notes=b.notes,
            created_at=b.created_at,
            source=b.source,
            doctor_name=d.full_name,
            doctor_specialty=d.specialty,
            treatment_name=t.treatment_name,
            clinic_id=c.clinic_id,
            clinic_name=c.clinic_name,
        )
        for b, d, t, c in db.execute(stmt)
    ]


def create_booking(db: Session, payload: BookingCreate) -> Booking:
    """Validate FK existence (unknown id → 422), then persist with a server-generated booking_id."""
    for model, label, value in (
        (Patient, "patient_id", payload.patient_id),
        (Doctor, "doctor_id", payload.doctor_id),
        (Treatment, "treatment_id", payload.treatment_id),
    ):
        if db.scalar(select(model).where(getattr(model, label) == value)) is None:
            raise HTTPException(status_code=422, detail=f"Unknown {label}: {value}")
    booking = Booking(
        booking_id=_new_booking_id(),
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        treatment_id=payload.treatment_id,
        booking_date=payload.booking_date,
        booking_time=payload.booking_time,
        notes=payload.notes,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_patient_context(db: Session, patient_id: str) -> dict:
    patient = db.scalar(select(Patient).where(Patient.patient_id == patient_id))
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient_id: {patient_id}")
    history = [
        HistoryOut(
            record_id=h.record_id,
            patient_id=h.patient_id,
            doctor_id=h.doctor_id,
            visit_date=h.visit_date,
            chief_complaint=h.chief_complaint,
            diagnosis=h.diagnosis,
            prescribed_medication=h.prescribed_medication,
            doctor_notes=h.doctor_notes,
            doctor_name=doctor_name,
        )
        for h, doctor_name in db.execute(
            select(TreatmentHistory, Doctor.full_name)
            .join(Doctor, TreatmentHistory.doctor_id == Doctor.doctor_id)
            .where(TreatmentHistory.patient_id == patient_id)
            .order_by(TreatmentHistory.visit_date.desc())
        )
    ]
    upcoming = list_bookings(db, patient_id=patient_id)
    today = date.today()
    return {
        "profile": patient,
        "treatment_history": history,
        "upcoming_bookings": [b for b in upcoming if b.booking_date >= today],
    }
