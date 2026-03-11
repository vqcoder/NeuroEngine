# Synthetic Lift Prior

## Scope

`synthetic_lift_prior` is a predictive prior that estimates directional incremental lift potential and iROAS before incrementality truth validation.

It is not a measured GeoX/holdout outcome.

## Inputs

The module combines:

- taxonomy diagnostics when available:
  - `attentional_synchrony`
  - `narrative_control`
  - `blink_transport`
  - `reward_anticipation`
  - `boundary_encoding`
  - `cta_reception`
  - `social_transmission`
  - `self_relevance`
  - inverse AU friction contribution (`au_friction`)
- legacy performance features:
  - `attention_synchrony`
  - `blink_synchrony`
  - `grip_control_score`
  - timeline `reward_proxy` mean
  - timeline `attention_score` mean
  - dead-zone control ratio
  - quality signal (`tracking_confidence`, `quality_score`)

## Outputs

`aggregate_metrics.synthetic_lift_prior` includes:

- `global_score` (0-100)
- `predicted_incremental_lift_pct`
- `predicted_iroas`
- uncertainty intervals:
  - `incremental_lift_ci_low` / `incremental_lift_ci_high`
  - `iroas_ci_low` / `iroas_ci_high`
- `uncertainty_band`
- `calibration_status`
- `model_version`
- evidence windows and feature inputs

## Calibration hook

Calibration state can be updated from completed experiment results through:

- `parse_incrementality_observations(...)`
- `apply_incrementality_calibration_updates(...)`
- `update_calibration_state_from_experiments(...)`
- `ingest_incrementality_experiment_results(...)`
- `reconcile_incrementality_calibration_store(...)`

First-class API surface for orchestration:

- `POST /calibration/synthetic-lift/experiments`
  - persists completed GeoX/holdout experiment rows idempotently
  - optionally applies calibration updates immediately (`apply_calibration_updates=true`)
- `GET /calibration/synthetic-lift/status`
  - returns persisted calibration state + pending experiment count

Current behavior when GeoX is not wired in:

- state is loaded from `SYNTHETIC_LIFT_PRIOR_CALIBRATION_PATH` if present
- experiment ingestion remains explicit, but persistence/reconciliation is now first-class
- `calibration_status` reports `truth_layer_unavailable` when `GEOX_CALIBRATION_ENABLED=false`

## Claim-safe language

- Use `predicted`, `prior`, `estimated`, and `directional`.
- Do not present this module as measured causal lift.
