# Remaining Work Queue (Prioritized)

_Last refreshed: 2026-03-08_

## Completed in this pass
- Prompt 1: Added canonical `traceRows` passthrough in watchlab upload; synthetic traces now run only as fallback.
- Prompt 2: Added extractor output canonical `video_time_ms` field while retaining legacy `t_ms`.
- Prompt 3: Removed recurring Next.js workspace-root warning by setting `outputFileTracingRoot`.
- Prompt 4: Updated stale status/audit docs to reflect implemented readout stack and current risks.
- Prompt 5: Added `STRICT_CANONICAL_TRACE_FIELDS` guardrail; strict mode now rejects alias-only `dopamine*` and `t_ms` ingest rows.
- Prompt 6: Added dashboard Reward Anticipation diagnostics card with pathway, confidence, timeline windows, warnings, and jump actions.
- Prompt 7: Added dashboard JS mirror sync/check workflow so TS is canonical and mirrored JS artifacts are validated in lint/typecheck/unit scripts.
- Prompt 8: Trace-source observability added end-to-end (`trace_source` telemetry event, readout quality summary field, dashboard badge, backend + dashboard tests).
- Prompt 9: Centralized extractor/readout quality thresholds in shared config (`packages/common/quality_thresholds.json`) with loader tests in both services.
- Prompt 10: Extended shared-contract checks to assert new `social_transmission` and `self_relevance` aggregate contract diagnostics across Pydantic and Zod fixture validation.
- Prompt 11: Implemented `CTA Reception Score` multi-signal diagnostics, aggregate/schema integration, taxonomy consumption, fixture/docs updates, and scenario tests (peak-overlap vs post-drop-off).

## P0 (next to execute)

### Prompt P0.1: make extractor-backed traces the default path for non-demo sessions
- Status: completed.

### Prompt P0.2: add trace-source observability
- Status: completed.

## P1 (stability and governance)

### Prompt P1.1: deprecation sunset controls for legacy ingest aliases
- Status: completed.

### Prompt P1.2: eliminate TS/JS mirror drift in dashboard/watchlab
- Status: completed.
- Note: watchlab remains TS-only for source artifacts; no mirrored JS track exists there, so no mirror-check step required.

## P2 (quality of life)

### Prompt P2.1: centralize quality/confidence threshold config
- Status: completed.

## Open Items
- None. The prioritized queue is currently complete.

## Validation Snapshot (2026-03-08)
- `services/biograph_api`: `uv run pytest` (103 passed, 1 warning).
- `services/biograph_api` targeted CTA/taxonomy/readout tests:
  - `uv run pytest tests/test_cta_reception.py tests/test_neuro_score_taxonomy.py tests/test_readout_payload_schema.py tests/test_readout_aggregate_synchrony.py tests/test_readout_endpoint.py` (27 passed).
- `services/extractor_worker`: `uv run python -m pytest` (17 passed).
- `apps/dashboard`: `npm run typecheck`, `npm run lint`, `npm run test:unit`, `npm run test:e2e` (14 e2e passed).
- `apps/watchlab`: `npm test -- --runInBand`, `npm run build` (6 test suites passed; build succeeded).
- `ml/training`: `uv run python -m pytest` (10 passed).
