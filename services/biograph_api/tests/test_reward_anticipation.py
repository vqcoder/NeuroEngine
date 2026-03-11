"""Unit tests for reward anticipation diagnostics from synthetic pacing patterns."""

from __future__ import annotations

from app.reward_anticipation import compute_reward_anticipation_diagnostics
from app.schemas import ReadoutCtaMarker


def _bucket_rows(
    reward_values: list[float],
    *,
    blink_values: list[float] | None = None,
    attention_values: list[float] | None = None,
    arousal_values: list[float] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    blink_series = blink_values or [0.25 for _ in reward_values]
    attention_series = attention_values or [60.0 for _ in reward_values]
    arousal_series = arousal_values or [50.0 for _ in reward_values]
    for index, reward in enumerate(reward_values):
        start_ms = index * 1000
        prev_attention = attention_series[index - 1] if index > 0 else attention_series[index]
        rows.append(
            {
                "bucket_start": start_ms,
                "scene_id": "scene-1" if start_ms < 4000 else "scene-2",
                "cut_id": f"cut-{index}",
                "cta_id": "cta-main" if 5000 <= start_ms <= 6000 else None,
                "reward_proxy": reward,
                "attention_score": attention_series[index],
                "attention_velocity": attention_series[index] - prev_attention,
                "blink_inhibition": blink_series[index],
                "arousal_proxy": arousal_series[index],
                "tracking_confidence": 0.86,
                "quality_score": 0.84,
            }
        )
    return rows


def _timeline_segments() -> list[dict[str, object]]:
    return [
        {"segment_type": "text_overlay", "start_ms": 4200, "end_ms": 5000},
        {"segment_type": "cta_window", "start_ms": 5000, "end_ms": 6400},
    ]


def _timeline_tracks(
    *,
    cut_cadence: list[float],
    audio_rms: list[float],
) -> list[dict[str, object]]:
    tracks: list[dict[str, object]] = []
    for index, value in enumerate(cut_cadence):
        tracks.append(
            {
                "track_name": "cut_cadence",
                "start_ms": index * 1000,
                "end_ms": (index * 1000) + 1000,
                "numeric_value": value,
            }
        )
    for index, value in enumerate(audio_rms):
        tracks.append(
            {
                "track_name": "audio_intensity_rms",
                "start_ms": index * 1000,
                "end_ms": (index * 1000) + 1000,
                "numeric_value": value,
            }
        )
    return tracks


def test_reward_anticipation_higher_for_setup_suspense_payoff_than_flat() -> None:
    cta_markers = [
        ReadoutCtaMarker(cta_id="cta-main", video_time_ms=5000, start_ms=5000, end_ms=6400),
    ]
    suspense_rows = _bucket_rows(
        [40, 43, 47, 54, 62, 76, 84, 70, 60],
        blink_values=[0.3, 0.34, 0.38, 0.42, 0.48, 0.52, 0.36, 0.22, 0.2],
        attention_values=[52, 56, 60, 66, 72, 79, 82, 70, 62],
        arousal_values=[44, 46, 50, 56, 62, 70, 73, 58, 50],
    )
    flat_rows = _bucket_rows(
        [55, 55, 56, 55, 56, 55, 56, 55, 55],
        blink_values=[0.2, 0.18, 0.21, 0.19, 0.2, 0.18, 0.2, 0.19, 0.2],
        attention_values=[58, 58, 59, 58, 59, 58, 59, 58, 58],
        arousal_values=[49, 49, 50, 49, 50, 49, 50, 49, 49],
    )
    suspense_tracks = _timeline_tracks(
        cut_cadence=[0.5, 0.6, 0.8, 1.1, 1.5, 1.8, 1.0, 0.7, 0.6],
        audio_rms=[0.04, 0.05, 0.06, 0.08, 0.11, 0.14, 0.12, 0.08, 0.06],
    )
    flat_tracks = _timeline_tracks(
        cut_cadence=[0.4, 0.42, 0.41, 0.4, 0.42, 0.4, 0.41, 0.4, 0.4],
        audio_rms=[0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
    )

    suspense = compute_reward_anticipation_diagnostics(
        bucket_rows=suspense_rows,
        cta_markers=cta_markers,
        timeline_segments=_timeline_segments(),
        timeline_feature_tracks=suspense_tracks,
        window_ms=1000,
    )
    flat = compute_reward_anticipation_diagnostics(
        bucket_rows=flat_rows,
        cta_markers=cta_markers,
        timeline_segments=_timeline_segments(),
        timeline_feature_tracks=flat_tracks,
        window_ms=1000,
    )

    assert suspense.pathway.value == "timeline_dynamics"
    assert flat.pathway.value == "timeline_dynamics"
    assert suspense.global_score is not None
    assert flat.global_score is not None
    assert suspense.global_score > flat.global_score + 8.0
    assert len(suspense.anticipation_ramps) >= 1
    assert len(suspense.payoff_windows) >= 1


def test_reward_anticipation_flags_unresolved_tension() -> None:
    rows = _bucket_rows(
        [42, 46, 51, 57, 59, 54, 50, 47, 45],
        blink_values=[0.28, 0.34, 0.4, 0.46, 0.5, 0.24, 0.2, 0.18, 0.16],
        attention_values=[50, 55, 60, 66, 71, 61, 56, 52, 49],
        arousal_values=[43, 47, 53, 60, 66, 57, 52, 49, 46],
    )
    tracks = _timeline_tracks(
        cut_cadence=[0.6, 0.8, 1.1, 1.5, 1.9, 1.1, 0.8, 0.7, 0.6],
        audio_rms=[0.04, 0.05, 0.07, 0.1, 0.13, 0.11, 0.08, 0.07, 0.06],
    )

    diagnostics = compute_reward_anticipation_diagnostics(
        bucket_rows=rows,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=5000, start_ms=5000, end_ms=6400)],
        timeline_segments=_timeline_segments(),
        timeline_feature_tracks=tracks,
        window_ms=1000,
    )

    warning_keys = {item.warning_key for item in diagnostics.warnings}
    assert diagnostics.global_score is not None
    assert "weak_payoff_release" in warning_keys or "tension_without_resolution" in warning_keys


def test_reward_anticipation_falls_back_without_timeline_tracks() -> None:
    rows = _bucket_rows(
        [41, 44, 49, 56, 64, 73, 80, 68, 58],
        blink_values=[0.25, 0.29, 0.35, 0.4, 0.47, 0.5, 0.34, 0.2, 0.18],
        attention_values=[52, 56, 61, 67, 72, 78, 81, 69, 60],
        arousal_values=[44, 47, 52, 58, 64, 71, 73, 57, 49],
    )

    diagnostics = compute_reward_anticipation_diagnostics(
        bucket_rows=rows,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=5000, start_ms=5000, end_ms=6400)],
        timeline_segments=_timeline_segments(),
        timeline_feature_tracks=[],
        window_ms=1000,
    )

    assert diagnostics.pathway.value == "fallback_proxy"
    assert diagnostics.global_score is not None
    assert diagnostics.confidence is not None
    assert diagnostics.confidence <= 0.72

