"""Ingestion service helpers.

Functions for resolving participants, parsing JSONL trace payloads,
bulk-inserting trace points / survey responses / session annotations /
playback events, and validating study-video linkage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence
from uuid import UUID

from .domain_exceptions import NotFoundError, UnprocessableError, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    Participant,
    Session as SessionModel,
    SessionAnnotation,
    SessionPlaybackEvent,
    Study,
    SurveyResponse,
    TracePoint,
    Video,
)
from .schemas import (
    AU_DEFAULTS,
    ParticipantAttach,
    SessionAnnotationIn,
    SessionPlaybackEventIn,
    SurveyResponseIn,
    TracePointIn,
)
from .services_catalog import _build_scene_graph_context, _resolve_scene_alignment


# ---------------------------------------------------------------------------
# AU normalisation (local helper)
# ---------------------------------------------------------------------------

def _normalize_au_payload(raw: Optional[Dict[str, float]]) -> Dict[str, float]:
    base = dict(AU_DEFAULTS)
    if not raw:
        return base
    for key in base:
        if key in raw:
            base[key] = float(raw[key])
    return base


# ---------------------------------------------------------------------------
# Participant resolution
# ---------------------------------------------------------------------------

def resolve_participant(db: Session, study_id: UUID, attach: ParticipantAttach) -> Participant:
    """Resolve participant for session creation (attach existing or create new)."""

    if attach.id is not None:
        participant = db.get(Participant, attach.id)
        if participant is None:
            raise NotFoundError("Participant")
        if participant.study_id != study_id:
            raise ValidationError("Participant does not belong to study")
        return participant

    if attach.external_id:
        participant = db.scalar(
            select(Participant).where(
                Participant.study_id == study_id,
                Participant.external_id == attach.external_id,
            )
        )
        if participant is not None:
            return participant

    participant = Participant(
        study_id=study_id,
        external_id=attach.external_id,
        demographics=attach.demographics,
    )
    db.add(participant)
    db.flush()
    return participant


# ---------------------------------------------------------------------------
# JSONL trace parsing
# ---------------------------------------------------------------------------

def parse_trace_jsonl(raw_body: bytes) -> tuple[List[TracePointIn], int]:
    """Parse JSONL payload into validated trace points."""

    text = raw_body.decode("utf-8").strip()
    if not text:
        return [], 0

    rows: List[TracePointIn] = []
    flagged_missing_video_time_ms = 0
    strict_canonical = bool(get_settings().strict_canonical_trace_fields)
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSONL at line {line_number}: {exc.msg}") from exc

        if isinstance(payload, dict) and strict_canonical:
            rejected_aliases: List[str] = []
            reward_aliases = [
                alias
                for alias in ("dopamine", "dopamine_score", "dopamineScore")
                if payload.get(alias) is not None
            ]
            if payload.get("reward_proxy") is None and reward_aliases:
                rejected_aliases.extend(reward_aliases)
            if payload.get("video_time_ms") is None and payload.get("t_ms") is not None:
                rejected_aliases.append("t_ms")

            if rejected_aliases:
                raise UnprocessableError({
                        "message": (
                            "Strict canonical trace mode rejected deprecated alias-only fields "
                            f"at line {line_number}."
                        ),
                        "line_number": line_number,
                        "strict_canonical_trace_fields": True,
                        "rejected_aliases": rejected_aliases,
                        "required_canonical_fields": [
                            "reward_proxy",
                            "video_time_ms",
                        ],
                    })

        # Backward compatibility: accept legacy dopamine-style keys and map them
        # into calibrated `reward_proxy` when reward_proxy is absent.
        if (
            isinstance(payload, dict)
            and "reward_proxy" not in payload
            and ("dopamine" in payload or "dopamine_score" in payload or "dopamineScore" in payload)
        ):
            payload["reward_proxy"] = (
                payload.get("dopamine")
                if payload.get("dopamine") is not None
                else (
                    payload.get("dopamine_score")
                    if payload.get("dopamine_score") is not None
                    else payload.get("dopamineScore")
                )
            )

        if isinstance(payload, dict) and payload.get("video_time_ms") is None:
            if payload.get("t_ms") is None:
                raise UnprocessableError(f"Invalid trace row at line {line_number}: video_time_ms is required")
            flagged_missing_video_time_ms += 1

        try:
            rows.append(TracePointIn.model_validate(payload))
        except Exception as exc:
            raise UnprocessableError(f"Invalid trace row at line {line_number}: {exc}") from exc

    return rows, flagged_missing_video_time_ms


# ---------------------------------------------------------------------------
# Trace source helpers
# ---------------------------------------------------------------------------

_TRACE_SOURCE_VALUES = {"provided", "synthetic_fallback"}


def _extract_trace_source_from_playback_event(event: SessionPlaybackEvent) -> Optional[str]:
    event_type = (event.event_type or "").strip().lower()
    if event_type != "trace_source":
        return None
    details = event.details if isinstance(event.details, dict) else {}
    candidate = details.get("trace_source")
    if not isinstance(candidate, str):
        candidate = details.get("traceSource")
    if not isinstance(candidate, str):
        return None
    normalized = candidate.strip().lower()
    if normalized in _TRACE_SOURCE_VALUES:
        return normalized
    return None


def _resolve_trace_source_summary(
    playback_events: Sequence[SessionPlaybackEvent],
    session_ids: Sequence[UUID],
) -> str:
    if not session_ids:
        return "unknown"

    source_by_session: Dict[UUID, str] = {}
    for event in playback_events:
        source = _extract_trace_source_from_playback_event(event)
        if source is None:
            continue
        source_by_session[event.session_id] = source

    if not source_by_session:
        return "unknown"

    unique_sources = set(source_by_session.values())
    if len(unique_sources) == 1 and len(source_by_session) == len(set(session_ids)):
        return next(iter(unique_sources))
    return "mixed"


# ---------------------------------------------------------------------------
# Bulk insert helpers
# ---------------------------------------------------------------------------

def bulk_insert_trace_points(
    db: Session,
    session_model: SessionModel,
    rows: Iterable[TracePointIn],
) -> int:
    """Bulk insert trace points for a session."""

    video = db.get(Video, session_model.video_id)
    if video is None:
        raise NotFoundError("Video", "Video not found for session")
    scene_graph = _build_scene_graph_context(video)

    objects: List[TracePoint] = []
    for row in rows:
        video_time_ms = int(row.video_time_ms if row.video_time_ms is not None else row.t_ms or 0)
        scene_id = row.scene_id
        cut_id = row.cut_id
        cta_id = row.cta_id
        if scene_id is None and cut_id is None and cta_id is None:
            derived_scene_id, derived_cut_id, derived_cta_id = _resolve_scene_alignment(
                scene_graph,
                video_time_ms,
            )
            scene_id = derived_scene_id
            cut_id = derived_cut_id
            cta_id = derived_cta_id

        objects.append(
            TracePoint(
                session_id=session_model.id,
                t_ms=int(row.t_ms if row.t_ms is not None else video_time_ms),
                video_time_ms=video_time_ms,
                scene_id=scene_id,
                cut_id=cut_id,
                cta_id=cta_id,
                face_ok=row.face_ok,
                face_presence_confidence=row.face_presence_confidence,
                brightness=float(row.brightness),
                blur=row.blur,
                landmarks_ok=row.landmarks_ok,
                landmarks_confidence=row.landmarks_confidence,
                eye_openness=row.eye_openness,
                blink=row.blink,
                blink_confidence=row.blink_confidence,
                rolling_blink_rate=row.rolling_blink_rate,
                blink_inhibition_score=row.blink_inhibition_score,
                blink_inhibition_active=row.blink_inhibition_active,
                blink_baseline_rate=row.blink_baseline_rate,
                dial=row.dial,
                reward_proxy=row.reward_proxy,
                au=_normalize_au_payload(row.au),
                au_norm=_normalize_au_payload(row.au_norm),
                au_confidence=row.au_confidence,
                head_pose={
                    "yaw": row.head_pose.get("yaw"),
                    "pitch": row.head_pose.get("pitch"),
                    "roll": row.head_pose.get("roll"),
                },
                head_pose_confidence=row.head_pose_confidence,
                head_pose_valid_pct=row.head_pose_valid_pct,
                gaze_on_screen_proxy=row.gaze_on_screen_proxy,
                gaze_on_screen_confidence=row.gaze_on_screen_confidence,
                fps=row.fps,
                fps_stability=row.fps_stability,
                face_visible_pct=row.face_visible_pct,
                occlusion_score=row.occlusion_score,
                quality_score=row.quality_score,
                quality_confidence=row.quality_confidence,
                tracking_confidence=row.tracking_confidence,
                quality_flags=list(row.quality_flags) if row.quality_flags else None,
            )
        )

    if objects:
        db.bulk_save_objects(objects)
    return len(objects)


def bulk_insert_survey_responses(
    db: Session,
    session_model: SessionModel,
    responses: Iterable[SurveyResponseIn],
) -> int:
    """Bulk insert survey responses for a session."""

    objects = [
        SurveyResponse(
            session_id=session_model.id,
            question_key=response.question_key,
            response_text=response.response_text,
            response_number=response.response_number,
            response_json=response.response_json,
        )
        for response in responses
    ]
    if objects:
        db.bulk_save_objects(objects)
    return len(objects)


def bulk_insert_session_annotations(
    db: Session,
    session_model: SessionModel,
    annotations: Iterable[SessionAnnotationIn],
) -> int:
    """Bulk insert timeline annotations for a session."""

    video = db.get(Video, session_model.video_id)
    if video is None:
        raise NotFoundError("Video", "Video not found for session")
    scene_graph = _build_scene_graph_context(video)

    objects: List[SessionAnnotation] = []
    for annotation in annotations:
        if annotation.session_id is not None and annotation.session_id != session_model.id:
            raise ValidationError("Annotation session_id does not match target session")
        if annotation.video_id != session_model.video_id:
            raise ValidationError("Annotation video_id does not match target session video")

        scene_id = annotation.scene_id
        cut_id = annotation.cut_id
        cta_id = annotation.cta_id
        if scene_id is None and cut_id is None and cta_id is None:
            derived_scene_id, derived_cut_id, derived_cta_id = _resolve_scene_alignment(
                scene_graph,
                annotation.video_time_ms,
            )
            scene_id = derived_scene_id
            cut_id = derived_cut_id
            cta_id = derived_cta_id

        objects.append(
            SessionAnnotation(
                session_id=session_model.id,
                video_id=session_model.video_id,
                marker_type=annotation.marker_type.value,
                video_time_ms=annotation.video_time_ms,
                scene_id=scene_id,
                cut_id=cut_id,
                cta_id=cta_id,
                note=annotation.note,
                created_at=annotation.created_at or datetime.now(timezone.utc),
            )
        )

    if objects:
        db.bulk_save_objects(objects)
    return len(objects)


def bulk_insert_playback_events(
    db: Session,
    session_model: SessionModel,
    events: Iterable[SessionPlaybackEventIn],
) -> int:
    """Bulk insert passive playback telemetry events for a session."""

    video = db.get(Video, session_model.video_id)
    if video is None:
        raise NotFoundError("Video", "Video not found for session")
    scene_graph = _build_scene_graph_context(video)

    objects: List[SessionPlaybackEvent] = []
    for event in events:
        if event.session_id is not None and event.session_id != session_model.id:
            raise ValidationError("Telemetry session_id does not match target session")
        if event.video_id != session_model.video_id:
            raise ValidationError("Telemetry video_id does not match target session video")

        scene_id = event.scene_id
        cut_id = event.cut_id
        cta_id = event.cta_id
        if scene_id is None and cut_id is None and cta_id is None:
            derived_scene_id, derived_cut_id, derived_cta_id = _resolve_scene_alignment(
                scene_graph,
                event.video_time_ms,
            )
            scene_id = derived_scene_id
            cut_id = derived_cut_id
            cta_id = derived_cta_id

        objects.append(
            SessionPlaybackEvent(
                session_id=session_model.id,
                video_id=session_model.video_id,
                event_type=event.event_type,
                video_time_ms=event.video_time_ms,
                wall_time_ms=event.wall_time_ms,
                client_monotonic_ms=event.client_monotonic_ms,
                details=event.details,
                scene_id=scene_id,
                cut_id=cut_id,
                cta_id=cta_id,
                created_at=event.created_at or datetime.now(timezone.utc),
            )
        )

    if objects:
        db.bulk_save_objects(objects)
    return len(objects)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_study_video_link(study: Optional[Study], video: Optional[Video]) -> None:
    """Validate study/video presence and linkage."""

    if study is None:
        raise NotFoundError("Study")
    if video is None:
        raise NotFoundError("Video")
    if video.study_id != study.id:
        raise ValidationError("Video does not belong to study")
