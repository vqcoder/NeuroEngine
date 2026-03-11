"""Observability and maintenance routes."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .neuro_observability import build_neuro_observability_status
from .schemas import (
    CaptureArchiveObservabilityStatusResponse,
    CaptureArchivePurgeResponse,
    FrontendDiagnosticEventIn,
    FrontendDiagnosticEventRead,
    FrontendDiagnosticEventsResponse,
    FrontendDiagnosticSummaryResponse,
    NeuroObservabilityStatusResponse,
    PredictJobsObservabilityStatus,
)
from .services_capture import (
    build_capture_archive_observability_status,
    purge_expired_capture_archives,
)
from .services_diagnostics import (
    build_frontend_diagnostic_summary,
    list_frontend_diagnostic_events,
    record_frontend_diagnostic_event,
)

from .runtime_stats import (
    predict_stats as _predict_stats,
    predict_stats_lock as _predict_stats_lock,
    github_upload_stats as _github_upload_stats,
    github_upload_stats_lock as _github_upload_stats_lock,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/observability/neuro", response_model=NeuroObservabilityStatusResponse)
def get_neuro_observability_status() -> NeuroObservabilityStatusResponse:
    runtime_settings = get_settings()
    status_payload = build_neuro_observability_status(
        enabled=runtime_settings.neuro_observability_enabled,
        history_path=runtime_settings.neuro_observability_history_path,
        history_max_entries=runtime_settings.neuro_observability_history_max_entries,
        drift_alert_threshold=runtime_settings.neuro_observability_drift_alert_threshold,
    )
    return NeuroObservabilityStatusResponse.model_validate(status_payload)


@router.get(
    "/observability/capture-archives",
    response_model=CaptureArchiveObservabilityStatusResponse,
)
def get_capture_archive_observability_status(
    db: Session = Depends(get_db),
) -> CaptureArchiveObservabilityStatusResponse:
    return build_capture_archive_observability_status(db)


@router.post(
    "/observability/frontend-diagnostics/events",
    response_model=FrontendDiagnosticEventRead,
    status_code=201,
)
def ingest_frontend_diagnostic_event(
    payload: FrontendDiagnosticEventIn,
    db: Session = Depends(get_db),
) -> FrontendDiagnosticEventRead:
    logger.info("ingest_frontend_diagnostic_event event_type=%s", payload.event_type)
    event = record_frontend_diagnostic_event(db, payload)
    db.commit()
    return event


@router.get(
    "/observability/frontend-diagnostics/events",
    response_model=FrontendDiagnosticEventsResponse,
)
def get_frontend_diagnostic_events(
    limit: int = Query(default=50, ge=1, le=200),
    surface: Optional[str] = Query(default=None),
    page: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> FrontendDiagnosticEventsResponse:
    return list_frontend_diagnostic_events(
        db,
        limit=limit,
        surface=surface,
        page=page,
        severity=severity,
        event_type=event_type,
    )


@router.get(
    "/observability/frontend-diagnostics/summary",
    response_model=FrontendDiagnosticSummaryResponse,
)
def get_frontend_diagnostic_summary(
    window_hours: int = Query(default=24, ge=1, le=168),
    top_n: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
) -> FrontendDiagnosticSummaryResponse:
    return build_frontend_diagnostic_summary(
        db,
        window_hours=window_hours,
        top_n=top_n,
    )


@router.post(
    "/maintenance/capture-archives/purge",
    response_model=CaptureArchivePurgeResponse,
)
def run_capture_archive_purge(
    dry_run: bool = Query(default=True, description="Preview purge candidates without deleting rows."),
    db: Session = Depends(get_db),
) -> CaptureArchivePurgeResponse:
    logger.info("run_capture_archive_purge dry_run=%s", dry_run)
    result = purge_expired_capture_archives(db, dry_run=dry_run)
    if not dry_run and result.enabled:
        db.commit()
    return result


@router.get("/observability/predict-jobs", response_model=PredictJobsObservabilityStatus)
def get_predict_jobs_observability() -> PredictJobsObservabilityStatus:
    """Return predict job queue stats and GitHub upload health."""
    with _predict_stats_lock:
        stats = dict(_predict_stats)
    with _github_upload_stats_lock:
        upload = dict(_github_upload_stats)
    attempts = upload["attempts"]
    successes = upload["successes"]
    success_rate = round(successes / attempts, 4) if attempts > 0 else None
    return PredictJobsObservabilityStatus(
        active_jobs=stats["active"],
        queued_total=stats["queued"],
        completed_total=stats["completed"],
        failed_total=stats["failed"],
        github_upload_attempts=attempts,
        github_upload_successes=successes,
        github_upload_failures=upload["failures"],
        github_upload_success_rate=success_rate,
    )
