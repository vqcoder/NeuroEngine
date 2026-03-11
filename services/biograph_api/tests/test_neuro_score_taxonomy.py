"""Unit tests for neuro-score taxonomy contracts and adapters."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from app.neuro_score_taxonomy import (
    _SCORE_REGISTRY,
    ScoreRegistryDefinition,
    build_neuro_score_taxonomy,
    list_rollup_registry_entries,
    list_score_registry_entries,
)
from app.schemas import (
    AttentionalSynchronyDiagnostics,
    AttentionalSynchronyExtrema,
    AttentionalSynchronyPathway,
    AttentionalSynchronyTimelineScore,
    AuFrictionDiagnostics,
    AuFrictionPathway,
    AuFrictionQualityWarning,
    AuFrictionQualityWarningSeverity,
    AuFrictionTimelineWindow,
    BlinkTransportDiagnostics,
    BlinkTransportPathway,
    BlinkTransportTimelineScore,
    BlinkTransportWarning,
    BlinkTransportWarningSeverity,
    BoundaryEncodingDiagnostics,
    BoundaryEncodingFlag,
    BoundaryEncodingFlagSeverity,
    BoundaryEncodingPathway,
    BoundaryEncodingTimelineWindow,
    BoundaryEncodingTimelineWindowType,
    CtaReceptionDiagnostics,
    CtaReceptionFlag,
    CtaReceptionFlagSeverity,
    CtaReceptionPathway,
    CtaReceptionTimelineWindow,
    NarrativeControlDiagnostics,
    NarrativeControlHeuristicCheck,
    NarrativeControlMomentContribution,
    NarrativeControlPathway,
    NarrativeControlSceneScore,
    RewardAnticipationDiagnostics,
    RewardAnticipationPathway,
    RewardAnticipationTimelineWindow,
    RewardAnticipationTimelineWindowType,
    RewardAnticipationWarning,
    RewardAnticipationWarningSeverity,
    SelfRelevanceDiagnostics,
    SelfRelevancePathway,
    SelfRelevanceTimelineWindow,
    SyntheticLiftCalibrationStatus,
    SyntheticLiftPriorDiagnostics,
    SyntheticLiftPriorFeatureInput,
    SyntheticLiftPriorFeatureInputSource,
    SyntheticLiftPriorPathway,
    SyntheticLiftPriorTimelineWindow,
    SelfRelevanceWarning,
    SelfRelevanceWarningSeverity,
    SocialTransmissionDiagnostics,
    SocialTransmissionPathway,
    SocialTransmissionTimelineWindow,
    NeuroScoreMachineName,
    NeuroScoreTaxonomy,
    ReadoutAggregateMetrics,
    ReadoutPayload,
)


READOUT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "readout_payload.sample.json"
)
TAXONOMY_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "neuro_score_taxonomy.sample.json"
)


def test_neuro_score_sample_fixture_validates() -> None:
    payload = json.loads(TAXONOMY_FIXTURE_PATH.read_text(encoding="utf-8"))
    parsed = NeuroScoreTaxonomy.model_validate(payload)

    assert parsed.schema_version == "1.0.0"
    assert parsed.scores.arrest_score.machine_name.value == "arrest_score"
    assert parsed.rollups.organic_reach_prior.machine_name.value == "organic_reach_prior"
    assert len(parsed.legacy_score_adapters) == 2


def test_builder_returns_all_score_families_rollups_and_adapters() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    assert taxonomy.scores.reward_anticipation_index.machine_name.value == "reward_anticipation_index"
    assert taxonomy.rollups.brand_memory_prior.machine_name.value == "brand_memory_prior"
    assert {adapter.legacy_output for adapter in taxonomy.legacy_score_adapters} == {
        "emotion",
        "attention",
    }
    assert len(taxonomy.registry) >= 11
    assert len(taxonomy.rollup_registry) >= 3


def test_registry_lists_match_expected_counts() -> None:
    assert len(list_score_registry_entries()) >= 11
    assert len(list_rollup_registry_entries()) >= 3


def test_builder_gracefully_degrades_when_single_score_module_errors() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )

    machine_name = NeuroScoreMachineName.reward_anticipation_index
    original_definition = _SCORE_REGISTRY[machine_name]

    def _failing_builder(_context):
        raise RuntimeError("simulated score module failure")

    _SCORE_REGISTRY[machine_name] = replace(
        original_definition,
        builder_key="tests:simulated_failure",
        builder=_failing_builder,
    )
    try:
        taxonomy = build_neuro_score_taxonomy(
            traces=readout_payload.traces,
            segments=readout_payload.segments,
            diagnostics=readout_payload.diagnostics,
            labels=readout_payload.labels,
            aggregate_metrics=readout_payload.aggregate_metrics,
            context=readout_payload.context,
            window_ms=readout_payload.timebase.window_ms,
            schema_version=readout_payload.schema_version,
        )
    finally:
        _SCORE_REGISTRY[machine_name] = original_definition

    failed_score = taxonomy.scores.reward_anticipation_index
    assert failed_score.status.value == "unavailable"
    assert failed_score.scalar_value is None
    assert failed_score.confidence == 0.0
    assert failed_score.evidence_windows[0].reason.startswith(
        "Score unavailable due to internal module fallback"
    )
    assert taxonomy.scores.arrest_score.machine_name.value == "arrest_score"
    assert len(taxonomy.registry) >= 11


def test_attentional_synchrony_index_prefers_direct_diagnostics_path() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        attention_synchrony=0.12,
        blink_synchrony=0.05,
        grip_control_score=0.08,
        included_sessions=4,
        downweighted_sessions=0,
        attentional_synchrony=AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.direct_panel_gaze,
            global_score=84.2,
            confidence=0.89,
            segment_scores=[
                AttentionalSynchronyTimelineScore(
                    start_ms=0,
                    end_ms=3000,
                    score=82.0,
                    confidence=0.87,
                    pathway=AttentionalSynchronyPathway.direct_panel_gaze,
                    reason="Direct panel gaze overlap and aligned attention supported convergence.",
                )
            ],
            peaks=[
                AttentionalSynchronyExtrema(
                    start_ms=3000,
                    end_ms=6000,
                    score=90.0,
                    reason="Peak convergence window with strongest shared visual focus.",
                )
            ],
            valleys=[],
            evidence_summary="Direct panel gaze overlap was available and used as the primary pathway.",
            signals_used=["panel_gaze_overlap", "cross_user_attention_alignment"],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.attentional_synchrony_index
    assert score.scalar_value == 84.2
    assert score.confidence == 0.89
    assert score.status.value == "available"
    assert score.evidence_windows[0].reason.startswith("Peak convergence window")
    assert any(
        contribution.feature_name == "attentional_synchrony_pathway_weight"
        for contribution in score.top_feature_contributions
    )


def test_attentional_synchrony_index_uses_fallback_confidence_when_direct_unavailable() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        attention_synchrony=0.04,
        blink_synchrony=0.02,
        grip_control_score=0.03,
        included_sessions=2,
        downweighted_sessions=1,
        attentional_synchrony=AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.fallback_proxy,
            global_score=58.6,
            confidence=0.44,
            segment_scores=[
                AttentionalSynchronyTimelineScore(
                    start_ms=0,
                    end_ms=3000,
                    score=56.0,
                    confidence=0.42,
                    pathway=AttentionalSynchronyPathway.fallback_proxy,
                    reason="Fallback proxy uses salience concentration and subject continuity with reduced certainty.",
                )
            ],
            peaks=[
                AttentionalSynchronyExtrema(
                    start_ms=0,
                    end_ms=3000,
                    score=56.0,
                    reason="Fallback proxy indicates stronger concentration and continuity in this window.",
                )
            ],
            valleys=[
                AttentionalSynchronyExtrema(
                    start_ms=6000,
                    end_ms=9000,
                    score=41.0,
                    reason="Fallback proxy indicates weaker concentration continuity in this window.",
                )
            ],
            evidence_summary="Fallback estimator used due to limited direct gaze overlap.",
            signals_used=["attention_concentration_proxy", "subject_continuity_proxy"],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.attentional_synchrony_index
    assert score.scalar_value == 58.6
    assert score.confidence == 0.44
    assert score.status.value == "available"
    pathway_contribution = next(
        contribution
        for contribution in score.top_feature_contributions
        if contribution.feature_name == "attentional_synchrony_pathway_weight"
    )
    assert pathway_contribution.contribution == 0.72


def test_narrative_control_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        attention_synchrony=0.12,
        blink_synchrony=0.05,
        grip_control_score=0.08,
        included_sessions=4,
        downweighted_sessions=0,
        narrative_control=NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.timeline_grammar,
            global_score=74.5,
            confidence=0.81,
            scene_scores=[
                NarrativeControlSceneScore(
                    start_ms=0,
                    end_ms=4000,
                    score=71.0,
                    confidence=0.78,
                    scene_id="scene-1",
                    scene_label="setup",
                    fragmentation_index=0.24,
                    boundary_density=0.46,
                    motion_continuity=0.82,
                    ordering_pattern="context_before_face",
                    summary="Setup held coherence and motion continuity.",
                )
            ],
            disruption_penalties=[
                NarrativeControlMomentContribution(
                    start_ms=6400,
                    end_ms=7400,
                    contribution=-3.4,
                    category="disruptive_transition",
                    reason="One transition introduced avoidable disorientation.",
                    scene_id="scene-2",
                    cut_id="cut-5",
                )
            ],
            reveal_structure_bonuses=[
                NarrativeControlMomentContribution(
                    start_ms=4200,
                    end_ms=5600,
                    contribution=5.2,
                    category="coherent_reveal",
                    reason="Reveal timing aligned with attention lift.",
                    scene_id="scene-2",
                )
            ],
            top_contributing_moments=[
                NarrativeControlMomentContribution(
                    start_ms=4200,
                    end_ms=5600,
                    contribution=5.2,
                    category="coherent_reveal",
                    reason="Reveal timing aligned with attention lift.",
                    scene_id="scene-2",
                )
            ],
            heuristic_checks=[
                NarrativeControlHeuristicCheck(
                    heuristic_key="hard_hook_first_1_to_3_seconds",
                    passed=True,
                    score_delta=6.0,
                    reason="Opening hook threshold met.",
                    start_ms=0,
                    end_ms=3000,
                )
            ],
            evidence_summary="Narrative diagnostics favored coherent reveal structure over sparse disruptions.",
            signals_used=[
                "attention_trace",
                "scene_graph_cuts",
                "cut_cadence",
                "camera_motion_proxy",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.narrative_control_score
    assert score.status.value == "available"
    assert score.scalar_value == 74.5
    assert score.confidence == 0.81
    assert any(
        contribution.feature_name == "narrative_pathway_weight"
        for contribution in score.top_feature_contributions
    )


def test_blink_transport_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        attention_synchrony=0.08,
        blink_synchrony=0.21,
        grip_control_score=0.14,
        included_sessions=3,
        downweighted_sessions=0,
        blink_transport=BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.direct_panel_blink,
            global_score=76.8,
            confidence=0.82,
            segment_scores=[
                BlinkTransportTimelineScore(
                    start_ms=3000,
                    end_ms=4000,
                    score=81.0,
                    confidence=0.8,
                    pathway=BlinkTransportPathway.direct_panel_blink,
                    reason="Blink suppression held during a high-information window.",
                    blink_suppression=0.64,
                    rebound_signal=0.52,
                    cta_avoidance_signal=0.58,
                )
            ],
            suppression_score=0.61,
            rebound_score=0.54,
            cta_avoidance_score=0.57,
            cross_viewer_blink_synchrony=0.74,
            engagement_warnings=[
                BlinkTransportWarning(
                    warning_key="high_blink_variability",
                    severity=BlinkTransportWarningSeverity.medium,
                    message="Blink suppression varied across windows.",
                    start_ms=0,
                    end_ms=12000,
                    metric_value=0.24,
                )
            ],
            evidence_summary="Direct panel blink timing overlap was available as the primary pathway.",
            signals_used=[
                "blink_inhibition_timing",
                "cross_viewer_blink_synchrony",
                "cta_and_reveal_windows",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.blink_transport_score
    assert score.status.value == "available"
    assert score.scalar_value == 76.8
    assert score.confidence == 0.82
    assert any(
        contribution.feature_name == "blink_transport_pathway_weight"
        for contribution in score.top_feature_contributions
    )


def test_blink_transport_score_returns_unavailable_when_disabled() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=1,
        downweighted_sessions=0,
        blink_transport=BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.disabled,
            evidence_summary="Blink transport instrumentation is disabled for this environment.",
            signals_used=[],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.blink_transport_score
    assert score.status.value == "unavailable"
    assert score.scalar_value is None


def test_reward_anticipation_index_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        attention_synchrony=0.08,
        blink_synchrony=0.14,
        grip_control_score=0.11,
        included_sessions=4,
        downweighted_sessions=0,
        reward_anticipation=RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.timeline_dynamics,
            global_score=73.6,
            confidence=0.79,
            anticipation_ramps=[
                RewardAnticipationTimelineWindow(
                    start_ms=2000,
                    end_ms=5000,
                    score=72.4,
                    confidence=0.78,
                    window_type=RewardAnticipationTimelineWindowType.anticipation_ramp,
                    reason="Pre-payoff ramp combined pacing and blink suppression cues.",
                    ramp_slope=3.6,
                    tension_level=0.62,
                    release_level=0.58,
                )
            ],
            payoff_windows=[
                RewardAnticipationTimelineWindow(
                    start_ms=5000,
                    end_ms=6800,
                    score=76.5,
                    confidence=0.8,
                    window_type=RewardAnticipationTimelineWindowType.payoff_window,
                    reason="Payoff release arrived on-time with strong pull.",
                    reward_delta=12.4,
                    tension_level=0.62,
                    release_level=0.69,
                )
            ],
            warnings=[
                RewardAnticipationWarning(
                    warning_key="late_resolution",
                    severity=RewardAnticipationWarningSeverity.medium,
                    message="One payoff resolved later than preferred timing.",
                    start_ms=5000,
                    end_ms=7600,
                    metric_value=2500.0,
                )
            ],
            anticipation_strength=0.72,
            payoff_release_strength=0.77,
            tension_release_balance=0.86,
            evidence_summary="Timeline dynamics indicate strong anticipatory pull into payoff.",
            signals_used=[
                "reward_proxy_trend",
                "blink_suppression_pre_payoff",
                "cut_cadence",
                "audio_intensity_rms",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.reward_anticipation_index
    assert score.status.value == "available"
    assert score.scalar_value == 73.6
    assert score.confidence == 0.79
    assert any(
        contribution.feature_name == "anticipation_strength"
        for contribution in score.top_feature_contributions
    )


def test_boundary_encoding_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        attention_synchrony=0.07,
        blink_synchrony=0.09,
        grip_control_score=0.1,
        included_sessions=4,
        downweighted_sessions=0,
        boundary_encoding=BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.timeline_boundary_model,
            global_score=71.4,
            confidence=0.77,
            strong_windows=[
                BoundaryEncodingTimelineWindow(
                    start_ms=5600,
                    end_ms=6400,
                    score=79.2,
                    confidence=0.79,
                    window_type=BoundaryEncodingTimelineWindowType.strong_encoding,
                    reason="Payload aligned near boundary with novelty and reinforcement support.",
                    payload_type="text_overlay",
                    nearest_boundary_ms=6000,
                    boundary_distance_ms=80,
                    novelty_signal=0.71,
                    reinforcement_signal=1.0,
                )
            ],
            weak_windows=[
                BoundaryEncodingTimelineWindow(
                    start_ms=10800,
                    end_ms=11600,
                    score=42.0,
                    confidence=0.63,
                    window_type=BoundaryEncodingTimelineWindowType.weak_encoding,
                    reason="Payload landed late relative to a boundary.",
                    payload_type="text_overlay",
                    nearest_boundary_ms=9000,
                    boundary_distance_ms=1900,
                    novelty_signal=0.43,
                    reinforcement_signal=0.0,
                )
            ],
            flags=[
                BoundaryEncodingFlag(
                    flag_key="poor_payload_timing",
                    severity=BoundaryEncodingFlagSeverity.medium,
                    message="Important payload was introduced away from an event boundary.",
                    start_ms=10800,
                    end_ms=11600,
                    metric_value=1900.0,
                )
            ],
            boundary_alignment_score=0.66,
            novelty_boundary_score=0.68,
            reinforcement_score=0.52,
            overload_risk_score=0.18,
            payload_count=4,
            boundary_count=3,
            evidence_summary="Boundary placement supported chunked encoding with one late payload warning.",
            signals_used=[
                "scene_graph_boundaries",
                "timeline_shot_boundaries",
                "text_overlay_payloads",
                "novelty_proxy",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.boundary_encoding_score
    assert score.status.value == "available"
    assert score.scalar_value == 71.4
    assert score.confidence == 0.77
    assert any(
        contribution.feature_name == "payload_boundary_alignment"
        for contribution in score.top_feature_contributions
    )


def test_social_transmission_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=4,
        downweighted_sessions=0,
        social_transmission=SocialTransmissionDiagnostics(
            pathway=SocialTransmissionPathway.annotation_augmented,
            global_score=74.2,
            confidence=0.78,
            segment_scores=[
                SocialTransmissionTimelineWindow(
                    start_ms=2000,
                    end_ms=3000,
                    score=80.0,
                    confidence=0.8,
                    reason="Novel reveal and quote-worthy text drove sharing potential.",
                    novelty_signal=0.76,
                    emotional_activation_signal=0.71,
                    quote_worthiness_signal=0.68,
                )
            ],
            novelty_signal=0.74,
            identity_signal=0.51,
            usefulness_signal=0.62,
            quote_worthiness_signal=0.66,
            emotional_activation_signal=0.7,
            memorability_signal=0.64,
            evidence_summary="Timeline and annotation markers converged on social handoff moments.",
            signals_used=[
                "novelty_proxy",
                "quote_comment_worthiness_language",
                "annotation_marker_support",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.social_transmission_score
    assert score.status.value == "available"
    assert score.scalar_value == 74.2
    assert score.confidence == 0.78
    assert any(
        contribution.feature_name == "social_transmission_pathway_weight"
        for contribution in score.top_feature_contributions
    )


def test_self_relevance_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=5,
        downweighted_sessions=0,
        self_relevance=SelfRelevanceDiagnostics(
            pathway=SelfRelevancePathway.contextual_personalization,
            global_score=77.4,
            confidence=0.8,
            segment_scores=[
                SelfRelevanceTimelineWindow(
                    start_ms=1000,
                    end_ms=3000,
                    score=79.0,
                    confidence=0.79,
                    reason="Direct address and audience-match cues aligned in setup window.",
                    direct_address_signal=0.72,
                    personalization_hook_signal=0.68,
                )
            ],
            warnings=[
                SelfRelevanceWarning(
                    warning_key="audience_metadata_missing",
                    severity=SelfRelevanceWarningSeverity.low,
                    message="Audience metadata was partial; overlap estimate used available tags only.",
                )
            ],
            direct_address_signal=0.7,
            audience_match_signal=0.62,
            niche_specificity_signal=0.58,
            personalization_hook_signal=0.65,
            resonance_signal=0.76,
            context_coverage=0.84,
            evidence_summary="Audience-match metadata and direct-address language supported self relevance.",
            signals_used=[
                "direct_address_cues",
                "audience_metadata_token_overlap",
                "survey_resonance_signal",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.self_relevance_score
    assert score.status.value == "available"
    assert score.scalar_value == 77.4
    assert score.confidence == 0.8
    assert any(
        contribution.feature_name == "self_relevance_pathway_weight"
        for contribution in score.top_feature_contributions
    )


def test_synthetic_lift_prior_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=6,
        downweighted_sessions=1,
        synthetic_lift_prior=SyntheticLiftPriorDiagnostics(
            pathway=SyntheticLiftPriorPathway.taxonomy_regression,
            global_score=68.4,
            confidence=0.72,
            predicted_incremental_lift_pct=8.1,
            predicted_iroas=2.18,
            incremental_lift_ci_low=2.4,
            incremental_lift_ci_high=13.8,
            iroas_ci_low=1.28,
            iroas_ci_high=3.08,
            uncertainty_band=5.7,
            calibration_status=SyntheticLiftCalibrationStatus.provisional,
            calibration_observation_count=4,
            model_version="synthetic_lift_prior_v1",
            segment_scores=[
                SyntheticLiftPriorTimelineWindow(
                    start_ms=5000,
                    end_ms=6000,
                    score=77.2,
                    confidence=0.75,
                    reason="Window overlaps CTA context with stronger reward and attention support for prior lift potential.",
                    contribution=0.579,
                )
            ],
            feature_inputs=[
                SyntheticLiftPriorFeatureInput(
                    feature_name="cta_reception_score",
                    source=SyntheticLiftPriorFeatureInputSource.taxonomy,
                    raw_value=73.1,
                    normalized_value=0.731,
                    weight=0.11,
                )
            ],
            evidence_summary="Synthetic prior indicates directional lift potential and remains distinct from measured incrementality truth.",
            signals_used=["cta_reception_score", "reward_anticipation_index"],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.synthetic_lift_prior
    assert score.status.value == "available"
    assert score.scalar_value == 68.4
    assert score.confidence is not None
    assert score.confidence < 0.72
    assert any(
        contribution.feature_name == "synthetic_lift_pathway_weight"
        for contribution in score.top_feature_contributions
    )
    assert any(
        contribution.feature_name == "predicted_incremental_lift_pct"
        for contribution in score.top_feature_contributions
    )


def test_cta_reception_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=5,
        downweighted_sessions=1,
        cta_reception=CtaReceptionDiagnostics(
            pathway=CtaReceptionPathway.multi_signal_model,
            global_score=73.1,
            confidence=0.78,
            cta_windows=[
                CtaReceptionTimelineWindow(
                    cta_id="cta-main",
                    cta_type="sign_up",
                    start_ms=5000,
                    end_ms=6200,
                    score=77.8,
                    confidence=0.8,
                    reason="CTA overlaps synchrony and payoff support windows.",
                    synchrony_support=0.76,
                    narrative_support=0.72,
                    blink_receptivity_support=0.7,
                    reward_timing_support=0.81,
                    boundary_coherence_support=0.68,
                    timing_fit_support=0.75,
                    flag_keys=[],
                )
            ],
            flags=[
                CtaReceptionFlag(
                    flag_key="cta_after_fragmentation",
                    severity=CtaReceptionFlagSeverity.medium,
                    message="One transition near CTA introduces continuity friction.",
                    start_ms=4700,
                    end_ms=5200,
                    cta_id="cta-main",
                    cta_type="sign_up",
                    metric_value=0.44,
                )
            ],
            synchrony_support=0.74,
            narrative_support=0.69,
            blink_receptivity_support=0.7,
            reward_timing_support=0.79,
            boundary_coherence_support=0.67,
            overload_risk_support=0.86,
            evidence_summary="CTA reception combines synchrony, narrative flow, blink receptivity, reward timing, and boundary support.",
            signals_used=[
                "attentional_synchrony_index",
                "narrative_control_score",
                "blink_transport_score",
                "reward_anticipation_index",
                "boundary_encoding_score",
            ],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.cta_reception_score
    assert score.status.value == "available"
    assert score.scalar_value == 73.1
    assert score.confidence == 0.78
    assert any(
        contribution.feature_name == "cta_reception_pathway_weight"
        for contribution in score.top_feature_contributions
    )


def test_cta_reception_score_tolerates_non_enum_pathway_value() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=5,
        downweighted_sessions=1,
        cta_reception=CtaReceptionDiagnostics(
            pathway=CtaReceptionPathway.multi_signal_model,
            global_score=73.1,
            confidence=0.78,
            cta_windows=[
                CtaReceptionTimelineWindow(
                    cta_id="cta-main",
                    cta_type="sign_up",
                    start_ms=5000,
                    end_ms=6200,
                    score=77.8,
                    confidence=0.8,
                    reason="CTA overlaps synchrony and payoff support windows.",
                    synchrony_support=0.76,
                    narrative_support=0.72,
                    blink_receptivity_support=0.7,
                    reward_timing_support=0.81,
                    boundary_coherence_support=0.68,
                    timing_fit_support=0.75,
                    flag_keys=[],
                )
            ],
            flags=[],
            synchrony_support=0.74,
            narrative_support=0.69,
            blink_receptivity_support=0.7,
            reward_timing_support=0.79,
            boundary_coherence_support=0.67,
            overload_risk_support=0.86,
            evidence_summary="CTA reception combines synchrony and timing cues.",
            signals_used=[
                "attentional_synchrony_index",
                "narrative_control_score",
                "blink_transport_score",
                "reward_anticipation_index",
                "boundary_encoding_score",
            ],
        ),
    )
    # Runtime hardening for non-canonical payload sources.
    readout_payload.aggregate_metrics.cta_reception.pathway = "legacy_proxy"  # type: ignore[assignment]

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.cta_reception_score
    assert score.status.value == "available"
    assert score.scalar_value == 73.1
    assert score.confidence == 0.78


def test_au_friction_score_prefers_structured_diagnostics() -> None:
    readout_payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    readout_payload.aggregate_metrics = ReadoutAggregateMetrics(
        included_sessions=4,
        downweighted_sessions=1,
        au_friction=AuFrictionDiagnostics(
            pathway=AuFrictionPathway.au_signal_model,
            global_score=57.2,
            confidence=0.69,
            segment_scores=[
                AuFrictionTimelineWindow(
                    start_ms=3000,
                    end_ms=4000,
                    score=63.4,
                    confidence=0.72,
                    reason="Dominant AU pattern suggested confusion after a transition.",
                    dominant_state="confusion",
                    transition_context="post_transition_spike",
                    au04_signal=0.49,
                    au06_signal=0.18,
                    au12_signal=0.14,
                    au25_signal=0.33,
                    au26_signal=0.27,
                    au45_signal=0.25,
                    confusion_signal=0.56,
                    strain_signal=0.42,
                    amusement_signal=0.11,
                    tension_signal=0.38,
                    resistance_signal=0.34,
                )
            ],
            warnings=[
                AuFrictionQualityWarning(
                    warning_key="high_lighting_variance",
                    severity=AuFrictionQualityWarningSeverity.medium,
                    message="Lighting instability reduced consistency of AU-level friction interpretation.",
                    metric_value=18.4,
                )
            ],
            confusion_signal=0.41,
            strain_signal=0.33,
            amusement_signal=0.18,
            tension_signal=0.31,
            resistance_signal=0.29,
            evidence_summary="AU-level friction diagnostics stayed quality-gated and flagged lighting variance.",
            signals_used=["au04_trace", "au12_trace", "face_quality_gating"],
        ),
    )

    taxonomy = build_neuro_score_taxonomy(
        traces=readout_payload.traces,
        segments=readout_payload.segments,
        diagnostics=readout_payload.diagnostics,
        labels=readout_payload.labels,
        aggregate_metrics=readout_payload.aggregate_metrics,
        context=readout_payload.context,
        window_ms=readout_payload.timebase.window_ms,
        schema_version=readout_payload.schema_version,
    )

    score = taxonomy.scores.au_friction_score
    assert score.status.value == "available"
    assert score.scalar_value == 57.2
    assert score.confidence == 0.69
    assert any(
        contribution.feature_name == "au_friction_pathway_weight"
        for contribution in score.top_feature_contributions
    )
