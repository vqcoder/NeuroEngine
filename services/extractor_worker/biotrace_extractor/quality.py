"""Heuristic passive-signal quality and confidence helpers.

These helpers intentionally expose *proxy* metrics suitable for laptop webcams.
They do not represent precise eye tracking or research-grade gaze coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from .blink import LEFT_EYE_IDX, RIGHT_EYE_IDX
from .geometry import Point, clamp01, eye_aspect_ratio
from .quality_thresholds import get_extractor_quality_thresholds
from .schemas import HeadPose


@dataclass(frozen=True)
class FaceFrameGeometry:
    """Geometry-derived frame descriptors used by quality proxies."""

    area_ratio: float
    center_offset: float
    border_touch_ratio: float
    landmark_ratio: float
    eye_asymmetry: float


def compute_blur_proxy(frame_bgr) -> float:
    """Estimate image sharpness via Laplacian variance.

    Higher values indicate sharper images.
    """

    try:
        import cv2
    except ImportError:
        return 0.0

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return round(max(0.0, variance), 6)


def brightness_quality_score(brightness: float) -> float:
    """Map brightness to a [0, 1] quality score."""

    return round(clamp01(1.0 - abs(float(brightness) - 115.0) / 120.0), 6)


def blur_quality_score(blur_proxy: float) -> float:
    """Map blur proxy to a [0, 1] quality score."""

    return round(clamp01(float(blur_proxy) / 220.0), 6)


def _select_eye(landmarks: Sequence[Point], indices: Sequence[int]) -> Optional[Sequence[Point]]:
    if len(landmarks) <= max(indices):
        return None
    return [landmarks[index] for index in indices]


def _eye_asymmetry(landmarks: Sequence[Point]) -> float:
    left_eye = _select_eye(landmarks, LEFT_EYE_IDX)
    right_eye = _select_eye(landmarks, RIGHT_EYE_IDX)
    if left_eye is None or right_eye is None:
        return 1.0

    left_ear = eye_aspect_ratio(left_eye)
    right_ear = eye_aspect_ratio(right_eye)
    maximum = max(left_ear, right_ear, 1e-6)
    relative_diff = abs(left_ear - right_ear) / maximum
    return clamp01(relative_diff / 0.5)


def compute_face_frame_geometry(
    landmarks: Optional[Sequence[Point]],
    frame_shape: Tuple[int, int, int],
) -> FaceFrameGeometry:
    """Compute face-box geometry descriptors from landmarks."""

    frame_h, frame_w = frame_shape[:2]
    if not landmarks or frame_h <= 0 or frame_w <= 0:
        return FaceFrameGeometry(
            area_ratio=0.0,
            center_offset=1.0,
            border_touch_ratio=1.0,
            landmark_ratio=0.0,
            eye_asymmetry=1.0,
        )

    xs = [point[0] for point in landmarks]
    ys = [point[1] for point in landmarks]

    min_x = max(0.0, min(xs))
    max_x = min(float(frame_w), max(xs))
    min_y = max(0.0, min(ys))
    max_y = min(float(frame_h), max(ys))

    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    area_ratio = clamp01((width * height) / float(frame_w * frame_h))

    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    dx = abs(center_x - (frame_w / 2.0)) / max(frame_w / 2.0, 1.0)
    dy = abs(center_y - (frame_h / 2.0)) / max(frame_h / 2.0, 1.0)
    center_offset = clamp01((dx + dy) / 2.0)

    border_margin_x = frame_w * 0.03
    border_margin_y = frame_h * 0.03
    touches = 0
    if min_x <= border_margin_x:
        touches += 1
    if max_x >= frame_w - border_margin_x:
        touches += 1
    if min_y <= border_margin_y:
        touches += 1
    if max_y >= frame_h - border_margin_y:
        touches += 1
    border_touch_ratio = touches / 4.0

    landmark_ratio = clamp01(len(landmarks) / 468.0)
    eye_asymmetry = _eye_asymmetry(landmarks)

    return FaceFrameGeometry(
        area_ratio=round(area_ratio, 6),
        center_offset=round(center_offset, 6),
        border_touch_ratio=round(border_touch_ratio, 6),
        landmark_ratio=round(landmark_ratio, 6),
        eye_asymmetry=round(eye_asymmetry, 6),
    )


def estimate_face_presence_confidence(geometry: FaceFrameGeometry) -> float:
    """Estimate confidence that a usable face is visible."""

    coverage = clamp01(geometry.area_ratio / 0.18)
    centering = clamp01(1.0 - geometry.center_offset)
    completeness = geometry.landmark_ratio

    confidence = (
        (0.45 * coverage)
        + (0.35 * centering)
        + (0.20 * completeness)
        - (0.15 * geometry.border_touch_ratio)
    )
    return round(clamp01(confidence), 6)


def estimate_occlusion_score(
    geometry: FaceFrameGeometry,
    eye_openness: Optional[float],
) -> float:
    """Estimate coarse occlusion severity in [0, 1]."""

    small_face_penalty = clamp01((0.06 - geometry.area_ratio) / 0.06)
    eye_penalty = 0.0 if eye_openness is None else clamp01((0.2 - eye_openness) / 0.2)

    score = (
        (0.45 * geometry.border_touch_ratio)
        + (0.30 * small_face_penalty)
        + (0.20 * geometry.eye_asymmetry)
        + (0.05 * eye_penalty)
    )
    return round(clamp01(score), 6)


def eye_openness_from_ear(ear_value: Optional[float]) -> Optional[float]:
    """Map EAR to a [0, 1] eye-openness proxy."""

    if ear_value is None:
        return None
    return round(clamp01((float(ear_value) - 0.14) / 0.18), 6)


def estimate_gaze_on_screen_proxy(
    head_pose: HeadPose,
    center_offset: float,
    eye_openness: Optional[float],
    face_presence_confidence: float,
) -> Tuple[Optional[float], float]:
    """Estimate coarse gaze-on-screen probability and confidence."""

    if face_presence_confidence <= 0.0:
        return None, 0.0

    yaw = head_pose.get("yaw")
    pitch = head_pose.get("pitch")
    roll = head_pose.get("roll")

    has_head_pose = yaw is not None and pitch is not None and roll is not None
    if has_head_pose:
        yaw_score = clamp01(1.0 - abs(float(yaw)) / 30.0)
        pitch_score = clamp01(1.0 - abs(float(pitch)) / 22.0)
        head_pose_factor = 1.0
    else:
        yaw_score = 0.5
        pitch_score = 0.5
        head_pose_factor = 0.45

    centered_score = clamp01(1.0 - float(center_offset))
    openness_score = 0.5 if eye_openness is None else clamp01(float(eye_openness))

    probability = face_presence_confidence * (
        (0.40 * yaw_score)
        + (0.25 * pitch_score)
        + (0.20 * centered_score)
        + (0.15 * openness_score)
    )
    confidence = face_presence_confidence * (
        (0.50 * head_pose_factor)
        + (0.30 * centered_score)
        + 0.20
    )

    return round(clamp01(probability), 6), round(clamp01(confidence), 6)


def estimate_head_pose_confidence(
    head_pose: HeadPose,
    face_presence_confidence: float,
) -> float:
    """Estimate confidence for yaw/pitch/roll validity."""

    yaw = head_pose.get("yaw")
    pitch = head_pose.get("pitch")
    roll = head_pose.get("roll")
    if yaw is None or pitch is None or roll is None:
        return 0.0

    range_score = 1.0 - max(
        abs(float(yaw)) / 65.0,
        abs(float(pitch)) / 50.0,
        abs(float(roll)) / 60.0,
    )
    confidence = face_presence_confidence * clamp01(range_score)
    return round(clamp01(confidence), 6)


def compose_quality_score(
    *,
    brightness: float,
    blur: float,
    fps_stability: float,
    face_visible_pct: float,
    occlusion_score: float,
    head_pose_valid_pct: float,
) -> float:
    """Compose per-frame/per-window quality score in [0, 1]."""

    brightness_quality = brightness_quality_score(brightness)
    score = (
        (0.22 * brightness_quality)
        + (0.20 * blur_quality_score(blur))
        + (0.20 * clamp01(fps_stability))
        + (0.18 * clamp01(face_visible_pct))
        + (0.12 * (1.0 - clamp01(occlusion_score)))
        + (0.08 * clamp01(head_pose_valid_pct))
    )
    # Low-light footage can still appear "stable" on other dimensions; apply
    # a brightness gate so poor lighting is reflected in total quality.
    brightness_gate = 0.35 + (0.65 * brightness_quality)
    return round(clamp01(score * brightness_gate), 6)


def compose_quality_confidence(
    *,
    face_presence_confidence: float,
    landmarks_confidence: float,
    window_confidence: float,
) -> float:
    """Estimate confidence for quality outputs."""

    confidence = (
        (0.45 * clamp01(face_presence_confidence))
        + (0.35 * clamp01(landmarks_confidence))
        + (0.20 * clamp01(window_confidence))
    )
    return round(clamp01(confidence), 6)


def compose_tracking_confidence(
    *,
    quality_confidence: float,
    face_presence_confidence: float,
    landmarks_confidence: float,
    head_pose_confidence: float,
    gaze_on_screen_confidence: float,
    au_confidence: float,
) -> float:
    """Compose per-sample tracking confidence in [0, 1]."""

    confidence = (
        (0.26 * clamp01(quality_confidence))
        + (0.20 * clamp01(face_presence_confidence))
        + (0.18 * clamp01(landmarks_confidence))
        + (0.14 * clamp01(head_pose_confidence))
        + (0.12 * clamp01(gaze_on_screen_confidence))
        + (0.10 * clamp01(au_confidence))
    )
    return round(clamp01(confidence), 6)


def derive_quality_flags(
    *,
    brightness: float,
    blur: float,
    face_visible_pct: float,
    head_pose_valid_pct: float,
) -> Sequence[str]:
    """Return quality flags for threshold-based diagnostics."""

    thresholds = get_extractor_quality_thresholds()
    flags: list[str] = []
    if brightness < thresholds.low_light_max_brightness:
        flags.append("low_light")
    if blur_quality_score(blur) < thresholds.blur_min_quality_score:
        flags.append("blur")
    if face_visible_pct < thresholds.face_visible_pct_min:
        flags.append("face_lost")
    if head_pose_valid_pct < thresholds.head_pose_valid_pct_min:
        flags.append("high_yaw_pitch")
    return sorted(set(flags))
