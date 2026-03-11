# Attentional Synchrony Index

This module estimates how strongly a video drives viewers to converge on the same visual target and moment.

## Output Surface

- Asset-level estimate:
  - `aggregate_metrics.attentional_synchrony.global_score` (0-100)
  - `aggregate_metrics.attentional_synchrony.confidence` (0-1)
  - `aggregate_metrics.attentional_synchrony.pathway`
- Timeline-level estimate:
  - `aggregate_metrics.attentional_synchrony.segment_scores[]`
  - `aggregate_metrics.attentional_synchrony.peaks[]`
  - `aggregate_metrics.attentional_synchrony.valleys[]`
- Evidence summary:
  - `aggregate_metrics.attentional_synchrony.evidence_summary`
  - `aggregate_metrics.attentional_synchrony.signals_used[]`

## Estimation Pathways

### 1) Direct Panel Gaze Pathway (`direct_panel_gaze`)

Used when panel-level gaze support is strong enough across aligned windows.

Primary signals:

- cross-user gaze overlap (`gaze_on_screen` concentration and pairwise alignment)
- cross-user attention alignment (`attention_score` synchrony)
- session quality weighting

Behavior:

- global score is driven by bucket-level convergence plus pairwise alignment metrics
- confidence increases with direct gaze coverage and panel quality
- timeline peaks/valleys are derived from segment-level convergence scores

### 2) Fallback Proxy Pathway (`fallback_proxy`)

Used when direct multi-user gaze overlap is limited.

Primary signals:

- attention concentration proxy
- subject continuity proxy (`face_presence`, `head_pose_stability`, scene continuity)
- playback continuity + quality weighting

Behavior:

- score remains available for downstream modules
- confidence is explicitly downweighted versus the direct pathway
- timeline windows still surface estimated peaks and valleys

### 3) Insufficient Data (`insufficient_data`)

Used when both direct and fallback support are too sparse for a stable estimate.

## Compatibility Notes

- Existing aggregate fields remain unchanged:
  - `aggregate_metrics.attention_synchrony`
  - `aggregate_metrics.blink_synchrony`
  - `aggregate_metrics.grip_control_score`
- `attentional_synchrony_index` in the neuro-score taxonomy now prefers the structured diagnostics output when present, then falls back to legacy `attention_synchrony` mapping.
- No fields were removed.
