"""Core session extraction pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from .au_proxy import estimate_au_proxies
from .baseline import apply_baseline_correction, compute_au_baseline
from .blink import BlinkDetector, compute_eye_aspect_ratio
from .facemesh import FaceMeshProcessor
from .geometry import clamp01
from .head_pose import estimate_head_pose
from .io_utils import list_frame_paths, load_events, resolve_frame_timestamps
from .quality import (
    blur_quality_score,
    compose_quality_confidence,
    compose_quality_score,
    compose_tracking_confidence,
    compute_blur_proxy,
    compute_face_frame_geometry,
    derive_quality_flags,
    estimate_face_presence_confidence,
    estimate_gaze_on_screen_proxy,
    estimate_head_pose_confidence,
    estimate_occlusion_score,
    eye_openness_from_ear,
)
from .rolling import RollingSignalTracker
from .schemas import ExtractorConfig, OutputRow, zero_aus

logger = logging.getLogger(__name__)


def _compute_brightness(frame_bgr) -> float:
    """Compute mean grayscale brightness in [0, 255]."""

    import cv2

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    mean_brightness = cv2.mean(gray)[0]
    return round(float(mean_brightness), 6)


class SessionExtractor:
    """Extract frame-level biometric traces for a single session directory."""

    def __init__(self, config: Optional[ExtractorConfig] = None) -> None:
        self.config = config or ExtractorConfig()

    def extract(self, session_dir: Path) -> List[OutputRow]:
        """Run extraction pipeline and return output rows."""

        import cv2

        events = load_events(session_dir)
        frame_paths = list_frame_paths(session_dir)
        timestamps = resolve_frame_timestamps(frame_paths, events)
        fps_hint = events.get("fps")
        fallback_fps = (
            float(fps_hint) if isinstance(fps_hint, (int, float)) and fps_hint > 0 else 0.0
        )

        blink_detector = BlinkDetector(
            threshold=self.config.blink_threshold,
            min_closed_frames=self.config.blink_min_closed_frames,
        )
        rolling_tracker = RollingSignalTracker(
            window_ms=self.config.rolling_window_ms,
            baseline_window_ms=self.config.baseline_window_ms,
            inhibition_threshold=self.config.blink_inhibition_threshold,
        )
        rows: List[OutputRow] = []

        with FaceMeshProcessor() as facemesh:
            for frame_path, t_ms in zip(frame_paths, timestamps):
                frame = cv2.imread(str(frame_path))
                if frame is None:
                    logger.warning("Skipping unreadable frame: %s", frame_path)
                    continue

                brightness = _compute_brightness(frame)
                blur = compute_blur_proxy(frame)
                landmarks = facemesh.process(frame)

                if landmarks is None:
                    blink = blink_detector.update(None)
                    au = zero_aus()
                    au["AU45"] = float(blink)
                    rolling = rolling_tracker.update(
                        t_ms=int(t_ms),
                        blink=blink,
                        face_visible=False,
                        head_pose_valid=False,
                    )
                    fps_value = rolling["fps"] if rolling["fps"] > 0 else fallback_fps
                    fps_stability = (
                        rolling["fps_stability"]
                        if rolling["fps"] > 0
                        else (1.0 if fallback_fps > 0 else 0.0)
                    )
                    quality_score = compose_quality_score(
                        brightness=brightness,
                        blur=blur,
                        fps_stability=fps_stability,
                        face_visible_pct=rolling["face_visible_pct"],
                        occlusion_score=1.0,
                        head_pose_valid_pct=rolling["head_pose_valid_pct"],
                    )
                    quality_confidence = compose_quality_confidence(
                        face_presence_confidence=0.0,
                        landmarks_confidence=0.0,
                        window_confidence=rolling["window_confidence"],
                    )
                    tracking_confidence = compose_tracking_confidence(
                        quality_confidence=quality_confidence,
                        face_presence_confidence=0.0,
                        landmarks_confidence=0.0,
                        head_pose_confidence=0.0,
                        gaze_on_screen_confidence=0.0,
                        au_confidence=0.0,
                    )
                    quality_flags = derive_quality_flags(
                        brightness=brightness,
                        blur=blur,
                        face_visible_pct=rolling["face_visible_pct"],
                        head_pose_valid_pct=rolling["head_pose_valid_pct"],
                    )
                    row: OutputRow = {
                        "t_ms": int(t_ms),
                        "video_time_ms": int(t_ms),
                        "face_ok": False,
                        "brightness": brightness,
                        "landmarks_ok": False,
                        "blink": blink,
                        "face_presence_confidence": 0.0,
                        "landmarks_confidence": 0.0,
                        "blink_confidence": 0.0,
                        "head_pose_confidence": 0.0,
                        "au_confidence": 0.0,
                        "eye_openness": None,
                        "rolling_blink_rate": rolling["rolling_blink_rate"],
                        "blink_baseline_rate": rolling["blink_baseline_rate"],
                        "blink_inhibition_score": rolling["blink_inhibition_score"],
                        "blink_inhibition_active": rolling["blink_inhibition_active"],
                        "gaze_on_screen_proxy": None,
                        "gaze_on_screen_confidence": 0.0,
                        "blur": blur,
                        "fps": round(fps_value, 6),
                        "fps_stability": round(fps_stability, 6),
                        "face_visible_pct": rolling["face_visible_pct"],
                        "occlusion_score": 1.0,
                        "head_pose_valid_pct": rolling["head_pose_valid_pct"],
                        "quality_score": quality_score,
                        "quality_confidence": quality_confidence,
                        "tracking_confidence": tracking_confidence,
                        "quality_flags": quality_flags,
                        "au": au,
                        "au_norm": zero_aus(),
                        "head_pose": {"yaw": None, "pitch": None, "roll": None},
                    }
                    rows.append(row)
                    continue

                ear_value = compute_eye_aspect_ratio(landmarks)
                eye_openness = eye_openness_from_ear(ear_value)
                blink = blink_detector.update(ear_value)
                au = estimate_au_proxies(landmarks, blink)
                head_pose = estimate_head_pose(landmarks, frame.shape)
                head_pose_valid = (
                    head_pose["yaw"] is not None
                    and head_pose["pitch"] is not None
                    and head_pose["roll"] is not None
                )

                geometry = compute_face_frame_geometry(landmarks, frame.shape)
                face_presence_confidence = estimate_face_presence_confidence(geometry)
                occlusion_score = estimate_occlusion_score(geometry, eye_openness)
                landmarks_confidence = clamp01(face_presence_confidence * (1.0 - occlusion_score))
                head_pose_confidence = estimate_head_pose_confidence(
                    head_pose,
                    face_presence_confidence,
                )
                blink_confidence = (
                    round(
                        clamp01(
                            landmarks_confidence
                            * (0.55 + (0.45 * blur_quality_score(blur)))
                        ),
                        6,
                    )
                    if ear_value is not None
                    else 0.0
                )
                au_confidence = round(clamp01(landmarks_confidence * blur_quality_score(blur)), 6)
                gaze_on_screen_proxy, gaze_on_screen_confidence = estimate_gaze_on_screen_proxy(
                    head_pose=head_pose,
                    center_offset=geometry.center_offset,
                    eye_openness=eye_openness,
                    face_presence_confidence=face_presence_confidence,
                )

                rolling = rolling_tracker.update(
                    t_ms=int(t_ms),
                    blink=blink,
                    face_visible=face_presence_confidence > 0.2,
                    head_pose_valid=head_pose_valid,
                )
                fps_value = rolling["fps"] if rolling["fps"] > 0 else fallback_fps
                fps_stability = (
                    rolling["fps_stability"]
                    if rolling["fps"] > 0
                    else (1.0 if fallback_fps > 0 else 0.0)
                )
                quality_score = compose_quality_score(
                    brightness=brightness,
                    blur=blur,
                    fps_stability=fps_stability,
                    face_visible_pct=rolling["face_visible_pct"],
                    occlusion_score=occlusion_score,
                    head_pose_valid_pct=rolling["head_pose_valid_pct"],
                )
                quality_confidence = compose_quality_confidence(
                    face_presence_confidence=face_presence_confidence,
                    landmarks_confidence=landmarks_confidence,
                    window_confidence=rolling["window_confidence"],
                )
                tracking_confidence = compose_tracking_confidence(
                    quality_confidence=quality_confidence,
                    face_presence_confidence=face_presence_confidence,
                    landmarks_confidence=landmarks_confidence,
                    head_pose_confidence=head_pose_confidence,
                    gaze_on_screen_confidence=gaze_on_screen_confidence,
                    au_confidence=au_confidence,
                )
                quality_flags = derive_quality_flags(
                    brightness=brightness,
                    blur=blur,
                    face_visible_pct=rolling["face_visible_pct"],
                    head_pose_valid_pct=rolling["head_pose_valid_pct"],
                )

                row = {
                    "t_ms": int(t_ms),
                    "video_time_ms": int(t_ms),
                    "face_ok": face_presence_confidence > 0.2,
                    "brightness": brightness,
                    "landmarks_ok": ear_value is not None,
                    "blink": blink,
                    "face_presence_confidence": round(face_presence_confidence, 6),
                    "landmarks_confidence": round(landmarks_confidence, 6),
                    "blink_confidence": blink_confidence,
                    "head_pose_confidence": head_pose_confidence,
                    "au_confidence": au_confidence,
                    "eye_openness": eye_openness,
                    "rolling_blink_rate": rolling["rolling_blink_rate"],
                    "blink_baseline_rate": rolling["blink_baseline_rate"],
                    "blink_inhibition_score": rolling["blink_inhibition_score"],
                    "blink_inhibition_active": rolling["blink_inhibition_active"],
                    "gaze_on_screen_proxy": gaze_on_screen_proxy,
                    "gaze_on_screen_confidence": gaze_on_screen_confidence,
                    "blur": blur,
                    "fps": round(fps_value, 6),
                    "fps_stability": round(fps_stability, 6),
                    "face_visible_pct": rolling["face_visible_pct"],
                    "occlusion_score": occlusion_score,
                    "head_pose_valid_pct": rolling["head_pose_valid_pct"],
                    "quality_score": quality_score,
                    "quality_confidence": quality_confidence,
                    "tracking_confidence": tracking_confidence,
                    "quality_flags": quality_flags,
                    "au": au,
                    "au_norm": zero_aus(),
                    "head_pose": head_pose,
                }
                rows.append(row)

        mutable_rows = [dict(row) for row in rows]
        baseline = compute_au_baseline(
            mutable_rows,
            baseline_window_ms=self.config.baseline_window_ms,
        )
        apply_baseline_correction(mutable_rows, baseline)

        return mutable_rows  # type: ignore[return-value]


def extract_session(
    session_dir: Path, config: Optional[ExtractorConfig] = None
) -> List[OutputRow]:
    """Functional wrapper around `SessionExtractor`."""

    return SessionExtractor(config=config).extract(session_dir)
