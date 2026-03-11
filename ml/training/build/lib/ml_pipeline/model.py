"""Baseline XGBoost multi-trace regressor wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

FEATURE_COLUMNS = [
    "shot_change_rate",
    "brightness",
    "motion_magnitude",
    "audio_rms",
]
TARGET_COLUMNS = ["attention", "blink_inhibition", "dial"]


@dataclass
class TraceModelBundle:
    """Container for per-trace regressors and metadata."""

    feature_columns: List[str]
    target_models: Dict[str, XGBRegressor]

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Predict all traces for input feature frame."""

        output = pd.DataFrame(index=frame.index)
        features = frame[self.feature_columns].astype(float)

        for target, model in self.target_models.items():
            output[target] = model.predict(features)

        return output


def train_trace_models(dataset: pd.DataFrame, seed: int = 42) -> TraceModelBundle:
    """Train independent XGBoost models per target trace."""

    models: Dict[str, XGBRegressor] = {}

    for target in TARGET_COLUMNS:
        subset = dataset.dropna(subset=[target])
        if subset.empty:
            continue

        x_train = subset[FEATURE_COLUMNS].astype(float)
        y_train = subset[target].astype(float)

        model = XGBRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=seed,
            n_jobs=4,
        )
        model.fit(x_train, y_train)
        models[target] = model

    if not models:
        raise RuntimeError("No target models were trained; dataset has no usable labels")

    return TraceModelBundle(feature_columns=list(FEATURE_COLUMNS), target_models=models)


def predict_with_bundle(bundle: TraceModelBundle, dataset: pd.DataFrame) -> pd.DataFrame:
    """Predict traces for all rows in dataset."""

    features = dataset[bundle.feature_columns].astype(float)
    predictions: Dict[str, Iterable[float]] = {}

    for target, model in bundle.target_models.items():
        predictions[target] = model.predict(features)

    return pd.DataFrame(predictions)
