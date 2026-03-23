"""Neuro-score taxonomy — reward and social score builders."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .readout_metrics import clamp, mean_optional

from .schemas import (
    AuFrictionPathway,
    CtaReceptionPathway,
    NeuroEvidenceWindow,
    NeuroFeatureContribution,
    NeuroScoreContract,
    NeuroScoreMachineName,
    NeuroScoreStatus,
    RewardAnticipationPathway,
    SelfRelevancePathway,
    SocialTransmissionPathway,
    SyntheticLiftPriorPathway,
)

from .neuro_score_taxonomy_core import (
    NeuroScoreComputationContext,
    _score,
    _segment_windows,
    _series_top_windows,
    _series_values,
    _to_100_from_unit,
    _tracking_confidence,
    register_score,
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
