"""Database engine and session management."""

from __future__ import annotations

import logging
import time
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base model."""


settings = get_settings()
engine = create_engine(
    settings.normalized_database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_timeout=30,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield request-scoped database session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(max_attempts: int = 5, base_delay: float = 2.0) -> None:
    """Block until the database is reachable, with exponential backoff.

    Raises ``RuntimeError`` after *max_attempts* consecutive failures so the
    process can crash-loop rather than start in a broken state.
    """

    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection established (attempt %d/%d).", attempt, max_attempts)
            return
        except Exception as exc:  # noqa: BLE001
            if attempt == max_attempts:
                logger.error(
                    "Could not connect to database after %d attempts: %s",
                    max_attempts,
                    exc,
                )
                raise RuntimeError(
                    f"Database unavailable after {max_attempts} attempts"
                ) from exc
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Database connection attempt %d/%d failed (%s). Retrying in %.1fs ...",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)
