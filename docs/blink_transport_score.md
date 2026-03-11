# Blink Transport Score

This module estimates narrative transportation from blink timing behavior and event-gating dynamics.

## Output Surface

- `aggregate_metrics.blink_transport.global_score` (0-100)
- `aggregate_metrics.blink_transport.confidence` (0-1)
- `aggregate_metrics.blink_transport.pathway`
- `aggregate_metrics.blink_transport.segment_scores[]`
- `aggregate_metrics.blink_transport.engagement_warnings[]`
- `aggregate_metrics.blink_transport.suppression_score`
- `aggregate_metrics.blink_transport.rebound_score`
- `aggregate_metrics.blink_transport.cta_avoidance_score`
- `aggregate_metrics.blink_transport.cross_viewer_blink_synchrony` (optional, panel-only)
- `aggregate_metrics.blink_transport.evidence_summary`
- `aggregate_metrics.blink_transport.signals_used[]`

## Interpretation

Blink Transport Score is a timing proxy for attentional segmentation. It is not a biochemical meter.

Primary signal families:

- blink suppression during high-information windows
- blink rebound at safe narrative boundaries
- blink avoidance around CTA/reveal windows
- cross-viewer blink synchrony when panel overlap exists

## Estimation Pathways

### 1) Direct panel blink pathway (`direct_panel_blink`)

Used when multi-session blink overlap is sufficient.

- Includes cross-viewer synchrony as a direct component.
- Confidence increases with panel quality and overlap density.

### 2) Fallback proxy pathway (`fallback_proxy`)

Used when per-session blink support exists but panel overlap is limited.

- Emphasizes suppression, rebound timing, and CTA/reveal avoidance.
- Confidence is downweighted relative to direct panel mode.

### 3) Sparse fallback (`sparse_fallback`)

Used when blink support is sparse.

- Returns approximate score with explicit confidence degradation.
- Emits `sparse_blink_signal` warning.

### 4) Unavailable / insufficient pathways

- `disabled`: feature flag disabled for environment/video.
- `insufficient_data`: no stable support for estimation.

## Warnings

`engagement_warnings[]` may include:

- `high_blink_variability`
- `mistimed_blink_rebound`
- `weak_cta_blink_avoidance`
- `sparse_blink_signal`

Warnings are diagnostic alerts, not hard labels.

## Configuration

Feature flag and config use existing patterns:

- env:
  - `BLINK_TRANSPORT_ENABLED`
  - `BLINK_TRANSPORT_CONFIG_JSON`
- per-video metadata:
  - `blink_transport_enabled` / `blinkTransportEnabled`
  - `blink_transport_config` / `blinkTransportConfig`

## Limitations

- Webcam blink/face streams are quality-dependent and can be noisy.
- Sparse or low-confidence blink data degrades confidence and may switch pathways.
- This score should be interpreted alongside tracking-quality overlays and timeline context.
