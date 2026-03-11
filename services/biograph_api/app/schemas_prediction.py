"""Prediction job/response, testing queue, and analyst view schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Predict
# ---------------------------------------------------------------------------


class PredictTracePoint(BaseModel):
    t_sec: float
    reward_proxy: Optional[float] = Field(
        default=None,
        description="Calibrated reward proxy prediction.",
    )
    dopamine_score: Optional[float] = Field(
        default=None,
        description="Deprecated alias for reward_proxy (retained for migration compatibility).",
    )
    attention: Optional[float] = Field(
        default=None,
        description="Compatibility alias for reward proxy / attention proxy trend.",
    )
    blink_inhibition: float
    dial: float
    attention_velocity: Optional[float] = Field(default=None)
    blink_rate: Optional[float] = Field(default=None, ge=0, le=1)
    valence_proxy: Optional[float] = Field(default=None, ge=0, le=100)
    arousal_proxy: Optional[float] = Field(default=None, ge=0, le=100)
    novelty_proxy: Optional[float] = Field(default=None, ge=0, le=100)
    tracking_confidence: Optional[float] = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_proxy_alignment(self):
        if self.reward_proxy is None and self.dopamine_score is not None:
            self.reward_proxy = self.dopamine_score
        if self.reward_proxy is None and self.attention is None:
            raise ValueError("Either reward_proxy or attention must be provided")
        if self.reward_proxy is None:
            self.reward_proxy = self.attention
        if self.attention is None:
            self.attention = self.reward_proxy
        if self.dopamine_score is None:
            self.dopamine_score = self.reward_proxy
        return self


class PredictResponse(BaseModel):
    model_artifact: str
    predictions: List[PredictTracePoint]
    resolved_video_url: Optional[str] = None
    prediction_backend: str = Field(
        description=(
            "Backend used to generate predictions, e.g. `ml_pipeline_artifact` or "
            "`heuristic_fallback_missing_artifact`."
        )
    )
    video_id: Optional[str] = Field(
        default=None,
        description="UUID of the catalog Video record created or found for this prediction.",
    )


class PredictJobStatus(BaseModel):
    job_id: str
    status: str = Field(description="One of: pending, downloading, running, uploading, done, failed")
    stage_label: str = Field(description="Human-readable description of the current stage.")
    result: Optional[PredictResponse] = None
    error: Optional[str] = None


class PredictJobsObservabilityStatus(BaseModel):
    active_jobs: int = Field(ge=0)
    queued_total: int = Field(ge=0)
    completed_total: int = Field(ge=0)
    failed_total: int = Field(ge=0)
    github_upload_attempts: int = Field(ge=0)
    github_upload_successes: int = Field(ge=0)
    github_upload_failures: int = Field(ge=0)
    github_upload_success_rate: Optional[float] = Field(default=None, ge=0, le=1)


# ---------------------------------------------------------------------------
# Testing Queue
# ---------------------------------------------------------------------------


class TestingUncertaintyPoint(BaseModel):
    t_sec: int = Field(ge=0)
    attention: float = Field(description="Attention/reward proxy trend used for prioritization.")
    blink_inhibition: float
    dial: float
    uncertainty: float = Field(ge=0.0)


class TestingQueueSegment(BaseModel):
    start_sec: int = Field(ge=0)
    end_sec: int = Field(gt=0)
    mean_uncertainty: float = Field(ge=0.0)
    hook_weight: float = Field(ge=0.0)
    impact_score: float = Field(ge=0.0)


class TestingQueueItem(BaseModel):
    study_id: UUID
    video_id: UUID
    title: str
    source_url: Optional[str] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    existing_sessions: int = Field(ge=0)
    pending_sessions: int = Field(ge=0)
    mean_uncertainty: float = Field(ge=0.0)
    top_impact_score: float = Field(ge=0.0)
    uncertainty_trace: List[TestingUncertaintyPoint] = Field(default_factory=list)
    recommended_segments: List[TestingQueueSegment] = Field(default_factory=list)


class TestingQueueAssignment(BaseModel):
    study_id: UUID
    video_id: UUID
    start_sec: int = Field(ge=0)
    end_sec: int = Field(gt=0)
    rationale: str


class TestingQueueResponse(BaseModel):
    generated_at: datetime
    queue_size: int = Field(ge=1)
    target_sessions_per_video: int = Field(ge=1)
    items: List[TestingQueueItem] = Field(default_factory=list)
    next_assignment: Optional[TestingQueueAssignment] = None


# ---------------------------------------------------------------------------
# Analyst View
# ---------------------------------------------------------------------------


class AnalystSurveyResponseItem(BaseModel):
    question_key: str
    response_text: Optional[str] = None
    response_number: Optional[float] = None
    response_json: Optional[Dict[str, Any]] = None


class AnalystSessionItem(BaseModel):
    session_id: UUID
    participant_external_id: Optional[str] = None
    participant_demographics: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    ended_at: Optional[datetime] = None
    survey_responses: List[AnalystSurveyResponseItem] = []
    has_capture: bool = False
    capture_frame_count: int = 0
    capture_created_at: Optional[datetime] = None
    trace_point_count: int = 0


class AnalystSessionsResponse(BaseModel):
    video_id: UUID
    video_title: str
    sessions: List[AnalystSessionItem] = []
    total_sessions: int = 0
    last_updated_at: Optional[datetime] = None
