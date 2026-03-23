"""Neuro-score taxonomy — rollup builders and main entry point."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

from .readout_metrics import clamp

from .schemas import (
    LegacyScoreAdapter,
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
    ReadoutSegments,
    ReadoutTraces,
    SceneDiagnosticCard,
)

from .neuro_score_taxonomy_core import (
    NeuroRollupComputationContext,
    NeuroScoreComputationContext,
    _ROLLUP_REGISTRY,
    _SCORE_REGISTRY,
    _rollup,
    _score,
    register_rollup,
)

# Force registration of all score builders by importing the submodules.
from . import neuro_score_taxonomy_attention as _attention_mod  # noqa: F401
from . import neuro_score_taxonomy_reward as _reward_mod  # noqa: F401

logger = logging.getLogger(__name__)


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
