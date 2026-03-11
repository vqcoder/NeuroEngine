"""Dataset export from Postgres sessions + passive/explicit label signals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from .feature_extraction import extract_video_features

TRACE_FEATURE_COLUMNS = [
    "second",
    "scene_id",
    "cut_id",
    "cta_id",
    "scene_transition",
    "cut_transition",
    "cta_active",
    "blink_rate",
    "rolling_blink_rate",
    "blink_inhibition",
    "dial",
    "observed_reward_proxy",
    "face_ok_rate",
    "face_presence_confidence",
    "gaze_on_screen_proxy",
    "capture_brightness",
    "capture_blur",
    "quality_score",
    "quality_confidence",
    "fps_stability",
    "face_visible_pct",
    "occlusion_score",
    "head_pose_valid_pct",
    "au12_norm",
    "au6_norm",
    "au4_norm",
    "head_pose_abs_yaw",
    "head_pose_abs_pitch",
    "head_pose_abs_roll",
]

PLAYBACK_FEATURE_COLUMNS = [
    "playback_play_count",
    "playback_pause_count",
    "playback_seek_count",
    "playback_rewind_count",
    "playback_mute_count",
    "playback_unmute_count",
    "playback_fullscreen_enter_count",
    "playback_fullscreen_exit_count",
    "playback_visibility_hidden_count",
    "playback_visibility_visible_count",
    "playback_window_blur_count",
    "playback_window_focus_count",
    "playback_session_incomplete_count",
    "playback_ended_count",
    "playback_event_count_total",
    "playback_friction_count",
]

ANNOTATION_FEATURE_COLUMNS = [
    "engaging_marker_count",
    "confusing_marker_count",
    "stop_marker_count",
    "cta_marker_count",
    "annotation_count_total",
]

SURVEY_FEATURE_COLUMNS = [
    "survey_overall_interest",
    "survey_recall_comprehension",
    "survey_desire_to_continue",
    "survey_completion_score",
    "survey_annotation_completion_score",
]

EXPORT_COLUMNS = [
    "session_id",
    "video_id",
    "second",
    "shot_change_rate",
    "brightness",
    "motion_magnitude",
    "audio_rms",
    *TRACE_FEATURE_COLUMNS[1:],
    *PLAYBACK_FEATURE_COLUMNS,
    *ANNOTATION_FEATURE_COLUMNS,
    *SURVEY_FEATURE_COLUMNS,
    "reward_proxy",
    "attention",
    "blink_inhibition",
    "dial",
]

ANNOTATION_COLUMN_BY_TYPE = {
    "engaging_moment": "engaging_marker_count",
    "confusing_moment": "confusing_marker_count",
    "stop_watching_moment": "stop_marker_count",
    "cta_landed_moment": "cta_marker_count",
}

SURVEY_KEYS = {
    "overall_interest": {"overall_interest_likert", "overall_engagement_likert"},
    "recall_comprehension": {"recall_comprehension_likert"},
    "desire_to_continue": {
        "desire_to_continue_or_take_action_likert",
        "desire_to_keep_watching_likert",
    },
}


def _normalize_video_path(source_url: Optional[str]) -> Optional[Path]:
    if not source_url:
        return None
    if source_url.startswith("file://"):
        return Path(source_url[len("file://") :])
    candidate = Path(source_url)
    if candidate.exists():
        return candidate
    return None


def _safe_json_dict(payload: object) -> Dict[str, object]:
    if payload is None:
        return {}
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _au_value(payload: object, key: str) -> float:
    value = _safe_json_dict(payload).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _head_pose_value(payload: object, key: str) -> float:
    value = _safe_json_dict(payload).get(key, 0.0)
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_numeric_series(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(default, index=frame.index, dtype=float)


def _safe_bool_series(frame: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float(default), index=frame.index, dtype=float)
    return frame[column].fillna(default).astype(bool).astype(float)


def _normalize_id(value: object) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    if text_value == "" or text_value.lower() == "nan":
        return None
    return text_value


def _first_non_empty_string(values: Sequence[object]) -> Optional[str]:
    for value in values:
        normalized = _normalize_id(value)
        if normalized is not None:
            return normalized
    return None


def _transition_flags(values: pd.Series) -> pd.Series:
    normalized = values.apply(_normalize_id)
    previous = normalized.shift(1)
    transitioned = (normalized.notna() & previous.notna() & (normalized != previous)).astype(float)
    if not transitioned.empty:
        transitioned.iloc[0] = 0.0
    return transitioned


def _mean_or_empty(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _aggregate_trace_per_second(trace_frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate passive trace rows into per-second passive features."""

    if trace_frame.empty:
        return pd.DataFrame(columns=TRACE_FEATURE_COLUMNS)

    frame = trace_frame.copy()
    video_time_series = _safe_numeric_series(frame, "video_time_ms")
    if video_time_series.isna().all():
        video_time_series = _safe_numeric_series(frame, "t_ms")

    frame = frame.loc[video_time_series.notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=TRACE_FEATURE_COLUMNS)

    frame["video_time_ms"] = video_time_series.loc[frame.index]
    frame["second"] = (frame["video_time_ms"] // 1000).astype(int)
    frame["blink"] = _safe_numeric_series(frame, "blink", default=0.0).clip(0.0, 1.0)
    frame["rolling_blink_rate"] = _safe_numeric_series(frame, "rolling_blink_rate", default=0.0)
    frame["blink_inhibition_score"] = _safe_numeric_series(frame, "blink_inhibition_score")
    frame["dial"] = _safe_numeric_series(frame, "dial")
    frame["reward_proxy"] = _safe_numeric_series(frame, "reward_proxy")
    frame["face_ok"] = _safe_bool_series(frame, "face_ok", default=False)
    frame["face_presence_confidence"] = _safe_numeric_series(frame, "face_presence_confidence", default=0.0)
    frame["gaze_on_screen_proxy"] = _safe_numeric_series(frame, "gaze_on_screen_proxy")
    frame["brightness"] = _safe_numeric_series(frame, "brightness")
    frame["blur"] = _safe_numeric_series(frame, "blur")
    frame["quality_score"] = _safe_numeric_series(frame, "quality_score")
    frame["quality_confidence"] = _safe_numeric_series(frame, "quality_confidence")
    frame["fps_stability"] = _safe_numeric_series(frame, "fps_stability")
    frame["face_visible_pct"] = _safe_numeric_series(frame, "face_visible_pct")
    frame["occlusion_score"] = _safe_numeric_series(frame, "occlusion_score")
    frame["head_pose_valid_pct"] = _safe_numeric_series(frame, "head_pose_valid_pct")
    frame["au12_norm"] = frame.get("au_norm", pd.Series([None] * len(frame))).apply(
        lambda payload: _au_value(payload, "AU12")
    )
    frame["au6_norm"] = frame.get("au_norm", pd.Series([None] * len(frame))).apply(
        lambda payload: _au_value(payload, "AU06")
    )
    frame["au4_norm"] = frame.get("au_norm", pd.Series([None] * len(frame))).apply(
        lambda payload: _au_value(payload, "AU04")
    )
    frame["head_pose_abs_yaw"] = frame.get("head_pose", pd.Series([None] * len(frame))).apply(
        lambda payload: abs(_head_pose_value(payload, "yaw"))
    )
    frame["head_pose_abs_pitch"] = frame.get("head_pose", pd.Series([None] * len(frame))).apply(
        lambda payload: abs(_head_pose_value(payload, "pitch"))
    )
    frame["head_pose_abs_roll"] = frame.get("head_pose", pd.Series([None] * len(frame))).apply(
        lambda payload: abs(_head_pose_value(payload, "roll"))
    )
    frame["scene_id"] = frame.get("scene_id", pd.Series([None] * len(frame))).apply(_normalize_id)
    frame["cut_id"] = frame.get("cut_id", pd.Series([None] * len(frame))).apply(_normalize_id)
    frame["cta_id"] = frame.get("cta_id", pd.Series([None] * len(frame))).apply(_normalize_id)

    grouped = (
        frame.groupby("second", as_index=False)
        .agg(
            scene_id=("scene_id", _first_non_empty_string),
            cut_id=("cut_id", _first_non_empty_string),
            cta_id=("cta_id", _first_non_empty_string),
            blink_rate=("blink", "mean"),
            rolling_blink_rate=("rolling_blink_rate", "mean"),
            blink_inhibition_raw=("blink_inhibition_score", "mean"),
            dial=("dial", "mean"),
            observed_reward_proxy=("reward_proxy", "mean"),
            face_ok_rate=("face_ok", "mean"),
            face_presence_confidence=("face_presence_confidence", "mean"),
            gaze_on_screen_proxy=("gaze_on_screen_proxy", "mean"),
            capture_brightness=("brightness", "mean"),
            capture_blur=("blur", "mean"),
            quality_score=("quality_score", "mean"),
            quality_confidence=("quality_confidence", "mean"),
            fps_stability=("fps_stability", "mean"),
            face_visible_pct=("face_visible_pct", "mean"),
            occlusion_score=("occlusion_score", "mean"),
            head_pose_valid_pct=("head_pose_valid_pct", "mean"),
            au12_norm=("au12_norm", "mean"),
            au6_norm=("au6_norm", "mean"),
            au4_norm=("au4_norm", "mean"),
            head_pose_abs_yaw=("head_pose_abs_yaw", "mean"),
            head_pose_abs_pitch=("head_pose_abs_pitch", "mean"),
            head_pose_abs_roll=("head_pose_abs_roll", "mean"),
        )
        .sort_values("second")
    )

    grouped["blink_inhibition"] = (
        ((grouped["blink_inhibition_raw"] + 1.0) / 2.0)
        .where(grouped["blink_inhibition_raw"].notna(), 1.0 - grouped["blink_rate"])
        .clip(0.0, 1.0)
    )
    grouped["scene_transition"] = _transition_flags(grouped["scene_id"])
    grouped["cut_transition"] = _transition_flags(grouped["cut_id"])
    grouped["cta_active"] = grouped["cta_id"].notna().astype(float)
    grouped.drop(columns=["blink_inhibition_raw"], inplace=True)

    for column in TRACE_FEATURE_COLUMNS:
        if column not in grouped.columns:
            grouped[column] = np.nan

    return grouped[TRACE_FEATURE_COLUMNS]


def _aggregate_playback_per_second(playback_frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate playback telemetry into per-second behavior features."""

    if playback_frame.empty:
        return pd.DataFrame(columns=["second", *PLAYBACK_FEATURE_COLUMNS])

    frame = playback_frame.copy()
    video_time_series = _safe_numeric_series(frame, "video_time_ms")
    frame = frame.loc[video_time_series.notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["second", *PLAYBACK_FEATURE_COLUMNS])

    frame["video_time_ms"] = video_time_series.loc[frame.index]
    frame["second"] = (frame["video_time_ms"] // 1000).astype(int)
    frame["event_type"] = (
        frame.get("event_type", pd.Series(["unknown"] * len(frame))).astype(str).str.strip().str.lower()
    )

    counts = frame.groupby(["second", "event_type"]).size().unstack(fill_value=0)
    result = pd.DataFrame({"second": counts.index.astype(int)})

    def _sum_event(names: Sequence[str]) -> pd.Series:
        available = [name for name in names if name in counts.columns]
        if not available:
            return pd.Series(0.0, index=counts.index, dtype=float)
        return counts[available].sum(axis=1).astype(float)

    result["playback_play_count"] = _sum_event(["play", "playback_started"])
    result["playback_pause_count"] = _sum_event(["pause"])
    result["playback_seek_count"] = _sum_event(["seek_end", "seek"])
    result["playback_rewind_count"] = _sum_event(["rewind"])
    result["playback_mute_count"] = _sum_event(["mute"])
    result["playback_unmute_count"] = _sum_event(["unmute"])
    result["playback_fullscreen_enter_count"] = _sum_event(["fullscreen_enter"])
    result["playback_fullscreen_exit_count"] = _sum_event(["fullscreen_exit"])
    result["playback_visibility_hidden_count"] = _sum_event(["visibility_hidden"])
    result["playback_visibility_visible_count"] = _sum_event(["visibility_visible"])
    result["playback_window_blur_count"] = _sum_event(["window_blur"])
    result["playback_window_focus_count"] = _sum_event(["window_focus"])
    result["playback_session_incomplete_count"] = _sum_event(
        ["session_incomplete", "abandonment", "incomplete_session", "abandon"]
    )
    result["playback_ended_count"] = _sum_event(["ended"])
    result["playback_event_count_total"] = counts.sum(axis=1).astype(float).to_numpy()
    result["playback_friction_count"] = (
        result["playback_pause_count"]
        + result["playback_seek_count"]
        + result["playback_rewind_count"]
        + result["playback_visibility_hidden_count"]
        + result["playback_window_blur_count"]
    )

    return result[["second", *PLAYBACK_FEATURE_COLUMNS]]


def _aggregate_annotations_per_second(annotation_frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate explicit timeline annotations per second."""

    if annotation_frame.empty:
        return pd.DataFrame(columns=["second", *ANNOTATION_FEATURE_COLUMNS])

    frame = annotation_frame.copy()
    video_time_series = _safe_numeric_series(frame, "video_time_ms")
    frame = frame.loc[video_time_series.notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["second", *ANNOTATION_FEATURE_COLUMNS])

    frame["second"] = (video_time_series.loc[frame.index] // 1000).astype(int)
    frame["marker_type"] = frame.get("marker_type", pd.Series([""] * len(frame))).astype(str).str.strip().str.lower()
    frame["mapped_type"] = frame["marker_type"].map(ANNOTATION_COLUMN_BY_TYPE)
    frame = frame.loc[frame["mapped_type"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["second", *ANNOTATION_FEATURE_COLUMNS])

    counts = frame.groupby(["second", "mapped_type"]).size().unstack(fill_value=0)
    result = pd.DataFrame({"second": counts.index.astype(int)})

    for column in ANNOTATION_FEATURE_COLUMNS:
        if column == "annotation_count_total":
            continue
        result[column] = counts[column].astype(float) if column in counts.columns else 0.0

    result["annotation_count_total"] = (
        result["engaging_marker_count"]
        + result["confusing_marker_count"]
        + result["stop_marker_count"]
        + result["cta_marker_count"]
    )

    return result[["second", *ANNOTATION_FEATURE_COLUMNS]]


def _normalize_likert_to_percent(value: Optional[float]) -> float:
    if value is None or np.isnan(value):
        return float("nan")
    if 1.0 <= value <= 5.0:
        return float(((value - 1.0) / 4.0) * 100.0)
    if 0.0 <= value <= 1.0:
        return float(value * 100.0)
    if 0.0 <= value <= 100.0:
        return float(value)
    return float("nan")


def _extract_latest_numeric_response(
    survey_frame: pd.DataFrame,
    question_keys: Sequence[str],
) -> float:
    if survey_frame.empty:
        return float("nan")

    normalized_keys = {key.lower() for key in question_keys}
    scoped = survey_frame.loc[
        survey_frame["question_key"].astype(str).str.lower().isin(normalized_keys)
    ]
    if scoped.empty:
        return float("nan")

    response_numbers = pd.to_numeric(scoped.get("response_number"), errors="coerce").dropna()
    if response_numbers.empty:
        return float("nan")
    return _normalize_likert_to_percent(float(response_numbers.iloc[-1]))


def _extract_survey_signals(survey_frame: pd.DataFrame) -> Dict[str, float]:
    """Extract scalar survey labels as normalized per-session features."""

    if survey_frame.empty:
        return {column: float("nan") for column in SURVEY_FEATURE_COLUMNS}

    overall_interest = _extract_latest_numeric_response(
        survey_frame, sorted(SURVEY_KEYS["overall_interest"])
    )
    recall_comprehension = _extract_latest_numeric_response(
        survey_frame, sorted(SURVEY_KEYS["recall_comprehension"])
    )
    desire_to_continue = _extract_latest_numeric_response(
        survey_frame, sorted(SURVEY_KEYS["desire_to_continue"])
    )

    completion_score = float("nan")
    annotation_completion_score = float("nan")

    for _, row in survey_frame.iterrows():
        key = str(row.get("question_key", "")).strip().lower()
        payload = _safe_json_dict(row.get("response_json"))
        if key == "session_completion_status":
            status = str(payload.get("status", "")).strip().lower()
            if status == "completed":
                completion_score = 100.0
            elif status == "incomplete":
                completion_score = 0.0
        elif key == "annotation_status":
            skipped = payload.get("annotation_skipped")
            if isinstance(skipped, bool):
                annotation_completion_score = 0.0 if skipped else 100.0

    return {
        "survey_overall_interest": overall_interest,
        "survey_recall_comprehension": recall_comprehension,
        "survey_desire_to_continue": desire_to_continue,
        "survey_completion_score": completion_score,
        "survey_annotation_completion_score": annotation_completion_score,
    }


def _centered_percent(frame: pd.DataFrame, column: str, default: float = 50.0) -> pd.Series:
    values = _mean_or_empty(frame, column, default=default)
    return (values - 50.0) / 50.0


def _compose_reward_proxy_target(frame: pd.DataFrame) -> pd.Series:
    """Compose calibrated reward proxy from passive + explicit signals.

    Uses a multi-signal composite when explicit reward labels are absent. This keeps
    webcam-only signals as diagnostic inputs, not direct ground-truth labels.
    """

    observed_reward = (
        pd.to_numeric(frame["observed_reward_proxy"], errors="coerce")
        if "observed_reward_proxy" in frame.columns
        else pd.Series(np.nan, index=frame.index, dtype=float)
    )

    au_component = (
        _mean_or_empty(frame, "au12_norm", 0.0) * 0.5
        + _mean_or_empty(frame, "au6_norm", 0.0) * 0.3
        - _mean_or_empty(frame, "au4_norm", 0.0) * 0.2
    ).clip(-1.0, 1.0)
    blink_component = (
        (_mean_or_empty(frame, "blink_inhibition", 0.5) - 0.5) * 1.2
        - _mean_or_empty(frame, "blink_rate", 0.0) * 0.4
        - _mean_or_empty(frame, "rolling_blink_rate", 0.0) * 0.25
    ).clip(-1.0, 1.0)
    playback_component = (
        -0.16 * _mean_or_empty(frame, "playback_friction_count", 0.0)
        - 0.35 * _mean_or_empty(frame, "playback_session_incomplete_count", 0.0)
        + 0.03 * _mean_or_empty(frame, "playback_play_count", 0.0)
    ).clip(-1.0, 1.0)
    annotation_component = (
        0.7 * _mean_or_empty(frame, "engaging_marker_count", 0.0)
        + 0.55 * _mean_or_empty(frame, "cta_marker_count", 0.0)
        - 0.65 * _mean_or_empty(frame, "confusing_marker_count", 0.0)
        - 0.8 * _mean_or_empty(frame, "stop_marker_count", 0.0)
    ).clip(-1.0, 1.0)
    survey_component = (
        _centered_percent(frame, "survey_overall_interest", default=50.0) * 0.4
        + _centered_percent(frame, "survey_recall_comprehension", default=50.0) * 0.25
        + _centered_percent(frame, "survey_desire_to_continue", default=50.0) * 0.35
    ).clip(-1.0, 1.0)
    dial_component = _centered_percent(frame, "dial", default=50.0).clip(-1.0, 1.0)
    quality_component = (
        (_mean_or_empty(frame, "quality_score", 0.5) - 0.5) * 0.6
        + (_mean_or_empty(frame, "face_ok_rate", 0.5) - 0.5) * 0.4
    ).clip(-1.0, 1.0)

    composite_reward = np.clip(
        50.0
        + au_component * 18.0
        + blink_component * 14.0
        + playback_component * 10.0
        + annotation_component * 22.0
        + survey_component * 18.0
        + dial_component * 10.0
        + quality_component * 8.0,
        0.0,
        100.0,
    )

    return observed_reward.where(observed_reward.notna(), composite_reward).astype(float)


def _read_sql_safe(connection, query: str, params: Dict[str, object]) -> pd.DataFrame:
    try:
        return pd.read_sql(text(query), connection, params=params)
    except Exception:
        return pd.DataFrame()


def export_training_dataset(database_url: str, output_path: Path) -> pd.DataFrame:
    """Export per-second dataset with passive signals and explicit labels.

    Rows include:
    - video-only model inputs: shot_change_rate, brightness, motion_magnitude, audio_rms
    - passive diagnostics: AU/blink/gaze/quality/playback telemetry
    - explicit labels: timeline markers and survey aggregates
    - targets: reward_proxy (primary), blink_inhibition, dial
    - backward-compatible alias: attention = reward_proxy
    """

    engine = create_engine(database_url, future=True)

    session_query = text(
        """
        SELECT s.id::text AS session_id, s.video_id::text AS video_id, v.source_url
        FROM sessions s
        JOIN videos v ON v.id = s.video_id
        ORDER BY s.created_at ASC
        """
    )

    trace_query = text(
        """
        SELECT *
        FROM trace_points
        WHERE session_id = CAST(:session_id AS uuid)
        ORDER BY COALESCE(video_time_ms, t_ms) ASC
        """
    )

    playback_query = """
        SELECT event_type, video_time_ms
        FROM session_playback_events
        WHERE session_id = CAST(:session_id AS uuid)
        ORDER BY video_time_ms ASC
    """

    annotation_query = """
        SELECT marker_type, video_time_ms
        FROM session_annotations
        WHERE session_id = CAST(:session_id AS uuid)
        ORDER BY video_time_ms ASC
    """

    survey_query = """
        SELECT question_key, response_number, response_json
        FROM survey_responses
        WHERE session_id = CAST(:session_id AS uuid)
        ORDER BY created_at ASC
    """

    dataset_frames: List[pd.DataFrame] = []
    feature_cache: Dict[str, pd.DataFrame] = {}

    with engine.connect() as connection:
        sessions = pd.read_sql(session_query, connection)
        for _, session_row in sessions.iterrows():
            session_id = str(session_row["session_id"])
            video_id = str(session_row["video_id"])
            source_url = session_row.get("source_url")

            trace_frame = pd.read_sql(
                trace_query,
                connection,
                params={"session_id": session_id},
            )
            if trace_frame.empty:
                continue

            trace_second = _aggregate_trace_per_second(trace_frame)
            if trace_second.empty:
                continue

            playback_frame = _read_sql_safe(
                connection,
                playback_query,
                params={"session_id": session_id},
            )
            playback_second = _aggregate_playback_per_second(playback_frame)

            annotation_frame = _read_sql_safe(
                connection,
                annotation_query,
                params={"session_id": session_id},
            )
            annotation_second = _aggregate_annotations_per_second(annotation_frame)

            survey_frame = _read_sql_safe(
                connection,
                survey_query,
                params={"session_id": session_id},
            )
            survey_signals = _extract_survey_signals(survey_frame)

            target_frame = trace_second.merge(playback_second, on="second", how="left")
            target_frame = target_frame.merge(annotation_second, on="second", how="left")

            for column in PLAYBACK_FEATURE_COLUMNS:
                if column not in target_frame.columns:
                    target_frame[column] = 0.0
                target_frame[column] = pd.to_numeric(target_frame[column], errors="coerce").fillna(0.0)

            for column in ANNOTATION_FEATURE_COLUMNS:
                if column not in target_frame.columns:
                    target_frame[column] = 0.0
                target_frame[column] = pd.to_numeric(target_frame[column], errors="coerce").fillna(0.0)

            for column in SURVEY_FEATURE_COLUMNS:
                target_frame[column] = survey_signals.get(column, float("nan"))

            target_frame["reward_proxy"] = _compose_reward_proxy_target(target_frame)
            target_frame["attention"] = target_frame["reward_proxy"]

            if video_id not in feature_cache:
                video_path = _normalize_video_path(source_url)
                if video_path is None:
                    continue
                feature_cache[video_id] = extract_video_features(video_path)

            merged = feature_cache[video_id].merge(target_frame, on="second", how="inner")
            if merged.empty:
                continue

            merged.insert(0, "video_id", video_id)
            merged.insert(0, "session_id", session_id)

            for column in EXPORT_COLUMNS:
                if column not in merged.columns:
                    merged[column] = np.nan

            dataset_frames.append(merged[EXPORT_COLUMNS])

    if dataset_frames:
        dataset = pd.concat(dataset_frames, ignore_index=True, sort=False)
    else:
        dataset = pd.DataFrame(columns=EXPORT_COLUMNS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)
    return dataset
