"""Evaluation metrics for sequence trace prediction."""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

import numpy as np


def mae(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Mean absolute error."""

    true_arr = np.asarray(y_true, dtype=float)
    pred_arr = np.asarray(y_pred, dtype=float)
    if true_arr.size == 0:
        return 0.0
    return float(np.mean(np.abs(true_arr - pred_arr)))


def correlation(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Pearson correlation with safe fallback."""

    true_arr = np.asarray(y_true, dtype=float)
    pred_arr = np.asarray(y_pred, dtype=float)
    if true_arr.size < 2:
        return 0.0
    true_std = float(np.std(true_arr))
    pred_std = float(np.std(pred_arr))
    if true_std < 1e-8 or pred_std < 1e-8:
        return 0.0
    return float(np.corrcoef(true_arr, pred_arr)[0, 1])


def peak_recall(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    top_k: int = 5,
    tolerance: int = 1,
) -> float:
    """Recall for top-k peaks with temporal tolerance.

    A true peak is recovered if any predicted peak index lies within +/- tolerance.
    """

    true_arr = np.asarray(y_true, dtype=float)
    pred_arr = np.asarray(y_pred, dtype=float)
    if true_arr.size == 0:
        return 0.0

    k = max(1, min(top_k, true_arr.size))
    true_idx = np.argpartition(true_arr, -k)[-k:]
    pred_idx = np.argpartition(pred_arr, -k)[-k:]

    hits = 0
    for t_idx in true_idx:
        if np.any(np.abs(pred_idx - t_idx) <= tolerance):
            hits += 1

    return float(hits / k)


def evaluate_trace(y_true: Sequence[float], y_pred: Sequence[float]) -> Dict[str, float]:
    """Compute all core metrics for one trace."""

    return {
        "mae": mae(y_true, y_pred),
        "correlation": correlation(y_true, y_pred),
        "peak_recall": peak_recall(y_true, y_pred),
    }


def session_average_peak_recall(
    session_ids: Iterable[str],
    y_true: Sequence[float],
    y_pred: Sequence[float],
    top_k: int = 5,
    tolerance: int = 1,
) -> float:
    """Average peak recall computed independently per session."""

    import pandas as pd

    frame = pd.DataFrame(
        {
            "session_id": list(session_ids),
            "y_true": list(y_true),
            "y_pred": list(y_pred),
        }
    )
    if frame.empty:
        return 0.0

    recalls = []
    for _, group in frame.groupby("session_id"):
        recalls.append(
            peak_recall(
                group["y_true"].to_numpy(dtype=float),
                group["y_pred"].to_numpy(dtype=float),
                top_k=top_k,
                tolerance=tolerance,
            )
        )
    return float(np.mean(recalls)) if recalls else 0.0
