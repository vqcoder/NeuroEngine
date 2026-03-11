# AU Friction Score

`AU Friction Score` is a diagnostic, AU-level signal that summarizes windows where facial action-unit patterns suggest confusion, strain, amusement, tension, or resistance.

## Scope
- Uses Action Unit traces (`AU04`, `AU06`, `AU12`, `AU25`, `AU26`, `AU45`) as one channel among many.
- Not a standalone truth engine.
- Not a direct predictor of sales, conversion, or factual truth.

## Inputs
- `traces.au_channels` (AU timeline traces)
- Aggregate timeline buckets (`bucket_rows`) with:
  - AU summaries (`au_norm`)
  - `face_presence`, `head_pose_stability`
  - `tracking_confidence`, `quality_score`
  - `quality_flags` (`low_light`, `face_lost`, `high_yaw_pitch`, etc.)
  - optional brightness/occlusion/head-pose-valid summaries
  - scene/cut alignment for transition context

## Output contract
- `aggregate_metrics.au_friction`
  - `pathway`: `au_signal_model` | `fallback_proxy` | `insufficient_data`
  - `global_score` (0-100)
  - `confidence` (0-1)
  - `segment_scores[]` with:
    - AU window score/confidence
    - dominant diagnostic state
    - AU signal mix and derived state signals
    - optional `transition_context` (`post_transition_spike`)
  - `warnings[]` for face-quality limitations

## Quality handling
Confidence is explicitly degraded when face input quality is weak, including:
- missing face windows
- unstable head pose
- high occlusion / face-loss
- high lighting variance or sustained low-light flags

## Transition mapping
When confusion-weighted AU signals spike immediately after a scene/cut change, the module marks that window as `post_transition_spike` for edit-diagnostic interpretation.
