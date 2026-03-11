# Neuro Score Eval + Observability Governance

## Scope

This layer adds non-blocking governance for the AlphaEngine neuro score stack:

- offline known-good vs known-bad creative evaluation
- model-version drift tracking
- fallback-path and missing-signal monitoring
- confidence distribution monitoring
- claim-safety and privacy/ethics checks

It is additive and does not alter score computation outputs.

## Offline Eval Harness

Dataset fixture:

- `/Users/johnkim/Documents/neurotrace/fixtures/neuro_score_pattern_eval_dataset.json`

Runner:

```bash
cd /Users/johnkim/Documents/neurotrace/services/biograph_api
uv run python -m app.neuro_eval_runner
```

Optional output file:

```bash
cd /Users/johnkim/Documents/neurotrace/services/biograph_api
uv run python -m app.neuro_eval_runner \
  --output /Users/johnkim/Documents/neurotrace/fixtures/neuro_eval_summary.sample.json
```

The summary includes:

- expectation pass/fail counts
- drift checks across model versions
- missing-signal rates
- fallback-path usage rates
- confidence distribution histogram
- claim-safety violations in eval fixture notes

## Runtime Observability

Readout generation now emits a structured log event:

- event key: `neuro_score_observability`

Telemetry payload includes:

- score availability + missing-signal rate
- confidence distribution
- per-module pathway usage + fallback rate
- privacy/ethics checks for biometric signal contexts
- drift vs prior model-signature snapshot (if history is configured)

## Config

`services/biograph_api` env vars:

- `NEURO_OBSERVABILITY_ENABLED` (`true` default)
- `NEURO_OBSERVABILITY_HISTORY_PATH` (empty default; set to enable JSONL history persistence)
- `NEURO_OBSERVABILITY_HISTORY_MAX_ENTRIES` (`500` default)
- `NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD` (`12.0` default)

If history path is unset, drift still reports but returns `no_reference` until history exists.

## Model Version Governance

- Source of model version truth is each score contract’s `model_version`.
- Drift compares same metric keys between current snapshot and prior snapshot from a different model signature.
- Alerts are raised when per-metric absolute deltas cross `NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD`.
- This complements (not replaces) `readout_guardian` baseline checks.

## Privacy + Ethics Checks

Observability payload includes quality-context checks when biometric pathways are active:

- missing quality summary
- missing or low tracking confidence context
- synthetic/mixed trace source warning

These checks are diagnostics and should be reviewed alongside consent/privacy policies.

Red-team review checklist:

- `/Users/johnkim/Documents/neurotrace/docs/neuro_red_team_checklist.md`
