"""Readout, reliability, and export-package routes."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
import threading
from time import monotonic
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as _sql_func
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import SessionPlaybackEvent as PlaybackEvent, Session as SessionModel, TracePoint, Video
from .readout_cache import (
    build_readout_cache_key,
    read_readout_cache,
    resolve_dual_query_param,
    write_readout_cache,
)
from .schemas import (
    CatalogReliabilityItem,
    CatalogReliabilityReport,
    ProductRollupMode,
    ReadoutExportPackageResponse,
    ReadoutPayload,
    ReadoutPreflightIssue,
    ReadoutPreflightResponse,
    ReadoutReliabilityScore,
)
from .services_readout import build_video_readout
from .services_readout_export import build_video_readout_export_package
from .services_readout import build_reliability_schema

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/videos/{video_id}/readout", response_model=ReadoutPayload)
def get_video_readout(
    video_id: UUID,
    session_id: Optional[UUID] = Query(default=None, description="Session mode filter."),
    session_id_legacy: Optional[UUID] = Query(default=None, alias="sessionId", include_in_schema=False),
    variant_id: Optional[str] = Query(default=None, description="Variant filter for scene graph/readout."),
    variant_id_legacy: Optional[str] = Query(default=None, alias="variantId", include_in_schema=False),
    aggregate: bool = Query(default=True),
    window_ms: int = Query(default=1000, ge=100, le=10000),
    window_ms_legacy: Optional[int] = Query(default=None, ge=100, le=10000, alias="windowMs", include_in_schema=False),
    product_mode: Optional[ProductRollupMode] = Query(
        default=None, description="Product presentation mode override."
    ),
    product_mode_legacy: Optional[ProductRollupMode] = Query(
        default=None, alias="productMode", include_in_schema=False
    ),
    workspace_tier: Optional[str] = Query(
        default=None, description="Workspace/account tier for product mode gating."
    ),
    workspace_tier_legacy: Optional[str] = Query(
        default=None, alias="workspaceTier", include_in_schema=False
    ),
    db: Session = Depends(get_db),
) -> ReadoutPayload:
    resolved_session_id = resolve_dual_query_param(
        canonical_value=session_id,
        legacy_value=session_id_legacy,
        canonical_name="session_id",
        legacy_name="sessionId",
    )
    resolved_variant_id = resolve_dual_query_param(
        canonical_value=variant_id,
        legacy_value=variant_id_legacy,
        canonical_name="variant_id",
        legacy_name="variantId",
    )
    resolved_window_ms = resolve_dual_query_param(
        canonical_value=window_ms,
        legacy_value=window_ms_legacy,
        canonical_name="window_ms",
        legacy_name="windowMs",
    )
    resolved_product_mode = resolve_dual_query_param(
        canonical_value=product_mode,
        legacy_value=product_mode_legacy,
        canonical_name="product_mode",
        legacy_name="productMode",
    )
    resolved_workspace_tier = resolve_dual_query_param(
        canonical_value=workspace_tier,
        legacy_value=workspace_tier_legacy,
        canonical_name="workspace_tier",
        legacy_name="workspaceTier",
    )
    cache_key = build_readout_cache_key(
        video_id=video_id,
        session_id=resolved_session_id,
        variant_id=resolved_variant_id,
        aggregate=aggregate,
        window_ms=resolved_window_ms,
        product_mode=resolved_product_mode,
        workspace_tier=resolved_workspace_tier,
    )
    cached = read_readout_cache(cache_key)
    if cached is not None:
        return cached

    payload = build_video_readout(
        db,
        video_id,
        session_id=resolved_session_id,
        variant_id=resolved_variant_id,
        aggregate=aggregate,
        window_ms=resolved_window_ms,
        product_mode=resolved_product_mode,
        workspace_tier=resolved_workspace_tier,
    )
    validated = ReadoutPayload.model_validate(payload.model_dump())
    write_readout_cache(cache_key, validated)
    return validated


@router.get("/videos/{video_id}/readout/check", response_model=ReadoutPreflightResponse)
def check_video_readout_preflight(
    video_id: UUID,
    session_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
) -> ReadoutPreflightResponse:
    """Pre-flight readiness check for a video readout."""

    issues: list[ReadoutPreflightIssue] = []

    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        return ReadoutPreflightResponse(
            video_id=video_id,
            ready=False,
            issues=[ReadoutPreflightIssue(severity="error", code="video_not_found", message="Video not found.")],
        )

    session_filter = [SessionModel.video_id == video_id]
    if session_id is not None:
        session_filter.append(SessionModel.id == session_id)

    sessions = db.query(SessionModel).filter(*session_filter).all()
    session_ids = [s.id for s in sessions]

    if not session_ids:
        issues.append(ReadoutPreflightIssue(
            severity="error",
            code="no_sessions",
            message="No sessions found for this video. Watch data is required for a readout.",
        ))
        return ReadoutPreflightResponse(video_id=video_id, ready=False, issues=issues)

    total_trace_points = (
        db.query(TracePoint)
        .filter(TracePoint.session_id.in_(session_ids))
        .count()
    )

    if total_trace_points == 0:
        issues.append(ReadoutPreflightIssue(
            severity="error",
            code="no_trace_data",
            message="Sessions exist but contain no trace data. Readout cannot be computed.",
        ))
        return ReadoutPreflightResponse(
            video_id=video_id,
            ready=False,
            issues=issues,
            sessions_with_trace=0,
            total_trace_points=0,
            duration_ms=video.duration_ms,
        )

    sessions_with_data = (
        db.query(TracePoint.session_id)
        .filter(TracePoint.session_id.in_(session_ids))
        .group_by(TracePoint.session_id)
        .count()
    )

    if total_trace_points < 3:
        issues.append(ReadoutPreflightIssue(
            severity="warning",
            code="insufficient_trace_points",
            message=f"Only {total_trace_points} trace point(s) found — readout quality will be very low.",
        ))

    blink_count = (
        db.query(TracePoint)
        .filter(TracePoint.session_id.in_(session_ids), TracePoint.blink.is_(True))
        .count()
    )
    if blink_count == 0:
        issues.append(ReadoutPreflightIssue(
            severity="warning",
            code="no_blink_events",
            message=(
                "No blink events detected across all trace points. "
                "Blink rate will be derived from variance correction rather than measured data."
            ),
        ))

    trace_source_events = (
        db.query(PlaybackEvent)
        .filter(
            PlaybackEvent.session_id.in_(session_ids),
            PlaybackEvent.event_type == "trace_source",
        )
        .all()
    )
    fallback_sessions = []
    for event in trace_source_events:
        details = event.details or {}
        if details.get("trace_source") == "synthetic_fallback":
            fallback_sessions.append(str(event.session_id))
    if fallback_sessions:
        issues.append(ReadoutPreflightIssue(
            severity="warning",
            code="synthetic_fallback_trace",
            message=(
                f"{len(fallback_sessions)} session(s) used synthetic (no-webcam) fallback trace. "
                "Blink rate will be estimated rather than measured."
            ),
        ))

    max_video_time = (
        db.query(_sql_func.max(TracePoint.video_time_ms))
        .filter(TracePoint.session_id.in_(session_ids))
        .scalar()
    ) or 0

    duration_ms = video.duration_ms
    estimated_usable_seconds: Optional[float] = None

    if duration_ms is None:
        issues.append(ReadoutPreflightIssue(
            severity="info",
            code="duration_ms_missing",
            message=(
                "video.duration_ms is not set. usable_seconds will be estimated from trace extent. "
                "Run a new predict job to capture accurate duration."
            ),
        ))
        estimated_usable_seconds = round((max_video_time + 1000) / 1000.0, 3)
    else:
        estimated_usable_seconds = round(duration_ms / 1000.0, 3)
        if duration_ms > 0 and max_video_time > 0:
            coverage_ratio = max_video_time / duration_ms
            if coverage_ratio < 0.4:
                issues.append(ReadoutPreflightIssue(
                    severity="warning",
                    code="low_trace_coverage",
                    message=(
                        f"Trace data covers only {coverage_ratio:.0%} of video duration "
                        f"({max_video_time / 1000:.1f}s of {duration_ms / 1000:.1f}s). "
                        "usable_seconds may be misleading."
                    ),
                ))

    ready = not any(i.severity == "error" for i in issues)
    return ReadoutPreflightResponse(
        video_id=video_id,
        ready=ready,
        issues=issues,
        sessions_with_trace=sessions_with_data,
        total_trace_points=total_trace_points,
        duration_ms=duration_ms,
        estimated_usable_seconds=estimated_usable_seconds,
    )


@router.get("/videos/{video_id}/readout/reliability", response_model=ReadoutReliabilityScore)
def get_video_readout_reliability(
    video_id: UUID,
    session_id: Optional[UUID] = Query(default=None),
    aggregate: bool = Query(default=True),
    window_ms: int = Query(default=1000, ge=100, le=10000),
    db: Session = Depends(get_db),
) -> ReadoutReliabilityScore:
    """Compute and return only the reliability score for a recording."""
    from .reliability_engine import compute_reliability_score as _compute_rel
    payload = build_video_readout(
        db,
        video_id,
        session_id=session_id,
        aggregate=aggregate,
        window_ms=window_ms,
    )
    _rel = _compute_rel(payload)
    return build_reliability_schema(_rel)


# ---------------------------------------------------------------------------
# Reliability report response-level cache (Q12 — amortizes N+1 query cost)
# ---------------------------------------------------------------------------
_RELIABILITY_REPORT_CACHE_TTL = 60  # seconds
_reliability_report_cache: dict[str, tuple[float, CatalogReliabilityReport]] = {}
_reliability_report_cache_lock = threading.Lock()


@router.get("/reliability-report", response_model=CatalogReliabilityReport)
def get_catalog_reliability_report(
    limit: int = Query(default=50, ge=1, le=200),
    window_ms: int = Query(default=1000, ge=100, le=10000),
    db: Session = Depends(get_db),
) -> CatalogReliabilityReport:
    """Rescore every video in the catalog and return a reliability report."""
    cache_key = f"{limit}:{window_ms}"
    with _reliability_report_cache_lock:
        if cache_key in _reliability_report_cache:
            cached_at, cached_report = _reliability_report_cache[cache_key]
            if monotonic() - cached_at < _RELIABILITY_REPORT_CACHE_TTL:
                return cached_report

    from .reliability_engine import compute_reliability_score as _compute_rel

    videos = db.query(Video).order_by(Video.created_at.desc()).limit(limit).all()

    # Batch-fetch session counts in a single query (eliminates N+1 — Q12).
    video_ids = [v.id for v in videos]
    session_count_map: dict = {}
    if video_ids:
        session_count_rows = (
            db.query(SessionModel.video_id, _sql_func.count(SessionModel.id))
            .filter(SessionModel.video_id.in_(video_ids))
            .group_by(SessionModel.video_id)
            .all()
        )
        session_count_map = dict(session_count_rows)

    items: list[CatalogReliabilityItem] = []
    reliability_scores: list[float] = []

    for video in videos:
        try:
            session_count = session_count_map.get(video.id, 0)
            if session_count == 0:
                items.append(CatalogReliabilityItem(
                    video_id=video.id,
                    title=video.title,
                    source_url=video.source_url,
                    sessions_count=0,
                    reliability=None,
                    error="no_sessions",
                ))
                continue

            payload = build_video_readout(db, video.id, aggregate=True, window_ms=window_ms)
            _rel = _compute_rel(payload)
            rel_schema = build_reliability_schema(_rel)
            reliability_scores.append(_rel.overall)
            items.append(CatalogReliabilityItem(
                video_id=video.id,
                title=video.title,
                source_url=video.source_url,
                sessions_count=session_count,
                reliability=rel_schema,
            ))
        except Exception as exc:
            logger.warning(
                "Reliability scoring failed for video %s: %s",
                video.id,
                exc,
                exc_info=True,
            )
            items.append(CatalogReliabilityItem(
                video_id=video.id,
                title=video.title,
                source_url=video.source_url,
                sessions_count=0,
                reliability=None,
                error=str(exc)[:200],
            ))

    mean_reliability = round(sum(reliability_scores) / len(reliability_scores), 2) if reliability_scores else None

    report = CatalogReliabilityReport(
        total_videos=len(videos),
        scored_videos=len(reliability_scores),
        mean_reliability=mean_reliability,
        items=items,
    )

    with _reliability_report_cache_lock:
        _reliability_report_cache[cache_key] = (monotonic(), report)

    return report


@router.get("/videos/{video_id}/readout/export-package", response_model=ReadoutExportPackageResponse)
def get_video_readout_export_package(
    video_id: UUID,
    session_id: Optional[UUID] = Query(default=None),
    session_id_legacy: Optional[UUID] = Query(default=None, alias="sessionId", include_in_schema=False),
    variant_id: Optional[str] = Query(default=None),
    variant_id_legacy: Optional[str] = Query(default=None, alias="variantId", include_in_schema=False),
    aggregate: bool = Query(default=True),
    window_ms: int = Query(default=1000, ge=100, le=10000),
    window_ms_legacy: Optional[int] = Query(default=None, ge=100, le=10000, alias="windowMs", include_in_schema=False),
    product_mode: Optional[ProductRollupMode] = Query(default=None),
    product_mode_legacy: Optional[ProductRollupMode] = Query(
        default=None, alias="productMode", include_in_schema=False
    ),
    workspace_tier: Optional[str] = Query(default=None),
    workspace_tier_legacy: Optional[str] = Query(
        default=None, alias="workspaceTier", include_in_schema=False
    ),
    db: Session = Depends(get_db),
) -> ReadoutExportPackageResponse:
    resolved_session_id = resolve_dual_query_param(
        canonical_value=session_id,
        legacy_value=session_id_legacy,
        canonical_name="session_id",
        legacy_name="sessionId",
    )
    resolved_variant_id = resolve_dual_query_param(
        canonical_value=variant_id,
        legacy_value=variant_id_legacy,
        canonical_name="variant_id",
        legacy_name="variantId",
    )
    resolved_window_ms = resolve_dual_query_param(
        canonical_value=window_ms,
        legacy_value=window_ms_legacy,
        canonical_name="window_ms",
        legacy_name="windowMs",
    )
    resolved_product_mode = resolve_dual_query_param(
        canonical_value=product_mode,
        legacy_value=product_mode_legacy,
        canonical_name="product_mode",
        legacy_name="productMode",
    )
    resolved_workspace_tier = resolve_dual_query_param(
        canonical_value=workspace_tier,
        legacy_value=workspace_tier_legacy,
        canonical_name="workspace_tier",
        legacy_name="workspaceTier",
    )
    return build_video_readout_export_package(
        db,
        video_id,
        session_id=resolved_session_id,
        variant_id=resolved_variant_id,
        aggregate=aggregate,
        window_ms=resolved_window_ms,
        product_mode=resolved_product_mode,
        workspace_tier=resolved_workspace_tier,
    )
