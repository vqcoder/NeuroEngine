# Readout Dashboard Spec

## Goals
- Provide an editor-facing dashboard for scene-level diagnosis of viewer response using passive and explicit signals.
- Keep playback, traces, and labels synchronized on `video_time_ms`.
- Surface confidence and capture-quality context next to webcam-derived signals.
- Support scene-aware analysis using `scene_id`, `cut_id`, and `cta_id` where available.
- Standardize naming around `reward_proxy` and avoid direct dopamine claims.

## Non-goals
- Do not claim direct dopamine measurement.
- Do not claim precise eye tracking, fixation maps, microsaccades, or research-grade pupilometry from laptop webcams.
- Do not introduce a mandatory live reaction tapping workflow for first-pass viewing.
- Do not move business-critical aggregation logic from backend to frontend when summary services already exist.

## Metrics

All metric series are keyed by `video_time_ms` and should include confidence/quality context where relevant.

### attention_score
- Description: calibrated attention proxy score on a normalized 0-100 scale.
- Type: float.
- Source: backend summary from passive traces and aligned labels.

### attention_velocity
- Description: first derivative of `attention_score` over time (rate of change).
- Type: float.
- Source: backend-derived per bucket/window.

### attention_gain_segments
- Description: contiguous intervals where attention is rising beyond configured thresholds.
- Type: list of intervals with `{start_video_time_ms, end_video_time_ms, strength}`.
- Source: backend segmentation logic.

### attention_loss_segments
- Description: contiguous intervals where attention is dropping beyond configured thresholds.
- Type: list of intervals with `{start_video_time_ms, end_video_time_ms, severity}`.
- Source: backend segmentation logic.

### blink_rate
- Description: rolling blink frequency estimate.
- Type: float.
- Source: extractor + backend aggregation.

### blink_inhibition
- Description: baseline-relative suppression score/window indicator.
- Type: float (and optional boolean active flag).
- Source: extractor baseline normalization and backend aggregation.

### reward_proxy
- Description: calibrated engagement proxy target/output derived from multiple signals and labels.
- Type: float.
- Source: ML/summary pipeline.
- Naming: canonical field is `reward_proxy`; avoid introducing alternative dopamine-like names.

### tracking_confidence
- Description: confidence that webcam-derived signals are reliable at each time point/window.
- Type: float in [0,1].
- Source: fused face/landmark/head-pose/gaze/capture-quality confidence.

### session_quality
- Description: aggregate quality score for session usability.
- Type: float in [0,1] (or 0-100 if normalized consistently).
- Source: quality metrics such as brightness, blur, fps stability, face visibility, occlusion, and head-pose validity.

## API contracts

## Read contract (dashboard)
- Endpoint: `GET /videos/{id}/summary`
- Required dashboard payload sections:
  - `trace_buckets`: time-series buckets aligned to `video_time_ms`, including `attention_score`, `attention_velocity` (if available), `blink_rate`, `blink_inhibition`, AU traces, `reward_proxy`, and quality/confidence fields.
  - `scene_metrics`: scene-level rollups and boundaries with optional `scene_id`, `cut_id`, `cta_id`.
  - `annotations`: explicit post-view markers with marker type and timestamp.
  - `playback_telemetry`: passive telemetry events aligned to `video_time_ms`.
  - `qc_stats`: session-level quality summary.

## Export contract
- CSV export:
  - per-time-row metrics including `video_time_ms`, scene IDs (if present), key traces, confidence, and quality fields.
- JSON export:
  - scene summary, explicit labels, and quality overlays suitable for downstream editing workflows.

## Naming and compatibility rules
- External/public contract uses `reward_proxy`.
- If legacy ingest accepts `dopamine`, it must be explicitly documented as a deprecated alias mapped server-side.

## UI requirements
- Keep existing video + timeline workflow.
- Timeline layers include:
  - `attention_score`
  - `attention_velocity` (if available)
  - `blink_rate`
  - `blink_inhibition`
  - AU traces currently supported
  - `reward_proxy`
  - annotation markers
  - scene boundaries
  - CTA markers where available
- Chart interactions:
  - clicking trace points or markers seeks the player.
- Quality UX:
  - show low-confidence/quality badges and overlays.
- Interpretation copy:
  - if showing gaze, explicitly label it as coarse webcam proxy.
  - use `Reward Proxy` wording in UI and describe it as a quality-dependent estimate.

## Acceptance criteria
- All dashboard traces and events render against `video_time_ms`.
- Scene-aware overlays (`scene_id`, `cut_id`, `cta_id`) appear when available.
- Quality/confidence overlays display for webcam-derived signals.
- Metric naming is normalized to `reward_proxy`; no direct dopamine-measurement claims in UI/docs/contracts.
- Dashboard can query and render explicit post-view annotation markers.
- Exported CSV/JSON include core metrics, labels, quality fields, and IDs where available.
