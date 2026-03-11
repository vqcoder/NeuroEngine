# Neuro Score Taxonomy Migration Notes

Date: 2026-03-07

## Summary

This change adds an additive neuro-score taxonomy contract to readout payloads and export artifacts without removing or renaming existing fields.

## Added Contracts

- Shared canonical contracts:
  - `packages/common/zod/neuroScoreTaxonomy.ts`
  - `packages/common/pydantic/neuro_score_taxonomy.py`
- API contracts:
  - `services/biograph_api/app/schemas.py` (`NeuroScoreTaxonomy`, score families, rollups, registry entries, legacy adapters)

## Serialization and API Surface

- `GET /videos/{video_id}/readout` now includes:
  - `neuro_scores` (optional object)
  - `legacy_score_adapters` (array)
- `GET /videos/{video_id}/readout/export-package` now includes taxonomy fields inside:
  - `readout_json.neuro_scores`
  - `readout_json.legacy_score_adapters`
  - `compact_report.neuro_scores`
  - `compact_report.legacy_score_adapters`

## Compatibility Layer

- Legacy score adapters are emitted to preserve migration compatibility:
  - `attention` -> `arrest_score`
  - `emotion` -> `reward_anticipation_index`
  - Note: `emotion` is deprecated for facial interpretation surfaces; AU-level consumers should migrate to `au_friction_score` + `traces.au_channels`.
- Existing readout traces and metrics remain unchanged:
  - `traces.attention_score`
  - `traces.reward_proxy`
  - `aggregate_metrics.*`
- Structured reward anticipation diagnostics are additive under:
  - `aggregate_metrics.reward_anticipation`
- No existing fields were removed.

## Synthetic Lift Prior Notes

- `scores.synthetic_lift_prior` now prefers structured `aggregate_metrics.synthetic_lift_prior` diagnostics when available.
- The synthetic lift output remains a predicted prior and is explicitly distinct from measured incrementality truth.
- GeoX/holdout truth-layer integration is represented through calibration hooks and status fields:
  - `calibration_status`
  - uncertainty intervals
  - calibration observation count
- Legacy fallback remains active when structured diagnostics are unavailable.

## Runtime Safety

- Neuro taxonomy composition is wrapped with a compatibility guard in the readout service.
- If taxonomy composition fails, readout payload generation continues with existing fields.

## Data Migration

- No database schema migration required.
- No backfill required.
- Taxonomy is computed at read time from existing traces/segments/diagnostics/labels.
