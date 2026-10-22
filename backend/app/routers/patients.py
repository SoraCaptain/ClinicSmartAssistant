from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.patient import PatientContextOut
from app.services import booking_service

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("/{patient_id}/context", response_model=PatientContextOut)
def patient_context(patient_id: str, db: Session = Depends(get_db)):
    return booking_service.get_patient_context(db, patient_id)
