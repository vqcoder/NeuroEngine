"""Unit tests for pupillometry proxy module."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from biotrace_extractor.pupillometry import (
    PupilBaselineTracker,
    estimate_iris_radius,
    estimate_pupil_dilation_proxy,
    smooth_pupil_signal,
    LEFT_IRIS_IDX,
    RIGHT_IRIS_IDX,
)


def _make_landmarks(n: int = 478) -> List[Tuple[float, float]]:
    """Create synthetic landmarks with iris points placed realistically."""
    landmarks: List[Tuple[float, float]] = [(0.0, 0.0)] * n
    # Left iris: centre at (100, 200), boundary 10px away
    landmarks[468] = (100.0, 200.0)
    landmarks[469] = (110.0, 200.0)
    landmarks[470] = (90.0, 200.0)
    landmarks[471] = (100.0, 210.0)
    landmarks[472] = (100.0, 190.0)
    # Right iris: centre at (200, 200), boundary 10px away
    landmarks[473] = (200.0, 200.0)
    landmarks[474] = (210.0, 200.0)
    landmarks[475] = (190.0, 200.0)
    landmarks[476] = (200.0, 210.0)
    landmarks[477] = (200.0, 190.0)
    return landmarks


# ---------------------------------------------------------------------------
# estimate_iris_radius
# ---------------------------------------------------------------------------

def test_iris_radius_returns_none_for_short_landmarks() -> None:
    landmarks = [(0.0, 0.0)] * 400  # fewer than 478
    result = estimate_iris_radius(landmarks, LEFT_IRIS_IDX)
    assert result is None


def test_iris_radius_returns_positive_for_valid_landmarks() -> None:
    landmarks = _make_landmarks()
    result = estimate_iris_radius(landmarks, LEFT_IRIS_IDX)
    assert result is not None
    assert result > 0.0
    assert abs(result - 10.0) < 0.01  # boundary points are 10px from centre


# ---------------------------------------------------------------------------
# estimate_pupil_dilation_proxy
# ---------------------------------------------------------------------------

def test_pupil_proxy_returns_none_when_iod_degenerate() -> None:
    landmarks = _make_landmarks()
    # Place both iris centres at the same point
    landmarks[473] = landmarks[468]
    landmarks[474] = (landmarks[468][0] + 10, landmarks[468][1])
    landmarks[475] = (landmarks[468][0] - 10, landmarks[468][1])
    landmarks[476] = (landmarks[468][0], landmarks[468][1] + 10)
    landmarks[477] = (landmarks[468][0], landmarks[468][1] - 10)
    result = estimate_pupil_dilation_proxy(landmarks)
    assert result is None


def test_pupil_proxy_returns_value_in_0_1() -> None:
    landmarks = _make_landmarks()
    result = estimate_pupil_dilation_proxy(landmarks)
    assert result is not None
    assert 0.0 <= result <= 1.0


def test_pupil_proxy_returns_none_for_short_landmarks() -> None:
    landmarks = [(0.0, 0.0)] * 100
    result = estimate_pupil_dilation_proxy(landmarks)
    assert result is None


# ---------------------------------------------------------------------------
# smooth_pupil_signal
# ---------------------------------------------------------------------------

def test_smooth_preserves_nones() -> None:
    values: List[Optional[float]] = [0.5, None, 0.6, None, 0.7]
    result = smooth_pupil_signal(values, window=3)
    assert result[1] is None
    assert result[3] is None
    assert result[0] is not None
    assert result[2] is not None
    assert result[4] is not None


def test_smooth_smooths_neighbours() -> None:
    values: List[Optional[float]] = [0.1, 0.2, 0.3, 0.4, 0.5]
    result = smooth_pupil_signal(values, window=3)
    # Middle element should be mean of [0.2, 0.3, 0.4] = 0.3
    assert result[2] is not None
    assert abs(result[2] - 0.3) < 0.001


# ---------------------------------------------------------------------------
# PupilBaselineTracker
# ---------------------------------------------------------------------------

def test_baseline_tracker_returns_none_until_10_samples() -> None:
    tracker = PupilBaselineTracker(baseline_window_ms=30_000)
    for i in range(9):
        result = tracker.update(i * 100, 0.5)
        assert result is None, f"Expected None at sample {i}, got {result}"


def test_baseline_tracker_returns_value_in_0_1_after_sufficient_samples() -> None:
    tracker = PupilBaselineTracker(baseline_window_ms=30_000)
    # Feed 15 samples with slight variation
    for i in range(15):
        result = tracker.update(i * 100, 0.5 + (i % 3) * 0.01)

    # The last result should be valid
    assert result is not None
    assert 0.0 <= result <= 1.0


def test_baseline_tracker_returns_none_for_none_input() -> None:
    tracker = PupilBaselineTracker()
    # Fill with enough samples first
    for i in range(15):
        tracker.update(i * 100, 0.5)
    result = tracker.update(2000, None)
    assert result is None
