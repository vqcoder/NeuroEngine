"""Inference helpers for model artifact + video feature extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import joblib
import pandas as pd

from .feature_extraction import extract_video_features


def predict_video_file(video_path: Path, model_artifact_path: Path) -> pd.DataFrame:
    """Predict traces for a video using saved artifact."""

    artifact = joblib.load(model_artifact_path)
    feature_columns = artifact["feature_columns"]
    target_models = artifact["target_models"]

    feature_frame = extract_video_features(video_path)
    prediction_frame = pd.DataFrame({"second": feature_frame["second"]})

    for target_name, model in target_models.items():
        prediction_frame[target_name] = model.predict(feature_frame[feature_columns])

    return prediction_frame


def predictions_to_records(prediction_frame: pd.DataFrame) -> List[Dict[str, float]]:
    """Convert prediction frame into API-friendly JSON rows."""

    rows: List[Dict[str, float]] = []
    for _, row in prediction_frame.iterrows():
        rows.append(
            {
                "t_sec": float(row.get("second", 0.0)),
                "attention": float(row.get("attention", 0.0)),
                "blink_inhibition": float(row.get("blink_inhibition", 0.0)),
                "dial": float(row.get("dial", 0.0)),
            }
        )
    return rows
