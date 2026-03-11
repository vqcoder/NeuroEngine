# Boundary Encoding Score

This module estimates whether important payload moments are placed at event boundaries where viewers are more likely to chunk and retain information.

## Output Surface

- `aggregate_metrics.boundary_encoding.global_score` (0-100)
- `aggregate_metrics.boundary_encoding.confidence` (0-1)
- `aggregate_metrics.boundary_encoding.pathway`
- `aggregate_metrics.boundary_encoding.strong_windows[]`
- `aggregate_metrics.boundary_encoding.weak_windows[]`
- `aggregate_metrics.boundary_encoding.flags[]`
- `aggregate_metrics.boundary_encoding.boundary_alignment_score`
- `aggregate_metrics.boundary_encoding.novelty_boundary_score`
- `aggregate_metrics.boundary_encoding.reinforcement_score`
- `aggregate_metrics.boundary_encoding.overload_risk_score`
- `aggregate_metrics.boundary_encoding.payload_count`
- `aggregate_metrics.boundary_encoding.boundary_count`
- `aggregate_metrics.boundary_encoding.evidence_summary`
- `aggregate_metrics.boundary_encoding.signals_used[]`

## Signals Mapped To Score

The score is timeline-local and boundary-first. It does not equate memory potential with emotion intensity.

- event boundaries:
  - scene graph cuts/scenes
  - timeline `shot_boundary`/`scene_block`
- novelty at boundaries:
  - `novelty_proxy` sampled around payload windows and nearest boundaries
- claim/product/brand/offer placement:
  - CTA windows, text overlays, and keyword-labeled scene/cut markers
  - distance from payload midpoint to nearest boundary
- memory-friendly reinforcement:
  - repeated semantic payload keys with spacing in a configurable retention window
- overload risk:
  - multiple payloads stacked near one boundary window

## Pathways

- `timeline_boundary_model`:
  - preferred when boundary+payload timeline coverage is present.
- `fallback_proxy`:
  - used when payload markers or timeline support are partial.
  - confidence is explicitly capped/downweighted.
- `insufficient_data`:
  - returned when payload and boundary support are both missing.

## Flags

The module emits explicit timing/structure risk flags, including:

- `payload_overload_at_boundary`
- `poor_payload_timing`
- `payload_markers_missing`
- `memory_timing_weakness`

## Example Payload Windows

```json
{
  "strong_windows": [
    {
      "start_ms": 5750,
      "end_ms": 6350,
      "window_type": "strong_encoding",
      "reason": "Payload aligned close to an event boundary; novelty support was present.",
      "boundary_distance_ms": 50
    }
  ],
  "weak_windows": [
    {
      "start_ms": 10800,
      "end_ms": 11600,
      "window_type": "weak_encoding",
      "reason": "Payload was placed far from the nearest event boundary; novelty support was limited.",
      "boundary_distance_ms": 1900
    }
  ],
  "flags": [
    {
      "flag_key": "poor_payload_timing",
      "severity": "medium",
      "message": "Important payload was introduced away from an event boundary."
    }
  ]
}
```

## Configuration

Use existing config override patterns:

- global env override:
  - `BOUNDARY_ENCODING_CONFIG_JSON`
- per-video override in `videos.metadata`:
  - `boundary_encoding_config` or `boundaryEncodingConfig`

Supported keys are defined by `BoundaryEncodingConfig` in:

- `services/biograph_api/app/boundary_encoding.py`
