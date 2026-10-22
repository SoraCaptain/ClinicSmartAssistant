from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.health import HealthOut

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        db_state = "up"
    except Exception:
        db_state = "down"
    return HealthOut(status="ok" if db_state == "up" else "degraded", db=db_state)
