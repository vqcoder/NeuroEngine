"""Readout export-package construction (CSV, peak extraction)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from .domain_exceptions import NotFoundError
from .models import Study, Video
from .schemas import (
    CompactReadoutHighlights,
    CompactReadoutReport,
    ProductRollupMode,
    ReadoutExportJson,
    ReadoutExportPackageResponse,
    ReadoutSegment,
    ReadoutTracePoint,
    ReadoutVideoMetadata,
    RewardProxyPeak,
    VideoReadoutResponse,
)
from .services_readout import build_video_readout


def _ensure_readout_timepoint_row(
    rows_by_time: Dict[int, Dict[str, object]],
    video_time_ms: int,
) -> Dict[str, object]:
    row = rows_by_time.get(video_time_ms)
    if row is not None:
        return row
    row = {
        "video_time_ms": video_time_ms,
        "scene_id": None,
        "cut_id": None,
        "cta_id": None,
        "attention_score": None,
        "attention_velocity": None,
        "blink_rate": None,
        "blink_inhibition": None,
        "reward_proxy": None,
        "valence_proxy": None,
        "arousal_proxy": None,
        "novelty_proxy": None,
        "tracking_confidence": None,
    }
    rows_by_time[video_time_ms] = row
    return row


def _assign_trace_series_to_rows(
    rows_by_time: Dict[int, Dict[str, object]],
    series: Sequence[ReadoutTracePoint],
    field_name: str,
) -> None:
    for point in series:
        row = _ensure_readout_timepoint_row(rows_by_time, int(point.video_time_ms))
        row[field_name] = point.value
        if row["scene_id"] is None and point.scene_id is not None:
            row["scene_id"] = point.scene_id
        if row["cut_id"] is None and point.cut_id is not None:
            row["cut_id"] = point.cut_id
        if row["cta_id"] is None and point.cta_id is not None:
            row["cta_id"] = point.cta_id


def _build_readout_timepoint_rows(
    readout: VideoReadoutResponse,
) -> tuple[List[Dict[str, object]], List[str]]:
    rows_by_time: Dict[int, Dict[str, object]] = {}

    _assign_trace_series_to_rows(rows_by_time, readout.traces.attention_score, "attention_score")
    _assign_trace_series_to_rows(
        rows_by_time,
        readout.traces.attention_velocity,
        "attention_velocity",
    )
    _assign_trace_series_to_rows(rows_by_time, readout.traces.blink_rate, "blink_rate")
    _assign_trace_series_to_rows(
        rows_by_time,
        readout.traces.blink_inhibition,
        "blink_inhibition",
    )
    _assign_trace_series_to_rows(rows_by_time, readout.traces.reward_proxy, "reward_proxy")
    _assign_trace_series_to_rows(rows_by_time, readout.traces.valence_proxy, "valence_proxy")
    _assign_trace_series_to_rows(rows_by_time, readout.traces.arousal_proxy, "arousal_proxy")
    _assign_trace_series_to_rows(rows_by_time, readout.traces.novelty_proxy, "novelty_proxy")
    _assign_trace_series_to_rows(
        rows_by_time,
        readout.traces.tracking_confidence,
        "tracking_confidence",
    )

    au_names: List[str] = [channel.au_name for channel in readout.traces.au_channels]
    for channel in readout.traces.au_channels:
        column_name = f"au_{channel.au_name}"
        for point in channel.points:
            row = _ensure_readout_timepoint_row(rows_by_time, int(point.video_time_ms))
            row[column_name] = point.value
            if row["scene_id"] is None and point.scene_id is not None:
                row["scene_id"] = point.scene_id
            if row["cut_id"] is None and point.cut_id is not None:
                row["cut_id"] = point.cut_id
            if row["cta_id"] is None and point.cta_id is not None:
                row["cta_id"] = point.cta_id

    rows = [rows_by_time[key] for key in sorted(rows_by_time)]
    return rows, au_names


def _render_readout_csv(
    rows: Sequence[Dict[str, object]],
    au_names: Sequence[str],
) -> str:
    header = [
        "video_time_ms",
        "second",
        "scene_id",
        "cut_id",
        "cta_id",
        "attention_score",
        "attention_velocity",
        "blink_rate",
        "blink_inhibition",
        "reward_proxy",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
        "tracking_confidence",
        *[f"au_{name}" for name in au_names],
    ]

    def _fmt(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value)

    content_rows: List[List[str]] = [header]
    for row in rows:
        video_time_ms = int(row["video_time_ms"])
        line = [
            str(video_time_ms),
            f"{video_time_ms / 1000.0:.3f}",
            _fmt(row.get("scene_id")),
            _fmt(row.get("cut_id")),
            _fmt(row.get("cta_id")),
            _fmt(row.get("attention_score")),
            _fmt(row.get("attention_velocity")),
            _fmt(row.get("blink_rate")),
            _fmt(row.get("blink_inhibition")),
            _fmt(row.get("reward_proxy")),
            _fmt(row.get("valence_proxy")),
            _fmt(row.get("arousal_proxy")),
            _fmt(row.get("novelty_proxy")),
            _fmt(row.get("tracking_confidence")),
            *[_fmt(row.get(f"au_{name}")) for name in au_names],
        ]
        content_rows.append(line)

    escaped_lines = []
    for line in content_rows:
        escaped_lines.append(
            ",".join('"' + cell.replace('"', '""') + '"' for cell in line)
        )
    return "\n".join(escaped_lines)


def _build_reward_proxy_peaks(readout: VideoReadoutResponse, limit: int = 5) -> List[RewardProxyPeak]:
    confidence_by_time = {
        item.video_time_ms: item.value for item in readout.traces.tracking_confidence
    }
    candidates = [
        item for item in readout.traces.reward_proxy if item.value is not None
    ]
    ranked = sorted(
        candidates,
        key=lambda item: (-(item.value or 0.0), item.video_time_ms),
    )
    peaks: List[RewardProxyPeak] = []
    for item in ranked[:limit]:
        peaks.append(
            RewardProxyPeak(
                video_time_ms=item.video_time_ms,
                reward_proxy=float(item.value or 0.0),
                scene_id=item.scene_id,
                cut_id=item.cut_id,
                cta_id=item.cta_id,
                tracking_confidence=confidence_by_time.get(item.video_time_ms),
            )
        )
    return peaks


def _top_segment(
    segments: Sequence[ReadoutSegment],
) -> Optional[ReadoutSegment]:
    if not segments:
        return None
    return max(segments, key=lambda item: item.magnitude)


def build_video_readout_export_package(
    db: Session,
    video_id: UUID,
    session_id: Optional[UUID] = None,
    variant_id: Optional[str] = None,
    aggregate: bool = True,
    window_ms: int = 1000,
    product_mode: Optional[ProductRollupMode] = None,
    workspace_tier: Optional[str] = None,
) -> ReadoutExportPackageResponse:
    """Build export package with CSV, rich JSON, and compact report payload."""

    readout = build_video_readout(
        db,
        video_id,
        session_id=session_id,
        variant_id=variant_id,
        aggregate=aggregate,
        window_ms=window_ms,
        product_mode=product_mode,
        workspace_tier=workspace_tier,
    )
    video = db.get(Video, video_id)
    if video is None:
        raise NotFoundError("Video")
    study = db.get(Study, video.study_id)

    generated_at = datetime.now(timezone.utc)
    video_metadata = ReadoutVideoMetadata(
        video_id=video.id,
        study_id=video.study_id,
        study_name=study.name if study is not None else None,
        title=video.title,
        source_url=video.source_url,
        duration_ms=video.duration_ms,
        variant_id=variant_id,
        aggregate=aggregate,
        session_id=session_id,
        window_ms=window_ms,
        generated_at=generated_at,
    )

    rows, au_names = _build_readout_timepoint_rows(readout)
    csv_payload = _render_readout_csv(rows, au_names)
    reward_proxy_peaks = _build_reward_proxy_peaks(readout)

    readout_json = ReadoutExportJson(
        video_metadata=video_metadata,
        scenes=readout.context.scenes,
        cta_markers=readout.context.cta_markers,
        segments=readout.segments,
        diagnostics=readout.diagnostics,
        reward_proxy_peaks=reward_proxy_peaks,
        quality_summary=readout.quality.session_quality_summary,
        annotation_summary=readout.labels.annotation_summary or readout.annotation_summary,
        survey_summary=readout.labels.survey_summary or readout.survey_summary,
        neuro_scores=readout.neuro_scores,
        product_rollups=readout.product_rollups,
        legacy_score_adapters=readout.legacy_score_adapters,
    )

    compact_report = CompactReadoutReport(
        video_metadata=video_metadata,
        scenes=readout.context.scenes,
        cta_markers=readout.context.cta_markers,
        attention_gain_segments=readout.segments.attention_gain_segments,
        attention_loss_segments=readout.segments.attention_loss_segments,
        golden_scenes=readout.segments.golden_scenes,
        dead_zones=readout.segments.dead_zones,
        reward_proxy_peaks=reward_proxy_peaks,
        quality_summary=readout.quality.session_quality_summary,
        annotation_summary=readout.labels.annotation_summary or readout.annotation_summary,
        survey_summary=readout.labels.survey_summary or readout.survey_summary,
        highlights=CompactReadoutHighlights(
            top_reward_proxy_peak=reward_proxy_peaks[0] if reward_proxy_peaks else None,
            top_attention_gain_segment=_top_segment(readout.segments.attention_gain_segments),
            top_attention_loss_segment=_top_segment(readout.segments.attention_loss_segments),
            top_golden_scene=_top_segment(readout.segments.golden_scenes),
            top_dead_zone=_top_segment(readout.segments.dead_zones),
        ),
        neuro_scores=readout.neuro_scores,
        product_rollups=readout.product_rollups,
        legacy_score_adapters=readout.legacy_score_adapters,
    )

    return ReadoutExportPackageResponse(
        video_metadata=video_metadata,
        per_timepoint_csv=csv_payload,
        readout_json=readout_json,
        compact_report=compact_report,
    )
