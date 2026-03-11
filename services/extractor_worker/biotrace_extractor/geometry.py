"""Low-level geometry helpers for landmark processing."""

from __future__ import annotations

import math
from typing import Sequence, Tuple

Point = Tuple[float, float]


def clamp01(value: float) -> float:
    """Clamp numeric value to [0, 1]."""

    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def distance(p1: Point, p2: Point) -> float:
    """Euclidean distance between two 2D points."""

    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide safely, returning `default` when denominator is ~0."""

    if abs(denominator) < 1e-6:
        return default
    return numerator / denominator


def eye_aspect_ratio(points: Sequence[Point]) -> float:
    """Compute EAR from 6 eye landmarks.

    Expected point order: [p1, p2, p3, p4, p5, p6].
    EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    """

    if len(points) != 6:
        raise ValueError("eye_aspect_ratio requires exactly 6 points")

    vertical_1 = distance(points[1], points[5])
    vertical_2 = distance(points[2], points[4])
    horizontal = distance(points[0], points[3])
    return safe_ratio(vertical_1 + vertical_2, 2.0 * horizontal)
