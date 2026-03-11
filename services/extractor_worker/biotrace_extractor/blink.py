"""Blink detection utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .geometry import Point, eye_aspect_ratio

# MediaPipe FaceMesh eye landmark groups used for EAR calculation.
LEFT_EYE_IDX = (33, 160, 158, 133, 153, 144)
RIGHT_EYE_IDX = (362, 385, 387, 263, 373, 380)


def _select_eye(landmarks: Sequence[Point], indices: Sequence[int]) -> Optional[Sequence[Point]]:
    if len(landmarks) <= max(indices):
        return None
    return [landmarks[index] for index in indices]


def compute_eye_aspect_ratio(landmarks: Sequence[Point]) -> Optional[float]:
    """Compute mean EAR over both eyes from a FaceMesh landmark set."""

    left_eye = _select_eye(landmarks, LEFT_EYE_IDX)
    right_eye = _select_eye(landmarks, RIGHT_EYE_IDX)
    if left_eye is None or right_eye is None:
        return None

    left_ear = eye_aspect_ratio(left_eye)
    right_ear = eye_aspect_ratio(right_eye)
    return (left_ear + right_ear) / 2.0


@dataclass
class BlinkDetector:
    """Stateful blink detector.

    This MVP implementation returns 1 when the eye stays below threshold for at
    least `min_closed_frames` consecutive frames; otherwise returns 0.
    """

    threshold: float = 0.21
    min_closed_frames: int = 2
    _closed_run: int = 0

    def update(self, ear_value: Optional[float]) -> int:
        """Update detector with current EAR and return blink probability (0/1)."""

        if ear_value is None:
            self._closed_run = 0
            return 0

        if ear_value < self.threshold:
            self._closed_run += 1
        else:
            self._closed_run = 0

        return 1 if self._closed_run >= self.min_closed_frames else 0
