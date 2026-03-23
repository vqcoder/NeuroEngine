"""Pupillometry proxy via MediaPipe iris landmarks.

Estimates normalised pupil dilation from iris landmarks 468-477 which are
captured when ``refine_landmarks=True`` is set in FaceMeshProcessor.
"""

from __future__ import annotations

import math
from collections import deque
from typing import List, Optional, Sequence, Tuple

from .geometry import clamp01

# MediaPipe iris landmark indices.  Centre is index 0 of each group,
# boundary points are indices 1-4.
LEFT_IRIS_IDX: Tuple[int, ...] = (468, 469, 470, 471, 472)
RIGHT_IRIS_IDX: Tuple[int, ...] = (473, 474, 475, 476, 477)


def estimate_iris_radius(
    landmarks: Sequence[Tuple[float, float]],
    indices: Tuple[int, ...],
) -> Optional[float]:
    """Mean pixel distance from iris centre to each boundary landmark.

    Returns ``None`` when the landmark list has fewer than 478 entries or
    any required index is out of range.
    """

    if len(landmarks) < 478:
        return None

    centre_idx = indices[0]
    boundary_indices = indices[1:]

    try:
        cx, cy = landmarks[centre_idx]
    except (IndexError, TypeError):
        return None

    total = 0.0
    count = 0
    for idx in boundary_indices:
        try:
            bx, by = landmarks[idx]
        except (IndexError, TypeError):
            return None
        total += math.hypot(bx - cx, by - cy)
        count += 1

    if count == 0:
        return None

    return total / count


def estimate_pupil_dilation_proxy(
    landmarks: Sequence[Tuple[float, float]],
) -> Optional[float]:
    """Normalised pupil dilation proxy from iris landmarks.

    Returns a value in [0, 1] representing the mean normalised iris area
    (left + right), or ``None`` when estimation is not possible.
    """

    left_radius = estimate_iris_radius(landmarks, LEFT_IRIS_IDX)
    right_radius = estimate_iris_radius(landmarks, RIGHT_IRIS_IDX)

    if left_radius is None or right_radius is None:
        return None

    # Inter-ocular distance: pixel distance between left and right iris centres.
    left_cx, left_cy = landmarks[LEFT_IRIS_IDX[0]]
    right_cx, right_cy = landmarks[RIGHT_IRIS_IDX[0]]
    iod = math.hypot(right_cx - left_cx, right_cy - left_cy)

    if iod < 1.0:
        return None

    left_norm = math.pi * (left_radius / iod) ** 2
    right_norm = math.pi * (right_radius / iod) ** 2
    mean_norm = (left_norm + right_norm) / 2.0

    return clamp01(round(mean_norm, 6))


def smooth_pupil_signal(
    values: List[Optional[float]],
    window: int = 5,
) -> List[Optional[float]]:
    """Centred rolling mean that preserves ``None`` values."""

    n = len(values)
    half = window // 2
    result: List[Optional[float]] = [None] * n

    for i in range(n):
        if values[i] is None:
            continue

        total = 0.0
        count = 0
        for j in range(max(0, i - half), min(n, i + half + 1)):
            if values[j] is not None:
                total += values[j]  # type: ignore[operator]
                count += 1

        result[i] = round(total / count, 6) if count > 0 else values[i]

    return result


class PupilBaselineTracker:
    """Rolling baseline corrector that emits z-score normalised to [0, 1]."""

    def __init__(self, baseline_window_ms: int = 30_000) -> None:
        self._window_ms = baseline_window_ms
        self._samples: deque[Tuple[int, float]] = deque()

    def update(self, t_ms: int, raw_value: Optional[float]) -> Optional[float]:
        """Return baseline-normalised value in [0, 1], or ``None``."""

        if raw_value is None:
            return None

        self._samples.append((t_ms, raw_value))

        # Evict samples outside the baseline window.
        cutoff = t_ms - self._window_ms
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        if len(self._samples) < 10:
            return None

        vals = [v for _, v in self._samples]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance) if variance > 0 else 0.0

        if std < 1e-9:
            return 0.5  # no variance → neutral

        z = (raw_value - mean) / std
        z_clamped = max(-3.0, min(3.0, z))
        normalised = (z_clamped + 3.0) / 6.0

        return clamp01(round(normalised, 6))
