"""Unit tests for synthetic lift prior inference and calibration hooks."""

from __future__ import annotations

import json

from app.schemas import (
    AttentionalSynchronyDiagnostics,
    AttentionalSynchronyPathway,
    AuFrictionDiagnostics,
    AuFrictionPathway,
    BlinkTransportDiagnostics,
    BlinkTransportPathway,
    BoundaryEncodingDiagnostics,
    BoundaryEncodingPathway,
    CtaReceptionDiagnostics,
    CtaReceptionPathway,
    NarrativeControlDiagnostics,
    NarrativeControlPathway,
    RewardAnticipationDiagnostics,
    RewardAnticipationPathway,
    SelfRelevanceDiagnostics,
    SelfRelevancePathway,
    SocialTransmissionDiagnostics,
    SocialTransmissionPathway,
)
from app.synthetic_lift_prior import (
    IncrementalityObservation,
    SyntheticLiftCalibrationState,
    SyntheticLiftPriorConfig,
    apply_incrementality_calibration_updates,
    compute_synthetic_lift_prior_diagnostics,
    load_synthetic_lift_calibration_state,
    update_calibration_state_from_experiments,
)


def _bucket_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    reward = [42.0, 48.0, 55.0, 64.0, 72.0, 78.0, 70.0, 63.0]
    attention = [45.0, 51.0, 58.0, 66.0, 74.0, 79.0, 71.0, 62.0]
    for index, _ in enumerate(reward):
        rows.append(
            {
                "bucket_start": index * 1000,
                "reward_proxy": reward[index],
                "attention_score": attention[index],
                "tracking_confidence": 0.82,
                "quality_score": 0.8,
                "cta_id": "cta-main" if 4000 <= index * 1000 <= 5000 else None,
            }
        )
    return rows


def test_synthetic_lift_prior_inference_returns_expected_shape() -> None:
    diagnostics = compute_synthetic_lift_prior_diagnostics(
        bucket_rows=_bucket_rows(),
        window_ms=1000,
        attention_synchrony=0.62,
        blink_synchrony=0.44,
        grip_control_score=0.53,
        attentional_synchrony=AttentionalSynchronyDiagnostics(
            pathway=AttentionalSynchronyPathway.fallback_proxy,
            global_score=68.0,
            confidence=0.62,
            evidence_summary="Fallback synchrony pathway was used.",
            signals_used=["salience_concentration_proxy"],
        ),
        narrative_control=NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.timeline_grammar,
            global_score=71.0,
            confidence=0.76,
            evidence_summary="Narrative continuity stayed mostly coherent.",
            signals_used=["scene_graph_cuts"],
        ),
        blink_transport=BlinkTransportDiagnostics(
            pathway=BlinkTransportPathway.fallback_proxy,
            global_score=69.0,
            confidence=0.64,
            evidence_summary="Fallback blink-event gating was used.",
            signals_used=["blink_inhibition_timing"],
        ),
        reward_anticipation=RewardAnticipationDiagnostics(
            pathway=RewardAnticipationPathway.timeline_dynamics,
            global_score=74.0,
            confidence=0.75,
            evidence_summary="Setup to payoff dynamics were present.",
            signals_used=["reward_proxy_trend"],
        ),
        boundary_encoding=BoundaryEncodingDiagnostics(
            pathway=BoundaryEncodingPathway.timeline_boundary_model,
            global_score=70.0,
            confidence=0.73,
            payload_count=3,
            boundary_count=3,
            evidence_summary="Payload timing aligned with boundaries.",
            signals_used=["scene_graph_boundaries"],
        ),
        cta_reception=CtaReceptionDiagnostics(
            pathway=CtaReceptionPathway.multi_signal_model,
            global_score=73.0,
            confidence=0.74,
            evidence_summary="CTA landed near payoff support windows.",
            signals_used=["cta_marker_timeline_alignment"],
        ),
        social_transmission=SocialTransmissionDiagnostics(
            pathway=SocialTransmissionPathway.timeline_signal_model,
            global_score=67.0,
            confidence=0.68,
            evidence_summary="Novelty and quote-worthiness signals were moderate.",
            signals_used=["novelty_proxy"],
        ),
        self_relevance=SelfRelevanceDiagnostics(
            pathway=SelfRelevancePathway.fallback_proxy,
            global_score=65.0,
            confidence=0.63,
            evidence_summary="Self relevance used direct-address fallback cues.",
            signals_used=["direct_address_cues"],
        ),
        au_friction=AuFrictionDiagnostics(
            pathway=AuFrictionPathway.au_signal_model,
            global_score=52.0,
            confidence=0.66,
            evidence_summary="AU friction remained moderate.",
            signals_used=["au04_trace"],
        ),
        calibration_state=SyntheticLiftCalibrationState(
            truth_layer="geox",
            observation_count=6,
            lift_bias_pct=1.5,
            iroas_bias=0.12,
            uncertainty_scale=0.82,
            updated_at="2026-03-08T00:00:00+00:00",
        ),
    )

    assert diagnostics.pathway.value == "taxonomy_regression"
    assert diagnostics.global_score is not None
    assert diagnostics.confidence is not None
    assert diagnostics.predicted_incremental_lift_pct is not None
    assert diagnostics.predicted_iroas is not None
    assert diagnostics.incremental_lift_ci_low is not None
    assert diagnostics.incremental_lift_ci_high is not None
    assert diagnostics.incremental_lift_ci_low <= diagnostics.incremental_lift_ci_high
    assert diagnostics.iroas_ci_low is not None
    assert diagnostics.iroas_ci_high is not None
    assert diagnostics.iroas_ci_low <= diagnostics.iroas_ci_high
    assert diagnostics.calibration_status.value == "geox_calibrated"
    assert diagnostics.model_version == "synthetic_lift_prior_v1"
    assert len(diagnostics.segment_scores) >= 1
    assert len(diagnostics.feature_inputs) >= 3


def test_apply_incrementality_calibration_updates_adjusts_bias_and_uncertainty() -> None:
    baseline = SyntheticLiftCalibrationState(
        truth_layer="stub",
        observation_count=0,
        lift_bias_pct=0.0,
        iroas_bias=0.0,
        uncertainty_scale=1.0,
    )
    observations = [
        IncrementalityObservation(
            experiment_id="exp-1",
            measured_incremental_lift_pct=12.0,
            measured_iroas=2.8,
            predicted_incremental_lift_pct=6.0,
            predicted_iroas=1.9,
            source="geox_holdout",
        ),
        IncrementalityObservation(
            experiment_id="exp-2",
            measured_incremental_lift_pct=8.0,
            measured_iroas=2.4,
            predicted_incremental_lift_pct=5.0,
            predicted_iroas=1.8,
            source="geox_holdout",
        ),
    ]

    updated = apply_incrementality_calibration_updates(
        baseline,
        observations=observations,
        config=SyntheticLiftPriorConfig(geox_calibration_enabled=True),
    )

    assert updated.observation_count == 2
    assert updated.lift_bias_pct > 0.0
    assert updated.iroas_bias > 0.0
    assert updated.uncertainty_scale < 1.0
    assert updated.truth_layer == "geox"
    assert updated.updated_at is not None


def test_update_calibration_state_from_experiments_persists_state(tmp_path) -> None:
    calibration_path = tmp_path / "synthetic_lift_calibration.json"
    updated = update_calibration_state_from_experiments(
        experiment_results=[
            {
                "experiment_id": "exp-99",
                "measured_incremental_lift_pct": 9.2,
                "measured_iroas": 2.3,
                "predicted_incremental_lift_pct": 6.0,
                "predicted_iroas": 1.7,
                "source": "geox_holdout",
            }
        ],
        calibration_path=str(calibration_path),
        config=SyntheticLiftPriorConfig(geox_calibration_enabled=True),
    )

    assert calibration_path.exists()
    persisted_payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    reloaded = load_synthetic_lift_calibration_state(str(calibration_path))

    assert updated.observation_count == 1
    assert persisted_payload["observation_count"] == 1
    assert reloaded.observation_count == 1
    assert reloaded.lift_bias_pct == updated.lift_bias_pct
