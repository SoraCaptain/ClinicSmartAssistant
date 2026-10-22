"""ORM models mirroring mock-data CSVs 1:1 (snake_case, string PKs)."""

from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Clinic(Base):
    __tablename__ = "clinics"

    clinic_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    clinic_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(String(50))
    operating_hours: Mapped[str] = mapped_column(Text)
    cancellation_policy: Mapped[str] = mapped_column(Text)
    emergency_instructions: Mapped[str] = mapped_column(Text)

    doctors: Mapped[list["Doctor"]] = relationship(back_populates="clinic")


class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.clinic_id"))
    full_name: Mapped[str] = mapped_column(String(200))
    specialty: Mapped[str] = mapped_column(String(100))
    languages_spoken: Mapped[str] = mapped_column(String(200))
    consultation_fee_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    bio: Mapped[str] = mapped_column(Text)

    clinic: Mapped[Clinic] = relationship(back_populates="doctors")


class Treatment(Base):
    __tablename__ = "treatments"

    treatment_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    treatment_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    pre_treatment_instructions: Mapped[str] = mapped_column(Text)


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(20))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(200))
    known_allergies: Mapped[str] = mapped_column(Text)
    emergency_contact: Mapped[str] = mapped_column(Text)


class Booking(Base):
    __tablename__ = "patient_bookings"

    booking_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"))
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.doctor_id"))
    treatment_id: Mapped[str] = mapped_column(ForeignKey("treatments.treatment_id"))
    booking_date: Mapped[date] = mapped_column(Date)
    booking_time: Mapped[time] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(20), default="Confirmed")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source: Mapped[str] = mapped_column(String(20), default="chatbot")

    doctor: Mapped[Doctor] = relationship()
    treatment: Mapped[Treatment] = relationship()
    patient: Mapped[Patient] = relationship()


class TreatmentHistory(Base):
    __tablename__ = "patient_treatment_history"

    record_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"))
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.doctor_id"))
    visit_date: Mapped[date] = mapped_column(Date)
    chief_complaint: Mapped[str] = mapped_column(Text)
    diagnosis: Mapped[str] = mapped_column(Text)
    prescribed_medication: Mapped[str] = mapped_column(Text)
    doctor_notes: Mapped[str] = mapped_column(Text)
