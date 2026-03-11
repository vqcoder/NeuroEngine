"""Bucket-accumulation logic extracted from services_readout.

Handles the per-point accumulation into time-windowed buckets for both the
global aggregate and per-session breakdown.  Also provides ``_build_bucket_row``
(row construction from an accumulated bucket) and
``_apply_velocity_and_reward_decomposition`` (velocity + reward patching).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional
from uuid import UUID

from .readout_metrics import (
    ReadoutMetricConfig,
    SessionBlinkSample,
    clamp,
    compute_attention_score,
    compute_blink_inhibition,
    compute_head_pose_stability,
    compute_reward_proxy_decomposition,
    compute_session_blink_baseline,
    compute_tracking_confidence,
    mean,
)
from .schemas import AU_DEFAULTS
from .services_catalog import SceneGraphContext, _resolve_scene_alignment
from .services_math import _mean, _mean_optional, _first_present


# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------
PLAYBACK_PENALTY_FACTOR = 0.18
REWARD_BLEND_CURRENT_WEIGHT = 0.75
REWARD_BLEND_HISTORICAL_WEIGHT = 0.25
GAZE_FACE_PRESENCE_WEIGHT = 0.6
GAZE_HEAD_STABILITY_WEIGHT = 0.4
GAZE_DEFAULT_HEAD_STABILITY = 0.5


def _derive_quality_flags(point) -> List[str]:
    """Derive quality-flag strings from a TracePoint."""
    if point.quality_flags:
        return [str(item) for item in point.quality_flags]

    flags: List[str] = []
    if point.brightness < 45:
        flags.append("low_light")
    if point.blur is not None and point.blur < 40:
        flags.append("blur")
    if point.face_ok is False or (
        point.face_visible_pct is not None and point.face_visible_pct < 0.5
    ):
        flags.append("face_lost")
    yaw = (point.head_pose or {}).get("yaw")
    pitch = (point.head_pose or {}).get("pitch")
    if (
        (yaw is not None and abs(float(yaw)) > 28)
        or (pitch is not None and abs(float(pitch)) > 20)
        or (point.head_pose_valid_pct is not None and point.head_pose_valid_pct < 0.6)
    ):
        flags.append("high_yaw_pitch")
    return sorted(set(flags))


def _new_global_bucket() -> Dict[str, object]:
    return {
        "samples": 0,
        "face_ok": 0,
        "brightness": [],
        "blink": 0,
        "face_presence": [],
        "head_pose_stability": [],
        "gaze_on_screen": [],
        "direct_gaze_flags": [],
        "eye_openness": [],
        "blink_rates": [],
        "blink_baselines": [],
        "blink_inhibition_scores": [],
        "occlusion_scores": [],
        "head_pose_valid_pcts": [],
        "reward_proxy_values": [],
        "dial_values": [],
        "tracking_confidences": [],
        "quality_scores": [],
        "quality_flag_counts": defaultdict(int),
        "scene_ids": [],
        "cut_ids": [],
        "cta_ids": [],
        "au_norm": defaultdict(list),
    }


def _new_session_bucket() -> Dict[str, object]:
    return {
        "samples": 0,
        "face_presence": [],
        "head_pose_stability": [],
        "gaze_on_screen": [],
        "direct_gaze_flags": [],
        "eye_openness": [],
        "blink_rates": [],
        "blink_baselines": [],
        "blink_inhibition_scores": [],
        "brightness": [],
        "occlusion_scores": [],
        "head_pose_valid_pcts": [],
        "reward_proxy_values": [],
        "dial_values": [],
        "tracking_confidences": [],
        "quality_scores": [],
        "scene_ids": [],
        "cut_ids": [],
        "cta_ids": [],
        "au_norm": defaultdict(list),
    }


# ---------------------------------------------------------------------------
# Main accumulation
# ---------------------------------------------------------------------------

def accumulate_points_into_buckets(
    points: list,
    window_ms: int,
    seconds_per_window: float,
    scene_graph: SceneGraphContext,
    blink_baseline_by_session: Dict[UUID, float],
    global_blink_baseline: float,
    config: ReadoutMetricConfig,
) -> tuple:
    """Walk *points* and fill bucket accumulators.

    Returns ``(bucket_acc, session_bucket_acc)`` where:

    - ``bucket_acc`` maps ``bucket_start -> accumulator dict``
    - ``session_bucket_acc`` maps ``session_id -> bucket_start -> accumulator dict``
    """
    bucket_acc: Dict[int, Dict[str, object]] = defaultdict(_new_global_bucket)
    session_bucket_acc: Dict[UUID, Dict[int, Dict[str, object]]] = defaultdict(
        lambda: defaultdict(_new_session_bucket)
    )

    for point in points:
        point_video_time_ms = int(point.video_time_ms if point.video_time_ms is not None else point.t_ms)
        bucket_start = (point_video_time_ms // window_ms) * window_ms
        acc = bucket_acc[bucket_start]
        acc["samples"] = int(acc["samples"]) + 1
        acc["face_ok"] = int(acc["face_ok"]) + int(bool(point.face_ok))
        acc["brightness"].append(float(point.brightness))  # type: ignore[index]
        acc["blink"] = int(acc["blink"]) + int(point.blink)

        head_pose_payload = point.head_pose or {}
        head_pose_stability = compute_head_pose_stability(
            yaw=head_pose_payload.get("yaw"),
            pitch=head_pose_payload.get("pitch"),
            roll=head_pose_payload.get("roll"),
            head_pose_valid_pct=point.head_pose_valid_pct,
        )

        face_presence = point.face_presence_confidence
        if face_presence is None:
            face_presence = 1.0 if point.face_ok else 0.0
        gaze_on_screen = point.gaze_on_screen_proxy
        direct_gaze_flag = 1.0 if point.gaze_on_screen_proxy is not None else 0.0
        if gaze_on_screen is None:
            gaze_on_screen = clamp(
                GAZE_FACE_PRESENCE_WEIGHT * face_presence + GAZE_HEAD_STABILITY_WEIGHT * (head_pose_stability if head_pose_stability is not None else GAZE_DEFAULT_HEAD_STABILITY),
                0.0,
                1.0,
            )
        eye_openness = point.eye_openness if point.eye_openness is not None else (0.2 if point.blink else 0.82)
        blink_rate = (
            float(point.rolling_blink_rate)
            if point.rolling_blink_rate is not None
            else float(point.blink) / seconds_per_window
        )
        blink_baseline = blink_baseline_by_session.get(point.session_id, global_blink_baseline)
        blink_inhibition_score = (
            float(point.blink_inhibition_score)
            if point.blink_inhibition_score is not None
            else compute_blink_inhibition(blink_rate, blink_baseline)
        )
        tracking_confidence = point.tracking_confidence
        if tracking_confidence is None:
            tracking_confidence = compute_tracking_confidence(
                quality_confidence=point.quality_confidence,
                face_presence_confidence=point.face_presence_confidence,
                landmarks_confidence=point.landmarks_confidence,
                gaze_on_screen_confidence=point.gaze_on_screen_confidence,
                head_pose_confidence=point.head_pose_confidence,
                au_confidence=point.au_confidence,
            )
        quality_score = point.quality_score
        if quality_score is None:
            quality_parts = [
                value
                for value in [
                    face_presence,
                    point.landmarks_confidence,
                    point.gaze_on_screen_confidence,
                    point.fps_stability,
                    point.face_visible_pct,
                    (1.0 - point.occlusion_score) if point.occlusion_score is not None else None,
                ]
                if value is not None
            ]
            quality_score = clamp(mean(quality_parts), 0.0, 1.0) if quality_parts else None

        acc["face_presence"].append(float(face_presence))  # type: ignore[index]
        if head_pose_stability is not None:
            acc["head_pose_stability"].append(float(head_pose_stability))  # type: ignore[index]
        if point.occlusion_score is not None:
            acc["occlusion_scores"].append(float(point.occlusion_score))  # type: ignore[index]
        if point.head_pose_valid_pct is not None:
            acc["head_pose_valid_pcts"].append(float(point.head_pose_valid_pct))  # type: ignore[index]
        acc["gaze_on_screen"].append(float(gaze_on_screen))  # type: ignore[index]
        acc["direct_gaze_flags"].append(float(direct_gaze_flag))  # type: ignore[index]
        acc["eye_openness"].append(float(eye_openness))  # type: ignore[index]
        acc["blink_rates"].append(float(blink_rate))  # type: ignore[index]
        acc["blink_baselines"].append(float(blink_baseline))  # type: ignore[index]

        acc["blink_inhibition_scores"].append(float(blink_inhibition_score))  # type: ignore[index]
        if point.reward_proxy is not None:
            acc["reward_proxy_values"].append(float(point.reward_proxy))  # type: ignore[index]
        if point.dial is not None:
            acc["dial_values"].append(float(point.dial))  # type: ignore[index]
        if quality_score is not None:
            acc["quality_scores"].append(float(quality_score))  # type: ignore[index]
        if tracking_confidence is not None:
            acc["tracking_confidences"].append(float(tracking_confidence))  # type: ignore[index]
        quality_flags = _derive_quality_flags(point)
        for quality_flag in quality_flags:
            acc["quality_flag_counts"][quality_flag] += 1  # type: ignore[index]

        scene_id_value = point.scene_id
        cut_id_value = point.cut_id
        cta_id_value = point.cta_id
        if scene_id_value is None and cut_id_value is None and cta_id_value is None:
            scene_id_value, cut_id_value, cta_id_value = _resolve_scene_alignment(
                scene_graph,
                point_video_time_ms,
            )
        if scene_id_value is not None:
            acc["scene_ids"].append(scene_id_value)  # type: ignore[index]
        if cut_id_value is not None:
            acc["cut_ids"].append(cut_id_value)  # type: ignore[index]
        if cta_id_value is not None:
            acc["cta_ids"].append(cta_id_value)  # type: ignore[index]

        au_norm_payload = point.au_norm or point.au or {}
        for key in AU_DEFAULTS:
            acc["au_norm"][key].append(float(au_norm_payload.get(key, 0.0)))  # type: ignore[index]

        session_acc = session_bucket_acc[point.session_id][bucket_start]
        session_acc["samples"] = int(session_acc["samples"]) + 1
        session_acc["face_presence"].append(float(face_presence))  # type: ignore[index]
        if head_pose_stability is not None:
            session_acc["head_pose_stability"].append(float(head_pose_stability))  # type: ignore[index]
        session_acc["gaze_on_screen"].append(float(gaze_on_screen))  # type: ignore[index]
        session_acc["direct_gaze_flags"].append(float(direct_gaze_flag))  # type: ignore[index]
        session_acc["eye_openness"].append(float(eye_openness))  # type: ignore[index]
        session_acc["blink_rates"].append(float(blink_rate))  # type: ignore[index]
        session_acc["blink_baselines"].append(float(blink_baseline))  # type: ignore[index]
        session_acc["blink_inhibition_scores"].append(float(blink_inhibition_score))  # type: ignore[index]
        session_acc["brightness"].append(float(point.brightness))  # type: ignore[index]
        if point.occlusion_score is not None:
            session_acc["occlusion_scores"].append(float(point.occlusion_score))  # type: ignore[index]
        if point.head_pose_valid_pct is not None:
            session_acc["head_pose_valid_pcts"].append(float(point.head_pose_valid_pct))  # type: ignore[index]
        if point.reward_proxy is not None:
            session_acc["reward_proxy_values"].append(float(point.reward_proxy))  # type: ignore[index]
        if point.dial is not None:
            session_acc["dial_values"].append(float(point.dial))  # type: ignore[index]
        if tracking_confidence is not None:
            session_acc["tracking_confidences"].append(float(tracking_confidence))  # type: ignore[index]
        if quality_score is not None:
            session_acc["quality_scores"].append(float(quality_score))  # type: ignore[index]
        if scene_id_value is not None:
            session_acc["scene_ids"].append(scene_id_value)  # type: ignore[index]
        if cut_id_value is not None:
            session_acc["cut_ids"].append(cut_id_value)  # type: ignore[index]
        if cta_id_value is not None:
            session_acc["cta_ids"].append(cta_id_value)  # type: ignore[index]
        for key in AU_DEFAULTS:
            session_acc["au_norm"][key].append(float(au_norm_payload.get(key, 0.0)))  # type: ignore[index]

    return bucket_acc, session_bucket_acc


# ---------------------------------------------------------------------------
# Row construction from accumulated buckets
# ---------------------------------------------------------------------------

def build_bucket_row(
    acc: Dict[str, object],
    bucket_start: int,
    scene_graph: SceneGraphContext,
    global_blink_baseline: float,
    playback_penalty: float,
    label_signal_raw: float,
    config: ReadoutMetricConfig,
    *,
    fallback_blink_rate: Optional[float] = None,
) -> Dict[str, object]:
    """Build a single bucket-row dict from an accumulated bucket.

    Shared by both per-session and aggregate row construction.
    """
    aligned_scene_id, aligned_cut_id, aligned_cta_id = _resolve_scene_alignment(
        scene_graph,
        bucket_start,
    )
    scene_id_value = _first_present(acc["scene_ids"]) or aligned_scene_id  # type: ignore[arg-type]
    cut_id_value = _first_present(acc["cut_ids"]) or aligned_cut_id  # type: ignore[arg-type]
    cta_id_value = _first_present(acc["cta_ids"]) or aligned_cta_id  # type: ignore[arg-type]

    face_presence = _mean_optional(acc["face_presence"])  # type: ignore[arg-type]
    head_pose_stability = _mean_optional(acc["head_pose_stability"])  # type: ignore[arg-type]
    gaze_on_screen = _mean_optional(acc["gaze_on_screen"])  # type: ignore[arg-type]
    eye_openness = _mean_optional(acc["eye_openness"])  # type: ignore[arg-type]
    blink_rate_value = (
        _mean(acc["blink_rates"])  # type: ignore[arg-type]
        if len(acc["blink_rates"]) > 0  # type: ignore[arg-type]
        else (fallback_blink_rate if fallback_blink_rate is not None else 0.0)
    )
    blink_baseline_value = (
        _mean(acc["blink_baselines"])  # type: ignore[arg-type]
        if len(acc["blink_baselines"]) > 0  # type: ignore[arg-type]
        else global_blink_baseline
    )
    blink_inhibition_value = _mean_optional(acc["blink_inhibition_scores"])  # type: ignore[arg-type]
    if blink_inhibition_value is None:
        blink_inhibition_value = compute_blink_inhibition(blink_rate_value, blink_baseline_value)
    tracking_confidence_value = _mean_optional(acc["tracking_confidences"])  # type: ignore[arg-type]
    quality_score_value = _mean_optional(acc["quality_scores"])  # type: ignore[arg-type]
    playback_continuity = clamp(1.0 - (PLAYBACK_PENALTY_FACTOR * playback_penalty), 0.0, 1.0)
    label_signal = clamp(label_signal_raw, -1.0, 1.0)
    dial_value = _mean_optional(acc["dial_values"])  # type: ignore[arg-type]
    au4_value = _mean(acc["au_norm"]["AU04"])  # type: ignore[index]
    au6_value = _mean(acc["au_norm"]["AU06"])  # type: ignore[index]
    au12_value = _mean(acc["au_norm"]["AU12"])  # type: ignore[index]
    attention_score = compute_attention_score(
        face_presence=face_presence,
        head_pose_stability=head_pose_stability,
        gaze_on_screen=gaze_on_screen,
        eye_openness=eye_openness,
        blink_inhibition=blink_inhibition_value,
        playback_continuity=playback_continuity,
        au12=au12_value,
        au6=au6_value,
        au4=au4_value,
        tracking_confidence=tracking_confidence_value,
        quality_score=quality_score_value,
        config=config,
    )
    observed_reward_proxy = _mean_optional(acc["reward_proxy_values"])  # type: ignore[arg-type]
    reward_proxy_value = (
        round(observed_reward_proxy, 6)
        if observed_reward_proxy is not None
        else None
    )

    return {
        "bucket_start": bucket_start,
        "scene_id": scene_id_value,
        "cut_id": cut_id_value,
        "cta_id": cta_id_value,
        "attention_score": attention_score,
        "attention_velocity": 0.0,
        "face_presence": face_presence,
        "head_pose_stability": head_pose_stability,
        "gaze_on_screen": gaze_on_screen,
        "eye_openness": eye_openness,
        "gaze_direct_coverage": (
            _mean(acc["direct_gaze_flags"])  # type: ignore[arg-type]
            if len(acc["direct_gaze_flags"]) > 0  # type: ignore[arg-type]
            else 0.0
        ),
        "blink_rate": round(blink_rate_value, 6),
        "blink_baseline_rate": round(blink_baseline_value, 6),
        "blink_inhibition": round(float(blink_inhibition_value), 6),
        "mean_brightness": _mean(acc["brightness"]),  # type: ignore[arg-type]
        "mean_occlusion_score": _mean_optional(acc["occlusion_scores"]),  # type: ignore[arg-type]
        "mean_head_pose_valid_pct": _mean_optional(acc["head_pose_valid_pcts"]),  # type: ignore[arg-type]
        "reward_proxy": reward_proxy_value,
        "tracking_confidence": tracking_confidence_value,
        "quality_score": quality_score_value,
        "label_signal": float(label_signal),
        "dial": dial_value,
        "playback_penalty": float(playback_penalty),
        "playback_continuity": float(playback_continuity),
        "au4": float(au4_value),
        "au6": float(au6_value),
        "au12": float(au12_value),
        "reward_proxy_observed": observed_reward_proxy is not None,
        "valence_proxy": None,
        "arousal_proxy": None,
        "novelty_proxy": None,
        "au_norm": {
            au_name: _mean(acc["au_norm"][au_name])  # type: ignore[index]
            for au_name in AU_DEFAULTS
        },
    }


# ---------------------------------------------------------------------------
# Velocity + reward decomposition
# ---------------------------------------------------------------------------

def apply_velocity_and_reward_decomposition(
    rows: List[Dict[str, object]],
    velocities: List[float],
    global_blink_baseline: float,
    config: ReadoutMetricConfig,
) -> None:
    """Assign attention velocity and compute reward decomposition in-place.

    This is the shared inner loop for both per-session and aggregate bucket
    rows.  It patches ``attention_velocity``, ``reward_proxy``,
    ``valence_proxy``, ``arousal_proxy``, and ``novelty_proxy`` on each row.
    """
    for index, row in enumerate(rows):
        row["attention_velocity"] = (
            round(velocities[index], 6) if index < len(velocities) else 0.0
        )
        previous_row = rows[index - 1] if index > 0 else None
        scene_change_signal = 0.0
        if previous_row is not None:
            if (
                row.get("scene_id") is not None
                and previous_row.get("scene_id") is not None
                and row.get("scene_id") != previous_row.get("scene_id")
            ):
                scene_change_signal = max(scene_change_signal, 1.0)
            if (
                row.get("cut_id") is not None
                and previous_row.get("cut_id") is not None
                and row.get("cut_id") != previous_row.get("cut_id")
            ):
                scene_change_signal = max(scene_change_signal, 0.7)
            if (
                row.get("cta_id") is not None
                and previous_row.get("cta_id") is not None
                and row.get("cta_id") != previous_row.get("cta_id")
            ):
                scene_change_signal = max(scene_change_signal, 0.6)

        playback_penalty = float(row.get("playback_penalty", 0.0))
        telemetry_disruption = clamp(playback_penalty / 2.5, 0.0, 1.0)
        playback_continuity = clamp(
            float(
                row.get(
                    "playback_continuity",
                    1.0 if playback_penalty <= 0 else 1.0 - (PLAYBACK_PENALTY_FACTOR * playback_penalty),
                )
            ),
            0.0,
            1.0,
        )
        reward_decomposition = compute_reward_proxy_decomposition(
            attention_score=float(row["attention_score"]),
            attention_velocity=float(row["attention_velocity"]),
            au12=float(row.get("au12", 0.0)),
            au6=float(row.get("au6", 0.0)),
            au4=float(row.get("au4", 0.0)),
            blink_rate=float(row["blink_rate"]),
            blink_baseline_rate=max(
                float(row.get("blink_baseline_rate", global_blink_baseline) or global_blink_baseline),
                1e-3,
            ),
            blink_inhibition=float(row["blink_inhibition"]) if row.get("blink_inhibition") is not None else None,
            label_signal=float(row.get("label_signal", 0.0)),
            dial=float(row["dial"]) if row.get("dial") is not None else None,
            playback_continuity=playback_continuity,
            scene_change_signal=scene_change_signal,
            telemetry_disruption=telemetry_disruption,
            tracking_confidence=float(row["tracking_confidence"]) if row.get("tracking_confidence") is not None else None,
            quality_score=float(row["quality_score"]) if row.get("quality_score") is not None else None,
            config=config,
        )
        reward_proxy_value = reward_decomposition.reward_proxy
        if row.get("reward_proxy_observed") and row.get("reward_proxy") is not None:
            reward_proxy_value = round(
                clamp(
                    (REWARD_BLEND_CURRENT_WEIGHT * reward_proxy_value) + (REWARD_BLEND_HISTORICAL_WEIGHT * float(row["reward_proxy"])),
                    0.0,
                    100.0,
                ),
                6,
            )
        row["reward_proxy"] = reward_proxy_value
        row["valence_proxy"] = reward_decomposition.valence_proxy
        row["arousal_proxy"] = reward_decomposition.arousal_proxy
        row["novelty_proxy"] = reward_decomposition.novelty_proxy
