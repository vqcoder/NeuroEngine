"""Analyst View routes – admin session browser."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .schemas import AnalystSessionsResponse
from .services_analyst import list_analyst_sessions

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/analyst/videos/{video_id}/sessions",
    response_model=AnalystSessionsResponse,
)
def get_analyst_sessions(
    video_id: UUID,
    db: Session = Depends(get_db),
) -> AnalystSessionsResponse:
    """List all sessions for a video with survey, capture, and trace metadata."""
    return list_analyst_sessions(db, video_id)
