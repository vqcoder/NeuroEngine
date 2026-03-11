# Repository instructions

## Product truth
- Facial action coding measures face movement / AUs, not direct dopamine.
- Use `reward_proxy` / `engagement_proxy` internally; never expose "measured dopamine" in UI copy, API docs, schema names, or comments unless clearly marked deprecated.
- Default study flow is:
  1. consent
  2. camera quality check
  3. passive first viewing
  4. post-view timeline annotation
  5. short survey
- Do not add continuous like/dislike tapping during the default first viewing path.
- First-class passive signals are:
  - AU traces
  - blink events / rolling blink rate / blink inhibition windows
  - face presence
  - head pose
  - coarse gaze-on-screen probability
  - playback telemetry
  - capture quality metrics
- Treat laptop webcam gaze as coarse only. Do not claim precise screen-coordinate fixation maps, microsaccades, or research-grade pupilometry.
- Every event and derived signal must align to `video_time_ms`.
- Where available, align reactions to `scene_id`, `cut_id`, and `cta_id`.
- Store capture quality fields such as brightness, blur, fps stability, face_visible_pct, occlusion score, and head_pose_valid_pct.
- All face/gaze/blink outputs must include confidence or quality fields.
- Product language should favor:
  - attention
  - blink inhibition
  - gaze-on-screen proxy
  - reward proxy
  - coarse gaze
  and avoid overclaiming.

## Readout Dashboard rules
- We do not claim direct dopamine measurement.
- Internal metric naming must use `reward_proxy`.
- UI labels should use `Reward Proxy` with explicit proxy/estimate wording where helpful.
- All traces must align to `video_time_ms`.
- Dashboard views must be scene-aware with `scene_id`, `cut_id`, and `cta_id` where available.
- Show confidence and quality overlays for webcam-derived signals.
- Treat laptop webcam gaze as coarse only.

## Engineering expectations
- Inspect the existing repo and extend current modules before creating parallel replacements.
- Keep backward compatibility where practical; if a rename is required, add deprecation shims and migrations.
- Add or update tests for each behavior change.
- Run the smallest relevant validation suite after edits.
- Update docs/spec files when schemas, metrics, UI copy, or behavior changes.
- At the end of each task, report:
  - files changed
  - commands run
  - tests passed
  - follow-up risks or TODOs
