# Readout Dashboard Status

## current milestone
- Milestone 5 complete: ReadoutPayload contract, readout endpoint, dashboard renderer, overlays, diagnostics, and exports are implemented.
- Current focus: integration hardening and productionization of trace ingestion quality.

## decisions made
- Canonical metric naming is `reward_proxy`; no direct dopamine measurement claims.
- UI wording uses `Reward Proxy` and describes it as a proxy/estimate.
- Dashboard remains aligned to `video_time_ms` as the canonical timeline key.
- Scene-aware identifiers (`scene_id`, `cut_id`, `cta_id`) are required where available.
- Webcam-derived traces must surface confidence and quality context.
- Laptop webcam gaze is treated as coarse on-screen proxy only.

## commands to run
- Contract/copy scans:
  - `cd neurotrace && rg -n "dopamine|reward_proxy|video_time_ms|scene_id|cut_id|cta_id" docs apps services ml packages`
- Backend validation:
  - `cd neurotrace/services/biograph_api && uv run pytest -q tests`
- Dashboard validation:
  - `cd neurotrace/apps/dashboard && npm run typecheck`
  - `cd neurotrace/apps/dashboard && npm run lint`
  - `cd neurotrace/apps/dashboard && npm run test:unit`
  - `cd neurotrace/apps/dashboard && npm run test:e2e`
- End-to-end validation:
  - `cd neurotrace/apps/watchlab && npm test -- --runInBand`
  - `cd neurotrace/apps/watchlab && npm run test:e2e`
  - `cd neurotrace/services/extractor_worker && uv run pytest -q biotrace_extractor_tests`
  - `cd neurotrace/ml/training && uv run pytest -q tests`

## known issues
- Watchlab currently supports direct canonical trace-row upload (`traceRows`) and synthetic fallback for demo continuity when traces are not provided.
- Deprecated ingest aliases (`dopamine`, `t_ms`) are intentionally retained for backward compatibility and should be sunset in a planned API version.
- The repository keeps both TypeScript and transpiled `.js` mirrors in dashboard/watchlab; maintainers must update both or automate generation to avoid drift.
- Some non-blocking warnings remain in tooling output (for example, Alembic `path_separator` deprecation warning).
