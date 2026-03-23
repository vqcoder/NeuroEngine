"""Reusable timeline extraction and feature-store APIs for video assets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Video,
    VideoFeatureTrack,
    VideoTimelineAnalysis,
    VideoTimelineSegment,
)
from .config import get_settings
from .schemas import (
    FeatureTrackRead,
    TimelineAnalysisJobResponse,
    TimelineAnalysisRequest,
    TimelineFeatureWindowResponse,
    TimelineSegmentRead,
)

from .timeline_feature_store_media import (
    _ResolvedSource,
    _cleanup_source_asset,
    _compute_file_sha256,
    _extract_keyframes,
    _extract_sampled_frames,
    _extract_shot_boundaries,
    _probe_video,
    _resolve_asset_id,
    _resolve_source_asset,
)
from .timeline_feature_store_extractors import (
    _build_audio_outputs,
    _build_cta_segments,
    _build_frame_level_outputs,
    _build_keyframe_segments,
    _build_object_salience_tracks,
    _build_scene_segments,
    _build_shot_outputs,
    _build_trace_outputs,
    _extract_audio_rms,
    _extract_text_overlay_segments,
    _extract_transcript_segments,
)
from .timeline_feature_store_utils import (
    _analysis_to_job_response,
    _apply_analysis_retention_policy,
    _mark_analysis_failed,
    _normalize_segment,
    _normalize_track,
    _replace_analysis_rows,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMELINE_ANALYSIS_VERSION = "timeline_v1"


@dataclass(frozen=True)
class _TimelineExtractionPayload:
    segments: List[Dict[str, Any]]
    tracks: List[Dict[str, Any]]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class TimelineAnalysisExecutionContext:
    analysis_id: UUID
    source_path: Path
    source_is_temporary: bool
    sample_interval_ms: int
    scene_threshold: float


@dataclass(frozen=True)
class _PreparedTimelineAnalysis:
    response: TimelineAnalysisJobResponse
    execution_context: Optional[TimelineAnalysisExecutionContext]


def run_timeline_analysis_job(
    db: Session,
    video_id: UUID,
    request: TimelineAnalysisRequest,
) -> TimelineAnalysisJobResponse:
    """Run synchronous timeline extraction (prepare + execute)."""

    prepared = prepare_timeline_analysis_job(db, video_id, request)
    if prepared.execution_context is None:
        return prepared.response
    return complete_timeline_analysis_job(db, prepared.execution_context)


def prepare_timeline_analysis_job(
    db: Session,
    video_id: UUID,
    request: TimelineAnalysisRequest,
) -> _PreparedTimelineAnalysis:
    """Prepare an idempotent timeline analysis run and return executable context."""

    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    resolved_source = _resolve_source_asset(video, override_source_ref=request.source_ref)
    analysis: Optional[VideoTimelineAnalysis] = None
    cleanup_source = True
    try:
        fingerprint = _compute_file_sha256(resolved_source.path)
        analysis_version = (request.analysis_version or DEFAULT_TIMELINE_ANALYSIS_VERSION).strip()
        if not analysis_version:
            analysis_version = DEFAULT_TIMELINE_ANALYSIS_VERSION

        asset_id = _resolve_asset_id(video)
        existing = db.scalar(
            select(VideoTimelineAnalysis)
            .where(
                VideoTimelineAnalysis.video_id == video.id,
                VideoTimelineAnalysis.analysis_version == analysis_version,
                VideoTimelineAnalysis.asset_fingerprint == fingerprint,
            )
            .order_by(VideoTimelineAnalysis.created_at.desc())
        )

        if existing is not None and existing.status == "completed" and not request.force_recompute:
            return _PreparedTimelineAnalysis(
                response=_analysis_to_job_response(existing, reused_existing=True),
                execution_context=None,
            )

        now = datetime.now(timezone.utc)
        if existing is None:
            analysis = VideoTimelineAnalysis(
                video_id=video.id,
                asset_id=asset_id,
                analysis_version=analysis_version,
                asset_fingerprint=fingerprint,
                source_ref=resolved_source.source_ref,
                status="running",
                started_at=now,
                completed_at=None,
                metadata_json={
                    "source_kind": resolved_source.source_kind,
                    "source_ref": resolved_source.source_ref,
                    "sample_interval_ms": int(request.sample_interval_ms),
                    "scene_threshold": float(request.scene_threshold),
                    "reused_existing": False,
                    "run_async": bool(request.run_async),
                },
            )
            db.add(analysis)
            db.flush()
        else:
            analysis = existing
            meta = dict(existing.metadata_json or {})
            meta.update(
                {
                    "source_kind": resolved_source.source_kind,
                    "source_ref": resolved_source.source_ref,
                    "sample_interval_ms": int(request.sample_interval_ms),
                    "scene_threshold": float(request.scene_threshold),
                    "reused_existing": False,
                    "run_async": bool(request.run_async),
                    "resumed_from_status": existing.status,
                }
            )
            analysis.asset_id = asset_id
            analysis.source_ref = resolved_source.source_ref
            analysis.status = "running"
            analysis.started_at = now
            analysis.completed_at = None
            analysis.metadata_json = meta

        db.commit()
        db.refresh(analysis)

        execution_context = TimelineAnalysisExecutionContext(
            analysis_id=analysis.id,
            source_path=resolved_source.path,
            source_is_temporary=resolved_source.is_temporary,
            sample_interval_ms=int(request.sample_interval_ms),
            scene_threshold=float(request.scene_threshold),
        )
        cleanup_source = False

        return _PreparedTimelineAnalysis(
            response=_analysis_to_job_response(analysis, reused_existing=False),
            execution_context=execution_context,
        )
    except HTTPException:
        _mark_analysis_failed(db, analysis, "timeline_analysis_prepare_failed")
        raise
    except Exception as exc:
        _mark_analysis_failed(db, analysis, str(exc))
        raise HTTPException(status_code=500, detail=f"Timeline analysis prepare failed: {exc}") from exc
    finally:
        if cleanup_source:
            _cleanup_source_asset(resolved_source)


def complete_timeline_analysis_job(
    db: Session,
    execution_context: TimelineAnalysisExecutionContext,
) -> TimelineAnalysisJobResponse:
    """Execute a prepared timeline analysis context and persist reusable outputs."""

    analysis = db.get(VideoTimelineAnalysis, execution_context.analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Timeline analysis not found")

    video = db.get(Video, analysis.video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if analysis.status not in {"running", "pending"}:
        meta = dict(analysis.metadata_json or {})
        if analysis.status == "completed":
            return _analysis_to_job_response(analysis, reused_existing=bool(meta.get("reused_existing")))
        raise HTTPException(status_code=409, detail=f"Cannot execute analysis with status={analysis.status}")

    try:
        extraction = _extract_timeline_feature_payload(
            db=db,
            video=video,
            source_path=execution_context.source_path,
            sample_interval_ms=int(execution_context.sample_interval_ms),
            scene_threshold=float(execution_context.scene_threshold),
        )

        _replace_analysis_rows(
            db=db,
            analysis=analysis,
            asset_id=analysis.asset_id,
            segments=extraction.segments,
            tracks=extraction.tracks,
        )

        meta = dict(analysis.metadata_json or {})
        meta.update(extraction.metadata)
        analysis.metadata_json = meta
        analysis.status = "completed"
        analysis.completed_at = datetime.now(timezone.utc)

        retention_limit = max(int(get_settings().timeline_analysis_retention_limit), 1)
        _apply_analysis_retention_policy(
            db,
            video_id=analysis.video_id,
            asset_id=analysis.asset_id,
            analysis_version=analysis.analysis_version,
            keep_limit=retention_limit,
            protect_analysis_id=analysis.id,
        )

        db.commit()
        db.refresh(analysis)
        return _analysis_to_job_response(analysis, reused_existing=False)
    except HTTPException:
        _mark_analysis_failed(db, analysis, "timeline_analysis_failed")
        raise
    except Exception as exc:
        _mark_analysis_failed(db, analysis, str(exc))
        raise HTTPException(status_code=500, detail=f"Timeline analysis failed: {exc}") from exc
    finally:
        if execution_context.source_is_temporary:
            execution_context.source_path.unlink(missing_ok=True)


def get_timeline_analysis_job(
    db: Session,
    analysis_id: UUID,
) -> TimelineAnalysisJobResponse:
    """Fetch timeline analysis job status."""

    analysis = db.get(VideoTimelineAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Timeline analysis not found")
    meta = dict(analysis.metadata_json or {})
    return _analysis_to_job_response(analysis, reused_existing=bool(meta.get("reused_existing")))


def query_timeline_features_window(
    db: Session,
    *,
    asset_id: str,
    start_ms: int = 0,
    end_ms: Optional[int] = None,
    analysis_version: str = DEFAULT_TIMELINE_ANALYSIS_VERSION,
    track_names: Optional[Sequence[str]] = None,
    segment_types: Optional[Sequence[str]] = None,
) -> TimelineFeatureWindowResponse:
    """Return reusable timeline segments and feature tracks for an asset window."""

    version = (analysis_version or DEFAULT_TIMELINE_ANALYSIS_VERSION).strip() or DEFAULT_TIMELINE_ANALYSIS_VERSION
    resolved_start_ms = max(int(start_ms), 0)

    analysis = db.scalar(
        select(VideoTimelineAnalysis)
        .where(
            VideoTimelineAnalysis.asset_id == asset_id,
            VideoTimelineAnalysis.analysis_version == version,
            VideoTimelineAnalysis.status == "completed",
        )
        .order_by(VideoTimelineAnalysis.completed_at.desc(), VideoTimelineAnalysis.created_at.desc())
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="No completed timeline analysis found for asset_id")

    meta = dict(analysis.metadata_json or {})
    inferred_end = int(meta.get("duration_ms") or (resolved_start_ms + 1))
    resolved_end_ms = int(end_ms) if end_ms is not None else inferred_end
    if resolved_end_ms <= resolved_start_ms:
        raise HTTPException(status_code=400, detail="end_ms must be greater than start_ms")

    segment_stmt = (
        select(VideoTimelineSegment)
        .where(
            VideoTimelineSegment.analysis_id == analysis.id,
            VideoTimelineSegment.asset_id == analysis.asset_id,
            VideoTimelineSegment.end_ms > resolved_start_ms,
            VideoTimelineSegment.start_ms < resolved_end_ms,
        )
        .order_by(VideoTimelineSegment.start_ms.asc(), VideoTimelineSegment.segment_type.asc())
    )
    if segment_types:
        normalized_segment_types = [value.strip() for value in segment_types if value and value.strip()]
        if normalized_segment_types:
            segment_stmt = segment_stmt.where(
                VideoTimelineSegment.segment_type.in_(normalized_segment_types)
            )

    track_stmt = (
        select(VideoFeatureTrack)
        .where(
            VideoFeatureTrack.analysis_id == analysis.id,
            VideoFeatureTrack.asset_id == analysis.asset_id,
            VideoFeatureTrack.end_ms > resolved_start_ms,
            VideoFeatureTrack.start_ms < resolved_end_ms,
        )
        .order_by(VideoFeatureTrack.start_ms.asc(), VideoFeatureTrack.track_name.asc())
    )
    if track_names:
        normalized_track_names = [value.strip() for value in track_names if value and value.strip()]
        if normalized_track_names:
            track_stmt = track_stmt.where(VideoFeatureTrack.track_name.in_(normalized_track_names))

    segments = db.scalars(segment_stmt).all()
    tracks = db.scalars(track_stmt).all()

    return TimelineFeatureWindowResponse(
        analysis_id=analysis.id,
        video_id=analysis.video_id,
        asset_id=analysis.asset_id,
        analysis_version=analysis.analysis_version,
        window_start_ms=resolved_start_ms,
        window_end_ms=resolved_end_ms,
        generated_at=datetime.now(timezone.utc),
        segments=[
            TimelineSegmentRead(
                id=row.id,
                segment_type=row.segment_type,
                start_ms=row.start_ms,
                end_ms=row.end_ms,
                label=row.label,
                confidence=row.confidence,
                details=row.details,
            )
            for row in segments
        ],
        feature_tracks=[
            FeatureTrackRead(
                id=row.id,
                track_name=row.track_name,
                start_ms=row.start_ms,
                end_ms=row.end_ms,
                numeric_value=row.numeric_value,
                text_value=row.text_value,
                unit=row.unit,
                details=row.details,
            )
            for row in tracks
        ],
        metadata=meta,
    )


def _extract_timeline_feature_payload(
    *,
    db: Session,
    video: Video,
    source_path: Path,
    sample_interval_ms: int,
    scene_threshold: float,
) -> _TimelineExtractionPayload:
    probe = _probe_video(source_path)
    duration_ms = int(probe.get("duration_ms") or video.duration_ms or 0)
    if duration_ms <= 0:
        duration_ms = 1000

    sampled_frames = _extract_sampled_frames(source_path, sample_interval_ms=sample_interval_ms)
    keyframes = _extract_keyframes(source_path)
    shot_boundaries = _extract_shot_boundaries(source_path, scene_threshold=scene_threshold)
    audio_rms = _extract_audio_rms(source_path)

    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []

    frame_segments, frame_tracks = _build_frame_level_outputs(sampled_frames, duration_ms=duration_ms)
    segments.extend(frame_segments)
    tracks.extend(frame_tracks)

    keyframe_segments = _build_keyframe_segments(keyframes, duration_ms=duration_ms)
    segments.extend(keyframe_segments)

    shot_segments, shot_tracks = _build_shot_outputs(
        shot_boundaries=shot_boundaries,
        duration_ms=duration_ms,
    )
    segments.extend(shot_segments)
    tracks.extend(shot_tracks)

    scene_segments = _build_scene_segments(video=video, shot_segments=shot_segments, duration_ms=duration_ms)
    segments.extend(scene_segments)

    cta_segments = _build_cta_segments(video=video, duration_ms=duration_ms)
    segments.extend(cta_segments)

    audio_segments, audio_tracks = _build_audio_outputs(audio_rms=audio_rms, duration_ms=duration_ms)
    segments.extend(audio_segments)
    tracks.extend(audio_tracks)

    transcript_segments, asr_available, asr_provider = _extract_transcript_segments(
        video=video,
        source_path=source_path,
        duration_ms=duration_ms,
    )
    segments.extend(transcript_segments)

    text_overlay_segments, ocr_available, ocr_provider = _extract_text_overlay_segments(
        video=video,
        source_path=source_path,
        duration_ms=duration_ms,
    )
    segments.extend(text_overlay_segments)

    trace_segments, trace_tracks = _build_trace_outputs(db=db, video_id=video.id, duration_ms=duration_ms)
    segments.extend(trace_segments)
    tracks.extend(trace_tracks)

    object_tracks = _build_object_salience_tracks(video=video, duration_ms=duration_ms)
    tracks.extend(object_tracks)

    segment_type_counts: Dict[str, int] = {}
    for segment in segments:
        key = str(segment["segment_type"])
        segment_type_counts[key] = segment_type_counts.get(key, 0) + 1

    track_name_counts: Dict[str, int] = {}
    for track in tracks:
        key = str(track["track_name"])
        track_name_counts[key] = track_name_counts.get(key, 0) + 1

    metadata = {
        "duration_ms": duration_ms,
        "width": probe.get("width"),
        "height": probe.get("height"),
        "fps": probe.get("fps"),
        "audio_stream_present": probe.get("audio_stream_present"),
        "sample_interval_ms": int(sample_interval_ms),
        "scene_threshold": float(scene_threshold),
        "segment_count": len(segments),
        "feature_track_count": len(tracks),
        "segment_type_counts": segment_type_counts,
        "track_name_counts": track_name_counts,
        "asr_tokens_available": asr_available,
        "asr_provider": asr_provider,
        "text_overlay_available": ocr_available,
        "ocr_provider": ocr_provider,
        "trace_subject_signals_available": bool(trace_tracks),
        "claim_safe_note": (
            "Timeline features are diagnostic proxies for creative analysis; "
            "they are not direct measures of cognitive truth."
        ),
    }

    segments = sorted(
        (_normalize_segment(item, duration_ms=duration_ms) for item in segments),
        key=lambda item: (item["start_ms"], item["end_ms"], item["segment_type"]),
    )
    tracks = sorted(
        (_normalize_track(item, duration_ms=duration_ms) for item in tracks),
        key=lambda item: (item["start_ms"], item["end_ms"], item["track_name"]),
    )

    return _TimelineExtractionPayload(segments=segments, tracks=tracks, metadata=metadata)
