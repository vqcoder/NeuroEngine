"""Shared Pydantic contract for readout aggregate synchrony metrics."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .schemas_common import OptionalTimeWindowMixin, TimeRangeMixin


class AttentionalSynchronyPathway(str, Enum):
    direct_panel_gaze = "direct_panel_gaze"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class AttentionalSynchronyTimelineScore(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    pathway: AttentionalSynchronyPathway
    reason: str = Field(min_length=1)


class AttentionalSynchronyExtrema(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class AttentionalSynchronyDiagnostics(BaseModel):
    pathway: AttentionalSynchronyPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    segment_scores: List[AttentionalSynchronyTimelineScore] = Field(default_factory=list)
    peaks: List[AttentionalSynchronyExtrema] = Field(default_factory=list)
    valleys: List[AttentionalSynchronyExtrema] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pathway_payload(self) -> "AttentionalSynchronyDiagnostics":
        if self.pathway != AttentionalSynchronyPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class NarrativeControlPathway(str, Enum):
    timeline_grammar = "timeline_grammar"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class NarrativeControlSceneScore(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    scene_id: Optional[str] = None
    scene_label: Optional[str] = None
    fragmentation_index: Optional[float] = Field(default=None, ge=0, le=1)
    boundary_density: Optional[float] = Field(default=None, ge=0)
    motion_continuity: Optional[float] = Field(default=None, ge=0, le=1)
    ordering_pattern: Optional[Literal["context_before_face", "face_before_context", "balanced"]] = None
    summary: str = Field(min_length=1)


class NarrativeControlMomentContribution(TimeRangeMixin):
    contribution: float
    category: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1)
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


class NarrativeControlHeuristicCheck(OptionalTimeWindowMixin):
    heuristic_key: str = Field(min_length=1, max_length=128)
    passed: bool
    score_delta: float
    reason: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)


class NarrativeControlDiagnostics(BaseModel):
    pathway: NarrativeControlPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    scene_scores: List[NarrativeControlSceneScore] = Field(default_factory=list)
    disruption_penalties: List[NarrativeControlMomentContribution] = Field(default_factory=list)
    reveal_structure_bonuses: List[NarrativeControlMomentContribution] = Field(default_factory=list)
    top_contributing_moments: List[NarrativeControlMomentContribution] = Field(default_factory=list)
    heuristic_checks: List[NarrativeControlHeuristicCheck] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "NarrativeControlDiagnostics":
        if self.pathway != NarrativeControlPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class BlinkTransportPathway(str, Enum):
    direct_panel_blink = "direct_panel_blink"
    fallback_proxy = "fallback_proxy"
    sparse_fallback = "sparse_fallback"
    insufficient_data = "insufficient_data"
    disabled = "disabled"


class BlinkTransportTimelineScore(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    pathway: BlinkTransportPathway
    reason: str = Field(min_length=1)
    blink_suppression: Optional[float] = Field(default=None, ge=0, le=1)
    rebound_signal: Optional[float] = Field(default=None, ge=0, le=1)
    cta_avoidance_signal: Optional[float] = Field(default=None, ge=0, le=1)


class BlinkTransportWarningSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class BlinkTransportWarning(OptionalTimeWindowMixin):
    warning_key: str = Field(min_length=1, max_length=128)
    severity: BlinkTransportWarningSeverity
    message: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    metric_value: Optional[float] = None


class BlinkTransportDiagnostics(BaseModel):
    pathway: BlinkTransportPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    segment_scores: List[BlinkTransportTimelineScore] = Field(default_factory=list)
    suppression_score: Optional[float] = Field(default=None, ge=0, le=1)
    rebound_score: Optional[float] = Field(default=None, ge=0, le=1)
    cta_avoidance_score: Optional[float] = Field(default=None, ge=0, le=1)
    cross_viewer_blink_synchrony: Optional[float] = Field(default=None, ge=-1, le=1)
    engagement_warnings: List[BlinkTransportWarning] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "BlinkTransportDiagnostics":
        if self.pathway not in {
            BlinkTransportPathway.insufficient_data,
            BlinkTransportPathway.disabled,
        }:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class RewardAnticipationPathway(str, Enum):
    timeline_dynamics = "timeline_dynamics"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class RewardAnticipationTimelineWindowType(str, Enum):
    anticipation_ramp = "anticipation_ramp"
    payoff_window = "payoff_window"


class RewardAnticipationTimelineWindow(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    window_type: RewardAnticipationTimelineWindowType
    reason: str = Field(min_length=1)
    ramp_slope: Optional[float] = None
    reward_delta: Optional[float] = None
    tension_level: Optional[float] = Field(default=None, ge=0, le=1)
    release_level: Optional[float] = Field(default=None, ge=0, le=1)


class RewardAnticipationWarningSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RewardAnticipationWarning(OptionalTimeWindowMixin):
    warning_key: str = Field(min_length=1, max_length=128)
    severity: RewardAnticipationWarningSeverity
    message: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    metric_value: Optional[float] = None


class RewardAnticipationDiagnostics(BaseModel):
    pathway: RewardAnticipationPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    anticipation_ramps: List[RewardAnticipationTimelineWindow] = Field(default_factory=list)
    payoff_windows: List[RewardAnticipationTimelineWindow] = Field(default_factory=list)
    warnings: List[RewardAnticipationWarning] = Field(default_factory=list)
    anticipation_strength: Optional[float] = Field(default=None, ge=0, le=1)
    payoff_release_strength: Optional[float] = Field(default=None, ge=0, le=1)
    tension_release_balance: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "RewardAnticipationDiagnostics":
        if self.pathway != RewardAnticipationPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class BoundaryEncodingPathway(str, Enum):
    timeline_boundary_model = "timeline_boundary_model"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class BoundaryEncodingTimelineWindowType(str, Enum):
    strong_encoding = "strong_encoding"
    weak_encoding = "weak_encoding"


class BoundaryEncodingTimelineWindow(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    window_type: BoundaryEncodingTimelineWindowType
    reason: str = Field(min_length=1)
    payload_type: Optional[str] = None
    nearest_boundary_ms: Optional[int] = Field(default=None, ge=0)
    boundary_distance_ms: Optional[int] = Field(default=None, ge=0)
    novelty_signal: Optional[float] = Field(default=None, ge=0, le=1)
    reinforcement_signal: Optional[float] = Field(default=None, ge=0, le=1)


class BoundaryEncodingFlagSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class BoundaryEncodingFlag(OptionalTimeWindowMixin):
    flag_key: str = Field(min_length=1, max_length=128)
    severity: BoundaryEncodingFlagSeverity
    message: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    metric_value: Optional[float] = None


class BoundaryEncodingDiagnostics(BaseModel):
    pathway: BoundaryEncodingPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    strong_windows: List[BoundaryEncodingTimelineWindow] = Field(default_factory=list)
    weak_windows: List[BoundaryEncodingTimelineWindow] = Field(default_factory=list)
    flags: List[BoundaryEncodingFlag] = Field(default_factory=list)
    boundary_alignment_score: Optional[float] = Field(default=None, ge=0, le=1)
    novelty_boundary_score: Optional[float] = Field(default=None, ge=0, le=1)
    reinforcement_score: Optional[float] = Field(default=None, ge=0, le=1)
    overload_risk_score: Optional[float] = Field(default=None, ge=0, le=1)
    payload_count: int = Field(default=0, ge=0)
    boundary_count: int = Field(default=0, ge=0)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "BoundaryEncodingDiagnostics":
        if self.pathway != BoundaryEncodingPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class SocialTransmissionPathway(str, Enum):
    annotation_augmented = "annotation_augmented"
    timeline_signal_model = "timeline_signal_model"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class SocialTransmissionTimelineWindow(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    novelty_signal: Optional[float] = Field(default=None, ge=0, le=1)
    emotional_activation_signal: Optional[float] = Field(default=None, ge=0, le=1)
    quote_worthiness_signal: Optional[float] = Field(default=None, ge=0, le=1)


class SocialTransmissionDiagnostics(BaseModel):
    pathway: SocialTransmissionPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    segment_scores: List[SocialTransmissionTimelineWindow] = Field(default_factory=list)
    novelty_signal: Optional[float] = Field(default=None, ge=0, le=1)
    identity_signal: Optional[float] = Field(default=None, ge=0, le=1)
    usefulness_signal: Optional[float] = Field(default=None, ge=0, le=1)
    quote_worthiness_signal: Optional[float] = Field(default=None, ge=0, le=1)
    emotional_activation_signal: Optional[float] = Field(default=None, ge=0, le=1)
    memorability_signal: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "SocialTransmissionDiagnostics":
        if self.pathway != SocialTransmissionPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class SelfRelevancePathway(str, Enum):
    contextual_personalization = "contextual_personalization"
    survey_augmented = "survey_augmented"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class SelfRelevanceTimelineWindow(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    direct_address_signal: Optional[float] = Field(default=None, ge=0, le=1)
    personalization_hook_signal: Optional[float] = Field(default=None, ge=0, le=1)


class SelfRelevanceWarningSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class SelfRelevanceWarning(OptionalTimeWindowMixin):
    warning_key: str = Field(min_length=1, max_length=128)
    severity: SelfRelevanceWarningSeverity
    message: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    metric_value: Optional[float] = None


class SelfRelevanceDiagnostics(BaseModel):
    pathway: SelfRelevancePathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    segment_scores: List[SelfRelevanceTimelineWindow] = Field(default_factory=list)
    warnings: List[SelfRelevanceWarning] = Field(default_factory=list)
    direct_address_signal: Optional[float] = Field(default=None, ge=0, le=1)
    audience_match_signal: Optional[float] = Field(default=None, ge=0, le=1)
    niche_specificity_signal: Optional[float] = Field(default=None, ge=0, le=1)
    personalization_hook_signal: Optional[float] = Field(default=None, ge=0, le=1)
    resonance_signal: Optional[float] = Field(default=None, ge=0, le=1)
    context_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "SelfRelevanceDiagnostics":
        if self.pathway != SelfRelevancePathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class SyntheticLiftPriorPathway(str, Enum):
    taxonomy_regression = "taxonomy_regression"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class SyntheticLiftCalibrationStatus(str, Enum):
    uncalibrated = "uncalibrated"
    provisional = "provisional"
    geox_calibrated = "geox_calibrated"
    truth_layer_unavailable = "truth_layer_unavailable"


class SyntheticLiftPriorFeatureInputSource(str, Enum):
    taxonomy = "taxonomy"
    legacy_performance = "legacy_performance"
    calibration = "calibration"


class SyntheticLiftPriorFeatureInput(BaseModel):
    feature_name: str = Field(min_length=1, max_length=128)
    source: SyntheticLiftPriorFeatureInputSource
    raw_value: float
    normalized_value: float = Field(ge=0, le=1)
    weight: float = Field(ge=0)


class SyntheticLiftPriorTimelineWindow(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    contribution: Optional[float] = None


class SyntheticLiftPriorDiagnostics(BaseModel):
    pathway: SyntheticLiftPriorPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    predicted_incremental_lift_pct: Optional[float] = None
    predicted_iroas: Optional[float] = None
    incremental_lift_ci_low: Optional[float] = None
    incremental_lift_ci_high: Optional[float] = None
    iroas_ci_low: Optional[float] = None
    iroas_ci_high: Optional[float] = None
    uncertainty_band: Optional[float] = Field(default=None, ge=0)
    calibration_status: SyntheticLiftCalibrationStatus = SyntheticLiftCalibrationStatus.uncalibrated
    calibration_observation_count: int = Field(default=0, ge=0)
    calibration_last_updated_at: Optional[datetime] = None
    model_version: str = Field(min_length=1)
    segment_scores: List[SyntheticLiftPriorTimelineWindow] = Field(default_factory=list)
    feature_inputs: List[SyntheticLiftPriorFeatureInput] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "SyntheticLiftPriorDiagnostics":
        if self.pathway != SyntheticLiftPriorPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when synthetic lift prior pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when synthetic lift prior pathway has data")
            if self.predicted_incremental_lift_pct is None:
                raise ValueError("predicted_incremental_lift_pct must be provided when pathway has data")
            if self.predicted_iroas is None:
                raise ValueError("predicted_iroas must be provided when pathway has data")
            if self.incremental_lift_ci_low is None or self.incremental_lift_ci_high is None:
                raise ValueError("incremental_lift_ci_low/high must be provided when pathway has data")
            if self.iroas_ci_low is None or self.iroas_ci_high is None:
                raise ValueError("iroas_ci_low/high must be provided when pathway has data")
        if (
            self.incremental_lift_ci_low is not None
            and self.incremental_lift_ci_high is not None
            and self.incremental_lift_ci_low > self.incremental_lift_ci_high
        ):
            raise ValueError("incremental_lift_ci_low must be <= incremental_lift_ci_high")
        if (
            self.iroas_ci_low is not None
            and self.iroas_ci_high is not None
            and self.iroas_ci_low > self.iroas_ci_high
        ):
            raise ValueError("iroas_ci_low must be <= iroas_ci_high")
        return self


class AuFrictionPathway(str, Enum):
    au_signal_model = "au_signal_model"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class AuFrictionState(str, Enum):
    confusion = "confusion"
    strain = "strain"
    amusement = "amusement"
    tension = "tension"
    resistance = "resistance"


class AuFrictionTimelineWindow(TimeRangeMixin):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    dominant_state: AuFrictionState
    transition_context: Optional[Literal["post_transition_spike"]] = None
    au04_signal: Optional[float] = Field(default=None, ge=0, le=1)
    au06_signal: Optional[float] = Field(default=None, ge=0, le=1)
    au12_signal: Optional[float] = Field(default=None, ge=0, le=1)
    au25_signal: Optional[float] = Field(default=None, ge=0, le=1)
    au26_signal: Optional[float] = Field(default=None, ge=0, le=1)
    au45_signal: Optional[float] = Field(default=None, ge=0, le=1)
    confusion_signal: Optional[float] = Field(default=None, ge=0, le=1)
    strain_signal: Optional[float] = Field(default=None, ge=0, le=1)
    amusement_signal: Optional[float] = Field(default=None, ge=0, le=1)
    tension_signal: Optional[float] = Field(default=None, ge=0, le=1)
    resistance_signal: Optional[float] = Field(default=None, ge=0, le=1)


class AuFrictionQualityWarningSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AuFrictionQualityWarning(OptionalTimeWindowMixin):
    warning_key: str = Field(min_length=1, max_length=128)
    severity: AuFrictionQualityWarningSeverity
    message: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    metric_value: Optional[float] = None


class AuFrictionDiagnostics(BaseModel):
    pathway: AuFrictionPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    segment_scores: List[AuFrictionTimelineWindow] = Field(default_factory=list)
    warnings: List[AuFrictionQualityWarning] = Field(default_factory=list)
    confusion_signal: Optional[float] = Field(default=None, ge=0, le=1)
    strain_signal: Optional[float] = Field(default=None, ge=0, le=1)
    amusement_signal: Optional[float] = Field(default=None, ge=0, le=1)
    tension_signal: Optional[float] = Field(default=None, ge=0, le=1)
    resistance_signal: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "AuFrictionDiagnostics":
        if self.pathway != AuFrictionPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class CtaReceptionPathway(str, Enum):
    multi_signal_model = "multi_signal_model"
    fallback_proxy = "fallback_proxy"
    insufficient_data = "insufficient_data"


class CtaReceptionTimelineWindow(TimeRangeMixin):
    cta_id: Optional[str] = None
    cta_type: str = Field(min_length=1, max_length=64)
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    synchrony_support: Optional[float] = Field(default=None, ge=0, le=1)
    narrative_support: Optional[float] = Field(default=None, ge=0, le=1)
    blink_receptivity_support: Optional[float] = Field(default=None, ge=0, le=1)
    reward_timing_support: Optional[float] = Field(default=None, ge=0, le=1)
    boundary_coherence_support: Optional[float] = Field(default=None, ge=0, le=1)
    timing_fit_support: Optional[float] = Field(default=None, ge=0, le=1)
    flag_keys: List[str] = Field(default_factory=list)


class CtaReceptionFlagSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class CtaReceptionFlag(OptionalTimeWindowMixin):
    flag_key: str = Field(min_length=1, max_length=128)
    severity: CtaReceptionFlagSeverity
    message: str = Field(min_length=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    cta_id: Optional[str] = None
    cta_type: Optional[str] = None
    metric_value: Optional[float] = None


class CtaReceptionDiagnostics(BaseModel):
    pathway: CtaReceptionPathway
    global_score: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    cta_windows: List[CtaReceptionTimelineWindow] = Field(default_factory=list)
    flags: List[CtaReceptionFlag] = Field(default_factory=list)
    synchrony_support: Optional[float] = Field(default=None, ge=0, le=1)
    narrative_support: Optional[float] = Field(default=None, ge=0, le=1)
    blink_receptivity_support: Optional[float] = Field(default=None, ge=0, le=1)
    reward_timing_support: Optional[float] = Field(default=None, ge=0, le=1)
    boundary_coherence_support: Optional[float] = Field(default=None, ge=0, le=1)
    overload_risk_support: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_summary: str = Field(min_length=1)
    signals_used: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "CtaReceptionDiagnostics":
        if self.pathway != CtaReceptionPathway.insufficient_data:
            if self.global_score is None:
                raise ValueError("global_score must be provided when pathway has data")
            if self.confidence is None:
                raise ValueError("confidence must be provided when pathway has data")
        return self


class ReadoutAggregateMetrics(BaseModel):
    attention_synchrony: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    blink_synchrony: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    grip_control_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    attentional_synchrony: Optional[AttentionalSynchronyDiagnostics] = None
    narrative_control: Optional[NarrativeControlDiagnostics] = None
    blink_transport: Optional[BlinkTransportDiagnostics] = None
    reward_anticipation: Optional[RewardAnticipationDiagnostics] = None
    boundary_encoding: Optional[BoundaryEncodingDiagnostics] = None
    au_friction: Optional[AuFrictionDiagnostics] = None
    cta_reception: Optional[CtaReceptionDiagnostics] = None
    social_transmission: Optional[SocialTransmissionDiagnostics] = None
    self_relevance: Optional[SelfRelevanceDiagnostics] = None
    synthetic_lift_prior: Optional[SyntheticLiftPriorDiagnostics] = None
    ci_method: Optional[Literal["sem_95"]] = "sem_95"
    included_sessions: int = Field(default=0, ge=0)
    downweighted_sessions: int = Field(default=0, ge=0)


for _model in (
    AttentionalSynchronyTimelineScore,
    AttentionalSynchronyExtrema,
    AttentionalSynchronyDiagnostics,
    NarrativeControlSceneScore,
    NarrativeControlMomentContribution,
    NarrativeControlHeuristicCheck,
    NarrativeControlDiagnostics,
    BlinkTransportTimelineScore,
    BlinkTransportWarning,
    BlinkTransportDiagnostics,
    RewardAnticipationTimelineWindow,
    RewardAnticipationWarning,
    RewardAnticipationDiagnostics,
    BoundaryEncodingTimelineWindow,
    BoundaryEncodingFlag,
    BoundaryEncodingDiagnostics,
    SocialTransmissionTimelineWindow,
    SocialTransmissionDiagnostics,
    SelfRelevanceTimelineWindow,
    SelfRelevanceWarning,
    SelfRelevanceDiagnostics,
    SyntheticLiftPriorTimelineWindow,
    SyntheticLiftPriorFeatureInput,
    SyntheticLiftPriorDiagnostics,
    AuFrictionTimelineWindow,
    AuFrictionQualityWarning,
    AuFrictionDiagnostics,
    CtaReceptionTimelineWindow,
    CtaReceptionFlag,
    CtaReceptionDiagnostics,
    ReadoutAggregateMetrics,
):
    _model.model_rebuild()
