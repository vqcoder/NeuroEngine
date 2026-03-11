"""Blink transport diagnostics from attentional blink timing and event gating windows."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import to_float_optional

from .schemas import (
    BlinkTransportDiagnostics,
    BlinkTransportPathway,
    BlinkTransportTimelineScore,
    BlinkTransportWarning,
    BlinkTransportWarningSeverity,
    ReadoutCtaMarker,
    TimelineSegmentRead,
)


@dataclass(frozen=True)
class BlinkTransportConfig:
    enabled: bool = True
    min_tracking_confidence: float = 0.3
    min_quality_score: float = 0.25
    high_info_attention_threshold: float = 62.0
    high_info_velocity_threshold: float = 5.5
    high_info_label_signal_threshold: float = 0.3
    boundary_pre_window_ms: int = 1000
    boundary_post_window_ms: int = 1200
    cta_probe_window_ms: int = 1200
    sparse_min_blink_windows: int = 4
    direct_path_min_sessions: int = 2
    direct_path_min_windows: int = 5
    high_variability_std_threshold: float = 0.22
    mistimed_rebound_delta_threshold: float = -0.08
    low_cta_avoidance_threshold: float = 0.35
    fallback_confidence_cap: float = 0.72
    sparse_confidence_cap: float = 0.46


@dataclass(frozen=True)
class _BlinkWindow:
    start_ms: int
    end_ms: int
    attention_score: Optional[float]
    attention_velocity: Optional[float]
    label_signal: Optional[float]
    blink_rate: Optional[float]
    blink_baseline_rate: Optional[float]
    blink_inhibition: Optional[float]
    tracking_confidence: Optional[float]
    quality_score: Optional[float]
    cta_id: Optional[str]
    scene_id: Optional[str]
    cut_id: Optional[str]


@dataclass(frozen=True)
class _BoundaryReboundSample:
    boundary_ms: int
    start_ms: int
    end_ms: int
    rebound_delta: float
    rebound_unit: float
    reason: str


@dataclass(frozen=True)
class _TargetWindowSample:
    start_ms: int
    end_ms: int
    delta: float
    unit: float
    reason: str


def resolve_blink_transport_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> BlinkTransportConfig:
    """Build blink transport settings from env + optional per-video metadata."""

    settings = get_settings()
    config = BlinkTransportConfig(enabled=bool(settings.blink_transport_enabled))
    settings_overrides = _parse_override_payload(settings.blink_transport_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("blink_transport_config", "blinkTransportConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break

        for key in (
            "blink_transport_enabled",
            "blinkTransportEnabled",
            "blink_instrumentation_enabled",
            "blinkInstrumentationEnabled",
        ):
            raw_flag = video_metadata.get(key)
            parsed_flag = _parse_optional_bool(raw_flag)
            if parsed_flag is not None:
                config = replace(config, enabled=parsed_flag)
                break

    return config


def compute_blink_transport_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    session_bucket_rows_by_session: Mapping[object, Mapping[int, Dict[str, object]]],
    cta_markers: Sequence[ReadoutCtaMarker],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]] = (),
    window_ms: int,
    config: Optional[BlinkTransportConfig] = None,
) -> BlinkTransportDiagnostics:
    """Estimate blink transport as attentional timing and event-segmentation behavior."""

    resolved = config or BlinkTransportConfig()
    if not resolved.enabled:
        return BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.disabled,
            evidence_summary=(
                "Blink transport instrumentation is disabled for this environment; score remains unavailable."
            ),
            signals_used=[],
        )

    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    if not rows:
        return BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.insufficient_data,
            evidence_summary="No timeline buckets were available for blink transport diagnostics.",
            signals_used=[],
        )

    resolved_window_ms = max(int(window_ms), 1)
    blink_windows = _to_blink_windows(rows, window_ms=resolved_window_ms)
    if not blink_windows:
        return BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.insufficient_data,
            evidence_summary="Timeline buckets could not be normalized for blink transport diagnostics.",
            signals_used=[],
        )

    reveal_windows = _resolve_segment_windows(timeline_segments, segment_type="text_overlay")
    cta_windows = _resolve_cta_windows(cta_markers, timeline_segments)
    boundary_times = _resolve_boundary_times(timeline_segments, blink_windows)

    reliable_windows = [item for item in blink_windows if _is_blink_reliable(item, resolved)]
    suppression_values = [
        clamp(float(item.blink_inhibition), 0.0, 1.0)
        for item in reliable_windows
        if item.blink_inhibition is not None
    ]

    high_info_windows = [
        item
        for item in reliable_windows
        if _is_high_information_window(item, reveal_windows, resolved)
    ]
    suppression_high_info = [
        clamp(float(item.blink_inhibition), 0.0, 1.0)
        for item in high_info_windows
        if item.blink_inhibition is not None
    ]
    suppression_component = mean_optional(suppression_high_info) or mean_optional(suppression_values) or 0.0

    rebound_samples = _compute_boundary_rebounds(
        reliable_windows,
        boundary_times=boundary_times,
        config=resolved,
    )
    rebound_component = mean_optional([item.rebound_unit for item in rebound_samples]) or 0.0

    target_samples = _compute_target_window_samples(
        reliable_windows,
        target_windows=[*cta_windows, *reveal_windows],
        probe_window_ms=resolved.cta_probe_window_ms,
    )
    cta_avoidance_component = mean_optional([item.unit for item in target_samples])
    if cta_avoidance_component is None:
        cta_avoidance_component = 0.5

    panel_synchrony = _compute_panel_blink_synchrony(
        session_bucket_rows_by_session,
        min_tracking_confidence=resolved.min_tracking_confidence,
    )

    high_info_coverage = (
        len(high_info_windows) / float(max(len(reliable_windows), 1))
        if reliable_windows
        else 0.0
    )
    blink_coverage = len(reliable_windows) / float(max(len(blink_windows), 1))
    quality_mean = mean_optional(
        [
            _row_quality(item)
            for item in reliable_windows
        ]
    ) or 0.35

    pathway: BlinkTransportPathway
    if not reliable_windows:
        attention_proxy = mean_optional(
            [
                clamp(float(item.attention_score or 50.0) / 100.0, 0.0, 1.0)
                for item in blink_windows
            ]
        ) or 0.5
        proxy_unit = clamp((0.7 * attention_proxy) + (0.3 * clamp(high_info_coverage + 0.2, 0.0, 1.0)), 0.0, 1.0)
        segment_scores = _build_timeline_scores(
            blink_windows=blink_windows,
            pathway=BlinkTransportPathway.sparse_fallback,
            quality_mean=quality_mean,
            suppression_component=0.0,
            rebound_samples=rebound_samples,
            target_samples=target_samples,
            high_info_windows=high_info_windows,
            fallback_without_blink=True,
            confidence_cap=resolved.sparse_confidence_cap,
        )
        return BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.sparse_fallback,
            global_score=round(proxy_unit * 100.0, 6),
            confidence=round(
                clamp(
                    0.14 + (0.18 * quality_mean) + (0.18 * clamp(high_info_coverage, 0.0, 1.0)),
                    0.0,
                    resolved.sparse_confidence_cap,
                ),
                6,
            ),
            segment_scores=segment_scores,
            suppression_score=0.0,
            rebound_score=round(rebound_component, 6),
            cta_avoidance_score=round(cta_avoidance_component, 6),
            cross_viewer_blink_synchrony=panel_synchrony,
            engagement_warnings=[
                BlinkTransportWarning(
                    warning_key="sparse_blink_signal",
                    severity=BlinkTransportWarningSeverity.high,
                    message=(
                        "Reliable blink timing was sparse; a low-confidence fallback estimate was used."
                    ),
                    start_ms=int(blink_windows[0].start_ms),
                    end_ms=int(blink_windows[-1].end_ms),
                )
            ],
            evidence_summary=(
                "Reliable blink instrumentation was sparse, so an approximate fallback path was used with reduced confidence."
            ),
            signals_used=[
                "attention_high_information_windows",
                "timeline_reveal_windows",
                "fallback_attention_proxy",
            ],
        )

    session_count = len(session_bucket_rows_by_session)
    if (
        panel_synchrony is not None
        and session_count >= resolved.direct_path_min_sessions
        and len(reliable_windows) >= resolved.direct_path_min_windows
    ):
        pathway = BlinkTransportPathway.direct_panel_blink
    elif len(reliable_windows) < resolved.sparse_min_blink_windows:
        pathway = BlinkTransportPathway.sparse_fallback
    else:
        pathway = BlinkTransportPathway.fallback_proxy

    score_components: List[tuple[float, float]] = [
        (suppression_component, 0.45 if pathway != BlinkTransportPathway.direct_panel_blink else 0.35),
        (rebound_component, 0.30 if pathway != BlinkTransportPathway.direct_panel_blink else 0.25),
        (cta_avoidance_component, 0.25 if pathway != BlinkTransportPathway.direct_panel_blink else 0.2),
    ]
    if pathway == BlinkTransportPathway.direct_panel_blink and panel_synchrony is not None:
        score_components.append((clamp((panel_synchrony + 1.0) / 2.0, 0.0, 1.0), 0.2))

    score_weight_total = sum(weight for _, weight in score_components)
    global_unit = (
        sum(value * weight for value, weight in score_components) / score_weight_total
        if score_weight_total > 0
        else 0.0
    )
    global_score = clamp(global_unit * 100.0, 0.0, 100.0)

    boundary_support = clamp(len(rebound_samples) / 4.0, 0.0, 1.0)
    target_support = clamp(len(target_samples) / 3.0, 0.0, 1.0)
    synchrony_support = clamp((panel_synchrony + 1.0) / 2.0, 0.0, 1.0) if panel_synchrony is not None else 0.0

    if pathway == BlinkTransportPathway.direct_panel_blink:
        confidence = clamp(
            0.26
            + (0.34 * quality_mean)
            + (0.17 * blink_coverage)
            + (0.11 * boundary_support)
            + (0.12 * synchrony_support),
            0.0,
            1.0,
        )
    elif pathway == BlinkTransportPathway.fallback_proxy:
        confidence = clamp(
            0.2
            + (0.34 * quality_mean)
            + (0.22 * blink_coverage)
            + (0.14 * boundary_support)
            + (0.1 * target_support),
            0.0,
            resolved.fallback_confidence_cap,
        )
    else:
        confidence = clamp(
            0.14
            + (0.24 * quality_mean)
            + (0.2 * blink_coverage)
            + (0.12 * high_info_coverage),
            0.0,
            resolved.sparse_confidence_cap,
        )

    timeline_scores = _build_timeline_scores(
        blink_windows=blink_windows,
        pathway=pathway,
        quality_mean=quality_mean,
        suppression_component=suppression_component,
        rebound_samples=rebound_samples,
        target_samples=target_samples,
        high_info_windows=high_info_windows,
        fallback_without_blink=False,
        confidence_cap=confidence,
    )

    warnings = _build_engagement_warnings(
        blink_windows=reliable_windows,
        rebound_samples=rebound_samples,
        target_samples=target_samples,
        variability_threshold=resolved.high_variability_std_threshold,
        mistimed_rebound_threshold=resolved.mistimed_rebound_delta_threshold,
        low_cta_avoidance_threshold=resolved.low_cta_avoidance_threshold,
    )

    pathway_summary = {
        BlinkTransportPathway.direct_panel_blink: "Direct panel blink timing overlap was available and used as the primary pathway.",
        BlinkTransportPathway.fallback_proxy: "Direct panel blink overlap was limited, so fallback event-gating estimation was used.",
        BlinkTransportPathway.sparse_fallback: "Blink support was sparse; score uses reduced-confidence fallback weighting.",
        BlinkTransportPathway.insufficient_data: "Insufficient blink support for transport diagnostics.",
        BlinkTransportPathway.disabled: "Blink transport instrumentation is disabled.",
    }[pathway]

    signals_used = [
        "blink_inhibition_timing",
        "blink_rebound_at_event_boundaries",
        "attention_high_information_windows",
    ]
    if cta_windows or reveal_windows:
        signals_used.append("cta_and_reveal_windows")
    if panel_synchrony is not None:
        signals_used.append("cross_viewer_blink_synchrony")
    if pathway == BlinkTransportPathway.sparse_fallback:
        signals_used.append("sparse_signal_downweighting")

    return BlinkTransportDiagnostics(
        pathway=pathway,
        global_score=round(global_score, 6),
        confidence=round(confidence, 6),
        segment_scores=timeline_scores,
        suppression_score=round(suppression_component, 6),
        rebound_score=round(rebound_component, 6),
        cta_avoidance_score=round(cta_avoidance_component, 6),
        cross_viewer_blink_synchrony=round(panel_synchrony, 6) if panel_synchrony is not None else None,
        engagement_warnings=warnings,
        evidence_summary=(
            f"{pathway_summary} "
            "Blink transport is interpreted as attentional/event-segmentation timing behavior, not biochemical measurement."
        ),
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
    config: BlinkTransportConfig,
    overrides: Mapping[str, object],
) -> BlinkTransportConfig:
    allowed_fields = {field.name for field in fields(config)}
    replacement: Dict[str, object] = {}
    for key, value in overrides.items():
        if key not in allowed_fields:
            continue
        replacement[key] = value
    if not replacement:
        return config
    try:
        return replace(config, **replacement)
    except TypeError:
        return config


def _parse_optional_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return None


def _to_blink_windows(
    rows: Sequence[Dict[str, object]],
    *,
    window_ms: int,
) -> List[_BlinkWindow]:
    output: List[_BlinkWindow] = []
    for row in rows:
        start_ms = int(row.get("bucket_start") or 0)
        end_ms = max(start_ms + window_ms, start_ms + 1)
        blink_rate = to_float_optional(row.get("blink_rate"))
        baseline_rate = to_float_optional(row.get("blink_baseline_rate"))
        blink_inhibition = to_float_optional(row.get("blink_inhibition"))
        if blink_inhibition is None and blink_rate is not None and baseline_rate is not None:
            blink_inhibition = clamp((baseline_rate - blink_rate) / max(baseline_rate, 1e-3), -1.0, 1.0)
        output.append(
            _BlinkWindow(
                start_ms=start_ms,
                end_ms=end_ms,
                attention_score=to_float_optional(row.get("attention_score")),
                attention_velocity=to_float_optional(row.get("attention_velocity")),
                label_signal=to_float_optional(row.get("label_signal")),
                blink_rate=blink_rate,
                blink_baseline_rate=baseline_rate,
                blink_inhibition=blink_inhibition,
                tracking_confidence=to_float_optional(row.get("tracking_confidence")),
                quality_score=to_float_optional(row.get("quality_score")),
                cta_id=str(row.get("cta_id")) if row.get("cta_id") is not None else None,
                scene_id=str(row.get("scene_id")) if row.get("scene_id") is not None else None,
                cut_id=str(row.get("cut_id")) if row.get("cut_id") is not None else None,
            )
        )
    return output


def _resolve_segment_windows(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    *,
    segment_type: str,
) -> List[tuple[int, int]]:
    windows: List[tuple[int, int]] = []
    for item in timeline_segments:
        item_type = _segment_attr(item, "segment_type")
        if item_type != segment_type:
            continue
        start_ms = _segment_attr(item, "start_ms")
        end_ms = _segment_attr(item, "end_ms")
        if start_ms is None or end_ms is None:
            continue
        start_value = max(int(start_ms), 0)
        end_value = max(int(end_ms), start_value + 1)
        windows.append((start_value, end_value))
    return windows


def _resolve_cta_windows(
    cta_markers: Sequence[ReadoutCtaMarker],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
) -> List[tuple[int, int]]:
    windows: List[tuple[int, int]] = []
    for marker in cta_markers:
        start_ms = int(marker.start_ms if marker.start_ms is not None else marker.video_time_ms)
        end_source = marker.end_ms if marker.end_ms is not None else (start_ms + 1000)
        end_ms = max(int(end_source), start_ms + 1)
        windows.append((start_ms, end_ms))
    windows.extend(_resolve_segment_windows(timeline_segments, segment_type="cta_window"))
    return sorted(set(windows), key=lambda item: (item[0], item[1]))


def _resolve_boundary_times(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    blink_windows: Sequence[_BlinkWindow],
) -> List[int]:
    boundaries: set[int] = set()
    for item in timeline_segments:
        segment_type = _segment_attr(item, "segment_type")
        if segment_type not in {"shot_boundary", "scene_block"}:
            continue
        start_ms = _segment_attr(item, "start_ms")
        if start_ms is None:
            continue
        timestamp = max(int(start_ms), 0)
        if timestamp > 0:
            boundaries.add(timestamp)

    previous_scene: Optional[str] = None
    previous_cut: Optional[str] = None
    for item in blink_windows:
        if (
            previous_scene is not None
            and item.scene_id is not None
            and item.scene_id != previous_scene
        ):
            boundaries.add(int(item.start_ms))
        if (
            previous_cut is not None
            and item.cut_id is not None
            and item.cut_id != previous_cut
        ):
            boundaries.add(int(item.start_ms))
        previous_scene = item.scene_id
        previous_cut = item.cut_id

    return sorted(boundaries)


def _is_blink_reliable(item: _BlinkWindow, config: BlinkTransportConfig) -> bool:
    if item.blink_inhibition is None:
        return False
    quality_values = [
        value for value in [item.tracking_confidence, item.quality_score] if value is not None
    ]
    if not quality_values:
        return True
    return max(quality_values) >= min(config.min_tracking_confidence, config.min_quality_score)


def _is_high_information_window(
    item: _BlinkWindow,
    reveal_windows: Sequence[tuple[int, int]],
    config: BlinkTransportConfig,
) -> bool:
    attention_ok = (
        item.attention_score is not None
        and float(item.attention_score) >= float(config.high_info_attention_threshold)
    )
    velocity_ok = (
        item.attention_velocity is not None
        and abs(float(item.attention_velocity)) >= float(config.high_info_velocity_threshold)
    )
    label_ok = (
        item.label_signal is not None
        and abs(float(item.label_signal)) >= float(config.high_info_label_signal_threshold)
    )
    reveal_overlap = any(_overlaps(item.start_ms, item.end_ms, start, end) for start, end in reveal_windows)
    return bool(attention_ok or velocity_ok or label_ok or reveal_overlap)


def _compute_boundary_rebounds(
    blink_windows: Sequence[_BlinkWindow],
    *,
    boundary_times: Sequence[int],
    config: BlinkTransportConfig,
) -> List[_BoundaryReboundSample]:
    samples: List[_BoundaryReboundSample] = []
    for boundary_ms in boundary_times:
        pre_windows = [
            item
            for item in blink_windows
            if item.start_ms >= (boundary_ms - config.boundary_pre_window_ms)
            and item.start_ms < boundary_ms
            and item.blink_inhibition is not None
        ]
        post_windows = [
            item
            for item in blink_windows
            if item.start_ms >= boundary_ms
            and item.start_ms < (boundary_ms + config.boundary_post_window_ms)
            and item.blink_inhibition is not None
        ]
        if not pre_windows or not post_windows:
            continue
        pre_inhibition = mean_optional([float(item.blink_inhibition or 0.0) for item in pre_windows]) or 0.0
        post_inhibition = mean_optional([float(item.blink_inhibition or 0.0) for item in post_windows]) or 0.0
        rebound_delta = pre_inhibition - post_inhibition
        rebound_unit = clamp(rebound_delta / 0.6, 0.0, 1.0)
        samples.append(
            _BoundaryReboundSample(
                boundary_ms=int(boundary_ms),
                start_ms=max(int(boundary_ms - config.boundary_pre_window_ms), 0),
                end_ms=int(boundary_ms + config.boundary_post_window_ms),
                rebound_delta=round(rebound_delta, 6),
                rebound_unit=round(rebound_unit, 6),
                reason="Blink rebound followed a safe narrative boundary window.",
            )
        )
    return samples


def _compute_target_window_samples(
    blink_windows: Sequence[_BlinkWindow],
    *,
    target_windows: Sequence[tuple[int, int]],
    probe_window_ms: int,
) -> List[_TargetWindowSample]:
    samples: List[_TargetWindowSample] = []
    for start_ms, end_ms in target_windows:
        inside = [
            item
            for item in blink_windows
            if _overlaps(item.start_ms, item.end_ms, start_ms, end_ms)
            and item.blink_inhibition is not None
        ]
        if not inside:
            continue
        outside = [
            item
            for item in blink_windows
            if (
                _overlaps(item.start_ms, item.end_ms, max(start_ms - probe_window_ms, 0), start_ms)
                or _overlaps(item.start_ms, item.end_ms, end_ms, end_ms + probe_window_ms)
            )
            and item.blink_inhibition is not None
        ]
        inside_value = mean_optional([float(item.blink_inhibition or 0.0) for item in inside]) or 0.0
        outside_value = mean_optional([float(item.blink_inhibition or 0.0) for item in outside]) or 0.0
        delta = inside_value - outside_value
        samples.append(
            _TargetWindowSample(
                start_ms=int(start_ms),
                end_ms=int(end_ms),
                delta=round(delta, 6),
                unit=round(clamp(0.5 + delta, 0.0, 1.0), 6),
                reason="Blink avoidance was measured around CTA/reveal windows.",
            )
        )
    return samples


def _build_timeline_scores(
    *,
    blink_windows: Sequence[_BlinkWindow],
    pathway: BlinkTransportPathway,
    quality_mean: float,
    suppression_component: float,
    rebound_samples: Sequence[_BoundaryReboundSample],
    target_samples: Sequence[_TargetWindowSample],
    high_info_windows: Sequence[_BlinkWindow],
    fallback_without_blink: bool,
    confidence_cap: float,
) -> List[BlinkTransportTimelineScore]:
    high_info_ranges = {(item.start_ms, item.end_ms) for item in high_info_windows}
    scores: List[BlinkTransportTimelineScore] = []
    for item in blink_windows:
        suppression_local = (
            clamp(float(item.blink_inhibition), 0.0, 1.0)
            if item.blink_inhibition is not None
            else None
        )
        rebound_local = _nearest_rebound_unit(item.start_ms, rebound_samples, tolerance_ms=1500)
        cta_local = _nearest_target_unit(item.start_ms, target_samples, tolerance_ms=1200)

        if fallback_without_blink:
            attention_proxy = clamp(float(item.attention_score or 50.0) / 100.0, 0.0, 1.0)
            local_unit = clamp(
                (0.6 * attention_proxy)
                + (0.2 * (rebound_local if rebound_local is not None else 0.5))
                + (0.2 * (cta_local if cta_local is not None else 0.5)),
                0.0,
                1.0,
            )
            local_confidence = clamp(0.12 + (0.18 * quality_mean), 0.0, confidence_cap)
            reason = "Fallback proxy estimate from timeline pacing; direct blink support was sparse."
        else:
            local_unit = clamp(
                (0.55 * (suppression_local if suppression_local is not None else suppression_component))
                + (0.25 * (rebound_local if rebound_local is not None else 0.5))
                + (0.2 * (cta_local if cta_local is not None else 0.5)),
                0.0,
                1.0,
            )
            local_confidence = clamp(
                0.2
                + (0.35 * _row_quality(item))
                + (0.15 if suppression_local is not None else 0.0),
                0.0,
                confidence_cap,
            )
            if (item.start_ms, item.end_ms) in high_info_ranges and (suppression_local or 0.0) >= 0.35:
                reason = "Blink suppression held during a high-information window."
            elif rebound_local is not None and rebound_local >= 0.5:
                reason = "Blink rebound aligned with an event boundary."
            elif cta_local is not None and cta_local >= 0.5:
                reason = "Blink avoidance held around CTA/reveal timing."
            else:
                reason = "Blink timing support was mixed in this window."

        scores.append(
            BlinkTransportTimelineScore(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                score=round(local_unit * 100.0, 6),
                confidence=round(local_confidence, 6),
                pathway=pathway,
                reason=reason,
                blink_suppression=round(float(suppression_local), 6) if suppression_local is not None else None,
                rebound_signal=round(float(rebound_local), 6) if rebound_local is not None else None,
                cta_avoidance_signal=round(float(cta_local), 6) if cta_local is not None else None,
            )
        )

    return scores


def _build_engagement_warnings(
    *,
    blink_windows: Sequence[_BlinkWindow],
    rebound_samples: Sequence[_BoundaryReboundSample],
    target_samples: Sequence[_TargetWindowSample],
    variability_threshold: float,
    mistimed_rebound_threshold: float,
    low_cta_avoidance_threshold: float,
) -> List[BlinkTransportWarning]:
    warnings: List[BlinkTransportWarning] = []
    suppression_values = [
        clamp(float(item.blink_inhibition), 0.0, 1.0)
        for item in blink_windows
        if item.blink_inhibition is not None
    ]
    suppression_std = _stddev(suppression_values)
    if suppression_std is not None and suppression_std > variability_threshold:
        warnings.append(
            BlinkTransportWarning(
                warning_key="high_blink_variability",
                severity=(
                    BlinkTransportWarningSeverity.high
                    if suppression_std > (variability_threshold * 1.5)
                    else BlinkTransportWarningSeverity.medium
                ),
                message=(
                    "Blink suppression varied substantially across windows; transport estimates may be less stable."
                ),
                start_ms=int(blink_windows[0].start_ms),
                end_ms=int(blink_windows[-1].end_ms),
                metric_value=round(float(suppression_std), 6),
            )
        )

    worst_rebound = min(
        rebound_samples,
        default=None,
        key=lambda item: float(item.rebound_delta),
    )
    if worst_rebound is not None and worst_rebound.rebound_delta < mistimed_rebound_threshold:
        warnings.append(
            BlinkTransportWarning(
                warning_key="mistimed_blink_rebound",
                severity=BlinkTransportWarningSeverity.high,
                message=(
                    "Blink rebound appeared delayed or mistimed near a narrative boundary window."
                ),
                start_ms=int(worst_rebound.start_ms),
                end_ms=int(worst_rebound.end_ms),
                metric_value=round(float(worst_rebound.rebound_delta), 6),
            )
        )

    if target_samples:
        target_mean = mean_optional([item.unit for item in target_samples]) or 0.0
        if target_mean < low_cta_avoidance_threshold:
            first_target = min(target_samples, key=lambda item: item.start_ms)
            last_target = max(target_samples, key=lambda item: item.end_ms)
            warnings.append(
                BlinkTransportWarning(
                    warning_key="weak_cta_blink_avoidance",
                    severity=BlinkTransportWarningSeverity.medium,
                    message=(
                        "Blink avoidance around CTA/reveal windows was weaker than expected."
                    ),
                    start_ms=int(first_target.start_ms),
                    end_ms=int(last_target.end_ms),
                    metric_value=round(float(target_mean), 6),
                )
            )

    return warnings


def _compute_panel_blink_synchrony(
    session_bucket_rows_by_session: Mapping[object, Mapping[int, Dict[str, object]]],
    *,
    min_tracking_confidence: float,
) -> Optional[float]:
    sessions = list(session_bucket_rows_by_session.items())
    if len(sessions) < 2:
        return None

    pairwise: List[float] = []
    for left_index in range(len(sessions)):
        left_rows = sessions[left_index][1]
        for right_index in range(left_index + 1, len(sessions)):
            right_rows = sessions[right_index][1]
            common_times = sorted(set(left_rows.keys()) & set(right_rows.keys()))
            left_values: List[float] = []
            right_values: List[float] = []
            for bucket_time in common_times:
                left_item = left_rows[bucket_time]
                right_item = right_rows[bucket_time]
                left_inhibition = to_float_optional(left_item.get("blink_inhibition"))
                right_inhibition = to_float_optional(right_item.get("blink_inhibition"))
                if left_inhibition is None or right_inhibition is None:
                    continue
                left_tracking = to_float_optional(left_item.get("tracking_confidence"))
                right_tracking = to_float_optional(right_item.get("tracking_confidence"))
                if (
                    left_tracking is not None
                    and left_tracking < min_tracking_confidence
                ) or (
                    right_tracking is not None
                    and right_tracking < min_tracking_confidence
                ):
                    continue
                left_values.append(float(left_inhibition))
                right_values.append(float(right_inhibition))
            if len(left_values) < 3:
                continue
            correlation = _pearson(left_values, right_values)
            if correlation is not None:
                pairwise.append(correlation)
    return mean_optional(pairwise)


def _row_quality(item: _BlinkWindow) -> float:
    values = [
        value for value in [item.tracking_confidence, item.quality_score] if value is not None
    ]
    if not values:
        return 0.5
    return clamp(sum(values) / float(len(values)), 0.0, 1.0)


def _nearest_rebound_unit(
    timestamp_ms: int,
    samples: Sequence[_BoundaryReboundSample],
    *,
    tolerance_ms: int,
) -> Optional[float]:
    nearest = min(
        samples,
        default=None,
        key=lambda item: abs(int(item.boundary_ms) - int(timestamp_ms)),
    )
    if nearest is None:
        return None
    if abs(int(nearest.boundary_ms) - int(timestamp_ms)) > tolerance_ms:
        return None
    return float(nearest.rebound_unit)


def _nearest_target_unit(
    timestamp_ms: int,
    samples: Sequence[_TargetWindowSample],
    *,
    tolerance_ms: int,
) -> Optional[float]:
    nearest = min(
        samples,
        default=None,
        key=lambda item: abs(int(item.start_ms) - int(timestamp_ms)),
    )
    if nearest is None:
        return None
    if abs(int(nearest.start_ms) - int(timestamp_ms)) > tolerance_ms:
        return None
    return float(nearest.unit)


def _segment_attr(item: TimelineSegmentRead | Dict[str, Any], key: str) -> Optional[object]:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def _stddev(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    avg = mean_optional(values)
    if avg is None:
        return None
    variance = sum((value - avg) ** 2 for value in values) / float(len(values))
    return math.sqrt(max(variance, 0.0))


def _pearson(left: Sequence[float], right: Sequence[float]) -> Optional[float]:
    if len(left) != len(right) or len(left) < 2:
        return None
    ml = mean_optional(left)
    mr = mean_optional(right)
    if ml is None or mr is None:
        return None
    numerator = sum((x - ml) * (y - mr) for x, y in zip(left, right))
    denominator_left = math.sqrt(sum((x - ml) ** 2 for x in left))
    denominator_right = math.sqrt(sum((y - mr) ** 2 for y in right))
    denominator = denominator_left * denominator_right
    if denominator <= 0:
        return None
    return clamp(numerator / denominator, -1.0, 1.0)

