"""Typed schemas and shared constants used by the extractor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence, TypedDict

AU_KEYS: Sequence[str] = ("AU04", "AU06", "AU12", "AU45", "AU25", "AU26")


class HeadPose(TypedDict):
    """Approximate head pose angles in degrees."""

    yaw: Optional[float]
    pitch: Optional[float]
    roll: Optional[float]


class OutputRow(TypedDict):
    """Per-frame output row written to JSONL."""

    t_ms: int
    video_time_ms: int
    face_ok: bool
    brightness: float
    landmarks_ok: bool
    blink: int
    face_presence_confidence: float
    landmarks_confidence: float
    blink_confidence: float
    head_pose_confidence: float
    au_confidence: float
    eye_openness: Optional[float]
    rolling_blink_rate: float
    blink_baseline_rate: float
    blink_inhibition_score: float
    blink_inhibition_active: bool
    gaze_on_screen_proxy: Optional[float]
    gaze_on_screen_confidence: float
    blur: float
    fps: float
    fps_stability: float
    face_visible_pct: float
    occlusion_score: float
    head_pose_valid_pct: float
    quality_score: float
    quality_confidence: float
    tracking_confidence: float
    quality_flags: Sequence[str]
    au: Dict[str, float]
    au_norm: Dict[str, float]
    head_pose: HeadPose


@dataclass(frozen=True)
class ExtractorConfig:
    """Runtime configuration for extraction."""

    baseline_window_ms: int = 10_000
    blink_threshold: float = 0.21
    blink_min_closed_frames: int = 2
    rolling_window_ms: int = 10_000
    blink_inhibition_threshold: float = 0.35


def zero_aus() -> Dict[str, float]:
    """Return a new AU dictionary initialized to zeros."""

    return {key: 0.0 for key in AU_KEYS}
