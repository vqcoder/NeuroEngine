"""Product-facing rollup presentations derived from shared neuro score taxonomy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import get_settings
from .schemas import (
    CtaReceptionFlagSeverity,
    NeuroCompositeRollup,
    NeuroRollupMachineName,
    NeuroScoreContract,
    NeuroScoreMachineName,
    NeuroScoreStatus,
    NeuroScoreTaxonomy,
    ProductLiftComparison,
    ProductLiftTruthStatus,
    ProductRollupMode,
    ProductRollupPresentation,
    ProductRollupWarning,
    ProductRollupWarningSeverity,
    ProductScoreSummary,
    ReadoutAggregateMetrics,
    ReadoutSegment,
    SceneDiagnosticCard,
    CreatorProductRollups,
    EnterpriseDecisionSupport,
    EnterpriseProductRollups,
)


@dataclass(frozen=True)
class _ModeRule:
    default_mode: ProductRollupMode
    enabled_modes: Tuple[ProductRollupMode, ...]


@dataclass(frozen=True)
class _ModeResolution:
    mode: ProductRollupMode
    workspace_tier: str
    enabled_modes: Tuple[ProductRollupMode, ...]
    note: Optional[str]


_DEFAULT_MODE_RULES: Dict[str, _ModeRule] = {
    "creator": _ModeRule(
        default_mode=ProductRollupMode.creator,
        enabled_modes=(ProductRollupMode.creator,),
    ),
    "enterprise": _ModeRule(
        default_mode=ProductRollupMode.enterprise,
        enabled_modes=(ProductRollupMode.creator, ProductRollupMode.enterprise),
    ),
}


def _parse_json_object(value: str) -> Dict[str, Any]:
    candidate = value.strip()
    if not candidate:
        return {}
    try:
        loaded = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_mode(value: Any) -> Optional[ProductRollupMode]:
    if value is None:
        return None
    if isinstance(value, ProductRollupMode):
        return value
    normalized = str(value).strip().lower()
    if normalized == ProductRollupMode.creator.value:
        return ProductRollupMode.creator
    if normalized == ProductRollupMode.enterprise.value:
        return ProductRollupMode.enterprise
    return None


def _resolve_workspace_tier(
    video_metadata: Optional[Mapping[str, Any]],
    requested_workspace_tier: Optional[str],
) -> str:
    if requested_workspace_tier:
        return requested_workspace_tier.strip().lower()
    if not isinstance(video_metadata, Mapping):
        return get_settings().product_rollup_default_tier.strip().lower() or "creator"

    for key in (
        "workspace_tier",
        "workspaceTier",
        "account_tier",
        "accountTier",
        "plan_tier",
        "planTier",
    ):
        raw = video_metadata.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lower()
    return get_settings().product_rollup_default_tier.strip().lower() or "creator"


def _resolve_mode_rules() -> Dict[str, _ModeRule]:
    rules = dict(_DEFAULT_MODE_RULES)
    overrides = _parse_json_object(get_settings().product_rollup_tier_modes_json)
    for tier, payload in overrides.items():
        if not isinstance(tier, str) or not isinstance(payload, Mapping):
            continue
        default_mode = _normalize_mode(payload.get("default_mode"))
        enabled = payload.get("enabled_modes")
        enabled_modes: List[ProductRollupMode] = []
        if isinstance(enabled, Sequence) and not isinstance(enabled, (str, bytes)):
            for item in enabled:
                normalized = _normalize_mode(item)
                if normalized is not None and normalized not in enabled_modes:
                    enabled_modes.append(normalized)
        if default_mode is None:
            default_mode = enabled_modes[0] if enabled_modes else None
        if default_mode is None:
            continue
        if not enabled_modes:
            enabled_modes = [default_mode]
        if default_mode not in enabled_modes:
            enabled_modes.insert(0, default_mode)
        rules[tier.strip().lower()] = _ModeRule(
            default_mode=default_mode,
            enabled_modes=tuple(enabled_modes),
        )
    return rules


def _resolve_mode(
    *,
    video_metadata: Optional[Mapping[str, Any]],
    requested_mode: Optional[ProductRollupMode],
    requested_workspace_tier: Optional[str],
) -> _ModeResolution:
    workspace_tier = _resolve_workspace_tier(video_metadata, requested_workspace_tier)
    rules = _resolve_mode_rules()
    rule = rules.get(workspace_tier)
    note: Optional[str] = None
    if rule is None:
        default_tier = get_settings().product_rollup_default_tier.strip().lower() or "creator"
        rule = rules.get(default_tier, _DEFAULT_MODE_RULES["creator"])
        note = (
            f"Tier '{workspace_tier}' is not configured; using '{default_tier}' mode policy."
        )

    mode = requested_mode or rule.default_mode
    if mode not in rule.enabled_modes:
        note = (
            f"Requested mode '{mode.value}' is disabled for tier '{workspace_tier}'; "
            f"using '{rule.default_mode.value}'."
        )
        mode = rule.default_mode

    return _ModeResolution(
        mode=mode,
        workspace_tier=workspace_tier,
        enabled_modes=rule.enabled_modes,
        note=note,
    )


def _as_score_summary(
    *,
    metric_key: str,
    display_label: str,
    score: Optional[NeuroScoreContract],
    rollup: Optional[NeuroCompositeRollup],
    explanation: str,
    source_metrics: Sequence[str],
) -> ProductScoreSummary:
    candidate_status = NeuroScoreStatus.insufficient_data
    scalar_value: Optional[float] = None
    confidence: Optional[float] = None
    if score is not None:
        candidate_status = score.status
        scalar_value = score.scalar_value
        confidence = score.confidence
    elif rollup is not None:
        candidate_status = rollup.status
        scalar_value = rollup.scalar_value
        confidence = rollup.confidence

    return ProductScoreSummary(
        metric_key=metric_key,
        display_label=display_label,
        scalar_value=scalar_value,
        confidence=confidence,
        status=candidate_status,
        explanation=explanation,
        source_metrics=list(source_metrics),
    )


def _weighted_composite(
    *,
    metric_key: str,
    display_label: str,
    source_scores: Sequence[Tuple[NeuroScoreContract, float]],
    explanation: str,
    source_metrics: Sequence[str],
) -> ProductScoreSummary:
    weighted_sum = 0.0
    total_weight = 0.0
    confidence_sum = 0.0
    confidence_weight = 0.0
    for score, weight in source_scores:
        if score.status != NeuroScoreStatus.available or score.scalar_value is None:
            continue
        safe_weight = max(float(weight), 0.0)
        weighted_sum += float(score.scalar_value) * safe_weight
        total_weight += safe_weight
        if score.confidence is not None:
            confidence_sum += float(score.confidence) * safe_weight
            confidence_weight += safe_weight

    if total_weight <= 0:
        return ProductScoreSummary(
            metric_key=metric_key,
            display_label=display_label,
            scalar_value=None,
            confidence=None,
            status=NeuroScoreStatus.insufficient_data,
            explanation=explanation,
            source_metrics=list(source_metrics),
        )

    confidence = (
        confidence_sum / confidence_weight if confidence_weight > 0 else None
    )
    return ProductScoreSummary(
        metric_key=metric_key,
        display_label=display_label,
        scalar_value=weighted_sum / total_weight,
        confidence=confidence,
        status=NeuroScoreStatus.available,
        explanation=explanation,
        source_metrics=list(source_metrics),
    )


def _creator_warnings(
    *,
    diagnostics: Sequence[SceneDiagnosticCard],
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
) -> List[ProductRollupWarning]:
    warnings: List[ProductRollupWarning] = []

    hook = next((item for item in diagnostics if item.card_type == "hook_strength"), None)
    if hook is not None and hook.primary_metric_value < 55.0:
        warnings.append(
            ProductRollupWarning(
                warning_key="weak_hook",
                severity=ProductRollupWarningSeverity.high,
                message=(
                    "Opening hook underperformed. Tighten the first 1-3 seconds so viewers "
                    "stabilize earlier."
                ),
                source_metrics=[
                    NeuroScoreMachineName.arrest_score.value,
                    NeuroScoreMachineName.narrative_control_score.value,
                ],
            )
        )

    synchrony_score: Optional[float] = None
    if (
        aggregate_metrics is not None
        and aggregate_metrics.attentional_synchrony is not None
        and aggregate_metrics.attentional_synchrony.global_score is not None
    ):
        synchrony_score = float(aggregate_metrics.attentional_synchrony.global_score)
    if synchrony_score is not None and synchrony_score < 52.0:
        warnings.append(
            ProductRollupWarning(
                warning_key="low_synchrony",
                severity=ProductRollupWarningSeverity.medium,
                message=(
                    "Viewer focus appears dispersed. Strengthen focal hierarchy around key moments."
                ),
                source_metrics=[NeuroScoreMachineName.attentional_synchrony_index.value],
            )
        )

    if aggregate_metrics is not None and aggregate_metrics.reward_anticipation is not None:
        poor_timing = [
            warning
            for warning in aggregate_metrics.reward_anticipation.warnings
            if warning.warning_key in {"late_resolution", "no_resolution", "unresolved_tension"}
        ]
        if poor_timing:
            warnings.append(
                ProductRollupWarning(
                    warning_key="poor_payoff_timing",
                    severity=ProductRollupWarningSeverity.medium,
                    message=(
                        "Setup and payoff timing may be misaligned; resolution is likely too late "
                        "or too weak."
                    ),
                    source_metrics=[NeuroScoreMachineName.reward_anticipation_index.value],
                )
            )

    if aggregate_metrics is not None and aggregate_metrics.cta_reception is not None:
        collapse_flags = [
            flag
            for flag in aggregate_metrics.cta_reception.flags
            if flag.severity == CtaReceptionFlagSeverity.high
            or flag.flag_key in {"cta_after_fragmentation", "cta_after_collapse", "cta_missed_reward_window"}
        ]
        if collapse_flags:
            warnings.append(
                ProductRollupWarning(
                    warning_key="cta_collapse",
                    severity=ProductRollupWarningSeverity.high,
                    message=(
                        "CTA likely lands after engagement collapse or fragmentation. Move CTA closer "
                        "to coherent payoff."
                    ),
                    source_metrics=[NeuroScoreMachineName.cta_reception_score.value],
                )
            )

    return warnings


def _extract_measured_lift(
    video_metadata: Optional[Mapping[str, Any]],
) -> tuple[ProductLiftTruthStatus, Optional[float], Optional[float], str]:
    if not isinstance(video_metadata, Mapping):
        return (
            ProductLiftTruthStatus.unavailable,
            None,
            None,
            "Measured GeoX/holdout lift is unavailable for this asset; use synthetic prior as directional.",
        )

    measured_incremental: Optional[float] = None
    measured_iroas: Optional[float] = None

    for key in ("measured_incremental_lift_pct", "measuredLiftPct", "geox_incremental_lift_pct"):
        raw = video_metadata.get(key)
        if isinstance(raw, (int, float)):
            measured_incremental = float(raw)
            break

    for key in ("measured_iroas", "measuredIROAS", "geox_iroas"):
        raw = video_metadata.get(key)
        if isinstance(raw, (int, float)):
            measured_iroas = float(raw)
            break

    measured_payload = video_metadata.get("measured_lift")
    if isinstance(measured_payload, Mapping):
        if measured_incremental is None and isinstance(
            measured_payload.get("incremental_lift_pct"), (int, float)
        ):
            measured_incremental = float(measured_payload["incremental_lift_pct"])
        if measured_iroas is None and isinstance(
            measured_payload.get("iroas"), (int, float)
        ):
            measured_iroas = float(measured_payload["iroas"])

    if measured_incremental is not None or measured_iroas is not None:
        return (
            ProductLiftTruthStatus.measured,
            measured_incremental,
            measured_iroas,
            "Measured GeoX/holdout results are available; use measured lift as truth calibration.",
        )

    geox_pending = video_metadata.get("geox_status")
    if isinstance(geox_pending, str) and geox_pending.strip().lower() in {"pending", "running"}:
        return (
            ProductLiftTruthStatus.pending,
            None,
            None,
            "GeoX/holdout measurement is in progress; synthetic prior remains provisional.",
        )

    return (
        ProductLiftTruthStatus.unavailable,
        None,
        None,
        "Measured GeoX/holdout lift is unavailable for this asset; use synthetic prior as directional.",
    )


def _build_creator_payload(
    *,
    taxonomy: NeuroScoreTaxonomy,
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
    diagnostics: Sequence[SceneDiagnosticCard],
) -> CreatorProductRollups:
    scores = taxonomy.scores
    reception = _weighted_composite(
        metric_key="reception_score",
        display_label="Reception Score",
        source_scores=[
            (scores.cta_reception_score, 0.45),
            (scores.arrest_score, 0.2),
            (scores.attentional_synchrony_index, 0.2),
            (scores.reward_anticipation_index, 0.15),
        ],
        explanation=(
            "Blend of CTA reception, arrest, synchrony, and reward anticipation to summarize likely "
            "viewer reception."
        ),
        source_metrics=[
            NeuroScoreMachineName.cta_reception_score.value,
            NeuroScoreMachineName.arrest_score.value,
            NeuroScoreMachineName.attentional_synchrony_index.value,
            NeuroScoreMachineName.reward_anticipation_index.value,
        ],
    )
    organic = _as_score_summary(
        metric_key="organic_reach_prior",
        display_label="Organic Reach Prior",
        score=None,
        rollup=taxonomy.rollups.organic_reach_prior,
        explanation=(
            "Directional prior for share and pass-along potential from the underlying score taxonomy."
        ),
        source_metrics=[NeuroRollupMachineName.organic_reach_prior.value],
    )
    return CreatorProductRollups(
        reception_score=reception,
        organic_reach_prior=organic,
        explanations=[
            "Reception Score is a presentation-layer blend over existing taxonomy scores.",
            "Organic Reach Prior is sourced directly from taxonomy rollups, not a separate model.",
            "Warnings highlight likely failure points for hook, synchrony, payoff timing, and CTA timing.",
        ],
        warnings=_creator_warnings(
            diagnostics=diagnostics,
            aggregate_metrics=aggregate_metrics,
        ),
    )


def _build_enterprise_payload(
    *,
    taxonomy: NeuroScoreTaxonomy,
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
    video_metadata: Optional[Mapping[str, Any]],
) -> EnterpriseProductRollups:
    paid = _as_score_summary(
        metric_key="paid_lift_prior",
        display_label="Paid Lift Prior",
        score=None,
        rollup=taxonomy.rollups.paid_lift_prior,
        explanation="Directional paid-media lift prior from shared taxonomy rollups.",
        source_metrics=[NeuroRollupMachineName.paid_lift_prior.value],
    )
    brand = _as_score_summary(
        metric_key="brand_memory_prior",
        display_label="Brand Memory Prior",
        score=None,
        rollup=taxonomy.rollups.brand_memory_prior,
        explanation="Directional memory encoding prior from boundary, narrative, and relevance signals.",
        source_metrics=[NeuroRollupMachineName.brand_memory_prior.value],
    )
    cta = _as_score_summary(
        metric_key="cta_reception_score",
        display_label="CTA Reception Score",
        score=taxonomy.scores.cta_reception_score,
        rollup=None,
        explanation="CTA landing quality estimate tied to synchrony, narrative coherence, and timing support.",
        source_metrics=[NeuroScoreMachineName.cta_reception_score.value],
    )
    synthetic = _as_score_summary(
        metric_key="synthetic_lift_prior",
        display_label="Synthetic Lift Prior",
        score=taxonomy.scores.synthetic_lift_prior,
        rollup=None,
        explanation=(
            "Fast model prior for expected lift; distinct from measured incrementality."
        ),
        source_metrics=[NeuroScoreMachineName.synthetic_lift_prior.value],
    )

    measured_status, measured_incremental, measured_iroas, note = _extract_measured_lift(
        video_metadata
    )
    synthetic_diag = aggregate_metrics.synthetic_lift_prior if aggregate_metrics is not None else None
    synthetic_vs_measured = ProductLiftComparison(
        synthetic_lift_prior=synthetic,
        predicted_incremental_lift_pct=(
            synthetic_diag.predicted_incremental_lift_pct if synthetic_diag is not None else None
        ),
        predicted_iroas=(synthetic_diag.predicted_iroas if synthetic_diag is not None else None),
        predicted_incremental_lift_ci_low=(
            synthetic_diag.incremental_lift_ci_low if synthetic_diag is not None else None
        ),
        predicted_incremental_lift_ci_high=(
            synthetic_diag.incremental_lift_ci_high if synthetic_diag is not None else None
        ),
        measured_lift_status=measured_status,
        measured_incremental_lift_pct=measured_incremental,
        measured_iroas=measured_iroas,
        calibration_status=(
            synthetic_diag.calibration_status if synthetic_diag is not None else None
        ),
        note=note,
    )

    media_summary = (
        "Media plan can prioritize this asset using paid lift prior bands; keep GeoX/holdout as final truth layer."
        if paid.scalar_value is not None and paid.scalar_value >= 60.0
        else "Paid lift prior is soft or uncertain; gate larger spend until calibration or measured lift arrives."
    )
    creative_summary = (
        "Creative structure appears memory-supportive and CTA-ready; iterate around top contributing moments."
        if (brand.scalar_value or 0.0) >= 60.0 and (cta.scalar_value or 0.0) >= 55.0
        else "Creative sequencing likely needs refinement around memory encoding or CTA timing windows."
    )
    return EnterpriseProductRollups(
        paid_lift_prior=paid,
        brand_memory_prior=brand,
        cta_reception_score=cta,
        synthetic_lift_prior=synthetic,
        synthetic_vs_measured_lift=synthetic_vs_measured,
        decision_support=EnterpriseDecisionSupport(
            media_team_summary=media_summary,
            creative_team_summary=creative_summary,
        ),
    )


def build_product_rollup_presentation(
    *,
    taxonomy: Optional[NeuroScoreTaxonomy],
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
    diagnostics: Sequence[SceneDiagnosticCard],
    segments: Sequence[ReadoutSegment] | None = None,
    video_metadata: Optional[Mapping[str, Any]] = None,
    requested_mode: Optional[ProductRollupMode] = None,
    requested_workspace_tier: Optional[str] = None,
) -> Optional[ProductRollupPresentation]:
    """Build tier-aware product rollup presentation over shared taxonomy outputs."""

    del segments  # Reserved for future product-level heuristics.
    settings = get_settings()
    if not settings.product_rollups_enabled:
        return None
    if taxonomy is None:
        return None

    mode_resolution = _resolve_mode(
        video_metadata=video_metadata,
        requested_mode=requested_mode,
        requested_workspace_tier=requested_workspace_tier,
    )

    creator_payload = None
    enterprise_payload = None
    if mode_resolution.mode == ProductRollupMode.creator:
        creator_payload = _build_creator_payload(
            taxonomy=taxonomy,
            aggregate_metrics=aggregate_metrics,
            diagnostics=diagnostics,
        )
    else:
        enterprise_payload = _build_enterprise_payload(
            taxonomy=taxonomy,
            aggregate_metrics=aggregate_metrics,
            video_metadata=video_metadata,
        )

    return ProductRollupPresentation(
        mode=mode_resolution.mode,
        workspace_tier=mode_resolution.workspace_tier,
        enabled_modes=list(mode_resolution.enabled_modes),
        mode_resolution_note=mode_resolution.note,
        source_schema_version=taxonomy.schema_version,
        creator=creator_payload,
        enterprise=enterprise_payload,
    )
