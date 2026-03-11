# optimizer

`optimizer` consumes a `video_summary.json` payload (scene boundaries + traces) and produces
`edit_suggestions.json` with ranked edit recommendations and predicted engagement uplift.

## Rules implemented

- Dead zone: attention below threshold for more than 2 seconds.
- Confusion/friction: blink rate increase plus AU4 increase.
- Late reward hook: strong reward proxy peak occurring late in the video.
- Cut realignment: scene cuts misaligned with natural event boundaries (blink rebounds / motion discontinuities).

## Output highlights

- Ranked `suggestions` with:
  - rule label
  - time interval / scene context
  - rationale and recommendation
  - severity, confidence, predicted delta engagement
- Overall scoring:
  - `engagement_score_before`
  - `predicted_total_delta_engagement`
  - `engagement_score_after`

## Install

```bash
pip install -e .
```

For tests:

```bash
pip install -e .[dev]
```

## CLI

```bash
optimize-edits --input /path/video_summary.json --output /path/edit_suggestions.json
```

or

```bash
python -m optimizer.cli --input /path/video_summary.json --output /path/edit_suggestions.json
```

## Demo notebook

See [notebooks/demo_optimizer.ipynb](/Users/johnkim/Documents/Personal CRM and Project management app/Alpha Engine/Alpha Engine/optimizer/notebooks/demo_optimizer.ipynb).
