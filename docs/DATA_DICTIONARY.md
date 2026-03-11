# DATA_DICTIONARY

## studies
- `id` (uuid)
- `name` (text)
- `description` (text, nullable)
- `created_at` (timestamp)

## videos
- `id` (uuid)
- `study_id` (uuid)
- `title` (text)
- `source_url` (text)
- `duration_ms` (int, nullable)
- `metadata` (json, nullable)
- `scene_boundaries` (json[], nullable)

## participants
- `id` (uuid)
- `study_id` (uuid)
- `external_id` (text, nullable)
- `demographics` (json, nullable)

## sessions
- `id` (uuid)
- `study_id` (uuid)
- `video_id` (uuid)
- `participant_id` (uuid)
- `status` (text)
- `started_at`, `ended_at`, `created_at` (timestamp)

## trace_points
- `id` (int)
- `session_id` (uuid)
- `t_ms` (int, aligned to `video_time_ms`)
- `video_time_ms` (int, canonical playback alignment clock)
- `scene_id` (text, nullable)
- `cut_id` (text, nullable)
- `cta_id` (text, nullable)
- `face_ok` (bool)
- `face_presence_confidence` (float, nullable)
- `brightness` (float)
- `blur` (float, nullable)
- `landmarks_ok` (bool)
- `landmarks_confidence` (float, nullable)
- `eye_openness` (float, nullable)
- `blink` (int)
- `blink_confidence` (float, nullable)
- `rolling_blink_rate` (float, nullable)
- `blink_inhibition_score` (float, nullable)
- `blink_inhibition_active` (bool, nullable)
- `blink_baseline_rate` (float, nullable)
- `dial` (float, nullable)
- `reward_proxy` (float, nullable, calibrated engagement proxy)
- `au` (json)
- `au_norm` (json)
- `au_confidence` (float, nullable)
- `head_pose` (json)
- `head_pose_confidence` (float, nullable)
- `head_pose_valid_pct` (float, nullable)
- `gaze_on_screen_proxy` (float, nullable, coarse webcam proxy only)
- `gaze_on_screen_confidence` (float, nullable)
- `fps` (float, nullable)
- `fps_stability` (float, nullable)
- `face_visible_pct` (float, nullable)
- `occlusion_score` (float, nullable)
- `quality_score` (float, nullable)
- `quality_confidence` (float, nullable)

### Legacy ingest alias

- `dopamine`, `dopamine_score`, and `dopamineScore` are deprecated aliases for `reward_proxy`.
- `t_ms` is a deprecated alias for `video_time_ms`.
- Default compatibility mode (`STRICT_CANONICAL_TRACE_FIELDS=false`) keeps these aliases accepted and normalized server-side.
- Strict mode (`STRICT_CANONICAL_TRACE_FIELDS=true`) rejects alias-only rows with HTTP 422 and details listing rejected aliases and required canonical fields.

### Alias sunset rollout

1. Keep `STRICT_CANONICAL_TRACE_FIELDS=false` while producers migrate to `reward_proxy` + `video_time_ms`.
2. Monitor `flagged_missing_video_time_ms` and ingest validation errors until alias usage is near zero.
3. Enable strict mode in staging, then production.
4. After all producers are canonical, remove alias support in a versioned API change.

## survey_responses
- `id` (uuid)
- `session_id` (uuid)
- `question_key` (text)
- `response_text` (text, nullable)
- `response_number` (float, nullable)
- `response_json` (json, nullable)

## session_playback_events
- `id` (uuid)
- `session_id` (uuid)
- `video_id` (uuid)
- `event_type` (text)
- `video_time_ms` (int)
- `wall_time_ms` (bigint, nullable)
- `client_monotonic_ms` (bigint, nullable)
- `details` (json, nullable)
- `scene_id` / `cut_id` / `cta_id` (text, nullable)

### Trace source observability

- Upload flow writes a `trace_source` playback event with:
  - `details.trace_source = "provided"` or `"synthetic_fallback"`.
- Readout quality rollup surfaces aggregate provenance as:
  - `quality.session_quality_summary.trace_source` (`provided` | `synthetic_fallback` | `mixed` | `unknown`).
