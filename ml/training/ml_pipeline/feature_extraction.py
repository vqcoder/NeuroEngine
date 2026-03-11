"""Video/audio feature extraction for per-second model inputs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
import pandas as pd


def _safe_ffmpeg_audio_rms(video_path: Path, sample_rate: int = 16_000) -> Dict[int, float]:
    """Extract mono PCM via ffmpeg and compute per-second RMS."""

    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]

    try:
        result = subprocess.run(command, capture_output=True, check=True)
    except Exception:
        return {}

    audio = np.frombuffer(result.stdout, dtype=np.float32)
    if audio.size == 0:
        return {}

    rms_by_second: Dict[int, float] = {}
    total_seconds = int(np.ceil(audio.size / sample_rate))

    for second in range(total_seconds):
        start = second * sample_rate
        end = min((second + 1) * sample_rate, audio.size)
        chunk = audio[start:end]
        if chunk.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        rms_by_second[second] = rms

    return rms_by_second


def extract_video_features(video_path: Path) -> pd.DataFrame:
    """Compute per-second video + audio features.

    Output columns:
    - second
    - shot_change_rate
    - brightness
    - motion_magnitude
    - audio_rms
    """

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        fps = 30.0

    brightness_acc: Dict[int, List[float]] = {}
    motion_acc: Dict[int, List[float]] = {}
    shot_changes: Dict[int, int] = {}
    frame_counts: Dict[int, int] = {}

    previous_gray = None
    previous_hist = None
    frame_index = 0

    while True:
        ok, frame = capture.read()
        if not ok:
            break

        second = int(frame_index / fps)
        frame_counts[second] = frame_counts.get(second, 0) + 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_acc.setdefault(second, []).append(float(np.mean(gray)))

        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        if previous_gray is not None:
            motion = float(np.mean(cv2.absdiff(gray, previous_gray)))
            motion_acc.setdefault(second, []).append(motion)

        if previous_hist is not None:
            hist_distance = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
            if hist_distance > 0.45:
                shot_changes[second] = shot_changes.get(second, 0) + 1

        previous_gray = gray
        previous_hist = hist
        frame_index += 1

    capture.release()

    audio_rms = _safe_ffmpeg_audio_rms(video_path)
    max_second = max(
        [-1] + list(frame_counts.keys()) + list(audio_rms.keys())
    )

    rows = []
    for second in range(max_second + 1):
        count = frame_counts.get(second, 0)
        shot_change_rate = float(shot_changes.get(second, 0) / count) if count > 0 else 0.0
        rows.append(
            {
                "second": second,
                "shot_change_rate": shot_change_rate,
                "brightness": float(np.mean(brightness_acc.get(second, [0.0]))),
                "motion_magnitude": float(np.mean(motion_acc.get(second, [0.0]))),
                "audio_rms": float(audio_rms.get(second, 0.0)),
            }
        )

    return pd.DataFrame(rows)
