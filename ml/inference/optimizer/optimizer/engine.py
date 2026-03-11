"""Rule engine for generating edit suggestions from video summaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import OptimizationResult, SceneBoundary, Suggestion, TracePoint
from .scoring import BASE_RULE_UPLIFT, aggregate_total_delta, predict_delta, priority_from_delta


@dataclass(frozen=True)
class OptimizerConfig:
    """Configurable thresholds for heuristic rules."""

    dead_zone_attention_threshold: float = 40.0
    dead_zone_min_duration_sec: int = 3
    confusion_window_sec: int = 2
    confusion_blink_delta_threshold: float = 0.06
    confusion_au4_delta_threshold: float = 0.03
    confusion_min_duration_sec: int = 2
    late_peak_min_fraction: float = 0.6
    late_peak_strength_percentile: float = 0.8
    cut_alignment_tolerance_sec: float = 1.0
    cut_min_boundary_signal: float = 0.2
    blink_rebound_threshold: float = 0.08


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * _clamp(q, 0.0, 1.0)))
    return float(ordered[index])


def _scale_to_100(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    if math.isclose(vmin, vmax):
        return [50.0 for _ in values]
    return [((value - vmin) / (vmax - vmin)) * 100.0 for value in values]


def _extract_scenes(summary: Mapping[str, Any]) -> List[SceneBoundary]:
    scenes_raw = summary.get("scene_metrics") or summary.get("scene_boundaries") or []
    scenes: List[SceneBoundary] = []

    for index, row in enumerate(scenes_raw):
        if not isinstance(row, Mapping):
            continue
        start_ms = int(_safe_float(row.get("start_ms"), index * 1000))
        end_ms = int(_safe_float(row.get("end_ms"), start_ms + 1000))
        if end_ms <= start_ms:
            continue

        label = row.get("label")
        scenes.append(
            SceneBoundary(
                start_sec=max(start_ms // 1000, 0),
                end_sec=max(int(math.ceil(end_ms / 1000.0)), (start_ms // 1000) + 1),
                label=label if isinstance(label, str) else None,
            )
        )

    return sorted(scenes, key=lambda scene: scene.start_sec)


def _normalize_trace_points(summary: Mapping[str, Any]) -> List[TracePoint]:
    buckets = summary.get("trace_buckets") or summary.get("traces") or []
    if not isinstance(buckets, list):
        return []

    raw_rows: List[Dict[str, float]] = []
    provided_attention: List[Optional[float]] = []
    raw_attention_proxy: List[float] = []

    for index, bucket in enumerate(buckets):
        if not isinstance(bucket, Mapping):
            continue

        t_ms = int(_safe_float(bucket.get("bucket_start_ms", bucket.get("t_ms", index * 1000))))
        t_sec = max(int(round(t_ms / 1000.0)), 0)

        au_norm = bucket.get("mean_au_norm") or bucket.get("au_norm") or {}
        if not isinstance(au_norm, Mapping):
            au_norm = {}

        blink_rate = _safe_float(bucket.get("blink_rate", bucket.get("blink", 0.0)))
        brightness = _safe_float(bucket.get("mean_brightness", bucket.get("brightness", 0.0)))
        motion = _safe_float(
            bucket.get("motion_magnitude", bucket.get("motion", bucket.get("mean_motion", 0.0)))
        )

        au4 = _safe_float(bucket.get("au4", au_norm.get("AU04", 0.0)))
        au6 = _safe_float(bucket.get("au6", au_norm.get("AU06", 0.0)))
        au12 = _safe_float(bucket.get("au12", au_norm.get("AU12", 0.0)))

        reward_proxy_raw = _optional_float(bucket.get("reward_proxy"))
        attention_raw = _optional_float(bucket.get("attention"))

        proxy = (au12 * 0.55) + (au6 * 0.35) - (au4 * 0.2) - (blink_rate * 0.45)

        raw_rows.append(
            {
                "t_sec": float(t_sec),
                "blink_rate": blink_rate,
                "brightness": brightness,
                "motion": motion,
                "au4": au4,
                "au6": au6,
                "au12": au12,
                "reward_proxy_raw": reward_proxy_raw if reward_proxy_raw is not None else float("nan"),
            }
        )
        provided_attention.append(attention_raw)
        raw_attention_proxy.append(proxy)

    if not raw_rows:
        return []

    scaled_proxy_attention = _scale_to_100(raw_attention_proxy)

    provided_values = [value for value in provided_attention if value is not None]
    provided_in_unit_interval = bool(provided_values) and max(provided_values) <= 1.0

    for row, att_raw, proxy_attention in zip(raw_rows, provided_attention, scaled_proxy_attention):
        if att_raw is None:
            attention = proxy_attention
        else:
            attention = att_raw * 100.0 if provided_in_unit_interval else att_raw
        row["attention"] = _clamp(attention, 0.0, 100.0)

        reward_raw = row.pop("reward_proxy_raw")
        if isinstance(reward_raw, float) and not math.isnan(reward_raw):
            reward_proxy = reward_raw
        else:
            reward_proxy = row["attention"] * 0.7 + max(row["au12"], 0.0) * 30.0 - max(row["au4"], 0.0) * 15.0
        row["reward_proxy"] = _clamp(reward_proxy, 0.0, 100.0)

    if all(math.isclose(row["motion"], 0.0, abs_tol=1e-8) for row in raw_rows):
        prev_brightness = raw_rows[0]["brightness"]
        for row in raw_rows:
            row["motion"] = abs(row["brightness"] - prev_brightness)
            prev_brightness = row["brightness"]

    grouped: Dict[int, List[Dict[str, float]]] = {}
    for row in raw_rows:
        grouped.setdefault(int(row["t_sec"]), []).append(row)

    points: List[TracePoint] = []
    for t_sec in sorted(grouped):
        rows = grouped[t_sec]
        points.append(
            TracePoint(
                t_sec=t_sec,
                attention=_mean([r["attention"] for r in rows]),
                blink_rate=_mean([r["blink_rate"] for r in rows]),
                au4=_mean([r["au4"] for r in rows]),
                au6=_mean([r["au6"] for r in rows]),
                au12=_mean([r["au12"] for r in rows]),
                motion=_mean([r["motion"] for r in rows]),
                brightness=_mean([r["brightness"] for r in rows]),
                reward_proxy=_mean([r["reward_proxy"] for r in rows]),
            )
        )

    return points


def _scene_label_at(second: int, scenes: Sequence[SceneBoundary]) -> Optional[str]:
    for scene in scenes:
        if scene.start_sec <= second < scene.end_sec:
            return scene.label
    return None


def _group_consecutive_seconds(seconds: Iterable[int]) -> List[Tuple[int, int, List[int]]]:
    ordered = sorted(set(seconds))
    if not ordered:
        return []

    groups: List[Tuple[int, int, List[int]]] = []
    current = [ordered[0]]

    for value in ordered[1:]:
        if value - current[-1] <= 1:
            current.append(value)
        else:
            groups.append((current[0], current[-1], current.copy()))
            current = [value]

    groups.append((current[0], current[-1], current.copy()))
    return groups


def _detect_dead_zones(
    points: Sequence[TracePoint],
    scenes: Sequence[SceneBoundary],
    config: OptimizerConfig,
) -> List[Suggestion]:
    threshold = config.dead_zone_attention_threshold
    below_threshold_seconds = [point.t_sec for point in points if point.attention < threshold]
    groups = _group_consecutive_seconds(below_threshold_seconds)

    output: List[Suggestion] = []
    for index, (start_sec, end_sec, seconds) in enumerate(groups):
        duration = end_sec - start_sec + 1
        if duration < config.dead_zone_min_duration_sec:
            continue

        segment = [point for point in points if point.t_sec in seconds]
        mean_attention = _mean([point.attention for point in segment])
        drop = max(threshold - mean_attention, 0.0)

        severity = _clamp((drop / max(threshold, 1.0)) * 0.75 + min(duration / 8.0, 1.0) * 0.45, 0.0, 1.5)
        confidence = _clamp(0.68 + min(duration / 12.0, 0.22), 0.0, 1.0)
        position_weight = 1.1 if start_sec <= points[-1].t_sec * 0.5 else 1.0

        delta = predict_delta(
            rule="dead_zone",
            severity=severity,
            confidence=confidence,
            position_weight=position_weight,
            evidence_weight=1.0,
        )
        output.append(
            Suggestion(
                id=f"dead-zone-{index + 1}",
                rule="dead_zone",
                label="Dead zone",
                start_sec=start_sec,
                end_sec=end_sec,
                scene_label=_scene_label_at(start_sec, scenes),
                recommendation="Tighten pacing in this interval by trimming pauses or compressing low-signal shots.",
                rationale="Attention remains below threshold for a sustained interval (>2s).",
                severity=round(severity, 4),
                confidence=round(confidence, 4),
                predicted_delta_engagement=delta,
                priority=priority_from_delta(delta),
                evidence={
                    "duration_sec": duration,
                    "attention_threshold": round(threshold, 4),
                    "mean_attention": round(mean_attention, 4),
                },
            )
        )

    return output


def _detect_confusion_friction(
    points: Sequence[TracePoint],
    scenes: Sequence[SceneBoundary],
    config: OptimizerConfig,
) -> List[Suggestion]:
    if len(points) <= config.confusion_window_sec:
        return []

    flagged: List[int] = []
    blink_deltas: Dict[int, float] = {}
    au4_deltas: Dict[int, float] = {}

    window = max(config.confusion_window_sec, 1)
    for index in range(window, len(points)):
        current = points[index]
        history = points[index - window : index]

        blink_delta = current.blink_rate - _mean([item.blink_rate for item in history])
        au4_delta = current.au4 - _mean([item.au4 for item in history])

        if (
            blink_delta >= config.confusion_blink_delta_threshold
            and au4_delta >= config.confusion_au4_delta_threshold
        ):
            flagged.append(current.t_sec)
            blink_deltas[current.t_sec] = blink_delta
            au4_deltas[current.t_sec] = au4_delta

    groups = _group_consecutive_seconds(flagged)

    output: List[Suggestion] = []
    for index, (start_sec, end_sec, seconds) in enumerate(groups):
        duration = end_sec - start_sec + 1
        if duration < config.confusion_min_duration_sec:
            continue

        mean_blink_delta = _mean([blink_deltas[second] for second in seconds])
        mean_au4_delta = _mean([au4_deltas[second] for second in seconds])

        severity = _clamp(
            (mean_blink_delta / max(config.confusion_blink_delta_threshold, 1e-6)) * 0.35
            + (mean_au4_delta / max(config.confusion_au4_delta_threshold, 1e-6)) * 0.35
            + min(duration / 6.0, 1.0) * 0.3,
            0.0,
            1.5,
        )
        confidence = _clamp(0.62 + min(duration / 10.0, 0.15), 0.0, 1.0)
        position_weight = 1.08 if start_sec <= points[-1].t_sec * 0.5 else 1.0

        delta = predict_delta(
            rule="confusion_friction",
            severity=severity,
            confidence=confidence,
            position_weight=position_weight,
            evidence_weight=1.05,
        )
        output.append(
            Suggestion(
                id=f"confusion-friction-{index + 1}",
                rule="confusion_friction",
                label="Confusion/friction",
                start_sec=start_sec,
                end_sec=end_sec,
                scene_label=_scene_label_at(start_sec, scenes),
                recommendation="Clarify shot intent or voice-over in this segment to reduce cognitive friction.",
                rationale="Blink rate and AU4 rise together, indicating processing strain.",
                severity=round(severity, 4),
                confidence=round(confidence, 4),
                predicted_delta_engagement=delta,
                priority=priority_from_delta(delta),
                evidence={
                    "duration_sec": duration,
                    "mean_blink_delta": round(mean_blink_delta, 4),
                    "mean_au4_delta": round(mean_au4_delta, 4),
                },
            )
        )

    return output


def _detect_late_hook(
    points: Sequence[TracePoint],
    scenes: Sequence[SceneBoundary],
    config: OptimizerConfig,
) -> List[Suggestion]:
    if not points:
        return []

    reward_values = [point.reward_proxy for point in points]
    peak_index = max(range(len(points)), key=lambda idx: reward_values[idx])
    peak_point = points[peak_index]

    duration_sec = max(points[-1].t_sec + 1, 1)
    late_cutoff = int(math.floor(duration_sec * config.late_peak_min_fraction))
    strength_threshold = _percentile(reward_values, config.late_peak_strength_percentile)

    if peak_point.t_sec <= late_cutoff:
        return []
    if peak_point.reward_proxy < strength_threshold:
        return []

    late_window = max(duration_sec - late_cutoff, 1)
    lateness_ratio = (peak_point.t_sec - late_cutoff) / late_window
    strength_ratio = (peak_point.reward_proxy - strength_threshold) / max(strength_threshold, 1.0)

    severity = _clamp(0.55 + (lateness_ratio * 0.45) + (strength_ratio * 0.35), 0.0, 1.5)
    confidence = _clamp(0.68 + min(lateness_ratio + strength_ratio, 1.0) * 0.22, 0.0, 1.0)

    delta = predict_delta(
        rule="late_hook",
        severity=severity,
        confidence=confidence,
        position_weight=1.25,
        evidence_weight=1.1,
    )

    target_earlier_sec = max(int(duration_sec * 0.2), 0)

    return [
        Suggestion(
            id="late-hook-1",
            rule="late_hook",
            label="Late reward hook",
            start_sec=peak_point.t_sec,
            end_sec=peak_point.t_sec,
            scene_label=_scene_label_at(peak_point.t_sec, scenes),
            recommendation=(
                "Move this reward-driving beat earlier to improve early retention and hook strength "
                f"(target near {target_earlier_sec}s)."
            ),
            rationale="A strong reward proxy peak appears late in the timeline.",
            severity=round(severity, 4),
            confidence=round(confidence, 4),
            predicted_delta_engagement=delta,
            priority=priority_from_delta(delta),
            evidence={
                "peak_second": peak_point.t_sec,
                "reward_peak": round(peak_point.reward_proxy, 4),
                "late_cutoff_second": late_cutoff,
                "reward_strength_threshold": round(strength_threshold, 4),
            },
        )
    ]


def _detect_natural_boundaries(
    points: Sequence[TracePoint],
    config: OptimizerConfig,
) -> Dict[int, float]:
    if len(points) < 2:
        return {}

    motion_jumps = [abs(points[i].motion - points[i - 1].motion) for i in range(1, len(points))]
    motion_threshold = _percentile(motion_jumps, 0.85)
    max_motion_jump = max(motion_jumps) if motion_jumps else 1.0

    blink_values = [point.blink_rate for point in points]
    blink_high_threshold = _percentile(blink_values, 0.7)

    boundaries: Dict[int, float] = {}

    for index in range(1, len(points)):
        current = points[index]
        previous = points[index - 1]

        jump = abs(current.motion - previous.motion)
        if jump >= motion_threshold and jump > 0.0:
            score = _clamp(jump / max(max_motion_jump, 1e-6), 0.0, 1.0)
            boundaries[current.t_sec] = max(boundaries.get(current.t_sec, 0.0), score)

        blink_drop = previous.blink_rate - current.blink_rate
        if previous.blink_rate >= blink_high_threshold and blink_drop >= config.blink_rebound_threshold:
            rebound_score = _clamp(blink_drop / max(previous.blink_rate, 1e-6), 0.0, 1.0)
            boundaries[current.t_sec] = max(boundaries.get(current.t_sec, 0.0), rebound_score)

    return boundaries


def _detect_cut_realignment(
    points: Sequence[TracePoint],
    scenes: Sequence[SceneBoundary],
    config: OptimizerConfig,
) -> List[Suggestion]:
    if len(scenes) <= 1:
        return []

    boundaries = _detect_natural_boundaries(points, config)
    if not boundaries:
        return []

    candidate_seconds = sorted(boundaries)
    output: List[Suggestion] = []

    for index, scene in enumerate(scenes[1:], start=1):
        cut_second = scene.start_sec

        nearest_second = min(candidate_seconds, key=lambda sec: abs(sec - cut_second))
        distance = abs(nearest_second - cut_second)
        signal_strength = boundaries[nearest_second]

        if distance <= config.cut_alignment_tolerance_sec:
            continue
        if signal_strength < config.cut_min_boundary_signal:
            continue

        severity = _clamp((distance / 6.0) * 0.7 + signal_strength * 0.5, 0.0, 1.5)
        confidence = _clamp(0.6 + signal_strength * 0.25, 0.0, 1.0)

        delta = predict_delta(
            rule="cut_realignment",
            severity=severity,
            confidence=confidence,
            position_weight=1.05,
            evidence_weight=1.0 + min(signal_strength * 0.2, 0.2),
        )

        shift_direction = "later" if nearest_second > cut_second else "earlier"

        output.append(
            Suggestion(
                id=f"cut-realignment-{index}",
                rule="cut_realignment",
                label="Cut realignment",
                start_sec=max(cut_second - 1, 0),
                end_sec=cut_second + 1,
                scene_label=scene.label,
                recommendation=(
                    f"Realign cut near {nearest_second}s ({distance}s {shift_direction}) to match natural "
                    "viewer transition signals."
                ),
                rationale="Scene boundary does not align with detected blink/motion event boundary.",
                severity=round(severity, 4),
                confidence=round(confidence, 4),
                predicted_delta_engagement=delta,
                priority=priority_from_delta(delta),
                evidence={
                    "cut_second": cut_second,
                    "suggested_second": nearest_second,
                    "distance_sec": distance,
                    "boundary_signal_strength": round(signal_strength, 4),
                },
            )
        )

    return output


def optimize_video_summary(
    summary_data: Mapping[str, Any],
    config: Optional[OptimizerConfig] = None,
) -> OptimizationResult:
    """Generate ranked edit suggestions from a summary payload."""

    cfg = config or OptimizerConfig()
    points = _normalize_trace_points(summary_data)
    if not points:
        raise ValueError("video_summary has no usable traces")

    scenes = _extract_scenes(summary_data)
    if not scenes:
        scenes = [SceneBoundary(start_sec=0, end_sec=points[-1].t_sec + 1, label="Full video")]

    suggestions: List[Suggestion] = []
    suggestions.extend(_detect_dead_zones(points, scenes, cfg))
    suggestions.extend(_detect_confusion_friction(points, scenes, cfg))
    suggestions.extend(_detect_late_hook(points, scenes, cfg))
    suggestions.extend(_detect_cut_realignment(points, scenes, cfg))

    suggestions.sort(key=lambda item: (item.predicted_delta_engagement, -item.start_sec), reverse=True)

    engagement_score_before = _mean([point.attention for point in points])
    total_delta = aggregate_total_delta(item.predicted_delta_engagement for item in suggestions)
    engagement_score_after = _clamp(engagement_score_before + total_delta, 0.0, 100.0)

    video_id = str(summary_data.get("video_id", "unknown-video"))

    return OptimizationResult(
        video_id=video_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        scoring_model={
            "rule_base_uplift": BASE_RULE_UPLIFT,
            "aggregation": "diminishing_returns: sum(delta_i * 0.88^i)",
        },
        baseline_metrics={
            "duration_sec": float(points[-1].t_sec + 1),
            "mean_attention": round(engagement_score_before, 4),
            "mean_blink_rate": round(_mean([point.blink_rate for point in points]), 4),
            "mean_reward_proxy": round(_mean([point.reward_proxy for point in points]), 4),
            "dead_zone_threshold": round(cfg.dead_zone_attention_threshold, 4),
        },
        engagement_score_before=round(engagement_score_before, 4),
        predicted_total_delta_engagement=round(total_delta, 4),
        engagement_score_after=round(engagement_score_after, 4),
        suggestions=suggestions,
    )
