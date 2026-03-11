# CTA Reception Score

`CTA Reception Score` estimates whether call-to-action windows land while viewers are still synchronized, engaged, and receptive.

## Inputs
- `attentional_synchrony` (`aggregate_metrics.attentional_synchrony`)
- `narrative_control` (`aggregate_metrics.narrative_control`)
- `blink_transport` (`aggregate_metrics.blink_transport`)
- `reward_anticipation` (`aggregate_metrics.reward_anticipation`)
- `boundary_encoding` (`aggregate_metrics.boundary_encoding`)
- `context.cta_markers`
- Aggregate `bucket_rows` attention/quality traces

## Pathways
- `multi_signal_model`: at least 3 upstream modules have non-`insufficient_data` pathways.
- `fallback_proxy`: fewer than 3 upstream modules available; score still returned with capped confidence.
- `insufficient_data`: no CTA markers or no usable overlap for scoring.

## CTA window logic
- Computes one window per CTA marker (`start_ms`/`end_ms`).
- Evaluates support signals:
  - synchrony support
  - narrative coherence support
  - blink receptivity support
  - reward timing support
  - boundary coherence support
  - timing fit support
- Applies penalties/flags for known failure modes:
  - `cta_too_early`
  - `cta_too_late`
  - `cta_blinked_through`
  - `cta_after_fragmentation`
  - `cta_missed_reward_window`
  - `cta_cognitive_overload`

## Output contract
- `aggregate_metrics.cta_reception`
  - `global_score` (0-100)
  - `confidence` (0-1)
  - `cta_windows[]`
  - `flags[]`
  - signal rollups and `evidence_summary`

The taxonomy builder (`build_cta_reception_score`) uses `aggregate_metrics.cta_reception` as the primary source and preserves fallback support for legacy `cta_receptivity` diagnostic cards.
