"""Reliability tests for predict_service: NaN propagation, output validation, blink_rate bounds."""

from __future__ import annotations

import math

import pytest

from app.predict_service import _enrich_predict_trace_points, _heuristic_predictions
from app.readout_metrics import clamp as _clamp
from app.schemas import PredictTracePoint


# ---------------------------------------------------------------------------
# _clamp NaN / Inf guard
# ---------------------------------------------------------------------------

def test_clamp_nan_returns_lower():
    assert _clamp(float("nan"), 0.0, 100.0) == 0.0


def test_clamp_positive_inf_clamps_to_upper():
    # max(0, min(100, +inf)) == 100
    assert _clamp(float("inf"), 0.0, 100.0) == 100.0


def test_clamp_negative_inf_clamps_to_lower():
    # max(0, min(100, -inf)) == 0
    assert _clamp(float("-inf"), 0.0, 100.0) == 0.0


def test_clamp_nan_custom_bounds():
    result = _clamp(float("nan"), 5.0, 95.0)
    assert result == 5.0
    assert math.isfinite(result)


def test_clamp_normal_values_unchanged():
    assert _clamp(50.0, 0.0, 100.0) == 50.0
    assert _clamp(0.0, 0.0, 100.0) == 0.0
    assert _clamp(100.0, 0.0, 100.0) == 100.0
    assert _clamp(-1.0, 0.0, 100.0) == 0.0
    assert _clamp(101.0, 0.0, 100.0) == 100.0


# ---------------------------------------------------------------------------
# _enrich_predict_trace_points: NaN inputs produce finite outputs
# ---------------------------------------------------------------------------

def _make_point(**kwargs) -> PredictTracePoint:
    defaults = dict(t_sec=0.0, attention=50.0, blink_inhibition=30.0, dial=50.0)
    defaults.update(kwargs)
    return PredictTracePoint(**defaults)


def test_enrich_nan_reward_proxy_produces_finite_output():
    pts = [_make_point(t_sec=0.0, reward_proxy=float("nan"), attention=50.0)]
    enriched = _enrich_predict_trace_points(pts)
    assert len(enriched) == 1
    assert math.isfinite(enriched[0].reward_proxy)
    assert 0.0 <= enriched[0].reward_proxy <= 100.0


def test_enrich_nan_attention_produces_finite_output():
    pts = [_make_point(t_sec=0.0, attention=float("nan"))]
    enriched = _enrich_predict_trace_points(pts)
    assert math.isfinite(enriched[0].attention)
    assert 0.0 <= enriched[0].attention <= 100.0


def test_enrich_blink_rate_passthrough_stays_bounded():
    # schema enforces 0 <= blink_rate <= 1; enrich should preserve it
    pts = [_make_point(t_sec=0.0, blink_rate=0.8)]
    enriched = _enrich_predict_trace_points(pts)
    assert math.isfinite(enriched[0].blink_rate)
    assert 0.0 <= enriched[0].blink_rate <= 5.0


def test_enrich_multiple_rows_all_finite():
    pts = [
        _make_point(t_sec=0.0, reward_proxy=float("nan"), attention=float("nan")),
        _make_point(t_sec=1.0, reward_proxy=50.0, attention=99.9),
        _make_point(t_sec=2.0, blink_rate=0.5),
    ]
    enriched = _enrich_predict_trace_points(pts)
    for row in enriched:
        assert math.isfinite(row.reward_proxy), f"reward_proxy not finite: {row.reward_proxy}"
        assert math.isfinite(row.attention), f"attention not finite: {row.attention}"
        if row.blink_rate is not None:
            assert math.isfinite(row.blink_rate), f"blink_rate not finite: {row.blink_rate}"
        assert 0.0 <= row.reward_proxy <= 100.0
        assert 0.0 <= row.attention <= 100.0


# ---------------------------------------------------------------------------
# _heuristic_predictions: all output values bounded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("duration", [0, 1, 30, 93])
def test_heuristic_predictions_all_finite_and_bounded(duration: int):
    rows = _heuristic_predictions(duration)
    assert len(rows) >= 1
    for i, row in enumerate(rows):
        assert math.isfinite(row.t_sec), f"t_sec NaN at {i}"
        assert math.isfinite(row.reward_proxy), f"reward_proxy NaN at {i}"
        assert math.isfinite(row.blink_rate), f"blink_rate NaN at {i}"
        assert math.isfinite(row.attention), f"attention NaN at {i}"
        assert 0.0 <= row.reward_proxy <= 100.0, f"reward_proxy OOB at {i}: {row.reward_proxy}"
        assert 0.0 <= row.attention <= 100.0, f"attention OOB at {i}: {row.attention}"
        assert row.blink_rate >= 0.0, f"blink_rate negative at {i}: {row.blink_rate}"


def test_heuristic_predictions_t_sec_monotonic():
    rows = _heuristic_predictions(10)
    for i in range(1, len(rows)):
        assert rows[i].t_sec >= rows[i - 1].t_sec, f"t_sec not monotonic at row {i}"


# ---------------------------------------------------------------------------
# _validate_predict_output: correct rejection behaviour
# ---------------------------------------------------------------------------

from app.routes_prediction import _validate_predict_output  # noqa: E402


def test_validate_empty_raises():
    with pytest.raises(ValueError, match="zero rows"):
        _validate_predict_output([])


def test_validate_nan_reward_proxy_raises():
    pts = [_make_point(t_sec=0.0, reward_proxy=float("nan"))]
    with pytest.raises(ValueError, match="reward_proxy"):
        _validate_predict_output(pts)


def test_validate_out_of_range_reward_proxy_raises():
    pts = [_make_point(t_sec=0.0, reward_proxy=150.0)]
    with pytest.raises(ValueError, match="reward_proxy"):
        _validate_predict_output(pts)


def test_validate_non_monotonic_t_sec_raises():
    pts = [_make_point(t_sec=1.0), _make_point(t_sec=0.5)]
    with pytest.raises(ValueError, match="monotonic"):
        _validate_predict_output(pts)


def test_validate_valid_rows_passes():
    pts = [
        _make_point(t_sec=0.0, reward_proxy=30.0, attention=50.0, blink_rate=0.2),
        _make_point(t_sec=1.0, reward_proxy=55.0, attention=60.0, blink_rate=0.25),
    ]
    _validate_predict_output(pts)  # must not raise
