"""Readout metric formulas and segmentation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Dict, List, Literal, Optional, Sequence


def clamp(value: float, low: float, high: float) -> float:
    if value != value:  # fast NaN check (math.isnan without import)
        return low
    return max(low, min(high, value))


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def mean_optional(values: Sequence[Optional[float]]) -> Optional[float]:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return mean(numeric)


@dataclass(frozen=True)
class ReadoutMetricConfig:
    baseline_window_ms: int = 10_000
    quality_min_weight: float = 0.2
    velocity_smoothing_alpha: float = 0.35
    local_baseline_points: int = 3
    gain_threshold: float = 5.0
    loss_threshold: float = 5.0
    min_segment_windows: int = 2
    attention_face_presence_weight: float = 0.15
    attention_head_pose_stability_weight: float = 0.10
    attention_gaze_weight: float = 0.10
    attention_eye_openness_weight: float = 0.10
    attention_blink_inhibition_weight: float = 0.45
    attention_playback_continuity_weight: float = 0.10
    valence_bias: float = 0.18
    valence_au12_weight: float = 0.34
    valence_au6_weight: float = 0.20
    valence_au4_penalty_weight: float = 0.30
    valence_label_weight: float = 0.08
    valence_blink_inhibition_weight: float = 0.05
    valence_blink_rate_penalty_weight: float = 0.05
    arousal_bias: float = 0.18
    arousal_velocity_weight: float = 0.22
    arousal_blink_activation_weight: float = 0.18
    arousal_telemetry_disruption_weight: float = 0.12
    arousal_au_intensity_weight: float = 0.18
    novelty_bias: float = 0.16
    novelty_velocity_weight: float = 0.28
    novelty_scene_change_weight: float = 0.34
    novelty_telemetry_disruption_weight: float = 0.10
    novelty_label_surprise_weight: float = 0.08
    novelty_au_contrast_weight: float = 0.08
    reward_valence_weight: float = 0.36
    reward_arousal_weight: float = 0.19
    reward_novelty_weight: float = 0.11
    reward_facial_coding_weight: float = 0.34
    reward_au12_weight: float = 0.55
    reward_au6_weight: float = 0.35
    reward_au4_penalty_weight: float = 0.45
    reward_blink_inhibition_weight: float = 0.06
    reward_blink_rate_penalty_weight: float = 0.07
    reward_label_weight: float = 0.09
    reward_dial_weight: float = 0.05
    reward_playback_continuity_weight: float = 0.05
    dead_zone_threshold: float = 35.0
    confusion_blink_rate_threshold: float = 0.35
    confusion_au4_threshold: float = 0.08
    confusion_velocity_threshold: float = -2.0


@dataclass(frozen=True)
class SessionBlinkSample:
    video_time_ms: int
    blink: int
    rolling_blink_rate: Optional[float] = None
    blink_baseline_rate: Optional[float] = None


@dataclass(frozen=True)
class SegmentPoint:
    video_time_ms: int
    attention_score: float
    attention_velocity: float
    tracking_confidence: Optional[float]


DiagnosticCardType = Literal[
    "golden_scene",
    "hook_strength",
    "cta_receptivity",
    "attention_drop_scene",
    "confusion_scene",
    "recovery_scene",
]


@dataclass(frozen=True)
class DiagnosticScene:
    scene_index: int
    start_ms: int
    end_ms: int
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None
    label: Optional[str] = None
    thumbnail_url: Optional[str] = None


@dataclass(frozen=True)
class DiagnosticPoint:
    video_time_ms: int
    attention_score: float
    reward_proxy: float
    attention_velocity: float
    blink_rate: float
    au4: float
    tracking_confidence: Optional[float] = None
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


@dataclass(frozen=True)
class DiagnosticSegment:
    start_video_time_ms: int
    end_video_time_ms: int
    magnitude: float
    confidence: Optional[float]
    reason_codes: Sequence[str]
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None
    cta_id: Optional[str] = None


@dataclass(frozen=True)
class DiagnosticCtaMarker:
    cta_id: str
    video_time_ms: int
    scene_id: Optional[str] = None
    cut_id: Optional[str] = None


@dataclass(frozen=True)
class SceneDiagnosticCardData:
    card_type: DiagnosticCardType
    scene_index: Optional[int]
    scene_id: Optional[str]
    cut_id: Optional[str]
    cta_id: Optional[str]
    scene_label: Optional[str]
    scene_thumbnail_url: Optional[str]
    start_video_time_ms: int
    end_video_time_ms: int
    primary_metric: str
    primary_metric_value: float
    why_flagged: str
    confidence: Optional[float]
    reason_codes: List[str]


@dataclass(frozen=True)
class RewardProxyDecomposition:
    """Derived proxy traces for reward/valence/arousal/novelty on a 0-100 scale."""

    reward_proxy: float
    valence_proxy: float
    arousal_proxy: float
    novelty_proxy: float
    quality_weight: float


def estimate_window_ms(points: Sequence[int], fallback_window_ms: int = 1000) -> int:
    if len(points) < 2:
        return fallback_window_ms
    deltas = [points[index] - points[index - 1] for index in range(1, len(points))]
    positive = [delta for delta in deltas if delta > 0]
    if not positive:
        return fallback_window_ms
    return int(median(positive))


def compute_session_blink_baseline(
    samples: Sequence[SessionBlinkSample],
    config: ReadoutMetricConfig,
) -> float:
    """Compute per-session blink baseline from explicit baseline fields or early window."""

    if not samples:
        return 0.1

    explicit = [sample.blink_baseline_rate for sample in samples if sample.blink_baseline_rate is not None]
    if explicit:
        return max(mean([float(value) for value in explicit]), 1e-3)

    sorted_samples = sorted(samples, key=lambda sample: sample.video_time_ms)
    window_start = sorted_samples[0].video_time_ms
    window_end = window_start + config.baseline_window_ms
    baseline_window = [
        sample
        for sample in sorted_samples
        if sample.video_time_ms <= window_end
    ]
    if len(baseline_window) < 2:
        baseline_window = sorted_samples

    blink_count = sum(int(sample.blink) for sample in baseline_window)
    duration_ms = max(
        baseline_window[-1].video_time_ms - baseline_window[0].video_time_ms,
        estimate_window_ms([sample.video_time_ms for sample in baseline_window]),
    )
    duration_sec = max(duration_ms / 1000.0, 0.001)
    baseline_rate = blink_count / duration_sec
    return max(float(baseline_rate), 1e-3)


def compute_blink_inhibition(current_rate: float, baseline_rate: float) -> float:
    """Baseline-relative blink inhibition score in [-1, 1]."""

    normalized = (baseline_rate - current_rate) / max(baseline_rate, 1e-3)
    return clamp(float(normalized), -1.0, 1.0)


def compute_attention_velocity(
    attention_scores: Sequence[float],
    window_ms: int,
    config: ReadoutMetricConfig,
) -> List[float]:
    """Compute smoothed first derivative (delta/sec) for attention series."""

    if not attention_scores:
        return []
    seconds = max(float(window_ms) / 1000.0, 0.001)
    alpha = clamp(config.velocity_smoothing_alpha, 0.0, 1.0)
    raw: List[float] = [0.0]
    for index in range(1, len(attention_scores)):
        raw.append((attention_scores[index] - attention_scores[index - 1]) / seconds)

    smoothed: List[float] = []
    running = 0.0
    for index, value in enumerate(raw):
        if index == 0:
            running = value
        else:
            running = alpha * value + (1.0 - alpha) * running
        smoothed.append(running)
    return smoothed


def compute_quality_weight(
    tracking_confidence: Optional[float],
    quality_score: Optional[float],
    config: ReadoutMetricConfig,
) -> float:
    """Return quality/confidence weighting in [quality_min_weight, 1]."""

    parts = [
        float(value)
        for value in [tracking_confidence, quality_score]
        if value is not None
    ]
    if not parts:
        return 1.0
    base = clamp(mean(parts), 0.0, 1.0)
    min_weight = clamp(config.quality_min_weight, 0.0, 1.0)
    return min_weight + ((1.0 - min_weight) * base)


def compute_tracking_confidence(
    *,
    quality_confidence: Optional[float],
    face_presence_confidence: Optional[float],
    landmarks_confidence: Optional[float],
    gaze_on_screen_confidence: Optional[float],
    head_pose_confidence: Optional[float],
    au_confidence: Optional[float],
) -> Optional[float]:
    """Blend available confidence channels into a single tracking confidence."""

    values = [
        value
        for value in [
            quality_confidence,
            face_presence_confidence,
            landmarks_confidence,
            gaze_on_screen_confidence,
            head_pose_confidence,
            au_confidence,
        ]
        if value is not None
    ]
    if not values:
        return None
    return round(clamp(mean(values), 0.0, 1.0), 6)


def compute_head_pose_stability(
    *,
    yaw: Optional[float],
    pitch: Optional[float],
    roll: Optional[float],
    head_pose_valid_pct: Optional[float],
) -> Optional[float]:
    """Estimate coarse head-pose stability in [0, 1]."""

    if yaw is None and pitch is None and roll is None:
        return None
    magnitude = abs(yaw or 0.0) + abs(pitch or 0.0) + abs(roll or 0.0)
    # Treat summed absolute rotation around ~1.2 as very unstable.
    stability = clamp(1.0 - (magnitude / 1.2), 0.0, 1.0)
    if head_pose_valid_pct is not None:
        stability *= clamp(head_pose_valid_pct, 0.0, 1.0)
    return round(stability, 6)


def compute_attention_score(
    *,
    face_presence: Optional[float],
    head_pose_stability: Optional[float],
    gaze_on_screen: Optional[float],
    eye_openness: Optional[float],
    blink_inhibition: Optional[float],
    playback_continuity: Optional[float],
    au12: float,
    au6: float,
    au4: float,
    tracking_confidence: Optional[float],
    quality_score: Optional[float],
    config: ReadoutMetricConfig,
) -> float:
    """Compute interpretable attention proxy score on a 0-100 scale.

    Attention is intentionally dominated by passive viewing behavior and
    blink/continuity cues. Facial coding channels (AUs) are excluded from
    the score to keep attention and reward-proxy pathways distinct.
    """

    face_component = clamp(face_presence if face_presence is not None else 0.5, 0.0, 1.0)
    head_pose_component = clamp(
        head_pose_stability if head_pose_stability is not None else 0.5, 0.0, 1.0
    )
    gaze_component = clamp(gaze_on_screen if gaze_on_screen is not None else 0.5, 0.0, 1.0)
    eye_component = clamp(eye_openness if eye_openness is not None else 0.5, 0.0, 1.0)
    blink_component = clamp(0.5 + 0.5 * (blink_inhibition if blink_inhibition is not None else 0.0), 0.0, 1.0)
    playback_component = clamp(playback_continuity if playback_continuity is not None else 1.0, 0.0, 1.0)
    base_score = (
        config.attention_face_presence_weight * face_component
        + config.attention_head_pose_stability_weight * head_pose_component
        + config.attention_gaze_weight * gaze_component
        + config.attention_eye_openness_weight * eye_component
        + config.attention_blink_inhibition_weight * blink_component
        + config.attention_playback_continuity_weight * playback_component
    )
    quality_weight = compute_quality_weight(tracking_confidence, quality_score, config)
    return round(clamp(base_score * quality_weight * 100.0, 0.0, 100.0), 6)


def compute_reward_proxy_decomposition(
    *,
    attention_score: float,
    attention_velocity: float,
    au12: float,
    au6: float,
    au4: float,
    blink_rate: float,
    blink_baseline_rate: float,
    blink_inhibition: Optional[float],
    label_signal: float,
    dial: Optional[float],
    playback_continuity: Optional[float],
    scene_change_signal: Optional[float],
    telemetry_disruption: Optional[float],
    tracking_confidence: Optional[float],
    quality_score: Optional[float],
    config: ReadoutMetricConfig,
) -> RewardProxyDecomposition:
    """
    Compute calibrated reward decomposition (proxy/estimate, not direct biochemistry).

    The decomposition intentionally blends multiple passive channels with optional
    labels/telemetry and quality weighting to avoid single-signal overfitting.
    """

    velocity_component = clamp(abs(attention_velocity) / 12.0, 0.0, 1.0)
    baseline_rate = max(blink_baseline_rate, 1e-3)
    blink_ratio = clamp(blink_rate / baseline_rate, 0.0, 2.5)
    blink_activation = clamp((blink_ratio - 1.0) / 1.5, 0.0, 1.0)
    blink_rate_penalty = clamp((blink_ratio - 1.0) / 1.0, 0.0, 1.0)
    inhibition_component = clamp(
        0.5 + 0.5 * (blink_inhibition if blink_inhibition is not None else 0.0),
        0.0,
        1.0,
    )
    label_component = clamp(0.5 + 0.5 * label_signal, 0.0, 1.0)
    label_surprise_component = clamp(abs(label_signal), 0.0, 1.0)
    dial_component = clamp(dial / 100.0, 0.0, 1.0) if dial is not None else 0.5

    playback_component = clamp(
        playback_continuity if playback_continuity is not None else 1.0,
        0.0,
        1.0,
    )
    telemetry_disruption_component = clamp(
        telemetry_disruption
        if telemetry_disruption is not None
        else (1.0 - playback_component),
        0.0,
        1.0,
    )
    scene_change_component = clamp(scene_change_signal if scene_change_signal is not None else 0.0, 0.0, 1.0)

    au12_component = clamp(au12, 0.0, 1.0)
    au6_component = clamp(au6, 0.0, 1.0)
    au4_component = clamp(au4, 0.0, 1.0)
    au_positive_intensity = clamp((au12_component + au6_component) / 2.0, 0.0, 1.0)
    au_contrast_component = clamp(abs(au12_component - au4_component), 0.0, 1.0)
    facial_coding_component = clamp(
        0.35
        + config.reward_au12_weight * au12_component
        + config.reward_au6_weight * au6_component
        - config.reward_au4_penalty_weight * au4_component,
        0.0,
        1.0,
    )

    valence_raw = clamp(
        config.valence_bias
        + config.valence_au12_weight * au12_component
        + config.valence_au6_weight * au6_component
        - config.valence_au4_penalty_weight * au4_component
        + config.valence_label_weight * label_component
        + config.valence_blink_inhibition_weight * inhibition_component
        - config.valence_blink_rate_penalty_weight * blink_rate_penalty,
        0.0,
        1.0,
    )
    arousal_raw = clamp(
        config.arousal_bias
        + config.arousal_velocity_weight * velocity_component
        + config.arousal_blink_activation_weight * blink_activation
        + config.arousal_telemetry_disruption_weight * telemetry_disruption_component
        + config.arousal_au_intensity_weight * au_positive_intensity,
        0.0,
        1.0,
    )
    novelty_raw = clamp(
        config.novelty_bias
        + config.novelty_velocity_weight * velocity_component
        + config.novelty_scene_change_weight * scene_change_component
        + config.novelty_telemetry_disruption_weight * telemetry_disruption_component
        + config.novelty_label_surprise_weight * label_surprise_component
        + config.novelty_au_contrast_weight * au_contrast_component,
        0.0,
        1.0,
    )
    reward_raw = clamp(
        config.reward_valence_weight * valence_raw
        + config.reward_arousal_weight * arousal_raw
        + config.reward_novelty_weight * novelty_raw
        + config.reward_facial_coding_weight * facial_coding_component
        + config.reward_blink_inhibition_weight * inhibition_component
        - config.reward_blink_rate_penalty_weight * blink_rate_penalty
        + config.reward_label_weight * label_component
        + config.reward_dial_weight * dial_component
        + config.reward_playback_continuity_weight * playback_component,
        0.0,
        1.0,
    )

    quality_weight = compute_quality_weight(tracking_confidence, quality_score, config)
    return RewardProxyDecomposition(
        reward_proxy=round(clamp(reward_raw * quality_weight * 100.0, 0.0, 100.0), 6),
        valence_proxy=round(clamp(valence_raw * quality_weight * 100.0, 0.0, 100.0), 6),
        arousal_proxy=round(clamp(arousal_raw * quality_weight * 100.0, 0.0, 100.0), 6),
        novelty_proxy=round(clamp(novelty_raw * quality_weight * 100.0, 0.0, 100.0), 6),
        quality_weight=round(quality_weight, 6),
    )


def compute_reward_proxy(
    *,
    attention_score: float,
    au12: float,
    au6: float,
    au4: float,
    blink_rate: float,
    blink_baseline_rate: float,
    blink_inhibition: Optional[float],
    label_signal: float,
    dial: Optional[float],
    tracking_confidence: Optional[float],
    quality_score: Optional[float],
    config: ReadoutMetricConfig,
) -> float:
    """
    Compute calibrated reward proxy (not direct neurochemical measurement).

    Combines passive signals (AUs + blink dynamics + attention proxy) with
    optional explicit labels and dial signal when available.
    """

    decomposition = compute_reward_proxy_decomposition(
        attention_score=attention_score,
        attention_velocity=0.0,
        au12=au12,
        au6=au6,
        au4=au4,
        blink_rate=blink_rate,
        blink_baseline_rate=blink_baseline_rate,
        blink_inhibition=blink_inhibition,
        label_signal=label_signal,
        dial=dial,
        playback_continuity=1.0,
        scene_change_signal=0.0,
        telemetry_disruption=None,
        tracking_confidence=tracking_confidence,
        quality_score=quality_score,
        config=config,
    )
    return decomposition.reward_proxy


def build_attention_change_segments(
    points: Sequence[SegmentPoint],
    *,
    positive: bool,
    window_ms: int,
    config: ReadoutMetricConfig,
) -> List[Dict[str, float | int | List[str]]]:
    """Build sustained gain/loss windows relative to local baseline."""

    segments: List[Dict[str, float | int | List[str]]] = []
    if not points:
        return segments

    local_points = max(config.local_baseline_points, 1)
    threshold = config.gain_threshold if positive else config.loss_threshold
    min_windows = max(config.min_segment_windows, 1)

    active_start_index: Optional[int] = None
    active_end_index: Optional[int] = None
    active_deviation: List[float] = []
    active_confidence: List[float] = []

    for index, point in enumerate(points):
        baseline_start = max(0, index - local_points)
        baseline_window = [points[offset].attention_score for offset in range(baseline_start, index)]
        if not baseline_window:
            baseline_window = [point.attention_score]
        local_baseline = mean(baseline_window)
        deviation = point.attention_score - local_baseline
        condition = (
            deviation >= threshold and point.attention_velocity > 0
            if positive
            else deviation <= -threshold and point.attention_velocity < 0
        )

        if condition:
            if active_start_index is None:
                active_start_index = index
            active_end_index = index
            active_deviation.append(abs(deviation))
            if point.tracking_confidence is not None:
                active_confidence.append(float(point.tracking_confidence))
        else:
            if (
                active_start_index is not None
                and active_end_index is not None
                and (active_end_index - active_start_index + 1) >= min_windows
            ):
                segments.append(
                    {
                        "start_video_time_ms": points[active_start_index].video_time_ms,
                        "end_video_time_ms": points[active_end_index].video_time_ms + window_ms,
                        "magnitude": round(mean(active_deviation), 6),
                        "confidence": round(mean(active_confidence), 6)
                        if active_confidence
                        else 0.0,
                        "reason_codes": (
                            ["above_local_baseline", "upward_velocity"]
                            if positive
                            else ["below_local_baseline", "downward_velocity"]
                        ),
                    }
                )
            active_start_index = None
            active_end_index = None
            active_deviation = []
            active_confidence = []

    if (
        active_start_index is not None
        and active_end_index is not None
        and (active_end_index - active_start_index + 1) >= min_windows
    ):
        segments.append(
            {
                "start_video_time_ms": points[active_start_index].video_time_ms,
                "end_video_time_ms": points[active_end_index].video_time_ms + window_ms,
                "magnitude": round(mean(active_deviation), 6),
                "confidence": round(mean(active_confidence), 6) if active_confidence else 0.0,
                "reason_codes": (
                    ["above_local_baseline", "upward_velocity"]
                    if positive
                    else ["below_local_baseline", "downward_velocity"]
                ),
            }
        )

    return segments


def _resolve_scene_for_time(
    scenes: Sequence[DiagnosticScene],
    video_time_ms: int,
) -> Optional[DiagnosticScene]:
    if not scenes:
        return None
    for scene in scenes:
        if scene.start_ms <= video_time_ms < scene.end_ms:
            return scene
    if video_time_ms < scenes[0].start_ms:
        return scenes[0]
    return scenes[-1]


def _build_scene_diagnostic_card(
    *,
    card_type: DiagnosticCardType,
    scene: Optional[DiagnosticScene],
    start_ms: int,
    end_ms: int,
    primary_metric: str,
    primary_metric_value: float,
    why_flagged: str,
    confidence: Optional[float],
    reason_codes: Sequence[str],
    cta_id: Optional[str] = None,
) -> SceneDiagnosticCardData:
    return SceneDiagnosticCardData(
        card_type=card_type,
        scene_index=scene.scene_index if scene is not None else None,
        scene_id=scene.scene_id if scene is not None else None,
        cut_id=scene.cut_id if scene is not None else None,
        cta_id=cta_id or (scene.cta_id if scene is not None else None),
        scene_label=scene.label if scene is not None else None,
        scene_thumbnail_url=scene.thumbnail_url if scene is not None else None,
        start_video_time_ms=max(0, int(start_ms)),
        end_video_time_ms=max(0, int(end_ms)),
        primary_metric=primary_metric,
        primary_metric_value=round(float(primary_metric_value), 6),
        why_flagged=why_flagged,
        confidence=round(float(confidence), 6) if confidence is not None else None,
        reason_codes=[str(code) for code in reason_codes],
    )


def build_scene_diagnostic_cards(
    *,
    scenes: Sequence[DiagnosticScene],
    points: Sequence[DiagnosticPoint],
    attention_gain_segments: Sequence[DiagnosticSegment],
    attention_loss_segments: Sequence[DiagnosticSegment],
    confusion_segments: Sequence[DiagnosticSegment],
    cta_markers: Sequence[DiagnosticCtaMarker],
    window_ms: int,
) -> List[SceneDiagnosticCardData]:
    """Build editor-facing scene diagnostics from readout traces and segments."""

    sorted_scenes = sorted(scenes, key=lambda item: item.start_ms)
    sorted_points = sorted(points, key=lambda item: item.video_time_ms)
    scene_by_id = {
        scene.scene_id: scene
        for scene in sorted_scenes
        if scene.scene_id is not None
    }
    scene_points: Dict[int, List[DiagnosticPoint]] = {scene.scene_index: [] for scene in sorted_scenes}

    for point in sorted_points:
        scene = scene_by_id.get(point.scene_id) if point.scene_id is not None else None
        if scene is None:
            scene = _resolve_scene_for_time(sorted_scenes, point.video_time_ms)
        if scene is None:
            continue
        scene_points.setdefault(scene.scene_index, []).append(point)

    stats_by_scene: Dict[int, Dict[str, float | Optional[float]]] = {}
    for scene in sorted_scenes:
        points_in_scene = scene_points.get(scene.scene_index, [])
        if not points_in_scene:
            continue
        attentions = [point.attention_score for point in points_in_scene]
        rewards = [point.reward_proxy for point in points_in_scene]
        velocities = [point.attention_velocity for point in points_in_scene]
        au4_values = [point.au4 for point in points_in_scene]
        confidences = [point.tracking_confidence for point in points_in_scene if point.tracking_confidence is not None]
        stats_by_scene[scene.scene_index] = {
            "mean_attention": mean(attentions),
            "mean_reward": mean(rewards),
            "mean_velocity": mean(velocities),
            "mean_au4": mean(au4_values),
            "retention_delta": points_in_scene[-1].attention_score - points_in_scene[0].attention_score,
            "confidence": mean(confidences) if confidences else None,
        }

    cards: List[SceneDiagnosticCardData] = []

    # 1) golden_scene
    if stats_by_scene:
        golden_scene = max(
            stats_by_scene.items(),
            key=lambda item: (
                0.65 * float(item[1]["mean_reward"])
                + 0.35 * float(item[1]["mean_attention"])
                + max(0.0, float(item[1]["retention_delta"])) * 0.8
            ),
        )
        golden_scene_obj = next(scene for scene in sorted_scenes if scene.scene_index == golden_scene[0])
        golden_stats = golden_scene[1]
        cards.append(
            _build_scene_diagnostic_card(
                card_type="golden_scene",
                scene=golden_scene_obj,
                start_ms=golden_scene_obj.start_ms,
                end_ms=golden_scene_obj.end_ms,
                primary_metric="reward_proxy",
                primary_metric_value=float(golden_stats["mean_reward"]),
                why_flagged="Highest sustained reward proxy with strong attention retention in this scene.",
                confidence=golden_stats["confidence"],  # type: ignore[arg-type]
                reason_codes=["high_reward_proxy", "attention_retention"],
            )
        )

    # 2) hook_strength (opening window / first scene)
    first_scene = sorted_scenes[0] if sorted_scenes else None
    if first_scene is not None and first_scene.scene_index in stats_by_scene:
        first_stats = stats_by_scene[first_scene.scene_index]
        hook_strength = (
            0.6 * float(first_stats["mean_attention"])
            + 0.4 * float(first_stats["mean_reward"])
            + max(0.0, float(first_stats["retention_delta"])) * 3.0
        )
        cards.append(
            _build_scene_diagnostic_card(
                card_type="hook_strength",
                scene=first_scene,
                start_ms=first_scene.start_ms,
                end_ms=first_scene.end_ms,
                primary_metric="hook_strength",
                primary_metric_value=hook_strength,
                why_flagged=(
                    "Opening window retained attention well."
                    if float(first_stats["retention_delta"]) >= 0
                    else "Opening window showed early attention leakage."
                ),
                confidence=first_stats["confidence"],  # type: ignore[arg-type]
                reason_codes=[
                    "opening_window",
                    "positive_attention_retention" if float(first_stats["retention_delta"]) >= 0 else "early_attention_drop",
                ],
            )
        )

    # 3) cta_receptivity (lead-in + on-CTA window)
    if cta_markers:
        cta_marker = sorted(cta_markers, key=lambda item: item.video_time_ms)[0]
        lead_in_start = max(0, cta_marker.video_time_ms - (2 * window_ms))
        cta_window_end = cta_marker.video_time_ms + window_ms
        cta_points = [
            point
            for point in sorted_points
            if lead_in_start <= point.video_time_ms <= cta_window_end
        ]
        receptivity = (
            mean([(0.55 * point.attention_score) + (0.45 * point.reward_proxy) for point in cta_points])
            if cta_points
            else 0.0
        )
        cta_conf = mean([point.tracking_confidence for point in cta_points if point.tracking_confidence is not None]) if cta_points else None
        cta_scene = (
            scene_by_id.get(cta_marker.scene_id)
            if cta_marker.scene_id is not None
            else _resolve_scene_for_time(sorted_scenes, cta_marker.video_time_ms)
        )
        cards.append(
            _build_scene_diagnostic_card(
                card_type="cta_receptivity",
                scene=cta_scene,
                start_ms=lead_in_start,
                end_ms=cta_window_end,
                primary_metric="cta_receptivity",
                primary_metric_value=receptivity,
                why_flagged=(
                    "CTA lead-in and CTA window showed strong attention/reward response."
                    if receptivity >= 55
                    else "CTA lead-in and CTA window showed weak response."
                ),
                confidence=cta_conf,
                reason_codes=["cta_lead_in_window", "cta_on_window"],
                cta_id=cta_marker.cta_id,
            )
        )
    else:
        cards.append(
            _build_scene_diagnostic_card(
                card_type="cta_receptivity",
                scene=None,
                start_ms=0,
                end_ms=0,
                primary_metric="cta_receptivity",
                primary_metric_value=0.0,
                why_flagged="CTA marker unavailable for this video.",
                confidence=None,
                reason_codes=["cta_marker_missing"],
            )
        )

    # 4) attention_drop_scene (largest sustained negative delta)
    top_drop_segment = (
        max(attention_loss_segments, key=lambda segment: segment.magnitude)
        if attention_loss_segments
        else None
    )
    drop_scene: Optional[DiagnosticScene] = None
    drop_end_ms = 0
    if top_drop_segment is not None:
        drop_midpoint = int((top_drop_segment.start_video_time_ms + top_drop_segment.end_video_time_ms) / 2)
        drop_scene = (
            scene_by_id.get(top_drop_segment.scene_id)
            if top_drop_segment.scene_id is not None
            else _resolve_scene_for_time(sorted_scenes, drop_midpoint)
        )
        drop_end_ms = top_drop_segment.end_video_time_ms
        cards.append(
            _build_scene_diagnostic_card(
                card_type="attention_drop_scene",
                scene=drop_scene,
                start_ms=top_drop_segment.start_video_time_ms,
                end_ms=top_drop_segment.end_video_time_ms,
                primary_metric="attention_drop_magnitude",
                primary_metric_value=top_drop_segment.magnitude,
                why_flagged="Largest sustained negative attention delta observed in this scene.",
                confidence=top_drop_segment.confidence,
                reason_codes=top_drop_segment.reason_codes,
                cta_id=top_drop_segment.cta_id,
            )
        )
    elif stats_by_scene:
        drop_scene_idx, drop_stats = min(
            stats_by_scene.items(),
            key=lambda item: float(item[1]["retention_delta"]),
        )
        drop_scene = next(scene for scene in sorted_scenes if scene.scene_index == drop_scene_idx)
        drop_end_ms = drop_scene.end_ms
        cards.append(
            _build_scene_diagnostic_card(
                card_type="attention_drop_scene",
                scene=drop_scene,
                start_ms=drop_scene.start_ms,
                end_ms=drop_scene.end_ms,
                primary_metric="attention_drop_magnitude",
                primary_metric_value=max(0.0, -float(drop_stats["retention_delta"])),
                why_flagged="Scene with the weakest retention relative to local baseline.",
                confidence=drop_stats["confidence"],  # type: ignore[arg-type]
                reason_codes=["retention_drop"],
            )
        )

    # 5) confusion_scene (AU4/friction + falling attention)
    top_confusion_segment = (
        max(confusion_segments, key=lambda segment: segment.magnitude)
        if confusion_segments
        else None
    )
    if top_confusion_segment is not None:
        confusion_midpoint = int((top_confusion_segment.start_video_time_ms + top_confusion_segment.end_video_time_ms) / 2)
        confusion_scene = (
            scene_by_id.get(top_confusion_segment.scene_id)
            if top_confusion_segment.scene_id is not None
            else _resolve_scene_for_time(sorted_scenes, confusion_midpoint)
        )
        cards.append(
            _build_scene_diagnostic_card(
                card_type="confusion_scene",
                scene=confusion_scene,
                start_ms=top_confusion_segment.start_video_time_ms,
                end_ms=top_confusion_segment.end_video_time_ms,
                primary_metric="friction_score",
                primary_metric_value=top_confusion_segment.magnitude,
                why_flagged="Friction indicators (AU4/blink + falling attention) were elevated in this scene.",
                confidence=top_confusion_segment.confidence,
                reason_codes=top_confusion_segment.reason_codes,
                cta_id=top_confusion_segment.cta_id,
            )
        )
    elif stats_by_scene:
        confusion_scene_idx, confusion_stats = max(
            stats_by_scene.items(),
            key=lambda item: (float(item[1]["mean_au4"]) * 100.0) + max(0.0, -float(item[1]["mean_velocity"]) * 5.0),
        )
        confusion_scene = next(scene for scene in sorted_scenes if scene.scene_index == confusion_scene_idx)
        friction_score = (float(confusion_stats["mean_au4"]) * 100.0) + max(
            0.0, -float(confusion_stats["mean_velocity"]) * 5.0
        )
        cards.append(
            _build_scene_diagnostic_card(
                card_type="confusion_scene",
                scene=confusion_scene,
                start_ms=confusion_scene.start_ms,
                end_ms=confusion_scene.end_ms,
                primary_metric="friction_score",
                primary_metric_value=friction_score,
                why_flagged="Scene shows the strongest friction proxy profile (AU4 + velocity pattern).",
                confidence=confusion_stats["confidence"],  # type: ignore[arg-type]
                reason_codes=["au4_friction_proxy", "negative_attention_velocity"],
            )
        )

    # 6) recovery_scene (restored attention after a drop)
    recovery_candidates = [
        segment
        for segment in attention_gain_segments
        if segment.start_video_time_ms >= drop_end_ms
    ]
    recovery_added = False
    if recovery_candidates:
        recovery_segment = max(recovery_candidates, key=lambda segment: segment.magnitude)
        recovery_midpoint = int((recovery_segment.start_video_time_ms + recovery_segment.end_video_time_ms) / 2)
        recovery_scene = (
            scene_by_id.get(recovery_segment.scene_id)
            if recovery_segment.scene_id is not None
            else _resolve_scene_for_time(sorted_scenes, recovery_midpoint)
        )
        cards.append(
            _build_scene_diagnostic_card(
                card_type="recovery_scene",
                scene=recovery_scene,
                start_ms=recovery_segment.start_video_time_ms,
                end_ms=recovery_segment.end_video_time_ms,
                primary_metric="attention_recovery_magnitude",
                primary_metric_value=recovery_segment.magnitude,
                why_flagged="Attention recovered after the largest drop in this later segment.",
                confidence=recovery_segment.confidence,
                reason_codes=list(recovery_segment.reason_codes) + ["post_drop_recovery"],
                cta_id=recovery_segment.cta_id,
            )
        )
        recovery_added = True
    elif stats_by_scene:
        fallback_recovery = [
            (scene_index, stats)
            for scene_index, stats in stats_by_scene.items()
            if float(stats["retention_delta"]) > 0
            and (not drop_scene or scene_index != drop_scene.scene_index)
            and (
                not drop_scene
                or next(scene for scene in sorted_scenes if scene.scene_index == scene_index).start_ms >= drop_end_ms
            )
        ]
        if fallback_recovery:
            recovery_scene_idx, recovery_stats = max(
                fallback_recovery,
                key=lambda item: float(item[1]["retention_delta"]),
            )
            recovery_scene = next(scene for scene in sorted_scenes if scene.scene_index == recovery_scene_idx)
            cards.append(
                _build_scene_diagnostic_card(
                    card_type="recovery_scene",
                    scene=recovery_scene,
                    start_ms=recovery_scene.start_ms,
                    end_ms=recovery_scene.end_ms,
                    primary_metric="attention_recovery_magnitude",
                    primary_metric_value=float(recovery_stats["retention_delta"]),
                    why_flagged="Later scene restored attention after earlier losses.",
                    confidence=recovery_stats["confidence"],  # type: ignore[arg-type]
                    reason_codes=["post_drop_recovery", "positive_attention_velocity"],
                )
            )
            recovery_added = True

    if not recovery_added:
        cards.append(
            _build_scene_diagnostic_card(
                card_type="recovery_scene",
                scene=None,
                start_ms=max(0, int(drop_end_ms)),
                end_ms=max(0, int(drop_end_ms + window_ms)),
                primary_metric="attention_recovery_magnitude",
                primary_metric_value=0.0,
                why_flagged="No clear post-drop recovery window was detected in this selection.",
                confidence=None,
                reason_codes=["no_recovery_detected"],
            )
        )

    return cards
