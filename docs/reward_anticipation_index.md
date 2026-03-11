# Reward Anticipation Index

This module estimates anticipatory pull into payoff moments from behavioral timing proxies.

## Output Surface

- `aggregate_metrics.reward_anticipation.global_score` (0-100)
- `aggregate_metrics.reward_anticipation.confidence` (0-1)
- `aggregate_metrics.reward_anticipation.pathway`
- `aggregate_metrics.reward_anticipation.anticipation_ramps[]`
- `aggregate_metrics.reward_anticipation.payoff_windows[]`
- `aggregate_metrics.reward_anticipation.warnings[]`
- `aggregate_metrics.reward_anticipation.evidence_summary`
- `aggregate_metrics.reward_anticipation.signals_used[]`
- Dashboard aggregate view includes a dedicated Reward Anticipation diagnostics card with jump-to-window controls.

## Signals Used

- pre-payoff attention concentration
- blink suppression leading into payoff windows
- reward/arousal slope into reveal windows
- uncertainty-to-resolution timing
- tension/release structure from cadence, pacing, and audio intensity proxies

The index is a claim-safe proxy. It is not a direct biochemical measurement.

## Pathways

- `timeline_dynamics`:
  - uses timeline cadence/audio plus readout traces.
- `fallback_proxy`:
  - uses readout traces without sufficient timeline dynamics coverage.
  - confidence is downweighted.
- `insufficient_data`:
  - returned when payoff/ramp evidence is too sparse.

## Warnings

Warning keys may include:

- `late_resolution`
- `tension_without_resolution`
- `weak_payoff_release`

These warnings indicate timing risk patterns, not medical or neural conclusions.

## Backward Compatibility

- Neuro taxonomy still exposes `reward_anticipation_index` with fallback behavior.
- Legacy ingest aliases remain accepted and mapped server-side:
  - `dopamine`
  - `dopamine_score`
  - `dopamineScore`
- Strict deprecation mode:
  - `STRICT_CANONICAL_TRACE_FIELDS=true` rejects alias-only trace rows and requires canonical `reward_proxy` and `video_time_ms`.
- Predict API keeps a deprecated compatibility alias:
  - `dopamine_score` mirrors `reward_proxy` during migration.
