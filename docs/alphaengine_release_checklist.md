# AlphaEngine Neuro Release Checklist

Date: 2026-03-08

## 1) Pre-release gates

- [ ] Confirm migration/compat docs are published:
  - `docs/alphaengine_neuro_migration_guide.md`
  - `docs/neuro_score_taxonomy_migration.md`
- [ ] Confirm claim-safe copy guardrails are active:
  - `services/biograph_api/app/claim_safety.py`
- [ ] Confirm feature flags are explicitly reviewed:
  - `neuro_score_taxonomy_enabled`
  - `product_rollups_enabled`
  - `blink_transport_enabled`
  - `geox_calibration_enabled`
  - `neuro_observability_enabled`

## 2) Schema and contract compatibility

- [ ] `ReadoutPayload` stays backward-compatible (`neuro_scores`/`product_rollups` additive).
- [ ] Legacy adapters are present for migrating clients (`legacy_score_adapters`).
- [ ] Legacy ingest aliases still accepted unless strict mode is intentionally enabled:
  - `dopamine*` -> `reward_proxy`
  - `t_ms` -> `video_time_ms`
- [ ] Shared contract fixtures validate for both Pydantic and Zod.

## 3) Data and pipeline checks

- [ ] Timeline analysis job succeeds (`POST /videos/{id}/timeline-analysis`).
- [ ] Timeline feature query works (`GET /timeline-features/{asset_id}`).
- [ ] Readout includes taxonomy and rollup payloads when enabled:
  - `GET /videos/{id}/readout`
  - `GET /videos/{id}/readout/export-package`
- [ ] Observability snapshots and drift tracking are enabled/logging.

## 4) Test and quality gates

Run and require green:

```bash
# API + scoring + observability
cd services/biograph_api && uv run python -m pytest

# Extractor worker
cd services/extractor_worker && uv run python -m pytest

# Training pipeline
cd ml/training && uv run python -m pytest

# Inference optimizer package
cd ml/inference/optimizer && ../../training/.venv/bin/python -m pytest

# Dashboard
cd apps/dashboard && npm run lint
cd apps/dashboard && npm run typecheck
cd apps/dashboard && npm run test:unit
cd apps/dashboard && npm run test:e2e

# Watchlab
cd apps/watchlab && npm test -- --runInBand
cd apps/watchlab && npm run build
cd apps/watchlab && npm run test:e2e
```

## 5) Smoke checks (manual)

- [ ] Watchlab upload completes and forwards traces/telemetry/annotations/survey.
- [ ] Dashboard `/videos/:videoId` renders readout and scorecards.
- [ ] Dashboard `/videos/:videoId/timeline-report` renders track lanes and key moments.
- [ ] Creator mode rollup renders simple warnings/explanations.
- [ ] Enterprise mode rollup renders paid lift prior + synthetic vs measured distinction.

## 6) Do not break constraints

- [ ] No direct biochemical/neural measurement claims in UI/API/docs.
- [ ] Facial analysis remains AU-diagnostic and quality-scoped.
- [ ] GeoX/measured lift remains distinct from synthetic prior outputs.
- [ ] Experimental pathways are behind feature flags.

## 7) Rollback and mitigation

- [ ] Fast rollback path: disable `neuro_score_taxonomy_enabled`.
- [ ] If rollups cause client issues: disable `product_rollups_enabled`.
- [ ] Keep core readout traces/segments endpoint behavior stable under rollback.
- [ ] Capture incident notes with failing endpoint, workspace tier, and feature-flag state.
