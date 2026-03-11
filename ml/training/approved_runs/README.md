# Approved Training Runs

Each file in this folder represents an approved training job metadata payload that
is allowed to refresh the readout guardian baseline.

File naming convention:

- `<run_id>.json`

Required fields are validated by:

- `services/biograph_api/app/readout_learning_metadata.py`

Baseline updates are blocked unless metadata status is approved and
`guardian.allow_baseline_refresh` is `true`.
