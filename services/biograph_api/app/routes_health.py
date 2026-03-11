"""Health check endpoints."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import engine, get_db
from .download_service import check_youtube_download_readiness
from .readout_guardian import ReadoutGuardianError, enforce_readout_guardian

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict:
    """Deep health check — verifies database connectivity and pool saturation."""
    checks: dict[str, str] = {}
    healthy = True

    # Database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        logger.warning("Health check: database unreachable", exc_info=True)
        checks["database"] = "unreachable"
        healthy = False

    # Readout guardian
    try:
        enforce_readout_guardian()
        checks["readout_guardian"] = "ok"
    except ReadoutGuardianError as exc:
        logger.warning("Health check: readout guardian failed: %s", exc)
        checks["readout_guardian"] = str(exc)[:200]
        healthy = False

    # YouTube download readiness (cookies + residential proxy)
    yt_readiness = check_youtube_download_readiness()
    checks["youtube_download"] = yt_readiness["status"]

    # Connection pool stats
    pool = engine.pool
    pool_info = {
        "size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "checked_in": pool.checkedin(),
    }

    if not healthy:
        response.status_code = 503

    return {
        "ok": healthy,
        "checks": checks,
        "pool": pool_info,
        "youtube_download": yt_readiness,
    }


@router.get("/")
def root() -> dict:
    return {"ok": True, "service": "biograph_api", "v": "2026-03-09b"}
