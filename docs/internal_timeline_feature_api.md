# Internal Timeline Feature API

This document describes the reusable timeline/feature pipeline used by downstream AlphaEngine score modules.

## Purpose

The timeline feature store converts one source video asset into reusable timeline segments and feature tracks so scoring modules can query by `asset_id` and time window instead of recomputing media features per score.

The outputs are diagnostic proxies and claim-safe heuristics, not direct neuroscience truth measures.

## Persistence model

`services/biograph_api/app/models.py` defines:

- `VideoTimelineAnalysis` (`video_timeline_analyses`)
- `VideoTimelineSegment` (`video_timeline_segments`)
- `VideoFeatureTrack` (`video_feature_tracks`)

Each analysis run is keyed by:

- `video_id`
- `analysis_version`
- `asset_fingerprint` (SHA-256 of source media bytes)

This supports idempotency and resumability:

- If the same fingerprint/version already completed, the job returns cached analysis metadata.
- If `force_recompute=true`, existing rows for that analysis are replaced.

## Job entrypoint

Python service function:

- `app.timeline_feature_store.run_timeline_analysis_job(db, video_id, request)`

HTTP endpoint:

- `POST /videos/{id}/timeline-analysis`

Request fields:

- `source_ref` (optional local path or `http(s)` URL)
- `analysis_version` (default `timeline_v1`)
- `force_recompute` (default `false`)
- `run_async` (default `false`; background execution with immediate job state response)
- `sample_interval_ms` (default `1000`)
- `scene_threshold` (default `0.35`)

Status endpoint:

- `GET /timeline-analysis/{analysis_id}`

## Windowed query API

Python service function:

- `app.timeline_feature_store.query_timeline_features_window(...)`

HTTP endpoint:

- `GET /timeline-features/{asset_id}`

Query params:

- `start_ms`
- `end_ms` (optional, defaults to analysis duration)
- `analysis_version` (default `timeline_v1`)
- repeated `track_name` filters (optional)
- repeated `segment_type` filters (optional)

Response includes:

- analysis identity/version metadata
- timeline `segments`
- reusable `feature_tracks`

## Segment/track coverage

Current extraction includes:

- sampled frame segments and keyframes
- shot boundaries and shot windows
- scene blocks (scene graph when available, heuristic fallback otherwise)
- CTA windows
- audio events and audio intensity
- speech/text overlay windows only when transcript/OCR payloads already exist in video metadata
- optional CLI providers:
  - ASR: `TIMELINE_ASR_PROVIDER=whisper_cli` (requires local Whisper CLI)
  - OCR: `TIMELINE_OCR_PROVIDER=tesseract_cli` (requires local Tesseract)
- feature tracks for cut cadence, shot duration distribution, luminance/color deltas, camera-motion proxy class, face presence/count proxy, primary-subject persistence proxy, object salience candidates, and audio intensity

Retention:

- completed analyses are automatically pruned per `video_id + asset_id + analysis_version`
- keep count is controlled by `TIMELINE_ANALYSIS_RETENTION_LIMIT` (default `5`)

## Downstream usage pattern

Score modules should:

1. Trigger timeline analysis once per source asset/fingerprint.
2. Query feature windows by `asset_id` and scoring window boundaries.
3. Reuse stored feature tracks unless source media fingerprint changes.
