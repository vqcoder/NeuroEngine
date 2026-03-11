# Integration Upgrade Plan

_Audit date: 2026-03-06_

## Refresh snapshot (2026-03-06, post-implementation)
- Implemented since the initial audit:
  - `GET /videos/{video_id}/readout` returns versioned `ReadoutPayload` with scene/cut/CTA context, derived traces, diagnostics, exports, and aggregate synchrony fields.
  - Watchlab forwards playback telemetry, annotations, and survey data to backend ingestion endpoints.
  - Dashboard renders readout layers/overlays/diagnostics and exports directly from `ReadoutPayload`.
  - Reward decomposition traces (`valence_proxy`, `arousal_proxy`, `novelty_proxy`) and aggregate synchrony (`attention_synchrony`, `blink_synchrony`) are available in backend + dashboard.
  - Watchlab upload now accepts canonical `traceRows` and only uses synthetic fallback rows when traces are absent.
- Remaining high-priority integration work:
  - Replace synthetic fallback trace generation in production study runs with extractor-backed trace upload by default.
  - Sunset deprecated ingest aliases (`dopamine`, `t_ms`) after downstream clients are migrated.
  - Automate TS/JS mirror generation (or remove checked-in transpiled mirrors) to avoid maintenance drift.

## Scope and constraints
- Goal: integrate the 10 requested upgrades into the existing NeuroTrace stack without adding parallel systems.
- Constraint: extend current paths (`watchlab` -> `biograph_api` -> `dashboard` -> `ml`) and keep backward compatibility where practical.
- Canonical timeline key remains `video_time_ms` across ingestion, storage, analytics, and rendering.

## Current state audit

### Frontend study player (`watchlab`)
- Primary module: `apps/watchlab/app/study/[studyId]/study-client.tsx`
  - Already uses staged flow: consent -> camera -> watch -> annotation -> survey.
  - Already emits timeline events with `videoTimeMs`, `clientMonotonicMs`, `wallTimeMs`.
  - Already captures telemetry event types for play/pause/seek/rewind/mute/fullscreen/visibility/focus/incomplete session.
- Upload path: `apps/watchlab/app/api/upload/route.ts`
  - Validates payload via Zod.
  - Currently forwards traces/annotations/survey to backend.
  - Gap: timeline telemetry is not yet forwarded to `POST /sessions/{id}/telemetry`.
  - Gap: trace ingest is placeholder synthesis (`apps/watchlab/lib/helloTrace.ts`) rather than quality/confidence-rich passive rows from extractor output.

### Backend ingestion/schema (`biograph_api`)
- Endpoint and orchestration: `services/biograph_api/app/main.py`
  - Already exposes `POST /sessions/{id}/trace`, `/annotations`, `/telemetry`, `/survey`.
  - Already exposes `GET /videos/{id}/readout` and `/readout/export-package`.
- Schema and models:
  - `services/biograph_api/app/models.py`
  - `services/biograph_api/app/schemas.py`
  - Existing `trace_points` already includes `video_time_ms`, scene/cut/cta IDs, quality/confidence, and `reward_proxy`.
  - Existing `session_playback_events` already includes `video_time_ms`, wall and monotonic clocks.
  - Existing backward compatibility map from `dopamine` -> `reward_proxy` in `parse_trace_jsonl`.
- Readout/trace computation:
  - `services/biograph_api/app/services.py`
  - `services/biograph_api/app/readout_metrics.py`
  - Already computes: `attention_score`, `attention_velocity`, `blink_rate`, `blink_inhibition`, `reward_proxy`, `tracking_confidence`, gain/loss segments, diagnostics.
  - Gaps:
    - No decomposition channels (`valence_proxy`, `arousal_proxy`, `novelty_proxy`).
    - No aggregate synchrony metrics or CI bands in readout payload.
    - Scene graph is currently derived from `videos.scene_boundaries` JSON; no normalized `scenes/cuts/cta_markers` tables.

### Extraction pipeline (`extractor_worker`)
- Core modules:
  - `services/extractor_worker/biotrace_extractor/extractor.py`
  - `services/extractor_worker/biotrace_extractor/quality.py`
  - `services/extractor_worker/biotrace_extractor/rolling.py`
  - `services/extractor_worker/biotrace_extractor/schemas.py`
- Already emits quality/confidence-rich passive signals and blink baseline/inhibition metrics.
- Gap:
  - Output rows are keyed by `t_ms`; alignment to `video_time_ms` is implicit. Canonical naming should be explicit end-to-end.

### Dashboard (`biotrace_dashboard`)
- Core modules:
  - `apps/dashboard/src/api.ts`
  - `apps/dashboard/src/types.ts`
  - `apps/dashboard/src/utils/readout.ts`
  - `apps/dashboard/src/components/SummaryChart.tsx`
  - `apps/dashboard/src/pages/VideoDashboardPage.tsx`
- Already renders readout traces, segments, scene/cut/cta overlays, low-confidence windows, annotations, and exports.
- Gap:
  - No render layers for reward decomposition (`valence_proxy`, `arousal_proxy`, `novelty_proxy`).
  - No aggregate synchrony/CI band rendering.
  - No explicit `ReadoutPayload` contract type shared from backend/common package (typed similarly but not canonicalized across all layers).

### Existing training/feature computation
- Core modules:
  - `ml/training/ml_pipeline/dataset.py`
  - `ml/training/ml_pipeline/model.py`
  - `ml/training/ml_pipeline/infer.py`
- Already uses `reward_proxy` as primary target and `attention` as compatibility alias.
- Gap:
  - No explicit modeling/outputs for `valence_proxy`, `arousal_proxy`, `novelty_proxy`.
  - No synchrony metrics export for aggregate readout analytics.

## Affected modules/files

### Watchlab
- `apps/watchlab/app/study/[studyId]/study-client.tsx`
- `apps/watchlab/lib/schema.ts`
- `apps/watchlab/app/api/upload/route.ts`
- `apps/watchlab/lib/helloTrace.ts` (deprecate placeholder path behind explicit dev flag)
- `packages/common/zod/sessionBundle.ts`
- `packages/common/pydantic/session_bundle.py`

### Backend API + DB
- `services/biograph_api/alembic/versions/*` (new migration(s))
- `services/biograph_api/app/models.py`
- `services/biograph_api/app/schemas.py`
- `services/biograph_api/app/services.py`
- `services/biograph_api/app/readout_metrics.py`
- `services/biograph_api/app/main.py`

### Extractor
- `services/extractor_worker/biotrace_extractor/schemas.py`
- `services/extractor_worker/biotrace_extractor/extractor.py`
- `services/extractor_worker/biotrace_extractor/cli.py` (if output contract changed)

### Dashboard
- `apps/dashboard/src/types.ts`
- `apps/dashboard/src/api.ts`
- `apps/dashboard/src/utils/readout.ts`
- `apps/dashboard/src/components/SummaryChart.tsx`
- `apps/dashboard/src/pages/VideoDashboardPage.tsx`
- `apps/dashboard/src/utils/exporters.ts`

### Docs
- `docs/SPEC.md`
- `docs/DATA_DICTIONARY.md`
- `docs/PRIVACY.md`
- `apps/watchlab/README.md`
- `apps/dashboard/README.md`
- `services/biograph_api/README.md`

## Migration plan (exact integration steps)

### Phase 0: Contract freeze and compatibility strategy
1. Define canonical `ReadoutPayload` schema in backend (`schemas.py`) and mirror it in `packages/common` (Zod + Pydantic).
2. Keep `/videos/{id}/summary` as compatibility endpoint; mark it deprecated in docs and build from existing readout service to avoid duplicate logic.
3. Keep `dopamine` accepted only as deprecated ingest alias mapped to `reward_proxy` until sunset.

### Phase 1: Canonical timebase hardening (`video_time_ms`)
1. Enforce `video_time_ms` presence for all trace/event ingest models (trace rows, playback telemetry, annotations).
2. Keep `t_ms` as compatibility alias in trace ingest; map to `video_time_ms` when needed.
3. Update extractor output schema to include `video_time_ms` (while retaining `t_ms` alias for compatibility).
4. Add migration indexes where missing for `video_time_ms` lookup-heavy paths.

### Phase 2: Scene graph layer with stable IDs
1. Add normalized tables:
   - `video_scenes` (`id`, `video_id`, `scene_id`, `start_ms`, `end_ms`, `label`, order index)
   - `video_cuts` (`id`, `video_id`, `cut_id`, `scene_id`, `start_ms`, `end_ms`, `label`)
   - `video_cta_markers` (`id`, `video_id`, `cta_id`, `video_time_ms`, optional scene/cut linkage, label)
2. Backfill from existing `videos.scene_boundaries` JSON on migration.
3. Keep `videos.scene_boundaries` as compatibility read/write shim short-term.
4. Update alignment helpers (`_resolve_scene_alignment`) to prefer normalized tables, fallback to legacy JSON during transition.

### Phase 3: Study flow and telemetry wiring (existing flow, no parallel player)
1. Keep current `study-client.tsx` staged flow as canonical.
2. Update upload route to forward `eventTimeline` to backend `/sessions/{id}/telemetry` (currently missing).
3. Ensure telemetry event type taxonomy is unified in shared schema (`packages/common` + watchlab zod + backend enums/validators).
4. Add explicit abandonment telemetry (`pagehide`, early exit) with consistent details payload.

### Phase 4: Quality + confidence ubiquity
1. Ensure all passive trace rows persist:
   - brightness, blur, fps stability, face_visible_pct, occlusion_score, head_pose_valid_pct
   - confidence fields for face/gaze/blink/AU/quality.
2. Ensure readout response exposes these as:
   - per-timepoint overlays
   - aggregate quality summary
   - confidence windows for visualization.
3. Replace placeholder trace generation path with extractor-based ingestion for non-demo flows.

### Phase 5: Reward decomposition extension
1. Add new optional trace fields in DB + schemas:
   - `valence_proxy`
   - `arousal_proxy`
   - `novelty_proxy`
2. Extend readout trace channels and export payloads to include the above.
3. Compute decomposition in backend metric service (`readout_metrics.py`) from existing passive/explicit signals.
4. Preserve `reward_proxy` as top-level composite and compatibility `attention` alias only where required.

### Phase 6: Aggregate synchrony + CI bands
1. In aggregate mode, compute per-bucket cross-session synchrony:
   - `attention_synchrony` (e.g., normalized inter-session similarity / inverse dispersion)
   - `blink_synchrony` (event-rate or correlation-based synchrony)
2. Compute confidence intervals (e.g., bootstrap or standard error bands) per trace in aggregate mode.
3. Add to `ReadoutPayload`:
   - `aggregate_metrics.synchrony`
   - `aggregate_metrics.ci_bands` keyed by trace channel.

### Phase 7: Single canonical ReadoutPayload endpoint
1. Keep `GET /videos/{id}/readout` as canonical endpoint.
2. Expand response schema to include:
   - existing traces/segments/diagnostics
   - decomposition traces
   - synchrony + CI bands
   - scene/cut/cta graph objects with stable IDs.
3. Keep `/readout/export-package` generated directly from canonical readout object to avoid drift.

### Phase 8: Dashboard upgrade (existing page, no parallel dashboard)
1. Extend `types.ts`, `api.ts`, `mapReadoutToTimeline` to consume new fields.
2. Add layer toggles and chart lines for:
   - `valence_proxy`, `arousal_proxy`, `novelty_proxy`
   - synchrony overlays and CI shading in aggregate mode.
3. Keep existing gain/loss/diagnostic cards but add decomposition summaries where useful.
4. Extend CSV/JSON exports to include new decomposition and aggregate metrics.

### Phase 9: ML/feature pipeline alignment
1. Extend dataset assembly to output decomposition targets/features.
2. Keep reward proxy as primary target; add decomposition targets as optional heads.
3. Maintain backward-compatible prediction contract with `reward_proxy` + legacy alias.

## Schema/API changes

### Database schema changes
- New tables:
  - `video_scenes`
  - `video_cuts`
  - `video_cta_markers`
- `trace_points` additions:
  - `valence_proxy` FLOAT NULL
  - `arousal_proxy` FLOAT NULL
  - `novelty_proxy` FLOAT NULL
- Indexes:
  - `(video_id, start_ms/end_ms)` on scene/cut tables
  - `(video_id, video_time_ms)` on CTA and traces (if not present)

### API contract changes
- `GET /videos/{id}/readout`
  - Add `traces.valence_proxy[]`, `traces.arousal_proxy[]`, `traces.novelty_proxy[]`
  - Add `aggregate_metrics` with synchrony and CI bands (aggregate mode only)
  - Source scene graph from normalized scene/cut/cta tables
- `GET /videos/{id}/summary`
  - Mark deprecated; internally map from readout builder to avoid dual logic
- `POST /sessions/{id}/trace`
  - Continue accepting legacy `t_ms` and `dopamine`, map to canonical fields
  - Prefer `video_time_ms` + `reward_proxy`

## UI changes

### Watchlab
- Keep current staged flow and privacy copy.
- Ensure telemetry is posted to backend as first-class ingestion.
- Keep continuous dial non-default; only annotation/calibration contexts via existing flag.

### Dashboard
- Reuse `VideoDashboardPage` and `SummaryChart`:
  - Add decomposition layers and legend.
  - Add aggregate synchrony widgets and CI-band shading.
  - Keep scene/cut/cta overlays and click-to-seek behavior.
- Keep proxy language explicit:
  - Reward/decomposition are estimates.
  - Gaze remains coarse webcam proxy.

## Test plan

### Backend
- Extend integration tests:
  - `tests/test_readout_endpoint.py`
  - `tests/test_readout_dashboard_regression.py`
  - new tests for scene graph normalized tables and backfill.
- Add migration tests:
  - verify backfill from `scene_boundaries` JSON to scene/cut/cta tables
  - verify legacy `dopamine` and `t_ms` alias mapping.
- Add aggregate metrics tests:
  - synchrony metrics determinism with synthetic fixture
  - CI band shape/ordering and bounds.

### Watchlab
- Extend Playwright:
  - ensure telemetry events are emitted and forwarded to `/sessions/{id}/telemetry`
  - verify `videoTimeMs` monotonic behavior through play/seek/rewind.
- Extend Jest schema tests for canonical timeline/event contract in `lib/schema.ts`.

### Extractor
- Extend extractor tests to assert explicit `video_time_ms` compatibility output and unchanged quality/confidence semantics.

### Dashboard
- Extend e2e in `apps/dashboard/e2e/dashboard.spec.ts`:
  - decomposition layer rendering/toggles
  - aggregate synchrony + CI rendering
  - exports include decomposition/synchrony fields.

### ML
- Extend unit tests:
  - target naming and decomposition target assembly
  - backward compatibility for `reward_proxy`/`attention` aliases.

## Rollout strategy (no parallel systems)

### Feature flags / staged rollout
- `READOUT_V2_ENABLED` (backend): enables expanded ReadoutPayload fields.
- `SCENE_GRAPH_TABLES_ENABLED` (backend): use normalized scene graph tables; fallback to legacy JSON when off.
- `WATCHLAB_FORWARD_TELEMETRY_ENABLED` (watchlab): enables telemetry forwarding call.
- `DASHBOARD_READOUT_V2_ENABLED` (dashboard): shows decomposition/synchrony layers when payload supports them.

### Rollout sequence
1. Deploy DB migration with backfill + backward-compatible model/schema support.
2. Deploy backend readout/service updates behind flags.
3. Enable telemetry forwarding in watchlab.
4. Deploy dashboard consuming optional new fields (guarded).
5. Enable backend flags progressively; monitor readout parity and latency.
6. Deprecate old pathways (`/summary` and legacy scene JSON writes) after verification window.

### Backward compatibility rules
- Accept old ingest fields (`dopamine`, `t_ms`) while writing canonical fields.
- Keep existing clients functional if decomposition/synchrony fields are absent.
- Maintain export package contract; append new fields without removing existing required keys.

## Risks and mitigations
- Risk: schema drift between watchlab/common/backend contracts.
  - Mitigation: source-of-truth schemas in `packages/common`; conformance tests in each service.
- Risk: scene graph dual-source inconsistency during migration.
  - Mitigation: one-way backfill + write-through adapter; deprecate legacy JSON writes on schedule.
- Risk: aggregate synchrony cost at scale.
  - Mitigation: pre-bucketed aggregation and optional caching for aggregate readout queries.
- Risk: dashboard complexity from added layers.
  - Mitigation: default layer presets and lazy toggles; keep expensive computation server-side.
