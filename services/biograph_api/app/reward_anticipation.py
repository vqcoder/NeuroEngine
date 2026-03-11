"""Reward anticipation diagnostics from timeline pacing and pre-payoff pull signals."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import to_float_optional, row_series_mean

from .schemas import (
    FeatureTrackRead,
    ReadoutCtaMarker,
    RewardAnticipationDiagnostics,
    RewardAnticipationPathway,
    RewardAnticipationTimelineWindow,
    RewardAnticipationTimelineWindowType,
    RewardAnticipationWarning,
    RewardAnticipationWarningSeverity,
    TimelineSegmentRead,
)


@dataclass(frozen=True)
class RewardAnticipationConfig:
    ramp_lookback_ms: int = 3000
    payoff_window_ms: int = 1800
    late_resolution_window_ms: int = 5000
    on_time_resolution_ms: int = 2200
    min_tracking_confidence: float = 0.3
    min_quality_score: float = 0.25
    min_release_delta: float = 4.0
    max_release_delta_for_scale: float = 18.0
    min_ramp_slope_per_sec: float = 1.8
    max_ramp_slope_per_sec: float = 9.0
    high_attention_floor: float = 55.0
    attention_std_penalty_scale: float = 22.0
    tension_cut_cadence_scale: float = 2.2
    tension_velocity_scale: float = 9.0
    unresolved_tension_threshold: float = 0.58
    unresolved_release_threshold: float = 0.38
    max_payoff_candidates: int = 5
    fallback_confidence_cap: float = 0.72


@dataclass(frozen=True)
class _PayoffCandidate:
    payoff_time_ms: int
    source: str


def resolve_reward_anticipation_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> RewardAnticipationConfig:
    """Build reward anticipation settings from env + optional video metadata."""

    config = RewardAnticipationConfig()
    settings_overrides = _parse_override_payload(get_settings().reward_anticipation_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("reward_anticipation_config", "rewardAnticipationConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def compute_reward_anticipation_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    cta_markers: Sequence[ReadoutCtaMarker],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]] = (),
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]] = (),
    window_ms: int,
    config: Optional[RewardAnticipationConfig] = None,
) -> RewardAnticipationDiagnostics:
    """Estimate reward anticipation pull from pre-payoff ramp and release dynamics."""

    resolved = config or RewardAnticipationConfig()
    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    if not rows:
        return RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.insufficient_data,
            evidence_summary="No timeline buckets were available for reward anticipation diagnostics.",
            signals_used=[],
        )

    window_size_ms = max(int(window_ms), 1)
    track_index = _index_tracks(timeline_feature_tracks)
    audio_stats = _track_min_max(track_index.get("audio_intensity_rms", []))

    candidates = _resolve_payoff_candidates(
        rows=rows,
        cta_markers=cta_markers,
        timeline_segments=timeline_segments,
        max_candidates=max(int(resolved.max_payoff_candidates), 1),
    )
    if not candidates:
        return RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.insufficient_data,
            evidence_summary="No payoff candidate windows were available for reward anticipation diagnostics.",
            signals_used=[],
        )

    anticipation_ramps: List[RewardAnticipationTimelineWindow] = []
    payoff_windows: List[RewardAnticipationTimelineWindow] = []
    warnings: List[RewardAnticipationWarning] = []
    anticipation_units: List[float] = []
    payoff_units: List[float] = []
    balance_units: List[float] = []
    local_confidences: List[float] = []

    duration_ms = int(rows[-1]["bucket_start"]) + window_size_ms

    for candidate in candidates:
        payoff_time_ms = int(candidate.payoff_time_ms)
        pre_start_ms = max(payoff_time_ms - int(resolved.ramp_lookback_ms), 0)
        payoff_end_ms = min(payoff_time_ms + int(resolved.payoff_window_ms), duration_ms)
        post_resolution_end_ms = min(payoff_time_ms + int(resolved.late_resolution_window_ms), duration_ms)

        pre_rows = _rows_in_window(rows, pre_start_ms, payoff_time_ms)
        payoff_rows = _rows_in_window(rows, payoff_time_ms, payoff_end_ms)
        resolution_rows = _rows_in_window(rows, payoff_time_ms, post_resolution_end_ms)
        if not pre_rows or not payoff_rows:
            continue

        reward_pre = row_series_mean(pre_rows, ("reward_proxy", "attention_score"))
        reward_post = row_series_mean(payoff_rows, ("reward_proxy", "attention_score"))
        if reward_pre is None or reward_post is None:
            continue
        reward_delta = reward_post - reward_pre
        release_unit = clamp(
            reward_delta / max(float(resolved.max_release_delta_for_scale), 1e-6),
            0.0,
            1.0,
        )

        reward_slope = _series_slope_per_second(pre_rows, ("reward_proxy", "attention_score"))
        ramp_slope_unit = clamp(
            (reward_slope - float(resolved.min_ramp_slope_per_sec))
            / max(
                float(resolved.max_ramp_slope_per_sec - resolved.min_ramp_slope_per_sec),
                1e-6,
            ),
            0.0,
            1.0,
        )
        blink_suppression = _series_mean_clamped(pre_rows, "blink_inhibition", lower=0.0, upper=1.0)
        arousal_slope = _series_slope_per_second(pre_rows, ("arousal_proxy",))
        arousal_unit = clamp(0.5 + (arousal_slope / 16.0), 0.0, 1.0)
        attention_concentration = _attention_concentration(pre_rows, resolved)
        tension_level = _tension_level(
            pre_rows=pre_rows,
            track_index=track_index,
            audio_stats=audio_stats,
            start_ms=pre_start_ms,
            end_ms=payoff_time_ms,
            config=resolved,
        )

        resolution_time_ms = _resolve_release_time(
            rows=resolution_rows,
            baseline_reward=reward_pre,
            min_release_delta=float(resolved.min_release_delta),
        )
        timing_unit = 0.5
        if resolution_time_ms is not None:
            resolution_delay_ms = max(int(resolution_time_ms) - payoff_time_ms, 0)
            if resolution_delay_ms <= int(resolved.on_time_resolution_ms):
                timing_unit = 1.0
            else:
                timing_unit = clamp(
                    1.0
                    - (
                        (resolution_delay_ms - int(resolved.on_time_resolution_ms))
                        / max(float(resolved.late_resolution_window_ms), 1.0)
                    ),
                    0.25,
                    0.7,
                )
                warnings.append(
                    RewardAnticipationWarning(
                        warning_key="late_resolution",
                        severity=RewardAnticipationWarningSeverity.medium,
                        message=(
                            "Tension appeared to resolve later than the primary payoff window."
                        ),
                        start_ms=int(payoff_time_ms),
                        end_ms=int(min(resolution_time_ms + window_size_ms, duration_ms)),
                        metric_value=round(float(resolution_delay_ms), 6),
                    )
                )
        elif tension_level >= float(resolved.unresolved_tension_threshold):
            timing_unit = 0.2
            warnings.append(
                RewardAnticipationWarning(
                    warning_key="tension_without_resolution",
                    severity=RewardAnticipationWarningSeverity.high,
                    message=(
                        "The video built tension but did not deliver a clear resolution in the observed window."
                    ),
                    start_ms=int(pre_start_ms),
                    end_ms=int(post_resolution_end_ms),
                    metric_value=round(float(tension_level), 6),
                )
            )

        if (
            tension_level >= float(resolved.unresolved_tension_threshold)
            and release_unit <= float(resolved.unresolved_release_threshold)
        ):
            warnings.append(
                RewardAnticipationWarning(
                    warning_key="weak_payoff_release",
                    severity=RewardAnticipationWarningSeverity.medium,
                    message="Payoff release was weak relative to pre-payoff tension cues.",
                    start_ms=int(payoff_time_ms),
                    end_ms=int(payoff_end_ms),
                    metric_value=round(float(reward_delta), 6),
                )
            )

        anticipation_unit = clamp(
            (0.32 * ramp_slope_unit)
            + (0.24 * blink_suppression)
            + (0.20 * arousal_unit)
            + (0.24 * attention_concentration),
            0.0,
            1.0,
        )
        payoff_unit = clamp(
            (0.45 * release_unit)
            + (0.20 * tension_level)
            + (0.20 * attention_concentration)
            + (0.15 * timing_unit),
            0.0,
            1.0,
        )
        balance_unit = clamp(1.0 - abs(tension_level - release_unit), 0.0, 1.0)

        quality_mean = mean_optional(
            [
                value
                for value in [
                    row_series_mean(pre_rows + payoff_rows, ("tracking_confidence",)),
                    row_series_mean(pre_rows + payoff_rows, ("quality_score",)),
                ]
                if value is not None
            ]
        ) or 0.45
        signal_coverage = _signal_coverage(
            reward_slope=reward_slope,
            blink_suppression=blink_suppression,
            arousal_slope=arousal_slope,
            has_cut_cadence=_track_has_values(track_index, "cut_cadence", pre_start_ms, payoff_time_ms),
            has_audio=_track_has_values(track_index, "audio_intensity_rms", pre_start_ms, payoff_time_ms),
        )
        local_confidence = clamp(
            0.26 + (0.42 * quality_mean) + (0.32 * signal_coverage),
            0.0,
            1.0,
        )

        anticipation_ramps.append(
            RewardAnticipationTimelineWindow(
                start_ms=int(pre_start_ms),
                end_ms=int(max(payoff_time_ms, pre_start_ms + 1)),
                score=round(anticipation_unit * 100.0, 6),
                confidence=round(local_confidence, 6),
                window_type=RewardAnticipationTimelineWindowType.anticipation_ramp,
                reason=(
                    "Pre-payoff ramp combined anticipation cues from pacing, blink suppression, and arousal trend."
                ),
                ramp_slope=round(float(reward_slope), 6),
                tension_level=round(float(tension_level), 6),
                release_level=round(float(release_unit), 6),
            )
        )
        payoff_windows.append(
            RewardAnticipationTimelineWindow(
                start_ms=int(payoff_time_ms),
                end_ms=int(max(payoff_end_ms, payoff_time_ms + 1)),
                score=round(payoff_unit * 100.0, 6),
                confidence=round(local_confidence, 6),
                window_type=RewardAnticipationTimelineWindowType.payoff_window,
                reason=(
                    "Payoff window score reflects release strength relative to setup tension and timing."
                ),
                reward_delta=round(float(reward_delta), 6),
                tension_level=round(float(tension_level), 6),
                release_level=round(float(release_unit), 6),
            )
        )
        anticipation_units.append(anticipation_unit)
        payoff_units.append(payoff_unit)
        balance_units.append(balance_unit)
        local_confidences.append(local_confidence)

    if not anticipation_ramps or not payoff_windows:
        return RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.insufficient_data,
            evidence_summary=(
                "Anticipation ramps or payoff windows were too sparse for a stable reward anticipation estimate."
            ),
            signals_used=[],
        )

    has_timeline_signals = bool(track_index.get("cut_cadence")) or bool(track_index.get("audio_intensity_rms"))
    pathway = (
        RewardAnticipationPathway.timeline_dynamics
        if has_timeline_signals
        else RewardAnticipationPathway.fallback_proxy
    )

    anticipation_strength = mean_optional(anticipation_units) or 0.0
    payoff_release_strength = mean_optional(payoff_units) or 0.0
    tension_release_balance = mean_optional(balance_units) or 0.0
    global_unit = clamp(
        (0.44 * anticipation_strength)
        + (0.44 * payoff_release_strength)
        + (0.12 * tension_release_balance),
        0.0,
        1.0,
    )
    confidence = mean_optional(local_confidences) or 0.5
    if pathway == RewardAnticipationPathway.fallback_proxy:
        confidence = min(confidence, float(resolved.fallback_confidence_cap))

    warning_count = len(warnings)
    confidence = clamp(
        confidence - min(0.04 * warning_count, 0.18),
        0.0,
        1.0,
    )
    unique_warnings = _unique_warnings(warnings)
    warning_summary = (
        "No major tension-resolution timing warnings."
        if not unique_warnings
        else f"{len(unique_warnings)} timing warning(s) detected."
    )
    signals_used = [
        "reward_proxy_trend",
        "pre_payoff_attention_concentration",
        "blink_suppression_pre_payoff",
        "arousal_slope_proxy",
        "uncertainty_to_resolution_timing",
    ]
    if has_timeline_signals:
        signals_used.extend(
            [
                "cut_cadence",
                "audio_intensity_rms",
                "pacing_tension_proxy",
            ]
        )

    return RewardAnticipationDiagnostics(
        pathway=pathway,
        global_score=round(global_unit * 100.0, 6),
        confidence=round(confidence, 6),
        anticipation_ramps=anticipation_ramps,
        payoff_windows=payoff_windows,
        warnings=unique_warnings,
        anticipation_strength=round(float(anticipation_strength), 6),
        payoff_release_strength=round(float(payoff_release_strength), 6),
        tension_release_balance=round(float(tension_release_balance), 6),
        evidence_summary=(
            "Reward anticipation reflects anticipatory pull into payoff moments from timing proxies; "
            f"{warning_summary} This is a behavioral proxy and not direct biochemical measurement."
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
    config: RewardAnticipationConfig,
    overrides: Mapping[str, object],
) -> RewardAnticipationConfig:
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


def _resolve_payoff_candidates(
    *,
    rows: Sequence[Dict[str, object]],
    cta_markers: Sequence[ReadoutCtaMarker],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    max_candidates: int,
) -> List[_PayoffCandidate]:
    candidates: Dict[int, str] = {}
    for marker in cta_markers:
        timestamp = int(marker.start_ms if marker.start_ms is not None else marker.video_time_ms)
        candidates[timestamp] = "cta_marker"

    for segment in timeline_segments:
        segment_type = _segment_attr(segment, "segment_type")
        start_ms = _segment_attr(segment, "start_ms")
        end_ms = _segment_attr(segment, "end_ms")
        if segment_type == "cta_window" and start_ms is not None:
            candidates[int(start_ms)] = "cta_window"
        if segment_type == "text_overlay" and end_ms is not None:
            candidates[int(end_ms)] = "text_overlay_reveal"

    for timestamp in _reward_peak_candidates(rows):
        candidates.setdefault(int(timestamp), "reward_peak")

    ranked: List[_PayoffCandidate] = [
        _PayoffCandidate(payoff_time_ms=int(timestamp), source=source)
        for timestamp, source in sorted(candidates.items(), key=lambda item: item[0])
    ]
    if len(ranked) <= max_candidates:
        return ranked

    # Keep CTA/reveal candidates first, then strongest reward-peak candidates.
    preferred = [item for item in ranked if item.source != "reward_peak"]
    reward_peaks = [item for item in ranked if item.source == "reward_peak"]
    reward_peaks.sort(
        key=lambda item: _reward_value_at_time(rows, int(item.payoff_time_ms)),
        reverse=True,
    )
    return [*preferred, *reward_peaks][:max_candidates]


def _reward_peak_candidates(rows: Sequence[Dict[str, object]]) -> List[int]:
    reward_points = [
        (int(row["bucket_start"]), to_float_optional(row.get("reward_proxy")))
        for row in rows
        if row.get("bucket_start") is not None
    ]
    reward_points = [(t, value) for t, value in reward_points if value is not None]
    if len(reward_points) < 3:
        return [time_ms for time_ms, _ in reward_points]

    values = [value for _, value in reward_points]
    mean_value = mean_optional(values) or 0.0
    std_value = _stddev(values) or 0.0
    threshold = mean_value + (0.15 * std_value)

    peaks: List[int] = []
    for index in range(1, len(reward_points) - 1):
        current_time, current_value = reward_points[index]
        previous_value = reward_points[index - 1][1]
        next_value = reward_points[index + 1][1]
        if current_value >= previous_value and current_value >= next_value and current_value >= threshold:
            peaks.append(current_time)

    if peaks:
        return peaks
    top_ranked = sorted(reward_points, key=lambda item: item[1], reverse=True)
    return [int(item[0]) for item in top_ranked[:3]]


def _reward_value_at_time(rows: Sequence[Dict[str, object]], timestamp_ms: int) -> float:
    nearest = min(
        rows,
        key=lambda row: abs(int(row["bucket_start"]) - int(timestamp_ms)),
    )
    return to_float_optional(nearest.get("reward_proxy")) or 0.0


def _rows_in_window(
    rows: Sequence[Dict[str, object]],
    start_ms: int,
    end_ms: int,
) -> List[Dict[str, object]]:
    return [
        row
        for row in rows
        if int(row["bucket_start"]) >= int(start_ms) and int(row["bucket_start"]) < int(end_ms)
    ]



def _series_slope_per_second(rows: Sequence[Dict[str, object]], keys: Sequence[str]) -> float:
    points: List[tuple[int, float]] = []
    for row in rows:
        for key in keys:
            value = to_float_optional(row.get(key))
            if value is not None:
                points.append((int(row["bucket_start"]), value))
                break
    if len(points) < 2:
        return 0.0
    first_time, first_value = points[0]
    last_time, last_value = points[-1]
    elapsed_seconds = max((last_time - first_time) / 1000.0, 0.001)
    return (last_value - first_value) / elapsed_seconds


def _series_mean_clamped(
    rows: Sequence[Dict[str, object]],
    key: str,
    *,
    lower: float,
    upper: float,
) -> float:
    values = [
        clamp(value, lower, upper)
        for value in (to_float_optional(row.get(key)) for row in rows)
        if value is not None
    ]
    return mean_optional(values) or 0.0


def _attention_concentration(
    rows: Sequence[Dict[str, object]],
    config: RewardAnticipationConfig,
) -> float:
    values = [
        value
        for value in (to_float_optional(row.get("attention_score")) for row in rows)
        if value is not None
    ]
    if not values:
        return 0.5
    mean_value = mean_optional(values) or 0.0
    std_value = _stddev(values) or 0.0
    mean_unit = clamp(
        (mean_value - float(config.high_attention_floor))
        / max(100.0 - float(config.high_attention_floor), 1e-6),
        0.0,
        1.0,
    )
    variability_penalty = clamp(std_value / max(float(config.attention_std_penalty_scale), 1e-6), 0.0, 0.85)
    return clamp(mean_unit * (1.0 - variability_penalty), 0.0, 1.0)


def _tension_level(
    *,
    pre_rows: Sequence[Dict[str, object]],
    track_index: Mapping[str, Sequence[Dict[str, Any]]],
    audio_stats: Optional[tuple[float, float]],
    start_ms: int,
    end_ms: int,
    config: RewardAnticipationConfig,
) -> float:
    components: List[float] = []
    cut_cadence = _track_mean(track_index, "cut_cadence", start_ms, end_ms)
    if cut_cadence is not None:
        components.append(
            clamp(cut_cadence / max(float(config.tension_cut_cadence_scale), 1e-6), 0.0, 1.0)
        )

    audio_mean = _track_mean(track_index, "audio_intensity_rms", start_ms, end_ms)
    if audio_mean is not None and audio_stats is not None:
        audio_min, audio_max = audio_stats
        if audio_max > audio_min:
            components.append(clamp((audio_mean - audio_min) / (audio_max - audio_min), 0.0, 1.0))

    velocity_values = [
        abs(value)
        for value in (to_float_optional(row.get("attention_velocity")) for row in pre_rows)
        if value is not None
    ]
    if velocity_values:
        components.append(
            clamp(
                (mean_optional(velocity_values) or 0.0)
                / max(float(config.tension_velocity_scale), 1e-6),
                0.0,
                1.0,
            )
        )

    if not components:
        return 0.45
    return mean_optional(components) or 0.45


def _resolve_release_time(
    *,
    rows: Sequence[Dict[str, object]],
    baseline_reward: float,
    min_release_delta: float,
) -> Optional[int]:
    threshold = baseline_reward + float(min_release_delta)
    for row in rows:
        reward_value = to_float_optional(row.get("reward_proxy"))
        if reward_value is None:
            reward_value = to_float_optional(row.get("attention_score"))
        if reward_value is None:
            continue
        if reward_value >= threshold:
            return int(row["bucket_start"])
    return None


def _signal_coverage(
    *,
    reward_slope: float,
    blink_suppression: float,
    arousal_slope: float,
    has_cut_cadence: bool,
    has_audio: bool,
) -> float:
    signals = 0.0
    signals += 1.0 if abs(float(reward_slope)) > 1e-6 else 0.0
    signals += 1.0 if blink_suppression > 0.0 else 0.0
    signals += 1.0 if abs(float(arousal_slope)) > 1e-6 else 0.0
    signals += 1.0 if has_cut_cadence else 0.0
    signals += 1.0 if has_audio else 0.0
    return signals / 5.0


def _unique_warnings(warnings: Sequence[RewardAnticipationWarning]) -> List[RewardAnticipationWarning]:
    deduped: Dict[tuple[str, Optional[int], Optional[int]], RewardAnticipationWarning] = {}
    for item in warnings:
        key = (item.warning_key, item.start_ms, item.end_ms)
        if key not in deduped:
            deduped[key] = item
    return list(deduped.values())


def _index_tracks(
    tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    indexed: Dict[str, List[Dict[str, Any]]] = {}
    for item in tracks:
        track_name = _track_attr(item, "track_name")
        if track_name is None:
            continue
        indexed.setdefault(str(track_name), []).append(
            {
                "start_ms": int(_track_attr(item, "start_ms") or 0),
                "end_ms": int(_track_attr(item, "end_ms") or 0),
                "numeric_value": to_float_optional(_track_attr(item, "numeric_value")),
            }
        )
    return indexed


def _track_has_values(
    index: Mapping[str, Sequence[Dict[str, Any]]],
    name: str,
    start_ms: int,
    end_ms: int,
) -> bool:
    values = _track_values(index, name, start_ms, end_ms)
    return bool(values)


def _track_mean(
    index: Mapping[str, Sequence[Dict[str, Any]]],
    name: str,
    start_ms: int,
    end_ms: int,
) -> Optional[float]:
    values = _track_values(index, name, start_ms, end_ms)
    return mean_optional(values)


def _track_values(
    index: Mapping[str, Sequence[Dict[str, Any]]],
    name: str,
    start_ms: int,
    end_ms: int,
) -> List[float]:
    rows = index.get(name) or []
    values: List[float] = []
    for row in rows:
        row_start = int(row.get("start_ms") or 0)
        row_end = int(row.get("end_ms") or 0)
        if row_end <= start_ms or row_start >= end_ms:
            continue
        value = to_float_optional(row.get("numeric_value"))
        if value is not None:
            values.append(value)
    return values


def _track_min_max(rows: Sequence[Dict[str, Any]]) -> Optional[tuple[float, float]]:
    values = [
        to_float_optional(row.get("numeric_value"))
        for row in rows
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return min(values), max(values)


def _segment_attr(item: TimelineSegmentRead | Dict[str, Any], key: str) -> Optional[object]:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _track_attr(item: FeatureTrackRead | Dict[str, Any], key: str) -> Optional[object]:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)



def _stddev(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean_value = mean_optional(values)
    if mean_value is None:
        return None
    variance = sum((value - mean_value) ** 2 for value in values) / float(len(values))
    return math.sqrt(max(variance, 0.0))

