"""Tests for offline neuro eval harness and summary output."""

from __future__ import annotations

import json
from pathlib import Path

from app.neuro_eval_runner import evaluate_dataset, load_dataset, main


DATASET_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "neuro_score_pattern_eval_dataset.json"
)


def test_eval_dataset_passes_known_good_bad_expectations() -> None:
    dataset = load_dataset(DATASET_FIXTURE_PATH)
    summary = evaluate_dataset(dataset, drift_alert_threshold=10.0)

    assert summary["passed"] is True
    assert summary["ordering_expectations"]["failed"] == 0
    assert summary["drift_expectations"]["failed"] == 0
    assert summary["cases_evaluated"] == 4
    assert summary["observability_summary"]["claim_safety_violations"] == {}
    assert summary["observability_summary"]["fallback_path_usage"]["fallback_rate"] is not None
    assert summary["observability_summary"]["missing_signal_rates"]["total_scores"] == 44


def test_eval_runner_main_writes_summary_file(tmp_path) -> None:
    output_path = tmp_path / "eval_summary.json"
    exit_code = main(
        [
            "--dataset",
            str(DATASET_FIXTURE_PATH),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["ordering_expectations"]["total"] >= 1

