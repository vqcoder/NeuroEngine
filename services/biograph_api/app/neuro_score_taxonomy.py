"""Neuro-score taxonomy composition with self-registering score builders."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from .readout_metrics import clamp, mean_optional

from .schemas import (
    AttentionalSynchronyPathway,
    AuFrictionPathway,
    BlinkTransportPathway,
    BoundaryEncodingPathway,
    CtaReceptionPathway,
    LegacyScoreAdapter,
    NarrativeControlPathway,
    RewardAnticipationPathway,
    SelfRelevancePathway,
    SocialTransmissionPathway,
    SyntheticLiftPriorPathway,
    NeuroCompositeRollup,
    NeuroEvidenceWindow,
    NeuroFeatureContribution,
    NeuroRollupFamilies,
    NeuroRollupMachineName,
    NeuroRollupRegistryEntry,
    NeuroScoreContract,
    NeuroScoreFamilies,
    NeuroScoreMachineName,
    NeuroScoreRegistryEntry,
    NeuroScoreStatus,
    NeuroScoreTaxonomy,
    ReadoutAggregateMetrics,
    ReadoutContext,
    ReadoutLabels,
    ReadoutSegment,
    ReadoutSegments,
    ReadoutTracePoint,
    ReadoutTraces,
    SceneDiagnosticCard,
)

SCORE_MODEL_VERSION = "neuro_taxonomy_v1"
logger = logging.getLogger(__name__)

ScoreBuilder = Callable[["NeuroScoreComputationContext"], NeuroScoreContract]
RollupBuilder = Callable[["NeuroRollupComputationContext"], NeuroCompositeRollup]


@dataclass(frozen=True)
class ScoreRegistryDefinition:
    machine_name: NeuroScoreMachineName
    display_label: str
    claim_safe_description: str
    builder_key: str
    builder: ScoreBuilder


@dataclass(frozen=True)
class RollupRegistryDefinition:
    machine_name: NeuroRollupMachineName
    display_label: str
    claim_safe_description: str
    builder_key: str
    builder: RollupBuilder


@dataclass(frozen=True)
class NeuroScoreComputationContext:
    traces: ReadoutTraces
    segments: ReadoutSegments
    diagnostics: Sequence[SceneDiagnosticCard]
    labels: ReadoutLabels
    aggregate_metrics: Optional[ReadoutAggregateMetrics]
    context: ReadoutContext
    window_ms: int


@dataclass(frozen=True)
class NeuroRollupComputationContext:
    scores: Dict[NeuroScoreMachineName, NeuroScoreContract]


_SCORE_REGISTRY: Dict[NeuroScoreMachineName, ScoreRegistryDefinition] = {}
_ROLLUP_REGISTRY: Dict[NeuroRollupMachineName, RollupRegistryDefinition] = {}


def register_score(
    machine_name: NeuroScoreMachineName,
    display_label: str,
    claim_safe_description: str,
) -> Callable[[ScoreBuilder], ScoreBuilder]:
    """Register a score builder in the taxonomy registry."""

    def decorator(builder: ScoreBuilder) -> ScoreBuilder:
        _SCORE_REGISTRY[machine_name] = ScoreRegistryDefinition(
            machine_name=machine_name,
            display_label=display_label,
            claim_safe_description=claim_safe_description,
            builder_key=f"{builder.__module__}:{builder.__name__}",
            builder=builder,
        )
        return builder

    return decorator


def register_rollup(
    machine_name: NeuroRollupMachineName,
    display_label: str,
    claim_safe_description: str,
) -> Callable[[RollupBuilder], RollupBuilder]:
    """Register a rollup builder in the taxonomy registry."""

    def decorator(builder: RollupBuilder) -> RollupBuilder:
        _ROLLUP_REGISTRY[machine_name] = RollupRegistryDefinition(
            machine_name=machine_name,
            display_label=display_label,
            claim_safe_description=claim_safe_description,
            builder_key=f"{builder.__module__}:{builder.__name__}",
            builder=builder,
        )
        return builder

    return decorator


def _to_100_from_unit(value: float) -> float:
    return clamp(value * 100.0, 0.0, 100.0)


def _to_100_from_signed_unit(value: float) -> float:
    return clamp((value + 1.0) * 50.0, 0.0, 100.0)


def _series_values(points: Sequence[ReadoutTracePoint]) -> List[float]:
    return [float(point.value) for point in points if point.value is not None]


def _safe_evidence_window(start_ms: int, end_ms: int, reason: str) -> Optional[NeuroEvidenceWindow]:
    """Return a NeuroEvidenceWindow only when end_ms > start_ms; otherwise return None."""
    if end_ms > start_ms:
        return NeuroEvidenceWindow(start_ms=start_ms, end_ms=end_ms, reason=reason)
    return None


def _series_top_windows(
    points: Sequence[ReadoutTracePoint],
    reason: str,
    window_ms: int,
    limit: int = 3,
) -> List[NeuroEvidenceWindow]:
    ranked = [
        point for point in points if point.value is not None
    ]
    ranked.sort(key=lambda point: float(point.value or 0.0), reverse=True)
    windows: List[NeuroEvidenceWindow] = []
    for point in ranked[:limit]:
        w = _safe_evidence_window(
            start_ms=int(point.video_time_ms),
            end_ms=int(point.video_time_ms) + int(window_ms),
            reason=reason,
        )
        if w is not None:
            windows.append(w)
    return windows


def _segment_windows(
    segments: Sequence[ReadoutSegment],
    reason: str,
    limit: int = 3,
) -> List[NeuroEvidenceWindow]:
    ranked = sorted(segments, key=lambda segment: float(segment.magnitude), reverse=True)
    windows: List[NeuroEvidenceWindow] = []
    for segment in ranked[:limit]:
        w = _safe_evidence_window(
            start_ms=int(segment.start_video_time_ms),
            end_ms=int(segment.end_video_time_ms),
            reason=reason,
        )
        if w is not None:
            windows.append(w)
    return windows


def _tracking_confidence(traces: ReadoutTraces) -> Optional[float]:
    return mean_optional(_series_values(traces.tracking_confidence))


def _score(
    machine_name: NeuroScoreMachineName,
    status: NeuroScoreStatus,
    scalar_value: Optional[float],
    confidence: Optional[float],
    evidence_windows: Optional[List[NeuroEvidenceWindow]] = None,
    top_feature_contributions: Optional[List[NeuroFeatureContribution]] = None,
) -> NeuroScoreContract:
    definition = _SCORE_REGISTRY[machine_name]
    bounded_score = None if scalar_value is None else clamp(float(scalar_value), 0.0, 100.0)
    bounded_confidence = (
        None if confidence is None else clamp(float(confidence), 0.0, 1.0)
    )
    return NeuroScoreContract(
        machine_name=machine_name,
        display_label=definition.display_label,
        scalar_value=bounded_score,
        confidence=bounded_confidence,
        status=status,
        evidence_windows=evidence_windows or [],
        top_feature_contributions=top_feature_contributions or [],
        model_version=SCORE_MODEL_VERSION,
        provenance=definition.builder_key,
        claim_safe_description=definition.claim_safe_description,
    )


def _rollup(
    machine_name: NeuroRollupMachineName,
    status: NeuroScoreStatus,
    scalar_value: Optional[float],
    confidence: Optional[float],
    component_weights: Dict[str, float],
    component_scores: List[NeuroScoreMachineName],
) -> NeuroCompositeRollup:
    definition = _ROLLUP_REGISTRY[machine_name]
    bounded_score = None if scalar_value is None else clamp(float(scalar_value), 0.0, 100.0)
    bounded_confidence = (
        None if confidence is None else clamp(float(confidence), 0.0, 1.0)
    )
    return NeuroCompositeRollup(
        machine_name=machine_name,
        display_label=definition.display_label,
        scalar_value=bounded_score,
        confidence=bounded_confidence,
        status=status,
        component_scores=component_scores,
        component_weights=component_weights,
        model_version=SCORE_MODEL_VERSION,
        provenance=definition.builder_key,
        claim_safe_description=definition.claim_safe_description,
    )


@register_score(
    NeuroScoreMachineName.arrest_score,
    "Arrest Score",
    "Proxy for early stopping-power based on attention and reward traces.",
)
def build_arrest_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    opening_attention = sorted(context.traces.attention_score, key=lambda item: item.video_time_ms)[:3]
    opening_reward = sorted(context.traces.reward_proxy, key=lambda item: item.video_time_ms)[:3]
    attention_mean = mean_optional(_series_values(opening_attention))
    reward_mean = mean_optional(_series_values(opening_reward))
    if attention_mean is None and reward_mean is None:
        return _score(
            NeuroScoreMachineName.arrest_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    attention_component = attention_mean if attention_mean is not None else reward_mean or 0.0
    reward_component = reward_mean if reward_mean is not None else attention_component
    scalar = (0.65 * attention_component) + (0.35 * reward_component)
    confidence = _tracking_confidence(context.traces)
    return _score(
        NeuroScoreMachineName.arrest_score,
        status=NeuroScoreStatus.available,
        scalar_value=scalar,
        confidence=confidence or 0.65,
        evidence_windows=_series_top_windows(
            opening_attention or context.traces.attention_score,
            reason="Opening attention windows showed above-baseline hold.",
            window_ms=context.window_ms,
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="opening_attention_mean",
                contribution=round((attention_component / 100.0), 6),
                rationale="Higher opening attention increases arrest score.",
            ),
            NeuroFeatureContribution(
                feature_name="opening_reward_proxy_mean",
                contribution=round((reward_component / 100.0), 6),
                rationale="Higher opening reward proxy increases arrest score.",
            ),
        ],
    )


@register_score(
    NeuroScoreMachineName.attentional_synchrony_index,
    "Attentional Synchrony Index",
    "Proxy for cross-viewer temporal alignment in attention dynamics.",
)
def build_attentional_synchrony_index(
    context: NeuroScoreComputationContext,
) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.attentional_synchrony
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != AttentionalSynchronyPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.peaks[:3]
        ]
        if not evidence_windows and diagnostics.segment_scores:
            top_segment = max(
                diagnostics.segment_scores,
                key=lambda item: float(item.score),
            )
            evidence_windows = [
                NeuroEvidenceWindow(
                    start_ms=int(top_segment.start_ms),
                    end_ms=int(top_segment.end_ms),
                    reason=top_segment.reason,
                )
            ]

        pathway_weight = (
            1.0
            if diagnostics.pathway == AttentionalSynchronyPathway.direct_panel_gaze
            else 0.72
        )
        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="attentional_synchrony_pathway_weight",
                contribution=pathway_weight,
                rationale="Direct panel gaze pathway receives full confidence weight; fallback is downweighted.",
            ),
            NeuroFeatureContribution(
                feature_name="segment_coverage",
                contribution=float(len(diagnostics.segment_scores)),
                rationale="More timeline segments increase support for a stable asset-level estimate.",
            ),
        ]
        if context.aggregate_metrics is not None and context.aggregate_metrics.attention_synchrony is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="aggregate_attention_synchrony",
                    contribution=round(float(context.aggregate_metrics.attention_synchrony), 6),
                    rationale="Pairwise attention trace alignment supports synchrony estimation.",
                )
            )

        return _score(
            NeuroScoreMachineName.attentional_synchrony_index,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.8 if pathway_weight >= 1.0 else 0.55)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    if context.aggregate_metrics is None or context.aggregate_metrics.attention_synchrony is None:
        return _score(
            NeuroScoreMachineName.attentional_synchrony_index,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    synchrony = float(context.aggregate_metrics.attention_synchrony)
    return _score(
        NeuroScoreMachineName.attentional_synchrony_index,
        status=NeuroScoreStatus.available,
        scalar_value=_to_100_from_signed_unit(synchrony),
        confidence=clamp(0.55 + (0.35 * abs(synchrony)), 0.0, 1.0),
        evidence_windows=_segment_windows(
            context.segments.attention_gain_segments,
            reason="Synchronized attention gains across viewers.",
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="aggregate_attention_synchrony",
                contribution=round(synchrony, 6),
                rationale="Directly mapped from aggregate attention synchrony.",
            ),
            NeuroFeatureContribution(
                feature_name="included_sessions",
                contribution=float(context.aggregate_metrics.included_sessions),
                rationale="More included sessions increase synchrony stability.",
            ),
        ],
    )


@register_score(
    NeuroScoreMachineName.narrative_control_score,
    "Narrative Control Score",
    "Proxy for how consistently the story maintains attention control.",
)
def build_narrative_control_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.narrative_control
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != NarrativeControlPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.top_contributing_moments[:3]
        ]
        if not evidence_windows and diagnostics.scene_scores:
            top_scene = max(
                diagnostics.scene_scores,
                key=lambda item: float(item.score),
            )
            evidence_windows = [
                NeuroEvidenceWindow(
                    start_ms=int(top_scene.start_ms),
                    end_ms=int(top_scene.end_ms),
                    reason=top_scene.summary,
                )
            ]

        disruption_penalty_total = sum(
            float(item.contribution)
            for item in diagnostics.disruption_penalties
        )
        reveal_bonus_total = sum(
            float(item.contribution)
            for item in diagnostics.reveal_structure_bonuses
        )
        scene_score_mean = mean_optional([float(item.score) for item in diagnostics.scene_scores]) or 0.0
        passed_heuristics = sum(1 for item in diagnostics.heuristic_checks if item.passed)
        total_heuristics = len(diagnostics.heuristic_checks)
        heuristic_pass_ratio = (
            float(passed_heuristics) / float(total_heuristics)
            if total_heuristics > 0
            else 0.0
        )
        pathway_weight = (
            1.0
            if diagnostics.pathway == NarrativeControlPathway.timeline_grammar
            else 0.74
        )
        return _score(
            NeuroScoreMachineName.narrative_control_score,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.78 if pathway_weight >= 1.0 else 0.58)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=[
                NeuroFeatureContribution(
                    feature_name="narrative_pathway_weight",
                    contribution=round(pathway_weight, 6),
                    rationale="Timeline grammar pathway receives full confidence weight; fallback is downweighted.",
                ),
                NeuroFeatureContribution(
                    feature_name="mean_scene_control_score",
                    contribution=round(scene_score_mean / 100.0, 6),
                    rationale="Average scene-level control quality anchors the global narrative estimate.",
                ),
                NeuroFeatureContribution(
                    feature_name="disruption_penalty_total",
                    contribution=round(disruption_penalty_total, 6),
                    rationale="Disruptive transitions decrease narrative control.",
                ),
                NeuroFeatureContribution(
                    feature_name="reveal_bonus_total",
                    contribution=round(reveal_bonus_total, 6),
                    rationale="Coherent reveal timing increases narrative control.",
                ),
                NeuroFeatureContribution(
                    feature_name="heuristic_pass_ratio",
                    contribution=round(heuristic_pass_ratio, 6),
                    rationale="Configured narrative heuristics indicate structural coherence when they pass.",
                ),
            ],
        )

    if context.aggregate_metrics is not None and context.aggregate_metrics.grip_control_score is not None:
        grip = float(context.aggregate_metrics.grip_control_score)
        return _score(
            NeuroScoreMachineName.narrative_control_score,
            status=NeuroScoreStatus.available,
            scalar_value=_to_100_from_signed_unit(grip),
            confidence=clamp(0.55 + (0.3 * abs(grip)), 0.0, 1.0),
            evidence_windows=_segment_windows(
                context.segments.attention_gain_segments,
                reason="Narrative windows sustained positive attention control.",
            ),
            top_feature_contributions=[
                NeuroFeatureContribution(
                    feature_name="grip_control_score",
                    contribution=round(grip, 6),
                    rationale="Mapped from aggregate narrative control proxy.",
                )
            ],
        )

    velocity_values = _series_values(context.traces.attention_velocity)
    if not velocity_values:
        return _score(
            NeuroScoreMachineName.narrative_control_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    velocity_stability = 1.0 - clamp(abs(mean_optional(velocity_values) or 0.0), 0.0, 1.0)
    return _score(
        NeuroScoreMachineName.narrative_control_score,
        status=NeuroScoreStatus.available,
        scalar_value=_to_100_from_unit(velocity_stability),
        confidence=_tracking_confidence(context.traces) or 0.6,
        evidence_windows=_segment_windows(
            context.segments.attention_gain_segments,
            reason="Stable attention velocity around narrative beats.",
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="attention_velocity_stability",
                contribution=round(velocity_stability, 6),
                rationale="Lower absolute velocity drift increases control score.",
            )
        ],
    )


@register_score(
    NeuroScoreMachineName.blink_transport_score,
    "Blink Transport Score",
    "Proxy for immersion inferred from blink-pattern modulation.",
)
def build_blink_transport_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.blink_transport
        if context.aggregate_metrics is not None
        else None
    )
    if diagnostics is not None:
        if diagnostics.pathway == BlinkTransportPathway.disabled:
            return _score(
                NeuroScoreMachineName.blink_transport_score,
                status=NeuroScoreStatus.unavailable,
                scalar_value=None,
                confidence=None,
                top_feature_contributions=[
                    NeuroFeatureContribution(
                        feature_name="blink_transport_feature_flag",
                        contribution=0.0,
                        rationale="Blink transport instrumentation is disabled for this environment.",
                    )
                ],
            )
        if (
            diagnostics.pathway != BlinkTransportPathway.insufficient_data
            and diagnostics.global_score is not None
        ):
            pathway_weight = {
                BlinkTransportPathway.direct_panel_blink: 1.0,
                BlinkTransportPathway.fallback_proxy: 0.78,
                BlinkTransportPathway.sparse_fallback: 0.58,
                BlinkTransportPathway.insufficient_data: 0.0,
                BlinkTransportPathway.disabled: 0.0,
            }[diagnostics.pathway]

            top_segments = sorted(
                diagnostics.segment_scores,
                key=lambda item: float(item.score),
                reverse=True,
            )[:3]
            evidence_windows = [
                NeuroEvidenceWindow(
                    start_ms=int(item.start_ms),
                    end_ms=int(item.end_ms),
                    reason=item.reason,
                )
                for item in top_segments
            ]
            if not evidence_windows:
                for warning in diagnostics.engagement_warnings[:2]:
                    if warning.start_ms is None or warning.end_ms is None:
                        continue
                    evidence_windows.append(
                        NeuroEvidenceWindow(
                            start_ms=int(warning.start_ms),
                            end_ms=int(warning.end_ms),
                            reason=warning.message,
                        )
                    )

            top_feature_contributions = [
                NeuroFeatureContribution(
                    feature_name="blink_transport_pathway_weight",
                    contribution=round(pathway_weight, 6),
                    rationale=(
                        "Direct panel blink pathway receives full weight; fallback pathways are confidence-downweighted."
                    ),
                )
            ]
            if diagnostics.suppression_score is not None:
                top_feature_contributions.append(
                    NeuroFeatureContribution(
                        feature_name="blink_suppression_high_information",
                        contribution=round(float(diagnostics.suppression_score), 6),
                        rationale="Sustained blink suppression in high-information windows supports transport scoring.",
                    )
                )
            if diagnostics.rebound_score is not None:
                top_feature_contributions.append(
                    NeuroFeatureContribution(
                        feature_name="blink_rebound_boundary_alignment",
                        contribution=round(float(diagnostics.rebound_score), 6),
                        rationale="Timely rebound near safe boundaries supports segmentation-aligned transport.",
                    )
                )
            if diagnostics.cta_avoidance_score is not None:
                top_feature_contributions.append(
                    NeuroFeatureContribution(
                        feature_name="blink_avoidance_cta_reveal",
                        contribution=round(float(diagnostics.cta_avoidance_score), 6),
                        rationale="Suppressed blinking around CTA/reveal windows increases transport support.",
                    )
                )
            if diagnostics.cross_viewer_blink_synchrony is not None:
                top_feature_contributions.append(
                    NeuroFeatureContribution(
                        feature_name="cross_viewer_blink_synchrony",
                        contribution=round(float(diagnostics.cross_viewer_blink_synchrony), 6),
                        rationale="Cross-viewer blink synchrony contributes when panel overlap is available.",
                    )
                )

            return _score(
                NeuroScoreMachineName.blink_transport_score,
                status=NeuroScoreStatus.available,
                scalar_value=float(diagnostics.global_score),
                confidence=(
                    float(diagnostics.confidence)
                    if diagnostics.confidence is not None
                    else (0.76 if pathway_weight >= 1.0 else 0.52)
                ),
                evidence_windows=evidence_windows,
                top_feature_contributions=top_feature_contributions,
            )

    inhibition_values = _series_values(context.traces.blink_inhibition)
    if not inhibition_values:
        return _score(
            NeuroScoreMachineName.blink_transport_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    inhibition_mean = mean_optional(inhibition_values) or 0.0
    return _score(
        NeuroScoreMachineName.blink_transport_score,
        status=NeuroScoreStatus.available,
        scalar_value=_to_100_from_signed_unit(inhibition_mean),
        confidence=_tracking_confidence(context.traces) or 0.6,
        evidence_windows=_series_top_windows(
            context.traces.blink_inhibition,
            reason="Blink inhibition windows suggest sustained transport.",
            window_ms=context.window_ms,
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="blink_inhibition_mean",
                contribution=round(inhibition_mean, 6),
                rationale="Higher blink inhibition maps to higher transport proxy.",
            )
        ],
    )


@register_score(
    NeuroScoreMachineName.boundary_encoding_score,
    "Boundary Encoding Score",
    "Proxy for memory-friendly payload placement at event boundaries.",
)
def build_boundary_encoding_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.boundary_encoding
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != BoundaryEncodingPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        evidence_windows: List[NeuroEvidenceWindow] = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.strong_windows[:2]
        ]
        if len(evidence_windows) < 3:
            evidence_windows.extend(
                [
                    NeuroEvidenceWindow(
                        start_ms=int(item.start_ms),
                        end_ms=int(item.end_ms),
                        reason=item.reason,
                    )
                    for item in diagnostics.weak_windows[: max(0, 3 - len(evidence_windows))]
                ]
            )
        if not evidence_windows and diagnostics.flags:
            for item in diagnostics.flags[:2]:
                if item.start_ms is None or item.end_ms is None:
                    continue
                evidence_windows.append(
                    NeuroEvidenceWindow(
                        start_ms=int(item.start_ms),
                        end_ms=int(item.end_ms),
                        reason=item.message,
                    )
                )

        pathway_weight = (
            1.0
            if diagnostics.pathway == BoundaryEncodingPathway.timeline_boundary_model
            else 0.74
        )
        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="boundary_encoding_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Timeline boundary model receives full weight; fallback is confidence-downweighted.",
            )
        ]
        if diagnostics.boundary_alignment_score is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="payload_boundary_alignment",
                    contribution=round(float(diagnostics.boundary_alignment_score), 6),
                    rationale="Closer payload placement to event boundaries increases boundary encoding support.",
                )
            )
        if diagnostics.novelty_boundary_score is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="novelty_at_boundaries",
                    contribution=round(float(diagnostics.novelty_boundary_score), 6),
                    rationale="Higher novelty concentration at boundary-adjacent payload windows supports chunked encoding.",
                )
            )
        if diagnostics.reinforcement_score is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="reinforcement_spacing_signal",
                    contribution=round(float(diagnostics.reinforcement_score), 6),
                    rationale="Memory-friendly repetition spacing increases boundary encoding support.",
                )
            )
        if diagnostics.overload_risk_score is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="payload_overload_risk",
                    contribution=round(-float(diagnostics.overload_risk_score), 6),
                    rationale="Payload overload near a single boundary reduces encoding quality.",
                )
            )

        return _score(
            NeuroScoreMachineName.boundary_encoding_score,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.77 if pathway_weight >= 1.0 else 0.56)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    if not context.context.cuts and not context.context.scenes:
        return _score(
            NeuroScoreMachineName.boundary_encoding_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )

    attention_by_time = {
        point.video_time_ms: point for point in context.traces.attention_score if point.value is not None
    }
    boundary_points: List[ReadoutTracePoint] = []
    for cut in context.context.cuts:
        nearest = min(
            attention_by_time.values(),
            default=None,
            key=lambda point: abs(int(point.video_time_ms) - int(cut.start_ms)),
        )
        if nearest is not None:
            boundary_points.append(nearest)

    if not boundary_points:
        return _score(
            NeuroScoreMachineName.boundary_encoding_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )

    boundary_attention = mean_optional(_series_values(boundary_points)) or 0.0
    return _score(
        NeuroScoreMachineName.boundary_encoding_score,
        status=NeuroScoreStatus.available,
        scalar_value=boundary_attention,
        confidence=_tracking_confidence(context.traces) or 0.58,
        evidence_windows=_series_top_windows(
            boundary_points,
            reason="Boundary windows retained attention across transitions.",
            window_ms=context.window_ms,
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="boundary_attention_mean",
                contribution=round(boundary_attention / 100.0, 6),
                rationale="Higher attention near cuts/scenes increases boundary encoding score.",
            ),
            NeuroFeatureContribution(
                feature_name="cut_count",
                contribution=float(len(context.context.cuts)),
                rationale="More measured transition boundaries increase support.",
            ),
        ],
    )


@register_score(
    NeuroScoreMachineName.reward_anticipation_index,
    "Reward Anticipation Index",
    "Proxy for anticipated reward engagement; not a direct neurotransmitter readout.",
)
def build_reward_anticipation_index(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.reward_anticipation
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != RewardAnticipationPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        pathway_weight = (
            1.0
            if diagnostics.pathway == RewardAnticipationPathway.timeline_dynamics
            else 0.76
        )
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.payoff_windows[:2]
        ]
        if len(evidence_windows) < 3:
            evidence_windows.extend(
                [
                    NeuroEvidenceWindow(
                        start_ms=int(item.start_ms),
                        end_ms=int(item.end_ms),
                        reason=item.reason,
                    )
                    for item in diagnostics.anticipation_ramps[: max(0, 3 - len(evidence_windows))]
                ]
            )
        if not evidence_windows:
            for warning in diagnostics.warnings[:2]:
                if warning.start_ms is None or warning.end_ms is None:
                    continue
                evidence_windows.append(
                    NeuroEvidenceWindow(
                        start_ms=int(warning.start_ms),
                        end_ms=int(warning.end_ms),
                        reason=warning.message,
                    )
                )

        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="reward_anticipation_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Timeline dynamics pathway receives full confidence weight; fallback is downweighted.",
            )
        ]
        if diagnostics.anticipation_strength is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="anticipation_strength",
                    contribution=round(float(diagnostics.anticipation_strength), 6),
                    rationale="Higher ramp strength before payoff windows increases anticipation score.",
                )
            )
        if diagnostics.payoff_release_strength is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="payoff_release_strength",
                    contribution=round(float(diagnostics.payoff_release_strength), 6),
                    rationale="Stronger payoff release relative to setup increases anticipation score.",
                )
            )
        if diagnostics.tension_release_balance is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="tension_release_balance",
                    contribution=round(float(diagnostics.tension_release_balance), 6),
                    rationale="Better balance between setup tension and resolution timing increases confidence.",
                )
            )

        warning_penalty = clamp(1.0 - (0.08 * len(diagnostics.warnings)), 0.6, 1.0)
        top_feature_contributions.append(
            NeuroFeatureContribution(
                feature_name="timing_warning_modifier",
                contribution=round(float(warning_penalty), 6),
                rationale="Late or missing resolution warnings reduce anticipation support.",
            )
        )

        return _score(
            NeuroScoreMachineName.reward_anticipation_index,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.78 if pathway_weight >= 1.0 else 0.58)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    reward_values = _series_values(context.traces.reward_proxy)
    if not reward_values:
        return _score(
            NeuroScoreMachineName.reward_anticipation_index,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    reward_mean = mean_optional(reward_values) or 0.0
    return _score(
        NeuroScoreMachineName.reward_anticipation_index,
        status=NeuroScoreStatus.available,
        scalar_value=reward_mean,
        confidence=_tracking_confidence(context.traces) or 0.65,
        evidence_windows=_series_top_windows(
            context.traces.reward_proxy,
            reason="Top reward proxy windows indicate anticipation peaks.",
            window_ms=context.window_ms,
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="reward_proxy_mean",
                contribution=round(reward_mean / 100.0, 6),
                rationale="Direct mapping from calibrated reward proxy trace.",
            )
        ],
    )


@register_score(
    NeuroScoreMachineName.social_transmission_score,
    "Social Transmission Score",
    "Proxy for potential social handoff based on behavioral and explicit-label patterns.",
)
def build_social_transmission_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.social_transmission
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != SocialTransmissionPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        pathway_weight = {
            SocialTransmissionPathway.annotation_augmented: 1.0,
            SocialTransmissionPathway.timeline_signal_model: 0.84,
            SocialTransmissionPathway.fallback_proxy: 0.64,
            SocialTransmissionPathway.insufficient_data: 0.0,
        }[diagnostics.pathway]
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.segment_scores[:3]
        ]
        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="social_transmission_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Annotation-augmented pathway receives full weight; timeline-only and fallback pathways are downweighted.",
            )
        ]
        if diagnostics.novelty_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="novelty_signal",
                    contribution=round(float(diagnostics.novelty_signal), 6),
                    rationale="Higher novelty concentration increases social handoff support.",
                )
            )
        if diagnostics.identity_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="identity_signaling_signal",
                    contribution=round(float(diagnostics.identity_signal), 6),
                    rationale="Identity-safe signaling language can increase share intent.",
                )
            )
        if diagnostics.usefulness_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="tell_a_friend_usefulness_signal",
                    contribution=round(float(diagnostics.usefulness_signal), 6),
                    rationale="Usefulness and tell-a-friend value increase transmission support.",
                )
            )
        if diagnostics.quote_worthiness_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="quote_comment_worthiness_signal",
                    contribution=round(float(diagnostics.quote_worthiness_signal), 6),
                    rationale="Quote/comment-worthy moments increase social conversation potential.",
                )
            )
        if diagnostics.emotional_activation_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="emotional_activation_signal",
                    contribution=round(float(diagnostics.emotional_activation_signal), 6),
                    rationale="Emotionally activating windows can support sharing behavior.",
                )
            )
        if diagnostics.memorability_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="memorability_signal",
                    contribution=round(float(diagnostics.memorability_signal), 6),
                    rationale="Distinctive moments are more likely to be recalled and discussed.",
                )
            )
        return _score(
            NeuroScoreMachineName.social_transmission_score,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.76 if pathway_weight >= 1.0 else 0.5)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    annotation_summary = context.labels.annotation_summary
    has_annotations = annotation_summary is not None and annotation_summary.total_annotations > 0
    synchrony = (
        float(context.aggregate_metrics.attention_synchrony)
        if context.aggregate_metrics is not None
        and context.aggregate_metrics.attention_synchrony is not None
        else None
    )
    reward_mean = mean_optional(_series_values(context.traces.reward_proxy))
    if not has_annotations and synchrony is None and reward_mean is None:
        return _score(
            NeuroScoreMachineName.social_transmission_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )

    engage_density = 0.0
    engaging_windows: List[NeuroEvidenceWindow] = []
    if annotation_summary is not None and annotation_summary.total_annotations > 0:
        engage_count = (
            annotation_summary.engaging_moment_count + annotation_summary.cta_landed_moment_count
        )
        engage_density = engage_count / float(annotation_summary.total_annotations)
        for marker in annotation_summary.top_engaging_timestamps[:3]:
            engaging_windows.append(
                NeuroEvidenceWindow(
                    start_ms=int(marker.video_time_ms),
                    end_ms=int(marker.video_time_ms) + int(context.window_ms),
                    reason="Explicit engaging marker concentration.",
                )
            )
    synchrony_component = 0.5 if synchrony is None else (synchrony + 1.0) / 2.0
    reward_component = 0.5 if reward_mean is None else clamp(reward_mean / 100.0, 0.0, 1.0)
    scalar = _to_100_from_unit((0.45 * engage_density) + (0.3 * synchrony_component) + (0.25 * reward_component))
    confidence = clamp(
        0.45
        + (0.25 * min((annotation_summary.total_annotations if annotation_summary else 0) / 8.0, 1.0))
        + (0.2 if synchrony is not None else 0.0),
        0.0,
        1.0,
    )
    return _score(
        NeuroScoreMachineName.social_transmission_score,
        status=NeuroScoreStatus.available,
        scalar_value=scalar,
        confidence=confidence,
        evidence_windows=engaging_windows,
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="engaging_marker_density",
                contribution=round(engage_density, 6),
                rationale="More engaging/CTA markers increase transmission proxy.",
            ),
            NeuroFeatureContribution(
                feature_name="attention_synchrony_component",
                contribution=round(synchrony_component, 6),
                rationale="Higher synchrony suggests broader transferability.",
            ),
        ],
    )


@register_score(
    NeuroScoreMachineName.self_relevance_score,
    "Self-Relevance Score",
    "Proxy for personal resonance from explicit and implicit signals.",
)
def build_self_relevance_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.self_relevance
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != SelfRelevancePathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        pathway_weight = {
            SelfRelevancePathway.contextual_personalization: 1.0,
            SelfRelevancePathway.survey_augmented: 0.88,
            SelfRelevancePathway.fallback_proxy: 0.62,
            SelfRelevancePathway.insufficient_data: 0.0,
        }[diagnostics.pathway]
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.segment_scores[:3]
        ]
        if not evidence_windows:
            for warning in diagnostics.warnings[:2]:
                if warning.start_ms is None or warning.end_ms is None:
                    continue
                evidence_windows.append(
                    NeuroEvidenceWindow(
                        start_ms=int(warning.start_ms),
                        end_ms=int(warning.end_ms),
                        reason=warning.message,
                    )
                )

        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="self_relevance_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Contextual personalization pathway has highest support; fallback pathways are downweighted.",
            )
        ]
        if diagnostics.direct_address_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="direct_address_signal",
                    contribution=round(float(diagnostics.direct_address_signal), 6),
                    rationale="Direct address cues increase personal relevance support.",
                )
            )
        if diagnostics.audience_match_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="audience_match_signal",
                    contribution=round(float(diagnostics.audience_match_signal), 6),
                    rationale="Explicit audience metadata overlap increases relevance support within consent boundaries.",
                )
            )
        if diagnostics.niche_specificity_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="niche_specificity_signal",
                    contribution=round(float(diagnostics.niche_specificity_signal), 6),
                    rationale="Niche specificity increases perceived personal fit.",
                )
            )
        if diagnostics.personalization_hook_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="personalization_hook_signal",
                    contribution=round(float(diagnostics.personalization_hook_signal), 6),
                    rationale="Personalization hooks increase self-relevance support.",
                )
            )
        if diagnostics.resonance_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="resonance_signal",
                    contribution=round(float(diagnostics.resonance_signal), 6),
                    rationale="Survey-supported resonance increases confidence in self-relevance.",
                )
            )
        if diagnostics.context_coverage is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="context_coverage",
                    contribution=round(float(diagnostics.context_coverage), 6),
                    rationale="Broader personalization context coverage increases stability of self-relevance estimates.",
                )
            )
        warning_penalty = clamp(1.0 - (0.08 * len(diagnostics.warnings)), 0.6, 1.0)
        top_feature_contributions.append(
            NeuroFeatureContribution(
                feature_name="context_warning_modifier",
                contribution=round(float(warning_penalty), 6),
                rationale="Limited personalization context warnings reduce confidence support.",
            )
        )
        return _score(
            NeuroScoreMachineName.self_relevance_score,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.75 if pathway_weight >= 1.0 else 0.52)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    survey_summary = context.labels.survey_summary
    if survey_summary is None:
        return _score(
            NeuroScoreMachineName.self_relevance_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    values = [
        survey_summary.overall_interest_mean,
        survey_summary.recall_comprehension_mean,
        survey_summary.desire_to_continue_or_take_action_mean,
    ]
    numeric_values = [float(item) for item in values if item is not None]
    if not numeric_values:
        return _score(
            NeuroScoreMachineName.self_relevance_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    avg_response = mean_optional(numeric_values) or 0.0
    scalar = (
        _to_100_from_unit((avg_response - 1.0) / 4.0)
        if avg_response <= 5.0
        else clamp(avg_response, 0.0, 100.0)
    )
    confidence = clamp(0.45 + min(survey_summary.responses_count / 20.0, 0.45), 0.0, 1.0)
    evidence_windows: List[NeuroEvidenceWindow] = []
    if context.labels.annotation_summary is not None:
        for marker in context.labels.annotation_summary.top_engaging_timestamps[:2]:
            evidence_windows.append(
                NeuroEvidenceWindow(
                    start_ms=int(marker.video_time_ms),
                    end_ms=int(marker.video_time_ms) + int(context.window_ms),
                    reason="Engaging timeline markers align with reported resonance.",
                )
            )
    return _score(
        NeuroScoreMachineName.self_relevance_score,
        status=NeuroScoreStatus.available,
        scalar_value=scalar,
        confidence=confidence,
        evidence_windows=evidence_windows,
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="survey_mean_signal",
                contribution=round(avg_response, 6),
                rationale="Derived from post-view survey means.",
            ),
            NeuroFeatureContribution(
                feature_name="survey_response_count",
                contribution=float(survey_summary.responses_count),
                rationale="More survey responses improve confidence.",
            ),
        ],
    )


@register_score(
    NeuroScoreMachineName.cta_reception_score,
    "CTA Reception Score",
    "Proxy for CTA uptake quality around call-to-action windows.",
)
def build_cta_reception_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.cta_reception
        if context.aggregate_metrics is not None
        else None
    )
    pathway_value = _normalized_cta_pathway_value(
        diagnostics.pathway if diagnostics is not None else None
    )
    if (
        diagnostics is not None
        and pathway_value != CtaReceptionPathway.insufficient_data.value
        and diagnostics.global_score is not None
    ):
        pathway_weight = {
            CtaReceptionPathway.multi_signal_model.value: 1.0,
            CtaReceptionPathway.fallback_proxy.value: 0.72,
            CtaReceptionPathway.insufficient_data.value: 0.0,
        }.get(pathway_value, 0.72)
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.cta_windows[:3]
        ]
        if not evidence_windows:
            for flag in diagnostics.flags[:2]:
                if flag.start_ms is None or flag.end_ms is None:
                    continue
                evidence_windows.append(
                    NeuroEvidenceWindow(
                        start_ms=int(flag.start_ms),
                        end_ms=int(flag.end_ms),
                        reason=flag.message,
                    )
                )

        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="cta_reception_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Multi-signal CTA reception has highest support; fallback pathways are downweighted.",
            )
        ]
        if diagnostics.synchrony_support is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="cta_window_synchrony_support",
                    contribution=round(float(diagnostics.synchrony_support), 6),
                    rationale="Higher synchrony around CTA windows increases expected CTA landing quality.",
                )
            )
        if diagnostics.narrative_support is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="cta_window_narrative_support",
                    contribution=round(float(diagnostics.narrative_support), 6),
                    rationale="Narrative coherence around CTA windows supports clearer CTA uptake.",
                )
            )
        if diagnostics.blink_receptivity_support is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="cta_window_blink_receptivity_support",
                    contribution=round(float(diagnostics.blink_receptivity_support), 6),
                    rationale="Lower blink-through likelihood during CTA windows supports reception quality.",
                )
            )
        if diagnostics.reward_timing_support is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="cta_window_reward_timing_support",
                    contribution=round(float(diagnostics.reward_timing_support), 6),
                    rationale="CTA windows aligned with payoff timing improve receptivity support.",
                )
            )
        if diagnostics.boundary_coherence_support is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="cta_window_boundary_coherence_support",
                    contribution=round(float(diagnostics.boundary_coherence_support), 6),
                    rationale="Boundary-coherent CTA placement improves chunking and CTA comprehension support.",
                )
            )
        if diagnostics.overload_risk_support is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="cta_window_overload_resilience",
                    contribution=round(float(diagnostics.overload_risk_support), 6),
                    rationale="Lower payload-overload risk around CTA windows improves landing quality.",
                )
            )

        flag_modifier = clamp(1.0 - (0.08 * len(diagnostics.flags)), 0.58, 1.0)
        top_feature_contributions.append(
            NeuroFeatureContribution(
                feature_name="cta_risk_flag_modifier",
                contribution=round(flag_modifier, 6),
                rationale="Timing, fragmentation, blink-through, or overload flags reduce CTA reception support.",
            )
        )
        return _score(
            NeuroScoreMachineName.cta_reception_score,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.74 if pathway_weight >= 1.0 else 0.52)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    cta_cards = [card for card in context.diagnostics if card.card_type == "cta_receptivity"]
    cta_markers = context.context.cta_markers
    if not cta_cards and not cta_markers:
        return _score(
            NeuroScoreMachineName.cta_reception_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    if cta_cards:
        best_card = max(cta_cards, key=lambda card: card.primary_metric_value)
        scalar = clamp(float(best_card.primary_metric_value), 0.0, 100.0)
        confidence = (
            clamp(float(best_card.confidence), 0.0, 1.0)
            if best_card.confidence is not None
            else 0.65
        )
        _ew_start = int(best_card.start_video_time_ms)
        _ew_end = int(best_card.end_video_time_ms)
        evidence = (
            [
                NeuroEvidenceWindow(
                    start_ms=_ew_start,
                    end_ms=_ew_end,
                    reason=best_card.why_flagged,
                )
            ]
            if _ew_end > _ew_start
            else []
        )
        return _score(
            NeuroScoreMachineName.cta_reception_score,
            status=NeuroScoreStatus.available,
            scalar_value=scalar,
            confidence=confidence,
            evidence_windows=evidence,
            top_feature_contributions=[
                NeuroFeatureContribution(
                    feature_name="cta_receptivity_diagnostic",
                    contribution=round(scalar / 100.0, 6),
                    rationale="Derived from CTA diagnostic card output.",
                )
            ],
        )

    reward_points = [point for point in context.traces.reward_proxy if point.value is not None]
    if not reward_points:
        return _score(
            NeuroScoreMachineName.cta_reception_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    cta_reward_values: List[float] = []
    evidence_windows: List[NeuroEvidenceWindow] = []
    for marker in cta_markers[:3]:
        nearest = min(
            reward_points,
            key=lambda point: abs(int(point.video_time_ms) - int(marker.video_time_ms)),
        )
        cta_reward_values.append(float(nearest.value or 0.0))
        evidence_windows.append(
            NeuroEvidenceWindow(
                start_ms=max(int(marker.video_time_ms) - int(context.window_ms), 0),
                end_ms=int(marker.video_time_ms) + int(context.window_ms),
                reason="CTA marker window with nearest reward proxy support.",
            )
        )
    scalar = mean_optional(cta_reward_values) or 0.0
    return _score(
        NeuroScoreMachineName.cta_reception_score,
        status=NeuroScoreStatus.available,
        scalar_value=scalar,
        confidence=_tracking_confidence(context.traces) or 0.6,
        evidence_windows=evidence_windows,
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="cta_window_reward_proxy_mean",
                contribution=round(scalar / 100.0, 6),
                rationale="Higher reward around CTA windows increases reception score.",
            )
        ],
    )


def _normalized_cta_pathway_value(pathway: Any) -> str:
    if isinstance(pathway, CtaReceptionPathway):
        return pathway.value
    if pathway is None:
        return ""
    return str(pathway).strip().lower()


@register_score(
    NeuroScoreMachineName.synthetic_lift_prior,
    "Synthetic Lift Prior",
    "Synthetic prior for directional lift potential before external incrementality validation.",
)
def build_synthetic_lift_prior(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.synthetic_lift_prior
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != SyntheticLiftPriorPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        pathway_weight = {
            SyntheticLiftPriorPathway.taxonomy_regression: 1.0,
            SyntheticLiftPriorPathway.fallback_proxy: 0.72,
            SyntheticLiftPriorPathway.insufficient_data: 0.0,
        }[diagnostics.pathway]
        calibration_weight = {
            "geox_calibrated": 1.0,
            "provisional": 0.82,
            "uncalibrated": 0.68,
            "truth_layer_unavailable": 0.62,
        }.get(diagnostics.calibration_status.value, 0.62)
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.segment_scores[:3]
        ]
        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="synthetic_lift_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Structured pathway weighting reflects model input quality and fallback usage.",
            ),
            NeuroFeatureContribution(
                feature_name="synthetic_lift_calibration_weight",
                contribution=round(calibration_weight, 6),
                rationale="Calibration status reflects distance between predicted prior and measured incrementality truth updates.",
            ),
        ]
        if diagnostics.predicted_incremental_lift_pct is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="predicted_incremental_lift_pct",
                    contribution=round(
                        clamp(float(diagnostics.predicted_incremental_lift_pct) / 25.0, -1.0, 1.0),
                        6,
                    ),
                    rationale="Directional predicted incremental lift prior (not measured lift).",
                )
            )
        if diagnostics.predicted_iroas is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="predicted_iroas_prior",
                    contribution=round(clamp(float(diagnostics.predicted_iroas) / 4.0, -1.0, 1.0), 6),
                    rationale="Directional iROAS prior before truth-layer calibration confirms causal lift.",
                )
            )
        for item in diagnostics.feature_inputs[:3]:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name=item.feature_name,
                    contribution=round(item.normalized_value * item.weight, 6),
                    rationale="Model input surfaced from synthetic-lift diagnostics.",
                )
            )

        combined_confidence = clamp(
            float(diagnostics.confidence or 0.0) * pathway_weight * calibration_weight,
            0.0,
            1.0,
        )
        return _score(
            NeuroScoreMachineName.synthetic_lift_prior,
            status=NeuroScoreStatus.available,
            scalar_value=diagnostics.global_score,
            confidence=combined_confidence,
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    golden = context.segments.golden_scenes
    dead = context.segments.dead_zones
    if not golden and not dead:
        return _score(
            NeuroScoreMachineName.synthetic_lift_prior,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    golden_mean = mean_optional([float(segment.magnitude) for segment in golden]) or 0.0
    dead_mean = mean_optional([float(segment.magnitude) for segment in dead]) or 0.0
    scalar = clamp(50.0 + ((golden_mean - dead_mean) * 5.0), 0.0, 100.0)
    confidence = clamp(0.5 + (0.05 * min(len(golden) + len(dead), 5)), 0.0, 1.0)
    return _score(
        NeuroScoreMachineName.synthetic_lift_prior,
        status=NeuroScoreStatus.available,
        scalar_value=scalar,
        confidence=confidence,
        evidence_windows=_segment_windows(
            golden if golden else dead,
            reason="Segment balance informs synthetic lift prior.",
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="golden_scene_magnitude_mean",
                contribution=round(golden_mean, 6),
                rationale="Higher golden-scene magnitude increases synthetic lift prior.",
            ),
            NeuroFeatureContribution(
                feature_name="dead_zone_magnitude_mean",
                contribution=round(-dead_mean, 6),
                rationale="Higher dead-zone magnitude suppresses synthetic lift prior.",
            ),
        ],
    )


@register_score(
    NeuroScoreMachineName.au_friction_score,
    "AU Friction Score",
    "Diagnostic AU-level friction proxy, not a standalone truth label.",
)
def build_au_friction_score(context: NeuroScoreComputationContext) -> NeuroScoreContract:
    diagnostics = (
        context.aggregate_metrics.au_friction
        if context.aggregate_metrics is not None
        else None
    )
    if (
        diagnostics is not None
        and diagnostics.pathway != AuFrictionPathway.insufficient_data
        and diagnostics.global_score is not None
    ):
        pathway_weight = {
            AuFrictionPathway.au_signal_model: 1.0,
            AuFrictionPathway.fallback_proxy: 0.68,
            AuFrictionPathway.insufficient_data: 0.0,
        }[diagnostics.pathway]
        evidence_windows = [
            NeuroEvidenceWindow(
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                reason=item.reason,
            )
            for item in diagnostics.segment_scores[:3]
        ]
        if not evidence_windows:
            for warning in diagnostics.warnings[:2]:
                if warning.start_ms is None or warning.end_ms is None:
                    continue
                evidence_windows.append(
                    NeuroEvidenceWindow(
                        start_ms=int(warning.start_ms),
                        end_ms=int(warning.end_ms),
                        reason=warning.message,
                    )
                )

        top_feature_contributions = [
            NeuroFeatureContribution(
                feature_name="au_friction_pathway_weight",
                contribution=round(pathway_weight, 6),
                rationale="Direct AU-signal pathway has highest support; fallback pathway is downweighted.",
            )
        ]
        if diagnostics.confusion_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="au_confusion_signal",
                    contribution=round(float(diagnostics.confusion_signal), 6),
                    rationale="AU confusion signal supports diagnostic friction interpretation.",
                )
            )
        if diagnostics.strain_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="au_strain_signal",
                    contribution=round(float(diagnostics.strain_signal), 6),
                    rationale="AU strain signal contributes to friction interpretation.",
                )
            )
        if diagnostics.tension_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="au_tension_signal",
                    contribution=round(float(diagnostics.tension_signal), 6),
                    rationale="AU tension signal contributes to friction interpretation.",
                )
            )
        if diagnostics.resistance_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="au_resistance_signal",
                    contribution=round(float(diagnostics.resistance_signal), 6),
                    rationale="AU resistance signal contributes to friction interpretation.",
                )
            )
        if diagnostics.amusement_signal is not None:
            top_feature_contributions.append(
                NeuroFeatureContribution(
                    feature_name="au_amusement_signal",
                    contribution=round(float(diagnostics.amusement_signal), 6),
                    rationale="AU amusement signal can offset high-friction interpretation in some windows.",
                )
            )
        quality_modifier = clamp(1.0 - (0.08 * len(diagnostics.warnings)), 0.55, 1.0)
        top_feature_contributions.append(
            NeuroFeatureContribution(
                feature_name="face_input_quality_modifier",
                contribution=round(quality_modifier, 6),
                rationale="Head pose, occlusion, lighting, and missing-face warnings reduce confidence support.",
            )
        )
        return _score(
            NeuroScoreMachineName.au_friction_score,
            status=NeuroScoreStatus.available,
            scalar_value=float(diagnostics.global_score),
            confidence=(
                float(diagnostics.confidence)
                if diagnostics.confidence is not None
                else (0.72 if pathway_weight >= 1.0 else 0.5)
            ),
            evidence_windows=evidence_windows,
            top_feature_contributions=top_feature_contributions,
        )

    confusion_segments = context.segments.confusion_segments
    au4_channel = next(
        (channel for channel in context.traces.au_channels if channel.au_name == "AU04"),
        None,
    )
    au4_mean = mean_optional(_series_values(au4_channel.points)) if au4_channel is not None else None
    confusion_mean = (
        mean_optional([float(segment.magnitude) for segment in confusion_segments])
        if confusion_segments
        else None
    )
    if au4_mean is None and confusion_mean is None:
        return _score(
            NeuroScoreMachineName.au_friction_score,
            status=NeuroScoreStatus.insufficient_data,
            scalar_value=None,
            confidence=None,
        )
    au4_component = _to_100_from_unit(au4_mean or 0.0)
    confusion_component = clamp((confusion_mean or 0.0) * 20.0, 0.0, 100.0)
    scalar = (0.55 * confusion_component) + (0.45 * au4_component)
    return _score(
        NeuroScoreMachineName.au_friction_score,
        status=NeuroScoreStatus.available,
        scalar_value=scalar,
        confidence=_tracking_confidence(context.traces) or 0.58,
        evidence_windows=_segment_windows(
            confusion_segments,
            reason="Confusion segments indicate AU-linked friction windows.",
        ),
        top_feature_contributions=[
            NeuroFeatureContribution(
                feature_name="confusion_segment_magnitude",
                contribution=round(confusion_mean or 0.0, 6),
                rationale="Higher confusion segment magnitude increases AU friction proxy score.",
            ),
            NeuroFeatureContribution(
                feature_name="au04_mean",
                contribution=round(au4_mean or 0.0, 6),
                rationale="Higher AU04 trace contributes to AU friction proxy in fallback mode.",
            ),
        ],
    )


def _weighted_rollup(
    scores: Dict[NeuroScoreMachineName, NeuroScoreContract],
    weights: Dict[NeuroScoreMachineName, float],
) -> tuple[NeuroScoreStatus, Optional[float], Optional[float]]:
    weighted_sum = 0.0
    weight_total = 0.0
    confidence_sum = 0.0
    confidence_weight_total = 0.0
    for machine_name, weight in weights.items():
        score = scores[machine_name]
        if score.status != NeuroScoreStatus.available or score.scalar_value is None:
            continue
        numeric_weight = max(float(weight), 0.0)
        weighted_sum += float(score.scalar_value) * numeric_weight
        weight_total += numeric_weight
        if score.confidence is not None:
            confidence_sum += float(score.confidence) * numeric_weight
            confidence_weight_total += numeric_weight
    if weight_total <= 0:
        return NeuroScoreStatus.insufficient_data, None, None
    scalar = weighted_sum / weight_total
    confidence = (
        confidence_sum / confidence_weight_total
        if confidence_weight_total > 0
        else None
    )
    return NeuroScoreStatus.available, scalar, confidence


@register_rollup(
    NeuroRollupMachineName.organic_reach_prior,
    "Organic Reach Prior",
    "Composite prior for organic spread potential.",
)
def build_organic_reach_prior(context: NeuroRollupComputationContext) -> NeuroCompositeRollup:
    weights = {
        NeuroScoreMachineName.arrest_score: 0.25,
        NeuroScoreMachineName.narrative_control_score: 0.2,
        NeuroScoreMachineName.self_relevance_score: 0.2,
        NeuroScoreMachineName.social_transmission_score: 0.2,
        NeuroScoreMachineName.cta_reception_score: 0.15,
    }
    status, scalar, confidence = _weighted_rollup(context.scores, weights)
    return _rollup(
        NeuroRollupMachineName.organic_reach_prior,
        status=status,
        scalar_value=scalar,
        confidence=confidence,
        component_weights={item.value: weight for item, weight in weights.items()},
        component_scores=list(weights.keys()),
    )


@register_rollup(
    NeuroRollupMachineName.paid_lift_prior,
    "Paid Lift Prior",
    "Composite prior for paid media lift potential.",
)
def build_paid_lift_prior(context: NeuroRollupComputationContext) -> NeuroCompositeRollup:
    weights = {
        NeuroScoreMachineName.synthetic_lift_prior: 0.3,
        NeuroScoreMachineName.cta_reception_score: 0.25,
        NeuroScoreMachineName.reward_anticipation_index: 0.2,
        NeuroScoreMachineName.attentional_synchrony_index: 0.15,
        NeuroScoreMachineName.arrest_score: 0.1,
    }
    status, scalar, confidence = _weighted_rollup(context.scores, weights)
    return _rollup(
        NeuroRollupMachineName.paid_lift_prior,
        status=status,
        scalar_value=scalar,
        confidence=confidence,
        component_weights={item.value: weight for item, weight in weights.items()},
        component_scores=list(weights.keys()),
    )


@register_rollup(
    NeuroRollupMachineName.brand_memory_prior,
    "Brand Memory Prior",
    "Composite prior for memory encoding and later recall potential.",
)
def build_brand_memory_prior(context: NeuroRollupComputationContext) -> NeuroCompositeRollup:
    weights = {
        NeuroScoreMachineName.boundary_encoding_score: 0.25,
        NeuroScoreMachineName.narrative_control_score: 0.25,
        NeuroScoreMachineName.self_relevance_score: 0.2,
        NeuroScoreMachineName.reward_anticipation_index: 0.15,
        NeuroScoreMachineName.blink_transport_score: 0.15,
    }
    status, scalar, confidence = _weighted_rollup(context.scores, weights)
    return _rollup(
        NeuroRollupMachineName.brand_memory_prior,
        status=status,
        scalar_value=scalar,
        confidence=confidence,
        component_weights={item.value: weight for item, weight in weights.items()},
        component_scores=list(weights.keys()),
    )


def build_legacy_score_adapters(
    scores: Dict[NeuroScoreMachineName, NeuroScoreContract],
) -> List[LegacyScoreAdapter]:
    attention = scores[NeuroScoreMachineName.arrest_score]
    emotion = scores[NeuroScoreMachineName.reward_anticipation_index]
    return [
        LegacyScoreAdapter(
            legacy_output="attention",
            mapped_machine_name=NeuroScoreMachineName.arrest_score,
            scalar_value=attention.scalar_value,
            confidence=attention.confidence,
            status=attention.status,
            notes="Legacy attention surfaces can map to arrest_score during migration.",
        ),
        LegacyScoreAdapter(
            legacy_output="emotion",
            mapped_machine_name=NeuroScoreMachineName.reward_anticipation_index,
            scalar_value=emotion.scalar_value,
            confidence=emotion.confidence,
            status=emotion.status,
            notes=(
                "Deprecated legacy emotion surfaces can map to reward_anticipation_index during migration; "
                "new facial diagnostics should use AU-level traces and au_friction_score."
            ),
        ),
    ]


def list_score_registry_entries() -> List[NeuroScoreRegistryEntry]:
    return [
        NeuroScoreRegistryEntry(
            machine_name=definition.machine_name,
            display_label=definition.display_label,
            claim_safe_description=definition.claim_safe_description,
            builder_key=definition.builder_key,
        )
        for definition in _SCORE_REGISTRY.values()
    ]


def list_rollup_registry_entries() -> List[NeuroRollupRegistryEntry]:
    return [
        NeuroRollupRegistryEntry(
            machine_name=definition.machine_name,
            display_label=definition.display_label,
            claim_safe_description=definition.claim_safe_description,
            builder_key=definition.builder_key,
        )
        for definition in _ROLLUP_REGISTRY.values()
    ]


def build_neuro_score_taxonomy(
    traces: ReadoutTraces,
    segments: ReadoutSegments,
    diagnostics: Sequence[SceneDiagnosticCard],
    labels: ReadoutLabels,
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
    context: ReadoutContext,
    window_ms: int,
    schema_version: str = "1.0.0",
) -> NeuroScoreTaxonomy:
    score_context = NeuroScoreComputationContext(
        traces=traces,
        segments=segments,
        diagnostics=diagnostics,
        labels=labels,
        aggregate_metrics=aggregate_metrics,
        context=context,
        window_ms=window_ms,
    )
    score_order = [
        NeuroScoreMachineName.arrest_score,
        NeuroScoreMachineName.attentional_synchrony_index,
        NeuroScoreMachineName.narrative_control_score,
        NeuroScoreMachineName.blink_transport_score,
        NeuroScoreMachineName.boundary_encoding_score,
        NeuroScoreMachineName.reward_anticipation_index,
        NeuroScoreMachineName.social_transmission_score,
        NeuroScoreMachineName.self_relevance_score,
        NeuroScoreMachineName.cta_reception_score,
        NeuroScoreMachineName.synthetic_lift_prior,
        NeuroScoreMachineName.au_friction_score,
    ]
    scores_by_name: Dict[NeuroScoreMachineName, NeuroScoreContract] = {}
    for machine_name in score_order:
        definition = _SCORE_REGISTRY[machine_name]
        try:
            built_score = definition.builder(score_context)
            if not isinstance(built_score, NeuroScoreContract):
                raise TypeError(
                    f"Score builder '{definition.builder_key}' returned "
                    f"{type(built_score).__name__}, expected NeuroScoreContract"
                )
        except Exception:
            logger.exception(
                "Neuro score builder failed; falling back to unavailable score contract",
                extra={"score_machine_name": machine_name.value, "builder_key": definition.builder_key},
            )
            built_score = _score(
                machine_name=machine_name,
                status=NeuroScoreStatus.unavailable,
                scalar_value=None,
                confidence=0.0,
                evidence_windows=[
                    NeuroEvidenceWindow(
                        start_ms=0,
                        end_ms=max(int(window_ms), 1),
                        reason="Score unavailable due to internal module fallback.",
                    )
                ],
                top_feature_contributions=[
                    NeuroFeatureContribution(
                        feature_name="score_module_fallback",
                        contribution=-1.0,
                        rationale="Internal score module failed during composition; fallback applied.",
                    )
                ],
            )
        scores_by_name[machine_name] = built_score

    score_families = NeuroScoreFamilies(
        arrest_score=scores_by_name[NeuroScoreMachineName.arrest_score],
        attentional_synchrony_index=scores_by_name[
            NeuroScoreMachineName.attentional_synchrony_index
        ],
        narrative_control_score=scores_by_name[NeuroScoreMachineName.narrative_control_score],
        blink_transport_score=scores_by_name[NeuroScoreMachineName.blink_transport_score],
        boundary_encoding_score=scores_by_name[NeuroScoreMachineName.boundary_encoding_score],
        reward_anticipation_index=scores_by_name[
            NeuroScoreMachineName.reward_anticipation_index
        ],
        social_transmission_score=scores_by_name[
            NeuroScoreMachineName.social_transmission_score
        ],
        self_relevance_score=scores_by_name[NeuroScoreMachineName.self_relevance_score],
        cta_reception_score=scores_by_name[NeuroScoreMachineName.cta_reception_score],
        synthetic_lift_prior=scores_by_name[NeuroScoreMachineName.synthetic_lift_prior],
        au_friction_score=scores_by_name[NeuroScoreMachineName.au_friction_score],
    )

    rollup_context = NeuroRollupComputationContext(scores=scores_by_name)
    rollup_families = NeuroRollupFamilies(
        organic_reach_prior=_ROLLUP_REGISTRY[
            NeuroRollupMachineName.organic_reach_prior
        ].builder(rollup_context),
        paid_lift_prior=_ROLLUP_REGISTRY[NeuroRollupMachineName.paid_lift_prior].builder(
            rollup_context
        ),
        brand_memory_prior=_ROLLUP_REGISTRY[
            NeuroRollupMachineName.brand_memory_prior
        ].builder(rollup_context),
    )

    return NeuroScoreTaxonomy(
        schema_version=schema_version,
        scores=score_families,
        rollups=rollup_families,
        registry=list_score_registry_entries(),
        rollup_registry=list_rollup_registry_entries(),
        legacy_score_adapters=build_legacy_score_adapters(scores_by_name),
    )
