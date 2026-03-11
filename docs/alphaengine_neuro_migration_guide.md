# AlphaEngine Neuro Score Migration Guide

Date: 2026-03-08  
Status: integration-ready, backward-compatible rollout

## Purpose

Migrate from legacy emotion/attention wording to the new neuroscience-driven score taxonomy without breaking existing integrations.

This guide is grounded in the current code paths in this repository.

## End-to-end flow (current implementation)

### 1) Asset upload and session ingest

- Watchlab upload entrypoint: `apps/watchlab/app/api/upload/route.ts`
  - `forwardToBiograph(...)` creates/uses study + video + session.
  - Forwards trace rows to `POST /sessions/{id}/trace`.
  - Forwards playback events to `POST /sessions/{id}/telemetry`.
  - Forwards annotations to `POST /sessions/{id}/annotations`.
  - Forwards survey to `POST /sessions/{id}/survey`.
- Canonical trace-row guard and fallback behavior: `apps/watchlab/lib/traceRows.ts`
  - Uses provided canonical `traceRows` when available.
  - Synthetic fallback is opt-in by study/env.

### 2) Timeline analysis and feature store

- API endpoints:
  - `POST /videos/{id}/timeline-analysis`
  - `GET /timeline-analysis/{analysis_id}`
  - `GET /timeline-features/{asset_id}`
  - Implemented in `services/biograph_api/app/main.py`.
- Orchestration and idempotency:
  - `prepare_timeline_analysis_job(...)`
  - `complete_timeline_analysis_job(...)`
  - in `services/biograph_api/app/timeline_feature_store.py`.
- Persistence tables:
  - `video_timeline_analyses`
  - `video_timeline_segments`
  - `video_feature_tracks`
  - in `services/biograph_api/app/models.py`.

### 3) Score computation and rollups

- Readout builder: `build_video_readout(...)` in `services/biograph_api/app/services.py`.
  - Pulls timeline window features via `query_timeline_features_window(...)`.
  - Computes aggregate diagnostics:
    - attentional synchrony
    - narrative control
    - blink transport
    - reward anticipation
    - boundary encoding
    - CTA reception
    - social transmission
    - self relevance
    - AU friction
    - synthetic lift prior
- Taxonomy composition:
  - `build_neuro_score_taxonomy(...)` in `services/biograph_api/app/neuro_score_taxonomy.py`.
- Product rollups:
  - `build_product_rollup_presentation(...)` in `services/biograph_api/app/product_rollups.py`.
- Observability and claim-safety governance:
  - `services/biograph_api/app/neuro_observability.py`
  - `services/biograph_api/app/claim_safety.py`
  - `services/biograph_api/app/neuro_eval_runner.py`
- Incrementality calibration persistence/reconciliation:
  - `POST /calibration/synthetic-lift/experiments`
  - `GET /calibration/synthetic-lift/status`
  - `services/biograph_api/app/synthetic_lift_prior.py`

### 4) Bidder/prior ranking surfaces

- In-stack prior outputs:
  - `synthetic_lift_prior` diagnostics in `services/biograph_api/app/synthetic_lift_prior.py`
  - enterprise rollup: `paid_lift_prior` / synthetic-vs-measured summary in `services/biograph_api/app/product_rollups.py`.
- API surface:
  - `GET /videos/{video_id}/readout` returns `product_rollups`.
  - `GET /videos/{video_id}/readout/export-package` includes `product_rollups`.
- Offline optimization package (currently separate from API runtime):
  - `ml/inference/optimizer/optimizer/engine.py` (`optimize_video_summary(...)`).

### 5) API and dashboard consumption

- Readout endpoints in `services/biograph_api/app/main.py`:
  - `GET /videos/{video_id}/readout`
  - `GET /videos/{video_id}/readout/export-package`
- Dashboard consumers:
  - API client: `apps/dashboard/src/api.ts`
  - timeline report page: `apps/dashboard/src/pages/VideoTimelineReportPage.tsx`
  - timeline track mapping: `apps/dashboard/src/utils/timelineReport.ts`
  - product rollup UI: `apps/dashboard/src/components/ProductRollupPanel.tsx`
  - exporter serialization: `apps/dashboard/src/utils/exporters.ts`

## Legacy -> new taxonomy mapping

| Legacy concept | Migration target | Compatibility behavior |
| --- | --- | --- |
| `emotion` summary wording | `reward_anticipation_index`, `au_friction_score` | Legacy adapter emitted in `legacy_score_adapters` |
| `attention` summary wording | `arrest_score`, `attentional_synchrony_index` | Legacy adapter emitted in `legacy_score_adapters` |
| `dopamine` / `dopamine_score` ingest keys | `reward_proxy` | Mapped server-side in `parse_trace_jsonl(...)` |
| face-emotion truth framing | AU diagnostic framing | AU traces + AU friction only; diagnostic scope |

## Backward compatibility contract

- Existing traces remain available:
  - `traces.attention_score`
  - `traces.reward_proxy`
  - existing scene/cut/CTA overlays.
- Additive fields (optional/null-safe):
  - `neuro_scores`
  - `product_rollups`
  - `legacy_score_adapters`
- Deprecated aliases still accepted for ingest:
  - `dopamine`, `dopamine_score`, `dopamineScore`
  - `t_ms` (mapped to `video_time_ms`)
- Strict mode exists for migration enforcement:
  - `STRICT_CANONICAL_TRACE_FIELDS` (`strict_canonical_trace_fields` setting).

## Feature flags and rollout controls

- `neuro_score_taxonomy_enabled` (default: true): gates taxonomy and product-rollup composition.
- `product_rollups_enabled` (default: true): gates creator/enterprise rollup payloads.
- `blink_transport_enabled` (default: true): gates blink transport diagnostics.
- `geox_calibration_enabled` (default: false): controls GeoX calibration behavior for synthetic lift prior.
- `neuro_observability_enabled` (default: true): emits observability snapshots.

All flags are defined in `services/biograph_api/app/config.py` and documented in `services/biograph_api/.env.example`.

## Migration steps for consumers

1. Read from `neuro_scores.scores.*` for all new score families.
2. Use `neuro_scores.rollups.*` for taxonomy-native rollups.
3. Use `product_rollups.creator` or `product_rollups.enterprise` for product-tier UX.
4. Keep fallback to legacy fields/adapters until all clients are migrated.
5. After migration, enable strict canonical ingest in non-demo environments.

## Do not break

- Do not remove legacy ingest aliases until downstream clients are migrated.
- Do not remove `/videos/{id}/summary` while existing clients still call it.
- Do not expose facial outputs as truth/causal performance claims.
- Do not imply measured biochemical/neural readout in API/UI copy.
- Do not couple predicted lift prior with measured lift truth; keep both explicit and separate.

## Known limitations

- `ml/inference/optimizer` remains an offline pipeline package and is not yet a first-class `biograph_api` endpoint.
