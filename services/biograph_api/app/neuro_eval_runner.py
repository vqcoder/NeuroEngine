"""Offline evaluation runner for neuro score quality, drift, and claim/privacy checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, model_validator

from .claim_safety import scan_texts_for_claim_safety
from .neuro_observability import (
    compute_confidence_distribution,
    compute_missing_signal_rates,
    compute_score_drift,
)
from .schemas import NeuroScoreMachineName, NeuroScoreStatus


_ALLOWED_SCORE_KEYS = {item.value for item in NeuroScoreMachineName}
_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "neuro_score_pattern_eval_dataset.json"
)


class EvalScoreObservation(BaseModel):
    scalar_value: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: NeuroScoreStatus
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_available_payload(self):
        if self.status == NeuroScoreStatus.available:
            if self.scalar_value is None:
                raise ValueError("scalar_value must be provided when status=available")
            if self.confidence is None:
                raise ValueError("confidence must be provided when status=available")
        return self


class EvalCaseQualitySnapshot(BaseModel):
    trace_source: Optional[str] = None
    mean_tracking_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    low_confidence_windows: int = Field(default=0, ge=0)


class EvalPatternCase(BaseModel):
    case_id: str = Field(min_length=1)
    pattern_id: str = Field(min_length=1)
    quality_label: str = Field(min_length=1)
    notes: str = Field(min_length=1)
    scores: Dict[str, EvalScoreObservation] = Field(default_factory=dict)
    pathways: Dict[str, str] = Field(default_factory=dict)
    quality: EvalCaseQualitySnapshot = Field(default_factory=EvalCaseQualitySnapshot)

    @model_validator(mode="after")
    def validate_scores(self):
        unknown = sorted(key for key in self.scores.keys() if key not in _ALLOWED_SCORE_KEYS)
        if unknown:
            raise ValueError(f"Unsupported score keys in case '{self.case_id}': {', '.join(unknown)}")
        return self


class EvalOrderingExpectation(BaseModel):
    expectation_id: str = Field(min_length=1)
    better_case_id: str = Field(min_length=1)
    worse_case_id: str = Field(min_length=1)
    metric_key: str = Field(min_length=1)
    min_delta: float = Field(default=0.0)

    @model_validator(mode="after")
    def validate_metric(self):
        if self.metric_key not in _ALLOWED_SCORE_KEYS:
            raise ValueError(f"Unsupported metric_key '{self.metric_key}'")
        return self


class EvalDriftExpectation(BaseModel):
    expectation_id: str = Field(min_length=1)
    baseline_case_id: str = Field(min_length=1)
    candidate_case_id: str = Field(min_length=1)
    max_mean_abs_delta: float = Field(ge=0)
    max_metric_abs_delta: float = Field(ge=0)


class NeuroEvalDataset(BaseModel):
    schema_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    cases: List[EvalPatternCase] = Field(default_factory=list)
    ordering_expectations: List[EvalOrderingExpectation] = Field(default_factory=list)
    drift_expectations: List[EvalDriftExpectation] = Field(default_factory=list)


def _case_score_payload(case: EvalPatternCase, metric_key: str) -> Optional[EvalScoreObservation]:
    return case.scores.get(metric_key)


def _case_observations(case: EvalPatternCase) -> Dict[str, Dict[str, Any]]:
    observations: Dict[str, Dict[str, Any]] = {}
    for metric_key, payload in case.scores.items():
        observations[metric_key] = {
            "status": payload.status.value,
            "scalar_value": payload.scalar_value,
            "confidence": payload.confidence,
            "model_version": payload.model_version,
        }
    return observations


def _aggregate_fallback_usage(cases: List[EvalPatternCase]) -> Dict[str, Any]:
    modules_evaluated = 0
    fallback_modules = 0
    insufficient_modules = 0
    module_pathway_counts: Dict[str, Dict[str, int]] = {}
    for case in cases:
        for module_key, pathway in case.pathways.items():
            modules_evaluated += 1
            pathway_value = str(pathway)
            if "fallback" in pathway_value:
                fallback_modules += 1
            if pathway_value in {"insufficient_data", "disabled"}:
                insufficient_modules += 1
            module_counts = module_pathway_counts.setdefault(module_key, {})
            module_counts[pathway_value] = module_counts.get(pathway_value, 0) + 1
    return {
        "modules_evaluated": modules_evaluated,
        "fallback_modules": fallback_modules,
        "insufficient_modules": insufficient_modules,
        "fallback_rate": (
            round(fallback_modules / modules_evaluated, 6) if modules_evaluated else None
        ),
        "module_pathway_counts": module_pathway_counts,
    }


def evaluate_dataset(
    dataset: NeuroEvalDataset,
    *,
    drift_alert_threshold: float,
) -> Dict[str, Any]:
    cases_by_id = {case.case_id: case for case in dataset.cases}
    ordering_results: List[Dict[str, Any]] = []
    for expectation in dataset.ordering_expectations:
        better_case = cases_by_id.get(expectation.better_case_id)
        worse_case = cases_by_id.get(expectation.worse_case_id)
        if better_case is None or worse_case is None:
            ordering_results.append(
                {
                    "expectation_id": expectation.expectation_id,
                    "passed": False,
                    "reason": "missing_case",
                    "metric_key": expectation.metric_key,
                }
            )
            continue

        better_score = _case_score_payload(better_case, expectation.metric_key)
        worse_score = _case_score_payload(worse_case, expectation.metric_key)
        if (
            better_score is None
            or worse_score is None
            or better_score.scalar_value is None
            or worse_score.scalar_value is None
        ):
            ordering_results.append(
                {
                    "expectation_id": expectation.expectation_id,
                    "passed": False,
                    "reason": "missing_metric_value",
                    "metric_key": expectation.metric_key,
                }
            )
            continue

        delta = float(better_score.scalar_value) - float(worse_score.scalar_value)
        passed = delta >= float(expectation.min_delta)
        ordering_results.append(
            {
                "expectation_id": expectation.expectation_id,
                "passed": passed,
                "metric_key": expectation.metric_key,
                "delta": round(delta, 6),
                "required_min_delta": round(float(expectation.min_delta), 6),
                "better_case_id": better_case.case_id,
                "worse_case_id": worse_case.case_id,
            }
        )

    drift_results: List[Dict[str, Any]] = []
    for expectation in dataset.drift_expectations:
        baseline_case = cases_by_id.get(expectation.baseline_case_id)
        candidate_case = cases_by_id.get(expectation.candidate_case_id)
        if baseline_case is None or candidate_case is None:
            drift_results.append(
                {
                    "expectation_id": expectation.expectation_id,
                    "passed": False,
                    "reason": "missing_case",
                }
            )
            continue

        baseline_observations = _case_observations(baseline_case)
        candidate_observations = _case_observations(candidate_case)
        drift = compute_score_drift(
            current_scores=candidate_observations,
            reference_scores=baseline_observations,
            alert_threshold=max(float(expectation.max_metric_abs_delta), float(drift_alert_threshold)),
        )
        mean_abs_delta = drift.get("mean_abs_delta")
        max_abs_delta = drift.get("max_abs_delta")
        passed = (
            drift.get("compared_metrics", 0) > 0
            and mean_abs_delta is not None
            and max_abs_delta is not None
            and float(mean_abs_delta) <= float(expectation.max_mean_abs_delta)
            and float(max_abs_delta) <= float(expectation.max_metric_abs_delta)
        )
        drift_results.append(
            {
                "expectation_id": expectation.expectation_id,
                "passed": passed,
                "baseline_case_id": baseline_case.case_id,
                "candidate_case_id": candidate_case.case_id,
                "mean_abs_delta": mean_abs_delta,
                "max_abs_delta": max_abs_delta,
                "allowed_mean_abs_delta": expectation.max_mean_abs_delta,
                "allowed_max_metric_abs_delta": expectation.max_metric_abs_delta,
                "metrics_exceeding_threshold": drift.get("metrics_exceeding_threshold", []),
            }
        )

    combined_observations: Dict[str, Dict[str, Any]] = {}
    for case in dataset.cases:
        for metric_key, payload in _case_observations(case).items():
            combined_observations[f"{case.case_id}:{metric_key}"] = payload

    missing_signal_rates = compute_missing_signal_rates(combined_observations)
    confidence_distribution = compute_confidence_distribution(combined_observations)
    fallback_usage = _aggregate_fallback_usage(dataset.cases)
    claim_safety_violations = scan_texts_for_claim_safety(
        {case.case_id: case.notes for case in dataset.cases}
    )

    ordering_failed = sum(1 for item in ordering_results if not item["passed"])
    drift_failed = sum(1 for item in drift_results if not item["passed"])
    claim_failed = len(claim_safety_violations)
    passed = ordering_failed == 0 and drift_failed == 0 and claim_failed == 0

    return {
        "schema_version": dataset.schema_version,
        "dataset_version": dataset.dataset_version,
        "cases_evaluated": len(dataset.cases),
        "ordering_expectations": {
            "total": len(ordering_results),
            "failed": ordering_failed,
            "results": ordering_results,
        },
        "drift_expectations": {
            "total": len(drift_results),
            "failed": drift_failed,
            "results": drift_results,
        },
        "observability_summary": {
            "missing_signal_rates": missing_signal_rates,
            "confidence_distribution": confidence_distribution,
            "fallback_path_usage": fallback_usage,
            "claim_safety_violations": claim_safety_violations,
        },
        "passed": passed,
    }


def load_dataset(path: Path) -> NeuroEvalDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return NeuroEvalDataset.model_validate(payload)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run offline neuro score evaluation for known-good and known-bad creative patterns."
    )
    parser.add_argument(
        "--dataset",
        default=str(_DEFAULT_DATASET_PATH),
        help="Path to eval dataset JSON fixture.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write JSON evaluation summary.",
    )
    parser.add_argument(
        "--drift-alert-threshold",
        type=float,
        default=12.0,
        help="Alert threshold for per-metric drift deltas used in diagnostics.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Exit with code 0 even when expectations fail.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    dataset_path = Path(args.dataset).expanduser().resolve()
    dataset = load_dataset(dataset_path)
    summary = evaluate_dataset(
        dataset,
        drift_alert_threshold=float(args.drift_alert_threshold),
    )

    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)

    output_path = str(args.output or "").strip()
    if output_path:
        resolved_output = Path(output_path).expanduser().resolve()
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(rendered + "\n", encoding="utf-8")

    if summary["passed"] or args.allow_failures:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
