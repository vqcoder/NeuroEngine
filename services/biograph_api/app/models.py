"""SQLAlchemy ORM models for biograph_api."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    videos: Mapped[List["Video"]] = relationship(back_populates="study", cascade="all,delete")
    participants: Mapped[List["Participant"]] = relationship(
        back_populates="study", cascade="all,delete"
    )
    sessions: Mapped[List["Session"]] = relationship(back_populates="study", cascade="all,delete")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    video_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON)
    scene_boundaries: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    study: Mapped[Study] = relationship(back_populates="videos")
    sessions: Mapped[List["Session"]] = relationship(back_populates="video", cascade="all,delete")
    annotations: Mapped[List["SessionAnnotation"]] = relationship(
        back_populates="video", cascade="all,delete"
    )
    playback_events: Mapped[List["SessionPlaybackEvent"]] = relationship(
        back_populates="video", cascade="all,delete"
    )
    capture_archives: Mapped[List["SessionCaptureArchive"]] = relationship(
        back_populates="video", cascade="all,delete"
    )
    scene_graph_scenes: Mapped[List["VideoScene"]] = relationship(
        back_populates="video", cascade="all,delete"
    )
    scene_graph_cuts: Mapped[List["VideoCut"]] = relationship(
        back_populates="video", cascade="all,delete"
    )
    scene_graph_cta_markers: Mapped[List["VideoCtaMarker"]] = relationship(
        back_populates="video", cascade="all,delete"
    )
    timeline_analyses: Mapped[List["VideoTimelineAnalysis"]] = relationship(
        back_populates="video", cascade="all,delete"
    )


class VideoScene(Base):
    __tablename__ = "video_scenes"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "variant_id",
            "scene_id",
            name="uq_video_scenes_video_variant_scene_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    variant_id: Mapped[str] = mapped_column(String(128), default="default")
    scene_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_index: Mapped[int] = mapped_column(Integer, default=0)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1024))
    cut_id: Mapped[Optional[str]] = mapped_column(String(128))
    cta_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    video: Mapped[Video] = relationship(back_populates="scene_graph_scenes")


class VideoCut(Base):
    __tablename__ = "video_cuts"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "variant_id",
            "cut_id",
            name="uq_video_cuts_video_variant_cut_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    variant_id: Mapped[str] = mapped_column(String(128), default="default")
    cut_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_index: Mapped[int] = mapped_column(Integer, default=0)
    video_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_id: Mapped[Optional[str]] = mapped_column(String(128))
    label: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    video: Mapped[Video] = relationship(back_populates="scene_graph_cuts")


class VideoCtaMarker(Base):
    __tablename__ = "video_cta_markers"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "variant_id",
            "cta_id",
            name="uq_video_cta_markers_video_variant_cta_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    variant_id: Mapped[str] = mapped_column(String(128), default="default")
    cta_id: Mapped[str] = mapped_column(String(128), nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    scene_id: Mapped[Optional[str]] = mapped_column(String(128))
    cut_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    video: Mapped[Video] = relationship(back_populates="scene_graph_cta_markers")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("study_id", "external_id", name="uq_participants_study_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"))
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    demographics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    study: Mapped[Study] = relationship(back_populates="participants")
    sessions: Mapped[List["Session"]] = relationship(
        back_populates="participant", cascade="all,delete"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"))
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(50), default="created")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    study: Mapped[Study] = relationship(back_populates="sessions")
    video: Mapped[Video] = relationship(back_populates="sessions")
    participant: Mapped[Participant] = relationship(back_populates="sessions")
    trace_points: Mapped[List["TracePoint"]] = relationship(
        back_populates="session", cascade="all,delete"
    )
    survey_responses: Mapped[List["SurveyResponse"]] = relationship(
        back_populates="session", cascade="all,delete"
    )
    annotations: Mapped[List["SessionAnnotation"]] = relationship(
        back_populates="session", cascade="all,delete"
    )
    playback_events: Mapped[List["SessionPlaybackEvent"]] = relationship(
        back_populates="session", cascade="all,delete"
    )
    capture_archives: Mapped[List["SessionCaptureArchive"]] = relationship(
        back_populates="session", cascade="all,delete"
    )


class TracePoint(Base):
    __tablename__ = "trace_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    t_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    video_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    scene_id: Mapped[Optional[str]] = mapped_column(String(128))
    cut_id: Mapped[Optional[str]] = mapped_column(String(128))
    cta_id: Mapped[Optional[str]] = mapped_column(String(128))
    face_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    face_presence_confidence: Mapped[Optional[float]] = mapped_column(Float)
    brightness: Mapped[float] = mapped_column(Float, nullable=False)
    blur: Mapped[Optional[float]] = mapped_column(Float)
    landmarks_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    landmarks_confidence: Mapped[Optional[float]] = mapped_column(Float)
    eye_openness: Mapped[Optional[float]] = mapped_column(Float)
    blink: Mapped[int] = mapped_column(Integer, nullable=False)
    blink_confidence: Mapped[Optional[float]] = mapped_column(Float)
    rolling_blink_rate: Mapped[Optional[float]] = mapped_column(Float)
    blink_inhibition_score: Mapped[Optional[float]] = mapped_column(Float)
    blink_inhibition_active: Mapped[Optional[bool]] = mapped_column(Boolean)
    blink_baseline_rate: Mapped[Optional[float]] = mapped_column(Float)
    dial: Mapped[Optional[float]] = mapped_column(Float)
    reward_proxy: Mapped[Optional[float]] = mapped_column(Float)
    au: Mapped[Dict[str, float]] = mapped_column(JSON, nullable=False)
    au_norm: Mapped[Dict[str, float]] = mapped_column(JSON, nullable=False)
    au_confidence: Mapped[Optional[float]] = mapped_column(Float)
    head_pose: Mapped[Dict[str, Optional[float]]] = mapped_column(JSON, nullable=False)
    head_pose_confidence: Mapped[Optional[float]] = mapped_column(Float)
    head_pose_valid_pct: Mapped[Optional[float]] = mapped_column(Float)
    gaze_on_screen_proxy: Mapped[Optional[float]] = mapped_column(Float)
    gaze_on_screen_confidence: Mapped[Optional[float]] = mapped_column(Float)
    fps: Mapped[Optional[float]] = mapped_column(Float)
    fps_stability: Mapped[Optional[float]] = mapped_column(Float)
    face_visible_pct: Mapped[Optional[float]] = mapped_column(Float)
    occlusion_score: Mapped[Optional[float]] = mapped_column(Float)
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    quality_confidence: Mapped[Optional[float]] = mapped_column(Float)
    tracking_confidence: Mapped[Optional[float]] = mapped_column(Float)
    pupil_dilation_proxy: Mapped[Optional[float]] = mapped_column(Float)
    pupil_dilation_proxy_raw: Mapped[Optional[float]] = mapped_column(Float)
    pupil_baseline_normalised: Mapped[Optional[float]] = mapped_column(Float)
    quality_flags: Mapped[Optional[List[str]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped[Session] = relationship(back_populates="trace_points")


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    question_key: Mapped[str] = mapped_column(String(255), nullable=False)
    response_text: Mapped[Optional[str]] = mapped_column(Text)
    response_number: Mapped[Optional[float]] = mapped_column(Float)
    response_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped[Session] = relationship(back_populates="survey_responses")


class SessionAnnotation(Base):
    __tablename__ = "session_annotations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    marker_type: Mapped[str] = mapped_column(String(64), nullable=False)
    video_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_id: Mapped[Optional[str]] = mapped_column(String(128))
    cut_id: Mapped[Optional[str]] = mapped_column(String(128))
    cta_id: Mapped[Optional[str]] = mapped_column(String(128))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped[Session] = relationship(back_populates="annotations")
    video: Mapped[Video] = relationship(back_populates="annotations")


class SessionPlaybackEvent(Base):
    __tablename__ = "session_playback_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    video_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    wall_time_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    client_monotonic_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    scene_id: Mapped[Optional[str]] = mapped_column(String(128))
    cut_id: Mapped[Optional[str]] = mapped_column(String(128))
    cta_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped[Session] = relationship(back_populates="playback_events")
    video: Mapped[Video] = relationship(back_populates="playback_events")


class SessionCaptureArchive(Base):
    __tablename__ = "session_capture_archives"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uq_session_capture_archives_session_id",
        ),
        Index(
            "ix_session_capture_archives_video_id_created_at",
            "video_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
    )
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frame_pointer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uncompressed_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compressed_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_gzip: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    encryption_key_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    session: Mapped[Session] = relationship(back_populates="capture_archives")
    video: Mapped[Video] = relationship(back_populates="capture_archives")


class SessionCaptureIngestEvent(Base):
    __tablename__ = "session_capture_ingest_events"
    __table_args__ = (
        Index("ix_session_capture_ingest_events_created_at", "created_at"),
        Index("ix_session_capture_ingest_events_outcome_created_at", "outcome", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    video_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frame_pointer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FrontendDiagnosticEvent(Base):
    __tablename__ = "frontend_diagnostic_events"
    __table_args__ = (
        Index("ix_frontend_diagnostic_events_created_at", "created_at"),
        Index(
            "ix_frontend_diagnostic_events_surface_page_created_at",
            "surface",
            "page",
            "created_at",
        ),
        Index(
            "ix_frontend_diagnostic_events_severity_created_at",
            "severity",
            "created_at",
        ),
        Index(
            "ix_frontend_diagnostic_events_event_type_created_at",
            "event_type",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[str] = mapped_column(String(32), nullable=False)
    route: Mapped[Optional[str]] = mapped_column(String(512))
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="error")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(128))
    message: Mapped[Optional[str]] = mapped_column(Text)
    context_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("context", JSON)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    video_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    study_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IncrementalityExperimentResult(Base):
    __tablename__ = "incrementality_experiment_results"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            name="uq_incrementality_experiment_results_experiment_id",
        ),
        Index(
            "ix_incrementality_experiment_results_pending",
            "calibration_applied_at",
        ),
        Index(
            "ix_incrementality_experiment_results_completed_at",
            "completed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    measured_incremental_lift_pct: Mapped[float] = mapped_column(Float, nullable=False)
    measured_iroas: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_incremental_lift_pct: Mapped[Optional[float]] = mapped_column(Float)
    predicted_iroas: Mapped[Optional[float]] = mapped_column(Float)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    calibration_applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    calibration_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class VideoTimelineAnalysis(Base):
    __tablename__ = "video_timeline_analyses"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "analysis_version",
            "asset_fingerprint",
            name="uq_video_timeline_analyses_video_version_fingerprint",
        ),
        Index("ix_video_timeline_analyses_asset_id", "asset_id"),
        Index("ix_video_timeline_analyses_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(64), nullable=False, default="timeline_v1")
    asset_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    video: Mapped[Video] = relationship(back_populates="timeline_analyses")
    segments: Mapped[List["VideoTimelineSegment"]] = relationship(
        back_populates="analysis", cascade="all,delete"
    )
    feature_tracks: Mapped[List["VideoFeatureTrack"]] = relationship(
        back_populates="analysis", cascade="all,delete"
    )


class VideoTimelineSegment(Base):
    __tablename__ = "video_timeline_segments"
    __table_args__ = (
        Index("ix_video_timeline_segments_asset_window", "asset_id", "start_ms", "end_ms"),
        Index("ix_video_timeline_segments_type", "segment_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_timeline_analyses.id", ondelete="CASCADE")
    )
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    segment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    analysis: Mapped[VideoTimelineAnalysis] = relationship(back_populates="segments")


class VideoFeatureTrack(Base):
    __tablename__ = "video_feature_tracks"
    __table_args__ = (
        Index("ix_video_feature_tracks_asset_window", "asset_id", "start_ms", "end_ms"),
        Index("ix_video_feature_tracks_track_name", "track_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_timeline_analyses.id", ondelete="CASCADE")
    )
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_name: Mapped[str] = mapped_column(String(128), nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    numeric_value: Mapped[Optional[float]] = mapped_column(Float)
    text_value: Mapped[Optional[str]] = mapped_column(String(255))
    unit: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    analysis: Mapped[VideoTimelineAnalysis] = relationship(back_populates="feature_tracks")


class VideoSynchronyCache(Base):
    __tablename__ = "video_synchrony_cache"
    __table_args__ = (
        UniqueConstraint("video_id", "window_ms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    session_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    windows: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
