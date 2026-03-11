"""Boundary encoding diagnostics from event-boundary placement and payload timing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import to_float_optional, row_series_mean

from .schemas import (
    BoundaryEncodingDiagnostics,
    BoundaryEncodingFlag,
    BoundaryEncodingFlagSeverity,
    BoundaryEncodingPathway,
    BoundaryEncodingTimelineWindow,
    BoundaryEncodingTimelineWindowType,
    FeatureTrackRead,
    ReadoutCtaMarker,
    ReadoutCut,
    ReadoutScene,
    TimelineSegmentRead,
)


@dataclass(frozen=True)
class BoundaryEncodingConfig:
    boundary_window_ms: int = 1200
    payload_boundary_distance_ms: int = 900
    poor_timing_distance_ms: int = 1600
    reinforcement_min_gap_ms: int = 1200
    reinforcement_max_gap_ms: int = 6500
    overload_payload_threshold: int = 3
    strong_window_threshold: float = 68.0
    weak_window_threshold: float = 45.0
    fallback_confidence_cap: float = 0.68
    top_window_limit: int = 5


@dataclass(frozen=True)
class _PayloadWindow:
    start_ms: int
    end_ms: int
    payload_type: str
    label: str
    semantic_key: str


@dataclass(frozen=True)
class _PayloadSample:
    payload: _PayloadWindow
    score_unit: float
    confidence: float
    reason: str
    nearest_boundary_ms: Optional[int]
    boundary_distance_ms: Optional[int]
    novelty_signal: Optional[float]
    reinforcement_signal: Optional[float]


_KEYWORD_PATTERN = re.compile(r"(brand|claim|product|offer|cta|deal|price|save|promo|benefit|proof)", re.IGNORECASE)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def resolve_boundary_encoding_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> BoundaryEncodingConfig:
    """Build boundary encoding config from env and optional per-video metadata."""

    config = BoundaryEncodingConfig()
    settings_overrides = _parse_override_payload(get_settings().boundary_encoding_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("boundary_encoding_config", "boundaryEncodingConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def compute_boundary_encoding_diagnostics(
    *,
    scenes: Sequence[ReadoutScene],
    cuts: Sequence[ReadoutCut],
    cta_markers: Sequence[ReadoutCtaMarker],
    bucket_rows: Sequence[Dict[str, object]],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]] = (),
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]] = (),
    window_ms: int,
    config: Optional[BoundaryEncodingConfig] = None,
) -> BoundaryEncodingDiagnostics:
    """Estimate memory-oriented boundary encoding from timeline-local structure."""

    resolved = config or BoundaryEncodingConfig()
    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    if not rows:
        return BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.insufficient_data,
            evidence_summary="No timeline buckets were available for boundary encoding diagnostics.",
            signals_used=[],
        )

    payloads = _resolve_payload_windows(
        cta_markers=cta_markers,
        timeline_segments=timeline_segments,
        scenes=scenes,
        cuts=cuts,
    )
    boundary_times = _resolve_boundary_times(
        scenes=scenes,
        cuts=cuts,
        timeline_segments=timeline_segments,
    )
    if not boundary_times:
        boundary_times = _infer_boundary_times_from_rows(rows, window_ms=max(int(window_ms), 1))

    if not payloads and not boundary_times:
        return BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.insufficient_data,
            evidence_summary=(
                "No payload windows or event boundaries were available for boundary encoding diagnostics."
            ),
            signals_used=[],
        )

    reinforcement_by_index = _build_reinforcement_lookup(payloads, resolved)
    boundary_payload_counts: Dict[int, int] = {boundary: 0 for boundary in boundary_times}
    samples: List[_PayloadSample] = []

    alignment_units: List[float] = []
    novelty_units: List[float] = []
    reinforcement_units: List[float] = []
    timing_units: List[float] = []

    quality_mean = mean_optional(
        [
            row_series_mean(rows, ("tracking_confidence",)),
            row_series_mean(rows, ("quality_score",)),
        ]
    ) or 0.48

    for index, payload in enumerate(payloads):
        midpoint_ms = int((payload.start_ms + payload.end_ms) / 2)
        nearest_boundary_ms, distance_ms = _nearest_boundary(midpoint_ms, boundary_times)
        if nearest_boundary_ms is not None:
            boundary_payload_counts[nearest_boundary_ms] = boundary_payload_counts.get(nearest_boundary_ms, 0) + 1

        if distance_ms is None:
            alignment_unit = 0.35
            timing_unit = 0.45
        else:
            alignment_unit = clamp(
                1.0 - (float(distance_ms) / max(float(resolved.payload_boundary_distance_ms), 1e-6)),
                0.0,
                1.0,
            )
            timing_unit = 1.0
            if distance_ms > int(resolved.poor_timing_distance_ms):
                timing_unit = clamp(
                    1.0
                    - (
                        (float(distance_ms) - float(resolved.poor_timing_distance_ms))
                        / max(float(resolved.poor_timing_distance_ms), 1e-6)
                    ),
                    0.0,
                    0.65,
                )

        novelty_value = _value_at_time(rows, midpoint_ms, keys=("novelty_proxy", "attention_score"))
        novelty_unit = clamp((novelty_value or 50.0) / 100.0, 0.0, 1.0)

        reinforcement_signal = reinforcement_by_index.get(index, 0.0)
        local_overload_penalty = 0.0
        if nearest_boundary_ms is not None:
            local_count = boundary_payload_counts.get(nearest_boundary_ms, 0)
            if local_count > int(resolved.overload_payload_threshold):
                local_overload_penalty = clamp(
                    (float(local_count - int(resolved.overload_payload_threshold)) / 3.0),
                    0.0,
                    0.35,
                )

        local_unit = clamp(
            (0.42 * alignment_unit)
            + (0.28 * novelty_unit)
            + (0.18 * reinforcement_signal)
            + (0.12 * timing_unit)
            - local_overload_penalty,
            0.0,
            1.0,
        )
        local_confidence = clamp(
            (0.55 * quality_mean)
            + (0.25 * (1.0 if novelty_value is not None else 0.55))
            + (0.2 * (0.9 if nearest_boundary_ms is not None else 0.6)),
            0.0,
            1.0,
        )

        reason_bits = []
        if nearest_boundary_ms is not None and distance_ms is not None:
            if distance_ms <= int(resolved.payload_boundary_distance_ms):
                reason_bits.append("Payload aligned close to an event boundary")
            else:
                reason_bits.append("Payload was placed far from the nearest event boundary")
        else:
            reason_bits.append("Boundary alignment fell back to trace-only inference")

        if novelty_unit >= 0.6:
            reason_bits.append("novelty support was present")
        else:
            reason_bits.append("novelty support was limited")

        if reinforcement_signal >= 1.0:
            reason_bits.append("reinforcement repeated within a memory-friendly spacing window")

        if local_overload_penalty > 0:
            reason_bits.append("payload density near the boundary increased overload risk")

        samples.append(
            _PayloadSample(
                payload=payload,
                score_unit=local_unit,
                confidence=local_confidence,
                reason="; ".join(reason_bits) + ".",
                nearest_boundary_ms=nearest_boundary_ms,
                boundary_distance_ms=distance_ms,
                novelty_signal=round(novelty_unit, 6),
                reinforcement_signal=round(reinforcement_signal, 6),
            )
        )

        alignment_units.append(alignment_unit)
        novelty_units.append(novelty_unit)
        reinforcement_units.append(reinforcement_signal)
        timing_units.append(timing_unit)

    overload_risk_score, overload_flags = _build_overload_flags(
        boundary_payload_counts=boundary_payload_counts,
        config=resolved,
    )

    weak_timing_samples = [
        sample
        for sample in samples
        if sample.boundary_distance_ms is not None
        and sample.boundary_distance_ms > int(resolved.poor_timing_distance_ms)
    ]
    poor_timing_flags = [
        BoundaryEncodingFlag(
            flag_key="poor_payload_timing",
            severity=(
                BoundaryEncodingFlagSeverity.high
                if (sample.boundary_distance_ms or 0) > (int(resolved.poor_timing_distance_ms) * 2)
                else BoundaryEncodingFlagSeverity.medium
            ),
            message=(
                "Important payload was introduced away from an event boundary, reducing chunked encoding support."
            ),
            start_ms=int(sample.payload.start_ms),
            end_ms=int(sample.payload.end_ms),
            metric_value=(
                float(sample.boundary_distance_ms)
                if sample.boundary_distance_ms is not None
                else None
            ),
        )
        for sample in weak_timing_samples[:3]
    ]

    flags: List[BoundaryEncodingFlag] = [*overload_flags, *poor_timing_flags]

    has_timeline_boundary_support = bool(boundary_times) and _has_segment(
        timeline_segments,
        "shot_boundary",
    )
    pathway = (
        BoundaryEncodingPathway.timeline_boundary_model
        if payloads and has_timeline_boundary_support
        else BoundaryEncodingPathway.fallback_proxy
    )

    if not payloads:
        boundary_novelty = _boundary_novelty_score(rows, boundary_times, resolved)
        global_unit = clamp((0.6 * boundary_novelty) + (0.4 * (1.0 - overload_risk_score)), 0.0, 1.0)
        confidence = clamp((0.55 * quality_mean) + (0.25 * boundary_novelty) + 0.12, 0.0, 1.0)
        confidence = min(confidence, 0.52)
        flags.append(
            BoundaryEncodingFlag(
                flag_key="payload_markers_missing",
                severity=BoundaryEncodingFlagSeverity.medium,
                message=(
                    "Important payload markers were sparse, so boundary encoding used a low-confidence fallback."
                ),
                metric_value=0.0,
            )
        )
        return BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.fallback_proxy,
            global_score=round(global_unit * 100.0, 6),
            confidence=round(confidence, 6),
            strong_windows=[],
            weak_windows=[],
            flags=flags,
            boundary_alignment_score=None,
            novelty_boundary_score=round(boundary_novelty, 6),
            reinforcement_score=0.0,
            overload_risk_score=round(overload_risk_score, 6),
            payload_count=0,
            boundary_count=len(boundary_times),
            evidence_summary=(
                "Boundary encoding fallback estimated novelty around inferred boundaries, but payload placement signals were limited."
            ),
            signals_used=[
                "novelty_proxy",
                "scene_graph_boundaries",
                "timeline_shot_boundaries",
            ],
        )

    alignment_score = mean_optional(alignment_units) or 0.0
    novelty_score = mean_optional(novelty_units) or 0.0
    reinforcement_score = mean_optional(reinforcement_units) or 0.0
    timing_score = mean_optional(timing_units) or 0.0

    global_unit = clamp(
        (0.38 * alignment_score)
        + (0.25 * novelty_score)
        + (0.21 * reinforcement_score)
        + (0.16 * timing_score),
        0.0,
        1.0,
    )
    global_unit *= (1.0 - (0.45 * overload_risk_score))
    global_unit = clamp(global_unit, 0.0, 1.0)

    sample_coverage = clamp(float(len(samples)) / 4.0, 0.0, 1.0)
    boundary_coverage = clamp(float(len(boundary_times)) / 6.0, 0.0, 1.0)
    signal_coverage = clamp(
        (0.45 * sample_coverage)
        + (0.35 * boundary_coverage)
        + (0.2 * (1.0 if _has_track(timeline_feature_tracks, "cut_cadence") else 0.6)),
        0.0,
        1.0,
    )
    confidence = clamp((0.45 * quality_mean) + (0.35 * signal_coverage) + 0.2, 0.0, 1.0)
    if pathway == BoundaryEncodingPathway.fallback_proxy:
        confidence = min(confidence, float(resolved.fallback_confidence_cap))

    strong_windows, weak_windows = _classify_windows(samples, resolved)

    weak_ratio = float(len(weak_windows)) / float(max(len(samples), 1))
    if weak_ratio >= 0.5:
        flags.append(
            BoundaryEncodingFlag(
                flag_key="memory_timing_weakness",
                severity=BoundaryEncodingFlagSeverity.medium,
                message=(
                    "A majority of payload windows had weak boundary timing support for chunked memory encoding."
                ),
                metric_value=round(weak_ratio, 6),
            )
        )

    best_sample = max(samples, key=lambda item: item.score_unit)
    worst_sample = min(samples, key=lambda item: item.score_unit)

    evidence_summary = (
        "Boundary encoding emphasizes event-boundary timing, novelty at placement, reinforcement spacing, and overload risk. "
        "It does not treat memory potential as equivalent to emotional intensity. "
        f"Strongest window: {best_sample.reason} Weakest window: {worst_sample.reason}"
    )

    signals_used = [
        "scene_graph_boundaries",
        "timeline_shot_boundaries",
        "cta_windows",
        "text_overlay_payloads",
        "novelty_proxy",
    ]
    if _has_track(timeline_feature_tracks, "cut_cadence"):
        signals_used.append("cut_cadence")

    return BoundaryEncodingDiagnostics(
        pathway=pathway,
        global_score=round(global_unit * 100.0, 6),
        confidence=round(confidence, 6),
        strong_windows=strong_windows,
        weak_windows=weak_windows,
        flags=flags,
        boundary_alignment_score=round(alignment_score, 6),
        novelty_boundary_score=round(novelty_score, 6),
        reinforcement_score=round(reinforcement_score, 6),
        overload_risk_score=round(overload_risk_score, 6),
        payload_count=len(payloads),
        boundary_count=len(boundary_times),
        evidence_summary=evidence_summary,
        signals_used=signals_used,
    )


def _parse_override_payload(raw_value: object) -> Dict[str, object]:
    if raw_value is None:
        return {}
    if isinstance(raw_value, Mapping):
        return dict(raw_value)
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if not candidate:
            return {}
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            return {}
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _apply_overrides(
    config: BoundaryEncodingConfig,
    overrides: Mapping[str, object],
) -> BoundaryEncodingConfig:
    allowed_fields = {field.name for field in fields(config)}
    replacement: Dict[str, object] = {}
    for key, value in overrides.items():
        if key in allowed_fields:
            replacement[key] = value
    if not replacement:
        return config
    try:
        return replace(config, **replacement)
    except TypeError:
        return config


def _resolve_payload_windows(
    *,
    cta_markers: Sequence[ReadoutCtaMarker],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    scenes: Sequence[ReadoutScene],
    cuts: Sequence[ReadoutCut],
) -> List[_PayloadWindow]:
    windows: List[_PayloadWindow] = []
    for marker in cta_markers:
        start_ms = int(marker.start_ms if marker.start_ms is not None else marker.video_time_ms)
        end_ms = int(marker.end_ms if marker.end_ms is not None else (start_ms + 1000))
        label = (marker.label or marker.cta_id or "cta").strip()
        windows.append(
            _PayloadWindow(
                start_ms=start_ms,
                end_ms=max(end_ms, start_ms + 1),
                payload_type="cta",
                label=label,
                semantic_key=_semantic_key(label, "cta", marker.cta_id),
            )
        )

    for segment in timeline_segments:
        segment_type = str(_item_field(segment, "segment_type", ""))
        if segment_type not in {"text_overlay", "cta_window"}:
            continue
        start_ms = int(_item_field(segment, "start_ms", 0) or 0)
        end_ms = int(_item_field(segment, "end_ms", start_ms + 1) or (start_ms + 1))
        label = str(_item_field(segment, "label", "") or "").strip()
        if "unavailable" in label.lower():
            continue
        payload_type = "text_overlay" if segment_type == "text_overlay" else "cta"
        windows.append(
            _PayloadWindow(
                start_ms=start_ms,
                end_ms=max(end_ms, start_ms + 1),
                payload_type=payload_type,
                label=label or payload_type,
                semantic_key=_semantic_key(label, payload_type, None),
            )
        )

    for scene in scenes:
        label = (scene.label or "").strip()
        if label and _KEYWORD_PATTERN.search(label):
            windows.append(
                _PayloadWindow(
                    start_ms=int(scene.start_ms),
                    end_ms=max(int(scene.end_ms), int(scene.start_ms) + 1),
                    payload_type="scene_label",
                    label=label,
                    semantic_key=_semantic_key(label, "scene_label", scene.scene_id),
                )
            )

    for cut in cuts:
        label = (cut.label or "").strip()
        if label and _KEYWORD_PATTERN.search(label):
            windows.append(
                _PayloadWindow(
                    start_ms=int(cut.start_ms),
                    end_ms=max(int(cut.end_ms), int(cut.start_ms) + 1),
                    payload_type="cut_label",
                    label=label,
                    semantic_key=_semantic_key(label, "cut_label", cut.cut_id),
                )
            )

    unique: Dict[tuple[int, int, str, str], _PayloadWindow] = {}
    for item in windows:
        key = (item.start_ms, item.end_ms, item.payload_type, item.semantic_key)
        unique[key] = item
    return sorted(unique.values(), key=lambda item: (item.start_ms, item.end_ms))


def _semantic_key(label: str, payload_type: str, identifier: Optional[str]) -> str:
    text = label.strip().lower()
    keyword_match = _KEYWORD_PATTERN.search(text)
    if keyword_match is not None:
        return f"{payload_type}:{keyword_match.group(1)}"

    tokens = [token for token in _TOKEN_PATTERN.findall(text) if len(token) >= 3]
    if tokens:
        return f"{payload_type}:{tokens[0]}"
    if identifier:
        return f"{payload_type}:{identifier}"
    return f"{payload_type}:generic"


def _resolve_boundary_times(
    *,
    scenes: Sequence[ReadoutScene],
    cuts: Sequence[ReadoutCut],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
) -> List[int]:
    boundary_times: set[int] = set()

    for cut in cuts:
        boundary_times.add(int(cut.start_ms))

    for scene in scenes:
        if int(scene.start_ms) > 0:
            boundary_times.add(int(scene.start_ms))

    for segment in timeline_segments:
        segment_type = str(_item_field(segment, "segment_type", ""))
        if segment_type in {"shot_boundary", "scene_block"}:
            start_ms = int(_item_field(segment, "start_ms", 0) or 0)
            if start_ms > 0:
                boundary_times.add(start_ms)

    return sorted(boundary_times)


def _infer_boundary_times_from_rows(rows: Sequence[Dict[str, object]], window_ms: int) -> List[int]:
    candidates: List[int] = []
    for row in rows:
        velocity = to_float_optional(row.get("attention_velocity"))
        novelty = to_float_optional(row.get("novelty_proxy"))
        if velocity is not None and abs(velocity) >= 8.0:
            candidates.append(int(row["bucket_start"]))
            continue
        if novelty is not None and novelty >= 70.0:
            candidates.append(int(row["bucket_start"]))

    if not candidates:
        return []

    candidates = sorted(set(candidates))
    merged: List[int] = []
    for candidate in candidates:
        if not merged or (candidate - merged[-1]) >= max(int(window_ms), 1):
            merged.append(candidate)
    return merged


def _build_reinforcement_lookup(
    payloads: Sequence[_PayloadWindow],
    config: BoundaryEncodingConfig,
) -> Dict[int, float]:
    grouped: Dict[str, List[tuple[int, _PayloadWindow]]] = {}
    for index, payload in enumerate(payloads):
        grouped.setdefault(payload.semantic_key, []).append((index, payload))

    reinforcement: Dict[int, float] = {}
    for group in grouped.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: (item[1].start_ms, item[1].end_ms))
        for left_index, (first_i, first_payload) in enumerate(ordered):
            for second_i, second_payload in ordered[left_index + 1 :]:
                gap = int(second_payload.start_ms) - int(first_payload.end_ms)
                if gap < int(config.reinforcement_min_gap_ms):
                    continue
                if gap > int(config.reinforcement_max_gap_ms):
                    break
                reinforcement[first_i] = max(reinforcement.get(first_i, 0.0), 1.0)
                reinforcement[second_i] = max(reinforcement.get(second_i, 0.0), 1.0)

    return reinforcement


def _classify_windows(
    samples: Sequence[_PayloadSample],
    config: BoundaryEncodingConfig,
) -> tuple[List[BoundaryEncodingTimelineWindow], List[BoundaryEncodingTimelineWindow]]:
    strong: List[BoundaryEncodingTimelineWindow] = []
    weak: List[BoundaryEncodingTimelineWindow] = []

    for sample in samples:
        score = round(float(sample.score_unit) * 100.0, 6)
        window = BoundaryEncodingTimelineWindow(
            start_ms=int(sample.payload.start_ms),
            end_ms=int(sample.payload.end_ms),
            score=score,
            confidence=round(float(sample.confidence), 6),
            window_type=(
                BoundaryEncodingTimelineWindowType.strong_encoding
                if score >= float(config.strong_window_threshold)
                else BoundaryEncodingTimelineWindowType.weak_encoding
            ),
            reason=sample.reason,
            payload_type=sample.payload.payload_type,
            nearest_boundary_ms=sample.nearest_boundary_ms,
            boundary_distance_ms=sample.boundary_distance_ms,
            novelty_signal=sample.novelty_signal,
            reinforcement_signal=sample.reinforcement_signal,
        )
        if score >= float(config.strong_window_threshold):
            strong.append(window)
        if score <= float(config.weak_window_threshold):
            weak.append(window)

    ordered = sorted(samples, key=lambda item: item.score_unit)
    if not strong and ordered:
        best = ordered[-1]
        strong.append(
            BoundaryEncodingTimelineWindow(
                start_ms=int(best.payload.start_ms),
                end_ms=int(best.payload.end_ms),
                score=round(float(best.score_unit) * 100.0, 6),
                confidence=round(float(best.confidence), 6),
                window_type=BoundaryEncodingTimelineWindowType.strong_encoding,
                reason="Best available payload window under current boundary support.",
                payload_type=best.payload.payload_type,
                nearest_boundary_ms=best.nearest_boundary_ms,
                boundary_distance_ms=best.boundary_distance_ms,
                novelty_signal=best.novelty_signal,
                reinforcement_signal=best.reinforcement_signal,
            )
        )
    if not weak and len(ordered) >= 2:
        worst = ordered[0]
        weak.append(
            BoundaryEncodingTimelineWindow(
                start_ms=int(worst.payload.start_ms),
                end_ms=int(worst.payload.end_ms),
                score=round(float(worst.score_unit) * 100.0, 6),
                confidence=round(float(worst.confidence), 6),
                window_type=BoundaryEncodingTimelineWindowType.weak_encoding,
                reason="Weakest payload window under current boundary support.",
                payload_type=worst.payload.payload_type,
                nearest_boundary_ms=worst.nearest_boundary_ms,
                boundary_distance_ms=worst.boundary_distance_ms,
                novelty_signal=worst.novelty_signal,
                reinforcement_signal=worst.reinforcement_signal,
            )
        )

    return (
        sorted(strong, key=lambda item: float(item.score), reverse=True)[: max(int(config.top_window_limit), 1)],
        sorted(weak, key=lambda item: float(item.score))[: max(int(config.top_window_limit), 1)],
    )


def _build_overload_flags(
    *,
    boundary_payload_counts: Mapping[int, int],
    config: BoundaryEncodingConfig,
) -> tuple[float, List[BoundaryEncodingFlag]]:
    if not boundary_payload_counts:
        return 0.0, []

    threshold = max(int(config.overload_payload_threshold), 1)
    max_count = max(boundary_payload_counts.values())
    overload_risk = clamp(float(max_count - threshold) / float(threshold + 1), 0.0, 1.0)

    flags: List[BoundaryEncodingFlag] = []
    for boundary_ms, count in sorted(boundary_payload_counts.items()):
        if count <= threshold:
            continue
        severity = (
            BoundaryEncodingFlagSeverity.high
            if count >= threshold + 2
            else BoundaryEncodingFlagSeverity.medium
        )
        flags.append(
            BoundaryEncodingFlag(
                flag_key="payload_overload_at_boundary",
                severity=severity,
                message=(
                    "Multiple payloads clustered around one boundary increased cognitive load risk."
                ),
                start_ms=max(int(boundary_ms - int(config.boundary_window_ms)), 0),
                end_ms=int(boundary_ms + int(config.boundary_window_ms)),
                metric_value=float(count),
            )
        )
    return overload_risk, flags


def _nearest_boundary(timestamp_ms: int, boundaries: Sequence[int]) -> tuple[Optional[int], Optional[int]]:
    if not boundaries:
        return None, None
    nearest = min(boundaries, key=lambda item: abs(int(item) - int(timestamp_ms)))
    return int(nearest), abs(int(nearest) - int(timestamp_ms))


def _boundary_novelty_score(
    rows: Sequence[Dict[str, object]],
    boundaries: Sequence[int],
    config: BoundaryEncodingConfig,
) -> float:
    if not boundaries:
        return 0.45
    novelty_units: List[float] = []
    for boundary in boundaries:
        novelty = _value_at_time(
            rows,
            int(boundary),
            keys=("novelty_proxy", "attention_score"),
            tolerance_ms=max(int(config.boundary_window_ms), 1),
        )
        if novelty is None:
            continue
        novelty_units.append(clamp(float(novelty) / 100.0, 0.0, 1.0))
    if not novelty_units:
        return 0.45
    return mean_optional(novelty_units) or 0.45


def _value_at_time(
    rows: Sequence[Dict[str, object]],
    timestamp_ms: int,
    *,
    keys: Sequence[str],
    tolerance_ms: int = 2000,
) -> Optional[float]:
    if not rows:
        return None
    nearest = min(rows, key=lambda item: abs(int(item["bucket_start"]) - int(timestamp_ms)))
    if abs(int(nearest["bucket_start"]) - int(timestamp_ms)) > int(tolerance_ms):
        return None
    for key in keys:
        value = to_float_optional(nearest.get(key))
        if value is not None:
            return value
    return None


def _item_field(item: object, key: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(key, default)  # type: ignore[return-value]
    return getattr(item, key, default)


def _has_segment(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    segment_type: str,
) -> bool:
    return any(str(_item_field(segment, "segment_type", "")) == segment_type for segment in timeline_segments)


def _has_track(
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    track_name: str,
) -> bool:
    return any(str(_item_field(track, "track_name", "")) == track_name for track in timeline_feature_tracks)


