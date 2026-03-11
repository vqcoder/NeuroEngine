"""Tests for shared readout quality-threshold config loading."""

from __future__ import annotations

import json
from pathlib import Path

from app.quality_thresholds import (
    _default_config_path_candidates,
    get_readout_quality_thresholds,
    is_low_confidence_window,
    resolve_quality_badge,
)


def test_readout_quality_thresholds_load_defaults() -> None:
    get_readout_quality_thresholds.cache_clear()
    thresholds = get_readout_quality_thresholds()

    assert thresholds.low_confidence_tracking_threshold == 0.5
    assert thresholds.high.min_tracking_confidence == 0.75
    assert thresholds.high.min_face_ok_rate == 0.85
    assert thresholds.medium.min_tracking_confidence == 0.55
    assert thresholds.medium.min_face_ok_rate == 0.65


def test_readout_quality_thresholds_honor_override(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "quality_thresholds.override.json"
    config_path.write_text(
        json.dumps(
            {
                "readout": {
                    "low_confidence_tracking_threshold": 0.62,
                    "quality_badge": {
                        "high": {
                            "min_tracking_confidence": 0.9,
                            "min_face_ok_rate": 0.9,
                        },
                        "medium": {
                            "min_tracking_confidence": 0.7,
                            "min_face_ok_rate": 0.72,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("QUALITY_THRESHOLDS_PATH", str(config_path))
    get_readout_quality_thresholds.cache_clear()
    try:
        thresholds = get_readout_quality_thresholds()
        assert thresholds.low_confidence_tracking_threshold == 0.62
        assert thresholds.high.min_tracking_confidence == 0.9
        assert thresholds.high.min_face_ok_rate == 0.9
        assert thresholds.medium.min_tracking_confidence == 0.7
        assert thresholds.medium.min_face_ok_rate == 0.72

        assert is_low_confidence_window(
            tracking_confidence=0.6,
            quality_flags=[],
            thresholds=thresholds,
        )
        assert resolve_quality_badge(
            mean_tracking_confidence=0.73,
            face_ok_rate=0.73,
            thresholds=thresholds,
        ) == "medium"
        assert resolve_quality_badge(
            mean_tracking_confidence=0.91,
            face_ok_rate=0.91,
            thresholds=thresholds,
        ) == "high"
    finally:
        get_readout_quality_thresholds.cache_clear()


def test_default_config_path_candidates_handle_shallow_container_paths() -> None:
    shallow_module_path = Path("/service/app/quality_thresholds.py")
    candidates = _default_config_path_candidates(shallow_module_path)

    assert len(candidates) > 0
    assert Path("/service/packages/common/quality_thresholds.json") in candidates
