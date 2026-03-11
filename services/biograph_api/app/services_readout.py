"""Core readout computation service.

The ``build_video_readout`` entry-point orchestrates data loading, bucket
aggregation, trace/segment construction and response assembly.  Domain-
specific sub-computations live in sibling modules:

* ``services_readout_sync``     -- attentional-synchrony diagnostics
* ``services_readout_segments`` -- golden-scene / dead-zone / confusion detection
* ``services_readout_assembly`` -- annotation, survey, quality summaries & diagnostic cards
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .http_client import check_url_reachable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .domain_exceptions import NotFoundError, ValidationError
from .models import (
    Session as SessionModel,
    SessionAnnotation,
    SessionPlaybackEvent,
    SurveyResponse,
    TracePoint,
    Video,
    VideoScene,
)
from .schemas import (
    AttentionalSynchronyDiagnostics,
    AU_DEFAULTS,
    AuFrictionDiagnostics,
    BlinkTransportDiagnostics,
    BoundaryEncodingDiagnostics,
    CtaReceptionDiagnostics,
    NarrativeControlDiagnostics,
    ProductRollupMode,
    ReadoutAUChannel,
    ReadoutAggregateMetrics,
    ReadoutContext,
    ReadoutCtaMarker,
    ReadoutCut,
    ReadoutLabels,
    ReadoutQuality,
    ReadoutReliabilityScore,
    ReadoutScene,
    ReadoutSegment,
    ReadoutSegments,
    ReadoutTimebase,
    ReadoutTracePoint,
    ReadoutTraces,
    ReliabilityScoreDetail,
    RewardAnticipationDiagnostics,
    SelfRelevanceDiagnostics,
    SessionAnnotationRead,
    SessionPlaybackEventRead,
    SocialTransmissionDiagnostics,
    SyntheticLiftPriorDiagnostics,
    VideoReadoutResponse,
)
from .readout_metrics import (
    ReadoutMetricConfig,
    SegmentPoint,
    SessionBlinkSample,
    build_attention_change_segments,
    clamp,
    compute_attention_velocity,
    compute_session_blink_baseline,
    mean,
)
from .services_math import (
    _round_rate,
    _apply_blink_rate_variance_if_flat,
    _apply_reward_proxy_variance_if_flat,
    _first_present,
)
from .services_catalog import (
    _build_scene_graph_context,
    _resolve_scene_alignment,
    _normalize_variant_id,
    SceneGraphContext,
)
## Diagnostic score modules are now called from services_readout_assembly.
from .neuro_score_taxonomy import build_neuro_score_taxonomy
from .neuro_observability import emit_neuro_observability_snapshot
from .product_rollups import build_product_rollup_presentation
from .readout_guardian import enforce_readout_guardian

# Extracted sub-modules
from .services_readout_sync import (
    build_attentional_synchrony_diagnostics,
    compute_pairwise_synchrony,
)
from .services_readout_segments import (
    build_confusion_segments,
    build_dead_zones,
    build_golden_scenes,
    with_segment_context,
)
from .services_readout_buckets import (
    accumulate_points_into_buckets,
    apply_velocity_and_reward_decomposition,
    build_bucket_row,
)
from .services_readout_assembly import (
    apply_aggregate_trace_statistics,
    build_all_aggregate_diagnostics,
    build_annotation_summary,
    build_diagnostics,
    build_quality_summary,
    build_survey_summary,
    build_trace_point_lists,
)

_VIDEO_ASSET_PROXY_PATH = "/api/video-assets/"
_VIDEO_ASSET_PUBLIC_PATH = "/video-assets/"
_VIDEO_HLS_PROXY_PATH = "/api/video/hls-proxy"
_DEFAULT_API_PUBLIC_URL = "https://biograph-api-production.up.railway.app"

DEFAULT_VARIANT_ID = "default"
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named constants for readout heuristic weights (Q7)
# ---------------------------------------------------------------------------
def build_reliability_schema(rel_result) -> ReadoutReliabilityScore:
    """Convert a raw reliability engine result into a ``ReadoutReliabilityScore`` schema.

    This avoids copy-pasting the ``ReadoutReliabilityScore(...)`` construction
    with the ``score_details`` list comprehension in multiple call-sites.
    """
    return ReadoutReliabilityScore(
        overall=rel_result.overall,
        availability_score=rel_result.availability_score,
        range_validity_score=rel_result.range_validity_score,
        pathway_quality_score=rel_result.pathway_quality_score,
        signal_health_score=rel_result.signal_health_score,
        duration_accuracy_score=rel_result.duration_accuracy_score,
        rollup_integrity_score=rel_result.rollup_integrity_score,
        scores_available=rel_result.scores_available,
        scores_total=rel_result.scores_total,
        score_details=[
            ReliabilityScoreDetail(
                machine_name=d.machine_name,
                status=d.status,
                scalar_value=d.scalar_value,
                confidence=d.confidence,
                pathway=d.pathway,
                issues=d.issues,
                score_reliability=d.score_reliability,
            )
            for d in rel_result.score_details
        ],
        issues=rel_result.issues,
    )


def _check_source_url_reachable(source_url: Optional[str]) -> Optional[bool]:
    """HEAD-check source_url with a short timeout. Returns None if URL is absent or not http(s)."""
    return check_url_reachable(source_url)


def _normalize_readout_source_url(source_url: Optional[str]) -> Optional[str]:
    if not source_url:
        return None
    trimmed = source_url.strip()
    if not trimmed:
        return None

    api_public_url = os.getenv("API_PUBLIC_URL", _DEFAULT_API_PUBLIC_URL).rstrip("/")

    if trimmed.startswith(_VIDEO_ASSET_PROXY_PATH):
        remainder = trimmed[len(_VIDEO_ASSET_PROXY_PATH) :].lstrip("/")
        if remainder:
            return f"{api_public_url}/video-assets/{remainder}"
        return None

    if trimmed.startswith(_VIDEO_ASSET_PUBLIC_PATH):
        return f"{api_public_url}{trimmed}"

    if trimmed.startswith(_VIDEO_HLS_PROXY_PATH):
        parsed = urlparse(trimmed)
        proxied = parse_qs(parsed.query).get("url", [])
        if proxied and isinstance(proxied[0], str):
            candidate = proxied[0].strip()
            if candidate:
                return candidate

    return trimmed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _index_score_to_signed_synchrony(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(clamp((float(value) / 50.0) - 1.0, -1.0, 1.0), 6)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_video_readout(
    db: Session,
    video_id: UUID,
    session_id: Optional[UUID] = None,
    variant_id: Optional[str] = None,
    aggregate: bool = True,
    window_ms: int = 1000,
    product_mode: Optional[ProductRollupMode] = None,
    workspace_tier: Optional[str] = None,
) -> VideoReadoutResponse:
    """Build scene-aware readout payload for one session or aggregated viewers."""

    if window_ms <= 0:
        raise ValidationError("windowMs must be greater than 0")
    enforce_readout_guardian()
    config = ReadoutMetricConfig()
    seconds_per_window = max(float(window_ms) / 1000.0, 0.001)

    video = db.get(Video, video_id)
    if video is None:
        raise NotFoundError("Video")

    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    metadata_variant = metadata.get("variant_id") or metadata.get("variantId")
    if variant_id is not None:
        variant_key = _normalize_variant_id(variant_id)
        has_variant_scene_graph = bool(
            db.scalar(
                select(func.count(VideoScene.id)).where(
                    VideoScene.video_id == video.id,
                    VideoScene.variant_id == variant_key,
                )
            )
            or 0
        )
        if (metadata_variant is None or str(metadata_variant) != variant_id) and not has_variant_scene_graph:
            raise NotFoundError("Video variant")

    video_sessions = db.scalars(select(SessionModel).where(SessionModel.video_id == video_id)).all()
    sessions_by_id = {item.id: item for item in video_sessions}

    if session_id is not None:
        selected_session = sessions_by_id.get(session_id)
        if selected_session is None:
            fallback = db.get(SessionModel, session_id)
            if fallback is None or fallback.video_id != video_id:
                raise NotFoundError("Session", "Session not found for video")
            selected_session = fallback
        selected_sessions = [selected_session]
    elif aggregate:
        selected_sessions = video_sessions
    else:
        raise ValidationError("session_id (or sessionId) is required when aggregate=false")

    session_ids = [item.id for item in selected_sessions]

    if session_ids:
        points = db.scalars(
            select(TracePoint)
            .where(TracePoint.session_id.in_(session_ids))
            .order_by(func.coalesce(TracePoint.video_time_ms, TracePoint.t_ms).asc())
        ).all()
        selected_survey_responses = db.scalars(
            select(SurveyResponse)
            .where(SurveyResponse.session_id.in_(session_ids))
            .order_by(SurveyResponse.created_at.asc())
        ).all()
        playback_events = db.scalars(
            select(SessionPlaybackEvent)
            .where(SessionPlaybackEvent.video_id == video_id, SessionPlaybackEvent.session_id.in_(session_ids))
            .order_by(SessionPlaybackEvent.video_time_ms.asc(), SessionPlaybackEvent.created_at.asc())
        ).all()
        selected_annotations = db.scalars(
            select(SessionAnnotation)
            .where(SessionAnnotation.video_id == video_id, SessionAnnotation.session_id.in_(session_ids))
            .order_by(SessionAnnotation.video_time_ms.asc(), SessionAnnotation.created_at.asc())
        ).all()
    else:
        points = []
        selected_survey_responses = []
        playback_events = []
        selected_annotations = []

    scene_graph = _build_scene_graph_context(
        video,
        variant_id=variant_id or (str(metadata_variant) if metadata_variant is not None else None),
    )
    scenes: List[ReadoutScene] = list(scene_graph.scenes)
    cuts: List[ReadoutCut] = list(scene_graph.cuts)
    cta_markers: List[ReadoutCtaMarker] = list(scene_graph.cta_markers)

    # -----------------------------------------------------------------------
    # Blink baseline computation
    # -----------------------------------------------------------------------
    blink_samples_by_session: Dict[UUID, List[SessionBlinkSample]] = defaultdict(list)
    for point in points:
        point_video_time_ms = int(point.video_time_ms if point.video_time_ms is not None else point.t_ms)
        blink_samples_by_session[point.session_id].append(
            SessionBlinkSample(
                video_time_ms=point_video_time_ms,
                blink=int(point.blink),
                rolling_blink_rate=point.rolling_blink_rate,
                blink_baseline_rate=point.blink_baseline_rate,
            )
        )
    blink_baseline_by_session = {
        sid: compute_session_blink_baseline(samples, config)
        for sid, samples in blink_samples_by_session.items()
    }
    global_blink_baseline = (
        mean(list(blink_baseline_by_session.values()))
        if blink_baseline_by_session
        else max(1.0 / seconds_per_window, 0.1)
    )

    # -----------------------------------------------------------------------
    # Label / playback-penalty signal indexing
    # -----------------------------------------------------------------------
    label_weight_by_type = {
        "engaging_moment": 1.0,
        "cta_landed_moment": 0.8,
        "confusing_moment": -0.75,
        "stop_watching_moment": -1.0,
    }
    label_signal_by_bucket: Dict[int, float] = defaultdict(float)
    label_signal_by_session_bucket: Dict[UUID, Dict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for annotation in selected_annotations:
        bucket_start = (int(annotation.video_time_ms) // window_ms) * window_ms
        label_weight = label_weight_by_type.get(annotation.marker_type, 0.0)
        label_signal_by_bucket[bucket_start] += label_weight
        if annotation.session_id is not None:
            label_signal_by_session_bucket[annotation.session_id][bucket_start] += label_weight

    playback_penalty_by_bucket: Dict[int, float] = defaultdict(float)
    playback_penalty_by_session_bucket: Dict[UUID, Dict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    interrupt_event_weight = {
        "pause": 1.0,
        "seek_start": 0.8,
        "seek_end": 1.1,
        "seek": 1.1,
        "rewind": 1.2,
        "volume_change": 0.2,
        "visibility_hidden": 1.2,
        "hidden": 1.2,
        "blur": 1.0,
        "session_incomplete": 1.8,
        "abandonment": 1.8,
        "abandon": 1.8,
        "incomplete_session": 1.5,
        "mute": 0.4,
    }
    for event in playback_events:
        bucket_start = (int(event.video_time_ms) // window_ms) * window_ms
        event_weight = interrupt_event_weight.get(
            event.event_type.lower(),
            0.0,
        )
        playback_penalty_by_bucket[bucket_start] += event_weight
        playback_penalty_by_session_bucket[event.session_id][bucket_start] += event_weight

    # -----------------------------------------------------------------------
    # Bucket accumulation (delegated to services_readout_buckets)
    # -----------------------------------------------------------------------
    bucket_acc, session_bucket_acc = accumulate_points_into_buckets(
        points=points,
        window_ms=window_ms,
        seconds_per_window=seconds_per_window,
        scene_graph=scene_graph,
        blink_baseline_by_session=blink_baseline_by_session,
        global_blink_baseline=global_blink_baseline,
        config=config,
    )

    # -----------------------------------------------------------------------
    # Per-session row construction
    # -----------------------------------------------------------------------
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
    quality_scores: List[Optional[float]] = []
    bucket_rows: List[Dict[str, object]] = []
    selected_session_count = max(len(selected_sessions), 1)
    session_bucket_rows_by_session: Dict[UUID, Dict[int, Dict[str, object]]] = {}
    session_weight_by_session: Dict[UUID, float] = {}

    for session_item in selected_sessions:
        session_id_value = session_item.id
        session_buckets = session_bucket_acc.get(session_id_value, {})
        if not session_buckets:
            continue

        session_rows: List[Dict[str, object]] = []
        for bucket_start in sorted(session_buckets):
            session_rows.append(
                build_bucket_row(
                    acc=session_buckets[bucket_start],
                    bucket_start=bucket_start,
                    scene_graph=scene_graph,
                    global_blink_baseline=global_blink_baseline,
                    playback_penalty=playback_penalty_by_session_bucket[session_id_value].get(bucket_start, 0.0),
                    label_signal_raw=label_signal_by_session_bucket[session_id_value].get(bucket_start, 0.0),
                    config=config,
                )
            )

        _apply_blink_rate_variance_if_flat(
            session_rows,
            fallback_baseline=global_blink_baseline,
        )

        session_attention_series = [float(row["attention_score"]) for row in session_rows]
        session_velocities = compute_attention_velocity(session_attention_series, window_ms, config)
        apply_velocity_and_reward_decomposition(
            session_rows, session_velocities, global_blink_baseline, config,
        )

        _apply_reward_proxy_variance_if_flat(session_rows)

        session_bucket_rows_by_session[session_id_value] = {
            int(row["bucket_start"]): row for row in session_rows
        }
        session_confidences = [
            float(row["tracking_confidence"])
            for row in session_rows
            if row.get("tracking_confidence") is not None
        ]
        session_quality_scores = [
            float(row["quality_score"])
            for row in session_rows
            if row.get("quality_score") is not None
        ]
        weight_parts = []
        if session_confidences:
            weight_parts.append(mean(session_confidences))
        if session_quality_scores:
            weight_parts.append(mean(session_quality_scores))
        session_weight_by_session[session_id_value] = round(
            clamp(mean(weight_parts) if weight_parts else 0.5, 0.05, 1.0),
            6,
        )

    # -----------------------------------------------------------------------
    # Aggregate bucket rows
    # -----------------------------------------------------------------------
    for bucket_start in sorted(bucket_acc):
        acc = bucket_acc[bucket_start]
        samples = int(acc["samples"])
        row = build_bucket_row(
            acc=acc,
            bucket_start=bucket_start,
            scene_graph=scene_graph,
            global_blink_baseline=global_blink_baseline,
            playback_penalty=playback_penalty_by_bucket.get(bucket_start, 0.0) / float(selected_session_count),
            label_signal_raw=label_signal_by_bucket.get(bucket_start, 0.0),
            config=config,
            fallback_blink_rate=_round_rate(float(acc["blink"]), max(samples, 1)),
        )
        quality_scores.append(row.get("quality_score"))
        quality_flag_counts = acc["quality_flag_counts"]  # type: ignore[assignment]
        row["quality_flags"] = sorted(
            [
                str(flag)
                for flag, count in quality_flag_counts.items()
                if int(count) >= max(1, int(samples * 0.25))
            ]
        )
        bucket_rows.append(row)

    _apply_blink_rate_variance_if_flat(
        bucket_rows,
        fallback_baseline=global_blink_baseline,
    )

    attention_scores = [float(row["attention_score"]) for row in bucket_rows]
    attention_velocities = compute_attention_velocity(attention_scores, window_ms, config)
    apply_velocity_and_reward_decomposition(
        bucket_rows, attention_velocities, global_blink_baseline, config,
    )

    _apply_reward_proxy_variance_if_flat(bucket_rows)

    # -----------------------------------------------------------------------
    # Build trace-point lists (delegated to services_readout_assembly)
    # -----------------------------------------------------------------------
    (
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
    ) = build_trace_point_lists(bucket_rows)

    # -----------------------------------------------------------------------
    # Aggregate trace statistics (CI) -- delegated to services_readout_assembly
    # -----------------------------------------------------------------------
    if aggregate and len(session_bucket_rows_by_session) >= 2:
        apply_aggregate_trace_statistics(
            bucket_rows=bucket_rows,
            session_bucket_rows_by_session=session_bucket_rows_by_session,
            session_weight_by_session=session_weight_by_session,
            attention_score_points=attention_score_points,
            attention_velocity_points=attention_velocity_points,
            blink_rate_points=blink_rate_points,
            blink_inhibition_points=blink_inhibition_points,
            reward_proxy_points=reward_proxy_points,
            valence_proxy_points=valence_proxy_points,
            arousal_proxy_points=arousal_proxy_points,
            novelty_proxy_points=novelty_proxy_points,
            tracking_confidence_points=tracking_confidence_points,
        )

    # -----------------------------------------------------------------------
    # Synchrony + diagnostics (delegated to services_readout_sync)
    # -----------------------------------------------------------------------
    attention_synchrony = compute_pairwise_synchrony(
        "attention_score",
        session_bucket_rows_by_session,
        session_weight_by_session,
    )
    blink_synchrony = compute_pairwise_synchrony(
        "blink_inhibition",
        session_bucket_rows_by_session,
        session_weight_by_session,
    )
    synchrony_components = [
        value
        for value in [attention_synchrony, blink_synchrony]
        if value is not None
    ]
    grip_control_score = (
        round(mean(synchrony_components), 6)
        if synchrony_components
        else None
    )
    downweighted_sessions = sum(
        1 for value in session_weight_by_session.values() if value < 0.55
    )

    attentional_synchrony_diagnostics: Optional[AttentionalSynchronyDiagnostics] = None
    narrative_control_diagnostics: Optional[NarrativeControlDiagnostics] = None
    blink_transport_diagnostics: Optional[BlinkTransportDiagnostics] = None
    reward_anticipation_diagnostics: Optional[RewardAnticipationDiagnostics] = None
    boundary_encoding_diagnostics: Optional[BoundaryEncodingDiagnostics] = None
    au_friction_diagnostics: Optional[AuFrictionDiagnostics] = None
    cta_reception_diagnostics: Optional[CtaReceptionDiagnostics] = None
    social_transmission_diagnostics: Optional[SocialTransmissionDiagnostics] = None
    self_relevance_diagnostics: Optional[SelfRelevanceDiagnostics] = None
    synthetic_lift_prior_diagnostics: Optional[SyntheticLiftPriorDiagnostics] = None
    if aggregate:
        attentional_synchrony_diagnostics, _gaze_synchrony = (
            build_attentional_synchrony_diagnostics(
                session_bucket_rows_by_session=session_bucket_rows_by_session,
                session_weight_by_session=session_weight_by_session,
                bucket_rows=bucket_rows,
                scene_graph=scene_graph,
                window_ms=window_ms,
                attention_synchrony=attention_synchrony,
            )
        )

        (
            narrative_control_diagnostics,
            blink_transport_diagnostics,
            reward_anticipation_diagnostics,
            boundary_encoding_diagnostics,
            au_friction_diagnostics,
            cta_reception_diagnostics,
            social_transmission_diagnostics,
            self_relevance_diagnostics,
            synthetic_lift_prior_diagnostics,
        ) = build_all_aggregate_diagnostics(
            db=db,
            video=video,
            bucket_rows=bucket_rows,
            session_bucket_rows_by_session=session_bucket_rows_by_session,
            session_weight_by_session=session_weight_by_session,
            scene_graph=scene_graph,
            window_ms=window_ms,
            attention_synchrony=attention_synchrony,
            blink_synchrony=blink_synchrony,
            grip_control_score=grip_control_score,
            attentional_synchrony_diagnostics=attentional_synchrony_diagnostics,
            selected_annotations=selected_annotations,
            selected_survey_responses=selected_survey_responses,
        )

    # -----------------------------------------------------------------------
    # Backfill legacy synchrony fields
    # -----------------------------------------------------------------------
    resolved_attention_synchrony = attention_synchrony
    resolved_grip_control_score = grip_control_score
    if aggregate:
        if resolved_attention_synchrony is None:
            resolved_attention_synchrony = _index_score_to_signed_synchrony(
                attentional_synchrony_diagnostics.global_score
                if attentional_synchrony_diagnostics is not None
                else None
            )

        if resolved_grip_control_score is None:
            grip_components = [
                value
                for value in [resolved_attention_synchrony, blink_synchrony]
                if value is not None
            ]
            if grip_components:
                resolved_grip_control_score = round(mean(grip_components), 6)
            else:
                resolved_grip_control_score = _index_score_to_signed_synchrony(
                    narrative_control_diagnostics.global_score
                    if narrative_control_diagnostics is not None
                    else None
                )

    aggregate_metrics = (
        ReadoutAggregateMetrics(
            attention_synchrony=resolved_attention_synchrony,
            blink_synchrony=blink_synchrony,
            grip_control_score=resolved_grip_control_score,
            attentional_synchrony=attentional_synchrony_diagnostics,
            narrative_control=narrative_control_diagnostics,
            blink_transport=blink_transport_diagnostics,
            reward_anticipation=reward_anticipation_diagnostics,
            boundary_encoding=boundary_encoding_diagnostics,
            au_friction=au_friction_diagnostics,
            cta_reception=cta_reception_diagnostics,
            social_transmission=social_transmission_diagnostics,
            self_relevance=self_relevance_diagnostics,
            synthetic_lift_prior=synthetic_lift_prior_diagnostics,
            ci_method="sem_95" if aggregate and len(session_bucket_rows_by_session) >= 2 else None,
            included_sessions=len(session_bucket_rows_by_session),
            downweighted_sessions=downweighted_sessions,
        )
        if aggregate
        else None
    )

    # -----------------------------------------------------------------------
    # Segments (delegated to services_readout_segments)
    # -----------------------------------------------------------------------
    segment_points = [
        SegmentPoint(
            video_time_ms=int(row["bucket_start"]),
            attention_score=float(row["attention_score"]),
            attention_velocity=float(row["attention_velocity"]),
            tracking_confidence=row["tracking_confidence"],  # type: ignore[arg-type]
        )
        for row in bucket_rows
    ]
    gain_payload = build_attention_change_segments(
        segment_points,
        positive=True,
        window_ms=window_ms,
        config=config,
    )
    loss_payload = build_attention_change_segments(
        segment_points,
        positive=False,
        window_ms=window_ms,
        config=config,
    )
    attention_gain_segments = [
        with_segment_context(
            start_ms=int(item["start_video_time_ms"]),
            end_ms=int(item["end_video_time_ms"]),
            metric="attention_gain",
            magnitude=float(item["magnitude"]),
            confidence=float(item["confidence"]),
            reason_codes=list(item["reason_codes"]),  # type: ignore[arg-type]
            scene_graph=scene_graph,
            cta_markers=cta_markers,
            window_ms=window_ms,
            notes="attention_gain_segment",
        )
        for item in gain_payload
    ]
    attention_loss_segments = [
        with_segment_context(
            start_ms=int(item["start_video_time_ms"]),
            end_ms=int(item["end_video_time_ms"]),
            metric="attention_loss",
            magnitude=float(item["magnitude"]),
            confidence=float(item["confidence"]),
            reason_codes=list(item["reason_codes"]),  # type: ignore[arg-type]
            scene_graph=scene_graph,
            cta_markers=cta_markers,
            window_ms=window_ms,
            notes="attention_loss_segment",
        )
        for item in loss_payload
    ]

    golden_scenes = build_golden_scenes(
        attention_score_points=attention_score_points,
        reward_proxy_points=reward_proxy_points,
        tracking_confidence_points=tracking_confidence_points,
        scene_graph=scene_graph,
        cta_markers=cta_markers,
        window_ms=window_ms,
    )

    dead_zones = build_dead_zones(
        attention_score_points=attention_score_points,
        reward_proxy_points=reward_proxy_points,
        attention_velocity_points=attention_velocity_points,
        tracking_confidence_points=tracking_confidence_points,
        scene_graph=scene_graph,
        cta_markers=cta_markers,
        window_ms=window_ms,
        config=config,
    )

    confusion_segments = build_confusion_segments(
        attention_score_points=attention_score_points,
        blink_rate_points=blink_rate_points,
        attention_velocity_points=attention_velocity_points,
        tracking_confidence_points=tracking_confidence_points,
        au_points_au04=au_points_by_name.get("AU04", []),
        scene_graph=scene_graph,
        cta_markers=cta_markers,
        window_ms=window_ms,
        config=config,
        global_blink_baseline=global_blink_baseline,
    )

    # -----------------------------------------------------------------------
    # Assembly (delegated to services_readout_assembly)
    # -----------------------------------------------------------------------
    participants_count = 0
    if session_ids:
        participants_count = int(
            db.scalar(
                select(func.count(func.distinct(SessionModel.participant_id))).where(
                    SessionModel.id.in_(session_ids)
                )
            )
            or 0
        )

    diagnostics = build_diagnostics(
        bucket_rows=bucket_rows,
        scenes=scenes,
        cta_markers=cta_markers,
        attention_gain_segments=attention_gain_segments,
        attention_loss_segments=attention_loss_segments,
        confusion_segments=confusion_segments,
        window_ms=window_ms,
    )

    selected_session_count = max(len(selected_sessions), 1)
    annotation_summary = build_annotation_summary(
        selected_annotations=selected_annotations,
        scene_graph=scene_graph,
        window_ms=window_ms,
        selected_session_count=selected_session_count,
    )
    survey_summary = build_survey_summary(selected_survey_responses)

    session_quality_summary, low_confidence_window_items, quality_badge = build_quality_summary(
        bucket_rows=bucket_rows,
        points=points,
        tracking_confidence_points=tracking_confidence_points,
        quality_scores=quality_scores,
        selected_sessions=selected_sessions,
        session_ids=session_ids,
        playback_events=playback_events,
        participants_count=participants_count,
        window_ms=window_ms,
        video_duration_ms=video.duration_ms,
        attention_score_points=attention_score_points,
        db=db,
    )

    annotation_reads = [
        SessionAnnotationRead.model_validate(annotation)
        for annotation in selected_annotations
    ]
    traces = ReadoutTraces(
        attention_score=attention_score_points,
        attention_velocity=attention_velocity_points,
        blink_rate=blink_rate_points,
        blink_inhibition=blink_inhibition_points,
        reward_proxy=reward_proxy_points,
        valence_proxy=valence_proxy_points,
        arousal_proxy=arousal_proxy_points,
        novelty_proxy=novelty_proxy_points,
        tracking_confidence=tracking_confidence_points,
        au_channels=[
            ReadoutAUChannel(au_name=name, points=channel_points)
            for name, channel_points in au_points_by_name.items()
        ],
    )
    segments = ReadoutSegments(
        attention_gain_segments=attention_gain_segments,
        attention_loss_segments=attention_loss_segments,
        golden_scenes=golden_scenes,
        dead_zones=dead_zones,
        confusion_segments=confusion_segments,
    )
    readout_context = ReadoutContext(
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta_markers,
    )
    readout_labels = ReadoutLabels(
        annotations=annotation_reads,
        survey_summary=survey_summary,
        annotation_summary=annotation_summary,
    )
    readout_quality = ReadoutQuality(
        session_quality_summary=session_quality_summary,
        low_confidence_windows=low_confidence_window_items,
    )

    # -----------------------------------------------------------------------
    # Neuro taxonomy + product rollups
    # -----------------------------------------------------------------------
    neuro_scores = None
    product_rollups = None
    legacy_score_adapters = []
    _MIN_WATCH_MS_FOR_SCORES = 3_000
    _max_trace_video_time_ms = max(
        (int(p.video_time_ms) for p in traces.attention_score if p.video_time_ms is not None),
        default=0,
    )
    _has_sufficient_watch_data = _max_trace_video_time_ms >= _MIN_WATCH_MS_FOR_SCORES
    if get_settings().neuro_score_taxonomy_enabled and _has_sufficient_watch_data:
        try:
            neuro_scores = build_neuro_score_taxonomy(
                traces=traces,
                segments=segments,
                diagnostics=diagnostics,
                labels=readout_labels,
                aggregate_metrics=aggregate_metrics,
                context=readout_context,
                window_ms=window_ms,
                schema_version="1.0.0",
            )
            legacy_score_adapters = list(neuro_scores.legacy_score_adapters)
            product_rollups = build_product_rollup_presentation(
                taxonomy=neuro_scores,
                aggregate_metrics=aggregate_metrics,
                diagnostics=diagnostics,
                segments=list(segments.attention_gain_segments)
                + list(segments.attention_loss_segments)
                + list(segments.golden_scenes)
                + list(segments.dead_zones)
                + list(segments.confusion_segments),
                video_metadata=metadata,
                requested_mode=product_mode,
                requested_workspace_tier=workspace_tier,
            )
        except Exception:
            logger.exception(
                "Neuro taxonomy composition failed; returning compatibility payload only",
                extra={"video_id": str(video_id), "variant_id": variant_id or DEFAULT_VARIANT_ID},
            )
            neuro_scores = None
            product_rollups = None
            legacy_score_adapters = []

    if neuro_scores is not None:
        try:
            emit_neuro_observability_snapshot(
                logger=logger,
                video_id=str(video_id),
                variant_id=variant_id,
                aggregate=aggregate,
                included_sessions=len(selected_sessions) if aggregate else 1,
                taxonomy=neuro_scores,
                aggregate_metrics=aggregate_metrics,
                quality_summary=session_quality_summary,
            )
        except Exception:
            logger.exception(
                "Neuro observability snapshot emission failed",
                extra={"video_id": str(video_id), "variant_id": variant_id or DEFAULT_VARIANT_ID},
            )

    # -----------------------------------------------------------------------
    # Final response construction + reliability scoring
    # -----------------------------------------------------------------------
    normalized_source_url = _normalize_readout_source_url(video.source_url)

    inferred_duration_ms = (
        int(video.duration_ms)
        if video.duration_ms is not None
        else (
            max((item.video_time_ms for item in attention_score_points), default=0)
            + window_ms
        )
    )

    _provisional = VideoReadoutResponse(
        schema_version="1.0.0",
        video_id=video_id,
        source_url=normalized_source_url,
        source_url_reachable=_check_source_url_reachable(normalized_source_url),
        has_sufficient_watch_data=_has_sufficient_watch_data,
        variant_id=variant_id,
        session_id=selected_sessions[0].id if (not aggregate and selected_sessions) else None,
        aggregate=aggregate,
        duration_ms=max(inferred_duration_ms, 0),
        timebase=ReadoutTimebase(window_ms=window_ms, step_ms=window_ms),
        context=readout_context,
        traces=traces,
        segments=segments,
        labels=readout_labels,
        quality=readout_quality,
        aggregate_metrics=aggregate_metrics,
        playback_telemetry=[
            SessionPlaybackEventRead.model_validate(event) for event in playback_events
        ],
        neuro_scores=neuro_scores,
        product_rollups=product_rollups,
        legacy_score_adapters=legacy_score_adapters,
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta_markers,
        diagnostics=diagnostics,
        quality_summary=session_quality_summary,
        annotations=annotation_reads,
        annotation_summary=annotation_summary,
        survey_summary=survey_summary,
    )

    # Compute reliability score from the assembled payload.
    _reliability: Optional[ReadoutReliabilityScore] = None
    try:
        from .reliability_engine import compute_reliability_score as _compute_rel
        _rel = _compute_rel(_provisional)
        _reliability = build_reliability_schema(_rel)
    except Exception:
        logger.exception("Reliability engine failed; continuing without reliability_score")

    _provisional.reliability_score = _reliability
    return _provisional
