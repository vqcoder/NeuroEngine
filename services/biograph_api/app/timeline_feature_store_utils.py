"""Utility helpers for timeline feature store: DB ops, normalization, subprocess."""

from __future__ import annotations

import logging
import math
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .models import (
    VideoFeatureTrack,
    VideoTimelineAnalysis,
    VideoTimelineSegment,
)
from .schemas import TimelineAnalysisJobResponse
from .services_math import to_float_optional

logger = logging.getLogger(__name__)


def _apply_analysis_retention_policy(
    db: Session,
    *,
    video_id,
    asset_id: str,
    analysis_version: str,
    keep_limit: int,
    protect_analysis_id,
) -> None:
    from sqlalchemy import select

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
