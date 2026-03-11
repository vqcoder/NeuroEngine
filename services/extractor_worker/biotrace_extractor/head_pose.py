"""Approximate head pose estimation from 2D facial landmarks."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from .geometry import Point
from .schemas import HeadPose


def _head_pose_unavailable() -> HeadPose:
    return {"yaw": None, "pitch": None, "roll": None}


def estimate_head_pose(landmarks: Sequence[Point], frame_shape: Tuple[int, int, int]) -> HeadPose:
    """Estimate yaw/pitch/roll using solvePnP and a sparse facial model.

    Returns None-valued angles when estimation fails.
    """

    try:
        import cv2
        import numpy as np
    except ImportError:
        return _head_pose_unavailable()

    required = (1, 33, 61, 152, 263, 291)
    if len(landmarks) <= max(required):
        return _head_pose_unavailable()

    image_points = np.array(
        [
            landmarks[1],   # nose tip
            landmarks[152], # chin
            landmarks[33],  # left eye outer
            landmarks[263], # right eye outer
            landmarks[61],  # left mouth corner
            landmarks[291], # right mouth corner
        ],
        dtype=np.float64,
    )

    model_points = np.array(
        [
            (0.0, 0.0, 0.0),
            (0.0, -330.0, -65.0),
            (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0),
            (-150.0, -150.0, -125.0),
            (150.0, -150.0, -125.0),
        ],
        dtype=np.float64,
    )

    frame_h, frame_w = frame_shape[:2]
    focal_length = float(frame_w)
    camera_center = (frame_w / 2.0, frame_h / 2.0)
    camera_matrix = np.array(
        [
            [focal_length, 0.0, camera_center[0]],
            [0.0, focal_length, camera_center[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    success, rotation_vector, _ = cv2.solvePnP(
        model_points,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )

    if not success:
        return _head_pose_unavailable()

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    angles, *_ = cv2.RQDecomp3x3(rotation_matrix)

    pitch = float(angles[0])
    yaw = float(angles[1])
    roll = float(angles[2])

    return {
        "yaw": round(yaw, 6),
        "pitch": round(pitch, 6),
        "roll": round(roll, 6),
    }
