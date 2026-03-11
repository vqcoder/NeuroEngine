# NeuroTrace Update Plan (Audit + Implementation Order)

## Scope
This plan audits current repo behavior against updated product requirements and defines a concrete implementation sequence.

## Current-state audit vs requirements

### 1) Keep webcam opt-in and session quality gating
- **Current state**
  - `apps/watchlab/app/study/[studyId]/study-client.tsx` currently enforces webcam as required after consent.
  - Quality checks exist (brightness, face detect fallback, FPS), with gating to start playback.
- **Gap**
  - Webcam is not opt-in in current implementation.
- **Planned change**
  - Restore explicit webcam opt-in in consent/camera step while preserving quality gating when webcam is enabled.
  - Add explicit “continue without webcam” path for opt-out sessions, with data-quality flags so downstream can segment opt-out cohorts.

### 2) Passive first viewing by default; no continuous like/dislike tapping in first pass
- **Current state**
  - First-view flow is mostly passive.
  - Dial is now behind `STUDY_DIAL_ENABLED` and can be disabled by default.
- **Gap**
  - No explicit “first pass is always passive” contract in shared schemas/API/docs.
- **Planned change**
  - Add explicit `view_mode` / `pass_index` semantics to session payloads and backend models.
  - Keep dial disabled by default in first pass; reserve for calibration/second-pass mode only.

### 3) Post-view timeline tagging (engaging/confusing/stop/CTA landed)
- **Current state**
  - Post-view survey exists, but no structured timeline tagging UI or persistence model.
- **Gap**
  - Missing tagging UI, schema, backend storage, and dashboard rendering.
- **Planned change**
  - Add post-view timeline annotation step with four required tags:
    - `most_engaging_moment`
    - `most_confusing_moment`
    - `wanted_to_stop_moment`
    - `cta_landed_moment`
  - Persist each with `video_time_ms` (+ optional text notes), and optional `scene_id`/`cut_id`/`cta_id`.

### 4) Capture/persist full passive signal set + telemetry + capture quality
- **Current state**
  - Persisted trace row fields today: `t_ms`, `face_ok`, `brightness`, `landmarks_ok`, `blink`, `dial`, `au`, `au_norm`, `head_pose`.
  - Watchlab collects event timeline but does not forward full event details into `biograph_api` tables.
  - `extractor_worker` computes AU proxies, blink, baseline-corrected AUs, head pose, brightness.
- **Gaps**
  - Missing persisted fields:
    - rolling blink rate
    - blink inhibition windows vs baseline
    - coarse gaze-on-screen probability
    - capture-quality metrics: blur, fps stability, face_visible_pct, occlusion score, head_pose_valid_pct
    - explicit confidence/quality fields on face/gaze/blink outputs
  - Missing playback telemetry persistence:
    - rewind, mute/unmute, fullscreen enter/exit, window blur/focus, abandonment.
- **Planned change**
  - Extend ingestion schemas + DB trace/event tables.
  - Add event/session telemetry table and quality aggregate fields.
  - Extend extractor output schema and computations for blink-rate/inhibition/gaze/quality/confidence.

### 5) Align all traces/events to `video_time_ms` and optionally to `scene_id`/`cut_id`/`cta_id`
- **Current state**
  - Frontend timeline/events are keyed by `videoTimeMs`.
  - Backend trace table uses `t_ms` naming.
  - Scene boundaries exist (`videos.scene_boundaries`) but no first-class `scene_id`/`cut_id`/`cta_id`.
- **Gap**
  - Naming inconsistency (`t_ms` vs `video_time_ms`).
  - No structured IDs for scene/cut/CTA alignment.
- **Planned change**
  - Add `video_time_ms` column(s) and compatibility shims for `t_ms`.
  - Add optional alignment fields on trace/events/tags: `scene_id`, `cut_id`, `cta_id`.
  - Extend video metadata schema to carry cut/CTA maps and runtime resolver in ingest pipeline.

### 6) Rename/deprecate any “dopamine” fields to reward-proxy naming
- **Current state**
  - No active schema fields named “dopamine” found.
  - Optimizer already uses `reward_proxy`.
- **Gap**
  - Need explicit anti-overclaim guardrails and deprecation policy for future fields/copy.
- **Planned change**
  - Add naming guard tests/checks and docs policy references.
  - If future legacy fields appear, support read-only aliases and migrate to `reward_proxy` / `engagement_proxy`.

### 7) Update dashboard/docs to avoid full eye tracking or direct dopamine implication
- **Current state**
  - No explicit direct dopamine or precise eye-tracking claims detected in current dashboard/docs.
  - No coarse-gaze trace currently shown.
- **Gap**
  - Need explicit coarse-gaze language where gaze is introduced.
  - Need dashboards/docs updated with new timeline tags + telemetry semantics.
- **Planned change**
  - Add coarse-gaze labels/tooltips and confidence semantics.
  - Update README/spec/data dictionary/privacy docs with non-overclaim copy and signal definitions.

---

## Affected files/modules and exact changes

## 1. Study player (`apps/watchlab`)
- **`apps/watchlab/app/study/[studyId]/study-client.tsx`**
  - Reintroduce webcam opt-in branch while preserving quality gating for opted-in sessions.
  - Keep first viewing passive by default; dial hidden in first pass.
  - Add post-view timeline tagging UI step after playback with 4 required tags.
  - Add telemetry listeners:
    - video: play/pause/seek/rewind/ratechange/volumechange/mute/fullscreen enter-exit
    - window/document: blur/focus/visibilitychange before completion => abandonment candidate
  - Ensure every emitted event/tag includes `videoTimeMs`.
  - Add alignment resolver hook to attach `scene_id`/`cut_id`/`cta_id` when metadata exists.
- **`apps/watchlab/lib/schema.ts`**
  - Add schemas for timeline tags and richer telemetry events.
  - Add confidence/quality fields where applicable.
  - Keep backward compatibility for existing event types.
- **`apps/watchlab/app/api/study/[studyId]/config/route.ts`**
  - Extend config payload to optionally provide scene/cut/CTA maps and study mode flags.
- **`apps/watchlab/app/api/upload/route.ts`**
  - Forward telemetry and timeline tags to `biograph_api` (new endpoints or expanded ingest payloads).
  - Stop relying on placeholder-only trace generation as primary path when extracted signals are available.
- **Tests**
  - `apps/watchlab/tests/playwright/smoke.spec.ts`:
    - cover opt-in and opt-out gating
    - verify passive first-view path
    - verify timeline-tag step appears after ended
    - verify audio/camera gating behavior remains stable
  - `apps/watchlab/tests/jest/schema.test.ts`:
    - validate new timeline tag and telemetry schema rules.
- **Docs**
  - `apps/watchlab/README.md` update flow and payload contract.

## 2. Backend ingestion/schema (`services/biograph_api`)
- **`services/biograph_api/app/models.py`**
  - Extend `trace_points` with:
    - `video_time_ms` (deprecating `t_ms`)
    - `blink_rate_rolling`
    - `blink_inhibition_score`
    - `gaze_on_screen_prob`
    - confidence fields (`blink_confidence`, `gaze_confidence`, `face_confidence`)
    - quality fields (`blur`, `fps_stability`, `occlusion_score`, `head_pose_valid`)
    - optional `scene_id`, `cut_id`, `cta_id`
  - Add session telemetry table (e.g., `playback_events`).
  - Add timeline-tag table (e.g., `timeline_tags`).
  - Optionally add session-level quality aggregate table/columns.
- **`services/biograph_api/app/schemas.py`**
  - Extend `TracePointIn`, `TraceBucket`, `QCStats`, and summary response models.
  - Add ingestion/response schemas for timeline tags and playback telemetry.
- **`services/biograph_api/app/services.py`**
  - Parse/insert new fields; keep compatibility with existing `t_ms`.
  - Aggregate new metrics in summary output.
  - Add scene/cut/CTA alignment propagation where IDs are present.
- **`services/biograph_api/app/main.py`**
  - Add endpoints or expand existing endpoints for:
    - playback telemetry ingest
    - timeline tag ingest
  - Keep existing endpoint contracts functioning for old clients.
- **Migrations**
  - Add Alembic migration(s) after `0002_trace_points_add_dial.py` for new columns/tables.
  - Include data migration/backfill from `t_ms` -> `video_time_ms`.
- **Tests**
  - Update integration tests (`services/biograph_api/tests/test_integration_summary.py`) for new schema and aggregations.
  - Add tests for tag + telemetry ingest and summary.

## 3. Vision extraction pipeline (`services/extractor_worker`)
- **`services/extractor_worker/biotrace_extractor/schemas.py`**
  - Extend output row with:
    - `video_time_ms` alias or replacement strategy
    - rolling blink rate
    - blink inhibition score/window flags
    - coarse gaze-on-screen probability
    - confidence fields
    - quality fields (blur/fps stability/occlusion/head_pose_valid)
    - optional scene/cut/CTA IDs.
- **`services/extractor_worker/biotrace_extractor/extractor.py`**
  - Compute blur metric (e.g., Laplacian variance), rolling blink rate, inhibition vs baseline.
  - Add coarse gaze-on-screen heuristic from eye/face orientation confidence.
  - Emit quality + confidence outputs per row.
- **`blink.py`, `baseline.py`, `head_pose.py`, `facemesh.py`**
  - Add confidence-aware outputs and helpers for inhibition windows.
- **`services/extractor_worker/README.md` and tests**
  - Update documented output schema.
  - Add/extend tests for blink-rate rolling/inhibition and new quality fields.

## 4. Dashboard (`apps/dashboard`)
- **`apps/dashboard/src/types.ts`**
  - Add types for timeline tags, telemetry aggregates, confidence/quality metrics, and optional scene/cut/CTA IDs.
- **`apps/dashboard/src/api.ts`**
  - Consume expanded summary payload.
- **`apps/dashboard/src/pages/VideoDashboardPage.tsx`**
  - Render post-view timeline tags and playback telemetry overlays.
  - Show coarse-gaze wording and confidence disclaimers.
  - Ensure copy does not imply precise eye tracking or direct dopamine.
- **`apps/dashboard/src/components/SummaryChart.tsx`**
  - Overlay timeline tags and telemetry events (seek/rewind/mute/fullscreen/abandon).
  - Add scene/cut/CTA alignment markers when available.
- **`apps/dashboard/src/utils/exporters.ts`**
  - Include new fields in CSV/JSON exports.
- **Tests**
  - Update `apps/dashboard/e2e/dashboard.spec.ts` for new payload and UI elements.
- **Docs**
  - `apps/dashboard/README.md` refresh metric language and limits.

## 5. Shared contracts (`packages/common`)
- **`packages/common/zod/sessionBundle.ts`**
  - Add timeline tags + telemetry + optional alignment IDs + quality/confidence fields.
  - Keep old fields supported with deprecation comments.
- **`packages/common/pydantic/session_bundle.py`**
  - Mirror Zod updates.
- **`packages/common/README.md`**
  - Document parity and deprecation strategy.

## 6. ML/training + inference (`ml/training`, `ml/inference`)
- **`ml/training/ml_pipeline/dataset.py`**
  - Consume expanded trace schema (`video_time_ms`, blink metrics, gaze proxy, quality/confidence).
  - Keep compatibility with legacy `t_ms`.
- **`ml/training/ml_pipeline/model.py`, `train.py`, `metrics.py`**
  - Add support for calibrated `reward_proxy` target naming where relevant.
- **`ml/inference/optimizer/optimizer/engine.py` and models**
  - Ensure input contracts use `reward_proxy`/`engagement_proxy` naming consistently.
  - Add optional use of timeline tags and telemetry for suggestion context.
- **Docs**
  - Update `ml/training/README.md`, `ml/inference/README.md` wording and field names.

## 7. Repository docs/spec
- **`README.md`**
  - Reconcile with actual flow (opt-in webcam + quality gating + passive first pass + post-view tags).
- **`docs/SPEC.md`**
  - Add canonical stage flow and signal contracts.
- **`docs/DATA_DICTIONARY.md`**
  - Add new tables/columns and deprecation notes (`t_ms` -> `video_time_ms`).
- **`docs/PRIVACY.md`**
  - Clarify coarse gaze, confidence semantics, and no precise eye-tracking claims.
- **`docs/CLOUD_RAILWAY.md`**
  - Add any new env flags (e.g., first-pass mode, timeline tag feature toggles).

---

## Migration risks

1. **Time-axis migration risk (`t_ms` -> `video_time_ms`)**
   - Existing queries, API responses, dashboard mapping, and training pipeline currently use `t_ms`.
   - Mitigation: additive migration first, dual-write/dual-read period, then planned deprecation.

2. **Ingestion compatibility risk**
   - Existing watchlab payloads and tests rely on current schema.
   - Mitigation: versioned schema handling + defaults for missing new fields.

3. **Data volume/performance risk**
   - Adding per-event telemetry and richer per-point quality fields increases storage and query costs.
   - Mitigation: indexing on `(session_id, video_time_ms)`, optional compression/aggregation jobs.

4. **Extractor confidence quality risk**
   - Coarse gaze and inhibition estimates can be noisy across device/browser conditions.
   - Mitigation: always expose confidence and quality gates; avoid hard claims in UI.

5. **Dashboard contract drift risk**
   - Frontend type changes can break existing summary rendering.
   - Mitigation: additive summary fields, robust null-safe rendering, e2e fixture expansion.

6. **Feature-flag behavior risk**
   - Passive-first and dial/calibration modes can diverge unexpectedly.
   - Mitigation: explicit `pass_index` and `study_mode` in payloads + integration tests per mode.

---

## Recommended implementation order

1. **Schema + naming foundations (no UI changes yet)**
   - Finalize `video_time_ms`, tag model, telemetry model, and reward-proxy naming in shared schemas and API schemas.
2. **DB migrations + backend dual-read/dual-write**
   - Add columns/tables and compatibility shims in `biograph_api`.
3. **Watchlab data capture updates**
   - Restore webcam opt-in + quality gating.
   - Add passive-first enforcement and post-view timeline tagging.
   - Add full playback telemetry capture with `video_time_ms`.
4. **Extractor enhancements**
   - Add rolling blink/inhibition, coarse gaze proxy, and quality/confidence metrics.
5. **API summary expansion**
   - Aggregate new telemetry/tag/quality fields and alignment IDs.
6. **Dashboard updates**
   - Visualize new signals/tags/telemetry with non-overclaim copy.
7. **ML/training/optimizer updates**
   - Consume expanded schema and normalized reward-proxy naming.
8. **Docs + final verification**
   - Update all docs/spec/data dictionary/privacy language.
   - Run targeted tests across watchlab, biograph_api, dashboard, extractor, and training.

---

## Validation note for this planning task
- Repo audit found **no dedicated docs lint/markdown link-check command** configured in package scripts or project tooling.
- Therefore no docs-specific lint command was executed for this task.
