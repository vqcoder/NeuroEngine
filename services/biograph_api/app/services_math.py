"""Math and statistical utility functions extracted from services.py.

Pure helper functions used for rounding, averaging, clamping, variance
injection, confidence-interval estimation, correlation, and lightweight
data normalisation across the biograph aggregation pipeline.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Video
from .readout_metrics import clamp, compute_blink_inhibition


def _round_rate(numerator: float, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / float(len(values)), 6)


def _mean_optional(values: Sequence[Optional[float]]) -> Optional[float]:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return round(sum(numeric) / float(len(numeric)), 6)


def _resolve_timeline_asset_id(video: Video) -> str:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    for key in ("asset_id", "assetId", "video_asset_id", "videoAssetId"):
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(video.id)


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    if len(values) != len(weights):
        return None
    weighted_pairs = [
        (float(value), max(float(weight), 0.0)) for value, weight in zip(values, weights)
    ]
    total_weight = sum(weight for _, weight in weighted_pairs)
    if total_weight <= 0:
        return round(sum(value for value, _ in weighted_pairs) / float(len(weighted_pairs)), 6)
    return round(
        sum(value * weight for value, weight in weighted_pairs) / total_weight,
        6,
    )


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return round((ordered[middle - 1] + ordered[middle]) / 2.0, 6)
    return round(ordered[middle], 6)


def _series_range(values: Sequence[Optional[float]]) -> float:
    numeric = [float(value) for value in values if value is not None]
    if len(numeric) < 2:
        return 0.0
    return max(numeric) - min(numeric)


def _apply_blink_rate_variance_if_flat(
    rows: List[Dict[str, object]],
    *,
    fallback_baseline: float,
    min_range: float = 0.02,
) -> None:
    if len(rows) < 3:
        return

    blink_values = [
        float(row["blink_rate"])
        for row in rows
        if row.get("blink_rate") is not None
    ]
    if len(blink_values) < 3:
        return
    if _series_range(blink_values) >= min_range:
        return

    modulation_values: List[float] = []
    for index, row in enumerate(rows):
        blink_inhibition = float(row.get("blink_inhibition", 0.0) or 0.0)
        eye_openness = row.get("eye_openness")
        eye_component = (
            clamp((0.82 - float(eye_openness)) / 0.62, -1.0, 1.0)
            if eye_openness is not None
            else 0.0
        )
        occlusion_component = float(row.get("mean_occlusion_score", 0.0) or 0.0)
        tracking_confidence = row.get("tracking_confidence")
        confidence_component = (
            1.0 - clamp(float(tracking_confidence), 0.0, 1.0)
            if tracking_confidence is not None
            else 0.0
        )
        wave_component = math.sin((index + 1) * 1.13)
        modulation_values.append(
            (0.65 * wave_component)
            + (0.85 * (-blink_inhibition))
            + (0.45 * eye_component)
            + (0.35 * occlusion_component)
            + (0.3 * confidence_component)
        )

    max_abs_modulation = max(abs(value) for value in modulation_values) or 1.0
    center = sum(blink_values) / float(len(blink_values))
    half_span = max(min_range * 4.0, 0.10)

    for row, modulation in zip(rows, modulation_values):
        baseline = max(float(row.get("blink_baseline_rate") or fallback_baseline), 1e-3)
        adjusted = center + ((modulation / max_abs_modulation) * half_span)
        adjusted = (0.7 * adjusted) + (0.3 * baseline)
        adjusted = clamp(adjusted, 0.005, 1.2)
        row["blink_rate"] = round(adjusted, 6)
        row["blink_inhibition"] = round(compute_blink_inhibition(adjusted, baseline), 6)


def _apply_reward_proxy_variance_if_flat(
    rows: List[Dict[str, object]],
    *,
    min_range: float = 0.9,
) -> None:
    if len(rows) < 3:
        return

    reward_values = [
        float(row["reward_proxy"])
        for row in rows
        if row.get("reward_proxy") is not None
    ]
    if len(reward_values) < 3:
        return
    if _series_range(reward_values) >= min_range:
        return

    modulation_values: List[float] = []
    for index, row in enumerate(rows):
        attention_velocity = float(row.get("attention_velocity", 0.0) or 0.0)
        label_signal = float(row.get("label_signal", 0.0) or 0.0)
        dial_component = (
            (float(row["dial"]) - 50.0) / 50.0
            if row.get("dial") is not None
            else 0.0
        )
        blink_component = float(row.get("blink_inhibition", 0.0) or 0.0)
        au_component = clamp(
            float(row.get("au12", 0.0) or 0.0) - float(row.get("au4", 0.0) or 0.0),
            -1.0,
            1.0,
        )
        wave_component = math.sin((index + 1) * 0.87)
        modulation_values.append(
            (0.65 * wave_component)
            + (0.55 * clamp(attention_velocity / 6.0, -1.0, 1.0))
            + (0.45 * label_signal)
            + (0.35 * dial_component)
            + (0.25 * au_component)
            + (0.2 * blink_component)
        )

    max_abs_modulation = max(abs(value) for value in modulation_values) or 1.0
    center = sum(reward_values) / float(len(reward_values))
    half_span = max(min_range / 2.0, 0.8)

    for row, modulation in zip(rows, modulation_values):
        target = clamp(center + ((modulation / max_abs_modulation) * half_span), 0.0, 100.0)
        current = float(row.get("reward_proxy", target) or target)
        row["reward_proxy"] = round(clamp((0.55 * current) + (0.45 * target), 0.0, 100.0), 6)


def _sem_confidence_interval(
    values: Sequence[float],
    center: Optional[float] = None,
    z_score: float = 1.96,
) -> Tuple[Optional[float], Optional[float]]:
    if not values:
        return None, None
    numeric = [float(value) for value in values]
    if center is None:
        center = sum(numeric) / float(len(numeric))
    if len(numeric) < 2:
        rounded_center = round(center, 6)
        return rounded_center, rounded_center
    variance = sum((value - center) ** 2 for value in numeric) / float(len(numeric) - 1)
    std = math.sqrt(max(variance, 0.0))
    sem = std / math.sqrt(float(len(numeric)))
    margin = z_score * sem
    return round(center - margin, 6), round(center + margin, 6)


def _clamp_to_metric_domain(metric_name: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    bounded = float(value)
    if metric_name in {
        "attention_score",
        "reward_proxy",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
    }:
        bounded = clamp(bounded, 0.0, 100.0)
    elif metric_name == "blink_rate":
        bounded = max(0.0, bounded)
    elif metric_name == "blink_inhibition":
        bounded = clamp(bounded, -1.0, 1.0)
    elif metric_name == "tracking_confidence":
        bounded = clamp(bounded, 0.0, 1.0)
    return round(bounded, 6)


def _pearson_correlation(x_values: Sequence[float], y_values: Sequence[float]) -> Optional[float]:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = sum(float(value) for value in x_values) / float(len(x_values))
    y_mean = sum(float(value) for value in y_values) / float(len(y_values))
    numerator = sum(
        (float(x_value) - x_mean) * (float(y_value) - y_mean)
        for x_value, y_value in zip(x_values, y_values)
    )
    x_var = sum((float(x_value) - x_mean) ** 2 for x_value in x_values)
    y_var = sum((float(y_value) - y_mean) ** 2 for y_value in y_values)
    denominator = math.sqrt(x_var * y_var)
    if denominator <= 1e-12:
        return None
    return round(clamp(numerator / denominator, -1.0, 1.0), 6)


def _first_present(values: Sequence[Optional[str]]) -> Optional[str]:
    for value in values:
        if value:
            return value
    return None


# ---------------------------------------------------------------------------
# Shared float-conversion and row-series helpers (consolidated from
# boundary_encoding, reward_anticipation, blink_transport, au_friction,
# self_relevance, social_transmission, cta_reception, timeline_feature_store).
# ---------------------------------------------------------------------------


def to_float_optional(value: object) -> Optional[float]:
    """Convert *value* to ``float``, returning ``None`` for ``None``, NaN, Inf,
    or anything that cannot be converted."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def to_float(value: object, default: Optional[float] = None) -> float:
    """Convert *value* to ``float`` with an optional *default* fallback.

    Raises ``ValueError`` / ``TypeError`` when conversion fails **and** no
    *default* is supplied.  NaN / Inf inputs are replaced by *default* (or
    ``0.0`` when *default* itself is falsy).
    """
    if value is None:
        if default is None:
            raise ValueError("value cannot be None when default is not set")
        return float(default)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        if default is None:
            raise
        return float(default)
    if math.isnan(numeric) or math.isinf(numeric):
        return float(default or 0.0)
    return numeric


def row_series_mean(
    rows: Sequence[Dict[str, object]], keys: Sequence[str]
) -> Optional[float]:
    """Return the mean of the *first*-available key value per row.

    For each row the first key in *keys* that resolves to a finite float is
    used; rows where no key resolves are skipped.
    """
    values: List[float] = []
    for row in rows:
        for key in keys:
            v = to_float_optional(row.get(key))
            if v is not None:
                values.append(v)
                break
    return _mean_optional(values)
