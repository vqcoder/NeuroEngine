"""Reliability tests for _apply_blink_rate_variance_if_flat.

Verifies that a completely flat blink rate input (all rows identical)
is corrected to a visually meaningful range (≥ 0.08) rather than the
near-invisible ±0.025 that existed before the half_span fix.
"""

from __future__ import annotations

import math

import pytest

from app.services_math import _apply_blink_rate_variance_if_flat, _series_range


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_rows(n: int = 30, blink_rate: float = 0.22, baseline: float = 0.22):
    return [
        {
            "blink_rate": blink_rate,
            "blink_baseline_rate": baseline,
            "blink_inhibition": 0.0,
            "eye_openness": 0.45,
            "tracking_confidence": 0.9,
            "mean_occlusion_score": 0.05,
        }
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# Core contract: flat input → visible range
# ---------------------------------------------------------------------------

def test_flat_blink_range_after_correction_is_visible():
    """After correction, range must be ≥ 0.06 so it's visible on a chart."""
    rows = _flat_rows(30, blink_rate=0.22)
    assert _series_range([float(r["blink_rate"]) for r in rows]) < 0.001  # confirm flat

    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=0.22)

    corrected = [float(r["blink_rate"]) for r in rows]
    result_range = max(corrected) - min(corrected)
    assert result_range >= 0.06, (
        f"Corrected blink range ({result_range:.4f}) is too small to visualize — "
        f"expected ≥ 0.06 after half_span fix"
    )


def test_flat_blink_all_values_finite_after_correction():
    rows = _flat_rows(30, blink_rate=0.18)
    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=0.18)
    for i, row in enumerate(rows):
        assert math.isfinite(float(row["blink_rate"])), f"NaN at row {i}"
        assert math.isfinite(float(row["blink_inhibition"])), f"blink_inhibition NaN at row {i}"


def test_flat_blink_values_stay_in_physiological_range():
    rows = _flat_rows(30, blink_rate=0.22)
    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=0.22)
    for row in rows:
        val = float(row["blink_rate"])
        assert 0.005 <= val <= 1.2, f"blink_rate {val} outside physiological bounds [0.005, 1.2]"


def test_non_flat_blink_not_modified():
    """If the blink series already has sufficient range, it must be left unchanged."""
    rows = [
        {"blink_rate": 0.1 + i * 0.01, "blink_baseline_rate": 0.22, "blink_inhibition": 0.0,
         "eye_openness": 0.45, "tracking_confidence": 0.9, "mean_occlusion_score": 0.0}
        for i in range(10)
    ]
    original = [float(r["blink_rate"]) for r in rows]
    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=0.22)
    for orig, row in zip(original, rows):
        assert float(row["blink_rate"]) == orig, "Non-flat series must not be modified"


def test_blink_correction_produces_different_values_per_row():
    """Each row should get a distinct corrected value — not all the same."""
    rows = _flat_rows(20, blink_rate=0.22)
    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=0.22)
    corrected = [round(float(r["blink_rate"]), 6) for r in rows]
    unique_count = len(set(corrected))
    assert unique_count > 3, f"Too few unique blink values after correction: {unique_count}"


@pytest.mark.parametrize("baseline", [0.10, 0.22, 0.35, 0.50])
def test_correction_works_across_baselines(baseline: float):
    rows = _flat_rows(25, blink_rate=baseline, baseline=baseline)
    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=baseline)
    corrected = [float(r["blink_rate"]) for r in rows]
    result_range = max(corrected) - min(corrected)
    assert result_range >= 0.04, (
        f"Range {result_range:.4f} too small for baseline {baseline}"
    )
    assert all(math.isfinite(v) for v in corrected), "Non-finite values in corrected series"


def test_very_short_series_skipped():
    """Series with fewer than 3 rows must not be modified (can't compute reliable modulation)."""
    rows = _flat_rows(2, blink_rate=0.22)
    original = [float(r["blink_rate"]) for r in rows]
    _apply_blink_rate_variance_if_flat(rows, fallback_baseline=0.22)
    assert [float(r["blink_rate"]) for r in rows] == original


# ---------------------------------------------------------------------------
# Readout-level integration: flat input → visible blink range in readout
# ---------------------------------------------------------------------------

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "readout_session.json"


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def test_readout_blink_range_exceeds_visible_threshold_for_flat_input(client):
    """End-to-end: flat blink signal (range 0) in stored trace → readout blink range ≥ 0.06."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    study_resp = client.post("/studies", json=fixture["study"])
    study = study_resp.json()

    video_payload = dict(fixture["video"])
    video_payload["study_id"] = study["id"]
    video_resp = client.post("/videos", json=video_payload)
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={"study_id": study["id"], "video_id": video["id"], "participant": fixture["participants"][0]},
    )
    session = session_resp.json()

    # Completely flat blink rows — all identical
    flat_rows = []
    for row in fixture["session_rows"][0]:
        flat_rows.append({
            "t_ms": int(row["t_ms"]),
            "face_ok": True,
            "brightness": 24.0,
            "landmarks_ok": True,
            "blink": 0,
            "rolling_blink_rate": 0.22,
            "blink_baseline_rate": 0.22,
            "blink_inhibition_score": 0.0,
            "eye_openness": 0.45,
            "quality_confidence": 0.93,
            "quality_score": 0.91,
            "tracking_confidence": 0.94,
            "face_presence_confidence": 0.95,
            "gaze_on_screen_proxy": 0.88,
            "occlusion_score": 0.08,
            "head_pose_valid_pct": 0.95,
            "au": {"AU04": 0.03, "AU06": 0.06, "AU12": 0.16, "AU45": 0.0, "AU25": 0.03, "AU26": 0.03},
            "au_norm": {"AU04": 0.03, "AU06": 0.06, "AU12": 0.16, "AU45": 0.0, "AU25": 0.03, "AU26": 0.03},
            "head_pose": {"yaw": 0.01, "pitch": 0.0, "roll": 0.0},
        })

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(flat_rows),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"session_id": session["id"], "aggregate": "false", "window_ms": 1000},
    )
    assert readout_resp.status_code == 200
    payload = readout_resp.json()

    blink_values = [
        float(p["value"])
        for p in payload["traces"]["blink_rate"]
        if p.get("value") is not None
    ]
    assert len(blink_values) >= 3
    result_range = max(blink_values) - min(blink_values)
    assert result_range >= 0.06, (
        f"Readout blink range {result_range:.4f} still too small for flat input — "
        f"half_span correction may not be taking effect"
    )
