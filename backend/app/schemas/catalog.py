"""Catalog read models (agent tools consume these — keep fields flat and complete)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ClinicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clinic_id: str
    clinic_name: str
    address: str
    phone: str
    operating_hours: str
    cancellation_policy: str
    emergency_instructions: str


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    doctor_id: str
    clinic_id: str
    full_name: str
    specialty: str
    languages_spoken: str
    consultation_fee_usd: Decimal
    bio: str


class TreatmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    treatment_id: str
    treatment_name: str
    category: str
    duration_minutes: int
    price_usd: Decimal
    pre_treatment_instructions: str


class PatientProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    first_name: str
    last_name: str
    dob: date
    gender: str
    phone: str
    email: str
    known_allergies: str
    emergency_contact: str


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: str
    patient_id: str
    doctor_id: str
    doctor_name: str
    visit_date: date
    chief_complaint: str
    diagnosis: str
    prescribed_medication: str
    doctor_notes: str
