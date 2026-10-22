"""Idempotent seed entrypoint: `python -m scripts.seed` (run from backend/)."""

import logging

from app.core.logging import configure_logging
from app.database import Base, SessionLocal, engine
from app.services.seed_service import seed


def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("creating tables if needed")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        inserted = seed(db)
    print(f"seed complete (0 = table already populated): {inserted}")


if __name__ == "__main__":
    main()
