# Neuro Score Red-Team Checklist

Use this checklist before releasing score copy, docs, or dashboards.

## Unsupported Claims

- Verify no copy claims direct dopamine or biochemical measurement.
- Verify no copy frames facial expressions as a standalone truth engine.
- Verify no copy claims guaranteed sales outcomes or certainty.
- Verify reward/attention outputs are labeled as proxies with confidence context.
- Verify synthetic lift is clearly labeled as predicted prior, not measured incrementality.

## Privacy + Biometrics

- Verify biometric pathways have quality context (tracking confidence, low-confidence windows).
- Verify trace source (`provided` vs `synthetic_fallback`/`mixed`) is exposed for interpretation.
- Verify no protected-trait inference language is introduced.
- Verify audience-matching copy remains within consented metadata boundaries.
- Verify low-quality face input windows degrade confidence instead of fabricating precision.

## Fairness + Inference Limits

- Verify self-relevance and social transmission do not infer protected attributes.
- Verify fallback pathways explicitly reduce confidence.
- Verify missing-signal states return `insufficient_data`/`unavailable` where appropriate.
- Verify no single channel (especially facial/AU) dominates final decisioning claims.

## Release Gates

- Run offline eval harness and review expectation failures.
- Review drift summary across model versions before rollout.
- Review claim-safety test results for templated API/UI copy.
- Review observability logs for fallback spikes or missing-signal regressions.

