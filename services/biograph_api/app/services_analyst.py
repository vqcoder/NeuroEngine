"""Analyst View service – list sessions for a video with survey/capture/trace metadata."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from .domain_exceptions import NotFoundError
from .models import (
    Participant,
    Session,
    SessionCaptureArchive,
    SurveyResponse,
    TracePoint,
    Video,
)
from .schemas import (
    AnalystSessionItem,
    AnalystSessionsResponse,
    AnalystSurveyResponseItem,
)

logger = logging.getLogger(__name__)


def list_analyst_sessions(db: DbSession, video_id: UUID) -> AnalystSessionsResponse:
    """Return all sessions for *video_id* with survey responses, capture metadata,
    and trace-point counts.  Heavy blob columns (payload_gzip) are excluded."""

    # 1. Video lookup -----------------------------------------------------------
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise NotFoundError("Video")

    # 2. Sessions + participant join -------------------------------------------
    sessions = (
        db.query(Session, Participant)
        .join(Participant, Session.participant_id == Participant.id)
        .filter(Session.video_id == video_id)
        .order_by(Session.created_at.desc())
        .all()
    )

    if not sessions:
        return AnalystSessionsResponse(
            video_id=video.id,
            video_title=video.title,
            sessions=[],
            total_sessions=0,
            last_updated_at=None,
        )

    session_ids = [s.id for s, _p in sessions]

    # 3. Batch-fetch survey responses ------------------------------------------
    survey_rows = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.session_id.in_(session_ids))
        .all()
    )
    survey_map: dict[UUID, list[AnalystSurveyResponseItem]] = {}
    for sr in survey_rows:
        survey_map.setdefault(sr.session_id, []).append(
            AnalystSurveyResponseItem(
                question_key=sr.question_key,
                response_text=sr.response_text,
                response_number=sr.response_number,
                response_json=sr.response_json,
            )
        )

    # 4. Batch-fetch capture metadata (exclude payload_gzip) -------------------
    capture_rows = (
        db.query(
            SessionCaptureArchive.session_id,
            SessionCaptureArchive.frame_count,
            SessionCaptureArchive.created_at,
        )
        .filter(SessionCaptureArchive.session_id.in_(session_ids))
        .all()
    )
    capture_map: dict[UUID, tuple[int, object]] = {}
    for row in capture_rows:
        capture_map[row.session_id] = (row.frame_count, row.created_at)

    # 5. Batch-count trace points per session ----------------------------------
    tp_counts = (
        db.query(TracePoint.session_id, func.count(TracePoint.id))
        .filter(TracePoint.session_id.in_(session_ids))
        .group_by(TracePoint.session_id)
        .all()
    )
    tp_map: dict[UUID, int] = {sid: cnt for sid, cnt in tp_counts}

    # 6. Compute last_updated_at -----------------------------------------------
    last_updated_at = max(s.created_at for s, _p in sessions)

    # 7. Assemble response items -----------------------------------------------
    items: list[AnalystSessionItem] = []
    for sess, participant in sessions:
        cap = capture_map.get(sess.id)
        items.append(
            AnalystSessionItem(
                session_id=sess.id,
                participant_external_id=participant.external_id,
                participant_demographics=participant.demographics,
                status=sess.status,
                created_at=sess.created_at,
                ended_at=sess.ended_at,
                survey_responses=survey_map.get(sess.id, []),
                has_capture=cap is not None,
                capture_frame_count=cap[0] if cap else 0,
                capture_created_at=cap[1] if cap else None,
                trace_point_count=tp_map.get(sess.id, 0),
            )
        )

    return AnalystSessionsResponse(
        video_id=video.id,
        video_title=video.title,
        sessions=items,
        total_sessions=len(items),
        last_updated_at=last_updated_at,
    )
