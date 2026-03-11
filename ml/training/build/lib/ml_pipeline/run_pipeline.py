"""Reproducible one-command pipeline run (export + train + MLflow logging)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import export_training_dataset
from .train import train_baseline
from .config import TrainingConfig


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full biotrace baseline pipeline")
    parser.add_argument(
        "--database-url",
        type=str,
        default="postgresql+psycopg://biograph:biograph@localhost:5432/biograph",
    )
    parser.add_argument("--dataset-path", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-split", type=float, default=0.2)
    parser.add_argument("--mlflow-uri", type=str, default="file:./mlruns")
    parser.add_argument("--mlflow-experiment", type=str, default="biotrace_baseline")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    dataset = export_training_dataset(args.database_url, args.dataset_path)
    print(f"Exported rows: {len(dataset)}")

    config = TrainingConfig(
        dataset_path=args.dataset_path,
        model_output_path=args.model_path,
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
