"""Readout response, traces, segments, quality, labels, reliability, and export schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .schemas_common import TimeRangeMixin, VideoTimeRangeInclusiveMixin
from .schemas_session import (
    AnnotationMarkerType,
    SessionAnnotationRead,
    SessionPlaybackEventRead,
    SurveyResponseRead,
)
from .schemas_neuro import (
    LegacyScoreAdapter,
    NeuroScoreTaxonomy,
    ProductRollupPresentation,
    ReadoutAggregateMetrics,
    SyntheticLiftCalibrationStatus,
)


# ---------------------------------------------------------------------------
# Readout building blocks
# ---------------------------------------------------------------------------


class ReadoutScene(BaseModel):
    scene_index: int
    start_ms: int
    end_ms: int
    label: Optional[str] = None
    thumbnail_url: Optional[str] = None
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


class ReadoutCut(BaseModel):
    cut_id: str
    start_ms: int
    end_ms: int
    scene_id: Optional[str] = None
    cta_id: Optional[str] = None
    label: Optional[str] = None


class ReadoutCtaMarker(BaseModel):
    cta_id: str
    video_time_ms: int
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    label: Optional[str] = None


class ReadoutTracePoint(BaseModel):
    video_time_ms: int
    value: Optional[float] = None
    median: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


class ReadoutAUChannel(BaseModel):
    au_name: str
    points: List[ReadoutTracePoint] = Field(default_factory=list)


class ReadoutTraces(BaseModel):
    attention_score: List[ReadoutTracePoint] = Field(default_factory=list)
    attention_velocity: List[ReadoutTracePoint] = Field(default_factory=list)
    blink_rate: List[ReadoutTracePoint] = Field(default_factory=list)
    blink_inhibition: List[ReadoutTracePoint] = Field(default_factory=list)
    reward_proxy: List[ReadoutTracePoint] = Field(default_factory=list)
    valence_proxy: List[ReadoutTracePoint] = Field(default_factory=list)
    arousal_proxy: List[ReadoutTracePoint] = Field(default_factory=list)
    novelty_proxy: List[ReadoutTracePoint] = Field(default_factory=list)
    tracking_confidence: List[ReadoutTracePoint] = Field(default_factory=list)
    au_channels: List[ReadoutAUChannel] = Field(default_factory=list)


class ReadoutSegment(BaseModel):
    start_video_time_ms: int
    end_video_time_ms: int
    metric: str
    magnitude: float
    confidence: Optional[float] = None
    reason_codes: List[str] = Field(default_factory=list)
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None
    distance_to_cta_ms: Optional[int] = None
    cta_window: Optional[Literal["pre_cta", "on_cta", "post_cta"]] = None
    # Deprecated compatibility fields for earlier readout drafts.
    score: Optional[float] = None
    notes: Optional[str] = None


class ReadoutSegments(BaseModel):
    attention_gain_segments: List[ReadoutSegment] = Field(default_factory=list)
    attention_loss_segments: List[ReadoutSegment] = Field(default_factory=list)
    golden_scenes: List[ReadoutSegment] = Field(default_factory=list)
    dead_zones: List[ReadoutSegment] = Field(default_factory=list)
    confusion_segments: List[ReadoutSegment] = Field(default_factory=list)


class SceneDiagnosticCard(VideoTimeRangeInclusiveMixin):
    card_type: Literal[
        "golden_scene",
        "hook_strength",
        "cta_receptivity",
        "attention_drop_scene",
        "confusion_scene",
        "recovery_scene",
    ]
    scene_index: Optional[int] = None
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None
    scene_label: Optional[str] = None
    scene_thumbnail_url: Optional[str] = None
    primary_metric: str
    primary_metric_value: float
    why_flagged: str
    confidence: Optional[float] = None
    reason_codes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


class ReadoutQualitySummary(BaseModel):
    sessions_count: int
    participants_count: int
    total_trace_points: int
    face_ok_rate: float
    mean_brightness: float
    mean_tracking_confidence: Optional[float] = None
    mean_quality_score: Optional[float] = None
    low_confidence_windows: int = 0
    usable_seconds: Optional[float] = None
    quality_badge: Optional[Literal["high", "medium", "low"]] = None
    trace_source: Optional[Literal["provided", "synthetic_fallback", "mixed", "unknown"]] = None


class ReadoutLowConfidenceWindow(VideoTimeRangeInclusiveMixin):
    mean_tracking_confidence: Optional[float] = None
    quality_flags: List[str] = Field(default_factory=list)


class ReadoutQuality(BaseModel):
    session_quality_summary: ReadoutQualitySummary
    low_confidence_windows: List[ReadoutLowConfidenceWindow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Markers / Annotations summary
# ---------------------------------------------------------------------------


class MarkerDensityPoint(BaseModel):
    marker_type: AnnotationMarkerType
    video_time_ms: int = Field(ge=0)
    count: int = Field(ge=1)
    density: float = Field(ge=0)
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


class MarkerTimestampSummary(BaseModel):
    video_time_ms: int = Field(ge=0)
    count: int = Field(ge=1)
    density: float = Field(ge=0)
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


class AnnotationSummary(BaseModel):
    total_annotations: int = Field(ge=0)
    engaging_moment_count: int = Field(ge=0)
    confusing_moment_count: int = Field(ge=0)
    stop_watching_moment_count: int = Field(ge=0)
    cta_landed_moment_count: int = Field(ge=0)
    marker_density: List[MarkerDensityPoint] = Field(default_factory=list)
    top_engaging_timestamps: List[MarkerTimestampSummary] = Field(default_factory=list)
    top_confusing_timestamps: List[MarkerTimestampSummary] = Field(default_factory=list)


class SurveySummary(BaseModel):
    responses_count: int = Field(ge=0)
    overall_interest_mean: Optional[float] = None
    recall_comprehension_mean: Optional[float] = None
    desire_to_continue_or_take_action_mean: Optional[float] = None
    comment_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Readout context / timebase / labels
# ---------------------------------------------------------------------------


class ReadoutTimebase(BaseModel):
    window_ms: int = Field(ge=100, le=10000)
    step_ms: int = Field(ge=100, le=10000)


class ReadoutContext(BaseModel):
    scenes: List[ReadoutScene] = Field(default_factory=list)
    cuts: List[ReadoutCut] = Field(default_factory=list)
    cta_markers: List[ReadoutCtaMarker] = Field(default_factory=list)


class ReadoutLabels(BaseModel):
    annotations: List[SessionAnnotationRead] = Field(default_factory=list)
    survey_summary: Optional[SurveySummary] = None
    annotation_summary: Optional[AnnotationSummary] = None


# ---------------------------------------------------------------------------
# Video metadata for readout
# ---------------------------------------------------------------------------


class ReadoutVideoMetadata(BaseModel):
    video_id: UUID
    study_id: UUID
    study_name: Optional[str] = None
    title: str
    source_url: Optional[str] = None
    duration_ms: Optional[int] = None
    variant_id: Optional[str] = None
    aggregate: bool
    session_id: Optional[UUID] = None
    window_ms: int = Field(ge=100, le=10000)
    generated_at: datetime


# ---------------------------------------------------------------------------
# Reward proxy peaks / highlights
# ---------------------------------------------------------------------------


class RewardProxyPeak(BaseModel):
    video_time_ms: int = Field(ge=0)
    reward_proxy: float
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None
    tracking_confidence: Optional[float] = None


class CompactReadoutHighlights(BaseModel):
    top_reward_proxy_peak: Optional[RewardProxyPeak] = None
    top_attention_gain_segment: Optional[ReadoutSegment] = None
    top_attention_loss_segment: Optional[ReadoutSegment] = None
    top_golden_scene: Optional[ReadoutSegment] = None
    top_dead_zone: Optional[ReadoutSegment] = None


# ---------------------------------------------------------------------------
# Export / compact report
# ---------------------------------------------------------------------------


class ReadoutExportJson(BaseModel):
    video_metadata: ReadoutVideoMetadata
    scenes: List[ReadoutScene] = Field(default_factory=list)
    cta_markers: List[ReadoutCtaMarker] = Field(default_factory=list)
    segments: ReadoutSegments
    diagnostics: List[SceneDiagnosticCard] = Field(default_factory=list)
    reward_proxy_peaks: List[RewardProxyPeak] = Field(default_factory=list)
    quality_summary: ReadoutQualitySummary
    annotation_summary: AnnotationSummary
    survey_summary: SurveySummary
    neuro_scores: Optional[NeuroScoreTaxonomy] = None
    product_rollups: Optional[ProductRollupPresentation] = None
    legacy_score_adapters: List[LegacyScoreAdapter] = Field(default_factory=list)


class CompactReadoutReport(BaseModel):
    video_metadata: ReadoutVideoMetadata
    scenes: List[ReadoutScene] = Field(default_factory=list)
    cta_markers: List[ReadoutCtaMarker] = Field(default_factory=list)
    attention_gain_segments: List[ReadoutSegment] = Field(default_factory=list)
    attention_loss_segments: List[ReadoutSegment] = Field(default_factory=list)
    golden_scenes: List[ReadoutSegment] = Field(default_factory=list)
    dead_zones: List[ReadoutSegment] = Field(default_factory=list)
    reward_proxy_peaks: List[RewardProxyPeak] = Field(default_factory=list)
    quality_summary: ReadoutQualitySummary
    annotation_summary: AnnotationSummary
    survey_summary: SurveySummary
    highlights: CompactReadoutHighlights
    neuro_scores: Optional[NeuroScoreTaxonomy] = None
    product_rollups: Optional[ProductRollupPresentation] = None
    legacy_score_adapters: List[LegacyScoreAdapter] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Reliability
# ---------------------------------------------------------------------------


class ReliabilityScoreDetail(BaseModel):
    machine_name: str
    status: str
    scalar_value: Optional[float] = None
    confidence: Optional[float] = None
    pathway: Optional[str] = None
    issues: List[str] = Field(default_factory=list)
    score_reliability: float = 0.0


class ReadoutReliabilityScore(BaseModel):
    """Model output reliability report -- how accurately each score reflects its design intent."""
    overall: float = Field(ge=0, le=100, description="Overall reliability 0-100. 100 = all scores accurate.")
    availability_score: float = Field(ge=0, le=100)
    range_validity_score: float = Field(ge=0, le=100)
    pathway_quality_score: float = Field(ge=0, le=100)
    signal_health_score: float = Field(ge=0, le=100)
    duration_accuracy_score: float = Field(ge=0, le=100)
    rollup_integrity_score: float = Field(ge=0, le=100)
    scores_available: int
    scores_total: int
    score_details: List[ReliabilityScoreDetail] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    model_version: str = "reliability_v1"

    @property
    def label(self) -> str:
        if self.overall >= 80:
            return "high"
        if self.overall >= 50:
            return "medium"
        return "low"


class CatalogReliabilityItem(BaseModel):
    video_id: UUID
    title: Optional[str] = None
    source_url: Optional[str] = None
    sessions_count: int = 0
    reliability: Optional[ReadoutReliabilityScore] = None
    error: Optional[str] = None


class CatalogReliabilityReport(BaseModel):
    total_videos: int
    scored_videos: int
    mean_reliability: Optional[float] = None
    items: List[CatalogReliabilityItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


class ReadoutPreflightIssue(BaseModel):
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str


class ReadoutPreflightResponse(BaseModel):
    video_id: UUID
    ready: bool = Field(description="True when no blocking errors were found.")
    issues: List[ReadoutPreflightIssue] = Field(default_factory=list)
    sessions_with_trace: int = 0
    total_trace_points: int = 0
    duration_ms: Optional[int] = None
    estimated_usable_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Export package
# ---------------------------------------------------------------------------


class ReadoutExportPackageResponse(BaseModel):
    video_metadata: ReadoutVideoMetadata
    per_timepoint_csv: str
    readout_json: ReadoutExportJson
    compact_report: CompactReadoutReport


# ---------------------------------------------------------------------------
# Readout payload (full response)
# ---------------------------------------------------------------------------


class ReadoutPayload(BaseModel):
    schema_version: str = Field(
        description="Versioned readout payload contract.",
    )
    video_id: UUID
    source_url: Optional[str] = None
    source_url_reachable: Optional[bool] = Field(
        default=None,
        description="Whether source_url was reachable at readout build time. None means not checked.",
    )
    has_sufficient_watch_data: bool = Field(
        default=False,
        description="True when enough watch time was recorded for scores to be meaningful (>= 3 s of video_time_ms).",
    )
    variant_id: Optional[str] = None
    session_id: Optional[UUID] = None
    aggregate: bool
    duration_ms: int = Field(ge=0)
    timebase: ReadoutTimebase
    context: ReadoutContext
    traces: ReadoutTraces
    segments: ReadoutSegments
    labels: ReadoutLabels
    quality: ReadoutQuality
    aggregate_metrics: Optional[ReadoutAggregateMetrics] = None
    playback_telemetry: List[SessionPlaybackEventRead] = Field(default_factory=list)
    neuro_scores: Optional[NeuroScoreTaxonomy] = None
    product_rollups: Optional[ProductRollupPresentation] = None
    legacy_score_adapters: List[LegacyScoreAdapter] = Field(default_factory=list)
    reliability_score: Optional[ReadoutReliabilityScore] = Field(
        default=None,
        description="Engine report on how accurately each model score reflects its design intent.",
    )

    # Compatibility mirrors for older dashboard/client paths.
    scenes: List[ReadoutScene] = Field(default_factory=list)
    cuts: List[ReadoutCut] = Field(default_factory=list)
    cta_markers: List[ReadoutCtaMarker] = Field(default_factory=list)
    diagnostics: List[SceneDiagnosticCard] = Field(default_factory=list)
    annotations: List[SessionAnnotationRead] = Field(default_factory=list)
    annotation_summary: AnnotationSummary
    survey_summary: SurveySummary
    quality_summary: ReadoutQualitySummary


class VideoReadoutResponse(ReadoutPayload):
    """Backward-compatible alias for readout responses."""
