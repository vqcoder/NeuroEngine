"""Safe database migration with PostgreSQL advisory lock.

Ensures only one replica runs ``alembic upgrade head`` at a time.  If another
process already holds the lock, this replica logs a message and returns
immediately -- the other replica will finish the migration.

Can be called as ``python -m app.migrate`` for standalone use, or imported and
invoked via :func:`run_migrations_with_lock` during app startup.
"""

from __future__ import annotations

import logging
import time

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text

from .db import engine

logger = logging.getLogger(__name__)

# Arbitrary but fixed lock ID so every replica contends on the same key.
_ADVISORY_LOCK_ID = 72813


def run_migrations_with_lock() -> None:
    """Acquire a PostgreSQL advisory lock, then run Alembic migrations.

    If the lock cannot be acquired (another replica is migrating), the function
    waits briefly and returns without error so the application can proceed.

    On non-PostgreSQL backends (e.g. SQLite in tests), advisory locks are
    unavailable so the function skips locking and runs migrations directly.
    """

    # Advisory locks are PostgreSQL-specific; skip on other dialects.
    if engine.dialect.name != "postgresql":
        logger.info("Non-PostgreSQL backend (%s) — running migrations without advisory lock.", engine.dialect.name)
        try:
            cfg = AlembicConfig("alembic.ini")
            alembic_command.upgrade(cfg, "head")
            logger.info("Alembic migrations completed successfully.")
        except Exception:
            logger.exception("Alembic migration failed.")
            raise
        return

    with engine.connect() as conn:
        # pg_try_advisory_lock is session-level and non-blocking.
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": _ADVISORY_LOCK_ID},
        ).scalar()

        if acquired:
            try:
                logger.info("Advisory lock acquired -- running Alembic migrations ...")
                cfg = AlembicConfig("alembic.ini")
                alembic_command.upgrade(cfg, "head")
                logger.info("Alembic migrations completed successfully.")
            except Exception:
                logger.exception("Alembic migration failed.")
                raise
            finally:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _ADVISORY_LOCK_ID},
                )
                conn.commit()
                logger.info("Advisory lock released.")
        else:
            logger.info(
                "Advisory lock not acquired -- another replica is migrating. "
                "Waiting briefly before proceeding ..."
            )
            time.sleep(3)
            logger.info("Proceeding with application startup.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .db import wait_for_db  # noqa: PLC0415

    wait_for_db()
    run_migrations_with_lock()
