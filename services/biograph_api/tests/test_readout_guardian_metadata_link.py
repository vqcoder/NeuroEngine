"""Ensure guardian baseline is backed by approved training metadata."""

from __future__ import annotations

from pathlib import Path

from app.readout_guardian import load_guardian_baseline
from app.readout_learning_metadata import load_and_validate_approved_training_metadata


def test_guardian_baseline_links_to_approved_training_metadata() -> None:
    baseline = load_guardian_baseline()
    learning_approval = baseline.get("learning_approval", {})
    run_id = str(learning_approval.get("run_id", "")).strip()
    assert run_id

    repo_root = Path(__file__).resolve().parents[3]
    metadata_path = repo_root / "ml" / "training" / "approved_runs" / f"{run_id}.json"

    metadata = load_and_validate_approved_training_metadata(metadata_path)

    assert metadata["run_id"] == run_id
