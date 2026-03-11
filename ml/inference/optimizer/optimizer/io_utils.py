"""I/O helpers for optimizer input and output payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .models import OptimizationResult


def load_video_summary(path: Path) -> Dict[str, Any]:
    """Load summary JSON from disk."""

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("video_summary.json must contain a JSON object")
    return payload


def save_edit_suggestions(path: Path, result: OptimizationResult) -> None:
    """Persist optimizer output JSON to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result.to_dict(), handle, indent=2)
        handle.write("\n")
