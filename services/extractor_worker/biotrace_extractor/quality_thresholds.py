"""Shared threshold loading for extractor quality flags."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class ExtractorQualityThresholds:
    low_light_max_brightness: float = 45.0
    blur_min_quality_score: float = 0.4
    face_visible_pct_min: float = 0.5
    head_pose_valid_pct_min: float = 0.6


def _coerce_unit_interval(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, numeric))


def _coerce_non_negative(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, numeric)


def _resolve_config_path() -> Path:
    env_path = (os.getenv("QUALITY_THRESHOLDS_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parents[3] / "packages" / "common" / "quality_thresholds.json"


def _read_threshold_payload(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def get_extractor_quality_thresholds() -> ExtractorQualityThresholds:
    payload = _read_threshold_payload(_resolve_config_path())
    extractor = payload.get("extractor") if isinstance(payload, Mapping) else {}
    extractor = extractor if isinstance(extractor, Mapping) else {}
    quality_flags = extractor.get("quality_flags")
    quality_flags = quality_flags if isinstance(quality_flags, Mapping) else {}

    return ExtractorQualityThresholds(
        low_light_max_brightness=_coerce_non_negative(
            quality_flags.get("low_light_max_brightness"),
            45.0,
        ),
        blur_min_quality_score=_coerce_unit_interval(
            quality_flags.get("blur_min_quality_score"),
            0.4,
        ),
        face_visible_pct_min=_coerce_unit_interval(
            quality_flags.get("face_visible_pct_min"),
            0.5,
        ),
        head_pose_valid_pct_min=_coerce_unit_interval(
            quality_flags.get("head_pose_valid_pct_min"),
            0.6,
        ),
    )
