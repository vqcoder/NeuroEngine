"""Tests for readout guardian design lock checks."""

from __future__ import annotations

import json

import pytest

from app.readout_guardian import (
    ReadoutGuardianError,
    build_guardian_baseline,
    compute_algorithm_fingerprint,
    validate_readout_guardian,
    write_guardian_baseline_from_training_metadata,
)


def test_guardian_passes_current_baseline() -> None:
    report = validate_readout_guardian()

    assert report["algorithm_fingerprint"] == compute_algorithm_fingerprint()
    assert report["validated_attention_cases"] >= 4
    assert report["validated_reward_cases"] >= 4


def test_guardian_rejects_fingerprint_drift() -> None:
    baseline = build_guardian_baseline("test-learning-run")
    baseline["algorithm_fingerprint"] = "0" * 64

    with pytest.raises(ReadoutGuardianError, match="fingerprint mismatch"):
        validate_readout_guardian(baseline=baseline)


def test_guardian_rejects_case_output_drift() -> None:
    baseline = build_guardian_baseline("test-learning-run")
    baseline["attention_cases"][0]["expected"] = (
        float(baseline["attention_cases"][0]["expected"]) + 0.25
    )

    with pytest.raises(ReadoutGuardianError, match="attention case mismatch"):
        validate_readout_guardian(baseline=baseline)


def test_baseline_update_requires_approved_training_metadata(tmp_path) -> None:
    metadata_path = tmp_path / "approved.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "training": {
                    "run_id": "mlflow-guardian-metadata-test",
                    "status": "completed",
                    "pipeline": "ml/training",
                    "model_family": "biotrace_baseline",
                },
                "approval": {
                    "status": "approved",
                    "approved_by": "qa-reviewer",
                    "approved_at": "2026-03-07T15:30:00Z",
                },
                "guardian": {
                    "allow_baseline_refresh": True,
                    "target_metrics": ["attention_score", "reward_proxy"],
                },
            }
        ),
        encoding="utf-8",
    )

    baseline_path = tmp_path / "baseline.json"
    payload = write_guardian_baseline_from_training_metadata(
        metadata_path,
        baseline_path=baseline_path,
    )

    assert baseline_path.exists()
    assert payload["learning_approval"]["run_id"] == "mlflow-guardian-metadata-test"
