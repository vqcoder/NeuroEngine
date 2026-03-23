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
from sqlalchemy import inspect, text

from .db import engine

logger = logging.getLogger(__name__)

# Arbitrary but fixed lock ID so every replica contends on the same key.
_ADVISORY_LOCK_ID = 72813

# Tables that indicate the schema was created outside of Alembic (e.g. via
# Supabase MCP migrations).  If these exist but ``alembic_version`` does not,
# we stamp ``head`` instead of running ``upgrade head`` to avoid re-creating
# objects that already exist.
_CORE_TABLES = frozenset({"studies", "videos", "sessions", "trace_points", "survey_responses"})


def _schema_exists_without_alembic() -> bool:
    """Return *True* if core tables exist but Alembic has never been run."""

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    has_core = _CORE_TABLES.issubset(existing_tables)
    has_alembic = "alembic_version" in existing_tables
    if has_core and not has_alembic:
        logger.info(
            "Core tables present (%s) but alembic_version missing — schema was "
            "created outside of Alembic.",
            ", ".join(sorted(_CORE_TABLES & existing_tables)),
        )
        return True
    return False


def run_migrations_with_lock() -> None:
    """Acquire a PostgreSQL advisory lock, then run Alembic migrations.

    If the lock cannot be acquired (another replica is migrating), the function
    waits briefly and returns without error so the application can proceed.

    On non-PostgreSQL backends (e.g. SQLite in tests), advisory locks are
    unavailable so the function skips locking and runs migrations directly.
    """

    # Detect schemas created outside of Alembic (e.g. Supabase MCP) and stamp
    # head so that future migrations start from the right place.
    if _schema_exists_without_alembic():
        logger.info("Stamping alembic head instead of running migrations.")
        cfg = AlembicConfig("alembic.ini")
        alembic_command.stamp(cfg, "head")
        logger.info("Alembic stamp head completed successfully.")
        return

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
