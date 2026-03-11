# biotrace_extractor

`biotrace_extractor` extracts frame-level biometric traces from session data:

- input: `<session_dir>/frames/*.jpg` + `<session_dir>/events.json`
- output: JSONL rows with
  - `video_time_ms` (canonical timeline key)
  - `t_ms` (legacy compatibility alias)
  - `face_ok`
  - `face_presence_confidence`
  - `brightness`
  - `blur`
  - `fps`
  - `fps_stability`
  - `face_visible_pct`
  - `occlusion_score`
  - `head_pose_valid_pct`
  - `quality_score`
  - `quality_confidence`
  - `landmarks_ok`
  - `landmarks_confidence`
  - `eye_openness`
  - `blink`
  - `blink_confidence`
  - `rolling_blink_rate`
  - `blink_baseline_rate`
  - `blink_inhibition_score`
  - `blink_inhibition_active`
  - `gaze_on_screen_proxy` (coarse probability only)
  - `gaze_on_screen_confidence`
  - `au` (`AU04`, `AU06`, `AU12`, `AU45`, `AU25`, `AU26`)
  - `au_confidence`
  - `au_norm` (baseline-corrected AU values)
  - `head_pose`
  - `head_pose_confidence`

## Capability boundaries

- Gaze output is explicitly a **coarse on-screen proxy** inferred from head pose + face geometry.
- This pipeline does **not** produce precise screen-coordinate gaze maps, microsaccades, or research-grade eye tracking.
- Blink and AU metrics are heuristics with confidence fields to support downstream quality gating.
- Quality-flag thresholds are loaded from shared config: `packages/common/quality_thresholds.json` (override via `QUALITY_THRESHOLDS_PATH`).

## CLI

```bash
extract-session --input <session_dir> --output <out.jsonl>
```

## Install

```bash
pip install -e .
```

For development tools:

```bash
pip install -e .[dev]
```

## events.json

Supported timestamp hints (priority order):

1. `frame_timestamps_ms`: list of timestamps (ms)
2. `frames`: list of objects with `{file, t_ms}`
3. `fps`: used to derive timestamps from frame index
4. fallback: parse integer from frame filename, else default 100ms spacing
