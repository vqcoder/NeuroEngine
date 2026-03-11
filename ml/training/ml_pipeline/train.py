"""Model training entrypoint with MLflow logging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

import joblib
import mlflow
import numpy as np
import pandas as pd

from .config import TrainingConfig
from .metrics import evaluate_trace, session_average_peak_recall
from .model import TARGET_COLUMNS, predict_with_bundle, train_trace_models


def _split_by_session(dataset: pd.DataFrame, test_split: float, seed: int):
    sessions = np.array(sorted(dataset["session_id"].dropna().unique().tolist()))
    if sessions.size == 0:
        raise RuntimeError("Dataset has no session ids")

    rng = np.random.default_rng(seed)
    shuffled = sessions.copy()
    rng.shuffle(shuffled)

    n_test = max(1, int(round(len(shuffled) * test_split)))
    test_sessions = set(shuffled[:n_test])

    train_frame = dataset[~dataset["session_id"].isin(test_sessions)].copy()
    test_frame = dataset[dataset["session_id"].isin(test_sessions)].copy()

    if train_frame.empty or test_frame.empty:
        raise RuntimeError("Train/test split produced empty partition")

    return train_frame, test_frame


def train_baseline(config: TrainingConfig) -> Dict[str, Dict[str, float]]:
    """Train model, evaluate metrics, and persist artifact."""

    dataset = pd.read_csv(config.dataset_path)
    if dataset.empty:
        raise RuntimeError("Dataset is empty")

    train_frame, test_frame = _split_by_session(dataset, config.test_split, config.seed)
    bundle = train_trace_models(train_frame, seed=config.seed)

    predictions = predict_with_bundle(bundle, test_frame)

    metrics: Dict[str, Dict[str, float]] = {}
    for target in TARGET_COLUMNS:
        if target not in bundle.target_models:
            continue

        subset = test_frame.dropna(subset=[target]).copy()
        if subset.empty:
            continue

        pred_values = predictions.loc[subset.index, target].to_numpy(dtype=float)
        true_values = subset[target].to_numpy(dtype=float)
        trace_metrics = evaluate_trace(true_values, pred_values)
        trace_metrics["session_peak_recall"] = session_average_peak_recall(
            subset["session_id"].astype(str),
            true_values,
            pred_values,
            top_k=5,
            tolerance=1,
        )
        metrics[target] = trace_metrics

    config.model_output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "feature_columns": bundle.feature_columns,
            "target_models": bundle.target_models,
            "seed": config.seed,
            "targets": list(bundle.target_models.keys()),
        },
        config.model_output_path,
    )

    mlflow.set_tracking_uri(config.mlflow_uri)
    mlflow.set_experiment(config.mlflow_experiment)

    with mlflow.start_run(run_name=f"baseline_xgb_seed_{config.seed}"):
        mlflow.log_param("seed", config.seed)
        mlflow.log_param("test_split", config.test_split)
        mlflow.log_param("dataset_rows", int(dataset.shape[0]))
        mlflow.log_param("train_rows", int(train_frame.shape[0]))
        mlflow.log_param("test_rows", int(test_frame.shape[0]))

        for target, trace_metrics in metrics.items():
            for key, value in trace_metrics.items():
                mlflow.log_metric(f"{target}_{key}", float(value))

        metrics_path = config.model_output_path.with_suffix(".metrics.json")
        with metrics_path.open("w", encoding="utf-8") as handle:
            json.dump(metrics, handle, indent=2)

        mlflow.log_artifact(str(config.model_output_path))
        mlflow.log_artifact(str(metrics_path))

    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train baseline biotrace model")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-split", type=float, default=0.2)
    parser.add_argument("--mlflow-uri", type=str, default="file:./mlruns")
    parser.add_argument("--mlflow-experiment", type=str, default="biotrace_baseline")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = TrainingConfig(
        dataset_path=args.dataset,
        model_output_path=args.model_output,
        seed=args.seed,
        test_split=args.test_split,
        mlflow_uri=args.mlflow_uri,
        mlflow_experiment=args.mlflow_experiment,
    )
    metrics = train_baseline(config)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
