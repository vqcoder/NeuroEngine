"""Create a small synthetic sample session directory for manual CLI checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create synthetic sample session data")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--fps", type=float, default=10.0)
    args = parser.parse_args()

    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            "opencv-python and numpy are required to generate sample session data"
        ) from exc

    session_dir = args.output_dir
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_timestamps_ms = []
    for index in range(args.frames):
        timestamp_ms = int(round(index * (1000.0 / args.fps)))
        frame_timestamps_ms.append(timestamp_ms)

        frame = np.full((240, 320, 3), 30 + index * 2, dtype=np.uint8)
        cv2.putText(
            frame,
            f"t={timestamp_ms}ms",
            (30, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )
        frame_path = frames_dir / f"frame_{index:04d}.jpg"
        cv2.imwrite(str(frame_path), frame)

    events = {
        "fps": args.fps,
        "frame_timestamps_ms": frame_timestamps_ms,
        "events": [
            {"type": "session_started", "t_ms": 0},
            {"type": "session_finished", "t_ms": frame_timestamps_ms[-1] if frame_timestamps_ms else 0},
        ],
    }

    events_path = session_dir / "events.json"
    with events_path.open("w", encoding="utf-8") as handle:
        json.dump(events, handle, indent=2)

    print(f"Created sample session at: {session_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
