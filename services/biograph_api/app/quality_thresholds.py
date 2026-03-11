"""Shared quality-threshold loading and helpers for readout quality summaries."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


@dataclass(frozen=True)
class QualityBadgeThreshold:
    min_tracking_confidence: float
    min_face_ok_rate: float


@dataclass(frozen=True)
class ReadoutQualityThresholds:
    low_confidence_tracking_threshold: float = 0.5
    high: QualityBadgeThreshold = field(
        default_factory=lambda: QualityBadgeThreshold(
            min_tracking_confidence=0.75,
            min_face_ok_rate=0.85,
        )
    )
    medium: QualityBadgeThreshold = field(
        default_factory=lambda: QualityBadgeThreshold(
            min_tracking_confidence=0.55,
            min_face_ok_rate=0.65,
        )
    )


def _coerce_unit_interval(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, numeric))


def _resolve_config_path() -> Path:
    env_path = (os.getenv("QUALITY_THRESHOLDS_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser()
    candidates = _default_config_path_candidates(Path(__file__).resolve())
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path("packages/common/quality_thresholds.json")


def _default_config_path_candidates(module_path: Path) -> list[Path]:
    """Build likely quality-threshold config locations without index-based parent assumptions."""
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(root: Path) -> None:
        candidate = (root / "packages" / "common" / "quality_thresholds.json").resolve()
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    for root in [module_path.parent, *module_path.parents]:
        add_candidate(root)

    cwd = Path.cwd().resolve()
    for root in [cwd, *cwd.parents]:
        add_candidate(root)

    return candidates


def _read_threshold_payload(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def get_readout_quality_thresholds() -> ReadoutQualityThresholds:
    payload = _read_threshold_payload(_resolve_config_path())
    readout = payload.get("readout") if isinstance(payload, Mapping) else {}
    readout = readout if isinstance(readout, Mapping) else {}

    badge_payload = readout.get("quality_badge")
    badge_payload = badge_payload if isinstance(badge_payload, Mapping) else {}
    high_payload = badge_payload.get("high")
    high_payload = high_payload if isinstance(high_payload, Mapping) else {}
    medium_payload = badge_payload.get("medium")
    medium_payload = medium_payload if isinstance(medium_payload, Mapping) else {}

    return ReadoutQualityThresholds(
        low_confidence_tracking_threshold=_coerce_unit_interval(
            readout.get("low_confidence_tracking_threshold"),
            0.5,
        ),
        high=QualityBadgeThreshold(
            min_tracking_confidence=_coerce_unit_interval(
                high_payload.get("min_tracking_confidence"),
                0.75,
            ),
            min_face_ok_rate=_coerce_unit_interval(
                high_payload.get("min_face_ok_rate"),
                0.85,
            ),
        ),
        medium=QualityBadgeThreshold(
            min_tracking_confidence=_coerce_unit_interval(
                medium_payload.get("min_tracking_confidence"),
                0.55,
            ),
            min_face_ok_rate=_coerce_unit_interval(
                medium_payload.get("min_face_ok_rate"),
                0.65,
            ),
        ),
    )


def is_low_confidence_window(
    *,
    tracking_confidence: Optional[float],
    quality_flags: Sequence[str],
    thresholds: Optional[ReadoutQualityThresholds] = None,
) -> bool:
    active = thresholds or get_readout_quality_thresholds()
    return (
        tracking_confidence is not None
        and float(tracking_confidence) < active.low_confidence_tracking_threshold
    ) or len(quality_flags) > 0


def resolve_quality_badge(
    *,
    mean_tracking_confidence: Optional[float],
    face_ok_rate: float,
    thresholds: Optional[ReadoutQualityThresholds] = None,
) -> str:
    active = thresholds or get_readout_quality_thresholds()
    tracking = float(mean_tracking_confidence) if mean_tracking_confidence is not None else 0.0
    face_ok = float(face_ok_rate)

    if (
        tracking >= active.high.min_tracking_confidence
        and face_ok >= active.high.min_face_ok_rate
    ):
        return "high"
    if (
        tracking >= active.medium.min_tracking_confidence
        and face_ok >= active.medium.min_face_ok_rate
    ):
        return "medium"
    return "low"
