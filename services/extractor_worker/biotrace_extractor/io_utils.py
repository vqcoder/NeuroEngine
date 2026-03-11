"""I/O helpers for session loading and JSONL writing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def load_events(session_dir: Path) -> Dict[str, Any]:
    """Load and validate `events.json` from session directory."""

    events_path = session_dir / "events.json"
    if not events_path.exists():
        raise FileNotFoundError(f"events.json not found at: {events_path}")

    with events_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("events.json must contain a top-level JSON object")

    return payload


def _natural_key(path: Path) -> List[Any]:
    chunks = re.split(r"(\d+)", path.name)
    key: List[Any] = []
    for chunk in chunks:
        if chunk.isdigit():
            key.append(int(chunk))
        else:
            key.append(chunk.lower())
    return key


def list_frame_paths(session_dir: Path) -> List[Path]:
    """Return sorted JPEG frame paths from `<session_dir>/frames`."""

    frames_dir = session_dir / "frames"
    if not frames_dir.exists():
        raise FileNotFoundError(f"frames directory not found at: {frames_dir}")

    patterns = ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG")
    frames: List[Path] = []
    for pattern in patterns:
        frames.extend(frames_dir.glob(pattern))

    frames = sorted(frames, key=_natural_key)
    if not frames:
        raise FileNotFoundError(f"No JPEG frames found in: {frames_dir}")

    return frames


def _timestamps_from_frame_list(frame_paths: Sequence[Path], events: Dict[str, Any]) -> List[int]:
    frames = events.get("frames")
    if not isinstance(frames, list):
        return []

    by_file: Dict[str, int] = {}
    for item in frames:
        if not isinstance(item, dict):
            continue
        file_name = item.get("file")
        t_ms = item.get("t_ms")
        if isinstance(file_name, str) and isinstance(t_ms, (int, float)):
            by_file[file_name] = int(t_ms)

    if not by_file:
        return []

    timestamps: List[int] = []
    for frame_path in frame_paths:
        if frame_path.name not in by_file:
            return []
        timestamps.append(by_file[frame_path.name])

    return timestamps


def _timestamps_from_filename(frame_paths: Sequence[Path]) -> List[int]:
    timestamps: List[int] = []
    for frame_path in frame_paths:
        match = re.search(r"(\d+)", frame_path.stem)
        if match is None:
            return []
        timestamps.append(int(match.group(1)))
    return timestamps


def resolve_frame_timestamps(frame_paths: Sequence[Path], events: Dict[str, Any]) -> List[int]:
    """Resolve per-frame timestamps in ms from metadata or filename."""

    explicit = events.get("frame_timestamps_ms")
    if isinstance(explicit, list) and len(explicit) >= len(frame_paths):
        numeric = [int(float(value)) for value in explicit[: len(frame_paths)]]
        return numeric

    from_frames = _timestamps_from_frame_list(frame_paths, events)
    if from_frames:
        return from_frames

    fps = events.get("fps")
    if isinstance(fps, (int, float)) and fps > 0:
        frame_interval_ms = 1000.0 / float(fps)
        return [int(round(index * frame_interval_ms)) for index, _ in enumerate(frame_paths)]

    from_name = _timestamps_from_filename(frame_paths)
    if from_name:
        return from_name

    default_interval_ms = 100
    return [index * default_interval_ms for index, _ in enumerate(frame_paths)]


def write_jsonl(rows: Iterable[Dict[str, Any]], output_path: Path) -> None:
    """Write iterable of dict rows as JSON Lines."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
