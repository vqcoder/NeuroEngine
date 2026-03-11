"""Reusable timeline extraction and feature-store APIs for video assets."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import shutil
import statistics
import subprocess
import tempfile
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import unquote, urlparse

import httpx

from .http_client import get_sync_client, TIMEOUT_TIMELINE_DOWNLOAD
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (
    Session as SessionModel,
    TracePoint,
    Video,
    VideoFeatureTrack,
    VideoTimelineAnalysis,
    VideoTimelineSegment,
)
from .config import get_settings
from .services_math import to_float_optional
from .schemas import (
    FeatureTrackRead,
    TimelineAnalysisJobResponse,
    TimelineAnalysisRequest,
    TimelineFeatureWindowResponse,
    TimelineSegmentRead,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMELINE_ANALYSIS_VERSION = "timeline_v1"
SOURCE_DOWNLOAD_TIMEOUT_SECONDS = 30
SOURCE_DOWNLOAD_MAX_BYTES = 512 * 1024 * 1024
FFPROBE_TIMEOUT_SECONDS = 60
FFMPEG_TIMEOUT_SECONDS = 180
AUDIO_SAMPLE_RATE = 16000
CUT_CADENCE_WINDOW_MS = 5000
OCR_MAX_FRAMES = 240

SHOWINFO_FRAME_PATTERN = re.compile(
    r"pts_time:(?P<pts>[0-9]+(?:\.[0-9]+)?)"
    r".*?mean:\[(?P<y>[0-9]+) (?P<u>[0-9]+) (?P<v>[0-9]+)\]"
)
SHOWINFO_STDEV_PATTERN = re.compile(
    r"stdev:\[(?P<sy>[0-9]+(?:\.[0-9]+)?) (?P<su>[0-9]+(?:\.[0-9]+)?) (?P<sv>[0-9]+(?:\.[0-9]+)?)\]"
)
SHOWINFO_TIME_PATTERN = re.compile(r"pts_time:(?P<pts>[0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True)
class _ResolvedSource:
    path: Path
    source_ref: str
    source_kind: str
    is_temporary: bool


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


def _resolve_source_asset(video: Video, override_source_ref: Optional[str]) -> _ResolvedSource:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}

    candidates: List[str] = []
    if override_source_ref:
        candidates.append(str(override_source_ref))
    if video.source_url:
        candidates.append(str(video.source_url))
    for key in (
        "source_path",
        "local_path",
        "asset_path",
        "video_path",
        "source_url",
        "video_url",
    ):
        value = metadata.get(key)
        if value:
            candidates.append(str(value))

    for candidate in candidates:
        cleaned = candidate.strip()
        if not cleaned:
            continue

        parsed = urlparse(cleaned)
        if parsed.scheme in {"http", "https"}:
            downloaded = _download_source_asset(cleaned)
            return _ResolvedSource(
                path=downloaded,
                source_ref=cleaned,
                source_kind="http_download",
                is_temporary=True,
            )

        if parsed.scheme == "file":
            local_path = Path(unquote(parsed.path))
            if local_path.exists():
                return _ResolvedSource(
                    path=local_path,
                    source_ref=str(local_path),
                    source_kind="file_url",
                    is_temporary=False,
                )

        local_path = Path(cleaned).expanduser()
        if local_path.exists():
            return _ResolvedSource(
                path=local_path,
                source_ref=str(local_path),
                source_kind="local_path",
                is_temporary=False,
            )

    raise HTTPException(
        status_code=400,
        detail="No readable source asset found; provide source_ref or set video source_url to a local path/http(s) URL",
    )


def _download_source_asset(source_url: str) -> Path:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="source_ref URL must use http or https")

    suffix = Path(parsed.path).suffix or ".mp4"
    try:
        client = get_sync_client()
        with client.stream(
            "GET",
            source_url,
            headers={
                "User-Agent": "AlphaEngineTimeline/1.0",
                "Accept": "video/*,*/*;q=0.8",
            },
            timeout=TIMEOUT_TIMELINE_DOWNLOAD,
        ) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                total_bytes = 0
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > SOURCE_DOWNLOAD_MAX_BYTES:
                        temp_path = Path(temp_file.name)
                        temp_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=400,
                            detail=f"source_ref exceeds byte limit ({SOURCE_DOWNLOAD_MAX_BYTES})",
                        )
                    temp_file.write(chunk)
                return Path(temp_file.name)
    except HTTPException:
        raise
    except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Unable to download source_ref: {exc}") from exc


def _cleanup_source_asset(resolved_source: _ResolvedSource) -> None:
    if resolved_source.is_temporary:
        resolved_source.path.unlink(missing_ok=True)


def _resolve_asset_id(video: Video) -> str:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    for key in ("asset_id", "assetId", "video_asset_id", "videoAssetId"):
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(video.id)


def _compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _probe_video(path: Path) -> Dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = _run_subprocess(command, timeout_seconds=FFPROBE_TIMEOUT_SECONDS, text=True)
    payload = json.loads(result.stdout or "{}")

    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}

    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), None)

    duration_sec = to_float_optional(format_info.get("duration"))
    if duration_sec is None:
        duration_sec = to_float_optional(video_stream.get("duration"))
    duration_ms = int(round(max(duration_sec or 0.0, 0.0) * 1000.0))

    fps = _parse_rational(video_stream.get("avg_frame_rate")) or _parse_rational(
        video_stream.get("r_frame_rate")
    )

    return {
        "duration_ms": duration_ms,
        "width": _to_int(video_stream.get("width")),
        "height": _to_int(video_stream.get("height")),
        "fps": fps,
        "audio_stream_present": audio_stream is not None,
    }


def _extract_sampled_frames(source_path: Path, sample_interval_ms: int) -> List[Dict[str, Any]]:
    fps = 1000.0 / float(max(sample_interval_ms, 1))
    command = [
        "ffmpeg",
        "-v",
        "info",
        "-i",
        str(source_path),
        "-vf",
        f"fps={fps:.6f},showinfo",
        "-f",
        "null",
        "-",
    ]
    result = _run_subprocess(command, timeout_seconds=FFMPEG_TIMEOUT_SECONDS, text=True, check=False)
    output = f"{result.stdout}\n{result.stderr}"

    seen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    for line in output.splitlines():
        if "showinfo" not in line or "pts_time" not in line:
            continue
        frame_match = SHOWINFO_FRAME_PATTERN.search(line)
        if frame_match is None:
            continue
        timestamp_ms = int(round(float(frame_match.group("pts")) * 1000.0))
        if timestamp_ms in seen:
            continue
        seen.add(timestamp_ms)
        row: Dict[str, Any] = {
            "start_ms": max(timestamp_ms, 0),
            "end_ms": max(timestamp_ms + 1, 1),
            "y": int(frame_match.group("y")),
            "u": int(frame_match.group("u")),
            "v": int(frame_match.group("v")),
        }
        stdev_match = SHOWINFO_STDEV_PATTERN.search(line)
        if stdev_match is not None:
            row["std_y"] = float(stdev_match.group("sy"))
            row["std_u"] = float(stdev_match.group("su"))
            row["std_v"] = float(stdev_match.group("sv"))
        rows.append(row)

    return sorted(rows, key=lambda item: item["start_ms"])


def _extract_keyframes(source_path: Path) -> List[Dict[str, Any]]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-skip_frame",
        "nokey",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,pkt_dts_time,pkt_pts_time,pict_type",
        "-of",
        "json",
        str(source_path),
    ]
    result = _run_subprocess(command, timeout_seconds=FFPROBE_TIMEOUT_SECONDS, text=True)
    payload = json.loads(result.stdout or "{}")
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []

    keyframes: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        timestamp_sec = (
            to_float_optional(frame.get("best_effort_timestamp_time"))
            or to_float_optional(frame.get("pkt_pts_time"))
            or to_float_optional(frame.get("pkt_dts_time"))
        )
        if timestamp_sec is None:
            continue
        timestamp_ms = int(round(timestamp_sec * 1000.0))
        if timestamp_ms in seen:
            continue
        seen.add(timestamp_ms)
        pict_type = str(frame.get("pict_type") or "I")
        keyframes.append(
            {
                "start_ms": max(timestamp_ms, 0),
                "end_ms": max(timestamp_ms + 1, 1),
                "label": f"keyframe_{pict_type.lower()}",
                "details": {"pict_type": pict_type},
            }
        )
    return sorted(keyframes, key=lambda item: item["start_ms"])


def _extract_shot_boundaries(source_path: Path, scene_threshold: float) -> List[int]:
    command = [
        "ffmpeg",
        "-v",
        "info",
        "-i",
        str(source_path),
        "-filter:v",
        f"select='gt(scene,{scene_threshold:.3f})',showinfo",
        "-f",
        "null",
        "-",
    ]
    result = _run_subprocess(command, timeout_seconds=FFMPEG_TIMEOUT_SECONDS, text=True, check=False)
    output = f"{result.stdout}\n{result.stderr}"

    boundaries: set[int] = set()
    for line in output.splitlines():
        if "showinfo" not in line or "pts_time" not in line:
            continue
        match = SHOWINFO_TIME_PATTERN.search(line)
        if match is None:
            continue
        timestamp_ms = int(round(float(match.group("pts")) * 1000.0))
        if timestamp_ms > 0:
            boundaries.add(timestamp_ms)

    return sorted(boundaries)


def _extract_audio_rms(source_path: Path) -> Dict[int, float]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-f",
        "s16le",
        "-",
    ]
    result = _run_subprocess(command, timeout_seconds=FFMPEG_TIMEOUT_SECONDS, check=False)
    if result.returncode != 0 or not result.stdout:
        return {}

    samples = array("h")
    samples.frombytes(result.stdout)
    if not samples:
        return {}

    per_second = AUDIO_SAMPLE_RATE
    total_seconds = int(math.ceil(len(samples) / float(per_second)))
    rms_map: Dict[int, float] = {}
    for second in range(total_seconds):
        start = second * per_second
        end = min((second + 1) * per_second, len(samples))
        if end <= start:
            continue
        chunk = samples[start:end]
        mean_square = sum((sample / 32768.0) ** 2 for sample in chunk) / float(len(chunk))
        rms_map[second] = round(math.sqrt(mean_square), 6)
    return rms_map


def _build_frame_level_outputs(
    sampled_frames: Sequence[Dict[str, Any]],
    *,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []

    if not sampled_frames:
        return segments, tracks

    previous = None
    motion_labels: List[str] = []
    for index, frame in enumerate(sampled_frames):
        start_ms = int(frame["start_ms"])
        next_start_ms = (
            int(sampled_frames[index + 1]["start_ms"])
            if index + 1 < len(sampled_frames)
            else min(start_ms + 1000, duration_ms)
        )
        end_ms = max(next_start_ms, start_ms + 1)

        segments.append(
            {
                "segment_type": "frame_sample",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": f"sample_{index}",
                "details": {
                    "mean_y": frame.get("y"),
                    "mean_u": frame.get("u"),
                    "mean_v": frame.get("v"),
                    "std_y": frame.get("std_y"),
                    "std_u": frame.get("std_u"),
                    "std_v": frame.get("std_v"),
                },
            }
        )
        tracks.append(
            {
                "track_name": "luminance_mean",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(frame.get("y", 0.0)),
                "unit": "yuv_y",
                "details": {"source": "ffmpeg_showinfo"},
            }
        )
        tracks.append(
            {
                "track_name": "color_u_mean",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(frame.get("u", 0.0)),
                "unit": "yuv_u",
                "details": {"source": "ffmpeg_showinfo"},
            }
        )
        tracks.append(
            {
                "track_name": "color_v_mean",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(frame.get("v", 0.0)),
                "unit": "yuv_v",
                "details": {"source": "ffmpeg_showinfo"},
            }
        )

        if previous is not None:
            luminance_delta = abs(float(frame.get("y", 0.0)) - float(previous.get("y", 0.0)))
            color_delta = math.sqrt(
                (float(frame.get("u", 0.0)) - float(previous.get("u", 0.0))) ** 2
                + (float(frame.get("v", 0.0)) - float(previous.get("v", 0.0))) ** 2
            )
            motion_proxy = round((0.7 * luminance_delta) + (0.3 * color_delta), 6)
            motion_label = "dynamic" if motion_proxy >= 6.0 else "steady"
            motion_labels.append(motion_label)

            tracks.append(
                {
                    "track_name": "luminance_delta",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "numeric_value": round(luminance_delta, 6),
                    "unit": "delta_y",
                    "details": {"source": "frame_delta"},
                }
            )
            tracks.append(
                {
                    "track_name": "color_delta",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "numeric_value": round(color_delta, 6),
                    "unit": "delta_uv",
                    "details": {"source": "frame_delta"},
                }
            )
            tracks.append(
                {
                    "track_name": "camera_motion_proxy",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "numeric_value": motion_proxy,
                    "unit": "proxy",
                    "details": {
                        "method": "luminance_chroma_delta_proxy",
                        "claim_safe": "heuristic camera motion class",
                    },
                }
            )
            tracks.append(
                {
                    "track_name": "camera_motion_class",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text_value": motion_label,
                    "details": {"method": "camera_motion_proxy_threshold"},
                }
            )

        previous = frame

    if motion_labels:
        dynamic_ratio = motion_labels.count("dynamic") / float(len(motion_labels))
        summary_label = "dynamic" if dynamic_ratio >= 0.5 else "steady"
        tracks.append(
            {
                "track_name": "camera_motion_class_summary",
                "start_ms": 0,
                "end_ms": max(duration_ms, 1),
                "text_value": summary_label,
                "details": {
                    "dynamic_ratio": round(dynamic_ratio, 6),
                    "method": "camera_motion_proxy_ratio",
                },
            }
        )

    return segments, tracks


def _build_keyframe_segments(
    keyframes: Sequence[Dict[str, Any]],
    *,
    duration_ms: int,
) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for keyframe in keyframes:
        start_ms = int(keyframe.get("start_ms", 0))
        end_ms = int(keyframe.get("end_ms", start_ms + 1))
        segments.append(
            {
                "segment_type": "keyframe",
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "label": keyframe.get("label"),
                "details": keyframe.get("details") or {"source": "ffprobe_skip_frame_nokey"},
            }
        )
    if not segments:
        segments.append(
            {
                "segment_type": "keyframe",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "keyframe_unavailable",
                "details": {"status": "unavailable", "reason": "No keyframe metadata extracted"},
            }
        )
    return segments


def _build_shot_outputs(
    *,
    shot_boundaries: Sequence[int],
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []

    boundaries = sorted(
        value for value in {int(item) for item in shot_boundaries} if 0 < value < duration_ms
    )
    cut_points = [0, *boundaries, duration_ms]

    shot_durations: List[int] = []
    for index in range(len(cut_points) - 1):
        start_ms = int(cut_points[index])
        end_ms = int(cut_points[index + 1])
        if end_ms <= start_ms:
            continue
        duration = end_ms - start_ms
        shot_durations.append(duration)
        segments.append(
            {
                "segment_type": "shot",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": f"shot_{index + 1}",
                "details": {"duration_ms": duration},
            }
        )
        tracks.append(
            {
                "track_name": "shot_duration_ms",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(duration),
                "unit": "ms",
                "details": {"shot_index": index + 1},
            }
        )

    for boundary in boundaries:
        segments.append(
            {
                "segment_type": "shot_boundary",
                "start_ms": boundary,
                "end_ms": boundary + 1,
                "label": "cut_event",
                "details": {"method": "ffmpeg_scene_detect"},
            }
        )

    for window_start in range(0, max(duration_ms, 1), CUT_CADENCE_WINDOW_MS):
        window_end = min(window_start + CUT_CADENCE_WINDOW_MS, duration_ms)
        if window_end <= window_start:
            continue
        cuts_in_window = sum(
            1 for boundary in boundaries if window_start <= boundary < window_end
        )
        window_seconds = max((window_end - window_start) / 1000.0, 0.001)
        tracks.append(
            {
                "track_name": "cut_cadence",
                "start_ms": window_start,
                "end_ms": window_end,
                "numeric_value": round(cuts_in_window / window_seconds, 6),
                "unit": "cuts_per_second",
                "details": {"cut_count": cuts_in_window, "window_ms": CUT_CADENCE_WINDOW_MS},
            }
        )

    if shot_durations:
        tracks.extend(
            [
                {
                    "track_name": "shot_duration_mean_ms",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "numeric_value": round(sum(shot_durations) / float(len(shot_durations)), 6),
                    "unit": "ms",
                    "details": {"sample_count": len(shot_durations)},
                },
                {
                    "track_name": "shot_duration_p50_ms",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "numeric_value": _percentile(shot_durations, 0.5),
                    "unit": "ms",
                    "details": {"sample_count": len(shot_durations)},
                },
                {
                    "track_name": "shot_duration_p90_ms",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "numeric_value": _percentile(shot_durations, 0.9),
                    "unit": "ms",
                    "details": {"sample_count": len(shot_durations)},
                },
            ]
        )

    return segments, tracks


def _build_scene_segments(
    *,
    video: Video,
    shot_segments: Sequence[Dict[str, Any]],
    duration_ms: int,
) -> List[Dict[str, Any]]:
    scene_rows = sorted(
        list(video.scene_graph_scenes or []),
        key=lambda row: (int(row.sort_index), int(row.start_ms), int(row.end_ms)),
    )

    segments: List[Dict[str, Any]] = []
    if scene_rows:
        for row in scene_rows:
            segments.append(
                {
                    "segment_type": "scene_block",
                    "start_ms": int(row.start_ms),
                    "end_ms": int(row.end_ms),
                    "label": row.label or row.scene_id,
                    "details": {
                        "scene_id": row.scene_id,
                        "cut_id": row.cut_id,
                        "cta_id": row.cta_id,
                        "source": "scene_graph",
                    },
                }
            )
        return segments

    # Fallback: contiguous blocks grouped from shot-level segmentation.
    ordered_shots = sorted(
        (segment for segment in shot_segments if segment.get("segment_type") == "shot"),
        key=lambda item: (int(item["start_ms"]), int(item["end_ms"])),
    )
    if not ordered_shots:
        return [
            {
                "segment_type": "scene_block",
                "start_ms": 0,
                "end_ms": duration_ms,
                "label": "scene_1",
                "details": {"source": "fallback_full_duration"},
            }
        ]

    block_size = 3
    block_index = 0
    for start in range(0, len(ordered_shots), block_size):
        chunk = ordered_shots[start : start + block_size]
        if not chunk:
            continue
        block_index += 1
        segments.append(
            {
                "segment_type": "scene_block",
                "start_ms": int(chunk[0]["start_ms"]),
                "end_ms": int(chunk[-1]["end_ms"]),
                "label": f"scene_{block_index}",
                "details": {"source": "heuristic_shot_grouping", "shot_count": len(chunk)},
            }
        )
    return segments


def _build_cta_segments(video: Video, *, duration_ms: int) -> List[Dict[str, Any]]:
    markers = sorted(
        list(video.scene_graph_cta_markers or []),
        key=lambda row: (int(row.start_ms), int(row.end_ms)),
    )
    segments: List[Dict[str, Any]] = []
    for marker in markers:
        start_ms = int(marker.start_ms)
        end_ms = int(marker.end_ms)
        segments.append(
            {
                "segment_type": "cta_window",
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "label": marker.label or marker.cta_id,
                "details": {
                    "cta_id": marker.cta_id,
                    "scene_id": marker.scene_id,
                    "cut_id": marker.cut_id,
                    "source": "scene_graph",
                },
            }
        )
    if not segments:
        segments.append(
            {
                "segment_type": "cta_window",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "cta_unavailable",
                "details": {"status": "unavailable", "reason": "No CTA markers configured"},
            }
        )
    return segments


def _build_audio_outputs(
    *,
    audio_rms: Dict[int, float],
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []
    if not audio_rms:
        tracks.append(
            {
                "track_name": "audio_intensity_rms",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "numeric_value": None,
                "unit": "rms",
                "details": {"status": "unavailable", "reason": "Audio stream unavailable or extraction failed"},
            }
        )
        return segments, tracks

    ordered_seconds = sorted(audio_rms.items(), key=lambda item: item[0])
    for second, rms in ordered_seconds:
        start_ms = int(second * 1000)
        end_ms = min(start_ms + 1000, duration_ms)
        tracks.append(
            {
                "track_name": "audio_intensity_rms",
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "numeric_value": float(rms),
                "unit": "rms",
                "details": {"source": "ffmpeg_pcm_rms"},
            }
        )

    rms_values = [value for _, value in ordered_seconds]
    baseline = statistics.median(rms_values) if rms_values else 0.0
    previous = ordered_seconds[0][1]
    for second, rms in ordered_seconds[1:]:
        delta = rms - previous
        onset_threshold = max(previous * 1.5, baseline * 1.2)
        if rms >= onset_threshold and delta > 0.015:
            start_ms = int(second * 1000)
            segments.append(
                {
                    "segment_type": "audio_event",
                    "start_ms": start_ms,
                    "end_ms": min(start_ms + 1000, duration_ms),
                    "label": "music_onset_proxy",
                    "confidence": 0.55,
                    "details": {
                        "rms": round(rms, 6),
                        "delta_rms": round(delta, 6),
                        "baseline_rms": round(baseline, 6),
                        "method": "rms_jump_proxy",
                    },
                }
            )
        previous = rms

    return segments, tracks


def _extract_transcript_segments(
    video: Video,
    *,
    source_path: Path,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], bool, str]:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    token_fields = ("speech_tokens", "asr_tokens", "transcript_tokens")
    for field in token_fields:
        raw_tokens = metadata.get(field)
        if not isinstance(raw_tokens, list):
            continue
        tokens: List[Dict[str, Any]] = []
        for token in raw_tokens:
            if not isinstance(token, dict):
                continue
            start_ms = _to_int(token.get("start_ms"))
            end_ms = _to_int(token.get("end_ms"))
            text = token.get("token") or token.get("text")
            if start_ms is None or end_ms is None or text is None:
                continue
            tokens.append(
                {
                    "segment_type": "speech_token",
                    "start_ms": start_ms,
                    "end_ms": max(end_ms, start_ms + 1),
                    "label": str(text),
                    "confidence": to_float_optional(token.get("confidence")),
                    "details": {"source": field},
                }
            )
        if tokens:
            return tokens, True, "metadata_tokens"

    transcript_text = metadata.get("transcript") or metadata.get("asr_transcript")
    if isinstance(transcript_text, str) and transcript_text.strip():
        return (
            [
                {
                    "segment_type": "speech_transcript",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "label": transcript_text.strip()[:120],
                    "details": {"source": "metadata_transcript", "text_length": len(transcript_text.strip())},
                }
            ],
            True,
            "metadata_transcript",
        )

    configured_provider = (get_settings().timeline_asr_provider or "metadata").strip().lower()
    if configured_provider == "whisper_cli":
        whisper_segments = _extract_transcript_with_whisper_cli(source_path, duration_ms=duration_ms)
        if whisper_segments:
            return whisper_segments, True, "whisper_cli"

    return (
        [
            {
                "segment_type": "speech_token",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "speech_unavailable",
                "details": {
                    "status": "unavailable",
                    "reason": "No ASR transcript/token payload configured",
                },
            }
        ],
        False,
        configured_provider,
    )


def _extract_text_overlay_segments(
    video: Video,
    *,
    source_path: Path,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], bool, str]:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    overlay_fields = ("text_overlays", "ocr_overlays")
    for field in overlay_fields:
        raw_overlays = metadata.get(field)
        if not isinstance(raw_overlays, list):
            continue
        overlays: List[Dict[str, Any]] = []
        for item in raw_overlays:
            if not isinstance(item, dict):
                continue
            start_ms = _to_int(item.get("start_ms"))
            end_ms = _to_int(item.get("end_ms"))
            text = item.get("text")
            if start_ms is None or end_ms is None or text is None:
                continue
            overlays.append(
                {
                    "segment_type": "text_overlay",
                    "start_ms": start_ms,
                    "end_ms": max(end_ms, start_ms + 1),
                    "label": str(text),
                    "confidence": to_float_optional(item.get("confidence")),
                    "details": {"source": field},
                }
            )
        if overlays:
            return overlays, True, "metadata_overlays"

    configured_provider = (get_settings().timeline_ocr_provider or "metadata").strip().lower()
    if configured_provider == "tesseract_cli":
        ocr_segments = _extract_text_overlays_with_tesseract_cli(source_path, duration_ms=duration_ms)
        if ocr_segments:
            return ocr_segments, True, "tesseract_cli"

    return (
        [
            {
                "segment_type": "text_overlay",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "text_overlay_unavailable",
                "details": {
                    "status": "unavailable",
                    "reason": "No OCR/text overlay payload configured",
                },
            }
        ],
        False,
        configured_provider,
    )


def _extract_transcript_with_whisper_cli(
    source_path: Path,
    *,
    duration_ms: int,
) -> List[Dict[str, Any]]:
    whisper_bin = shutil.which("whisper")
    ffmpeg_bin = shutil.which("ffmpeg")
    if whisper_bin is None or ffmpeg_bin is None:
        return []

    try:
        with tempfile.TemporaryDirectory(prefix="alphaengine_asr_") as temp_dir:
            temp_root = Path(temp_dir)
            audio_path = temp_root / "audio.wav"
            ffmpeg_result = _run_subprocess(
                [
                    ffmpeg_bin,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(source_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    str(AUDIO_SAMPLE_RATE),
                    str(audio_path),
                ],
                timeout_seconds=FFMPEG_TIMEOUT_SECONDS,
                check=False,
                text=True,
            )
            if ffmpeg_result.returncode != 0 or not audio_path.exists():
                return []

            whisper_result = _run_subprocess(
                [
                    whisper_bin,
                    str(audio_path),
                    "--model",
                    "tiny",
                    "--output_format",
                    "json",
                    "--output_dir",
                    str(temp_root),
                    "--fp16",
                    "False",
                    "--word_timestamps",
                    "True",
                ],
                timeout_seconds=max(FFMPEG_TIMEOUT_SECONDS, 300),
                check=False,
                text=True,
            )
            if whisper_result.returncode != 0:
                return []

            output_path = temp_root / f"{audio_path.stem}.json"
            if not output_path.exists():
                json_files = sorted(temp_root.glob("*.json"))
                if not json_files:
                    return []
                output_path = json_files[0]

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            segments: List[Dict[str, Any]] = []
            for segment in payload.get("segments", []):
                if not isinstance(segment, dict):
                    continue
                start_ms = int(round(max(to_float_optional(segment.get("start")) or 0.0, 0.0) * 1000.0))
                end_ms = int(round(max(to_float_optional(segment.get("end")) or 0.0, 0.0) * 1000.0))
                text = str(segment.get("text") or "").strip()
                if text:
                    segments.append(
                        {
                            "segment_type": "speech_transcript",
                            "start_ms": start_ms,
                            "end_ms": max(min(end_ms, duration_ms), start_ms + 1),
                            "label": text[:200],
                            "details": {"source": "whisper_cli"},
                        }
                    )
                words = segment.get("words")
                if isinstance(words, list):
                    for word in words:
                        if not isinstance(word, dict):
                            continue
                        token_text = str(word.get("word") or "").strip()
                        token_start = to_float_optional(word.get("start"))
                        token_end = to_float_optional(word.get("end"))
                        if not token_text or token_start is None or token_end is None:
                            continue
                        token_start_ms = int(round(max(token_start, 0.0) * 1000.0))
                        token_end_ms = int(round(max(token_end, 0.0) * 1000.0))
                        segments.append(
                            {
                                "segment_type": "speech_token",
                                "start_ms": token_start_ms,
                                "end_ms": max(min(token_end_ms, duration_ms), token_start_ms + 1),
                                "label": token_text,
                                "confidence": to_float_optional(word.get("probability")),
                                "details": {"source": "whisper_cli_word"},
                            }
                        )

            if segments:
                return sorted(
                    segments,
                    key=lambda item: (
                        int(item.get("start_ms", 0)),
                        int(item.get("end_ms", 0)),
                        str(item.get("segment_type", "")),
                    ),
                )

            transcript_text = str(payload.get("text") or "").strip()
            if transcript_text:
                return [
                    {
                        "segment_type": "speech_transcript",
                        "start_ms": 0,
                        "end_ms": max(duration_ms, 1),
                        "label": transcript_text[:200],
                        "details": {"source": "whisper_cli"},
                    }
                ]
    except Exception:
        logger.exception("whisper_cli provider failed for %s", source_path)
    return []


def _extract_text_overlays_with_tesseract_cli(
    source_path: Path,
    *,
    duration_ms: int,
) -> List[Dict[str, Any]]:
    tesseract_bin = shutil.which("tesseract")
    ffmpeg_bin = shutil.which("ffmpeg")
    if tesseract_bin is None or ffmpeg_bin is None:
        return []

    try:
        with tempfile.TemporaryDirectory(prefix="alphaengine_ocr_") as temp_dir:
            frames_dir = Path(temp_dir) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            frame_pattern = frames_dir / "frame_%06d.png"
            ffmpeg_result = _run_subprocess(
                [
                    ffmpeg_bin,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(source_path),
                    "-vf",
                    "fps=1",
                    str(frame_pattern),
                ],
                timeout_seconds=FFMPEG_TIMEOUT_SECONDS,
                check=False,
                text=True,
            )
            if ffmpeg_result.returncode != 0:
                return []

            overlays: List[Dict[str, Any]] = []
            frames = sorted(frames_dir.glob("frame_*.png"))[:OCR_MAX_FRAMES]
            for index, frame_path in enumerate(frames):
                start_ms = index * 1000
                if start_ms >= duration_ms:
                    break
                tesseract_result = _run_subprocess(
                    [tesseract_bin, str(frame_path), "stdout", "--psm", "6"],
                    timeout_seconds=30,
                    check=False,
                    text=True,
                )
                if tesseract_result.returncode != 0:
                    continue
                raw_text = tesseract_result.stdout if isinstance(tesseract_result.stdout, str) else ""
                normalized = " ".join(raw_text.split()).strip()
                if len(normalized) < 2:
                    continue
                overlays.append(
                    {
                        "segment_type": "text_overlay",
                        "start_ms": start_ms,
                        "end_ms": max(min(start_ms + 1000, duration_ms), start_ms + 1),
                        "label": normalized[:200],
                        "details": {
                            "source": "tesseract_cli",
                            "frame_index": index,
                        },
                    }
                )
            return overlays
    except Exception:
        logger.exception("tesseract_cli provider failed for %s", source_path)
    return []


def _build_trace_outputs(
    *,
    db: Session,
    video_id: UUID,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = db.execute(
        select(
            TracePoint.video_time_ms,
            TracePoint.face_ok,
            TracePoint.face_presence_confidence,
            TracePoint.head_pose_confidence,
        )
        .join(SessionModel, SessionModel.id == TracePoint.session_id)
        .where(
            SessionModel.video_id == video_id,
            TracePoint.video_time_ms.is_not(None),
        )
        .order_by(TracePoint.video_time_ms.asc())
    ).all()

    if not rows:
        return (
            [],
            [
                {
                    "track_name": "face_presence_rate",
                    "start_ms": 0,
                    "end_ms": min(max(duration_ms, 1), 1000),
                    "numeric_value": None,
                    "unit": "ratio",
                    "details": {
                        "status": "unavailable",
                        "reason": "No trace_points available for face/subject features",
                    },
                },
                {
                    "track_name": "face_count_proxy",
                    "start_ms": 0,
                    "end_ms": min(max(duration_ms, 1), 1000),
                    "numeric_value": None,
                    "unit": "proxy_count",
                    "details": {
                        "status": "unavailable",
                        "reason": "No trace_points available for face count proxy",
                    },
                },
                {
                    "track_name": "primary_subject_persistence",
                    "start_ms": 0,
                    "end_ms": max(duration_ms, 1),
                    "numeric_value": None,
                    "unit": "ratio",
                    "details": {
                        "status": "unavailable",
                        "reason": "No trace_points available for subject persistence proxy",
                    },
                },
            ],
        )

    buckets: Dict[int, Dict[str, float]] = {}
    for row in rows:
        video_time_ms = int(row.video_time_ms or 0)
        bucket_ms = (video_time_ms // 1000) * 1000
        acc = buckets.setdefault(
            bucket_ms,
            {
                "count": 0.0,
                "face_ok_sum": 0.0,
                "face_conf_sum": 0.0,
                "face_conf_count": 0.0,
                "head_conf_sum": 0.0,
                "head_conf_count": 0.0,
            },
        )
        acc["count"] += 1.0
        acc["face_ok_sum"] += 1.0 if bool(row.face_ok) else 0.0
        if row.face_presence_confidence is not None:
            acc["face_conf_sum"] += float(row.face_presence_confidence)
            acc["face_conf_count"] += 1.0
        if row.head_pose_confidence is not None:
            acc["head_conf_sum"] += float(row.head_pose_confidence)
            acc["head_conf_count"] += 1.0

    tracks: List[Dict[str, Any]] = []
    stable_windows: List[tuple[int, int]] = []
    ordered_bucket_times = sorted(buckets.keys())
    active_window_start: Optional[int] = None
    stable_bucket_count = 0

    for bucket_ms in ordered_bucket_times:
        acc = buckets[bucket_ms]
        count = max(acc["count"], 1.0)
        presence_rate = acc["face_ok_sum"] / count
        face_conf = (
            acc["face_conf_sum"] / acc["face_conf_count"]
            if acc["face_conf_count"] > 0
            else None
        )
        head_conf = (
            acc["head_conf_sum"] / acc["head_conf_count"]
            if acc["head_conf_count"] > 0
            else None
        )
        window_end = min(bucket_ms + 1000, duration_ms)
        tracks.append(
            {
                "track_name": "face_presence_rate",
                "start_ms": bucket_ms,
                "end_ms": max(window_end, bucket_ms + 1),
                "numeric_value": round(presence_rate, 6),
                "unit": "ratio",
                "details": {"mean_face_presence_confidence": round(face_conf, 6) if face_conf is not None else None},
            }
        )
        tracks.append(
            {
                "track_name": "face_count_proxy",
                "start_ms": bucket_ms,
                "end_ms": max(window_end, bucket_ms + 1),
                "numeric_value": round(presence_rate, 6),
                "unit": "proxy_count",
                "details": {
                    "method": "single_viewer_face_presence_proxy",
                    "note": "Not a multi-person detector count.",
                },
            }
        )

        is_stable = presence_rate >= 0.7 and (head_conf is None or head_conf >= 0.5)
        if is_stable:
            stable_bucket_count += 1
            if active_window_start is None:
                active_window_start = bucket_ms
        elif active_window_start is not None:
            stable_windows.append((active_window_start, bucket_ms))
            active_window_start = None

    if active_window_start is not None:
        stable_windows.append((active_window_start, min(duration_ms, active_window_start + 1000)))

    persistence_ratio = stable_bucket_count / float(max(len(ordered_bucket_times), 1))
    tracks.append(
        {
            "track_name": "primary_subject_persistence",
            "start_ms": 0,
            "end_ms": max(duration_ms, 1),
            "numeric_value": round(persistence_ratio, 6),
            "unit": "ratio",
            "details": {
                "stable_bucket_count": stable_bucket_count,
                "bucket_count": len(ordered_bucket_times),
                "method": "face_presence_head_pose_proxy",
            },
        }
    )

    segments = [
        {
            "segment_type": "primary_subject_window",
            "start_ms": start_ms,
            "end_ms": max(end_ms, start_ms + 1),
            "label": "subject_persistence_window",
            "confidence": 0.6,
            "details": {"method": "face_presence_head_pose_proxy"},
        }
        for start_ms, end_ms in stable_windows
    ]
    return segments, tracks


def _build_object_salience_tracks(video: Video, *, duration_ms: int) -> List[Dict[str, Any]]:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    raw_candidates = (
        metadata.get("object_salience_candidates")
        or metadata.get("object_labels")
        or metadata.get("salient_objects")
    )
    tracks: List[Dict[str, Any]] = []
    if isinstance(raw_candidates, list) and raw_candidates:
        for index, candidate in enumerate(raw_candidates):
            if isinstance(candidate, dict):
                label = candidate.get("label") or candidate.get("name")
                score = to_float_optional(candidate.get("score") or candidate.get("confidence"))
            else:
                label = str(candidate)
                score = None
            if label is None or not str(label).strip():
                continue
            tracks.append(
                {
                    "track_name": "object_salience_candidate",
                    "start_ms": 0,
                    "end_ms": max(duration_ms, 1),
                    "numeric_value": score,
                    "text_value": str(label).strip(),
                    "details": {"rank": index + 1, "source": "metadata"},
                }
            )
    if tracks:
        return tracks
    return [
        {
            "track_name": "object_salience_candidate",
            "start_ms": 0,
            "end_ms": max(duration_ms, 1),
            "text_value": None,
            "numeric_value": None,
            "details": {
                "status": "unavailable",
                "reason": "Object salience candidates were not provided by upstream detection.",
            },
        }
    ]


def _apply_analysis_retention_policy(
    db: Session,
    *,
    video_id: UUID,
    asset_id: str,
    analysis_version: str,
    keep_limit: int,
    protect_analysis_id: UUID,
) -> None:
    if keep_limit <= 0:
        return

    completed_rows = db.scalars(
        select(VideoTimelineAnalysis)
        .where(
            VideoTimelineAnalysis.video_id == video_id,
            VideoTimelineAnalysis.asset_id == asset_id,
            VideoTimelineAnalysis.analysis_version == analysis_version,
            VideoTimelineAnalysis.status == "completed",
        )
        .order_by(
            VideoTimelineAnalysis.completed_at.desc(),
            VideoTimelineAnalysis.created_at.desc(),
        )
    ).all()

    stale_rows = completed_rows[keep_limit:]
    for row in stale_rows:
        if row.id == protect_analysis_id:
            continue
        db.delete(row)


def _replace_analysis_rows(
    *,
    db: Session,
    analysis: VideoTimelineAnalysis,
    asset_id: str,
    segments: Sequence[Dict[str, Any]],
    tracks: Sequence[Dict[str, Any]],
) -> None:
    db.execute(
        delete(VideoTimelineSegment).where(VideoTimelineSegment.analysis_id == analysis.id)
    )
    db.execute(
        delete(VideoFeatureTrack).where(VideoFeatureTrack.analysis_id == analysis.id)
    )

    for segment in segments:
        db.add(
            VideoTimelineSegment(
                analysis_id=analysis.id,
                asset_id=asset_id,
                segment_type=str(segment["segment_type"]),
                start_ms=int(segment["start_ms"]),
                end_ms=int(segment["end_ms"]),
                label=_to_optional_str(segment.get("label")),
                confidence=to_float_optional(segment.get("confidence")),
                details=segment.get("details") if isinstance(segment.get("details"), dict) else None,
            )
        )

    for track in tracks:
        db.add(
            VideoFeatureTrack(
                analysis_id=analysis.id,
                asset_id=asset_id,
                track_name=str(track["track_name"]),
                start_ms=int(track["start_ms"]),
                end_ms=int(track["end_ms"]),
                numeric_value=to_float_optional(track.get("numeric_value")),
                text_value=_to_optional_str(track.get("text_value")),
                unit=_to_optional_str(track.get("unit")),
                details=track.get("details") if isinstance(track.get("details"), dict) else None,
            )
        )


def _mark_analysis_failed(
    db: Session,
    analysis: Optional[VideoTimelineAnalysis],
    error_message: str,
) -> None:
    if analysis is None:
        db.rollback()
        return
    try:
        db.rollback()
        managed = db.get(VideoTimelineAnalysis, analysis.id)
        if managed is None:
            return
        meta = dict(managed.metadata_json or {})
        meta["error"] = error_message
        managed.metadata_json = meta
        managed.status = "failed"
        managed.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:  # pragma: no cover - defensive failure path
        db.rollback()
        logger.exception("Failed to persist timeline analysis failure state")


def _analysis_to_job_response(
    analysis: VideoTimelineAnalysis,
    *,
    reused_existing: bool,
) -> TimelineAnalysisJobResponse:
    metadata = dict(analysis.metadata_json or {})
    metadata["reused_existing"] = reused_existing
    return TimelineAnalysisJobResponse(
        analysis_id=analysis.id,
        video_id=analysis.video_id,
        asset_id=analysis.asset_id,
        analysis_version=analysis.analysis_version,
        asset_fingerprint=analysis.asset_fingerprint,
        status=analysis.status,
        reused_existing=reused_existing,
        started_at=analysis.started_at,
        completed_at=analysis.completed_at,
        metadata=metadata,
    )


def _normalize_segment(segment: Dict[str, Any], *, duration_ms: int) -> Dict[str, Any]:
    start_ms = max(int(segment.get("start_ms", 0)), 0)
    end_ms = int(segment.get("end_ms", start_ms + 1))
    if duration_ms > 0:
        start_ms = min(start_ms, duration_ms)
        end_ms = min(max(end_ms, start_ms + 1), max(duration_ms, start_ms + 1))
    else:
        end_ms = max(end_ms, start_ms + 1)
    return {
        "segment_type": str(segment.get("segment_type", "unknown")),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "label": _to_optional_str(segment.get("label")),
        "confidence": to_float_optional(segment.get("confidence")),
        "details": segment.get("details") if isinstance(segment.get("details"), dict) else None,
    }


def _normalize_track(track: Dict[str, Any], *, duration_ms: int) -> Dict[str, Any]:
    start_ms = max(int(track.get("start_ms", 0)), 0)
    end_ms = int(track.get("end_ms", start_ms + 1))
    if duration_ms > 0:
        start_ms = min(start_ms, duration_ms)
        end_ms = min(max(end_ms, start_ms + 1), max(duration_ms, start_ms + 1))
    else:
        end_ms = max(end_ms, start_ms + 1)
    return {
        "track_name": str(track.get("track_name", "unknown")),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "numeric_value": to_float_optional(track.get("numeric_value")),
        "text_value": _to_optional_str(track.get("text_value")),
        "unit": _to_optional_str(track.get("unit")),
        "details": track.get("details") if isinstance(track.get("details"), dict) else None,
    }


def _run_subprocess(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    check: bool = True,
    text: bool = False,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=text,
        timeout=timeout_seconds,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore") if isinstance(result.stderr, bytes) else str(result.stderr)
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)} :: {stderr[:400]}"
        )
    return result


def _parse_rational(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if "/" in text:
            numerator, denominator = text.split("/", maxsplit=1)
            num = to_float_optional(numerator)
            den = to_float_optional(denominator)
            if num is None or den is None or abs(den) < 1e-9:
                return None
            return num / den
        return to_float_optional(text)
    return None


def _percentile(values: Sequence[int], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(float(item) for item in values)
    position = max(min(percentile, 1.0), 0.0) * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 6)
    fraction = position - lower
    return round((ordered[lower] * (1.0 - fraction)) + (ordered[upper] * fraction), 6)


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
