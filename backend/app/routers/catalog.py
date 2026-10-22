from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.catalog import ClinicOut, DoctorOut, TreatmentOut
from app.services import catalog_service

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/clinics", response_model=list[ClinicOut])
def list_clinics(clinic_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    return catalog_service.get_clinics(db, clinic_id=clinic_id)


@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(specialty: str | None = Query(default=None), db: Session = Depends(get_db)):
    return catalog_service.get_doctors(db, specialty=specialty)


@router.get("/treatments", response_model=list[TreatmentOut])
def list_treatments(search: str | None = Query(default=None), db: Session = Depends(get_db)):
    return catalog_service.search_treatments(db, search=search)
