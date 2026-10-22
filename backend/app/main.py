"""FastAPI app: lifespan (create_all + seed-if-empty, P4), CORS for split-origin dev."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging
from app.database import Base, SessionLocal, engine
from app.routers import bookings, catalog, health, patients
from app.services.seed_service import seed

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    logger.info("startup complete: schema ensured, seed applied if empty")
    yield


app = FastAPI(title="ClinicPilot Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(bookings.router)
app.include_router(patients.router)
