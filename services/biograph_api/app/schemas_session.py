"""Session, trace, annotation, survey, playback, capture, and study schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .schemas_common import AU_DEFAULTS


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------


class StudyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None


class StudyRead(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Participant / Session
# ---------------------------------------------------------------------------


class ParticipantAttach(BaseModel):
    id: Optional[UUID] = None
    external_id: Optional[str] = Field(default=None, max_length=255)
    demographics: Optional[Dict[str, Any]] = None


class SessionCreate(BaseModel):
    study_id: UUID
    video_id: UUID
    participant: ParticipantAttach
    status: str = Field(default="created", max_length=50)


class SessionRead(BaseModel):
    id: UUID
    study_id: UUID
    video_id: UUID
    participant_id: UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


class TracePointIn(BaseModel):
    t_ms: Optional[int] = Field(default=None, ge=0)
    video_time_ms: Optional[int] = Field(default=None, ge=0)
    scene_id: Optional[str] = Field(default=None, max_length=128)
    cut_id: Optional[str] = Field(default=None, max_length=128)
    cta_id: Optional[str] = Field(default=None, max_length=128)
    face_ok: bool
    face_presence_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    brightness: float
    blur: Optional[float] = Field(default=None, ge=0)
    landmarks_ok: bool
    landmarks_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    eye_openness: Optional[float] = Field(default=None, ge=0, le=1)
    blink: int = Field(ge=0, le=1)
    blink_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    rolling_blink_rate: Optional[float] = Field(default=None, ge=0)
    blink_inhibition_score: Optional[float] = Field(default=None, ge=-1, le=1)
    blink_inhibition_active: Optional[bool] = None
    blink_baseline_rate: Optional[float] = Field(default=None, ge=0)
    dial: Optional[float] = Field(default=None, ge=0, le=100)
    reward_proxy: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Calibrated reward proxy (quality-dependent engagement estimate). "
            "Legacy ingest payloads may still send `dopamine` or `dopamine_score`; these are mapped "
            "to `reward_proxy` server-side."
        ),
    )
    au: Dict[str, float] = Field(default_factory=lambda: dict(AU_DEFAULTS))
    au_norm: Dict[str, float] = Field(default_factory=lambda: dict(AU_DEFAULTS))
    au_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    head_pose: Dict[str, Optional[float]] = Field(
        default_factory=lambda: {"yaw": None, "pitch": None, "roll": None}
    )
    head_pose_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    head_pose_valid_pct: Optional[float] = Field(default=None, ge=0, le=1)
    gaze_on_screen_proxy: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Coarse gaze-on-screen probability proxy from webcam geometry; "
            "not precise fixation or eye-tracking coordinates."
        ),
    )
    gaze_on_screen_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    fps: Optional[float] = Field(default=None, ge=0)
    fps_stability: Optional[float] = Field(default=None, ge=0, le=1)
    face_visible_pct: Optional[float] = Field(default=None, ge=0, le=1)
    occlusion_score: Optional[float] = Field(default=None, ge=0, le=1)
    quality_score: Optional[float] = Field(default=None, ge=0, le=1)
    quality_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    tracking_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    quality_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_time_alignment(self):
        if self.video_time_ms is None and self.t_ms is None:
            raise ValueError("Either video_time_ms or t_ms must be provided")
        if self.video_time_ms is None:
            self.video_time_ms = self.t_ms
        if self.t_ms is None:
            self.t_ms = self.video_time_ms
        return self


class TraceIngestResponse(BaseModel):
    session_id: UUID
    inserted: int
    flagged_missing_video_time_ms: int = 0


class TraceBucket(BaseModel):
    bucket_start_ms: int
    samples: int
    mean_brightness: float
    mean_blur: float
    face_ok_rate: float
    mean_face_presence_confidence: float
    landmarks_ok_rate: float
    mean_landmarks_confidence: float
    blink_rate: float
    mean_rolling_blink_rate: float
    mean_blink_inhibition_score: float
    blink_inhibition_active_rate: float
    mean_blink_baseline_rate: float
    mean_dial: Optional[float]
    mean_reward_proxy: Optional[float]
    mean_gaze_on_screen_proxy: Optional[float]
    mean_gaze_on_screen_confidence: Optional[float]
    mean_fps: Optional[float]
    mean_fps_stability: Optional[float]
    mean_face_visible_pct: Optional[float]
    mean_occlusion_score: Optional[float]
    mean_head_pose_valid_pct: Optional[float]
    mean_quality_score: Optional[float]
    mean_quality_confidence: Optional[float]
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None
    mean_au_norm: Dict[str, float]


class SceneMetric(BaseModel):
    scene_index: int
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None
    label: Optional[str]
    start_ms: int
    end_ms: int
    samples: int
    face_ok_rate: float
    blink_rate: float
    mean_au12: float
    mean_reward_proxy: Optional[float] = None


class QualityOverlayBucket(BaseModel):
    bucket_start_ms: int
    samples: int
    mean_brightness: float
    mean_blur: float
    mean_fps_stability: Optional[float]
    mean_face_visible_pct: Optional[float]
    mean_occlusion_score: Optional[float]
    mean_head_pose_valid_pct: Optional[float]
    mean_quality_score: Optional[float]
    mean_quality_confidence: Optional[float]


class QCStats(BaseModel):
    sessions_count: int
    participants_count: int
    total_trace_points: int
    missing_trace_sessions: int
    face_ok_rate: float
    landmarks_ok_rate: float
    mean_brightness: float


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class AnnotationMarkerType(str, Enum):
    engaging_moment = "engaging_moment"
    confusing_moment = "confusing_moment"
    stop_watching_moment = "stop_watching_moment"
    cta_landed_moment = "cta_landed_moment"


class SessionAnnotationIn(BaseModel):
    session_id: Optional[UUID] = None
    video_id: UUID
    marker_type: AnnotationMarkerType
    video_time_ms: int = Field(ge=0)
    scene_id: Optional[str] = Field(default=None, max_length=128)
    cut_id: Optional[str] = Field(default=None, max_length=128)
    cta_id: Optional[str] = Field(default=None, max_length=128)
    note: Optional[str] = None
    created_at: Optional[datetime] = None


class SessionAnnotationRead(BaseModel):
    id: UUID
    session_id: UUID
    video_id: UUID
    marker_type: AnnotationMarkerType
    video_time_ms: int
    scene_id: Optional[str]
    cut_id: Optional[str]
    cta_id: Optional[str]
    note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionAnnotationIngestRequest(BaseModel):
    annotations: List[SessionAnnotationIn] = Field(default_factory=list)
    annotation_skipped: bool = False


class SessionAnnotationIngestResponse(BaseModel):
    session_id: UUID
    inserted: int
    annotation_skipped: bool


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------


class SurveyResponseRead(BaseModel):
    id: UUID
    session_id: UUID
    question_key: str
    response_text: Optional[str]
    response_number: Optional[float]
    response_json: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class SurveyResponseIn(BaseModel):
    question_key: str = Field(min_length=1, max_length=255)
    response_text: Optional[str] = None
    response_number: Optional[float] = None
    response_json: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_response_payload(self):
        if (
            self.response_json is None
            and self.response_text is None
            and self.response_number is None
        ):
            raise ValueError("At least one response value must be provided")
        return self


class SurveyIngestRequest(BaseModel):
    responses: List[SurveyResponseIn] = Field(default_factory=list)


class SurveyIngestResponse(BaseModel):
    session_id: UUID
    inserted: int


# ---------------------------------------------------------------------------
# Playback Telemetry
# ---------------------------------------------------------------------------


class SessionPlaybackEventIn(BaseModel):
    session_id: Optional[UUID] = None
    video_id: UUID
    event_type: str = Field(min_length=1, max_length=64)
    video_time_ms: int = Field(ge=0)
    wall_time_ms: Optional[int] = Field(default=None, ge=0)
    client_monotonic_ms: Optional[int] = Field(default=None, ge=0)
    details: Optional[Dict[str, Any]] = None
    scene_id: Optional[str] = Field(default=None, max_length=128)
    cut_id: Optional[str] = Field(default=None, max_length=128)
    cta_id: Optional[str] = Field(default=None, max_length=128)
    created_at: Optional[datetime] = None


class SessionPlaybackEventRead(BaseModel):
    id: UUID
    session_id: UUID
    video_id: UUID
    event_type: str
    video_time_ms: int
    wall_time_ms: Optional[int]
    client_monotonic_ms: Optional[int]
    details: Optional[Dict[str, Any]]
    scene_id: Optional[str]
    cut_id: Optional[str]
    cta_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaybackTelemetryIngestRequest(BaseModel):
    events: List[SessionPlaybackEventIn] = Field(default_factory=list)


class PlaybackTelemetryIngestResponse(BaseModel):
    session_id: UUID
    inserted: int


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


class SessionCaptureFrameIn(BaseModel):
    id: UUID
    timestamp_ms: int = Field(ge=0)
    video_time_ms: Optional[int] = Field(default=None, ge=0)
    jpeg_base64: str = Field(min_length=16)


class SessionCaptureFramePointerIn(BaseModel):
    id: UUID
    timestamp_ms: int = Field(ge=0)
    video_time_ms: Optional[int] = Field(default=None, ge=0)
    pointer: str = Field(min_length=1, max_length=1024)


class SessionCaptureIngestRequest(BaseModel):
    video_id: UUID
    frames: List[SessionCaptureFrameIn] = Field(default_factory=list)
    frame_pointers: List[SessionCaptureFramePointerIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_capture_payload(self):
        if not self.frames and not self.frame_pointers:
            raise ValueError("Capture payload must include frames or frame_pointers")
        return self


class SessionCaptureIngestResponse(BaseModel):
    capture_archive_id: UUID
    session_id: UUID
    video_id: UUID
    frame_count: int = Field(ge=0)
    frame_pointer_count: int = Field(ge=0)
    uncompressed_bytes: int = Field(ge=0)
    compressed_bytes: int = Field(ge=0)
    payload_sha256: str = Field(min_length=64, max_length=64)
    encryption_mode: str = Field(min_length=1, max_length=32)
    encryption_key_id: Optional[str] = Field(default=None, max_length=128)
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Video Summary (aggregate of trace/session data)
# ---------------------------------------------------------------------------


class VideoSummaryResponse(BaseModel):
    video_id: UUID
    trace_buckets: List[TraceBucket]
    passive_traces: List[TraceBucket] = Field(default_factory=list)
    quality_overlays: List[QualityOverlayBucket] = Field(default_factory=list)
    scene_metrics: List[SceneMetric]
    scene_aligned_summaries: List[SceneMetric] = Field(default_factory=list)
    qc_stats: QCStats
    annotations: List[SessionAnnotationRead] = Field(default_factory=list)
    explicit_labels: List[SessionAnnotationRead] = Field(default_factory=list)
    survey_responses: List[SurveyResponseRead] = Field(default_factory=list)
    playback_telemetry: List[SessionPlaybackEventRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch session ingest — atomic multi-step upload in a single transaction
# ---------------------------------------------------------------------------


class BatchSessionIngestRequest(BaseModel):
    """Atomic batch ingest: create a session and insert all associated data
    (trace, telemetry, annotations, survey, captures) in a single DB
    transaction.  On any failure the entire transaction rolls back — no
    partial state."""

    study_id: UUID
    video_id: UUID
    participant: ParticipantAttach
    status: str = Field(default="completed", max_length=50)

    # Trace data as JSONL string (one JSON object per line), same format as
    # ``POST /sessions/{id}/trace``.
    trace_jsonl: str = ""

    # Telemetry
    telemetry_events: List[SessionPlaybackEventIn] = Field(default_factory=list)

    # Annotations
    annotations: List[SessionAnnotationIn] = Field(default_factory=list)
    annotation_skipped: bool = False

    # Survey
    survey_responses: List[SurveyResponseIn] = Field(default_factory=list)

    # Captures (optional — skipped if archive is disabled server-side)
    capture_video_id: Optional[UUID] = None  # defaults to video_id if omitted
    capture_frames: List[SessionCaptureFrameIn] = Field(default_factory=list)
    capture_frame_pointers: List[SessionCaptureFramePointerIn] = Field(default_factory=list)


class BatchSessionIngestResponse(BaseModel):
    """Response from the atomic batch ingest endpoint."""

    session_id: UUID
    study_id: UUID
    video_id: UUID
    trace_inserted: int = 0
    trace_flagged_missing_video_time_ms: int = 0
    telemetry_inserted: int = 0
    annotations_inserted: int = 0
    annotation_skipped: bool = False
    survey_inserted: int = 0
    capture_archived: bool = False
    capture_frame_count: int = 0
    capture_pointer_count: int = 0
