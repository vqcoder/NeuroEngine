"""AU-level facial diagnostics for friction signals with quality-aware confidence handling."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import _weighted_mean, to_float, to_float_optional

from .schemas import (
    AuFrictionDiagnostics,
    AuFrictionPathway,
    AuFrictionQualityWarning,
    AuFrictionQualityWarningSeverity,
    AuFrictionState,
    AuFrictionTimelineWindow,
)


@dataclass(frozen=True)
class AuFrictionConfig:
    min_face_presence: float = 0.45
    min_head_pose_stability: float = 0.55
    max_occlusion_score: float = 0.55
    lighting_variance_threshold: float = 16.0
    low_light_rate_threshold: float = 0.35
    missing_face_window_threshold: int = 2
    fallback_confidence_cap: float = 0.58
    min_window_score_unit: float = 0.28
    amusement_window_threshold: float = 0.5
    transition_confusion_threshold: float = 0.42
    top_window_limit: int = 8


def resolve_au_friction_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> AuFrictionConfig:
    """Build AU friction config from env and optional per-video metadata."""

    config = AuFrictionConfig()
    settings_overrides = _parse_override_payload(get_settings().au_friction_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("au_friction_config", "auFrictionConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def compute_au_friction_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    window_ms: int,
    config: Optional[AuFrictionConfig] = None,
) -> AuFrictionDiagnostics:
    """Estimate AU friction windows and quality warnings from AU traces and face quality channels."""

    resolved = config or AuFrictionConfig()
    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    if not rows:
        return AuFrictionDiagnostics(
            pathway=AuFrictionPathway.insufficient_data,
            evidence_summary="No timeline buckets were available for AU friction diagnostics.",
            signals_used=[],
        )

    windows: List[AuFrictionTimelineWindow] = []
    warnings: List[AuFrictionQualityWarning] = []
    coverage_flags: List[bool] = []
    quality_flags_by_row: List[List[str]] = []
    brightness_values: List[float] = []
    confusion_values: List[float] = []
    strain_values: List[float] = []
    amusement_values: List[float] = []
    tension_values: List[float] = []
    resistance_values: List[float] = []
    window_scores: List[float] = []
    window_confidences: List[float] = []
    transition_spike_windows: List[tuple[int, int, float]] = []

    previous_row: Optional[Dict[str, object]] = None
    for row in rows:
        start_ms = int(to_float(row.get("bucket_start"), 0.0))
        end_ms = start_ms + max(int(window_ms), 1)
        au4 = _au_value(row, "AU04", "au4")
        au6 = _au_value(row, "AU06", "au6")
        au12 = _au_value(row, "AU12", "au12")
        au25 = _au_value(row, "AU25")
        au26 = _au_value(row, "AU26")
        au45 = _au_value(row, "AU45")

        attention_velocity = to_float(row.get("attention_velocity"), 0.0)
        playback_continuity = clamp(to_float(row.get("playback_continuity"), 1.0), 0.0, 1.0)
        face_presence = _clamp_optional(row.get("face_presence"))
        head_pose_stability = _clamp_optional(row.get("head_pose_stability"))
        tracking_confidence = _clamp_optional(row.get("tracking_confidence"))
        quality_score = _clamp_optional(row.get("quality_score"))
        occlusion_score = _clamp_optional(row.get("mean_occlusion_score"))
        if occlusion_score is None:
            occlusion_score = _clamp_optional(row.get("occlusion_score"))
        head_pose_valid_pct = _clamp_optional(row.get("mean_head_pose_valid_pct"))
        brightness_value = to_float_optional(row.get("mean_brightness"))
        if brightness_value is not None:
            brightness_values.append(brightness_value)

        row_quality_flags = [str(item) for item in (row.get("quality_flags") or [])]
        quality_flags_by_row.append(row_quality_flags)
        low_light_flag = "low_light" in row_quality_flags
        face_lost_flag = "face_lost" in row_quality_flags
        pose_flag = "high_yaw_pitch" in row_quality_flags

        confusion_signal = clamp(
            (0.46 * au4)
            + (0.2 * au25)
            + (0.18 * au26)
            + (0.16 * clamp(max(-attention_velocity, 0.0) / 8.0, 0.0, 1.0)),
            0.0,
            1.0,
        )
        strain_signal = clamp((0.62 * au4) + (0.22 * au25) + (0.16 * au45), 0.0, 1.0)
        amusement_signal = clamp((0.56 * au12) + (0.44 * au6) - (0.25 * au4), 0.0, 1.0)
        tension_signal = clamp(
            (0.5 * au4)
            + (0.22 * au45)
            + (0.14 * clamp(abs(attention_velocity) / 9.0, 0.0, 1.0))
            + (0.14 * (1.0 - playback_continuity)),
            0.0,
            1.0,
        )
        resistance_signal = clamp(
            (0.48 * au4)
            + (0.2 * au45)
            + (0.17 * clamp(max(-attention_velocity, 0.0) / 10.0, 0.0, 1.0))
            + (0.15 * (1.0 - playback_continuity)),
            0.0,
            1.0,
        )

        dominant_state = _dominant_state(
            confusion=confusion_signal,
            strain=strain_signal,
            amusement=amusement_signal,
            tension=tension_signal,
            resistance=resistance_signal,
        )
        negative_blend = (
            (0.34 * confusion_signal)
            + (0.26 * strain_signal)
            + (0.24 * tension_signal)
            + (0.16 * resistance_signal)
        )
        friction_unit = clamp(negative_blend - (0.12 * amusement_signal), 0.0, 1.0)

        face_coverage = (
            face_presence is not None
            and face_presence >= float(resolved.min_face_presence)
            and (not face_lost_flag)
        )
        coverage_flags.append(face_coverage)
        occlusion_quality = (
            1.0 - occlusion_score
            if occlusion_score is not None
            else (0.4 if face_lost_flag else None)
        )
        if occlusion_quality is not None:
            occlusion_quality = clamp(occlusion_quality, 0.0, 1.0)
        pose_quality = mean_optional([head_pose_stability, head_pose_valid_pct])
        if pose_flag:
            pose_quality = clamp((pose_quality or 0.45) * 0.7, 0.0, 1.0)
        lighting_quality = None
        if brightness_value is not None:
            lighting_quality = clamp((brightness_value - 25.0) / 65.0, 0.0, 1.0)
        elif low_light_flag:
            lighting_quality = 0.28

        local_quality = mean_optional(
            [tracking_confidence, quality_score, face_presence, pose_quality, occlusion_quality, lighting_quality]
        ) or 0.44
        confidence = clamp((0.72 * local_quality) + (0.28 * (1.0 if face_coverage else 0.45)), 0.0, 1.0)

        scene_change = False
        if previous_row is not None:
            scene_change = (
                (row.get("scene_id") is not None and previous_row.get("scene_id") is not None and row.get("scene_id") != previous_row.get("scene_id"))
                or (row.get("cut_id") is not None and previous_row.get("cut_id") is not None and row.get("cut_id") != previous_row.get("cut_id"))
            )
        transition_context = None
        if scene_change and confusion_signal >= float(resolved.transition_confusion_threshold):
            transition_context = "post_transition_spike"
            transition_spike_windows.append((start_ms, end_ms, confusion_signal))
            friction_unit = clamp(friction_unit + 0.08, 0.0, 1.0)

        include_window = (
            friction_unit >= float(resolved.min_window_score_unit)
            or amusement_signal >= float(resolved.amusement_window_threshold)
            or transition_context is not None
        )
        if include_window:
            windows.append(
                AuFrictionTimelineWindow(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    score=round(friction_unit * 100.0, 6),
                    confidence=round(confidence, 6),
                    reason=_window_reason(
                        dominant_state=dominant_state,
                        confusion=confusion_signal,
                        strain=strain_signal,
                        amusement=amusement_signal,
                        tension=tension_signal,
                        resistance=resistance_signal,
                        transition_context=transition_context,
                    ),
                    dominant_state=dominant_state,
                    transition_context=transition_context,
                    au04_signal=round(au4, 6),
                    au06_signal=round(au6, 6),
                    au12_signal=round(au12, 6),
                    au25_signal=round(au25, 6),
                    au26_signal=round(au26, 6),
                    au45_signal=round(au45, 6),
                    confusion_signal=round(confusion_signal, 6),
                    strain_signal=round(strain_signal, 6),
                    amusement_signal=round(amusement_signal, 6),
                    tension_signal=round(tension_signal, 6),
                    resistance_signal=round(resistance_signal, 6),
                )
            )
            window_scores.append(friction_unit * 100.0)
            window_confidences.append(confidence)

        confusion_values.append(confusion_signal)
        strain_values.append(strain_signal)
        amusement_values.append(amusement_signal)
        tension_values.append(tension_signal)
        resistance_values.append(resistance_signal)
        previous_row = row

    missing_windows = _find_missing_face_windows(
        rows=rows,
        coverage_flags=coverage_flags,
        window_ms=max(int(window_ms), 1),
        threshold=int(resolved.missing_face_window_threshold),
    )
    if missing_windows:
        start_ms, end_ms, window_count = missing_windows[0]
        warnings.append(
            AuFrictionQualityWarning(
                warning_key="missing_face_windows",
                severity=AuFrictionQualityWarningSeverity.high if window_count >= 3 else AuFrictionQualityWarningSeverity.medium,
                message="Face signal coverage dropped across consecutive windows; AU friction is downgraded in those periods.",
                start_ms=start_ms,
                end_ms=end_ms,
                metric_value=float(window_count),
            )
        )

    pose_issues = [
        int(to_float(row.get("bucket_start"), 0.0))
        for row, flags in zip(rows, quality_flags_by_row)
        if "high_yaw_pitch" in flags
        or (
            _clamp_optional(row.get("head_pose_stability")) is not None
            and _clamp_optional(row.get("head_pose_stability")) < float(resolved.min_head_pose_stability)
        )
    ]
    if pose_issues:
        warnings.append(
            AuFrictionQualityWarning(
                warning_key="unstable_head_pose",
                severity=AuFrictionQualityWarningSeverity.medium,
                message="Head-pose instability reduced facial feature reliability in some windows.",
                start_ms=min(pose_issues),
                end_ms=max(pose_issues) + max(int(window_ms), 1),
                metric_value=round(len(pose_issues) / float(max(len(rows), 1)), 6),
            )
        )

    occlusion_windows = [
        int(to_float(row.get("bucket_start"), 0.0))
        for row, flags in zip(rows, quality_flags_by_row)
        if "face_lost" in flags
        or (
            _clamp_optional(row.get("mean_occlusion_score")) is not None
            and _clamp_optional(row.get("mean_occlusion_score")) > float(resolved.max_occlusion_score)
        )
    ]
    if occlusion_windows:
        warnings.append(
            AuFrictionQualityWarning(
                warning_key="high_occlusion",
                severity=AuFrictionQualityWarningSeverity.medium,
                message="Occlusion/face-loss windows lowered confidence for AU diagnostics.",
                start_ms=min(occlusion_windows),
                end_ms=max(occlusion_windows) + max(int(window_ms), 1),
                metric_value=round(len(occlusion_windows) / float(max(len(rows), 1)), 6),
            )
        )

    low_light_rate = len(
        [
            flags
            for flags in quality_flags_by_row
            if "low_light" in flags
        ]
    ) / float(max(len(rows), 1))
    brightness_std = _std(brightness_values)
    if (
        (brightness_std is not None and brightness_std > float(resolved.lighting_variance_threshold))
        or low_light_rate >= float(resolved.low_light_rate_threshold)
    ):
        warnings.append(
            AuFrictionQualityWarning(
                warning_key="high_lighting_variance",
                severity=AuFrictionQualityWarningSeverity.medium,
                message="Lighting instability reduced consistency of AU-level friction interpretation.",
                metric_value=round(brightness_std if brightness_std is not None else low_light_rate, 6),
            )
        )

    if transition_spike_windows:
        start_ms = min(item[0] for item in transition_spike_windows)
        end_ms = max(item[1] for item in transition_spike_windows)
        max_signal = max(item[2] for item in transition_spike_windows)
        warnings.append(
            AuFrictionQualityWarning(
                warning_key="post_transition_confusion_spike",
                severity=AuFrictionQualityWarningSeverity.low,
                message="AU confusion signal rose after one or more scene/cut transitions.",
                start_ms=start_ms,
                end_ms=end_ms,
                metric_value=round(max_signal, 6),
            )
        )

    coverage_ratio = len([item for item in coverage_flags if item]) / float(max(len(rows), 1))
    pathway = (
        AuFrictionPathway.au_signal_model
        if coverage_ratio >= 0.45
        else AuFrictionPathway.fallback_proxy
    )
    if not windows:
        highest_row = max(
            rows,
            key=lambda row: _au_value(row, "AU04", "au4") + _au_value(row, "AU12", "au12"),
            default=None,
        )
        if highest_row is None:
            return AuFrictionDiagnostics(
                pathway=AuFrictionPathway.insufficient_data,
                evidence_summary="No AU evidence was available for AU friction diagnostics.",
                signals_used=[],
            )
        start_ms = int(to_float(highest_row.get("bucket_start"), 0.0))
        windows = [
            AuFrictionTimelineWindow(
                start_ms=start_ms,
                end_ms=start_ms + max(int(window_ms), 1),
                score=0.0,
                confidence=round(min(float(resolved.fallback_confidence_cap), 0.35), 6),
                reason="AU windows were sparse; score remained diagnostically unavailable.",
                dominant_state=AuFrictionState.confusion,
                au04_signal=round(_au_value(highest_row, "AU04", "au4"), 6),
                au06_signal=round(_au_value(highest_row, "AU06", "au6"), 6),
                au12_signal=round(_au_value(highest_row, "AU12", "au12"), 6),
            )
        ]
        window_scores = [0.0]
        window_confidences = [min(float(resolved.fallback_confidence_cap), 0.35)]
        pathway = AuFrictionPathway.fallback_proxy

    windows = sorted(windows, key=lambda item: float(item.score), reverse=True)[
        : max(int(resolved.top_window_limit), 1)
    ]
    global_score = _weighted_mean(window_scores, window_confidences)
    global_confidence = mean_optional(window_confidences) or 0.44
    if pathway == AuFrictionPathway.fallback_proxy:
        global_confidence = min(global_confidence, float(resolved.fallback_confidence_cap))

    signals_used = [
        "au04_trace",
        "au06_trace",
        "au12_trace",
        "au25_trace",
        "au26_trace",
        "au45_trace",
        "face_quality_gating",
        "scene_transition_context",
    ]
    evidence_summary = (
        "AU friction diagnostics interpret AU-level patterns as diagnostic indicators for confusion, strain, "
        "amusement, tension, or resistance. Results are quality-gated and should not be treated as a standalone truth engine."
    )
    if warnings:
        evidence_summary += " Quality warnings indicate where facial input reliability was reduced."

    return AuFrictionDiagnostics(
        pathway=pathway,
        global_score=round(global_score or 0.0, 6),
        confidence=round(global_confidence, 6),
        segment_scores=windows,
        warnings=warnings,
        confusion_signal=round(mean_optional(confusion_values) or 0.0, 6),
        strain_signal=round(mean_optional(strain_values) or 0.0, 6),
        amusement_signal=round(mean_optional(amusement_values) or 0.0, 6),
        tension_signal=round(mean_optional(tension_values) or 0.0, 6),
        resistance_signal=round(mean_optional(resistance_values) or 0.0, 6),
        evidence_summary=evidence_summary,
        signals_used=signals_used,
    )


def _window_reason(
    *,
    dominant_state: AuFrictionState,
    confusion: float,
    strain: float,
    amusement: float,
    tension: float,
    resistance: float,
    transition_context: Optional[str],
) -> str:
    state_label = dominant_state.value.replace("_", " ")
    strengths = {
        "confusion": confusion,
        "strain": strain,
        "amusement": amusement,
        "tension": tension,
        "resistance": resistance,
    }
    strongest_other = sorted(
        ((key, value) for key, value in strengths.items() if key != dominant_state.value),
        key=lambda item: item[1],
        reverse=True,
    )[0]
    reason = (
        f"Dominant AU pattern suggested {state_label}; secondary signal was {strongest_other[0]}."
    )
    if transition_context == "post_transition_spike":
        reason += " Pattern followed a scene/cut transition and aligned with a confusion spike."
    return reason


def _dominant_state(
    *,
    confusion: float,
    strain: float,
    amusement: float,
    tension: float,
    resistance: float,
) -> AuFrictionState:
    ranked = sorted(
        [
            (AuFrictionState.confusion, confusion),
            (AuFrictionState.strain, strain),
            (AuFrictionState.amusement, amusement),
            (AuFrictionState.tension, tension),
            (AuFrictionState.resistance, resistance),
        ],
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[0][0]


def _au_value(
    row: Mapping[str, object],
    au_name: str,
    direct_key: Optional[str] = None,
) -> float:
    if direct_key is not None and row.get(direct_key) is not None:
        return clamp(to_float(row.get(direct_key), 0.0), 0.0, 1.0)
    au_norm = row.get("au_norm")
    if isinstance(au_norm, Mapping):
        value = au_norm.get(au_name)
        if value is not None:
            return clamp(to_float(value, 0.0), 0.0, 1.0)
    return 0.0


def _find_missing_face_windows(
    *,
    rows: Sequence[Dict[str, object]],
    coverage_flags: Sequence[bool],
    window_ms: int,
    threshold: int,
) -> List[tuple[int, int, int]]:
    result: List[tuple[int, int, int]] = []
    run_start: Optional[int] = None
    run_count = 0
    for index, covered in enumerate(coverage_flags):
        start_ms = int(to_float(rows[index].get("bucket_start"), 0.0))
        if not covered:
            if run_start is None:
                run_start = start_ms
                run_count = 1
            else:
                run_count += 1
            continue
        if run_start is not None and run_count >= threshold:
            result.append((run_start, start_ms, run_count))
        run_start = None
        run_count = 0
    if run_start is not None and run_count >= threshold:
        result.append((run_start, run_start + (run_count * max(window_ms, 1)), run_count))
    return result



def _std(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    center = sum(float(value) for value in values) / float(len(values))
    variance = sum((float(value) - center) ** 2 for value in values) / float(len(values))
    return math.sqrt(max(variance, 0.0))


def _clamp_optional(value: object) -> Optional[float]:
    if value is None:
        return None
    return clamp(to_float(value, 0.0), 0.0, 1.0)


def _parse_override_payload(raw: object) -> Optional[Mapping[str, Any]]:
    if raw in (None, ""):
        return None
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping):
        return payload
    return None


def _apply_overrides(
    config: AuFrictionConfig,
    overrides: Mapping[str, Any],
) -> AuFrictionConfig:
    allowed_fields = {field.name for field in fields(config)}
    updates: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in allowed_fields:
            continue
        updates[key] = value
    if not updates:
        return config
    return replace(config, **updates)
