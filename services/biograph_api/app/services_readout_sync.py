"""Attentional-synchrony computation extracted from services_readout.

This module contains the pairwise synchrony calculation, timeline score
construction, and the full attentional-synchrony diagnostics builder that was
previously inlined inside ``build_video_readout``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

from .readout_metrics import clamp, mean
from .schemas import (
    AttentionalSynchronyDiagnostics,
    AttentionalSynchronyExtrema,
    AttentionalSynchronyPathway,
    AttentionalSynchronyTimelineScore,
    ReadoutScene,
)
from .services_math import (
    _mean_optional,
    _pearson_correlation,
    _weighted_mean,
)
from .services_catalog import SceneGraphContext

from uuid import UUID


# ---------------------------------------------------------------------------
# Helpers (formerly closures inside build_video_readout)
# ---------------------------------------------------------------------------

def compute_pairwise_synchrony(
    metric_field: str,
    session_bucket_rows_by_session: Dict[UUID, Dict[int, Dict[str, object]]],
    session_weight_by_session: Dict[UUID, float],
    *,
    min_confidence: float = 0.35,
) -> Optional[float]:
    """Compute weighted pairwise Pearson synchrony across sessions for *metric_field*."""
    if len(session_bucket_rows_by_session) < 2:
        return None
    pairwise_values: List[float] = []
    pairwise_weights: List[float] = []
    session_ids_for_sync = list(session_bucket_rows_by_session.keys())
    for left_id, right_id in combinations(session_ids_for_sync, 2):
        left_rows = session_bucket_rows_by_session[left_id]
        right_rows = session_bucket_rows_by_session[right_id]
        common_times = sorted(set(left_rows.keys()) & set(right_rows.keys()))
        left_series: List[float] = []
        right_series: List[float] = []
        local_quality_weights: List[float] = []
        for bucket_time in common_times:
            left_row = left_rows[bucket_time]
            right_row = right_rows[bucket_time]
            left_conf = left_row.get("tracking_confidence")
            right_conf = right_row.get("tracking_confidence")
            if left_conf is not None and float(left_conf) < min_confidence:
                continue
            if right_conf is not None and float(right_conf) < min_confidence:
                continue
            left_value = left_row.get(metric_field)
            right_value = right_row.get(metric_field)
            if left_value is None or right_value is None:
                continue
            left_series.append(float(left_value))
            right_series.append(float(right_value))
            quality_parts = [
                float(value)
                for value in [
                    left_row.get("tracking_confidence"),
                    right_row.get("tracking_confidence"),
                    left_row.get("quality_score"),
                    right_row.get("quality_score"),
                ]
                if value is not None
            ]
            local_quality_weights.append(
                clamp(mean(quality_parts), 0.1, 1.0) if quality_parts else 1.0
            )
        if len(left_series) < 3:
            continue
        correlation = _pearson_correlation(left_series, right_series)
        if correlation is None:
            continue
        base_pair_weight = min(
            session_weight_by_session.get(left_id, 0.5),
            session_weight_by_session.get(right_id, 0.5),
        )
        overlap_weight = (
            clamp(mean(local_quality_weights), 0.1, 1.0)
            if local_quality_weights
            else 1.0
        )
        pairwise_values.append(correlation)
        pairwise_weights.append(max(base_pair_weight * overlap_weight, 0.01))
    return _weighted_mean(pairwise_values, pairwise_weights)


def series_concentration(values: Sequence[float], span: float) -> Optional[float]:
    """Return how concentrated *values* are around their mean within *span*."""
    if len(values) < 2 or span <= 0:
        return None
    center = sum(float(value) for value in values) / float(len(values))
    variance = sum((float(value) - center) ** 2 for value in values) / float(len(values))
    std = math.sqrt(max(variance, 0.0))
    return round(clamp(1.0 - (std / span), 0.0, 1.0), 6)


def build_timeline_scores(
    bucket_scores: Dict[int, float],
    bucket_confidences: Dict[int, float],
    pathway: AttentionalSynchronyPathway,
    scene_graph: SceneGraphContext,
    window_ms: int,
) -> List[AttentionalSynchronyTimelineScore]:
    """Build per-scene (or per-bucket) timeline synchrony scores."""
    if not bucket_scores:
        return []
    sorted_times = sorted(bucket_scores.keys())
    reason_by_pathway = {
        AttentionalSynchronyPathway.direct_panel_gaze: "Direct panel gaze overlap and aligned attention supported convergence.",
        AttentionalSynchronyPathway.fallback_proxy: "Fallback proxy uses salience concentration and subject continuity with reduced certainty.",
        AttentionalSynchronyPathway.insufficient_data: "Not enough synchronized panel evidence to estimate timeline synchrony.",
    }
    segment_scores: List[AttentionalSynchronyTimelineScore] = []

    if scene_graph.scenes:
        for scene in scene_graph.scenes:
            scene_times = [
                bucket_time
                for bucket_time in sorted_times
                if int(scene.start_ms) <= int(bucket_time) < int(scene.end_ms)
            ]
            if not scene_times:
                continue
            score_values = [float(bucket_scores[bucket_time]) for bucket_time in scene_times]
            confidence_values = [
                float(bucket_confidences.get(bucket_time, 0.0))
                for bucket_time in scene_times
            ]
            score_mean = _mean_optional(score_values)
            confidence_mean = _mean_optional(confidence_values)
            if score_mean is None or confidence_mean is None:
                continue
            segment_scores.append(
                AttentionalSynchronyTimelineScore(
                    start_ms=int(scene.start_ms),
                    end_ms=max(int(scene.end_ms), int(scene.start_ms) + 1),
                    score=round(score_mean, 6),
                    confidence=round(confidence_mean, 6),
                    pathway=pathway,
                    reason=reason_by_pathway[pathway],
                )
            )

    if segment_scores:
        return segment_scores

    for bucket_time in sorted_times:
        segment_scores.append(
            AttentionalSynchronyTimelineScore(
                start_ms=int(bucket_time),
                end_ms=int(bucket_time) + window_ms,
                score=round(float(bucket_scores[bucket_time]), 6),
                confidence=round(float(bucket_confidences.get(bucket_time, 0.0)), 6),
                pathway=pathway,
                reason=reason_by_pathway[pathway],
            )
        )
    return segment_scores


def build_extrema(
    segment_scores: Sequence[AttentionalSynchronyTimelineScore],
    *,
    reverse: bool,
    reason: str,
    limit: int = 3,
) -> List[AttentionalSynchronyExtrema]:
    """Return top/bottom extrema from *segment_scores*."""
    ranked = sorted(segment_scores, key=lambda item: float(item.score), reverse=reverse)
    return [
        AttentionalSynchronyExtrema(
            start_ms=int(item.start_ms),
            end_ms=int(item.end_ms),
            score=round(float(item.score), 6),
            reason=reason,
        )
        for item in ranked[:limit]
    ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_attentional_synchrony_diagnostics(
    *,
    session_bucket_rows_by_session: Dict[UUID, Dict[int, Dict[str, object]]],
    session_weight_by_session: Dict[UUID, float],
    bucket_rows: List[Dict[str, object]],
    scene_graph: SceneGraphContext,
    window_ms: int,
    attention_synchrony: Optional[float],
) -> Tuple[
    Optional[AttentionalSynchronyDiagnostics],
    Optional[float],   # gaze_synchrony (needed downstream)
]:
    """Build the full attentional-synchrony diagnostic block.

    Returns ``(diagnostics, gaze_synchrony)`` so the caller can thread
    ``gaze_synchrony`` into subsequent computations without duplicating
    the pairwise-synchrony logic.
    """
    panel_rows_by_time: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    all_direct_coverages: List[float] = []
    for session_rows in session_bucket_rows_by_session.values():
        for bucket_time, row in session_rows.items():
            panel_rows_by_time[int(bucket_time)].append(row)
            all_direct_coverages.append(float(row.get("gaze_direct_coverage") or 0.0))
    direct_signal_coverage = _mean_optional(all_direct_coverages) or 0.0
    panel_quality = _mean_optional(
        [float(value) for value in session_weight_by_session.values()]
    ) or 0.45

    direct_bucket_scores: Dict[int, float] = {}
    direct_bucket_confidences: Dict[int, float] = {}
    fallback_bucket_scores: Dict[int, float] = {}
    fallback_bucket_confidences: Dict[int, float] = {}

    for bucket_time in sorted(panel_rows_by_time.keys()):
        rows_at_time = panel_rows_by_time[bucket_time]
        qualified_rows = []
        for row in rows_at_time:
            tracking_conf = row.get("tracking_confidence")
            if tracking_conf is not None and float(tracking_conf) < 0.3:
                continue
            gaze_value = row.get("gaze_on_screen")
            if gaze_value is None:
                continue
            qualified_rows.append(row)
        if len(qualified_rows) < 2:
            continue
        bucket_direct_coverage = _mean_optional(
            [float(row.get("gaze_direct_coverage") or 0.0) for row in qualified_rows]
        ) or 0.0
        if bucket_direct_coverage < 0.45:
            continue

        gaze_values = [float(row["gaze_on_screen"]) for row in qualified_rows]
        gaze_concentration = series_concentration(gaze_values, span=0.45)
        if gaze_concentration is None:
            continue
        attention_values = [
            float(row["attention_score"])
            for row in qualified_rows
            if row.get("attention_score") is not None
        ]
        attention_concentration = series_concentration(attention_values, span=25.0)
        quality_values = [
            float(value)
            for row in qualified_rows
            for value in [row.get("tracking_confidence"), row.get("quality_score")]
            if value is not None
        ]
        quality_mean = _mean_optional(quality_values) or panel_quality
        attention_component = (
            attention_concentration
            if attention_concentration is not None
            else gaze_concentration
        )
        direct_unit = clamp(
            (0.55 * gaze_concentration)
            + (0.25 * attention_component)
            + (0.20 * bucket_direct_coverage),
            0.0,
            1.0,
        )
        direct_bucket_scores[bucket_time] = round(direct_unit * 100.0, 6)
        direct_bucket_confidences[bucket_time] = round(
            clamp((0.55 * quality_mean) + (0.45 * bucket_direct_coverage), 0.0, 1.0),
            6,
        )

    sorted_bucket_rows = sorted(bucket_rows, key=lambda item: int(item["bucket_start"]))
    for index, row in enumerate(sorted_bucket_rows):
        bucket_time = int(row["bucket_start"])
        attention_score_value = row.get("attention_score")
        if attention_score_value is None:
            continue
        attention_component = clamp(float(attention_score_value) / 100.0, 0.0, 1.0)
        subject_parts = [
            float(value)
            for value in [
                row.get("face_presence"),
                row.get("head_pose_stability"),
                row.get("playback_continuity"),
            ]
            if value is not None
        ]
        subject_continuity = _mean_optional(subject_parts) or 0.45
        continuity_score = 0.4
        previous_row = sorted_bucket_rows[index - 1] if index > 0 else None
        next_row = (
            sorted_bucket_rows[index + 1]
            if index + 1 < len(sorted_bucket_rows)
            else None
        )
        current_scene = row.get("scene_id")
        if (
            previous_row is not None
            and current_scene is not None
            and previous_row.get("scene_id") == current_scene
        ):
            continuity_score += 0.3
        if (
            next_row is not None
            and current_scene is not None
            and next_row.get("scene_id") == current_scene
        ):
            continuity_score += 0.3
        continuity_score = clamp(continuity_score, 0.0, 1.0)
        fallback_unit = clamp(
            (0.5 * attention_component)
            + (0.3 * subject_continuity)
            + (0.2 * continuity_score),
            0.0,
            1.0,
        )
        quality_values = [
            float(value)
            for value in [row.get("tracking_confidence"), row.get("quality_score")]
            if value is not None
        ]
        quality_mean = _mean_optional(quality_values) or panel_quality
        fallback_bucket_scores[bucket_time] = round(fallback_unit * 100.0, 6)
        fallback_bucket_confidences[bucket_time] = round(
            clamp(quality_mean * 0.72, 0.12, 0.7),
            6,
        )

    gaze_synchrony = compute_pairwise_synchrony(
        "gaze_on_screen",
        session_bucket_rows_by_session,
        session_weight_by_session,
        min_confidence=0.3,
    )
    use_direct_path = (
        len(session_bucket_rows_by_session) >= 2
        and direct_signal_coverage >= 0.5
        and gaze_synchrony is not None
        and len(direct_bucket_scores) >= 3
    )

    if use_direct_path:
        bucket_global_score = _weighted_mean(
            list(direct_bucket_scores.values()),
            list(direct_bucket_confidences.values()),
        )
        global_candidates: List[Tuple[float, float]] = []
        if bucket_global_score is not None:
            global_candidates.append((float(bucket_global_score), 0.55))
        if gaze_synchrony is not None:
            global_candidates.append(
                (clamp((float(gaze_synchrony) + 1.0) * 50.0, 0.0, 100.0), 0.3)
            )
        if attention_synchrony is not None:
            global_candidates.append(
                (clamp((float(attention_synchrony) + 1.0) * 50.0, 0.0, 100.0), 0.15)
            )
        total_weight = sum(weight for _, weight in global_candidates)
        global_score = (
            round(
                sum(score * weight for score, weight in global_candidates) / total_weight,
                6,
            )
            if total_weight > 0
            else None
        )
        bucket_confidence_mean = _mean_optional(
            list(direct_bucket_confidences.values())
        ) or panel_quality
        global_confidence = round(
            clamp(
                (0.45 * direct_signal_coverage)
                + (0.35 * panel_quality)
                + (0.2 * bucket_confidence_mean),
                0.0,
                1.0,
            ),
            6,
        )
        segment_scores = build_timeline_scores(
            direct_bucket_scores,
            direct_bucket_confidences,
            AttentionalSynchronyPathway.direct_panel_gaze,
            scene_graph,
            window_ms,
        )
        diagnostics = AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.direct_panel_gaze,
            global_score=global_score,
            confidence=global_confidence,
            segment_scores=segment_scores,
            peaks=build_extrema(
                segment_scores,
                reverse=True,
                reason="Peak convergence window with strongest shared visual focus.",
            ),
            valleys=build_extrema(
                segment_scores,
                reverse=False,
                reason="Low-convergence window where viewer focus diverged.",
            ),
            evidence_summary=(
                "Direct panel gaze overlap was available and used as the primary pathway, "
                "with attention alignment as supporting evidence."
            ),
            signals_used=[
                "panel_gaze_overlap",
                "cross_user_attention_alignment",
                "signal_quality_weighting",
            ],
        )
    elif fallback_bucket_scores:
        global_score = _weighted_mean(
            list(fallback_bucket_scores.values()),
            list(fallback_bucket_confidences.values()),
        )
        global_confidence = _mean_optional(list(fallback_bucket_confidences.values()))
        segment_scores = build_timeline_scores(
            fallback_bucket_scores,
            fallback_bucket_confidences,
            AttentionalSynchronyPathway.fallback_proxy,
            scene_graph,
            window_ms,
        )
        diagnostics = AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.fallback_proxy,
            global_score=global_score,
            confidence=round(clamp((global_confidence or 0.35) * 0.85, 0.1, 0.68), 6),
            segment_scores=segment_scores,
            peaks=build_extrema(
                segment_scores,
                reverse=True,
                reason="Fallback proxy indicates stronger concentration and continuity in this window.",
            ),
            valleys=build_extrema(
                segment_scores,
                reverse=False,
                reason="Fallback proxy indicates weaker concentration continuity in this window.",
            ),
            evidence_summary=(
                "Direct multi-user gaze overlap was limited, so a fallback proxy estimator was used. "
                "Confidence is explicitly downweighted relative to the direct pathway."
            ),
            signals_used=[
                "attention_concentration_proxy",
                "subject_continuity_proxy",
                "playback_continuity",
                "signal_quality_weighting",
            ],
        )
    else:
        diagnostics = AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.insufficient_data,
            evidence_summary=(
                "Insufficient panel overlap and proxy support to estimate attentional synchrony."
            ),
            signals_used=[],
        )

    return diagnostics, gaze_synchrony
