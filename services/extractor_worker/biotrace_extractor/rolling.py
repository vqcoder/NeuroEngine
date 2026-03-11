"""Rolling-window passive-signal state tracking."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import pstdev
from typing import Deque, Dict, TypedDict

from .geometry import clamp01


class RollingSignalSnapshot(TypedDict):
    """Derived rolling metrics for blink, presence, and sampling stability."""

    rolling_blink_rate: float
    blink_baseline_rate: float
    blink_inhibition_score: float
    blink_inhibition_active: bool
    face_visible_pct: float
    head_pose_valid_pct: float
    fps: float
    fps_stability: float
    window_confidence: float


@dataclass
class RollingSignalTracker:
    """Track per-frame passive-signal summaries over a sliding window."""

    window_ms: int = 10_000
    baseline_window_ms: int = 10_000
    inhibition_threshold: float = 0.35
    _samples: Deque[Dict[str, int]] = field(default_factory=deque)
    _baseline_samples: Deque[Dict[str, int]] = field(default_factory=deque)

    def _prune_samples(self, t_ms: int) -> None:
        lower_bound = t_ms - self.window_ms
        while self._samples and self._samples[0]["t_ms"] < lower_bound:
            self._samples.popleft()

    def _blink_rate(self, samples: Deque[Dict[str, int]]) -> float:
        if len(samples) < 2:
            return 0.0

        first = samples[0]["t_ms"]
        last = samples[-1]["t_ms"]
        duration_ms = max(last - first, 1)
        blink_sum = sum(sample["blink"] for sample in samples)
        return round(float(blink_sum) / (duration_ms / 1000.0), 6)

    def _fps_metrics(self) -> tuple[float, float]:
        if len(self._samples) < 2:
            return 0.0, 0.0

        timestamps = [sample["t_ms"] for sample in self._samples]
        intervals = [
            timestamps[index] - timestamps[index - 1]
            for index in range(1, len(timestamps))
        ]
        positive = [interval for interval in intervals if interval > 0]
        if not positive:
            return 0.0, 0.0

        mean_interval = sum(positive) / float(len(positive))
        fps = 1000.0 / mean_interval if mean_interval > 0 else 0.0
        if len(positive) == 1:
            stability = 1.0
        else:
            stability = 1.0 - (pstdev(positive) / max(mean_interval, 1e-6))
        return round(max(0.0, fps), 6), round(clamp01(stability), 6)

    def update(
        self,
        *,
        t_ms: int,
        blink: int,
        face_visible: bool,
        head_pose_valid: bool,
    ) -> RollingSignalSnapshot:
        """Update tracker state and return latest rolling metrics."""

        blink_int = 1 if int(blink) > 0 else 0
        sample = {
            "t_ms": int(t_ms),
            "blink": blink_int,
            "face_visible": 1 if face_visible else 0,
            "head_pose_valid": 1 if head_pose_valid else 0,
        }
        self._samples.append(sample)
        self._prune_samples(int(t_ms))

        if int(t_ms) <= self.baseline_window_ms and face_visible:
            self._baseline_samples.append(sample)

        sample_count = len(self._samples)
        if sample_count == 0:
            return {
                "rolling_blink_rate": 0.0,
                "blink_baseline_rate": 0.0,
                "blink_inhibition_score": 0.0,
                "blink_inhibition_active": False,
                "face_visible_pct": 0.0,
                "head_pose_valid_pct": 0.0,
                "fps": 0.0,
                "fps_stability": 0.0,
                "window_confidence": 0.0,
            }

        face_visible_pct = sum(s["face_visible"] for s in self._samples) / float(sample_count)
        head_pose_valid_pct = sum(s["head_pose_valid"] for s in self._samples) / float(sample_count)
        rolling_blink_rate = self._blink_rate(self._samples)

        if len(self._baseline_samples) >= 2:
            blink_baseline_rate = self._blink_rate(self._baseline_samples)
        else:
            blink_baseline_rate = rolling_blink_rate

        if blink_baseline_rate <= 1e-6:
            blink_inhibition_score = 0.0
            blink_inhibition_active = False
        else:
            raw_score = (blink_baseline_rate - rolling_blink_rate) / blink_baseline_rate
            blink_inhibition_score = max(-1.0, min(1.0, raw_score))
            blink_inhibition_active = (
                blink_baseline_rate >= 0.05 and blink_inhibition_score >= self.inhibition_threshold
            )

        fps, fps_stability = self._fps_metrics()
        window_confidence = clamp01(
            (0.45 * face_visible_pct) + (0.35 * head_pose_valid_pct) + (0.20 * fps_stability)
        )

        return {
            "rolling_blink_rate": round(rolling_blink_rate, 6),
            "blink_baseline_rate": round(blink_baseline_rate, 6),
            "blink_inhibition_score": round(blink_inhibition_score, 6),
            "blink_inhibition_active": blink_inhibition_active,
            "face_visible_pct": round(face_visible_pct, 6),
            "head_pose_valid_pct": round(head_pose_valid_pct, 6),
            "fps": fps,
            "fps_stability": fps_stability,
            "window_confidence": round(window_confidence, 6),
        }
