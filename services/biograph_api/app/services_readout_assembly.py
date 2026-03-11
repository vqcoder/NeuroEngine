"""Response-assembly helpers extracted from services_readout.

Contains annotation summary, survey summary, quality summary, diagnostic
card builders, trace-point list construction, and the aggregate diagnostic
score orchestration that were previously inlined at the tail end of
``build_video_readout``.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from .readout_metrics import (
    DiagnosticCtaMarker,
    DiagnosticPoint,
    DiagnosticScene,
    DiagnosticSegment,
    ReadoutMetricConfig,
    build_scene_diagnostic_cards,
    clamp,
    mean,
)
from .schemas import (
    AnnotationMarkerType,
    AnnotationSummary,
    AttentionalSynchronyDiagnostics,
    AU_DEFAULTS,
    AuFrictionDiagnostics,
    BlinkTransportDiagnostics,
    BoundaryEncodingDiagnostics,
    CtaReceptionDiagnostics,
    MarkerDensityPoint,
    MarkerTimestampSummary,
    NarrativeControlDiagnostics,
    ReadoutAUChannel,
    ReadoutCtaMarker,
    ReadoutLabels,
    ReadoutLowConfidenceWindow,
    ReadoutQuality,
    ReadoutQualitySummary,
    ReadoutScene,
    ReadoutSegment,
    ReadoutSegments,
    ReadoutTracePoint,
    ReadoutTraces,
    RewardAnticipationDiagnostics,
    SceneDiagnosticCard,
    SelfRelevanceDiagnostics,
    SessionAnnotationRead,
    SocialTransmissionDiagnostics,
    SurveySummary,
    SurveyResponseRead,
    SyntheticLiftPriorDiagnostics,
)
from .services_math import _mean_optional, _round_rate
from .services_catalog import SceneGraphContext, _resolve_scene_alignment
from .quality_thresholds import (
    get_readout_quality_thresholds,
    is_low_confidence_window,
    resolve_quality_badge,
)
from .services_ingestion import _resolve_trace_source_summary
from fastapi import HTTPException
from .domain_exceptions import DomainError
from .au_friction import compute_au_friction_diagnostics, resolve_au_friction_config
from .blink_transport import compute_blink_transport_diagnostics, resolve_blink_transport_config
from .boundary_encoding import compute_boundary_encoding_diagnostics, resolve_boundary_encoding_config
from .cta_reception import compute_cta_reception_diagnostics, resolve_cta_reception_config
from .narrative_control import compute_narrative_control_diagnostics, resolve_narrative_control_config
from .reward_anticipation import compute_reward_anticipation_diagnostics, resolve_reward_anticipation_config
from .self_relevance import compute_self_relevance_diagnostics, resolve_self_relevance_config
from .social_transmission import compute_social_transmission_diagnostics, resolve_social_transmission_config
from .synthetic_lift_prior import compute_synthetic_lift_prior_diagnostics, resolve_synthetic_lift_prior_config
from .timeline_feature_store import DEFAULT_TIMELINE_ANALYSIS_VERSION, query_timeline_features_window
from .services_math import (
    _clamp_to_metric_domain,
    _median,
    _resolve_timeline_asset_id,
    _sem_confidence_interval,
    _weighted_mean,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Annotation summary
# ---------------------------------------------------------------------------

def build_annotation_summary(
    selected_annotations: list,
    scene_graph: SceneGraphContext,
    window_ms: int,
    selected_session_count: int,
) -> AnnotationSummary:
    """Compute the ``AnnotationSummary`` block."""
    annotation_counts: Dict[str, int] = {
        "engaging_moment": 0,
        "confusing_moment": 0,
        "stop_watching_moment": 0,
        "cta_landed_moment": 0,
    }
    density_buckets: Dict[Tuple[str, int], Dict[str, object]] = {}
    for annotation in selected_annotations:
        marker_type = annotation.marker_type
        if marker_type in annotation_counts:
            annotation_counts[marker_type] += 1

        bucket_start = (int(annotation.video_time_ms) // window_ms) * window_ms
        key = (marker_type, bucket_start)
        if key not in density_buckets:
            scene_id, cut_id, cta_id = _resolve_scene_alignment(scene_graph, bucket_start)
            density_buckets[key] = {
                "count": 0,
                "scene_id": annotation.scene_id or scene_id,
                "cut_id": annotation.cut_id or cut_id,
                "cta_id": annotation.cta_id or cta_id,
            }
        density_buckets[key]["count"] = int(density_buckets[key]["count"]) + 1

    marker_density: List[MarkerDensityPoint] = []
    for (marker_type, bucket_start), payload in sorted(
        density_buckets.items(),
        key=lambda item: (item[0][1], item[0][0]),
    ):
        count = int(payload["count"])
        marker_density.append(
            MarkerDensityPoint(
                marker_type=AnnotationMarkerType(marker_type),
                video_time_ms=bucket_start,
                count=count,
                density=round(count / float(selected_session_count), 6),
                scene_id=payload["scene_id"],  # type: ignore[arg-type]
                cut_id=payload["cut_id"],  # type: ignore[arg-type]
                cta_id=payload["cta_id"],  # type: ignore[arg-type]
            )
        )

    def _top_timestamps(mt: str) -> List[MarkerTimestampSummary]:
        filtered = [item for item in marker_density if item.marker_type.value == mt]
        ranked = sorted(filtered, key=lambda item: (-item.count, item.video_time_ms))
        return [
            MarkerTimestampSummary(
                video_time_ms=item.video_time_ms,
                count=item.count,
                density=item.density,
                scene_id=item.scene_id,
                cut_id=item.cut_id,
                cta_id=item.cta_id,
            )
            for item in ranked[:5]
        ]

    return AnnotationSummary(
        total_annotations=len(selected_annotations),
        engaging_moment_count=annotation_counts["engaging_moment"],
        confusing_moment_count=annotation_counts["confusing_moment"],
        stop_watching_moment_count=annotation_counts["stop_watching_moment"],
        cta_landed_moment_count=annotation_counts["cta_landed_moment"],
        marker_density=marker_density,
        top_engaging_timestamps=_top_timestamps("engaging_moment"),
        top_confusing_timestamps=_top_timestamps("confusing_moment"),
    )


# ---------------------------------------------------------------------------
# Survey summary
# ---------------------------------------------------------------------------

def build_survey_summary(
    selected_survey_responses: list,
) -> SurveySummary:
    """Compute the ``SurveySummary`` block."""

    def _mean_question(keys: Sequence[str]) -> Optional[float]:
        values = [
            float(item.response_number)
            for item in selected_survey_responses
            if item.question_key in keys and item.response_number is not None
        ]
        if not values:
            return None
        return round(mean(values), 6)

    return SurveySummary(
        responses_count=len(selected_survey_responses),
        overall_interest_mean=_mean_question(
            ["overall_interest_likert", "overall_interest", "interest_likert"]
        ),
        recall_comprehension_mean=_mean_question(
            ["recall_comprehension_likert", "recall_comprehension", "comprehension_recall_likert"]
        ),
        desire_to_continue_or_take_action_mean=_mean_question(
            [
                "desire_to_continue_or_take_action_likert",
                "desire_to_continue_likert",
                "desire_to_take_action_likert",
            ]
        ),
        comment_count=sum(
            1
            for item in selected_survey_responses
            if item.question_key == "post_annotation_comment"
            and item.response_text is not None
            and item.response_text.strip()
        ),
    )


# ---------------------------------------------------------------------------
# Quality summary + low-confidence windows
# ---------------------------------------------------------------------------

def build_quality_summary(
    bucket_rows: List[Dict[str, object]],
    points: list,
    tracking_confidence_points: List[ReadoutTracePoint],
    quality_scores: List[Optional[float]],
    selected_sessions: list,
    session_ids: list,
    playback_events: list,
    participants_count: int,
    window_ms: int,
    video_duration_ms: Optional[int],
    attention_score_points: List[ReadoutTracePoint],
    db,  # sqlalchemy Session
) -> Tuple[ReadoutQualitySummary, List[ReadoutLowConfidenceWindow], str]:
    """Build session quality summary, low-confidence windows, and quality badge.

    Returns ``(quality_summary, low_confidence_windows, quality_badge)``.
    """
    total_points = len(points)
    face_ok_rate = _round_rate(sum(int(item.face_ok) for item in points), total_points)
    mean_brightness = mean([float(item.brightness) for item in points]) if points else 0.0
    mean_tracking_confidence = _mean_optional([item.value for item in tracking_confidence_points])
    mean_quality_score = _mean_optional(quality_scores)
    quality_thresholds = get_readout_quality_thresholds()

    low_confidence_window_items: List[ReadoutLowConfidenceWindow] = []
    low_start: Optional[int] = None
    low_end: Optional[int] = None
    low_values: List[float] = []
    low_flags: set[str] = set()
    sorted_bucket_rows = sorted(bucket_rows, key=lambda item: int(item["bucket_start"]))
    for row in sorted_bucket_rows:
        point_video_time_ms = int(row["bucket_start"])
        confidence_value = row.get("tracking_confidence")
        quality_flags = [str(flag) for flag in (row.get("quality_flags") or [])]
        is_low = is_low_confidence_window(
            tracking_confidence=(
                float(confidence_value) if confidence_value is not None else None
            ),
            quality_flags=quality_flags,
            thresholds=quality_thresholds,
        )
        if is_low:
            if low_start is None:
                low_start = point_video_time_ms
            low_end = point_video_time_ms + window_ms
            if confidence_value is not None:
                low_values.append(float(confidence_value))
            low_flags.update(quality_flags)
            continue
        if low_start is not None and low_end is not None:
            low_confidence_window_items.append(
                ReadoutLowConfidenceWindow(
                    start_video_time_ms=low_start,
                    end_video_time_ms=low_end,
                    mean_tracking_confidence=round(mean(low_values), 6) if low_values else None,
                    quality_flags=sorted(low_flags),
                )
            )
            low_start = None
            low_end = None
            low_values = []
            low_flags = set()
    if low_start is not None and low_end is not None:
        low_confidence_window_items.append(
            ReadoutLowConfidenceWindow(
                start_video_time_ms=low_start,
                end_video_time_ms=low_end,
                mean_tracking_confidence=round(mean(low_values), 6) if low_values else None,
                quality_flags=sorted(low_flags),
            )
        )

    inferred_duration_ms = (
        int(video_duration_ms)
        if video_duration_ms is not None
        else (
            max((item.video_time_ms for item in attention_score_points), default=0)
            + window_ms
        )
    )
    low_confidence_duration_ms = sum(
        max(window.end_video_time_ms - window.start_video_time_ms, 0)
        for window in low_confidence_window_items
    )
    usable_seconds = round(max(inferred_duration_ms - low_confidence_duration_ms, 0) / 1000.0, 3)
    quality_badge = resolve_quality_badge(
        mean_tracking_confidence=mean_tracking_confidence,
        face_ok_rate=face_ok_rate,
        thresholds=quality_thresholds,
    )
    trace_source_summary = _resolve_trace_source_summary(playback_events, session_ids)

    session_quality_summary = ReadoutQualitySummary(
        sessions_count=len(selected_sessions),
        participants_count=participants_count,
        total_trace_points=total_points,
        face_ok_rate=face_ok_rate,
        mean_brightness=mean_brightness,
        mean_tracking_confidence=mean_tracking_confidence,
        mean_quality_score=mean_quality_score,
        low_confidence_windows=len(low_confidence_window_items),
        usable_seconds=usable_seconds,
        quality_badge=quality_badge,
        trace_source=trace_source_summary,
    )

    return session_quality_summary, low_confidence_window_items, quality_badge


# ---------------------------------------------------------------------------
# Diagnostic cards
# ---------------------------------------------------------------------------

def build_diagnostics(
    bucket_rows: List[Dict[str, object]],
    scenes: list,
    cta_markers: list,
    attention_gain_segments: List[ReadoutSegment],
    attention_loss_segments: List[ReadoutSegment],
    confusion_segments: List[ReadoutSegment],
    window_ms: int,
) -> List[SceneDiagnosticCard]:
    """Build scene diagnostic cards from bucket data."""
    diagnostic_points = [
        DiagnosticPoint(
            video_time_ms=int(row["bucket_start"]),
            attention_score=float(row["attention_score"]),
            reward_proxy=float(row["reward_proxy"]),
            attention_velocity=float(row["attention_velocity"]),
            blink_rate=float(row["blink_rate"]),
            au4=float((row["au_norm"] or {}).get("AU04", 0.0)),  # type: ignore[union-attr]
            tracking_confidence=row["tracking_confidence"],  # type: ignore[arg-type]
            scene_id=row["scene_id"],  # type: ignore[arg-type]
            cut_id=row["cut_id"],  # type: ignore[arg-type]
            cta_id=row["cta_id"],  # type: ignore[arg-type]
        )
        for row in bucket_rows
    ]
    diagnostic_scenes = [
        DiagnosticScene(
            scene_index=scene.scene_index,
            start_ms=scene.start_ms,
            end_ms=scene.end_ms,
            scene_id=scene.scene_id,
            cut_id=scene.cut_id,
            cta_id=scene.cta_id,
            label=scene.label,
            thumbnail_url=scene.thumbnail_url,
        )
        for scene in scenes
    ]
    diagnostic_ctas = [
        DiagnosticCtaMarker(
            cta_id=marker.cta_id,
            video_time_ms=marker.video_time_ms,
            scene_id=marker.scene_id,
            cut_id=marker.cut_id,
        )
        for marker in cta_markers
    ]
    diagnostic_gains = [
        DiagnosticSegment(
            start_video_time_ms=segment.start_video_time_ms,
            end_video_time_ms=segment.end_video_time_ms,
            magnitude=segment.magnitude,
            confidence=segment.confidence,
            reason_codes=segment.reason_codes,
            scene_id=segment.scene_id,
            cut_id=segment.cut_id,
            cta_id=segment.cta_id,
        )
        for segment in attention_gain_segments
    ]
    diagnostic_losses = [
        DiagnosticSegment(
            start_video_time_ms=segment.start_video_time_ms,
            end_video_time_ms=segment.end_video_time_ms,
            magnitude=segment.magnitude,
            confidence=segment.confidence,
            reason_codes=segment.reason_codes,
            scene_id=segment.scene_id,
            cut_id=segment.cut_id,
            cta_id=segment.cta_id,
        )
        for segment in attention_loss_segments
    ]
    diagnostic_confusions = [
        DiagnosticSegment(
            start_video_time_ms=segment.start_video_time_ms,
            end_video_time_ms=segment.end_video_time_ms,
            magnitude=segment.magnitude,
            confidence=segment.confidence,
            reason_codes=segment.reason_codes,
            scene_id=segment.scene_id,
            cut_id=segment.cut_id,
            cta_id=segment.cta_id,
        )
        for segment in confusion_segments
    ]
    return [
        SceneDiagnosticCard.model_validate(item.__dict__)
        for item in build_scene_diagnostic_cards(
            scenes=diagnostic_scenes,
            points=diagnostic_points,
            attention_gain_segments=diagnostic_gains,
            attention_loss_segments=diagnostic_losses,
            confusion_segments=diagnostic_confusions,
            cta_markers=diagnostic_ctas,
            window_ms=window_ms,
        )
    ]


# ---------------------------------------------------------------------------
# Trace-point list building
# ---------------------------------------------------------------------------

def build_trace_point_lists(
    bucket_rows: List[Dict[str, object]],
) -> Tuple[
    List[ReadoutTracePoint],  # attention_score
    List[ReadoutTracePoint],  # attention_velocity
    List[ReadoutTracePoint],  # blink_rate
    List[ReadoutTracePoint],  # blink_inhibition
    List[ReadoutTracePoint],  # reward_proxy
    List[ReadoutTracePoint],  # valence_proxy
    List[ReadoutTracePoint],  # arousal_proxy
    List[ReadoutTracePoint],  # novelty_proxy
    List[ReadoutTracePoint],  # tracking_confidence
    Dict[str, List[ReadoutTracePoint]],  # au_points_by_name
]:
    """Build all trace-point lists from aggregated bucket rows.

    Returns a 10-tuple of the trace-point lists in the order listed above.
    """
    attention_score_points: List[ReadoutTracePoint] = []
    attention_velocity_points: List[ReadoutTracePoint] = []
    blink_rate_points: List[ReadoutTracePoint] = []
    blink_inhibition_points: List[ReadoutTracePoint] = []
    reward_proxy_points: List[ReadoutTracePoint] = []
    valence_proxy_points: List[ReadoutTracePoint] = []
    arousal_proxy_points: List[ReadoutTracePoint] = []
    novelty_proxy_points: List[ReadoutTracePoint] = []
    tracking_confidence_points: List[ReadoutTracePoint] = []
    au_points_by_name: Dict[str, List[ReadoutTracePoint]] = {key: [] for key in AU_DEFAULTS}

    for row in bucket_rows:
        bucket_start = int(row["bucket_start"])
        scene_id = row["scene_id"]
        cut_id = row["cut_id"]
        cta_id = row["cta_id"]

        attention_score_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["attention_score"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        attention_velocity_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["attention_velocity"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        blink_rate_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["blink_rate"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        blink_inhibition_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["blink_inhibition"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        reward_proxy_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["reward_proxy"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        valence_proxy_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["valence_proxy"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        arousal_proxy_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["arousal_proxy"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        novelty_proxy_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=float(row["novelty_proxy"]),
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        tracking_confidence_points.append(
            ReadoutTracePoint(video_time_ms=bucket_start, value=row["tracking_confidence"],
                              scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
        )
        au_norm_values: Dict[str, float] = row["au_norm"]  # type: ignore[assignment]
        for au_name in AU_DEFAULTS:
            au_points_by_name[au_name].append(
                ReadoutTracePoint(video_time_ms=bucket_start,
                                  value=float(au_norm_values.get(au_name, 0.0)),
                                  scene_id=scene_id, cut_id=cut_id, cta_id=cta_id)  # type: ignore[arg-type]
            )

    return (
        attention_score_points,
        attention_velocity_points,
        blink_rate_points,
        blink_inhibition_points,
        reward_proxy_points,
        valence_proxy_points,
        arousal_proxy_points,
        novelty_proxy_points,
        tracking_confidence_points,
        au_points_by_name,
    )


# ---------------------------------------------------------------------------
# Aggregate diagnostic score orchestration
# ---------------------------------------------------------------------------

def build_all_aggregate_diagnostics(
    *,
    db,
    video,
    bucket_rows: List[Dict[str, object]],
    session_bucket_rows_by_session: Dict[UUID, Dict[int, Dict[str, object]]],
    session_weight_by_session: Dict[UUID, float],
    scene_graph: SceneGraphContext,
    window_ms: int,
    attention_synchrony: Optional[float],
    blink_synchrony: Optional[float],
    grip_control_score: Optional[float],
    attentional_synchrony_diagnostics: Optional[AttentionalSynchronyDiagnostics],
    selected_annotations: list,
    selected_survey_responses: list,
) -> Tuple[
    Optional[NarrativeControlDiagnostics],
    Optional[BlinkTransportDiagnostics],
    Optional[RewardAnticipationDiagnostics],
    Optional[BoundaryEncodingDiagnostics],
    Optional[AuFrictionDiagnostics],
    Optional[CtaReceptionDiagnostics],
    Optional[SocialTransmissionDiagnostics],
    Optional[SelfRelevanceDiagnostics],
    Optional[SyntheticLiftPriorDiagnostics],
]:
    """Compute all aggregate diagnostic scores.

    Returns a 9-tuple of diagnostic objects in the order:
    (narrative_control, blink_transport, reward_anticipation, boundary_encoding,
     au_friction, cta_reception, social_transmission, self_relevance, synthetic_lift_prior)
    """
    video_metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}

    # Timeline feature store
    timeline_segments = []
    timeline_feature_tracks = []
    inferred_timeline_end_ms = (
        int(video.duration_ms)
        if video.duration_ms is not None
        else (
            max((int(row["bucket_start"]) for row in bucket_rows), default=0)
            + max(window_ms, 1)
        )
    )
    try:
        timeline_window = query_timeline_features_window(
            db,
            asset_id=_resolve_timeline_asset_id(video),
            start_ms=0,
            end_ms=max(inferred_timeline_end_ms, 1),
            analysis_version=DEFAULT_TIMELINE_ANALYSIS_VERSION,
        )
        timeline_segments = list(timeline_window.segments)
        timeline_feature_tracks = list(timeline_window.feature_tracks)
    except (DomainError, HTTPException):
        # HTTPException(404) is raised by timeline_feature_store when no
        # completed analysis exists for this asset.  Gracefully degrade to
        # empty timeline data instead of crashing the entire readout.
        timeline_segments = []
        timeline_feature_tracks = []
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Timeline features query failed: %s", exc, exc_info=True)
        timeline_segments = []
        timeline_feature_tracks = []

    annotation_rows_for_diagnostics = [
        {
            "marker_type": annotation.marker_type,
            "video_time_ms": annotation.video_time_ms,
            "note": annotation.note,
            "scene_id": annotation.scene_id,
            "cut_id": annotation.cut_id,
            "cta_id": annotation.cta_id,
        }
        for annotation in selected_annotations
    ]
    survey_rows_for_diagnostics = [
        {
            "question_key": response.question_key,
            "response_number": response.response_number,
            "response_text": response.response_text,
        }
        for response in selected_survey_responses
    ]

    blink_transport = compute_blink_transport_diagnostics(
        bucket_rows=bucket_rows,
        session_bucket_rows_by_session=session_bucket_rows_by_session,
        cta_markers=scene_graph.cta_markers,
        timeline_segments=timeline_segments,
        window_ms=window_ms,
        config=resolve_blink_transport_config(video_metadata),
    )
    reward_anticipation = compute_reward_anticipation_diagnostics(
        bucket_rows=bucket_rows,
        cta_markers=scene_graph.cta_markers,
        timeline_segments=timeline_segments,
        timeline_feature_tracks=timeline_feature_tracks,
        window_ms=window_ms,
        config=resolve_reward_anticipation_config(video_metadata),
    )
    narrative_control = compute_narrative_control_diagnostics(
        scenes=scene_graph.scenes,
        cuts=scene_graph.cuts,
        cta_markers=scene_graph.cta_markers,
        bucket_rows=bucket_rows,
        window_ms=window_ms,
        timeline_segments=timeline_segments,
        timeline_feature_tracks=timeline_feature_tracks,
        config=resolve_narrative_control_config(video_metadata),
    )
    boundary_encoding = compute_boundary_encoding_diagnostics(
        scenes=scene_graph.scenes,
        cuts=scene_graph.cuts,
        cta_markers=scene_graph.cta_markers,
        bucket_rows=bucket_rows,
        timeline_segments=timeline_segments,
        timeline_feature_tracks=timeline_feature_tracks,
        window_ms=window_ms,
        config=resolve_boundary_encoding_config(video_metadata),
    )
    social_transmission = compute_social_transmission_diagnostics(
        bucket_rows=bucket_rows,
        annotation_rows=annotation_rows_for_diagnostics,
        timeline_segments=timeline_segments,
        timeline_feature_tracks=timeline_feature_tracks,
        window_ms=window_ms,
        config=resolve_social_transmission_config(video_metadata),
    )
    self_relevance = compute_self_relevance_diagnostics(
        bucket_rows=bucket_rows,
        survey_rows=survey_rows_for_diagnostics,
        timeline_segments=timeline_segments,
        cta_markers=scene_graph.cta_markers,
        video_metadata=video_metadata,
        window_ms=window_ms,
        config=resolve_self_relevance_config(video_metadata),
    )
    cta_reception = compute_cta_reception_diagnostics(
        bucket_rows=bucket_rows,
        cta_markers=scene_graph.cta_markers,
        attentional_synchrony=attentional_synchrony_diagnostics,
        narrative_control=narrative_control,
        blink_transport=blink_transport,
        reward_anticipation=reward_anticipation,
        boundary_encoding=boundary_encoding,
        window_ms=window_ms,
        config=resolve_cta_reception_config(video_metadata),
    )
    au_friction = compute_au_friction_diagnostics(
        bucket_rows=bucket_rows,
        window_ms=window_ms,
        config=resolve_au_friction_config(video_metadata),
    )
    synthetic_lift_prior = compute_synthetic_lift_prior_diagnostics(
        bucket_rows=bucket_rows,
        window_ms=window_ms,
        attention_synchrony=attention_synchrony,
        blink_synchrony=blink_synchrony,
        grip_control_score=grip_control_score,
        attentional_synchrony=attentional_synchrony_diagnostics,
        narrative_control=narrative_control,
        blink_transport=blink_transport,
        reward_anticipation=reward_anticipation,
        boundary_encoding=boundary_encoding,
        cta_reception=cta_reception,
        social_transmission=social_transmission,
        self_relevance=self_relevance,
        au_friction=au_friction,
        config=resolve_synthetic_lift_prior_config(video_metadata),
    )

    return (
        narrative_control,
        blink_transport,
        reward_anticipation,
        boundary_encoding,
        au_friction,
        cta_reception,
        social_transmission,
        self_relevance,
        synthetic_lift_prior,
    )


# ---------------------------------------------------------------------------
# Aggregate trace statistics (CI)
# ---------------------------------------------------------------------------

def apply_aggregate_trace_statistics(
    *,
    bucket_rows: List[Dict[str, object]],
    session_bucket_rows_by_session: Dict,
    session_weight_by_session: Dict,
    attention_score_points: List[ReadoutTracePoint],
    attention_velocity_points: List[ReadoutTracePoint],
    blink_rate_points: List[ReadoutTracePoint],
    blink_inhibition_points: List[ReadoutTracePoint],
    reward_proxy_points: List[ReadoutTracePoint],
    valence_proxy_points: List[ReadoutTracePoint],
    arousal_proxy_points: List[ReadoutTracePoint],
    novelty_proxy_points: List[ReadoutTracePoint],
    tracking_confidence_points: List[ReadoutTracePoint],
) -> Dict[str, Dict[int, Dict[str, float]]]:
    """Compute weighted-mean + SEM CI for each metric across sessions.

    Mutates *bucket_rows* and the trace-point lists in-place by patching
    ``value``, ``median``, ``ci_low``, and ``ci_high``.

    Returns the ``aggregate_trace_statistics`` dict for reference.
    """
    from collections import defaultdict

    aggregate_trace_statistics: Dict[str, Dict[int, Dict[str, float]]] = defaultdict(dict)
    metric_fields = [
        "attention_score",
        "attention_velocity",
        "blink_rate",
        "blink_inhibition",
        "reward_proxy",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
        "tracking_confidence",
    ]
    bucket_times = sorted(int(row["bucket_start"]) for row in bucket_rows)
    for metric_field in metric_fields:
        for bucket_time in bucket_times:
            values: List[float] = []
            weights: List[float] = []
            for session_id_value, session_rows in session_bucket_rows_by_session.items():
                session_row = session_rows.get(bucket_time)
                if session_row is None:
                    continue
                metric_value = session_row.get(metric_field)
                if metric_value is None:
                    continue
                session_weight = session_weight_by_session.get(session_id_value, 0.5)
                local_weight_parts = [
                    float(value)
                    for value in [
                        session_row.get("tracking_confidence"),
                        session_row.get("quality_score"),
                    ]
                    if value is not None
                ]
                local_weight = (
                    clamp(mean(local_weight_parts), 0.1, 1.0)
                    if local_weight_parts
                    else 1.0
                )
                weights.append(max(session_weight * local_weight, 0.01))
                values.append(float(metric_value))

            if not values:
                continue

            mean_value = _weighted_mean(values, weights)
            if mean_value is None:
                continue
            ci_low, ci_high = _sem_confidence_interval(values, center=mean_value)
            aggregate_trace_statistics[metric_field][bucket_time] = {
                "value": _clamp_to_metric_domain(metric_field, mean_value) or 0.0,
                "median": _clamp_to_metric_domain(metric_field, _median(values)) or 0.0,
                "ci_low": _clamp_to_metric_domain(metric_field, ci_low) or 0.0,
                "ci_high": _clamp_to_metric_domain(metric_field, ci_high) or 0.0,
            }

    # Patch bucket_rows with aggregated values
    bucket_rows_by_time = {int(row["bucket_start"]): row for row in bucket_rows}
    for metric_field, stats_by_time in aggregate_trace_statistics.items():
        for bucket_time, stat_payload in stats_by_time.items():
            row = bucket_rows_by_time.get(bucket_time)
            if row is not None:
                row[metric_field] = stat_payload["value"]

    # Patch trace-point lists with CI data
    trace_series_by_metric = {
        "attention_score": attention_score_points,
        "attention_velocity": attention_velocity_points,
        "blink_rate": blink_rate_points,
        "blink_inhibition": blink_inhibition_points,
        "reward_proxy": reward_proxy_points,
        "valence_proxy": valence_proxy_points,
        "arousal_proxy": arousal_proxy_points,
        "novelty_proxy": novelty_proxy_points,
        "tracking_confidence": tracking_confidence_points,
    }
    for metric_field, series in trace_series_by_metric.items():
        stats_by_time = aggregate_trace_statistics.get(metric_field, {})
        for point in series:
            stat_payload = stats_by_time.get(int(point.video_time_ms))
            if stat_payload is None:
                continue
            point.value = stat_payload["value"]
            point.median = stat_payload["median"]
            point.ci_low = stat_payload["ci_low"]
            point.ci_high = stat_payload["ci_high"]

    return aggregate_trace_statistics
