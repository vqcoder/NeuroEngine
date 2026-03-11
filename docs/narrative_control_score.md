# Narrative Control Score

This module estimates how consistently a video's cinematic grammar guides viewers through the intended sequence of understanding.

## Output Surface

- `aggregate_metrics.narrative_control.global_score` (0-100)
- `aggregate_metrics.narrative_control.confidence` (0-1)
- `aggregate_metrics.narrative_control.pathway`
- `aggregate_metrics.narrative_control.scene_scores[]`
- `aggregate_metrics.narrative_control.disruption_penalties[]`
- `aggregate_metrics.narrative_control.reveal_structure_bonuses[]`
- `aggregate_metrics.narrative_control.top_contributing_moments[]`
- `aggregate_metrics.narrative_control.heuristic_checks[]`
- `aggregate_metrics.narrative_control.evidence_summary`
- `aggregate_metrics.narrative_control.signals_used[]`

## Grammar Signals Mapped To Score

The score blends scene-level structure quality with transition penalties, reveal bonuses, and configurable heuristics.

- continuity vs discontinuity edits:
  - attention drop around cuts
  - motion jump around cuts (`camera_motion_proxy`)
  - local cut cadence spikes (`cut_cadence`)
- context-before-face or face-before-context ordering:
  - first-half vs second-half `face_presence_rate` trend within scenes
- shot scale shifts (proxy):
  - cut-adjacent face-presence deltas as scale/coverage shift proxy
- motion continuity:
  - frame-to-frame motion smoothness from `camera_motion_proxy` deltas
- boundary density:
  - cuts per second at scene/global scope
- reveal timing:
  - scene-transition attention gains
  - text-overlay reveal windows aligned to attention lift
- scene stability vs fragmentation:
  - cadence overload + short-shot ratio from `shot_duration_ms`

## Heuristic Checks

The module evaluates configurable rule checks:

- `hard_hook_first_1_to_3_seconds`
- `coherent_subject_persistence_during_setup`
- `payoff_not_buried_after_attention_collapse`
- `cta_not_after_disorienting_transition`

Each check contributes a signed `score_delta` and emits explicit pass/fail rationale.

## Pathways

- `timeline_grammar`:
  - preferred path when timeline feature store has shot/cadence/motion coverage.
- `fallback_proxy`:
  - uses scene graph + readout traces when timeline features are missing.
  - confidence is explicitly downweighted.
- `insufficient_data`:
  - returned when scene/trace support is too sparse.

## Configuration

Use existing config patterns:

- global env override:
  - `NARRATIVE_CONTROL_CONFIG_JSON`
- per-video override in `videos.metadata`:
  - `narrative_control_config` or `narrativeControlConfig`

Supported keys are defined by `NarrativeControlConfig` in:

- `services/biograph_api/app/narrative_control.py`
