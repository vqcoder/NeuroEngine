# biograph_api

FastAPI service with Postgres-backed study/session trace ingestion, post-view marker annotations, playback telemetry, and video summary analytics.
`trace_points` supports AU/blink signals, capture-quality metrics, coarse gaze proxies, and optional `dial` values for calibration overlays.
The calibrated engagement field is `reward_proxy` (`dopamine` is accepted only as a deprecated ingest alias for backward compatibility).

Capability boundaries:

- `reward_proxy` and `attention` outputs are proxies and quality-dependent estimates.
- Gaze values are coarse webcam-based on-screen proxies, not precise fixation maps or research-grade eye tracking.

## Readout Guardian

`build_video_readout` runs a guardian check before computing attention/reward traces.
The guardian enforces:

- algorithm fingerprint match against an approved baseline
- deterministic golden-case outputs for attention and reward decomposition
- design invariants (attention AU-invariance, quality weighting, reward novelty/label response)

Baseline file:

- `app/readout_guardian_baseline.json`

Validate manually:

```bash
uv run python -m app.readout_guardian --print-report
```

Update baseline only from approved learning runs:

```bash
uv run python -m app.readout_guardian \
  --update-baseline \
  --training-metadata ../../ml/training/approved_runs/<run-id>.json
```

Optional env toggles:

- `READOUT_GUARDIAN_ENABLED` (`true` by default)
- `READOUT_GUARDIAN_BASELINE_PATH` (override baseline file path)

Baseline refresh metadata requirements:

- metadata files are stored under `ml/training/approved_runs/<run_id>.json`
- metadata must be `approved` and set `guardian.allow_baseline_refresh=true`
- operations runbook: `docs/readout_guardian_ops.md`

## Endpoints

- `POST /studies`
- `GET /videos` (analyst catalog: videos + recording/session metadata)
- `POST /videos`
- `POST /sessions`
- `POST /sessions/{id}/trace` (bulk JSONL ingestion)
- `POST /sessions/{id}/annotations` (timestamped marker ingestion)
- `POST /sessions/{id}/telemetry` (passive playback telemetry events)
- `POST /sessions/{id}/captures` (persist compressed webcam capture payload for model-refinement workflows)
- `POST /sessions/{id}/survey`
- `GET /videos/{id}/summary`
- `GET /videos/{id}/readout` (scene-aligned session or aggregated multi-viewer readout)
- `GET /videos/{id}/readout/export-package` (CSV + JSON + compact report export payload)
- `POST /videos/{id}/timeline-analysis` (idempotent timeline/feature extraction job)
- `GET /timeline-analysis/{analysis_id}` (timeline analysis job status)
- `GET /timeline-features/{asset_id}` (windowed timeline/feature query for downstream scoring modules)
- `GET /observability/neuro` (runtime drift/fallback/missing-signal/confidence summary for neuro-score stack)
- `GET /observability/capture-archives` (capture ingest success/failure and storage footprint summary)
- `POST /observability/frontend-diagnostics/events` (ingest structured frontend failures/recoveries from Study/Readout/Predictor surfaces)
- `GET /observability/frontend-diagnostics/events` (list recent frontend diagnostics events with surface/page/severity filters)
- `GET /observability/frontend-diagnostics/summary` (windowed frontend diagnostics status + top failure signatures)
- `POST /maintenance/capture-archives/purge` (retention purge executor; `dry_run=true` by default)
- `POST /calibration/synthetic-lift/experiments` (persist completed GeoX/holdout experiments and optionally apply calibration reconciliation)
- `GET /calibration/synthetic-lift/status` (calibration state + pending experiment observability)
- `POST /predict` (upload video file and return predicted traces)
- `GET /testing-queue` (active-learning queue for assigning next study/video segment)

Canonical timebase notes:

- `video_time_ms` is the canonical playback coordinate across telemetry and trace ingest.
- Telemetry events without `video_time_ms` are rejected.
- Trace rows that omit `video_time_ms` but provide legacy `t_ms` are ingested with normalized `video_time_ms` and reported via `flagged_missing_video_time_ms` in the trace ingest response.
- Legacy reward aliases (`dopamine`, `dopamine_score`, `dopamineScore`) are normalized to `reward_proxy` when `reward_proxy` is absent.
- `STRICT_CANONICAL_TRACE_FIELDS=true` rejects alias-only trace rows (`t_ms` without `video_time_ms`, or legacy reward aliases without `reward_proxy`) with explicit 422 details.
- Upload/ingest can persist trace provenance through playback telemetry (`event_type=trace_source` with `details.trace_source`), surfaced in `quality.session_quality_summary.trace_source`.
- Readout quality thresholds are loaded from shared config: `packages/common/quality_thresholds.json` (override via `QUALITY_THRESHOLDS_PATH`).
- Product rollup presentation layer can be tier/mode resolved with optional readout query params:
  - `product_mode` / `productMode`: `creator` | `enterprise`
  - `workspace_tier` / `workspaceTier`: workspace/account tier hint for mode gating

## Local run

```bash
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker compose up --build
```

Cloud notes:

- Service binds to `${PORT}` automatically in Docker.
- Set `CORS_ALLOW_ORIGINS` for dashboard/watchlab origins.
- `DATABASE_URL` accepts `postgres://` and `postgresql://` formats.
- `TIMELINE_ANALYSIS_RETENTION_LIMIT` controls completed-analysis history kept per asset/version (default `5`).
- `TIMELINE_ASR_PROVIDER` supports `metadata` (default) or `whisper_cli` when local Whisper CLI is installed.
- `TIMELINE_OCR_PROVIDER` supports `metadata` (default) or `tesseract_cli` when local Tesseract is installed.
- `STRICT_CANONICAL_TRACE_FIELDS` defaults to `false`; set `true` to enforce canonical trace fields during alias sunset.
- `BOUNDARY_ENCODING_CONFIG_JSON` optionally overrides boundary-encoding timing/overload heuristics globally (JSON object).
- Product rollup mode config:
  - `PRODUCT_ROLLUPS_ENABLED` (`true` by default)
  - `PRODUCT_ROLLUP_DEFAULT_TIER` (`creator` by default)
  - `PRODUCT_ROLLUP_TIER_MODES_JSON` (tier-to-mode policy overrides as JSON)
- Neuro taxonomy feature flag:
  - `NEURO_SCORE_TAXONOMY_ENABLED` (`true` by default; disables `neuro_scores` + `product_rollups` composition when set `false`)
- Neuro-score observability config:
  - `NEURO_OBSERVABILITY_ENABLED` (`true` by default)
  - `NEURO_OBSERVABILITY_HISTORY_PATH` (optional JSONL path for drift history snapshots)
  - `NEURO_OBSERVABILITY_HISTORY_MAX_ENTRIES` (`500` by default)
  - `NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD` (`12.0` by default, absolute score delta)
- Webcam capture archive config:
  - `WEBCAM_CAPTURE_ARCHIVE_ENABLED` (`true` by default; disables `/sessions/{id}/captures` when `false`)
  - `WEBCAM_CAPTURE_ARCHIVE_MAX_FRAMES` (`240` by default; maximum raw frame objects accepted per upload)
  - `WEBCAM_CAPTURE_ARCHIVE_MAX_PAYLOAD_BYTES` (`5242880` by default; maximum serialized payload bytes before compression)
  - `WEBCAM_CAPTURE_ARCHIVE_RETENTION_DAYS` (`30` by default)
  - `WEBCAM_CAPTURE_ARCHIVE_PURGE_ENABLED` (`true` by default)
  - `WEBCAM_CAPTURE_ARCHIVE_PURGE_BATCH_SIZE` (`500` by default)
  - `WEBCAM_CAPTURE_ARCHIVE_OBSERVABILITY_WINDOW_HOURS` (`24` by default)
  - `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE` (`none` or `fernet`; default `none`)
  - `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_KEY` (required when mode is `fernet`; Fernet key string)
  - `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_KEY_ID` (optional key identifier for audit metadata)
  - note: `fernet` mode requires Python `cryptography` to be installed in the runtime image

## Integration tests

```bash
pytest -q
```

Tests create a temporary database schema, run Alembic migration checks, and validate end-to-end ingest + summary aggregation.
Set `TEST_DATABASE_URL` to run tests against Postgres instead of SQLite fallback.

## Neuro Eval Harness

Offline known-good vs known-bad creative checks plus drift/fallback/confidence summaries:

```bash
cd /Users/johnkim/Documents/neurotrace/services/biograph_api
uv run python -m app.neuro_eval_runner
```

Write a summary artifact:

```bash
cd /Users/johnkim/Documents/neurotrace/services/biograph_api
uv run python -m app.neuro_eval_runner \
  --output /Users/johnkim/Documents/neurotrace/fixtures/neuro_eval_summary.sample.json
```

## Prediction endpoint

`POST /predict` accepts either:

- multipart video upload (`file` field), or
- form field `video_url` (`http://` or `https://`) so the API downloads the video before inference.
  `video_url` can be either:
  - direct video file URL (`.mp4`, `.mov`, `.webm`), or
  - webpage URL that embeds a video. For webpages, the API resolves sources from OpenGraph video tags,
    `<video>/<source>` tags, and JSON-LD `VideoObject` metadata.

It loads the model artifact from `MODEL_ARTIFACT_PATH` and calls `ml_pipeline` inference.
Install the training package first:

```bash
pip install -e ../../ml/training
```

## Testing queue endpoint

`GET /testing-queue` builds a prioritized queue across pending videos using:

- per-second uncertainty from model inference
- segment impact score = `uncertainty * early_hook_weight`
- early-hook weighting (higher priority for earlier segments)

Useful query params:

- `queue_size` (default `10`)
- `target_sessions_per_video` (default `3`)
- `segment_length_sec` (default `6`)
- `per_video_segments` (default `3`)
- `early_hook_half_life_sec` (default `20`)
# Triggered by dependency upgrade PR
