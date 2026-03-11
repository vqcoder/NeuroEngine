"""Unit tests for blink transport diagnostics and fallback behavior."""

from __future__ import annotations

from app.blink_transport import compute_blink_transport_diagnostics
from app.schemas import ReadoutCtaMarker


def _bucket_rows(
    inhibition_values: list[float | None],
    *,
    attention_values: list[float] | None = None,
    cta_window: tuple[int, int] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    attention_series = attention_values or [66.0 for _ in inhibition_values]
    previous_attention = attention_series[0] if attention_series else 66.0
    for index, inhibition in enumerate(inhibition_values):
        start_ms = index * 1000
        attention_score = float(attention_series[index])
        velocity = attention_score - previous_attention if index > 0 else 0.0
        previous_attention = attention_score
        if inhibition is None:
            blink_rate = None
            blink_baseline = None
        else:
            blink_baseline = 0.18
            blink_rate = max(0.01, blink_baseline * (1.0 - inhibition))
        cta_id = None
        if cta_window is not None and cta_window[0] <= start_ms < cta_window[1]:
            cta_id = "cta-main"
        rows.append(
            {
                "bucket_start": start_ms,
                "scene_id": "scene-1" if start_ms < 4000 else "scene-2",
                "cut_id": f"cut-{index}",
                "cta_id": cta_id,
                "attention_score": attention_score,
                "attention_velocity": velocity,
                "label_signal": 0.5 if start_ms in {1000, 2000, 4000} else 0.0,
                "blink_rate": blink_rate,
                "blink_baseline_rate": blink_baseline,
                "blink_inhibition": inhibition,
                "tracking_confidence": 0.84,
                "quality_score": 0.82,
            }
        )
    return rows


def _timeline_segments() -> list[dict[str, object]]:
    return [
        {"segment_type": "shot_boundary", "start_ms": 3000, "end_ms": 3001},
        {"segment_type": "shot_boundary", "start_ms": 6000, "end_ms": 6001},
        {"segment_type": "text_overlay", "start_ms": 4200, "end_ms": 5000},
        {"segment_type": "cta_window", "start_ms": 4200, "end_ms": 5600},
    ]


def test_blink_transport_rewards_suppression_and_boundary_rebound() -> None:
    controlled_rows = _bucket_rows([0.58, 0.62, 0.55, 0.12, 0.54, 0.57, 0.16, 0.52])
    fragmented_rows = _bucket_rows([0.18, 0.12, 0.16, 0.25, 0.19, 0.14, 0.27, 0.13])

    controlled = compute_blink_transport_diagnostics(
        bucket_rows=controlled_rows,
        session_bucket_rows_by_session={},
        cta_markers=[],
        timeline_segments=_timeline_segments(),
        window_ms=1000,
    )
    fragmented = compute_blink_transport_diagnostics(
        bucket_rows=fragmented_rows,
        session_bucket_rows_by_session={},
        cta_markers=[],
        timeline_segments=_timeline_segments(),
        window_ms=1000,
    )

    assert controlled.pathway.value in {"fallback_proxy", "sparse_fallback"}
    assert controlled.global_score is not None
    assert fragmented.global_score is not None
    assert controlled.global_score > fragmented.global_score
    assert controlled.suppression_score is not None
    assert fragmented.suppression_score is not None
    assert controlled.suppression_score > fragmented.suppression_score
    assert controlled.rebound_score is not None
    assert fragmented.rebound_score is not None
    assert controlled.rebound_score > fragmented.rebound_score


def test_blink_transport_cta_avoidance_and_warning_path() -> None:
    cta_marker = ReadoutCtaMarker(
        cta_id="cta-main",
        video_time_ms=4200,
        start_ms=4200,
        end_ms=5600,
        label="Primary CTA",
    )
    strong_avoidance_rows = _bucket_rows(
        [0.2, 0.22, 0.25, 0.62, 0.66, 0.63, 0.22, 0.2],
        cta_window=(4200, 5600),
    )
    weak_avoidance_rows = _bucket_rows(
        [0.5, 0.48, 0.46, -0.2, -0.18, -0.22, 0.47, 0.49],
        cta_window=(4200, 5600),
    )

    strong = compute_blink_transport_diagnostics(
        bucket_rows=strong_avoidance_rows,
        session_bucket_rows_by_session={},
        cta_markers=[cta_marker],
        timeline_segments=_timeline_segments(),
        window_ms=1000,
    )
    weak = compute_blink_transport_diagnostics(
        bucket_rows=weak_avoidance_rows,
        session_bucket_rows_by_session={},
        cta_markers=[cta_marker],
        timeline_segments=_timeline_segments(),
        window_ms=1000,
    )

    assert strong.cta_avoidance_score is not None
    assert weak.cta_avoidance_score is not None
    assert strong.cta_avoidance_score > weak.cta_avoidance_score
    assert not any(
        warning.warning_key == "weak_cta_blink_avoidance"
        for warning in strong.engagement_warnings
    )
    assert any(
        warning.warning_key == "weak_cta_blink_avoidance"
        for warning in weak.engagement_warnings
    )


def test_blink_transport_sparse_signal_uses_low_confidence_fallback() -> None:
    rows = _bucket_rows(
        [None, None, None, None, None, None],
        attention_values=[64, 66, 68, 65, 63, 61],
    )

    diagnostics = compute_blink_transport_diagnostics(
        bucket_rows=rows,
        session_bucket_rows_by_session={},
        cta_markers=[],
        timeline_segments=_timeline_segments(),
        window_ms=1000,
    )

    assert diagnostics.pathway.value == "sparse_fallback"
    assert diagnostics.global_score is not None
    assert diagnostics.confidence is not None
    assert diagnostics.confidence <= 0.46
    assert any(
        warning.warning_key == "sparse_blink_signal"
        for warning in diagnostics.engagement_warnings
    )


def test_blink_transport_uses_direct_panel_path_when_synchrony_exists() -> None:
    rows = _bucket_rows([0.45, 0.48, 0.5, 0.2, 0.52, 0.49, 0.22, 0.5])
    session_rows = {
        1001: {
            index * 1000: {"blink_inhibition": value, "tracking_confidence": 0.86}
            for index, value in enumerate([0.46, 0.5, 0.52, 0.21, 0.54, 0.51, 0.23, 0.51])
        },
        1002: {
            index * 1000: {"blink_inhibition": value, "tracking_confidence": 0.83}
            for index, value in enumerate([0.44, 0.47, 0.49, 0.18, 0.5, 0.48, 0.2, 0.49])
        },
    }

    diagnostics = compute_blink_transport_diagnostics(
        bucket_rows=rows,
        session_bucket_rows_by_session=session_rows,
        cta_markers=[],
        timeline_segments=_timeline_segments(),
        window_ms=1000,
    )

    assert diagnostics.pathway.value == "direct_panel_blink"
    assert diagnostics.cross_viewer_blink_synchrony is not None
    assert diagnostics.cross_viewer_blink_synchrony > 0.75
    assert diagnostics.global_score is not None
    assert diagnostics.confidence is not None
