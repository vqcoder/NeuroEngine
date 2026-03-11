"""Configuration models for the training pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetExportConfig:
    """Config for exporting per-second datasets."""

    database_url: str
    output_path: Path


@dataclass(frozen=True)
class TrainingConfig:
    """Config for baseline model training."""

    dataset_path: Path
    model_output_path: Path
    seed: int = 42
    test_split: float = 0.2
    mlflow_uri: str = "file:./mlruns"
    mlflow_experiment: str = "biotrace_baseline"
