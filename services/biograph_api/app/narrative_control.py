"""Narrative control diagnostics from scene grammar and timeline features."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .config import get_settings
from .readout_metrics import clamp, mean_optional

from .schemas import (
    FeatureTrackRead,
    NarrativeControlDiagnostics,
    NarrativeControlHeuristicCheck,
    NarrativeControlMomentContribution,
    NarrativeControlPathway,
    NarrativeControlSceneScore,
    ReadoutCtaMarker,
    ReadoutCut,
    ReadoutScene,
    TimelineSegmentRead,
)


@dataclass(frozen=True)
class NarrativeControlConfig:
    hook_window_ms: int = 3000
    setup_window_ms: int = 6000
    disorient_transition_window_ms: int = 1500
    disruptive_attention_drop_threshold: float = 8.0
    disruptive_motion_jump_threshold: float = 5.0
    disruptive_cut_density_threshold: float = 1.4
    fragmentation_cut_cadence_threshold: float = 1.35
    short_shot_duration_ms: int = 850
    motion_discontinuity_threshold: float = 6.0
    velocity_instability_threshold: float = 12.0
    reveal_gain_threshold: float = 5.0
    context_before_face_margin: float = 0.08
    subject_persistence_min: float = 0.62
    payoff_attention_collapse_threshold: float = 40.0
    payoff_recovery_gain_threshold: float = 6.0
    hook_min_attention: float = 58.0
    scene_attention_floor: float = 30.0
    top_moment_limit: int = 5
    max_transition_penalty: float = 12.0
    max_reveal_bonus: float = 10.0
    transition_penalty_weight: float = 9.5
    reveal_bonus_weight: float = 8.5
    hook_bonus_points: float = 6.0
    setup_persistence_bonus_points: float = 5.0
    payoff_bonus_points: float = 7.0
    cta_transition_bonus_points: float = 4.0


def resolve_narrative_control_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> NarrativeControlConfig:
    """Build configurable narrative heuristics from settings + optional video metadata."""

    config = NarrativeControlConfig()
    settings_raw = get_settings().narrative_control_config_json
    settings_overrides = _parse_override_payload(settings_raw)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("narrative_control_config", "narrativeControlConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break

    return config


def compute_narrative_control_diagnostics(
    *,
    scenes: Sequence[ReadoutScene],
    cuts: Sequence[ReadoutCut],
    cta_markers: Sequence[ReadoutCtaMarker],
    bucket_rows: Sequence[Dict[str, object]],
    window_ms: int,
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]] = (),
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]] = (),
    config: Optional[NarrativeControlConfig] = None,
) -> NarrativeControlDiagnostics:
    """Estimate narrative control using cinematic grammar proxies and timeline signals."""

    resolved_config = config or NarrativeControlConfig()
    ordered_rows = sorted(
        [row for row in bucket_rows if "bucket_start" in row],
        key=lambda row: int(row["bucket_start"]),
    )
    if not ordered_rows:
        return NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.insufficient_data,
            evidence_summary="No readout timeline buckets were available for narrative diagnostics.",
            signals_used=[],
        )

    duration_ms = int(
        max(
            int(ordered_rows[-1]["bucket_start"]) + max(int(window_ms), 1),
            max((int(scene.end_ms) for scene in scenes), default=0),
            max((int(cut.end_ms) for cut in cuts), default=0),
            max((int(marker.end_ms or marker.video_time_ms) for marker in cta_markers), default=0),
        )
    )

    has_timeline_grammar = _has_timeline_grammar_support(
        timeline_segments=timeline_segments,
        timeline_feature_tracks=timeline_feature_tracks,
    )
    pathway = (
        NarrativeControlPathway.timeline_grammar
        if has_timeline_grammar
        else NarrativeControlPathway.fallback_proxy
    )

    scene_windows = _resolve_scene_windows(scenes, ordered_rows, duration_ms, window_ms)
    if not scene_windows:
        return NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.insufficient_data,
            evidence_summary="No scene windows were available for narrative diagnostics.",
            signals_used=[],
        )

    scene_scores: List[NarrativeControlSceneScore] = []
    scene_attention_by_range: Dict[tuple[int, int], float] = {}
    for scene in scene_windows:
        scene_rows = _rows_in_window(ordered_rows, scene.start_ms, scene.end_ms)
        if not scene_rows:
            continue

        scene_attention = mean_optional(_row_series(scene_rows, "attention_score")) or 0.0
        scene_attention_by_range[(int(scene.start_ms), int(scene.end_ms))] = scene_attention
        scene_tracking = mean_optional(_row_series(scene_rows, "tracking_confidence")) or 0.55
        velocity_abs = _mean_abs_optional(_row_series(scene_rows, "attention_velocity")) or 0.0
        playback_continuity = mean_optional(_row_series(scene_rows, "playback_continuity")) or 0.75

        cut_density = _cut_density(cuts, int(scene.start_ms), int(scene.end_ms))
        cut_cadence = _track_mean(
            timeline_feature_tracks,
            "cut_cadence",
            int(scene.start_ms),
            int(scene.end_ms),
        )
        if cut_cadence is None:
            cut_cadence = cut_density

        shot_durations = _track_values(
            timeline_feature_tracks,
            "shot_duration_ms",
            int(scene.start_ms),
            int(scene.end_ms),
        )
        short_shot_ratio = (
            sum(1 for value in shot_durations if value <= float(resolved_config.short_shot_duration_ms))
            / float(len(shot_durations))
            if shot_durations
            else 0.0
        )

        motion_values = _track_values(
            timeline_feature_tracks,
            "camera_motion_proxy",
            int(scene.start_ms),
            int(scene.end_ms),
        )
        motion_discontinuity = _mean_abs_delta(motion_values)
        motion_continuity = clamp(
            1.0 - (motion_discontinuity / max(resolved_config.motion_discontinuity_threshold, 1e-6)),
            0.0,
            1.0,
        )

        subject_persistence = _subject_persistence(
            timeline_feature_tracks,
            scene_start_ms=int(scene.start_ms),
            scene_end_ms=int(scene.end_ms),
        )
        ordering_pattern = _ordering_pattern(
            timeline_feature_tracks=timeline_feature_tracks,
            start_ms=int(scene.start_ms),
            end_ms=int(scene.end_ms),
            margin=resolved_config.context_before_face_margin,
        )
        ordering_unit = {
            "context_before_face": 1.0,
            "balanced": 0.84,
            "face_before_context": 0.72,
        }[ordering_pattern]

        fragmentation_cadence = clamp(
            (float(cut_cadence) - resolved_config.fragmentation_cut_cadence_threshold)
            / max(resolved_config.fragmentation_cut_cadence_threshold, 1e-6),
            0.0,
            1.0,
        )
        fragmentation_index = clamp((0.6 * fragmentation_cadence) + (0.4 * short_shot_ratio), 0.0, 1.0)

        velocity_unit = clamp(
            1.0 - (velocity_abs / max(resolved_config.velocity_instability_threshold, 1e-6)),
            0.0,
            1.0,
        )
        continuity_unit = clamp(
            (0.25 * playback_continuity)
            + (0.2 * velocity_unit)
            + (0.2 * motion_continuity)
            + (0.2 * subject_persistence)
            + (0.15 * ordering_unit),
            0.0,
            1.0,
        )

        attention_unit = clamp(
            (scene_attention - resolved_config.scene_attention_floor)
            / max(100.0 - resolved_config.scene_attention_floor, 1e-6),
            0.0,
            1.0,
        )
        scene_score = clamp(
            ((0.5 * continuity_unit) + (0.3 * (1.0 - fragmentation_index)) + (0.2 * attention_unit))
            * 100.0,
            0.0,
            100.0,
        )
        signal_coverage = 0.0
        signal_coverage += 1.0 if motion_values else 0.0
        signal_coverage += 1.0 if shot_durations else 0.0
        signal_coverage += 1.0 if cut_cadence is not None else 0.0
        signal_coverage += 1.0 if subject_persistence is not None else 0.0
        signal_coverage = signal_coverage / 4.0

        scene_confidence = clamp(
            (0.5 * scene_tracking)
            + (0.25 * signal_coverage)
            + (0.25 * (0.85 if has_timeline_grammar else 0.62)),
            0.0,
            1.0,
        )
        summary = (
            "Higher control from stable motion and moderate boundary density."
            if scene_score >= 60.0
            else "Lower control from elevated fragmentation or unstable transitions."
        )
        scene_scores.append(
            NarrativeControlSceneScore(
                start_ms=int(scene.start_ms),
                end_ms=int(scene.end_ms),
                score=round(scene_score, 6),
                confidence=round(scene_confidence, 6),
                scene_id=scene.scene_id,
                scene_label=scene.label,
                fragmentation_index=round(fragmentation_index, 6),
                boundary_density=round(float(cut_cadence), 6) if cut_cadence is not None else None,
                motion_continuity=round(motion_continuity, 6),
                ordering_pattern=ordering_pattern,
                summary=summary,
            )
        )

    if not scene_scores:
        return NarrativeControlDiagnostics(
            pathway=NarrativeControlPathway.insufficient_data,
            evidence_summary="No scene-level buckets had enough data for narrative diagnostics.",
            signals_used=[],
        )

    disruption_penalties = _build_disruption_penalties(
        cuts=cuts,
        rows=ordered_rows,
        timeline_feature_tracks=timeline_feature_tracks,
        window_ms=window_ms,
        duration_ms=duration_ms,
        config=resolved_config,
    )
    reveal_structure_bonuses = _build_reveal_bonuses(
        scene_scores=scene_scores,
        scene_attention_by_range=scene_attention_by_range,
        timeline_segments=timeline_segments,
        rows=ordered_rows,
        window_ms=window_ms,
        config=resolved_config,
    )

    heuristic_checks = _build_heuristic_checks(
        rows=ordered_rows,
        cuts=cuts,
        cta_markers=cta_markers,
        disruption_penalties=disruption_penalties,
        timeline_feature_tracks=timeline_feature_tracks,
        duration_ms=duration_ms,
        config=resolved_config,
    )

    scene_mean = mean_optional([float(item.score) for item in scene_scores]) or 0.0
    penalty_total = sum(float(item.contribution) for item in disruption_penalties)
    reveal_total = sum(float(item.contribution) for item in reveal_structure_bonuses)
    heuristic_total = sum(float(item.score_delta) for item in heuristic_checks)
    global_score = clamp(scene_mean + penalty_total + reveal_total + heuristic_total, 0.0, 100.0)

    heuristic_contributions = [
        NarrativeControlMomentContribution(
            start_ms=int(item.start_ms or 0),
            end_ms=int(item.end_ms or max(window_ms, 1)),
            contribution=round(float(item.score_delta), 6),
            category=f"heuristic:{item.heuristic_key}",
            reason=item.reason,
        )
        for item in heuristic_checks
    ]
    top_contributing_moments = sorted(
        [*disruption_penalties, *reveal_structure_bonuses, *heuristic_contributions],
        key=lambda item: abs(float(item.contribution)),
        reverse=True,
    )[: max(int(resolved_config.top_moment_limit), 1)]

    tracking_mean = mean_optional(_row_series(ordered_rows, "tracking_confidence")) or 0.55
    scene_coverage = len(scene_scores) / float(max(len(scene_windows), 1))
    timeline_coverage = _timeline_coverage_ratio(timeline_segments, timeline_feature_tracks)
    base_confidence = 0.8 if pathway == NarrativeControlPathway.timeline_grammar else 0.58
    confidence = clamp(
        (0.4 * base_confidence)
        + (0.35 * tracking_mean)
        + (0.15 * scene_coverage)
        + (0.10 * timeline_coverage),
        0.0,
        1.0,
    )
    if pathway == NarrativeControlPathway.fallback_proxy:
        confidence = min(confidence, 0.72)

    positive_moment = next(
        (item for item in top_contributing_moments if float(item.contribution) > 0),
        None,
    )
    negative_moment = next(
        (item for item in top_contributing_moments if float(item.contribution) < 0),
        None,
    )
    evidence_bits: List[str] = []
    if positive_moment is not None:
        evidence_bits.append(f"Top coherence bonus: {positive_moment.reason}")
    if negative_moment is not None:
        evidence_bits.append(f"Top disruption penalty: {negative_moment.reason}")
    evidence_bits.append(
        "Per-scene scores blend continuity, fragmentation, ordering pattern, and reveal timing proxies."
    )

    signals_used = [
        "attention_trace",
        "scene_graph_scenes",
        "scene_graph_cuts",
    ]
    if _has_track(timeline_feature_tracks, "cut_cadence"):
        signals_used.append("cut_cadence")
    if _has_track(timeline_feature_tracks, "shot_duration_ms"):
        signals_used.append("shot_duration_distribution")
    if _has_track(timeline_feature_tracks, "camera_motion_proxy"):
        signals_used.append("camera_motion_proxy")
    if _has_track(timeline_feature_tracks, "face_presence_rate"):
        signals_used.append("face_presence_proxy")
    if _has_segment(timeline_segments, "text_overlay"):
        signals_used.append("text_overlay_reveal_windows")
    if _has_segment(timeline_segments, "cta_window"):
        signals_used.append("cta_windows")

    return NarrativeControlDiagnostics(
        pathway=pathway,
        global_score=round(global_score, 6),
        confidence=round(confidence, 6),
        scene_scores=scene_scores,
        disruption_penalties=disruption_penalties,
        reveal_structure_bonuses=reveal_structure_bonuses,
        top_contributing_moments=top_contributing_moments,
        heuristic_checks=heuristic_checks,
        evidence_summary=" ".join(evidence_bits),
        signals_used=signals_used,
    )


def _parse_override_payload(raw_value: object) -> Dict[str, object]:
    if raw_value is None:
        return {}
    if isinstance(raw_value, Mapping):
        return dict(raw_value)
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if not candidate:
            return {}
        try:
            payload = json.loads(candidate)
        except (ValueError, TypeError):
            return {}
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _apply_overrides(
    config: NarrativeControlConfig,
    overrides: Mapping[str, object],
) -> NarrativeControlConfig:
    allowed_fields = {field.name: field.type for field in fields(config)}
    replacement: Dict[str, object] = {}
    for key, value in overrides.items():
        if key not in allowed_fields:
            continue
        replacement[key] = value
    if not replacement:
        return config
    try:
        return replace(config, **replacement)
    except TypeError:
        return config



def _mean_abs_optional(values: Sequence[Optional[float]]) -> Optional[float]:
    numeric = [abs(float(value)) for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / float(len(numeric))


def _mean_abs_delta(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    deltas = [abs(values[index] - values[index - 1]) for index in range(1, len(values))]
    if not deltas:
        return 0.0
    return sum(deltas) / float(len(deltas))


def _item_field(item: object, key: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(key, default)  # type: ignore[return-value]
    return getattr(item, key, default)


def _track_values(
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    track_name: str,
    start_ms: int,
    end_ms: int,
) -> List[float]:
    values: List[float] = []
    for track in timeline_feature_tracks:
        if str(_item_field(track, "track_name", "")) != track_name:
            continue
        track_start = int(_item_field(track, "start_ms", 0) or 0)
        track_end = int(_item_field(track, "end_ms", track_start + 1) or (track_start + 1))
        if track_end <= start_ms or track_start >= end_ms:
            continue
        numeric = _item_field(track, "numeric_value")
        if numeric is None:
            continue
        values.append(float(numeric))
    return values


def _track_mean(
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    track_name: str,
    start_ms: int,
    end_ms: int,
) -> Optional[float]:
    values = _track_values(timeline_feature_tracks, track_name, start_ms, end_ms)
    return mean_optional(values)


def _rows_in_window(rows: Sequence[Dict[str, object]], start_ms: int, end_ms: int) -> List[Dict[str, object]]:
    return [
        row
        for row in rows
        if start_ms <= int(row.get("bucket_start", 0)) < end_ms
    ]


def _row_series(rows: Sequence[Dict[str, object]], field_name: str) -> List[Optional[float]]:
    values: List[Optional[float]] = []
    for row in rows:
        value = row.get(field_name)
        if value is None:
            values.append(None)
            continue
        values.append(float(value))
    return values


def _has_track(
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    track_name: str,
) -> bool:
    return any(str(_item_field(track, "track_name", "")) == track_name for track in timeline_feature_tracks)


def _has_segment(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    segment_type: str,
) -> bool:
    return any(str(_item_field(segment, "segment_type", "")) == segment_type for segment in timeline_segments)


def _has_timeline_grammar_support(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
) -> bool:
    required_track_hits = sum(
        1
        for track_name in ("cut_cadence", "shot_duration_ms", "camera_motion_proxy")
        if _has_track(timeline_feature_tracks, track_name)
    )
    return required_track_hits >= 2 and _has_segment(timeline_segments, "shot_boundary")


def _timeline_coverage_ratio(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
) -> float:
    required_tracks = ("cut_cadence", "shot_duration_ms", "camera_motion_proxy", "face_presence_rate")
    required_segments = ("shot_boundary", "scene_block", "cta_window")
    track_ratio = sum(1 for name in required_tracks if _has_track(timeline_feature_tracks, name)) / float(
        len(required_tracks)
    )
    segment_ratio = sum(1 for name in required_segments if _has_segment(timeline_segments, name)) / float(
        len(required_segments)
    )
    return clamp((0.7 * track_ratio) + (0.3 * segment_ratio), 0.0, 1.0)


def _cut_density(cuts: Sequence[ReadoutCut], start_ms: int, end_ms: int) -> float:
    duration_seconds = max((end_ms - start_ms) / 1000.0, 0.001)
    cut_count = sum(1 for cut in cuts if start_ms <= int(cut.start_ms) < end_ms)
    return cut_count / duration_seconds


def _subject_persistence(
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    *,
    scene_start_ms: int,
    scene_end_ms: int,
) -> float:
    scene_specific = _track_mean(
        timeline_feature_tracks,
        "primary_subject_persistence",
        scene_start_ms,
        scene_end_ms,
    )
    if scene_specific is not None:
        return clamp(scene_specific, 0.0, 1.0)
    face_presence = _track_mean(
        timeline_feature_tracks,
        "face_presence_rate",
        scene_start_ms,
        scene_end_ms,
    )
    if face_presence is not None:
        return clamp(face_presence, 0.0, 1.0)
    return 0.55


def _ordering_pattern(
    *,
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    start_ms: int,
    end_ms: int,
    margin: float,
) -> str:
    face_values: List[tuple[int, float]] = []
    for track in timeline_feature_tracks:
        if str(_item_field(track, "track_name", "")) != "face_presence_rate":
            continue
        track_start = int(_item_field(track, "start_ms", 0) or 0)
        track_end = int(_item_field(track, "end_ms", track_start + 1) or (track_start + 1))
        if track_end <= start_ms or track_start >= end_ms:
            continue
        numeric = _item_field(track, "numeric_value")
        if numeric is None:
            continue
        face_values.append((track_start, float(numeric)))

    if len(face_values) < 2:
        return "balanced"
    face_values.sort(key=lambda item: item[0])
    midpoint = len(face_values) // 2
    first_half = [value for _, value in face_values[:midpoint]]
    second_half = [value for _, value in face_values[midpoint:]]
    first_mean = mean_optional(first_half) or 0.0
    second_mean = mean_optional(second_half) or 0.0
    if second_mean - first_mean >= margin:
        return "context_before_face"
    if first_mean - second_mean >= margin:
        return "face_before_context"
    return "balanced"


def _resolve_scene_windows(
    scenes: Sequence[ReadoutScene],
    rows: Sequence[Dict[str, object]],
    duration_ms: int,
    window_ms: int,
) -> List[ReadoutScene]:
    if scenes:
        return sorted(
            list(scenes),
            key=lambda scene: (int(scene.start_ms), int(scene.end_ms)),
        )

    inferred: List[ReadoutScene] = []
    current_scene_key: Optional[str] = None
    current_start: Optional[int] = None
    current_index = 0
    last_bucket_start = int(rows[0]["bucket_start"])
    for row in rows:
        bucket_start = int(row["bucket_start"])
        scene_key = row.get("scene_id")
        scene_key_text = str(scene_key) if scene_key is not None else "scene_unknown"
        if current_scene_key is None:
            current_scene_key = scene_key_text
            current_start = bucket_start
            current_index += 1
        elif scene_key_text != current_scene_key:
            inferred.append(
                ReadoutScene(
                    scene_index=current_index,
                    start_ms=int(current_start or 0),
                    end_ms=max(bucket_start, int(current_start or 0) + max(window_ms, 1)),
                    label=current_scene_key,
                    scene_id=current_scene_key if current_scene_key != "scene_unknown" else None,
                )
            )
            current_scene_key = scene_key_text
            current_start = bucket_start
            current_index += 1
        last_bucket_start = bucket_start

    if current_scene_key is not None:
        inferred.append(
            ReadoutScene(
                scene_index=current_index,
                start_ms=int(current_start or 0),
                end_ms=max(last_bucket_start + max(window_ms, 1), int(current_start or 0) + max(window_ms, 1)),
                label=current_scene_key,
                scene_id=current_scene_key if current_scene_key != "scene_unknown" else None,
            )
        )

    if inferred:
        return inferred
    return [
        ReadoutScene(
            scene_index=1,
            start_ms=0,
            end_ms=max(duration_ms, max(window_ms, 1)),
            label="scene_1",
            scene_id="scene_1",
        )
    ]


def _build_disruption_penalties(
    *,
    cuts: Sequence[ReadoutCut],
    rows: Sequence[Dict[str, object]],
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    window_ms: int,
    duration_ms: int,
    config: NarrativeControlConfig,
) -> List[NarrativeControlMomentContribution]:
    penalties: List[NarrativeControlMomentContribution] = []
    if not cuts:
        return penalties

    sorted_rows = sorted(rows, key=lambda row: int(row["bucket_start"]))
    for cut in sorted(cuts, key=lambda item: int(item.start_ms)):
        cut_start = int(cut.start_ms)
        pre_candidates = [row for row in sorted_rows if int(row["bucket_start"]) <= cut_start]
        post_candidates = [row for row in sorted_rows if int(row["bucket_start"]) > cut_start]
        if not pre_candidates or not post_candidates:
            continue
        pre_row = pre_candidates[-1]
        post_row = post_candidates[0]

        pre_attention = float(pre_row.get("attention_score") or 0.0)
        post_attention = float(post_row.get("attention_score") or 0.0)
        attention_drop = max(pre_attention - post_attention, 0.0)

        pre_motion = _track_mean(
            timeline_feature_tracks,
            "camera_motion_proxy",
            max(cut_start - window_ms, 0),
            cut_start + 1,
        ) or 0.0
        post_motion = _track_mean(
            timeline_feature_tracks,
            "camera_motion_proxy",
            cut_start,
            min(cut_start + window_ms, duration_ms),
        ) or 0.0
        motion_jump = abs(post_motion - pre_motion)

        pre_face = _track_mean(
            timeline_feature_tracks,
            "face_presence_rate",
            max(cut_start - window_ms, 0),
            cut_start + 1,
        ) or 0.0
        post_face = _track_mean(
            timeline_feature_tracks,
            "face_presence_rate",
            cut_start,
            min(cut_start + window_ms, duration_ms),
        ) or 0.0
        shot_scale_shift_proxy = abs(post_face - pre_face)

        local_cadence = _track_mean(
            timeline_feature_tracks,
            "cut_cadence",
            max(cut_start - window_ms, 0),
            min(cut_start + window_ms, duration_ms),
        ) or 0.0

        severity = clamp(
            (0.4 * clamp(
                (attention_drop - config.disruptive_attention_drop_threshold)
                / max(config.disruptive_attention_drop_threshold, 1e-6),
                0.0,
                1.0,
            ))
            + (0.25 * clamp(
                (motion_jump - config.disruptive_motion_jump_threshold)
                / max(config.disruptive_motion_jump_threshold, 1e-6),
                0.0,
                1.0,
            ))
            + (0.2 * clamp(
                (local_cadence - config.fragmentation_cut_cadence_threshold)
                / max(config.fragmentation_cut_cadence_threshold, 1e-6),
                0.0,
                1.0,
            ))
            + (0.15 * clamp(
                (shot_scale_shift_proxy - config.context_before_face_margin)
                / max(config.context_before_face_margin + 0.2, 1e-6),
                0.0,
                1.0,
            )),
            0.0,
            1.0,
        )
        if severity <= 0:
            continue
        penalty_value = -min(config.max_transition_penalty, config.transition_penalty_weight * severity)
        penalties.append(
            NarrativeControlMomentContribution(
                start_ms=cut_start,
                end_ms=max(int(cut.end_ms), cut_start + max(window_ms, 1)),
                contribution=round(penalty_value, 6),
                category="disruptive_transition",
                reason=(
                    "Transition disruption from attention drop, motion jump, and elevated cut cadence."
                ),
                scene_id=cut.scene_id,
                cut_id=cut.cut_id,
                cta_id=cut.cta_id,
            )
        )

    boundary_density = len(cuts) / max(duration_ms / 1000.0, 0.001)
    if boundary_density > config.disruptive_cut_density_threshold:
        density_severity = clamp(
            (boundary_density - config.disruptive_cut_density_threshold)
            / max(config.disruptive_cut_density_threshold, 1e-6),
            0.0,
            1.0,
        )
        penalties.append(
            NarrativeControlMomentContribution(
                start_ms=0,
                end_ms=max(duration_ms, 1),
                contribution=round(-min(6.0, 4.0 * density_severity), 6),
                category="boundary_density",
                reason="Boundary density exceeded configured continuity threshold.",
            )
        )
    return penalties


def _build_reveal_bonuses(
    *,
    scene_scores: Sequence[NarrativeControlSceneScore],
    scene_attention_by_range: Mapping[tuple[int, int], float],
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    rows: Sequence[Dict[str, object]],
    window_ms: int,
    config: NarrativeControlConfig,
) -> List[NarrativeControlMomentContribution]:
    bonuses: List[NarrativeControlMomentContribution] = []

    ordered_scene_scores = sorted(scene_scores, key=lambda item: (int(item.start_ms), int(item.end_ms)))
    for index in range(1, len(ordered_scene_scores)):
        previous_scene = ordered_scene_scores[index - 1]
        current_scene = ordered_scene_scores[index]
        previous_attention = scene_attention_by_range.get(
            (int(previous_scene.start_ms), int(previous_scene.end_ms)),
            0.0,
        )
        current_attention = scene_attention_by_range.get(
            (int(current_scene.start_ms), int(current_scene.end_ms)),
            0.0,
        )
        attention_gain = current_attention - previous_attention
        if attention_gain < config.reveal_gain_threshold:
            continue
        if (current_scene.fragmentation_index or 0.0) > 0.65:
            continue
        bonus_value = min(
            config.max_reveal_bonus,
            config.reveal_bonus_weight
            * clamp(attention_gain / max(config.reveal_gain_threshold * 2.0, 1e-6), 0.0, 1.0),
        )
        bonuses.append(
            NarrativeControlMomentContribution(
                start_ms=int(current_scene.start_ms),
                end_ms=min(
                    int(current_scene.end_ms),
                    int(current_scene.start_ms) + (2 * max(window_ms, 1)),
                ),
                contribution=round(bonus_value, 6),
                category="coherent_reveal",
                reason="Reveal timing aligned with a controlled attention increase across scene boundary.",
                scene_id=current_scene.scene_id,
            )
        )

    for segment in timeline_segments:
        if str(_item_field(segment, "segment_type", "")) != "text_overlay":
            continue
        start_ms = int(_item_field(segment, "start_ms", 0) or 0)
        end_ms = int(_item_field(segment, "end_ms", start_ms + 1) or (start_ms + 1))
        label = str(_item_field(segment, "label", "") or "")
        if "unavailable" in label.lower():
            continue
        pre_rows = _rows_in_window(rows, max(start_ms - window_ms, 0), start_ms + 1)
        post_rows = _rows_in_window(rows, start_ms, start_ms + window_ms)
        pre_attention = mean_optional(_row_series(pre_rows, "attention_score")) or 0.0
        post_attention = mean_optional(_row_series(post_rows, "attention_score")) or 0.0
        gain = post_attention - pre_attention
        if gain <= 0:
            continue
        bonus_value = min(
            4.0,
            2.5 * clamp(gain / max(config.reveal_gain_threshold, 1e-6), 0.0, 1.0),
        )
        bonuses.append(
            NarrativeControlMomentContribution(
                start_ms=start_ms,
                end_ms=max(end_ms, start_ms + 1),
                contribution=round(bonus_value, 6),
                category="reveal_timing",
                reason="Text-overlay reveal aligned with immediate attention lift.",
            )
        )

    return bonuses


def _build_heuristic_checks(
    *,
    rows: Sequence[Dict[str, object]],
    cuts: Sequence[ReadoutCut],
    cta_markers: Sequence[ReadoutCtaMarker],
    disruption_penalties: Sequence[NarrativeControlMomentContribution],
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    duration_ms: int,
    config: NarrativeControlConfig,
) -> List[NarrativeControlHeuristicCheck]:
    checks: List[NarrativeControlHeuristicCheck] = []

    hook_rows = _rows_in_window(rows, 0, min(config.hook_window_ms, duration_ms))
    hook_attention = mean_optional(_row_series(hook_rows, "attention_score")) or 0.0
    hook_cut_count = sum(1 for cut in cuts if int(cut.start_ms) <= config.hook_window_ms)
    hook_pass = hook_attention >= config.hook_min_attention and hook_cut_count >= 1
    checks.append(
        NarrativeControlHeuristicCheck(
            heuristic_key="hard_hook_first_1_to_3_seconds",
            passed=hook_pass,
            score_delta=round(
                config.hook_bonus_points if hook_pass else -(config.hook_bonus_points * 0.8),
                6,
            ),
            reason=(
                "Opening window met hook attention and pacing thresholds."
                if hook_pass
                else "Opening window did not meet configured hook attention/pacing thresholds."
            ),
            start_ms=0,
            end_ms=min(config.hook_window_ms, duration_ms),
        )
    )

    setup_end_ms = min(config.setup_window_ms, duration_ms)
    setup_persistence = _track_mean(
        timeline_feature_tracks,
        "face_presence_rate",
        0,
        setup_end_ms,
    )
    if setup_persistence is None:
        setup_persistence = _track_mean(
            timeline_feature_tracks,
            "primary_subject_persistence",
            0,
            setup_end_ms,
        )
    setup_persistence_value = setup_persistence if setup_persistence is not None else 0.5
    setup_cadence = _track_mean(
        timeline_feature_tracks,
        "cut_cadence",
        0,
        setup_end_ms,
    ) or 0.0
    setup_pass = (
        setup_persistence_value >= config.subject_persistence_min
        and setup_cadence <= (config.fragmentation_cut_cadence_threshold * 1.1)
    )
    checks.append(
        NarrativeControlHeuristicCheck(
            heuristic_key="coherent_subject_persistence_during_setup",
            passed=setup_pass,
            score_delta=round(
                config.setup_persistence_bonus_points
                if setup_pass
                else -(config.setup_persistence_bonus_points * 0.7),
                6,
            ),
            reason=(
                "Setup window maintained coherent subject persistence."
                if setup_pass
                else "Setup window showed weak persistence or over-fragmented pacing."
            ),
            start_ms=0,
            end_ms=setup_end_ms,
        )
    )

    payoff_start = _resolve_payoff_start(cta_markers=cta_markers, duration_ms=duration_ms)
    pre_rows = _rows_in_window(rows, max(payoff_start - 2000, 0), payoff_start)
    post_rows = _rows_in_window(rows, payoff_start, min(payoff_start + 2000, duration_ms))
    pre_values = [value for value in _row_series(pre_rows, "attention_score") if value is not None]
    post_values = [value for value in _row_series(post_rows, "attention_score") if value is not None]
    pre_min = min(pre_values) if pre_values else None
    post_mean = mean_optional(post_values)
    collapse_detected = pre_min is not None and pre_min < config.payoff_attention_collapse_threshold
    payoff_recovered = (
        pre_min is not None
        and post_mean is not None
        and (post_mean - pre_min) >= config.payoff_recovery_gain_threshold
    )
    payoff_pass = (not collapse_detected) or payoff_recovered
    checks.append(
        NarrativeControlHeuristicCheck(
            heuristic_key="payoff_not_buried_after_attention_collapse",
            passed=payoff_pass,
            score_delta=round(
                config.payoff_bonus_points if payoff_pass else -(config.payoff_bonus_points * 0.85),
                6,
            ),
            reason=(
                "Payoff timing avoided a buried post-collapse placement."
                if payoff_pass
                else "Payoff arrived after attention collapse without adequate recovery."
            ),
            start_ms=payoff_start,
            end_ms=min(payoff_start + 2000, duration_ms),
        )
    )

    cta_pass = True
    cta_reason = "CTA timing avoided immediate handoff from disorienting transitions."
    nearest_cta_start = payoff_start
    for marker in cta_markers:
        marker_start = int(marker.start_ms if marker.start_ms is not None else marker.video_time_ms)
        nearest_cta_start = min(nearest_cta_start, marker_start)
        has_near_penalty = any(
            int(penalty.start_ms) <= marker_start
            and marker_start - int(penalty.start_ms) <= config.disorient_transition_window_ms
            and float(penalty.contribution) < 0
            for penalty in disruption_penalties
        )
        if has_near_penalty:
            cta_pass = False
            cta_reason = "CTA followed a disorienting transition inside the configured cooldown window."
            break

    checks.append(
        NarrativeControlHeuristicCheck(
            heuristic_key="cta_not_after_disorienting_transition",
            passed=cta_pass,
            score_delta=round(
                config.cta_transition_bonus_points
                if cta_pass
                else -(config.cta_transition_bonus_points * 0.9),
                6,
            ),
            reason=cta_reason,
            start_ms=max(nearest_cta_start - config.disorient_transition_window_ms, 0),
            end_ms=min(nearest_cta_start + max(config.disorient_transition_window_ms, 1), duration_ms),
        )
    )
    return checks


def _resolve_payoff_start(*, cta_markers: Sequence[ReadoutCtaMarker], duration_ms: int) -> int:
    if cta_markers:
        return min(
            int(marker.start_ms if marker.start_ms is not None else marker.video_time_ms)
            for marker in cta_markers
        )
    return max(duration_ms - 2000, 0)
