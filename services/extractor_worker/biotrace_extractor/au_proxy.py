"""Heuristic proxy estimators for facial Action Units (AUs)."""

from __future__ import annotations

from typing import Dict, Sequence

from .geometry import Point, clamp01, distance, safe_ratio
from .schemas import zero_aus

# Landmark indices (MediaPipe FaceMesh):
# https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_mesh/face_mesh_connections.py
IDX_LEFT_BROW = 70
IDX_RIGHT_BROW = 300
IDX_LEFT_EYE_UP = 159
IDX_LEFT_EYE_DOWN = 145
IDX_RIGHT_EYE_UP = 386
IDX_RIGHT_EYE_DOWN = 374
IDX_LEFT_EYE_OUTER = 33
IDX_RIGHT_EYE_OUTER = 263
IDX_LEFT_MOUTH_CORNER = 61
IDX_RIGHT_MOUTH_CORNER = 291
IDX_UPPER_INNER_LIP = 13
IDX_LOWER_INNER_LIP = 14
IDX_CHIN = 152
IDX_FACE_LEFT = 234
IDX_FACE_RIGHT = 454
IDX_FOREHEAD = 10


def _has_indices(landmarks: Sequence[Point], required_indices: Sequence[int]) -> bool:
    return len(landmarks) > max(required_indices)


def estimate_au_proxies(landmarks: Sequence[Point], blink_prob: int) -> Dict[str, float]:
    """Return heuristic AU proxies in the range [0, 1].

    AU mapping (MVP proxies):
    - AU04: brow lowerer proxy from brow-eye distance
    - AU06: cheek raise proxy from eye aperture reduction
    - AU12: lip corner puller proxy from mouth width
    - AU25: lips part proxy from inner lip distance
    - AU26: jaw drop proxy from lower-lip to chin distance
    - AU45: blink proxy (0/1)
    """

    required = (
        IDX_LEFT_BROW,
        IDX_RIGHT_BROW,
        IDX_LEFT_EYE_UP,
        IDX_LEFT_EYE_DOWN,
        IDX_RIGHT_EYE_UP,
        IDX_RIGHT_EYE_DOWN,
        IDX_LEFT_EYE_OUTER,
        IDX_RIGHT_EYE_OUTER,
        IDX_LEFT_MOUTH_CORNER,
        IDX_RIGHT_MOUTH_CORNER,
        IDX_UPPER_INNER_LIP,
        IDX_LOWER_INNER_LIP,
        IDX_CHIN,
        IDX_FACE_LEFT,
        IDX_FACE_RIGHT,
        IDX_FOREHEAD,
    )
    if not _has_indices(landmarks, required):
        aus = zero_aus()
        aus["AU45"] = float(blink_prob)
        return aus

    face_width = distance(landmarks[IDX_FACE_LEFT], landmarks[IDX_FACE_RIGHT])
    face_height = distance(landmarks[IDX_FOREHEAD], landmarks[IDX_CHIN])
    if face_width < 1e-6 or face_height < 1e-6:
        aus = zero_aus()
        aus["AU45"] = float(blink_prob)
        return aus

    brow_eye_left = safe_ratio(
        distance(landmarks[IDX_LEFT_BROW], landmarks[IDX_LEFT_EYE_UP]), face_height
    )
    brow_eye_right = safe_ratio(
        distance(landmarks[IDX_RIGHT_BROW], landmarks[IDX_RIGHT_EYE_UP]), face_height
    )
    brow_eye_avg = (brow_eye_left + brow_eye_right) / 2.0

    eye_aperture_left = safe_ratio(
        distance(landmarks[IDX_LEFT_EYE_UP], landmarks[IDX_LEFT_EYE_DOWN]), face_height
    )
    eye_aperture_right = safe_ratio(
        distance(landmarks[IDX_RIGHT_EYE_UP], landmarks[IDX_RIGHT_EYE_DOWN]), face_height
    )
    eye_aperture_avg = (eye_aperture_left + eye_aperture_right) / 2.0

    mouth_width = safe_ratio(
        distance(landmarks[IDX_LEFT_MOUTH_CORNER], landmarks[IDX_RIGHT_MOUTH_CORNER]), face_width
    )
    lip_open = safe_ratio(
        distance(landmarks[IDX_UPPER_INNER_LIP], landmarks[IDX_LOWER_INNER_LIP]), face_height
    )
    jaw_drop = safe_ratio(distance(landmarks[IDX_LOWER_INNER_LIP], landmarks[IDX_CHIN]), face_height)

    # Piecewise-linear heuristic maps tuned to keep values stable in [0, 1].
    au04 = clamp01((0.090 - brow_eye_avg) / 0.050)
    au06 = clamp01((0.080 - eye_aperture_avg) / 0.040)
    au12 = clamp01((mouth_width - 0.320) / 0.180)
    au25 = clamp01((lip_open - 0.015) / 0.120)
    au26 = clamp01((jaw_drop - 0.220) / 0.260)

    return {
        "AU04": round(au04, 6),
        "AU06": round(au06, 6),
        "AU12": round(au12, 6),
        "AU45": float(blink_prob),
        "AU25": round(au25, 6),
        "AU26": round(au26, 6),
    }
