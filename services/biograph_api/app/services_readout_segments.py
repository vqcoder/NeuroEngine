"""Segment-detection logic extracted from services_readout.

Detects golden scenes, dead zones, and confusion segments from the
aggregated bucket rows.  Also provides ``with_segment_context`` and
``nearest_cta_context`` helpers used by the readout orchestrator.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .readout_metrics import (
    ReadoutMetricConfig,
    clamp,
    mean,
)
from .schemas import (
    ReadoutCtaMarker,
    ReadoutSegment,
    ReadoutTracePoint,
)
from .services_catalog import SceneGraphContext, _resolve_scene_alignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def nearest_cta_context(
    video_time_ms: int,
    cta_markers: List[ReadoutCtaMarker],
    window_ms: int,
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Return ``(cta_id, distance_ms, window_type)`` for the CTA closest to *video_time_ms*."""
    if not cta_markers:
        return None, None, None
    nearest = min(
        cta_markers,
        key=lambda marker: abs(video_time_ms - marker.video_time_ms),
    )
    distance = video_time_ms - nearest.video_time_ms
    if abs(distance) <= window_ms:
        window_type = "on_cta"
    elif distance < 0:
        window_type = "pre_cta"
    else:
        window_type = "post_cta"
    return nearest.cta_id, distance, window_type


def with_segment_context(
    *,
    start_ms: int,
    end_ms: int,
    metric: str,
    magnitude: float,
    confidence: Optional[float],
    reason_codes: List[str],
    scene_graph: SceneGraphContext,
    cta_markers: List[ReadoutCtaMarker],
    window_ms: int,
    notes: Optional[str] = None,
) -> ReadoutSegment:
    """Build a ``ReadoutSegment`` enriched with scene/CTA context."""
    midpoint = int((start_ms + end_ms) / 2)
    scene_id_value, cut_id_value, cta_id_value = _resolve_scene_alignment(
        scene_graph,
        midpoint,
    )
    nearest_cta_id, distance_to_cta_ms, cta_window = nearest_cta_context(
        midpoint, cta_markers, window_ms,
    )
    return ReadoutSegment(
        start_video_time_ms=start_ms,
        end_video_time_ms=end_ms,
        metric=metric,
        magnitude=round(magnitude, 6),
        confidence=round(confidence, 6) if confidence is not None else None,
        reason_codes=reason_codes,
        scene_id=scene_id_value,
        cut_id=cut_id_value,
        cta_id=cta_id_value or nearest_cta_id,
        distance_to_cta_ms=distance_to_cta_ms,
        cta_window=cta_window,  # type: ignore[arg-type]
        score=round(magnitude, 6),
        notes=notes or ",".join(reason_codes),
    )


# ---------------------------------------------------------------------------
# Segment builders
# ---------------------------------------------------------------------------

def build_golden_scenes(
    attention_score_points: List[ReadoutTracePoint],
    reward_proxy_points: List[ReadoutTracePoint],
    tracking_confidence_points: List[ReadoutTracePoint],
    scene_graph: SceneGraphContext,
    cta_markers: List[ReadoutCtaMarker],
    window_ms: int,
) -> List[ReadoutSegment]:
    """Return the top-5 golden-scene segments by blended reward+attention magnitude."""
    reward_by_time = {point.video_time_ms: point.value for point in reward_proxy_points}
    confidence_by_time = {point.video_time_ms: point.value for point in tracking_confidence_points}
    sorted_attention_points = sorted(attention_score_points, key=lambda point: point.video_time_ms)

    golden_candidates: List[ReadoutSegment] = []
    for point in sorted_attention_points:
        if point.value is None:
            continue
        reward_value = reward_by_time.get(point.video_time_ms) or 0.0
        magnitude = (0.62 * reward_value) + (0.38 * point.value)
        reason_codes = ["high_reward_proxy", "high_attention_score"]
        if point.cta_id:
            reason_codes.append("cta_context")
        golden_candidates.append(
            with_segment_context(
                start_ms=point.video_time_ms,
                end_ms=point.video_time_ms + window_ms,
                metric="golden_scene",
                magnitude=magnitude,
                confidence=confidence_by_time.get(point.video_time_ms),
                reason_codes=reason_codes,
                scene_graph=scene_graph,
                cta_markers=cta_markers,
                window_ms=window_ms,
                notes="golden_scene_window",
            )
        )
    return sorted(golden_candidates, key=lambda item: item.magnitude, reverse=True)[:5]


def build_dead_zones(
    attention_score_points: List[ReadoutTracePoint],
    reward_proxy_points: List[ReadoutTracePoint],
    attention_velocity_points: List[ReadoutTracePoint],
    tracking_confidence_points: List[ReadoutTracePoint],
    scene_graph: SceneGraphContext,
    cta_markers: List[ReadoutCtaMarker],
    window_ms: int,
    config: ReadoutMetricConfig,
) -> List[ReadoutSegment]:
    """Detect sustained low-attention / low-reward dead zones."""
    reward_by_time = {point.video_time_ms: point.value for point in reward_proxy_points}
    velocity_by_time = {point.video_time_ms: point.value for point in attention_velocity_points}
    confidence_by_time = {point.video_time_ms: point.value for point in tracking_confidence_points}
    sorted_attention_points = sorted(attention_score_points, key=lambda point: point.video_time_ms)

    dead_zones: List[ReadoutSegment] = []
    dead_start: Optional[int] = None
    dead_end: Optional[int] = None
    dead_magnitudes: List[float] = []
    dead_confidence: List[float] = []
    dead_reason_codes: set[str] = set()

    for point in sorted_attention_points:
        if point.value is None:
            continue
        reward_value = reward_by_time.get(point.video_time_ms) or 0.0
        velocity_value = velocity_by_time.get(point.video_time_ms) or 0.0
        conf_value = confidence_by_time.get(point.video_time_ms)
        low_attention = point.value <= config.dead_zone_threshold
        low_reward = reward_value <= 40.0
        dropping = velocity_value <= -abs(config.loss_threshold)
        is_dead = low_attention or (low_reward and dropping)
        if is_dead:
            if dead_start is None:
                dead_start = point.video_time_ms
            dead_end = point.video_time_ms + window_ms
            drop_mag = max(0.0, config.dead_zone_threshold - point.value) + max(0.0, 40.0 - reward_value)
            dead_magnitudes.append(drop_mag)
            if conf_value is not None:
                dead_confidence.append(conf_value)
            if low_attention:
                dead_reason_codes.add("sustained_attention_drop")
            if low_reward:
                dead_reason_codes.add("low_reward_proxy")
            if dropping:
                dead_reason_codes.add("negative_attention_velocity")
            if conf_value is not None and conf_value < 0.5:
                dead_reason_codes.add("low_tracking_confidence")
        else:
            if (
                dead_start is not None
                and dead_end is not None
                and (dead_end - dead_start) >= (config.min_segment_windows * window_ms)
            ):
                dead_zones.append(
                    with_segment_context(
                        start_ms=dead_start,
                        end_ms=dead_end,
                        metric="dead_zone",
                        magnitude=mean(dead_magnitudes) if dead_magnitudes else 0.0,
                        confidence=mean(dead_confidence) if dead_confidence else None,
                        reason_codes=sorted(dead_reason_codes) or ["sustained_attention_drop"],
                        scene_graph=scene_graph,
                        cta_markers=cta_markers,
                        window_ms=window_ms,
                        notes="dead_zone_segment",
                    )
                )
            dead_start = None
            dead_end = None
            dead_magnitudes = []
            dead_confidence = []
            dead_reason_codes = set()

    # Flush trailing run
    if (
        dead_start is not None
        and dead_end is not None
        and (dead_end - dead_start) >= (config.min_segment_windows * window_ms)
    ):
        dead_zones.append(
            with_segment_context(
                start_ms=dead_start,
                end_ms=dead_end,
                metric="dead_zone",
                magnitude=mean(dead_magnitudes) if dead_magnitudes else 0.0,
                confidence=mean(dead_confidence) if dead_confidence else None,
                reason_codes=sorted(dead_reason_codes) or ["sustained_attention_drop"],
                scene_graph=scene_graph,
                cta_markers=cta_markers,
                window_ms=window_ms,
                notes="dead_zone_segment",
            )
        )

    return dead_zones


def build_confusion_segments(
    attention_score_points: List[ReadoutTracePoint],
    blink_rate_points: List[ReadoutTracePoint],
    attention_velocity_points: List[ReadoutTracePoint],
    tracking_confidence_points: List[ReadoutTracePoint],
    au_points_au04: List[ReadoutTracePoint],
    scene_graph: SceneGraphContext,
    cta_markers: List[ReadoutCtaMarker],
    window_ms: int,
    config: ReadoutMetricConfig,
    global_blink_baseline: float,
) -> List[ReadoutSegment]:
    """Detect confusion segments from blink-rate + AU04 + velocity signals."""
    blink_rate_by_time = {point.video_time_ms: point.value for point in blink_rate_points}
    au4_by_time = {point.video_time_ms: point.value for point in au_points_au04}
    velocity_by_time = {point.video_time_ms: point.value for point in attention_velocity_points}
    confidence_by_time = {point.video_time_ms: point.value for point in tracking_confidence_points}
    sorted_attention_points = sorted(attention_score_points, key=lambda point: point.video_time_ms)

    confusion_segments: List[ReadoutSegment] = []
    confusion_start: Optional[int] = None
    confusion_end: Optional[int] = None
    confusion_magnitudes: List[float] = []
    confusion_confidence: List[float] = []

    for point in sorted_attention_points:
        blink_rate_value = blink_rate_by_time.get(point.video_time_ms) or 0.0
        au4_value = au4_by_time.get(point.video_time_ms) or 0.0
        velocity_value = velocity_by_time.get(point.video_time_ms) or 0.0
        conf_value = confidence_by_time.get(point.video_time_ms)
        is_confusion = (
            blink_rate_value >= max(config.confusion_blink_rate_threshold, global_blink_baseline * 1.35)
            and au4_value >= config.confusion_au4_threshold
        ) or (
            velocity_value <= config.confusion_velocity_threshold
            and au4_value >= config.confusion_au4_threshold
        )
        if is_confusion:
            if confusion_start is None:
                confusion_start = point.video_time_ms
            confusion_end = point.video_time_ms + window_ms
            blink_ratio = blink_rate_value / max(global_blink_baseline, 1e-3)
            confusion_magnitudes.append(max(0.0, blink_ratio - 1.0) + (au4_value * 4.0) + max(0.0, -velocity_value))
            if conf_value is not None:
                confusion_confidence.append(conf_value)
        else:
            if confusion_start is not None and confusion_end is not None:
                confusion_segments.append(
                    with_segment_context(
                        start_ms=confusion_start,
                        end_ms=confusion_end,
                        metric="confusion_segment",
                        magnitude=mean(confusion_magnitudes) if confusion_magnitudes else 0.0,
                        confidence=mean(confusion_confidence) if confusion_confidence else None,
                        reason_codes=[
                            "elevated_blink_rate",
                            "au4_friction_proxy",
                            "negative_attention_velocity",
                        ],
                        scene_graph=scene_graph,
                        cta_markers=cta_markers,
                        window_ms=window_ms,
                        notes="blink_rate_plus_au4_friction_proxy",
                    )
                )
            confusion_start = None
            confusion_end = None
            confusion_magnitudes = []
            confusion_confidence = []

    # Flush trailing run
    if confusion_start is not None and confusion_end is not None:
        confusion_segments.append(
            with_segment_context(
                start_ms=confusion_start,
                end_ms=confusion_end,
                metric="confusion_segment",
                magnitude=mean(confusion_magnitudes) if confusion_magnitudes else 0.0,
                confidence=mean(confusion_confidence) if confusion_confidence else None,
                reason_codes=[
                    "elevated_blink_rate",
                    "au4_friction_proxy",
                    "negative_attention_velocity",
                ],
                scene_graph=scene_graph,
                cta_markers=cta_markers,
                window_ms=window_ms,
                notes="blink_rate_plus_au4_friction_proxy",
            )
        )

    return confusion_segments
