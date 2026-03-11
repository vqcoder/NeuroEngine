# ml/training

Training pipeline for biograph traces.

## What it does

- Ingests sessions + trace points from Postgres
- Extracts per-second video/audio features:
  - shot change rate
  - brightness
  - motion magnitude
  - audio RMS
- Exports a per-second training dataset with passive + explicit label context:
  - passive diagnostics (AU/blink/gaze/playback/capture quality)
  - explicit labels (timeline annotations + survey aggregates)
- Builds a calibrated `reward_proxy` target (preferred)
  - `attention` is retained as a compatibility alias
- Trains baseline XGBoost regressors for:
  - reward_proxy
  - blink_inhibition
  - dial
  - attention (legacy alias)
- Logs params/metrics/artifacts to MLflow
- Saves model artifact for API inference

## Measurement language

- This pipeline does not model or claim direct dopamine measurement.
- `reward_proxy` is a learned/composite engagement target, informed by multiple signals.
- Face-only traces are diagnostic inputs, not direct ground-truth labels.

## Install

```bash
pip install -e .[dev]
```

## Reproducible run

```bash
ml-run \
  --database-url postgresql+psycopg://biograph:biograph@localhost:5432/biograph \
  --dataset-path artifacts/train_dataset.csv \
  --model-path artifacts/baseline_xgb.joblib \
  --seed 42
```

## Manual steps

```bash
ml-export-dataset --database-url <DB_URL> --output artifacts/train_dataset.csv
ml-train --dataset artifacts/train_dataset.csv --model-output artifacts/baseline_xgb.joblib --seed 42
```

## MLflow

By default, logs are written to `mlruns` under `neurotrace/ml/training` (local file store).
Override with `--mlflow-uri`.

## Guardian Approval Metadata

Approved training runs that are allowed to refresh the readout guardian baseline
must be recorded as JSON files under:

- `ml/training/approved_runs/<run_id>.json`

Those files are validated by `services/biograph_api/app/readout_learning_metadata.py`.
Baseline refresh is blocked unless metadata is explicitly approved and
`guardian.allow_baseline_refresh` is `true`.
