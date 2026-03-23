"""Neuro-score taxonomy — attention-related score builders."""

from __future__ import annotations

from typing import List

from .readout_metrics import clamp, mean_optional

from .schemas import (
    AttentionalSynchronyPathway,
    BlinkTransportPathway,
    BoundaryEncodingPathway,
    NarrativeControlPathway,
    NeuroEvidenceWindow,
    NeuroFeatureContribution,
    NeuroScoreContract,
    NeuroScoreMachineName,
    NeuroScoreStatus,
    ReadoutTracePoint,
)

from .neuro_score_taxonomy_core import (
    NeuroScoreComputationContext,
    _score,
    _segment_windows,
    _series_top_windows,
    _series_values,
    _to_100_from_signed_unit,
    _to_100_from_unit,
    _tracking_confidence,
    register_score,
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
