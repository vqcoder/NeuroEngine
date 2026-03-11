"""Inference helpers for model artifact + video feature extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

from .feature_extraction import extract_video_features


def _with_reward_attention_aliases(prediction_frame: pd.DataFrame) -> pd.DataFrame:
    frame = prediction_frame.copy()
    if "reward_proxy" not in frame.columns and "attention" in frame.columns:
        frame["reward_proxy"] = frame["attention"]
    if "attention" not in frame.columns and "reward_proxy" in frame.columns:
        frame["attention"] = frame["reward_proxy"]
    return frame


def predict_video_file(video_path: Path, model_artifact_path: Path) -> pd.DataFrame:
    """Predict traces for a video using saved artifact."""

    artifact = joblib.load(model_artifact_path)
    feature_columns = artifact["feature_columns"]
    target_models = artifact["target_models"]

    feature_frame = extract_video_features(video_path)
    prediction_frame = pd.DataFrame({"second": feature_frame["second"]})

    for target_name, model in target_models.items():
        prediction_frame[target_name] = model.predict(feature_frame[feature_columns])

    return _with_reward_attention_aliases(prediction_frame)


def predictions_to_records(prediction_frame: pd.DataFrame) -> List[Dict[str, float | None]]:
    """Convert prediction frame into API-friendly JSON rows.

    `attention` is retained as a compatibility alias while `reward_proxy`
    is the preferred engagement target.
    """

    rows: List[Dict[str, float | None]] = []
    passthrough_optional_columns = (
        "attention_velocity",
        "blink_rate",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
        "tracking_confidence",
    )
    for _, row in _with_reward_attention_aliases(prediction_frame).iterrows():
        reward_proxy = float(row.get("reward_proxy", 0.0))
        attention = float(row.get("attention", reward_proxy))
        record: Dict[str, float | None] = {
            "t_sec": float(row.get("second", 0.0)),
            "reward_proxy": reward_proxy,
            "attention": attention,
            "blink_inhibition": float(row.get("blink_inhibition", 0.0)),
            "dial": float(row.get("dial", 0.0)),
        }
        for column in passthrough_optional_columns:
            if column not in row:
                continue
            value = row.get(column)
            if pd.isna(value):
                record[column] = None
            else:
                record[column] = float(value)
        rows.append(record)
    return rows


def _column_noise_scale(values: pd.Series, jitter_fraction: float) -> float:
    std = float(values.std(ddof=0))
    baseline = abs(float(values.mean())) * jitter_fraction
    return float(max(std * jitter_fraction, baseline, 1e-4))


def predict_video_with_uncertainty(
    *,
    video_path: Path,
    model_artifact_path: Path,
    n_samples: int = 16,
    jitter_fraction: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Predict traces and estimate uncertainty via feature perturbation."""

    if n_samples < 2:
        raise ValueError("n_samples must be >= 2")

    artifact = joblib.load(model_artifact_path)
    feature_columns = artifact["feature_columns"]
    target_models = artifact["target_models"]

    feature_frame = extract_video_features(video_path)
    base_features = feature_frame[feature_columns].astype(float)
    prediction_frame = pd.DataFrame({"second": feature_frame["second"]})

    rng = np.random.default_rng(seed)
    perturbed_features: List[pd.DataFrame] = []
    for _ in range(n_samples):
        jittered = base_features.copy()
        for column in feature_columns:
            scale = _column_noise_scale(base_features[column], jitter_fraction)
            jittered[column] = jittered[column] + rng.normal(0.0, scale, size=jittered.shape[0])
        perturbed_features.append(jittered)

    uncertainty_terms: List[np.ndarray] = []
    for target_name, model in target_models.items():
        sample_predictions = np.vstack(
            [model.predict(perturbed_frame) for perturbed_frame in perturbed_features]
        )
        prediction_frame[target_name] = sample_predictions.mean(axis=0)
        uncertainty_terms.append(sample_predictions.std(axis=0))

    prediction_frame = _with_reward_attention_aliases(prediction_frame)

    if uncertainty_terms:
        prediction_frame["uncertainty"] = np.mean(np.vstack(uncertainty_terms), axis=0)
    else:
        prediction_frame["uncertainty"] = 0.0

    return prediction_frame
