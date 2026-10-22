from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.booking import BookingCreate, BookingJoined, BookingOut
from app.services import booking_service

router = APIRouter(prefix="/api", tags=["bookings"])


@router.get("/bookings", response_model=list[BookingJoined])
def list_bookings(patient_id: str | None = None, db: Session = Depends(get_db)):
    return booking_service.list_bookings(db, patient_id=patient_id)


@router.post("/bookings", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    return booking_service.create_booking(db, payload)
