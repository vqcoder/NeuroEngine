"""Unit tests for readout metric formulas."""

from __future__ import annotations

from app.readout_metrics import (
    ReadoutMetricConfig,
    SegmentPoint,
    SessionBlinkSample,
    build_attention_change_segments,
    compute_attention_score,
    compute_attention_velocity,
    compute_blink_inhibition,
    compute_quality_weight,
    compute_reward_proxy_decomposition,
    compute_reward_proxy,
    compute_session_blink_baseline,
)


def test_compute_session_blink_baseline_prefers_explicit_baseline_rate() -> None:
    config = ReadoutMetricConfig()
    samples = [
        SessionBlinkSample(video_time_ms=0, blink=0, blink_baseline_rate=0.4),
        SessionBlinkSample(video_time_ms=1000, blink=1, blink_baseline_rate=0.5),
    ]

    baseline = compute_session_blink_baseline(samples, config)

    assert abs(baseline - 0.45) < 1e-6


def test_compute_session_blink_baseline_uses_early_window_when_explicit_missing() -> None:
    config = ReadoutMetricConfig(baseline_window_ms=5000)
    samples = [
        SessionBlinkSample(video_time_ms=0, blink=0),
        SessionBlinkSample(video_time_ms=1000, blink=1),
        SessionBlinkSample(video_time_ms=2000, blink=0),
        SessionBlinkSample(video_time_ms=3000, blink=1),
    ]

    baseline = compute_session_blink_baseline(samples, config)
    inhibition = compute_blink_inhibition(current_rate=0.2, baseline_rate=baseline)

    assert 0.6 < baseline < 0.7
    assert inhibition > 0.6


def test_attention_velocity_is_smoothed_derivative() -> None:
    config = ReadoutMetricConfig(velocity_smoothing_alpha=0.5)
    velocity = compute_attention_velocity([10.0, 20.0, 30.0], 1000, config)

    assert len(velocity) == 3
    assert abs(velocity[0] - 0.0) < 1e-6
    assert abs(velocity[1] - 5.0) < 1e-6
    assert abs(velocity[2] - 7.5) < 1e-6


def test_build_attention_change_segments_detects_gain_and_loss_windows() -> None:
    config = ReadoutMetricConfig(
        local_baseline_points=2,
        gain_threshold=5.0,
        loss_threshold=5.0,
        min_segment_windows=2,
    )
    points = [
        SegmentPoint(video_time_ms=0, attention_score=40.0, attention_velocity=0.0, tracking_confidence=0.8),
        SegmentPoint(video_time_ms=1000, attention_score=42.0, attention_velocity=1.0, tracking_confidence=0.8),
        SegmentPoint(video_time_ms=2000, attention_score=52.0, attention_velocity=6.0, tracking_confidence=0.8),
        SegmentPoint(video_time_ms=3000, attention_score=60.0, attention_velocity=7.0, tracking_confidence=0.7),
        SegmentPoint(video_time_ms=4000, attention_score=58.0, attention_velocity=-2.0, tracking_confidence=0.6),
        SegmentPoint(video_time_ms=5000, attention_score=45.0, attention_velocity=-6.0, tracking_confidence=0.6),
        SegmentPoint(video_time_ms=6000, attention_score=35.0, attention_velocity=-8.0, tracking_confidence=0.6),
    ]

    gain_segments = build_attention_change_segments(points, positive=True, window_ms=1000, config=config)
    loss_segments = build_attention_change_segments(points, positive=False, window_ms=1000, config=config)

    assert len(gain_segments) == 1
    assert gain_segments[0]["start_video_time_ms"] == 2000
    assert gain_segments[0]["end_video_time_ms"] == 4000
    assert "above_local_baseline" in gain_segments[0]["reason_codes"]

    assert len(loss_segments) == 1
    assert loss_segments[0]["start_video_time_ms"] == 5000
    assert loss_segments[0]["end_video_time_ms"] == 7000
    assert "below_local_baseline" in loss_segments[0]["reason_codes"]


def test_quality_weighting_downweights_attention_and_reward() -> None:
    config = ReadoutMetricConfig(quality_min_weight=0.2)
    low_weight = compute_quality_weight(0.2, 0.4, config)
    high_weight = compute_quality_weight(0.9, 0.9, config)

    low_attention = compute_attention_score(
        face_presence=0.95,
        head_pose_stability=0.95,
        gaze_on_screen=0.95,
        eye_openness=0.95,
        blink_inhibition=0.3,
        playback_continuity=1.0,
        au12=0.4,
        au6=0.25,
        au4=0.05,
        tracking_confidence=0.2,
        quality_score=0.3,
        config=config,
    )
    high_attention = compute_attention_score(
        face_presence=0.95,
        head_pose_stability=0.95,
        gaze_on_screen=0.95,
        eye_openness=0.95,
        blink_inhibition=0.3,
        playback_continuity=1.0,
        au12=0.4,
        au6=0.25,
        au4=0.05,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )

    low_reward = compute_reward_proxy(
        attention_score=high_attention,
        au12=0.4,
        au6=0.25,
        au4=0.05,
        blink_rate=0.3,
        blink_baseline_rate=0.2,
        blink_inhibition=0.2,
        label_signal=-0.5,
        dial=35.0,
        tracking_confidence=0.2,
        quality_score=0.3,
        config=config,
    )
    high_reward = compute_reward_proxy(
        attention_score=high_attention,
        au12=0.4,
        au6=0.25,
        au4=0.05,
        blink_rate=0.15,
        blink_baseline_rate=0.2,
        blink_inhibition=0.5,
        label_signal=0.6,
        dial=75.0,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )

    assert abs(low_weight - 0.44) < 1e-6
    assert high_weight > low_weight
    assert high_attention > low_attention
    assert high_reward > low_reward


def test_attention_score_is_behavior_first_not_au_driven() -> None:
    config = ReadoutMetricConfig()
    low_au_attention = compute_attention_score(
        face_presence=0.9,
        head_pose_stability=0.85,
        gaze_on_screen=0.75,
        eye_openness=0.72,
        blink_inhibition=0.22,
        playback_continuity=0.95,
        au12=0.05,
        au6=0.03,
        au4=0.52,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )
    high_au_attention = compute_attention_score(
        face_presence=0.9,
        head_pose_stability=0.85,
        gaze_on_screen=0.75,
        eye_openness=0.72,
        blink_inhibition=0.22,
        playback_continuity=0.95,
        au12=0.62,
        au6=0.41,
        au4=0.04,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )

    assert abs(low_au_attention - high_au_attention) < 1e-6


def test_novelty_proxy_spikes_at_scene_change() -> None:
    config = ReadoutMetricConfig()
    base = compute_reward_proxy_decomposition(
        attention_score=58.0,
        attention_velocity=1.2,
        au12=0.22,
        au6=0.12,
        au4=0.08,
        blink_rate=0.2,
        blink_baseline_rate=0.2,
        blink_inhibition=0.05,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.95,
        scene_change_signal=0.0,
        telemetry_disruption=0.05,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )
    changed_scene = compute_reward_proxy_decomposition(
        attention_score=58.0,
        attention_velocity=1.2,
        au12=0.22,
        au6=0.12,
        au4=0.08,
        blink_rate=0.2,
        blink_baseline_rate=0.2,
        blink_inhibition=0.05,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.95,
        scene_change_signal=1.0,
        telemetry_disruption=0.05,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )

    assert changed_scene.novelty_proxy > base.novelty_proxy


def test_arousal_proxy_rises_with_intensity_and_velocity() -> None:
    config = ReadoutMetricConfig()
    low_intensity = compute_reward_proxy_decomposition(
        attention_score=45.0,
        attention_velocity=0.3,
        au12=0.10,
        au6=0.05,
        au4=0.04,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.2,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.98,
        scene_change_signal=0.0,
        telemetry_disruption=0.02,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    high_intensity = compute_reward_proxy_decomposition(
        attention_score=78.0,
        attention_velocity=5.5,
        au12=0.55,
        au6=0.30,
        au4=0.05,
        blink_rate=0.34,
        blink_baseline_rate=0.2,
        blink_inhibition=-0.1,
        label_signal=0.2,
        dial=70.0,
        playback_continuity=0.9,
        scene_change_signal=0.4,
        telemetry_disruption=0.15,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )

    assert high_intensity.arousal_proxy > low_intensity.arousal_proxy


def test_valence_proxy_tracks_au_pattern_heuristics() -> None:
    config = ReadoutMetricConfig()
    positive_pattern = compute_reward_proxy_decomposition(
        attention_score=62.0,
        attention_velocity=0.8,
        au12=0.62,
        au6=0.35,
        au4=0.04,
        blink_rate=0.16,
        blink_baseline_rate=0.2,
        blink_inhibition=0.3,
        label_signal=0.4,
        dial=65.0,
        playback_continuity=0.95,
        scene_change_signal=0.1,
        telemetry_disruption=0.05,
        tracking_confidence=0.92,
        quality_score=0.92,
        config=config,
    )
    friction_pattern = compute_reward_proxy_decomposition(
        attention_score=62.0,
        attention_velocity=0.8,
        au12=0.08,
        au6=0.06,
        au4=0.55,
        blink_rate=0.34,
        blink_baseline_rate=0.2,
        blink_inhibition=-0.3,
        label_signal=-0.4,
        dial=35.0,
        playback_continuity=0.95,
        scene_change_signal=0.1,
        telemetry_disruption=0.05,
        tracking_confidence=0.92,
        quality_score=0.92,
        config=config,
    )

    assert positive_pattern.valence_proxy > friction_pattern.valence_proxy


def test_reward_proxy_composes_components_stably() -> None:
    config = ReadoutMetricConfig()
    base = compute_reward_proxy_decomposition(
        attention_score=60.0,
        attention_velocity=1.0,
        au12=0.25,
        au6=0.15,
        au4=0.10,
        blink_rate=0.21,
        blink_baseline_rate=0.2,
        blink_inhibition=0.05,
        label_signal=0.0,
        dial=50.0,
        playback_continuity=0.95,
        scene_change_signal=0.0,
        telemetry_disruption=0.05,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    boosted = compute_reward_proxy_decomposition(
        attention_score=72.0,
        attention_velocity=2.2,
        au12=0.45,
        au6=0.28,
        au4=0.06,
        blink_rate=0.16,
        blink_baseline_rate=0.2,
        blink_inhibition=0.28,
        label_signal=0.35,
        dial=72.0,
        playback_continuity=0.97,
        scene_change_signal=0.65,
        telemetry_disruption=0.08,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )

    assert 0.0 <= base.reward_proxy <= 100.0
    assert 0.0 <= boosted.reward_proxy <= 100.0
    assert boosted.reward_proxy > base.reward_proxy
    assert (boosted.reward_proxy - base.reward_proxy) < 50.0


def test_reward_proxy_is_facial_coding_driven_not_attention_mirror() -> None:
    config = ReadoutMetricConfig()
    low_attention_same_face = compute_reward_proxy_decomposition(
        attention_score=22.0,
        attention_velocity=1.5,
        au12=0.58,
        au6=0.33,
        au4=0.06,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.12,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.96,
        scene_change_signal=0.2,
        telemetry_disruption=0.03,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    high_attention_same_face = compute_reward_proxy_decomposition(
        attention_score=88.0,
        attention_velocity=1.5,
        au12=0.58,
        au6=0.33,
        au4=0.06,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.12,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.96,
        scene_change_signal=0.2,
        telemetry_disruption=0.03,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    assert abs(low_attention_same_face.reward_proxy - high_attention_same_face.reward_proxy) < 1e-6

    low_face = compute_reward_proxy_decomposition(
        attention_score=55.0,
        attention_velocity=1.5,
        au12=0.10,
        au6=0.08,
        au4=0.48,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.12,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.96,
        scene_change_signal=0.2,
        telemetry_disruption=0.03,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    high_face = compute_reward_proxy_decomposition(
        attention_score=55.0,
        attention_velocity=1.5,
        au12=0.62,
        au6=0.36,
        au4=0.04,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.12,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.96,
        scene_change_signal=0.2,
        telemetry_disruption=0.03,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    assert high_face.reward_proxy > low_face.reward_proxy
