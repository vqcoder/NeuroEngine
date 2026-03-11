# SPEC

## Objective

NeuroTrace captures synchronized viewing signals (attention/reward proxies, blink dynamics, AU traces, quality/confidence metrics, and survey/annotation labels) and turns them into actionable editorial recommendations.

## Components

- `watchlab`: consented study playback + trace capture.
- `biograph_api`: ingest, aggregate, and serve summaries/predictions.
- `extractor_worker`: frame-level biometric extraction and normalization.
- `dashboard`: visualization, QC, and export workflows.
- `ml/training` and `ml/inference`: model lifecycle and active-learning support.
- `optimizer` (under `ml/inference`): heuristic edit suggestion generation.

## Measurement boundaries

- `reward_proxy` is a calibrated engagement proxy, not a direct dopamine measurement.
- Gaze output is a coarse on-screen webcam proxy, not precise fixation mapping or research-grade eye tracking.
- Face/AU/blink traces are model signals with confidence and quality context; they are not definitive emotion truth labels in isolation.

## Core flows

1. Participant completes a passive-first study session in `watchlab`:
   - consent
   - camera quality check
   - passive first playback
   - post-view timeline annotation
   - short survey
2. `watchlab` emits playback telemetry + labels aligned to `video_time_ms`.
3. `biograph_api` ingests traces, telemetry, annotation markers, and survey responses.
4. Worker extraction enriches sessions with per-frame/per-second passive signals + quality/confidence.
5. Dashboard loads `GET /videos/{id}/summary` for scene-level diagnostics.
6. ML predicts trace proxies for unlabeled videos and prioritizes testing queue.
7. Optimizer proposes edit suggestions with predicted engagement deltas.

## Data ingress map

- Playback telemetry ingress:
  - `watchlab` timeline events (`play`, `pause`, `seek`, `rewind`, `mute`, fullscreen, visibility/focus, abandonment)
  - persisted by `biograph_api` as playback telemetry rows
- Explicit label ingress:
  - post-view annotation markers (`engaging_moment`, `confusing_moment`, `stop_watching_moment`, `cta_landed_moment`)
  - post-video survey responses
- Passive signal ingress:
  - AU traces, blink dynamics, face/head-pose/coarse gaze proxies, and capture quality metrics
  - extracted in worker pipelines and stored in `trace_points`
- Training/export ingress:
  - `ml/training` consumes passive traces plus explicit labels/telemetry for calibrated targets such as `reward_proxy`
