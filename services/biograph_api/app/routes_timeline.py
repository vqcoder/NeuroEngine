"""Timeline analysis routes."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .db import get_db
from .schemas import (
    TimelineAnalysisJobResponse,
    TimelineAnalysisRequest,
    TimelineFeatureWindowResponse,
)
from .timeline_feature_store import (
    TimelineAnalysisExecutionContext,
    complete_timeline_analysis_job,
    get_timeline_analysis_job,
    prepare_timeline_analysis_job,
    query_timeline_features_window,
    run_timeline_analysis_job,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Background helper
# ---------------------------------------------------------------------------

def _run_timeline_analysis_background(
    execution_context: TimelineAnalysisExecutionContext,
    engine: Engine,
) -> None:
    background_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    db = background_session_factory()
    try:
        complete_timeline_analysis_job(db, execution_context)
    except Exception:
        logger.exception(
            "Background timeline analysis failed",
            extra={"analysis_id": str(execution_context.analysis_id)},
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/videos/{id}/timeline-analysis", response_model=TimelineAnalysisJobResponse)
def run_video_timeline_analysis(
    id: UUID,
    background_tasks: BackgroundTasks,
    payload: Optional[TimelineAnalysisRequest] = None,
    db: Session = Depends(get_db),
) -> TimelineAnalysisJobResponse:
    logger.info("run_video_timeline_analysis video_id=%s", id)
    request_payload = payload or TimelineAnalysisRequest()
    if request_payload.run_async:
        prepared = prepare_timeline_analysis_job(db, id, request_payload)
        if prepared.execution_context is not None:
            bound_engine = db.get_bind()
            background_tasks.add_task(
                _run_timeline_analysis_background,
                prepared.execution_context,
                bound_engine,
            )
        return prepared.response
    return run_timeline_analysis_job(db, id, request_payload)


@router.get("/timeline-analysis/{analysis_id}", response_model=TimelineAnalysisJobResponse)
def get_video_timeline_analysis_job(
    analysis_id: UUID,
    db: Session = Depends(get_db),
) -> TimelineAnalysisJobResponse:
    return get_timeline_analysis_job(db, analysis_id)


@router.get("/timeline-features/{asset_id}", response_model=TimelineFeatureWindowResponse)
def get_timeline_feature_window(
    asset_id: str,
    start_ms: int = Query(default=0, ge=0),
    end_ms: Optional[int] = Query(default=None, ge=1),
    analysis_version: str = Query(default="timeline_v1", min_length=1, max_length=64),
    track_name: Optional[list[str]] = Query(default=None),
    segment_type: Optional[list[str]] = Query(default=None),
    db: Session = Depends(get_db),
) -> TimelineFeatureWindowResponse:
    return query_timeline_features_window(
        db,
        asset_id=asset_id,
        start_ms=start_ms,
        end_ms=end_ms,
        analysis_version=analysis_version,
        track_names=track_name,
        segment_types=segment_type,
    )
