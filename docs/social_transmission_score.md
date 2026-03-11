# Social Transmission Score

The Social Transmission Score estimates whether a creative contains moments people are likely to pass along to others.

This score is distinct from self-relevance:
- social transmission asks: "Would someone share or mention this?"
- self relevance asks: "Does this feel personally meant for me?"

## Signals used
- novelty and distinctiveness proxies from timeline traces (`novelty_proxy`, pacing variation)
- identity-safe signaling language in overlays/CTA labels (no protected-trait inference)
- usefulness / tell-a-friend cues from instructional or benefit-oriented text
- quote/comment-worthiness cues from concise, discussable phrasing
- emotional activation support from proxy traces (`arousal_proxy`, `reward_proxy`, attention dynamics)
- annotation marker support when available (`engaging_moment`, `cta_landed_moment`, etc.)

## Output shape
`aggregate_metrics.social_transmission`
- `pathway`: `annotation_augmented` | `timeline_signal_model` | `fallback_proxy` | `insufficient_data`
- `global_score` (0-100)
- `confidence` (0-1)
- `segment_scores[]` with `start_ms`, `end_ms`, `score`, `confidence`, `reason`
- component signals:
  - `novelty_signal`
  - `identity_signal`
  - `usefulness_signal`
  - `quote_worthiness_signal`
  - `emotional_activation_signal`
  - `memorability_signal`

## Confidence behavior
- Confidence is highest when timeline signals and annotation support both exist.
- Fallback mode is explicitly downweighted when signal coverage is limited.

