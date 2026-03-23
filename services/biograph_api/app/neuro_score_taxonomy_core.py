"""Neuro-score taxonomy core: registries, dataclasses, and private helpers."""

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
