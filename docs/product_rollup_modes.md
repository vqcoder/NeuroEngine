# Product Rollup Modes

`product_rollups` is an additive presentation layer on top of `neuro_scores`. It does not introduce a separate scoring system.

## API Surface

- `GET /videos/{video_id}/readout`
  - optional query params:
    - `product_mode=creator|enterprise`
    - `workspace_tier=<tier>`
  - legacy aliases:
    - `productMode`
    - `workspaceTier`
- `GET /videos/{video_id}/readout/export-package` supports the same optional params.

Response fields:

- `readout.product_rollups`
- `readout_json.product_rollups`
- `compact_report.product_rollups`

## Creator Mode

Outputs:

- `reception_score`
- `organic_reach_prior`
- short explanations
- warnings (`weak_hook`, `low_synchrony`, `poor_payoff_timing`, `cta_collapse`)

Underlying score inputs:

- `reception_score`:
  - `cta_reception_score` (45%)
  - `arrest_score` (20%)
  - `attentional_synchrony_index` (20%)
  - `reward_anticipation_index` (15%)
- `organic_reach_prior`:
  - taxonomy rollup `organic_reach_prior` (no remapping)

## Enterprise Mode

Outputs:

- `paid_lift_prior`
- `brand_memory_prior`
- `cta_reception_score`
- `synthetic_lift_prior`
- `synthetic_vs_measured_lift` distinction
- decision-support summaries (`media_team_summary`, `creative_team_summary`)

Underlying score inputs:

- `paid_lift_prior`: taxonomy rollup `paid_lift_prior`
- `brand_memory_prior`: taxonomy rollup `brand_memory_prior`
- `cta_reception_score`: taxonomy score `cta_reception_score`
- `synthetic_lift_prior`: taxonomy score `synthetic_lift_prior`
- synthetic vs measured:
  - predicted values from `aggregate_metrics.synthetic_lift_prior`
  - measured values (if present) from video metadata keys:
    - `measured_incremental_lift_pct`
    - `measured_iroas`
    - `measured_lift.incremental_lift_pct`
    - `measured_lift.iroas`

## Tier-Based Mode Gating

Global config:

- `NEURO_SCORE_TAXONOMY_ENABLED` (`true` default; when `false`, taxonomy and product presentation layers are not emitted)
- `PRODUCT_ROLLUPS_ENABLED` (`true` default)
- `PRODUCT_ROLLUP_DEFAULT_TIER` (`creator` default)
- `PRODUCT_ROLLUP_TIER_MODES_JSON` (`{}` default)

Default tier policy:

- `creator` tier: creator mode only
- `enterprise` tier: creator + enterprise modes, defaulting to enterprise

If a requested mode is disabled for the workspace tier, API falls back to the tier default and sets `mode_resolution_note`.
