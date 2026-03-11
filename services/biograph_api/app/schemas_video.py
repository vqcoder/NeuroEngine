"""Video-related schemas: CRUD, scene graph, catalog, timeline analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .schemas_common import TimeRangeMixin, TimeRangeInclusiveMixin


class SceneBoundary(TimeRangeMixin):
    label: Optional[str] = None
    scene_id: Optional[str] = Field(default=None, max_length=128)
    cut_id: Optional[str] = Field(default=None, max_length=128)
    cta_id: Optional[str] = Field(default=None, max_length=128)


class VideoSceneIn(TimeRangeMixin):
    scene_id: Optional[str] = Field(default=None, max_length=128)
    label: Optional[str] = None
    thumbnail_url: Optional[str] = Field(default=None, max_length=1024)
    cut_id: Optional[str] = Field(default=None, max_length=128)
    cta_id: Optional[str] = Field(default=None, max_length=128)


class VideoCutIn(BaseModel):
    cut_id: Optional[str] = Field(default=None, max_length=128)
    video_time_ms: int = Field(ge=0)
    scene_id: Optional[str] = Field(default=None, max_length=128)
    label: Optional[str] = None


class VideoCtaMarkerIn(TimeRangeMixin):
    cta_id: Optional[str] = Field(default=None, max_length=128)
    label: Optional[str] = None
    scene_id: Optional[str] = Field(default=None, max_length=128)
    cut_id: Optional[str] = Field(default=None, max_length=128)


class VideoSceneRead(BaseModel):
    scene_id: str
    scene_index: int
    start_ms: int
    end_ms: int
    label: Optional[str] = None
    thumbnail_url: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


class VideoCutRead(BaseModel):
    cut_id: str
    video_time_ms: int
    scene_id: Optional[str] = None
    label: Optional[str] = None


class VideoCtaMarkerRead(BaseModel):
    cta_id: str
    start_ms: int
    end_ms: int
    label: Optional[str] = None
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    video_time_ms: int


class VideoCreate(BaseModel):
    study_id: UUID
    title: str = Field(min_length=1, max_length=255)
    source_url: Optional[str] = Field(default=None, max_length=1024)
    duration_ms: Optional[int] = Field(default=None, ge=0)
    variant_id: Optional[str] = Field(default=None, max_length=128)
    metadata: Optional[Dict[str, Any]] = None
    scene_boundaries: Optional[List[SceneBoundary]] = None
    scenes: Optional[List[VideoSceneIn]] = None
    cuts: Optional[List[VideoCutIn]] = None
    cta_markers: Optional[List[VideoCtaMarkerIn]] = None


class VideoUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    source_url: Optional[str] = Field(default=None, max_length=1024)
    duration_ms: Optional[int] = Field(default=None, ge=1, description="Video duration in milliseconds.")


class VideoRead(BaseModel):
    id: UUID
    study_id: UUID
    title: str
    source_url: Optional[str]
    duration_ms: Optional[int]
    variant_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    scene_boundaries: Optional[List[SceneBoundary]] = None
    scenes: List[VideoSceneRead] = Field(default_factory=list)
    cuts: List[VideoCutRead] = Field(default_factory=list)
    cta_markers: List[VideoCtaMarkerRead] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoCatalogSession(BaseModel):
    id: UUID
    participant_id: UUID
    participant_external_id: Optional[str] = None
    participant_demographics: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime


class VideoCatalogItem(BaseModel):
    video_id: UUID
    study_id: UUID
    study_name: str
    title: str
    source_url: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime
    sessions_count: int = Field(ge=0)
    completed_sessions_count: int = Field(ge=0)
    abandoned_sessions_count: int = Field(ge=0, default=0)
    participants_count: int = Field(ge=0)
    last_session_id: Optional[UUID] = None
    last_session_at: Optional[datetime] = None
    last_session_status: Optional[str] = None
    latest_trace_at: Optional[datetime] = None
    recent_sessions: List[VideoCatalogSession] = Field(default_factory=list)


class VideoCatalogResponse(BaseModel):
    items: List[VideoCatalogItem] = Field(default_factory=list)


class VideoSceneGraphResponse(BaseModel):
    video_id: UUID
    variant_id: str
    scenes: List[VideoSceneRead] = Field(default_factory=list)
    cuts: List[VideoCutRead] = Field(default_factory=list)
    cta_markers: List[VideoCtaMarkerRead] = Field(default_factory=list)


class VideoCtaMarkersUpdateRequest(BaseModel):
    cta_markers: List[VideoCtaMarkerIn] = Field(default_factory=list)


class VideoCtaMarkersResponse(BaseModel):
    video_id: UUID
    variant_id: str
    cta_markers: List[VideoCtaMarkerRead] = Field(default_factory=list)


class TimelineAnalysisRequest(BaseModel):
    source_ref: Optional[str] = Field(
        default=None,
        description="Optional local path or http(s) URL for the source asset.",
    )
    analysis_version: str = Field(default="timeline_v1", min_length=1, max_length=64)
    force_recompute: bool = Field(default=False)
    run_async: bool = Field(
        default=False,
        description="If true, analysis runs in background and returns initial job state.",
    )
    sample_interval_ms: int = Field(default=1000, ge=100, le=10000)
    scene_threshold: float = Field(default=0.35, gt=0.0, lt=1.0)


class TimelineSegmentRead(TimeRangeInclusiveMixin):
    id: int
    segment_type: str = Field(min_length=1, max_length=64)
    label: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    details: Optional[Dict[str, Any]] = None


class FeatureTrackRead(TimeRangeInclusiveMixin):
    id: int
    track_name: str = Field(min_length=1, max_length=128)
    numeric_value: Optional[float] = None
    text_value: Optional[str] = None
    unit: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class TimelineAnalysisJobResponse(BaseModel):
    analysis_id: UUID
    video_id: UUID
    asset_id: str
    analysis_version: str
    asset_fingerprint: str
    status: str
    reused_existing: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TimelineFeatureWindowResponse(BaseModel):
    analysis_id: UUID
    video_id: UUID
    asset_id: str
    analysis_version: str
    window_start_ms: int = Field(ge=0)
    window_end_ms: int = Field(gt=0)
    generated_at: datetime
    segments: List[TimelineSegmentRead] = Field(default_factory=list)
    feature_tracks: List[FeatureTrackRead] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
