"""Video summary aggregation service.

Provides ``build_video_summary`` which constructs a bucketed summary
payload for a given video, including trace buckets, quality overlays,
scene-level metrics, QC statistics, annotations, survey responses, and
playback telemetry.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain_exceptions import NotFoundError
from .models import (
    Session as SessionModel,
    SessionAnnotation,
    SessionPlaybackEvent,
    SurveyResponse,
    TracePoint,
    Video,
)
from .schemas import (
    AU_DEFAULTS,
    QCStats,
    QualityOverlayBucket,
    SceneMetric,
    SessionAnnotationRead,
    SessionPlaybackEventRead,
    SurveyResponseRead,
    TraceBucket,
    VideoSummaryResponse,
)
from .services_math import (
    _first_present,
    _mean,
    _mean_optional,
    _round_rate,
)
from .services_catalog import (
    _build_scene_graph_context,
    _resolve_scene_alignment,
)


def build_video_summary(db: Session, video_id: UUID, bucket_size_ms: int = 1000) -> VideoSummaryResponse:
    """Build aggregated summary payload for a video."""

    video = db.get(Video, video_id)
    if video is None:
        raise NotFoundError("Video")
    scene_graph = _build_scene_graph_context(video)

    sessions = db.scalars(select(SessionModel).where(SessionModel.video_id == video_id)).all()
    session_ids = [session.id for session in sessions]

    if session_ids:
        points = db.scalars(
            select(TracePoint)
            .where(TracePoint.session_id.in_(session_ids))
            .order_by(func.coalesce(TracePoint.video_time_ms, TracePoint.t_ms).asc())
        ).all()
    else:
        points = []

    bucket_acc: Dict[int, Dict[str, object]] = defaultdict(
        lambda: {
            "samples": 0,
            "brightness": [],
            "blur": [],
            "face_ok": 0,
            "face_presence_confidence": [],
            "landmarks_ok": 0,
            "landmarks_confidence": [],
            "blink": 0,
            "rolling_blink_rate": [],
            "blink_inhibition_score": [],
            "blink_inhibition_active": 0,
            "blink_baseline_rate": [],
            "dial_values": [],
            "reward_proxy_values": [],
            "gaze_on_screen_proxy": [],
            "gaze_on_screen_confidence": [],
            "fps": [],
            "fps_stability": [],
            "face_visible_pct": [],
            "occlusion_score": [],
            "head_pose_valid_pct": [],
            "quality_score": [],
            "quality_confidence": [],
            "scene_ids": [],
            "cut_ids": [],
            "cta_ids": [],
            "au_norm": defaultdict(list),
        }
    )

    for point in points:
        point_video_time_ms = int(point.video_time_ms if point.video_time_ms is not None else point.t_ms)
        bucket_start = (point_video_time_ms // bucket_size_ms) * bucket_size_ms
        acc = bucket_acc[bucket_start]
        acc["samples"] = int(acc["samples"]) + 1

        acc["brightness"].append(float(point.brightness))  # type: ignore[index]
        acc["blur"].append(float(point.blur) if point.blur is not None else 0.0)  # type: ignore[index]
        acc["face_ok"] = int(acc["face_ok"]) + int(bool(point.face_ok))
        acc["landmarks_ok"] = int(acc["landmarks_ok"]) + int(bool(point.landmarks_ok))
        acc["blink"] = int(acc["blink"]) + int(point.blink)
        acc["blink_inhibition_active"] = int(acc["blink_inhibition_active"]) + int(
            bool(point.blink_inhibition_active)
        )

        if point.face_presence_confidence is not None:
            acc["face_presence_confidence"].append(float(point.face_presence_confidence))  # type: ignore[index]
        if point.landmarks_confidence is not None:
            acc["landmarks_confidence"].append(float(point.landmarks_confidence))  # type: ignore[index]
        if point.rolling_blink_rate is not None:
            acc["rolling_blink_rate"].append(float(point.rolling_blink_rate))  # type: ignore[index]
        if point.blink_inhibition_score is not None:
            acc["blink_inhibition_score"].append(float(point.blink_inhibition_score))  # type: ignore[index]
        if point.blink_baseline_rate is not None:
            acc["blink_baseline_rate"].append(float(point.blink_baseline_rate))  # type: ignore[index]
        if point.dial is not None:
            acc["dial_values"].append(float(point.dial))  # type: ignore[index]
        if point.reward_proxy is not None:
            acc["reward_proxy_values"].append(float(point.reward_proxy))  # type: ignore[index]
        if point.gaze_on_screen_proxy is not None:
            acc["gaze_on_screen_proxy"].append(float(point.gaze_on_screen_proxy))  # type: ignore[index]
        if point.gaze_on_screen_confidence is not None:
            acc["gaze_on_screen_confidence"].append(float(point.gaze_on_screen_confidence))  # type: ignore[index]
        if point.fps is not None:
            acc["fps"].append(float(point.fps))  # type: ignore[index]
        if point.fps_stability is not None:
            acc["fps_stability"].append(float(point.fps_stability))  # type: ignore[index]
        if point.face_visible_pct is not None:
            acc["face_visible_pct"].append(float(point.face_visible_pct))  # type: ignore[index]
        if point.occlusion_score is not None:
            acc["occlusion_score"].append(float(point.occlusion_score))  # type: ignore[index]
        if point.head_pose_valid_pct is not None:
            acc["head_pose_valid_pct"].append(float(point.head_pose_valid_pct))  # type: ignore[index]
        if point.quality_score is not None:
            acc["quality_score"].append(float(point.quality_score))  # type: ignore[index]
        if point.quality_confidence is not None:
            acc["quality_confidence"].append(float(point.quality_confidence))  # type: ignore[index]
        if point.scene_id is not None:
            acc["scene_ids"].append(point.scene_id)  # type: ignore[index]
        if point.cut_id is not None:
            acc["cut_ids"].append(point.cut_id)  # type: ignore[index]
        if point.cta_id is not None:
            acc["cta_ids"].append(point.cta_id)  # type: ignore[index]

        au_norm_payload = point.au_norm or point.au or {}
        for key in AU_DEFAULTS:
            value = float(au_norm_payload.get(key, 0.0))
            acc["au_norm"][key].append(value)  # type: ignore[index]

    trace_buckets: List[TraceBucket] = []
    quality_overlays: List[QualityOverlayBucket] = []
    for bucket_start in sorted(bucket_acc):
        acc = bucket_acc[bucket_start]
        samples = int(acc["samples"])
        aligned_scene_id, aligned_cut_id, aligned_cta_id = _resolve_scene_alignment(
            scene_graph,
            bucket_start,
        )
        au_norm_means = {
            key: _mean(acc["au_norm"][key])  # type: ignore[index]
            for key in AU_DEFAULTS
        }

        trace_bucket = TraceBucket(
            bucket_start_ms=bucket_start,
            samples=samples,
            mean_brightness=_mean(acc["brightness"]),  # type: ignore[arg-type]
            mean_blur=_mean(acc["blur"]),  # type: ignore[arg-type]
            face_ok_rate=_round_rate(float(acc["face_ok"]), samples),
            mean_face_presence_confidence=_mean(acc["face_presence_confidence"]),  # type: ignore[arg-type]
            landmarks_ok_rate=_round_rate(float(acc["landmarks_ok"]), samples),
            mean_landmarks_confidence=_mean(acc["landmarks_confidence"]),  # type: ignore[arg-type]
            blink_rate=_round_rate(float(acc["blink"]), samples),
            mean_rolling_blink_rate=_mean(acc["rolling_blink_rate"]),  # type: ignore[arg-type]
            mean_blink_inhibition_score=_mean(acc["blink_inhibition_score"]),  # type: ignore[arg-type]
            blink_inhibition_active_rate=_round_rate(
                float(acc["blink_inhibition_active"]),
                samples,
            ),
            mean_blink_baseline_rate=_mean(acc["blink_baseline_rate"]),  # type: ignore[arg-type]
            mean_dial=(
                _mean(acc["dial_values"])  # type: ignore[arg-type]
                if len(acc["dial_values"]) > 0  # type: ignore[arg-type]
                else None
            ),
            mean_reward_proxy=_mean_optional(acc["reward_proxy_values"]),  # type: ignore[arg-type]
            mean_gaze_on_screen_proxy=_mean_optional(acc["gaze_on_screen_proxy"]),  # type: ignore[arg-type]
            mean_gaze_on_screen_confidence=_mean_optional(
                acc["gaze_on_screen_confidence"]  # type: ignore[arg-type]
            ),
            mean_fps=_mean_optional(acc["fps"]),  # type: ignore[arg-type]
            mean_fps_stability=_mean_optional(acc["fps_stability"]),  # type: ignore[arg-type]
            mean_face_visible_pct=_mean_optional(acc["face_visible_pct"]),  # type: ignore[arg-type]
            mean_occlusion_score=_mean_optional(acc["occlusion_score"]),  # type: ignore[arg-type]
            mean_head_pose_valid_pct=_mean_optional(acc["head_pose_valid_pct"]),  # type: ignore[arg-type]
            mean_quality_score=_mean_optional(acc["quality_score"]),  # type: ignore[arg-type]
            mean_quality_confidence=_mean_optional(acc["quality_confidence"]),  # type: ignore[arg-type]
            scene_id=_first_present(acc["scene_ids"]) or aligned_scene_id,  # type: ignore[arg-type]
            cut_id=_first_present(acc["cut_ids"]) or aligned_cut_id,  # type: ignore[arg-type]
            cta_id=_first_present(acc["cta_ids"]) or aligned_cta_id,  # type: ignore[arg-type]
            mean_au_norm=au_norm_means,
        )
        trace_buckets.append(trace_bucket)

        quality_overlays.append(
            QualityOverlayBucket(
                bucket_start_ms=bucket_start,
                samples=samples,
                mean_brightness=trace_bucket.mean_brightness,
                mean_blur=trace_bucket.mean_blur,
                mean_fps_stability=trace_bucket.mean_fps_stability,
                mean_face_visible_pct=trace_bucket.mean_face_visible_pct,
                mean_occlusion_score=trace_bucket.mean_occlusion_score,
                mean_head_pose_valid_pct=trace_bucket.mean_head_pose_valid_pct,
                mean_quality_score=trace_bucket.mean_quality_score,
                mean_quality_confidence=trace_bucket.mean_quality_confidence,
            )
        )

    scene_metrics: List[SceneMetric] = []
    for idx, scene in enumerate(scene_graph.scenes):
        start_ms = int(scene.start_ms)
        end_ms = int(scene.end_ms)
        scene_points = [
            point
            for point in points
            if start_ms
            <= int(point.video_time_ms if point.video_time_ms is not None else point.t_ms)
            < end_ms
        ]
        samples = len(scene_points)
        scene_metrics.append(
            SceneMetric(
                scene_index=idx,
                scene_id=scene.scene_id,
                cut_id=scene.cut_id,
                cta_id=scene.cta_id,
                label=scene.label if isinstance(scene.label, str) else None,
                start_ms=start_ms,
                end_ms=end_ms,
                samples=samples,
                face_ok_rate=_round_rate(sum(int(p.face_ok) for p in scene_points), samples),
                blink_rate=_round_rate(sum(int(p.blink) for p in scene_points), samples),
                mean_au12=_mean(
                    [
                        float((p.au_norm or p.au or {}).get("AU12", 0.0))
                        for p in scene_points
                    ]
                ),
                mean_reward_proxy=_mean_optional([p.reward_proxy for p in scene_points]),
            )
        )

    participants_count = 0
    if session_ids:
        participants_count = int(
            db.scalar(
                select(func.count(func.distinct(SessionModel.participant_id))).where(
                    SessionModel.video_id == video_id
                )
            )
            or 0
        )

    trace_count_by_session: Dict[UUID, int] = defaultdict(int)
    for point in points:
        trace_count_by_session[point.session_id] += 1
    missing_trace_sessions = sum(1 for s in sessions if trace_count_by_session.get(s.id, 0) == 0)

    total_points = len(points)
    qc_stats = QCStats(
        sessions_count=len(sessions),
        participants_count=participants_count,
        total_trace_points=total_points,
        missing_trace_sessions=missing_trace_sessions,
        face_ok_rate=_round_rate(sum(int(p.face_ok) for p in points), total_points),
        landmarks_ok_rate=_round_rate(sum(int(p.landmarks_ok) for p in points), total_points),
        mean_brightness=_mean([float(p.brightness) for p in points]),
    )

    annotations = db.scalars(
        select(SessionAnnotation)
        .where(SessionAnnotation.video_id == video_id)
        .order_by(SessionAnnotation.video_time_ms.asc(), SessionAnnotation.created_at.asc())
    ).all()

    survey_responses: List[SurveyResponse] = []
    if session_ids:
        survey_responses = db.scalars(
            select(SurveyResponse)
            .where(SurveyResponse.session_id.in_(session_ids))
            .order_by(SurveyResponse.created_at.asc())
        ).all()

    playback_events = db.scalars(
        select(SessionPlaybackEvent)
        .where(SessionPlaybackEvent.video_id == video_id)
        .order_by(SessionPlaybackEvent.video_time_ms.asc(), SessionPlaybackEvent.created_at.asc())
    ).all()

    annotation_reads = [SessionAnnotationRead.model_validate(annotation) for annotation in annotations]
    scene_aligned_summaries = scene_metrics

    return VideoSummaryResponse(
        video_id=video_id,
        trace_buckets=trace_buckets,
        passive_traces=trace_buckets,
        quality_overlays=quality_overlays,
        scene_metrics=scene_metrics,
        scene_aligned_summaries=scene_aligned_summaries,
        qc_stats=qc_stats,
        annotations=annotation_reads,
        explicit_labels=annotation_reads,
        survey_responses=[SurveyResponseRead.model_validate(item) for item in survey_responses],
        playback_telemetry=[
            SessionPlaybackEventRead.model_validate(event) for event in playback_events
        ],
    )
