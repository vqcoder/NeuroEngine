# @neurotrace/common

Shared schema contracts with parity targets across:

- `zod/` (TypeScript runtime validation)
- `pydantic/` (Python runtime validation)

Current contract focus: session upload bundle used by `watchlab` and `biograph_api`.

Additional contract focus: neuro-score taxonomy payloads used by readout APIs and dashboard rendering.
Additional contract focus: readout aggregate synchrony diagnostics (`attentional_synchrony`) used by dashboard timeline evidence views.
Additional contract focus: readout narrative grammar diagnostics (`narrative_control`) for per-scene control scoring and explainability.
Additional contract focus: blink transport diagnostics (`blink_transport`) for timeline evidence and warning overlays.
Additional contract focus: reward anticipation diagnostics (`reward_anticipation`) for payoff-ramp timeline explainability.
Additional contract focus: boundary encoding diagnostics (`boundary_encoding`) for event-boundary payload placement and overload-risk explainability.
Additional contract focus: synthetic lift prior diagnostics (`synthetic_lift_prior`) for predicted incremental lift/iROAS priors with uncertainty and calibration status.
Additional contract focus: product-facing rollup presentation payloads (`creator` and `enterprise` modes) layered on top of shared taxonomy scores.
Additional shared config: `quality_thresholds.json` for extractor quality-flag thresholds and readout quality badge thresholds.

The shared bundle includes:

- passive playback telemetry aligned to `videoTimeMs`
- post-view annotation markers
- post-video survey responses
- optional dial replay samples (annotation mode only)
- webcam frames and/or frame pointers

Reference payload:

- [examples/session_bundle.sample.json](/Users/johnkim/Documents/Personal CRM and Project management app/Alpha Engine/Alpha Engine/neurotrace/packages/common/examples/session_bundle.sample.json)
- [/Users/johnkim/Documents/neurotrace/fixtures/neuro_score_taxonomy.sample.json](/Users/johnkim/Documents/neurotrace/fixtures/neuro_score_taxonomy.sample.json) (neuro-score taxonomy sample)
- [/Users/johnkim/Documents/neurotrace/fixtures/readout_aggregate_metrics.sample.json](/Users/johnkim/Documents/neurotrace/fixtures/readout_aggregate_metrics.sample.json) (aggregate synchrony + narrative diagnostics sample)
- [/Users/johnkim/Documents/neurotrace/fixtures/product_rollups_creator.sample.json](/Users/johnkim/Documents/neurotrace/fixtures/product_rollups_creator.sample.json) (creator mode product rollup sample)
- [/Users/johnkim/Documents/neurotrace/fixtures/product_rollups_enterprise.sample.json](/Users/johnkim/Documents/neurotrace/fixtures/product_rollups_enterprise.sample.json) (enterprise mode product rollup sample)
