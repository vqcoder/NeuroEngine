"""Tests for approved training metadata validation."""

from __future__ import annotations

import json

import pytest

from app.readout_learning_metadata import (
    ReadoutLearningMetadataError,
    load_and_validate_approved_training_metadata,
)


def test_load_and_validate_approved_training_metadata_passes(tmp_path) -> None:
    metadata_path = tmp_path / "approved-run.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "training": {
                    "run_id": "mlflow-2026-03-07-abc123",
                    "status": "completed",
                    "pipeline": "ml/training",
                    "model_family": "biotrace_baseline",
                },
                "approval": {
                    "status": "approved",
                    "approved_by": "neuroscience-lead",
                    "approved_at": "2026-03-07T12:00:00Z",
                },
                "guardian": {
                    "allow_baseline_refresh": True,
                    "target_metrics": ["attention_score", "reward_proxy"],
                },
            }
        ),
        encoding="utf-8",
    )

    payload = load_and_validate_approved_training_metadata(metadata_path)

    assert payload["run_id"] == "mlflow-2026-03-07-abc123"
    assert payload["approved_by"] == "neuroscience-lead"


def test_load_and_validate_approved_training_metadata_requires_explicit_approval(
    tmp_path,
) -> None:
    metadata_path = tmp_path / "rejected-run.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "training": {
                    "run_id": "mlflow-2026-03-07-denied",
                    "status": "completed",
                    "pipeline": "ml/training",
                    "model_family": "biotrace_baseline",
                },
                "approval": {
                    "status": "pending",
                    "approved_by": "reviewer",
                    "approved_at": "2026-03-07T12:00:00Z",
                },
                "guardian": {
                    "allow_baseline_refresh": True,
                    "target_metrics": ["attention_score", "reward_proxy"],
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReadoutLearningMetadataError, match="approval.status"):
        load_and_validate_approved_training_metadata(metadata_path)
