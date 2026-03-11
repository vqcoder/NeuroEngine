"""Session-related API routes."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
from threading import Lock as _Lock
from time import monotonic as _monotonic
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .domain_exceptions import DomainError
from .models import Session as SessionModel
from .models import Study, Video
from .readout_cache import invalidate_readout_cache
from .schemas import (
    BatchSessionIngestRequest,
    BatchSessionIngestResponse,
    PlaybackTelemetryIngestRequest,
    PlaybackTelemetryIngestResponse,
    SessionAnnotationIngestRequest,
    SessionAnnotationIngestResponse,
    SessionCaptureIngestRequest,
    SessionCaptureIngestResponse,
    SessionCreate,
    SessionRead,
    SurveyIngestRequest,
    SurveyIngestResponse,
    TraceIngestResponse,
)
from .services_ingestion import (
    bulk_insert_playback_events,
    bulk_insert_session_annotations,
    bulk_insert_survey_responses,
    bulk_insert_trace_points,
    parse_trace_jsonl,
    resolve_participant,
    validate_study_video_link,
)
from .services_capture import (
    derive_capture_ingest_error_code,
    record_capture_ingest_event,
    upsert_session_capture_archive,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trace idempotency cache — prevents duplicate insertion on client retries
# ---------------------------------------------------------------------------
_TRACE_IDEMPOTENCY_TTL = 300  # 5 minutes
_TRACE_IDEMPOTENCY_MAX = 10_000
_trace_idempotency_lock = _Lock()
_trace_idempotency_cache: dict[str, tuple[float, TraceIngestResponse]] = {}


def _check_trace_idempotency(key: str) -> Optional[TraceIngestResponse]:
    """Return cached response if this idempotency key was already processed."""
    with _trace_idempotency_lock:
        entry = _trace_idempotency_cache.get(key)
        if entry is None:
            return None
        expires_at, response = entry
        if _monotonic() >= expires_at:
            _trace_idempotency_cache.pop(key, None)
            return None
        return response


def _store_trace_idempotency(key: str, response: TraceIngestResponse) -> None:
    """Cache a trace ingest response for idempotency dedup."""
    now = _monotonic()
    with _trace_idempotency_lock:
        _trace_idempotency_cache[key] = (now + _TRACE_IDEMPOTENCY_TTL, response)
        # Evict expired entries
        expired = [k for k, (exp, _) in _trace_idempotency_cache.items() if now >= exp]
        for k in expired:
            _trace_idempotency_cache.pop(k, None)
        # Evict oldest if still over capacity
        if len(_trace_idempotency_cache) > _TRACE_IDEMPOTENCY_MAX:
            oldest_key = min(_trace_idempotency_cache, key=lambda k: _trace_idempotency_cache[k][0])
            _trace_idempotency_cache.pop(oldest_key, None)


@router.post("/sessions", response_model=SessionRead, status_code=201)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> SessionModel:
    logger.info("create_session study_id=%s video_id=%s", payload.study_id, payload.video_id)
    study = db.get(Study, payload.study_id)
    video = db.get(Video, payload.video_id)
    validate_study_video_link(study, video)

    participant = resolve_participant(db, payload.study_id, payload.participant)

    session = SessionModel(
        study_id=payload.study_id,
        video_id=payload.video_id,
        participant_id=participant.id,
        status=payload.status,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/sessions/{id}/trace", response_model=TraceIngestResponse)
async def ingest_trace_jsonl(
    id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> TraceIngestResponse:
    logger.info("ingest_trace_jsonl session_id=%s", id)

    # Idempotency: check if this exact request was already processed
    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key:
        cached = _check_trace_idempotency(idempotency_key)
        if cached is not None:
            logger.info("Trace idempotency hit key=%s session_id=%s", idempotency_key, id)
            return cached

    session_model = db.get(SessionModel, id)
    if session_model is None:
        raise HTTPException(status_code=404, detail="Session not found")

    body = await request.body()
    rows, flagged_missing_video_time_ms = parse_trace_jsonl(body)
    inserted = bulk_insert_trace_points(db, session_model, rows)
    db.commit()
    invalidate_readout_cache(session_model.video_id)

    response = TraceIngestResponse(
        session_id=id,
        inserted=inserted,
        flagged_missing_video_time_ms=flagged_missing_video_time_ms,
    )

    if idempotency_key:
        _store_trace_idempotency(idempotency_key, response)

    return response


@router.post("/sessions/{id}/survey", response_model=SurveyIngestResponse)
def ingest_survey_responses(
    id: UUID,
    payload: SurveyIngestRequest,
    db: Session = Depends(get_db),
) -> SurveyIngestResponse:
    logger.info("ingest_survey_responses session_id=%s", id)
    session_model = db.get(SessionModel, id)
    if session_model is None:
        raise HTTPException(status_code=404, detail="Session not found")

    inserted = bulk_insert_survey_responses(db, session_model, payload.responses)
    db.commit()
    invalidate_readout_cache(session_model.video_id)

    return SurveyIngestResponse(session_id=id, inserted=inserted)


@router.post("/sessions/{id}/annotations", response_model=SessionAnnotationIngestResponse)
def ingest_session_annotations(
    id: UUID,
    payload: SessionAnnotationIngestRequest,
    db: Session = Depends(get_db),
) -> SessionAnnotationIngestResponse:
    logger.info("ingest_session_annotations session_id=%s", id)
    session_model = db.get(SessionModel, id)
    if session_model is None:
        raise HTTPException(status_code=404, detail="Session not found")

    inserted = bulk_insert_session_annotations(db, session_model, payload.annotations)
    db.commit()
    invalidate_readout_cache(session_model.video_id)

    return SessionAnnotationIngestResponse(
        session_id=id,
        inserted=inserted,
        annotation_skipped=payload.annotation_skipped,
    )


@router.post("/sessions/{id}/telemetry", response_model=PlaybackTelemetryIngestResponse)
def ingest_playback_telemetry(
    id: UUID,
    payload: PlaybackTelemetryIngestRequest,
    db: Session = Depends(get_db),
) -> PlaybackTelemetryIngestResponse:
    logger.info("ingest_playback_telemetry session_id=%s", id)
    session_model = db.get(SessionModel, id)
    if session_model is None:
        raise HTTPException(status_code=404, detail="Session not found")

    inserted = bulk_insert_playback_events(db, session_model, payload.events)
    db.commit()
    invalidate_readout_cache(session_model.video_id)

    return PlaybackTelemetryIngestResponse(session_id=id, inserted=inserted)


@router.post("/sessions/{id}/captures", response_model=SessionCaptureIngestResponse)
def ingest_session_captures(
    id: UUID,
    payload: SessionCaptureIngestRequest,
    db: Session = Depends(get_db),
) -> SessionCaptureIngestResponse:
    logger.info("ingest_session_captures session_id=%s", id)
    payload_bytes = len(payload.model_dump_json(exclude_none=True).encode("utf-8"))
    frame_count = len(payload.frames)
    frame_pointer_count = len(payload.frame_pointers)
    try:
        if not get_settings().webcam_capture_archive_enabled:
            raise HTTPException(status_code=404, detail="Session capture archive endpoint is disabled")

        session_model = db.get(SessionModel, id)
        if session_model is None:
            raise HTTPException(status_code=404, detail="Session not found")

        response = upsert_session_capture_archive(db, session_model, payload)
        record_capture_ingest_event(
            db,
            session_id=session_model.id,
            video_id=session_model.video_id,
            outcome="success",
            status_code=200,
            error_code=None,
            frame_count=response.frame_count,
            frame_pointer_count=response.frame_pointer_count,
            payload_bytes=response.uncompressed_bytes,
        )
        db.commit()
        return response
    except HTTPException as exc:
        error_code = derive_capture_ingest_error_code(exc.status_code, str(exc.detail))
        record_capture_ingest_event(
            db,
            session_id=id,
            video_id=payload.video_id if hasattr(payload, "video_id") else None,
            outcome="failure",
            status_code=exc.status_code,
            error_code=error_code,
            frame_count=frame_count,
            frame_pointer_count=frame_pointer_count,
            payload_bytes=payload_bytes,
        )
        db.commit()
        raise
    except DomainError as exc:
        # Map domain exceptions (ValidationError → 400, PayloadTooLarge → 413, etc.)
        # to HTTP status codes so the global handler doesn't compete with the
        # generic Exception catch below.
        status = {
            "ValidationError": 400,
            "PayloadTooLargeError": 413,
            "NotFoundError": 404,
            "UnprocessableError": 422,
            "ServiceUnavailableError": 503,
        }.get(type(exc).__name__, 400)
        error_code = derive_capture_ingest_error_code(status, str(exc))
        record_capture_ingest_event(
            db,
            session_id=id,
            video_id=payload.video_id if hasattr(payload, "video_id") else None,
            outcome="failure",
            status_code=status,
            error_code=error_code,
            frame_count=frame_count,
            frame_pointer_count=frame_pointer_count,
            payload_bytes=payload_bytes,
        )
        db.commit()
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        db.rollback()
        record_capture_ingest_event(
            db,
            session_id=id,
            video_id=payload.video_id if hasattr(payload, "video_id") else None,
            outcome="failure",
            status_code=500,
            error_code="unexpected_error",
            frame_count=frame_count,
            frame_pointer_count=frame_pointer_count,
            payload_bytes=payload_bytes,
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"Capture archive ingest failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Atomic batch ingest (R23)
# ---------------------------------------------------------------------------


@router.post("/sessions/batch-ingest", response_model=BatchSessionIngestResponse, status_code=201)
def batch_ingest_session(
    payload: BatchSessionIngestRequest,
    db: Session = Depends(get_db),
) -> BatchSessionIngestResponse:
    """Create a session and ingest all associated data atomically.

    Replaces the multi-step upload flow (create session → trace → telemetry →
    annotations → survey → captures) with a single DB transaction.  On any
    failure the entire transaction rolls back — no partial state.
    """
    logger.info(
        "batch_ingest_session study_id=%s video_id=%s",
        payload.study_id,
        payload.video_id,
    )

    try:
        # 1. Validate study + video
        study = db.get(Study, payload.study_id)
        video = db.get(Video, payload.video_id)
        validate_study_video_link(study, video)

        # 2. Resolve participant
        participant = resolve_participant(db, payload.study_id, payload.participant)

        # 3. Create session
        session = SessionModel(
            study_id=payload.study_id,
            video_id=payload.video_id,
            participant_id=participant.id,
            status=payload.status,
        )
        db.add(session)
        db.flush()  # obtain session.id without committing

        trace_inserted = 0
        trace_flagged = 0
        telemetry_inserted = 0
        annotations_inserted = 0
        survey_inserted = 0
        capture_archived = False
        capture_frame_count = 0
        capture_pointer_count = 0

        # 4. Parse + insert trace points
        if payload.trace_jsonl.strip():
            rows, trace_flagged = parse_trace_jsonl(payload.trace_jsonl.encode("utf-8"))
            trace_inserted = bulk_insert_trace_points(db, session, rows)

        # 5. Insert telemetry events
        if payload.telemetry_events:
            telemetry_inserted = bulk_insert_playback_events(
                db, session, payload.telemetry_events,
            )

        # 6. Insert annotations
        if payload.annotations:
            annotations_inserted = bulk_insert_session_annotations(
                db, session, payload.annotations,
            )

        # 7. Insert survey responses
        if payload.survey_responses:
            survey_inserted = bulk_insert_survey_responses(
                db, session, payload.survey_responses,
            )

        # 8. Insert captures (optional — skipped when archive is disabled)
        has_captures = bool(payload.capture_frames or payload.capture_frame_pointers)
        if has_captures and get_settings().webcam_capture_archive_enabled:
            capture_req = SessionCaptureIngestRequest(
                video_id=payload.capture_video_id or payload.video_id,
                frames=payload.capture_frames,
                frame_pointers=payload.capture_frame_pointers,
            )
            capture_resp = upsert_session_capture_archive(db, session, capture_req)
            capture_archived = True
            capture_frame_count = capture_resp.frame_count
            capture_pointer_count = capture_resp.frame_pointer_count

        # 9. Single atomic commit
        db.commit()
        db.refresh(session)

        # 10. Invalidate readout cache
        invalidate_readout_cache(payload.video_id)

        return BatchSessionIngestResponse(
            session_id=session.id,
            study_id=payload.study_id,
            video_id=payload.video_id,
            trace_inserted=trace_inserted,
            trace_flagged_missing_video_time_ms=trace_flagged,
            telemetry_inserted=telemetry_inserted,
            annotations_inserted=annotations_inserted,
            annotation_skipped=payload.annotation_skipped,
            survey_inserted=survey_inserted,
            capture_archived=capture_archived,
            capture_frame_count=capture_frame_count,
            capture_pointer_count=capture_pointer_count,
        )
    except Exception:
        db.rollback()
        raise
