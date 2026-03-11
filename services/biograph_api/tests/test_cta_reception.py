"""Unit tests for CTA reception diagnostics and CTA window placement quality."""

from __future__ import annotations

from app.cta_reception import compute_cta_reception_diagnostics
from app.schemas import (
    AttentionalSynchronyDiagnostics,
    AttentionalSynchronyPathway,
    AttentionalSynchronyTimelineScore,
    BlinkTransportDiagnostics,
    BlinkTransportPathway,
    BlinkTransportTimelineScore,
    BoundaryEncodingDiagnostics,
    BoundaryEncodingFlag,
    BoundaryEncodingFlagSeverity,
    BoundaryEncodingPathway,
    BoundaryEncodingTimelineWindow,
    BoundaryEncodingTimelineWindowType,
    NarrativeControlDiagnostics,
    NarrativeControlMomentContribution,
    NarrativeControlPathway,
    NarrativeControlSceneScore,
    ReadoutCtaMarker,
    RewardAnticipationDiagnostics,
    RewardAnticipationPathway,
    RewardAnticipationTimelineWindow,
    RewardAnticipationTimelineWindowType,
)


def _bucket_rows(attention_values: list[float]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, attention in enumerate(attention_values):
        start_ms = index * 1000
        prev_attention = attention_values[index - 1] if index > 0 else attention
        rows.append(
            {
                "bucket_start": start_ms,
                "attention_score": attention,
                "attention_velocity": attention - prev_attention,
                "tracking_confidence": 0.86,
                "quality_score": 0.84,
            }
        )
    return rows


def _peak_aligned_inputs() -> tuple[
    AttentionalSynchronyDiagnostics,
    NarrativeControlDiagnostics,
    BlinkTransportDiagnostics,
    RewardAnticipationDiagnostics,
    BoundaryEncodingDiagnostics,
]:
    return (
        AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.direct_panel_gaze,
            global_score=81.0,
            confidence=0.84,
            segment_scores=[
                AttentionalSynchronyTimelineScore(
                    start_ms=5000,
                    end_ms=6000,
                    score=84.0,
                    confidence=0.86,
                    pathway=AttentionalSynchronyPathway.direct_panel_gaze,
                    reason="Panel gaze overlap concentrated during CTA payoff timing.",
                )
            ],
            peaks=[],
            valleys=[],
            evidence_summary="Direct panel gaze overlap supported synchrony estimation.",
            signals_used=["panel_gaze_overlap"],
        ),
        NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.timeline_grammar,
            global_score=76.0,
            confidence=0.8,
            scene_scores=[
                NarrativeControlSceneScore(
                    start_ms=4000,
                    end_ms=8000,
                    score=79.0,
                    confidence=0.8,
                    scene_id="scene-payoff",
                    scene_label="payoff",
                    summary="Scene preserved coherent reveal structure before CTA.",
                )
            ],
            disruption_penalties=[],
            reveal_structure_bonuses=[],
            top_contributing_moments=[],
            heuristic_checks=[],
            evidence_summary="Narrative flow remained coherent into CTA window.",
            signals_used=["scene_graph_cuts"],
        ),
        BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.fallback_proxy,
            global_score=72.0,
            confidence=0.74,
            segment_scores=[
                BlinkTransportTimelineScore(
                    start_ms=5000,
                    end_ms=6000,
                    score=78.0,
                    confidence=0.75,
                    pathway=BlinkTransportPathway.fallback_proxy,
                    reason="Blink avoidance held through CTA window.",
                    cta_avoidance_signal=0.78,
                )
            ],
            suppression_score=0.62,
            rebound_score=0.55,
            cta_avoidance_score=0.76,
            cross_viewer_blink_synchrony=0.38,
            engagement_warnings=[],
            evidence_summary="Blink timing remained favorable around CTA.",
            signals_used=["blink_inhibition_timing"],
        ),
        RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.timeline_dynamics,
            global_score=80.0,
            confidence=0.79,
            anticipation_ramps=[
                RewardAnticipationTimelineWindow(
                    start_ms=3000,
                    end_ms=5000,
                    score=74.0,
                    confidence=0.75,
                    window_type=RewardAnticipationTimelineWindowType.anticipation_ramp,
                    reason="Anticipation ramp leads into payoff.",
                )
            ],
            payoff_windows=[
                RewardAnticipationTimelineWindow(
                    start_ms=5000,
                    end_ms=6200,
                    score=86.0,
                    confidence=0.82,
                    window_type=RewardAnticipationTimelineWindowType.payoff_window,
                    reason="Payoff window aligns with CTA.",
                )
            ],
            warnings=[],
            anticipation_strength=0.77,
            payoff_release_strength=0.84,
            tension_release_balance=0.88,
            evidence_summary="CTA overlaps a strong payoff release window.",
            signals_used=["reward_proxy_trend"],
        ),
        BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.timeline_boundary_model,
            global_score=75.0,
            confidence=0.78,
            strong_windows=[
                BoundaryEncodingTimelineWindow(
                    start_ms=5100,
                    end_ms=6200,
                    score=81.0,
                    confidence=0.79,
                    window_type=BoundaryEncodingTimelineWindowType.strong_encoding,
                    reason="CTA aligns with event boundary chunking.",
                )
            ],
            weak_windows=[],
            flags=[],
            boundary_alignment_score=0.74,
            novelty_boundary_score=0.69,
            reinforcement_score=0.63,
            overload_risk_score=0.12,
            payload_count=2,
            boundary_count=3,
            evidence_summary="Boundary timing supports CTA encoding.",
            signals_used=["scene_graph_boundaries"],
        ),
    )


def _post_dropoff_inputs() -> tuple[
    AttentionalSynchronyDiagnostics,
    NarrativeControlDiagnostics,
    BlinkTransportDiagnostics,
    RewardAnticipationDiagnostics,
    BoundaryEncodingDiagnostics,
]:
    return (
        AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.fallback_proxy,
            global_score=48.0,
            confidence=0.52,
            segment_scores=[
                AttentionalSynchronyTimelineScore(
                    start_ms=9000,
                    end_ms=10000,
                    score=31.0,
                    confidence=0.48,
                    pathway=AttentionalSynchronyPathway.fallback_proxy,
                    reason="Late CTA segment has weaker attention convergence.",
                )
            ],
            peaks=[],
            valleys=[],
            evidence_summary="Fallback proxy indicates weaker late-window synchrony.",
            signals_used=["attention_concentration_proxy"],
        ),
        NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.timeline_grammar,
            global_score=54.0,
            confidence=0.61,
            scene_scores=[
                NarrativeControlSceneScore(
                    start_ms=8000,
                    end_ms=11000,
                    score=46.0,
                    confidence=0.58,
                    scene_id="scene-late",
                    scene_label="late",
                    summary="Late section is fragmented with continuity disruptions.",
                )
            ],
            disruption_penalties=[
                NarrativeControlMomentContribution(
                    start_ms=8600,
                    end_ms=9500,
                    contribution=-4.2,
                    category="disruptive_transition",
                    reason="Disruptive transition immediately precedes CTA.",
                    scene_id="scene-late",
                )
            ],
            reveal_structure_bonuses=[],
            top_contributing_moments=[],
            heuristic_checks=[],
            evidence_summary="Fragmentation increases around late CTA placement.",
            signals_used=["scene_graph_cuts"],
        ),
        BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.fallback_proxy,
            global_score=43.0,
            confidence=0.56,
            segment_scores=[
                BlinkTransportTimelineScore(
                    start_ms=9000,
                    end_ms=10000,
                    score=28.0,
                    confidence=0.53,
                    pathway=BlinkTransportPathway.fallback_proxy,
                    reason="Blink-through risk rises during late CTA window.",
                    cta_avoidance_signal=0.18,
                )
            ],
            suppression_score=0.31,
            rebound_score=0.26,
            cta_avoidance_score=0.2,
            cross_viewer_blink_synchrony=0.18,
            engagement_warnings=[],
            evidence_summary="Late CTA window shows weaker blink receptivity.",
            signals_used=["blink_inhibition_timing"],
        ),
        RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.timeline_dynamics,
            global_score=59.0,
            confidence=0.6,
            anticipation_ramps=[],
            payoff_windows=[
                RewardAnticipationTimelineWindow(
                    start_ms=5000,
                    end_ms=6200,
                    score=68.0,
                    confidence=0.67,
                    window_type=RewardAnticipationTimelineWindowType.payoff_window,
                    reason="Payoff arrives earlier than the late CTA window.",
                )
            ],
            warnings=[],
            anticipation_strength=0.52,
            payoff_release_strength=0.6,
            tension_release_balance=0.62,
            evidence_summary="CTA misses strongest payoff timing window.",
            signals_used=["reward_proxy_trend"],
        ),
        BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.timeline_boundary_model,
            global_score=46.0,
            confidence=0.57,
            strong_windows=[],
            weak_windows=[
                BoundaryEncodingTimelineWindow(
                    start_ms=9000,
                    end_ms=10000,
                    score=34.0,
                    confidence=0.55,
                    window_type=BoundaryEncodingTimelineWindowType.weak_encoding,
                    reason="CTA appears in a weak boundary-coherence window.",
                )
            ],
            flags=[
                BoundaryEncodingFlag(
                    flag_key="payload_overload_at_boundary",
                    severity=BoundaryEncodingFlagSeverity.high,
                    message="Multiple payloads collide near the CTA moment.",
                    start_ms=8800,
                    end_ms=10100,
                    metric_value=4.0,
                )
            ],
            boundary_alignment_score=0.4,
            novelty_boundary_score=0.35,
            reinforcement_score=0.3,
            overload_risk_score=0.72,
            payload_count=5,
            boundary_count=2,
            evidence_summary="Late CTA timing collides with payload overload risk.",
            signals_used=["scene_graph_boundaries"],
        ),
    )


def test_cta_reception_scores_peak_overlap_higher_than_post_dropoff_window() -> None:
    peak_inputs = _peak_aligned_inputs()
    dropoff_inputs = _post_dropoff_inputs()

    peak = compute_cta_reception_diagnostics(
        bucket_rows=_bucket_rows([58, 62, 67, 71, 75, 79, 77, 74, 72, 70, 68, 66]),
        cta_markers=[
            ReadoutCtaMarker(
                cta_id="cta-peak",
                label="Sign up now",
                video_time_ms=5000,
                start_ms=5000,
                end_ms=6200,
            )
        ],
        attentional_synchrony=peak_inputs[0],
        narrative_control=peak_inputs[1],
        blink_transport=peak_inputs[2],
        reward_anticipation=peak_inputs[3],
        boundary_encoding=peak_inputs[4],
        window_ms=1000,
    )
    post_dropoff = compute_cta_reception_diagnostics(
        bucket_rows=_bucket_rows([58, 62, 67, 71, 75, 79, 74, 61, 49, 43, 37, 33]),
        cta_markers=[
            ReadoutCtaMarker(
                cta_id="cta-late",
                label="Visit www.alphaengine.example",
                video_time_ms=9000,
                start_ms=9000,
                end_ms=10000,
            )
        ],
        attentional_synchrony=dropoff_inputs[0],
        narrative_control=dropoff_inputs[1],
        blink_transport=dropoff_inputs[2],
        reward_anticipation=dropoff_inputs[3],
        boundary_encoding=dropoff_inputs[4],
        window_ms=1000,
    )

    assert peak.pathway.value == "multi_signal_model"
    assert post_dropoff.pathway.value == "multi_signal_model"
    assert peak.global_score is not None
    assert post_dropoff.global_score is not None
    assert peak.global_score > post_dropoff.global_score + 25.0
    assert peak.cta_windows[0].cta_type == "sign_up"
    assert post_dropoff.cta_windows[0].cta_type == "url"


def test_cta_reception_sets_actionable_flags_for_bad_cta_placement() -> None:
    dropoff_inputs = _post_dropoff_inputs()

    diagnostics = compute_cta_reception_diagnostics(
        bucket_rows=_bucket_rows([58, 62, 67, 71, 75, 79, 74, 61, 49, 43, 37, 33]),
        cta_markers=[
            ReadoutCtaMarker(
                cta_id="cta-late",
                label="Visit www.alphaengine.example",
                video_time_ms=9000,
                start_ms=9000,
                end_ms=10000,
            )
        ],
        attentional_synchrony=dropoff_inputs[0],
        narrative_control=dropoff_inputs[1],
        blink_transport=dropoff_inputs[2],
        reward_anticipation=dropoff_inputs[3],
        boundary_encoding=dropoff_inputs[4],
        window_ms=1000,
    )

    flag_keys = {flag.flag_key for flag in diagnostics.flags}
    assert "cta_too_late" in flag_keys
    assert "cta_after_fragmentation" in flag_keys
    assert "cta_missed_reward_window" in flag_keys
    assert "cta_blinked_through" in flag_keys
    assert "cta_cognitive_overload" in flag_keys


def test_cta_reception_classifies_multiple_cta_marker_types() -> None:
    peak_inputs = _peak_aligned_inputs()
    markers = [
        ReadoutCtaMarker(cta_id="cta-brand", label="Brand reveal", video_time_ms=3000, start_ms=3000, end_ms=3600),
        ReadoutCtaMarker(cta_id="cta-offer", label="Limited time offer", video_time_ms=4200, start_ms=4200, end_ms=4800),
        ReadoutCtaMarker(cta_id="cta-url", label="Visit www.alphaengine.example", video_time_ms=5000, start_ms=5000, end_ms=5600),
        ReadoutCtaMarker(cta_id="cta-install", label="Install app", video_time_ms=6200, start_ms=6200, end_ms=6800),
        ReadoutCtaMarker(cta_id="cta-signup", label="Sign up now", video_time_ms=7400, start_ms=7400, end_ms=8000),
        ReadoutCtaMarker(cta_id="cta-cart", label="Add to cart", video_time_ms=8600, start_ms=8600, end_ms=9200),
    ]

    diagnostics = compute_cta_reception_diagnostics(
        bucket_rows=_bucket_rows([58, 60, 64, 67, 70, 74, 73, 71, 69, 67, 65, 63]),
        cta_markers=markers,
        attentional_synchrony=peak_inputs[0],
        narrative_control=peak_inputs[1],
        blink_transport=peak_inputs[2],
        reward_anticipation=peak_inputs[3],
        boundary_encoding=peak_inputs[4],
        window_ms=1000,
    )

    types_by_id = {window.cta_id: window.cta_type for window in diagnostics.cta_windows}
    assert types_by_id["cta-brand"] == "brand_reveal"
    assert types_by_id["cta-offer"] == "offer"
    assert types_by_id["cta-url"] == "url"
    assert types_by_id["cta-install"] == "app_install"
    assert types_by_id["cta-signup"] == "sign_up"
    assert types_by_id["cta-cart"] == "add_to_cart"
