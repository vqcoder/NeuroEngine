"""Synthetic lift prior diagnostics with optional truth-layer calibration hooks."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import IncrementalityExperimentResult
from .readout_metrics import clamp

from .schemas import (
    AttentionalSynchronyDiagnostics,
    AuFrictionDiagnostics,
    BlinkTransportDiagnostics,
    BoundaryEncodingDiagnostics,
    CtaReceptionDiagnostics,
    NarrativeControlDiagnostics,
    RewardAnticipationDiagnostics,
    SelfRelevanceDiagnostics,
    SocialTransmissionDiagnostics,
    SyntheticLiftCalibrationStatus,
    SyntheticLiftPriorDiagnostics,
    SyntheticLiftPriorFeatureInput,
    SyntheticLiftPriorFeatureInputSource,
    SyntheticLiftPriorPathway,
    SyntheticLiftPriorTimelineWindow,
)


SYNTHETIC_LIFT_MODEL_VERSION = "synthetic_lift_prior_v1"


@dataclass(frozen=True)
class SyntheticLiftPriorConfig:
    attentional_synchrony_weight: float = 0.12
    narrative_control_weight: float = 0.11
    blink_transport_weight: float = 0.08
    reward_anticipation_weight: float = 0.13
    boundary_encoding_weight: float = 0.1
    cta_reception_weight: float = 0.11
    social_transmission_weight: float = 0.1
    self_relevance_weight: float = 0.08
    au_friction_inverse_weight: float = 0.05
    legacy_attention_synchrony_weight: float = 0.04
    legacy_blink_synchrony_weight: float = 0.03
    legacy_grip_control_weight: float = 0.04
    reward_mean_weight: float = 0.05
    attention_mean_weight: float = 0.03
    dead_zone_control_weight: float = 0.02
    quality_signal_weight: float = 0.01
    min_tracking_confidence: float = 0.3
    min_quality_score: float = 0.25
    fallback_confidence_cap: float = 0.68
    max_evidence_windows: int = 4
    min_truth_observations: int = 5
    geox_calibration_enabled: bool = False


@dataclass(frozen=True)
class SyntheticLiftCalibrationState:
    model_version: str = SYNTHETIC_LIFT_MODEL_VERSION
    truth_layer: str = "stub"
    observation_count: int = 0
    lift_bias_pct: float = 0.0
    iroas_bias: float = 0.0
    uncertainty_scale: float = 1.0
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class IncrementalityObservation:
    experiment_id: str
    measured_incremental_lift_pct: float
    measured_iroas: float
    predicted_incremental_lift_pct: Optional[float] = None
    predicted_iroas: Optional[float] = None
    source: str = "unknown"


@dataclass(frozen=True)
class IncrementalityExperimentIngestResult:
    ingested_count: int
    duplicate_count: int


@dataclass(frozen=True)
class IncrementalityCalibrationReconciliationResult:
    calibration_state: SyntheticLiftCalibrationState
    applied_count: int
    pending_before: int
    pending_after: int


def resolve_synthetic_lift_prior_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> SyntheticLiftPriorConfig:
    """Resolve synthetic-lift config from env and optional video-level overrides."""

    settings = get_settings()
    config = SyntheticLiftPriorConfig(
        geox_calibration_enabled=bool(settings.geox_calibration_enabled),
    )

    settings_overrides = _parse_override_payload(settings.synthetic_lift_prior_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("synthetic_lift_prior_config", "syntheticLiftPriorConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def load_synthetic_lift_calibration_state(
    calibration_path: Optional[str] = None,
) -> SyntheticLiftCalibrationState:
    """Load calibration state persisted from completed incrementality experiments."""

    path = _resolve_calibration_path(calibration_path)
    if path is None or not path.exists():
        return SyntheticLiftCalibrationState()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SyntheticLiftCalibrationState()

    if not isinstance(payload, Mapping):
        return SyntheticLiftCalibrationState()

    return SyntheticLiftCalibrationState(
        model_version=str(payload.get("model_version") or SYNTHETIC_LIFT_MODEL_VERSION),
        truth_layer=str(payload.get("truth_layer") or "stub"),
        observation_count=max(int(_to_float(payload.get("observation_count"), 0.0)), 0),
        lift_bias_pct=_to_float(payload.get("lift_bias_pct"), 0.0),
        iroas_bias=_to_float(payload.get("iroas_bias"), 0.0),
        uncertainty_scale=clamp(_to_float(payload.get("uncertainty_scale"), 1.0), 0.35, 2.0),
        updated_at=(
            str(payload.get("updated_at"))
            if payload.get("updated_at") is not None
            else None
        ),
    )


def persist_synthetic_lift_calibration_state(
    state: SyntheticLiftCalibrationState,
    *,
    calibration_path: Optional[str] = None,
) -> None:
    """Persist calibration state for later inference calls."""

    path = _resolve_calibration_path(calibration_path)
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def parse_incrementality_observations(
    experiment_results: Sequence[Mapping[str, Any]],
) -> List[IncrementalityObservation]:
    """Normalize completed incrementality results into calibration observations."""

    output: List[IncrementalityObservation] = []
    for index, item in enumerate(experiment_results):
        measured_lift = _first_float(
            item,
            (
                "measured_incremental_lift_pct",
                "incremental_lift_pct",
                "measured_lift_pct",
                "lift_pct",
            ),
        )
        measured_iroas = _first_float(
            item,
            (
                "measured_iroas",
                "iroas",
                "incremental_iroas",
            ),
        )
        if measured_lift is None or measured_iroas is None:
            continue

        experiment_id = _resolve_experiment_identifier(item, index)
        predicted_lift = _first_float(
            item,
            (
                "predicted_incremental_lift_pct",
                "predicted_lift_pct",
            ),
        )
        predicted_iroas = _first_float(
            item,
            (
                "predicted_iroas",
                "predicted_incremental_iroas",
            ),
        )
        source = str(item.get("source") or item.get("truth_source") or "unknown")

        output.append(
            IncrementalityObservation(
                experiment_id=experiment_id,
                measured_incremental_lift_pct=float(measured_lift),
                measured_iroas=float(measured_iroas),
                predicted_incremental_lift_pct=(
                    float(predicted_lift) if predicted_lift is not None else None
                ),
                predicted_iroas=(float(predicted_iroas) if predicted_iroas is not None else None),
                source=source,
            )
        )
    return output


def ingest_incrementality_experiment_results(
    db: Session,
    *,
    experiment_results: Sequence[Mapping[str, Any]],
) -> IncrementalityExperimentIngestResult:
    """Persist completed incrementality experiments for idempotent calibration reconciliation."""

    observations = parse_incrementality_observations(experiment_results)
    if not observations:
        return IncrementalityExperimentIngestResult(ingested_count=0, duplicate_count=0)

    raw_by_experiment: Dict[str, Mapping[str, Any]] = {}
    for index, payload in enumerate(experiment_results):
        experiment_id = _resolve_experiment_identifier(payload, index)
        raw_by_experiment.setdefault(experiment_id, payload)

    ingested_count = 0
    duplicate_count = 0
    seen_ids: set[str] = set()
    for observation in observations:
        if observation.experiment_id in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(observation.experiment_id)

        existing = db.scalar(
            select(IncrementalityExperimentResult).where(
                IncrementalityExperimentResult.experiment_id == observation.experiment_id
            )
        )
        if existing is not None:
            duplicate_count += 1
            continue

        raw_payload = raw_by_experiment.get(observation.experiment_id)
        db.add(
            IncrementalityExperimentResult(
                experiment_id=observation.experiment_id,
                source=observation.source,
                measured_incremental_lift_pct=float(observation.measured_incremental_lift_pct),
                measured_iroas=float(observation.measured_iroas),
                predicted_incremental_lift_pct=observation.predicted_incremental_lift_pct,
                predicted_iroas=observation.predicted_iroas,
                completed_at=_resolve_experiment_completed_at(raw_payload),
                calibration_applied_at=None,
                calibration_run_id=None,
                raw_payload=_json_safe_payload(raw_payload),
            )
        )
        ingested_count += 1

    return IncrementalityExperimentIngestResult(
        ingested_count=ingested_count,
        duplicate_count=duplicate_count,
    )


def reconcile_incrementality_calibration_store(
    db: Session,
    *,
    calibration_path: Optional[str] = None,
    config: Optional[SyntheticLiftPriorConfig] = None,
) -> IncrementalityCalibrationReconciliationResult:
    """Apply pending persisted incrementality experiments to calibration state."""

    pending_rows = list(
        db.scalars(
            select(IncrementalityExperimentResult)
            .where(IncrementalityExperimentResult.calibration_applied_at.is_(None))
            .order_by(
                func.coalesce(
                    IncrementalityExperimentResult.completed_at,
                    IncrementalityExperimentResult.created_at,
                ).asc(),
                IncrementalityExperimentResult.created_at.asc(),
            )
        )
    )
    pending_before = len(pending_rows)
    current_state = load_synthetic_lift_calibration_state(calibration_path)
    if not pending_rows:
        return IncrementalityCalibrationReconciliationResult(
            calibration_state=current_state,
            applied_count=0,
            pending_before=0,
            pending_after=0,
        )

    observations = [
        IncrementalityObservation(
            experiment_id=row.experiment_id,
            measured_incremental_lift_pct=float(row.measured_incremental_lift_pct),
            measured_iroas=float(row.measured_iroas),
            predicted_incremental_lift_pct=(
                float(row.predicted_incremental_lift_pct)
                if row.predicted_incremental_lift_pct is not None
                else None
            ),
            predicted_iroas=float(row.predicted_iroas) if row.predicted_iroas is not None else None,
            source=row.source,
        )
        for row in pending_rows
    ]
    updated_state = apply_incrementality_calibration_updates(
        current_state,
        observations=observations,
        config=config,
    )
    persist_synthetic_lift_calibration_state(updated_state, calibration_path=calibration_path)

    applied_at = datetime.now(timezone.utc)
    calibration_run_id = uuid4()
    for row in pending_rows:
        row.calibration_applied_at = applied_at
        row.calibration_run_id = calibration_run_id

    db.flush()
    pending_after = int(
        db.scalar(
            select(func.count())
            .select_from(IncrementalityExperimentResult)
            .where(IncrementalityExperimentResult.calibration_applied_at.is_(None))
        )
        or 0
    )
    return IncrementalityCalibrationReconciliationResult(
        calibration_state=updated_state,
        applied_count=len(pending_rows),
        pending_before=pending_before,
        pending_after=pending_after,
    )


def get_incrementality_experiment_store_counts(db: Session) -> tuple[int, int]:
    """Return total and pending experiment counts for calibration observability."""

    total = int(db.scalar(select(func.count()).select_from(IncrementalityExperimentResult)) or 0)
    pending = int(
        db.scalar(
            select(func.count())
            .select_from(IncrementalityExperimentResult)
            .where(IncrementalityExperimentResult.calibration_applied_at.is_(None))
        )
        or 0
    )
    return total, pending


def get_last_calibration_applied_at(db: Session) -> Optional[datetime]:
    """Return latest calibration application timestamp across persisted observations."""

    return db.scalar(select(func.max(IncrementalityExperimentResult.calibration_applied_at)))


def apply_incrementality_calibration_updates(
    state: SyntheticLiftCalibrationState,
    *,
    observations: Sequence[IncrementalityObservation],
    config: Optional[SyntheticLiftPriorConfig] = None,
) -> SyntheticLiftCalibrationState:
    """Update calibration offsets from completed incrementality observations."""

    cleaned = list(observations)
    if not cleaned:
        return state

    resolved = config or SyntheticLiftPriorConfig()
    residual_lift: List[float] = []
    residual_iroas: List[float] = []

    for item in cleaned:
        baseline_lift = item.predicted_incremental_lift_pct or 0.0
        baseline_iroas = item.predicted_iroas or 1.0
        residual_lift.append(float(item.measured_incremental_lift_pct) - float(baseline_lift))
        residual_iroas.append(float(item.measured_iroas) - float(baseline_iroas))

    residual_lift_mean = _safe_mean(residual_lift) or 0.0
    residual_iroas_mean = _safe_mean(residual_iroas) or 0.0

    learning_rate = clamp(len(cleaned) / float(len(cleaned) + 8), 0.12, 0.55)
    next_lift_bias = state.lift_bias_pct + (learning_rate * (residual_lift_mean - state.lift_bias_pct))
    next_iroas_bias = state.iroas_bias + (learning_rate * (residual_iroas_mean - state.iroas_bias))

    next_count = state.observation_count + len(cleaned)
    uncertainty_reduction = 1.0 - min(0.35, 0.045 * len(cleaned))
    next_uncertainty_scale = clamp(
        state.uncertainty_scale * uncertainty_reduction,
        0.5,
        2.0,
    )

    truth_layer = state.truth_layer
    if any(_looks_like_geox_source(item.source) for item in cleaned):
        truth_layer = "geox"
    elif truth_layer == "stub" and resolved.geox_calibration_enabled:
        truth_layer = "incrementality_feed"

    return SyntheticLiftCalibrationState(
        model_version=SYNTHETIC_LIFT_MODEL_VERSION,
        truth_layer=truth_layer,
        observation_count=next_count,
        lift_bias_pct=round(next_lift_bias, 6),
        iroas_bias=round(next_iroas_bias, 6),
        uncertainty_scale=round(next_uncertainty_scale, 6),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def update_calibration_state_from_experiments(
    *,
    experiment_results: Sequence[Mapping[str, Any]],
    calibration_path: Optional[str] = None,
    config: Optional[SyntheticLiftPriorConfig] = None,
) -> SyntheticLiftCalibrationState:
    """Update persisted calibration state from completed truth-layer experiments."""

    observations = parse_incrementality_observations(experiment_results)
    current_state = load_synthetic_lift_calibration_state(calibration_path)
    updated_state = apply_incrementality_calibration_updates(
        current_state,
        observations=observations,
        config=config,
    )
    persist_synthetic_lift_calibration_state(updated_state, calibration_path=calibration_path)
    return updated_state


def compute_synthetic_lift_prior_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    window_ms: int,
    attention_synchrony: Optional[float] = None,
    blink_synchrony: Optional[float] = None,
    grip_control_score: Optional[float] = None,
    attentional_synchrony: Optional[AttentionalSynchronyDiagnostics] = None,
    narrative_control: Optional[NarrativeControlDiagnostics] = None,
    blink_transport: Optional[BlinkTransportDiagnostics] = None,
    reward_anticipation: Optional[RewardAnticipationDiagnostics] = None,
    boundary_encoding: Optional[BoundaryEncodingDiagnostics] = None,
    cta_reception: Optional[CtaReceptionDiagnostics] = None,
    social_transmission: Optional[SocialTransmissionDiagnostics] = None,
    self_relevance: Optional[SelfRelevanceDiagnostics] = None,
    au_friction: Optional[AuFrictionDiagnostics] = None,
    config: Optional[SyntheticLiftPriorConfig] = None,
    calibration_state: Optional[SyntheticLiftCalibrationState] = None,
) -> SyntheticLiftPriorDiagnostics:
    """Estimate a synthetic lift/iROAS prior from taxonomy and legacy readout signals."""

    resolved = config or SyntheticLiftPriorConfig(
        geox_calibration_enabled=get_settings().geox_calibration_enabled,
    )
    state = calibration_state or load_synthetic_lift_calibration_state()

    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )

    feature_inputs: List[SyntheticLiftPriorFeatureInput] = []

    def add_feature(
        *,
        feature_name: str,
        raw_value: Optional[float],
        normalized_value: Optional[float],
        weight: float,
        source: SyntheticLiftPriorFeatureInputSource,
    ) -> None:
        if raw_value is None or normalized_value is None:
            return
        feature_inputs.append(
            SyntheticLiftPriorFeatureInput(
                feature_name=feature_name,
                source=source,
                raw_value=round(float(raw_value), 6),
                normalized_value=round(clamp(float(normalized_value), 0.0, 1.0), 6),
                weight=round(max(float(weight), 0.0), 6),
            )
        )

    add_feature(
        feature_name="attentional_synchrony_index",
        raw_value=attentional_synchrony.global_score if attentional_synchrony else None,
        normalized_value=_to_unit_100(attentional_synchrony.global_score if attentional_synchrony else None),
        weight=resolved.attentional_synchrony_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="narrative_control_score",
        raw_value=narrative_control.global_score if narrative_control else None,
        normalized_value=_to_unit_100(narrative_control.global_score if narrative_control else None),
        weight=resolved.narrative_control_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="blink_transport_score",
        raw_value=blink_transport.global_score if blink_transport else None,
        normalized_value=_to_unit_100(blink_transport.global_score if blink_transport else None),
        weight=resolved.blink_transport_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="reward_anticipation_index",
        raw_value=reward_anticipation.global_score if reward_anticipation else None,
        normalized_value=_to_unit_100(reward_anticipation.global_score if reward_anticipation else None),
        weight=resolved.reward_anticipation_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="boundary_encoding_score",
        raw_value=boundary_encoding.global_score if boundary_encoding else None,
        normalized_value=_to_unit_100(boundary_encoding.global_score if boundary_encoding else None),
        weight=resolved.boundary_encoding_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="cta_reception_score",
        raw_value=cta_reception.global_score if cta_reception else None,
        normalized_value=_to_unit_100(cta_reception.global_score if cta_reception else None),
        weight=resolved.cta_reception_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="social_transmission_score",
        raw_value=social_transmission.global_score if social_transmission else None,
        normalized_value=_to_unit_100(social_transmission.global_score if social_transmission else None),
        weight=resolved.social_transmission_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="self_relevance_score",
        raw_value=self_relevance.global_score if self_relevance else None,
        normalized_value=_to_unit_100(self_relevance.global_score if self_relevance else None),
        weight=resolved.self_relevance_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )
    add_feature(
        feature_name="au_friction_inverse",
        raw_value=(100.0 - float(au_friction.global_score)) if au_friction and au_friction.global_score is not None else None,
        normalized_value=(
            1.0 - _to_unit_100(au_friction.global_score)
            if au_friction and au_friction.global_score is not None
            else None
        ),
        weight=resolved.au_friction_inverse_weight,
        source=SyntheticLiftPriorFeatureInputSource.taxonomy,
    )

    add_feature(
        feature_name="attention_synchrony_legacy",
        raw_value=attention_synchrony,
        normalized_value=_to_unit_signed(attention_synchrony),
        weight=resolved.legacy_attention_synchrony_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )
    add_feature(
        feature_name="blink_synchrony_legacy",
        raw_value=blink_synchrony,
        normalized_value=_to_unit_signed(blink_synchrony),
        weight=resolved.legacy_blink_synchrony_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )
    add_feature(
        feature_name="grip_control_legacy",
        raw_value=grip_control_score,
        normalized_value=_to_unit_signed(grip_control_score),
        weight=resolved.legacy_grip_control_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )

    reward_mean = _safe_mean(
        [
            _to_float(row.get("reward_proxy"))
            for row in rows
            if row.get("reward_proxy") is not None
        ]
    )
    attention_mean = _safe_mean(
        [
            _to_float(row.get("attention_score"))
            for row in rows
            if row.get("attention_score") is not None
        ]
    )
    dead_zone_ratio = _dead_zone_ratio(rows)
    quality_signal = _quality_signal(rows, resolved)

    add_feature(
        feature_name="reward_proxy_mean",
        raw_value=reward_mean,
        normalized_value=_to_unit_100(reward_mean),
        weight=resolved.reward_mean_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )
    add_feature(
        feature_name="attention_score_mean",
        raw_value=attention_mean,
        normalized_value=_to_unit_100(attention_mean),
        weight=resolved.attention_mean_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )
    add_feature(
        feature_name="dead_zone_control",
        raw_value=(1.0 - dead_zone_ratio) * 100.0 if dead_zone_ratio is not None else None,
        normalized_value=(1.0 - dead_zone_ratio) if dead_zone_ratio is not None else None,
        weight=resolved.dead_zone_control_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )
    add_feature(
        feature_name="quality_signal",
        raw_value=quality_signal * 100.0 if quality_signal is not None else None,
        normalized_value=quality_signal,
        weight=resolved.quality_signal_weight,
        source=SyntheticLiftPriorFeatureInputSource.legacy_performance,
    )

    if not feature_inputs and not rows:
        return SyntheticLiftPriorDiagnostics(
            pathway=SyntheticLiftPriorPathway.insufficient_data,
            model_version=SYNTHETIC_LIFT_MODEL_VERSION,
            calibration_status=_resolve_calibration_status(
                state,
                geox_enabled=resolved.geox_calibration_enabled,
                min_truth_observations=resolved.min_truth_observations,
            ),
            calibration_observation_count=state.observation_count,
            calibration_last_updated_at=_parse_optional_datetime(state.updated_at),
            evidence_summary=(
                "Synthetic lift prior was unavailable because no taxonomy or legacy performance signals were present."
            ),
            signals_used=[],
        )

    total_weight = sum(max(item.weight, 0.0) for item in feature_inputs)
    weighted_sum = sum(item.normalized_value * max(item.weight, 0.0) for item in feature_inputs)
    global_unit = (weighted_sum / total_weight) if total_weight > 0 else 0.5

    taxonomy_feature_count = sum(1 for item in feature_inputs if item.source == SyntheticLiftPriorFeatureInputSource.taxonomy)
    pathway = (
        SyntheticLiftPriorPathway.taxonomy_regression
        if taxonomy_feature_count >= 5
        else SyntheticLiftPriorPathway.fallback_proxy
    )

    feature_coverage = clamp(len(feature_inputs) / 14.0, 0.0, 1.0)
    quality_mean = quality_signal if quality_signal is not None else 0.5
    calibration_bonus = clamp(state.observation_count / 30.0, 0.0, 0.2)
    confidence = clamp(
        (0.35 * quality_mean) + (0.45 * feature_coverage) + (0.2 + calibration_bonus),
        0.0,
        1.0,
    )
    if pathway == SyntheticLiftPriorPathway.fallback_proxy:
        confidence = min(confidence, resolved.fallback_confidence_cap)

    predicted_incremental_lift_pct = clamp(
        ((global_unit - 0.5) * 28.0) + state.lift_bias_pct,
        -20.0,
        35.0,
    )
    predicted_iroas = clamp(
        0.45 + (global_unit * 2.9) + state.iroas_bias,
        -2.0,
        8.0,
    )

    uncertainty_scale = clamp(state.uncertainty_scale, 0.5, 2.0)
    lift_half_width = (5.0 + ((1.0 - confidence) * 11.0)) * uncertainty_scale
    iroas_half_width = (0.3 + ((1.0 - confidence) * 1.1)) * uncertainty_scale

    lift_ci_low = predicted_incremental_lift_pct - lift_half_width
    lift_ci_high = predicted_incremental_lift_pct + lift_half_width
    iroas_ci_low = predicted_iroas - iroas_half_width
    iroas_ci_high = predicted_iroas + iroas_half_width

    evidence_windows = _build_evidence_windows(rows, window_ms=max(int(window_ms), 1), limit=resolved.max_evidence_windows)

    sorted_feature_inputs = sorted(
        feature_inputs,
        key=lambda item: abs((item.normalized_value - 0.5) * item.weight),
        reverse=True,
    )

    calibration_status = _resolve_calibration_status(
        state,
        geox_enabled=resolved.geox_calibration_enabled,
        min_truth_observations=resolved.min_truth_observations,
    )

    signals_used = sorted({item.feature_name for item in feature_inputs})
    evidence_summary = (
        "Synthetic Lift Prior combines taxonomy scores with legacy performance signals to estimate "
        "directional incremental lift and iROAS before external incrementality validation. "
        "This output is a predictive prior and not a measured GeoX/holdout result."
    )
    if calibration_status == SyntheticLiftCalibrationStatus.geox_calibrated:
        evidence_summary += " Calibration offsets were updated from completed incrementality experiments."
    elif calibration_status == SyntheticLiftCalibrationStatus.truth_layer_unavailable:
        evidence_summary += " Truth-layer calibration is currently unavailable in this environment."

    return SyntheticLiftPriorDiagnostics(
        pathway=pathway,
        global_score=round(global_unit * 100.0, 6),
        confidence=round(confidence, 6),
        predicted_incremental_lift_pct=round(predicted_incremental_lift_pct, 6),
        predicted_iroas=round(predicted_iroas, 6),
        incremental_lift_ci_low=round(lift_ci_low, 6),
        incremental_lift_ci_high=round(lift_ci_high, 6),
        iroas_ci_low=round(iroas_ci_low, 6),
        iroas_ci_high=round(iroas_ci_high, 6),
        uncertainty_band=round(lift_half_width, 6),
        calibration_status=calibration_status,
        calibration_observation_count=state.observation_count,
        calibration_last_updated_at=_parse_optional_datetime(state.updated_at),
        model_version=SYNTHETIC_LIFT_MODEL_VERSION,
        segment_scores=evidence_windows,
        feature_inputs=sorted_feature_inputs[:8],
        evidence_summary=evidence_summary,
        signals_used=signals_used,
    )


def _resolve_calibration_path(calibration_path: Optional[str]) -> Optional[Path]:
    configured = calibration_path or get_settings().synthetic_lift_prior_calibration_path
    if not configured:
        return None
    return Path(configured)


def _parse_override_payload(raw_payload: str) -> Dict[str, Any]:
    if not raw_payload:
        return {}
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _apply_overrides(
    config: SyntheticLiftPriorConfig,
    overrides: Mapping[str, Any],
) -> SyntheticLiftPriorConfig:
    valid_fields = {item.name for item in fields(config)}
    updates: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in valid_fields:
            continue
        current = getattr(config, key)
        if isinstance(current, bool):
            updates[key] = _coerce_bool(value, current)
            continue
        if isinstance(current, int):
            try:
                updates[key] = int(value)
            except (TypeError, ValueError):
                continue
            continue
        if isinstance(current, float):
            try:
                updates[key] = float(value)
            except (TypeError, ValueError):
                continue
            continue
    if not updates:
        return config
    return replace(config, **updates)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _build_evidence_windows(
    rows: Sequence[Dict[str, object]],
    *,
    window_ms: int,
    limit: int,
) -> List[SyntheticLiftPriorTimelineWindow]:
    if not rows:
        return []

    ranked = []
    for row in rows:
        start_ms = int(row.get("bucket_start") or 0)
        reward = _to_float(row.get("reward_proxy"), 50.0)
        attention = _to_float(row.get("attention_score"), 50.0)
        confidence = _safe_mean(
            [
                _to_float(row.get("tracking_confidence")),
                _to_float(row.get("quality_score")),
            ]
        ) or 0.55
        score = clamp((0.58 * reward) + (0.42 * attention), 0.0, 100.0)
        ranked.append((score, confidence, start_ms, row))

    ranked.sort(key=lambda item: item[0], reverse=True)
    output: List[SyntheticLiftPriorTimelineWindow] = []
    for score, confidence, start_ms, row in ranked[: max(limit, 1)]:
        reason = "Window combined stronger reward and attention proxies that support directional lift potential."
        if row.get("cta_id"):
            reason = "Window overlaps CTA context with stronger reward and attention support for prior lift potential."
        output.append(
            SyntheticLiftPriorTimelineWindow(
                start_ms=start_ms,
                end_ms=start_ms + window_ms,
                score=round(score, 6),
                confidence=round(clamp(confidence, 0.0, 1.0), 6),
                reason=reason,
                contribution=round((score / 100.0) * confidence, 6),
            )
        )
    return output


def _quality_signal(
    rows: Sequence[Dict[str, object]],
    config: SyntheticLiftPriorConfig,
) -> Optional[float]:
    if not rows:
        return None

    values: List[float] = []
    for row in rows:
        tracking = row.get("tracking_confidence")
        quality = row.get("quality_score")
        if tracking is not None:
            values.append(clamp(_to_float(tracking), 0.0, 1.0))
        if quality is not None:
            values.append(clamp(_to_float(quality), 0.0, 1.0))

    if not values:
        return None

    base = _safe_mean(values) or 0.0
    if base < config.min_tracking_confidence:
        return clamp(base * 0.75, 0.0, 1.0)
    return clamp(base, 0.0, 1.0)


def _dead_zone_ratio(rows: Sequence[Dict[str, object]]) -> Optional[float]:
    values = [
        _to_float(row.get("attention_score"))
        for row in rows
        if row.get("attention_score") is not None
    ]
    if not values:
        return None
    dead_count = sum(1 for value in values if value < 45.0)
    return dead_count / float(len(values))


def _resolve_calibration_status(
    state: SyntheticLiftCalibrationState,
    *,
    geox_enabled: bool,
    min_truth_observations: int,
) -> SyntheticLiftCalibrationStatus:
    if state.observation_count >= max(min_truth_observations, 1) and _looks_like_geox_source(state.truth_layer):
        return SyntheticLiftCalibrationStatus.geox_calibrated
    if state.observation_count > 0:
        return SyntheticLiftCalibrationStatus.provisional
    if not geox_enabled:
        return SyntheticLiftCalibrationStatus.truth_layer_unavailable
    return SyntheticLiftCalibrationStatus.uncalibrated


def _looks_like_geox_source(value: str) -> bool:
    lowered = value.strip().lower()
    return "geox" in lowered or "holdout" in lowered or "incrementality" in lowered


def _resolve_experiment_identifier(payload: Mapping[str, Any], index: int) -> str:
    return str(payload.get("experiment_id") or payload.get("id") or f"experiment-{index + 1}")


def _resolve_experiment_completed_at(payload: Optional[Mapping[str, Any]]) -> Optional[datetime]:
    if payload is None:
        return None
    value = payload.get("completed_at")
    if value is None:
        value = payload.get("completedAt")
    if value is None:
        value = payload.get("ended_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        normalized = candidate.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _json_safe_payload(payload: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return None

    def _convert(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(key): _convert(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [_convert(item) for item in value]
        return value

    converted = _convert(payload)
    if isinstance(converted, dict):
        return converted
    return None


def _first_float(payload: Mapping[str, Any], keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _to_unit_100(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return clamp(float(value) / 100.0, 0.0, 1.0)


def _to_unit_signed(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return clamp((float(value) + 1.0) / 2.0, 0.0, 1.0)


def _to_float(value: Any, default: Optional[float] = None) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        if default is None:
            return float("nan")
        return float(default)


def _safe_mean(values: Sequence[float]) -> Optional[float]:  # noqa: N802 — renamed from _mean to avoid shadowing services_math._mean
    cleaned = [value for value in values if value is not None and not math.isnan(float(value))]
    if not cleaned:
        return None
    return sum(cleaned) / float(len(cleaned))



def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
