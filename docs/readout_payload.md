# ReadoutPayload Contract

`ReadoutPayload` is the versioned API contract for `GET /videos/{video_id}/readout`.

## Versioning
- Field: `schema_version`
- Current value: `"1.0.0"`
- Backward-compatible extensions should add optional fields.
- Breaking changes require incrementing `schema_version`.

## Core shape
- `video_id` (`uuid`)
- `variant_id` (`string | null`)
- `session_id` (`uuid | null`)
- `aggregate` (`boolean`)
- `duration_ms` (`int`)
- `timebase`
  - `window_ms`
  - `step_ms`
- `context`
  - `scenes[]`
  - `cuts[]`
  - `cta_markers[]`
- `traces`
  - `attention_score[]`
  - `attention_velocity[]`
  - `blink_rate[]`
  - `blink_inhibition[]`
  - `reward_proxy[]`
  - `valence_proxy[]`
  - `arousal_proxy[]`
  - `novelty_proxy[]`
  - `tracking_confidence[]`
  - `au_channels[]` (optional)
- `segments`
  - `attention_gain_segments[]`
  - `attention_loss_segments[]`
  - `golden_scenes[]`
  - `dead_zones[]`
  - `confusion_segments[]`
- `labels`
  - `annotations[]`
  - `survey_summary` (optional)
- `quality`
  - `session_quality_summary`
    - `trace_source` (`provided` | `synthetic_fallback` | `mixed` | `unknown`)
  - `low_confidence_windows[]`
- `aggregate_metrics` (optional; populated for aggregate readouts)
  - `attention_synchrony`
  - `blink_synchrony`
  - `grip_control_score`
  - `attentional_synchrony` (structured pathway diagnostics)
  - `narrative_control` (structured cinematic-grammar diagnostics)
  - `blink_transport` (structured blink timing and event-gating diagnostics)
  - `reward_anticipation` (structured anticipation-ramp and payoff diagnostics)
  - `boundary_encoding` (structured boundary-placement and memory-chunking diagnostics)
  - `au_friction` (AU-level diagnostic friction windows with quality-gated confidence and warnings)
  - `cta_reception` (structured CTA-window landing diagnostics from synchrony, narrative, blink, reward, and boundary timing)
  - `social_transmission` (structured shareability/support-for-social-handoff diagnostics)
  - `self_relevance` (structured personal-fit and direct-address diagnostics)
  - `synthetic_lift_prior` (predicted incremental lift/iROAS prior with uncertainty and calibration status; distinct from measured GeoX/holdout lift)
- `playback_telemetry[]` (optional, event overlays)
  - `event_type`
  - `video_time_ms`
  - `client_monotonic_ms`
  - `wall_time_ms`
  - `details`
- `product_rollups` (optional, tier-aware presentation layer over shared taxonomy)
  - `mode` (`creator` | `enterprise`)
  - `workspace_tier`
  - `enabled_modes[]`
  - `creator` surface (reception + organic reach + warnings) or `enterprise` surface (paid/brand/CTA + synthetic-vs-measured distinction)

## Time alignment
- Readout time series use explicit trace points:
  - `{ "video_time_ms": <int>, "value": <number|null>, ... }`
- Segment boundaries also use explicit `video_time_ms` fields.
- `timebase.step_ms` describes expected spacing, but explicit `video_time_ms` is the source of truth.

## Naming rules
- Use proxy names for inferred outcomes:
  - `reward_proxy`
  - `valence_proxy`
  - `arousal_proxy`
  - `novelty_proxy`
- Do not describe these fields as direct biochemical measurements.
- If legacy payloads contain `dopamine`, `dopamine_score`, or `dopamineScore`, ingestion maps them to `reward_proxy`.
- If `STRICT_CANONICAL_TRACE_FIELDS=true`, alias-only rows are rejected and canonical `reward_proxy` + `video_time_ms` are required.

## Compatibility
- During migration, response includes compatibility mirrors used by older clients:
  - `scenes`, `cuts`, `cta_markers`
  - `annotations`, `annotation_summary`, `survey_summary`
  - `quality_summary`
- New clients should prefer `context`, `labels`, and `quality`.
