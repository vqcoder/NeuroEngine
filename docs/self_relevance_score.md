# Self-Relevance Score

The Self-Relevance Score estimates whether a creative feels personally applicable to the intended audience context.

This score is intentionally separate from social transmission:
- self relevance asks: "Does this feel made for me (or my role/use case)?"
- social transmission asks: "Is this likely to be shared or talked about?"

## Signals used
- direct-address cues in text overlays / CTA language (`you`, `your`, etc.)
- optional audience metadata overlap (only explicit metadata; no protected-trait inference)
- niche specificity and personalization hooks in wording
- survey-supported resonance when available
- conservative timeline fallback when personalization context is sparse

## Privacy and safety boundaries
- Protected-trait terms are excluded from audience matching.
- Audience matching is restricted to explicit metadata and token overlap.
- When personalization context is missing, the module degrades confidence and adds warnings instead of inventing specificity.

## Output shape
`aggregate_metrics.self_relevance`
- `pathway`: `contextual_personalization` | `survey_augmented` | `fallback_proxy` | `insufficient_data`
- `global_score` (0-100)
- `confidence` (0-1)
- `segment_scores[]` with `start_ms`, `end_ms`, `score`, `confidence`, `reason`
- `warnings[]` for limited context or sparse support
- component signals:
  - `direct_address_signal`
  - `audience_match_signal`
  - `niche_specificity_signal`
  - `personalization_hook_signal`
  - `resonance_signal`
  - `context_coverage`

