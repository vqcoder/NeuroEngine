"""Baseline XGBoost multi-trace regressor wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import pandas as pd
from xgboost import XGBRegressor

FEATURE_COLUMNS = [
    "shot_change_rate",
    "brightness",
    "motion_magnitude",
    "audio_rms",
]

PRIMARY_TARGET_COLUMNS = ["reward_proxy", "blink_inhibition", "dial"]
LEGACY_TARGET_COLUMNS = ["attention"]
TARGET_COLUMNS = [*PRIMARY_TARGET_COLUMNS, *LEGACY_TARGET_COLUMNS]
TARGET_FALLBACKS = {
    "attention": "reward_proxy",
}


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

        if "reward_proxy" not in output.columns and "attention" in output.columns:
            output["reward_proxy"] = output["attention"]
        if "attention" not in output.columns and "reward_proxy" in output.columns:
            output["attention"] = output["reward_proxy"]

        return output


def _resolve_target_column(dataset: pd.DataFrame, target: str) -> Optional[str]:
    if target in dataset.columns:
        return target
    fallback = TARGET_FALLBACKS.get(target)
    if fallback and fallback in dataset.columns:
        return fallback
    return None


def train_trace_models(dataset: pd.DataFrame, seed: int = 42) -> TraceModelBundle:
    """Train independent XGBoost models per target trace."""

    models: Dict[str, XGBRegressor] = {}

    for target in TARGET_COLUMNS:
        source_column = _resolve_target_column(dataset, target)
        if source_column is None:
            continue

        subset = dataset.dropna(subset=[source_column])
        if subset.empty:
            continue

        x_train = subset[FEATURE_COLUMNS].astype(float)
        y_train = subset[source_column].astype(float)

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

    frame = pd.DataFrame(predictions)
    if "reward_proxy" not in frame.columns and "attention" in frame.columns:
        frame["reward_proxy"] = frame["attention"]
    if "attention" not in frame.columns and "reward_proxy" in frame.columns:
        frame["attention"] = frame["reward_proxy"]
    return frame
