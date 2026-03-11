"""Dataset export from Postgres sessions + trace points."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from .feature_extraction import extract_video_features


def _normalize_video_path(source_url: Optional[str]) -> Optional[Path]:
    if not source_url:
        return None
    if source_url.startswith("file://"):
        return Path(source_url[len("file://") :])
    candidate = Path(source_url)
    if candidate.exists():
        return candidate
    return None


def _au_value(payload: object, key: str) -> float:
    if payload is None:
        return 0.0
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return 0.0
    if not isinstance(payload, dict):
        return 0.0
    value = payload.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _attention_proxy(au_norm: object, blink: float) -> float:
    au12 = _au_value(au_norm, "AU12")
    au6 = _au_value(au_norm, "AU06")
    au4 = _au_value(au_norm, "AU04")
    raw = au12 * 0.55 + au6 * 0.35 - au4 * 0.2 - blink * 0.45
    return float(np.clip(50.0 + raw * 50.0, 0.0, 100.0))


def _aggregate_trace_per_second(trace_frame: pd.DataFrame) -> pd.DataFrame:
    if trace_frame.empty:
        return pd.DataFrame(columns=["second", "attention", "blink_inhibition", "dial"])

    frame = trace_frame.copy()
    frame["second"] = (frame["t_ms"] // 1000).astype(int)
    frame["blink"] = frame["blink"].astype(float)
    frame["attention"] = frame.apply(
        lambda row: _attention_proxy(row.get("au_norm"), float(row.get("blink", 0.0))),
        axis=1,
    )
    frame["dial"] = pd.to_numeric(frame.get("dial"), errors="coerce")

    grouped = (
        frame.groupby("second", as_index=False)
        .agg(
            attention=("attention", "mean"),
            blink_rate=("blink", "mean"),
            dial=("dial", "mean"),
        )
        .sort_values("second")
    )
    grouped["blink_inhibition"] = 1.0 - grouped["blink_rate"]
    return grouped[["second", "attention", "blink_inhibition", "dial"]]


def export_training_dataset(database_url: str, output_path: Path) -> pd.DataFrame:
    """Export per-second training dataset from Postgres-backed sessions.

    Rows include:
    - session_id, video_id, second
    - feature columns: shot_change_rate, brightness, motion_magnitude, audio_rms
    - targets: attention, blink_inhibition, dial
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
        SELECT t_ms, blink, dial, au_norm
        FROM trace_points
        WHERE session_id = CAST(:session_id AS uuid)
        ORDER BY t_ms ASC
        """
    )

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
            target_frame = _aggregate_trace_per_second(trace_frame)
            if target_frame.empty:
                continue

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
            dataset_frames.append(merged)

    if dataset_frames:
        dataset = pd.concat(dataset_frames, ignore_index=True)
    else:
        dataset = pd.DataFrame(
            columns=[
                "session_id",
                "video_id",
                "second",
                "shot_change_rate",
                "brightness",
                "motion_magnitude",
                "audio_rms",
                "attention",
                "blink_inhibition",
                "dial",
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)
    return dataset
