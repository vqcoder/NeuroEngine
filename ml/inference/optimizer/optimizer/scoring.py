"""Scoring functions for estimating engagement deltas from suggestions."""

from __future__ import annotations

from typing import Dict, Iterable


BASE_RULE_UPLIFT: Dict[str, float] = {
    "dead_zone": 6.0,
    "confusion_friction": 5.0,
    "late_hook": 8.0,
    "cut_realignment": 4.0,
}


def clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def priority_from_delta(delta: float) -> str:
    if delta >= 6.0:
        return "high"
    if delta >= 3.0:
        return "medium"
    return "low"


def predict_delta(
    *,
    rule: str,
    severity: float,
    confidence: float,
    position_weight: float = 1.0,
    evidence_weight: float = 1.0,
) -> float:
    """Predict engagement uplift (points on 0-100 scale) for one suggestion."""

    base = BASE_RULE_UPLIFT.get(rule, 3.0)
    normalized_severity = clamp(severity, 0.0, 1.5)
    normalized_confidence = clamp(confidence, 0.0, 1.0)
    normalized_position = clamp(position_weight, 0.6, 1.4)
    normalized_evidence = clamp(evidence_weight, 0.6, 1.4)

    raw = base * normalized_severity * normalized_confidence * normalized_position * normalized_evidence
    return round(clamp(raw, 0.0, 20.0), 4)


def aggregate_total_delta(predicted_deltas: Iterable[float]) -> float:
    """Aggregate uplift with diminishing returns across stacked suggestions."""

    ordered = sorted((max(float(delta), 0.0) for delta in predicted_deltas), reverse=True)
    total = 0.0
    for index, delta in enumerate(ordered):
        total += delta * (0.88 ** index)
    return round(total, 4)
