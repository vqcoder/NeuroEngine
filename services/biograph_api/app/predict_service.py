"""Prediction service bridging API uploads and ml_pipeline artifacts."""

from __future__ import annotations

import logging
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

from .readout_metrics import clamp
from .schemas import PredictTracePoint


# ---------------------------------------------------------------------------
# Named constants for heuristic / enrichment magic numbers
# ---------------------------------------------------------------------------

# -- Blink-rate proxy (enrichment fallback) --
BLINK_RATE_BASELINE = 0.45          # resting blink rate (blinks/sec)
BLINK_RATE_INHIBITION_SLOPE = 0.35  # how much inhibition suppresses blink rate
BLINK_RATE_MIN = 0.02
BLINK_RATE_MAX = 0.85

# -- Valence proxy weights (enrichment fallback) --
VALENCE_ATTENTION_WEIGHT = 0.65
VALENCE_DIAL_WEIGHT = 0.35

# -- Arousal proxy parameters (enrichment fallback) --
AROUSAL_BASELINE = 25.0
AROUSAL_VELOCITY_SCALE = 5.0       # multiplier on |attention_velocity|
AROUSAL_INHIBITION_PENALTY = 20.0  # penalty for negative blink inhibition

# -- Novelty proxy parameters (enrichment fallback) --
NOVELTY_BASELINE = 15.0
NOVELTY_VELOCITY_SCALE = 8.0      # multiplier on |attention_velocity|

# -- Heuristic blink-rate waveform --
HEURISTIC_BLINK_RATE_BASELINE = 0.24
HEURISTIC_BLINK_RATE_MIN = 0.06
HEURISTIC_BLINK_RATE_MAX = 0.52
HEURISTIC_BLINK_RATE_CEILING = 0.60  # normaliser for inhibition derivation

# -- Heuristic attention parameters --
HEURISTIC_ATTENTION_BASELINE = 24.0
HEURISTIC_ATTENTION_BLINK_WEIGHT = 0.62   # blink inhibition contribution
HEURISTIC_ATTENTION_CONTINUITY_WEIGHT = 12.0

# -- Heuristic reward-proxy AU weights --
HEURISTIC_REWARD_BASELINE = 20.0
HEURISTIC_REWARD_AU12_WEIGHT = 48.0   # smile / zygomaticus
HEURISTIC_REWARD_AU6_WEIGHT = 24.0    # cheek raiser / orbicularis
HEURISTIC_REWARD_AU4_PENALTY = 34.0   # brow lowerer (negative valence)
HEURISTIC_REWARD_NOVELTY_WEIGHT = 8.0

# -- Heuristic dial blend --
HEURISTIC_DIAL_REWARD_WEIGHT = 0.55
HEURISTIC_DIAL_ATTENTION_WEIGHT = 0.25


def _estimate_duration_seconds(video_path: Path) -> int:
    """Estimate video duration in seconds via ffprobe; fallback to 60s."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        duration_sec = int(round(float(result.stdout.strip())))
        return max(duration_sec, 1)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError):
        logger.warning("ffprobe duration estimation failed for %s, defaulting to 60s", video_path, exc_info=True)
        return 60


def _enrich_predict_trace_points(points: List[PredictTracePoint]) -> List[PredictTracePoint]:
    if not points:
        return points

    sorted_points = sorted(points, key=lambda row: row.t_sec)
    previous_attention: float | None = None
    previous_second: float | None = None

    enriched: List[PredictTracePoint] = []
    for point in sorted_points:
        reward_proxy = clamp(float(point.reward_proxy if point.reward_proxy is not None else point.attention or 0.0), 0.0, 100.0)
        attention = clamp(float(point.attention if point.attention is not None else reward_proxy), 0.0, 100.0)
        dt = 1.0 if previous_second is None else max(0.001, float(point.t_sec - previous_second))
        computed_attention_velocity = (
            0.0 if previous_attention is None else float((attention - previous_attention) / dt)
        )
        blink_inhibition = clamp(float(point.blink_inhibition), 0.0, 100.0)
        blink_inhibition_norm = blink_inhibition / 100.0
        dial = clamp(float(point.dial), 0.0, 100.0)

        enriched_point = PredictTracePoint(
            t_sec=float(point.t_sec),
            reward_proxy=reward_proxy,
            dopamine_score=point.dopamine_score if point.dopamine_score is not None else reward_proxy,
            attention=attention,
            blink_inhibition=blink_inhibition,
            dial=dial,
            attention_velocity=(
                float(point.attention_velocity)
                if point.attention_velocity is not None
                else float(round(computed_attention_velocity, 6))
            ),
            blink_rate=(
                float(point.blink_rate)
                if point.blink_rate is not None
                else float(clamp(
                    BLINK_RATE_BASELINE - BLINK_RATE_INHIBITION_SLOPE * blink_inhibition_norm,
                    BLINK_RATE_MIN,
                    BLINK_RATE_MAX,
                ))
            ),
            valence_proxy=(
                float(point.valence_proxy)
                if point.valence_proxy is not None
                else float(clamp(
                    attention * VALENCE_ATTENTION_WEIGHT + dial * VALENCE_DIAL_WEIGHT,
                    0.0, 100.0,
                ))
            ),
            arousal_proxy=(
                float(point.arousal_proxy)
                if point.arousal_proxy is not None
                else float(
                    clamp(
                        AROUSAL_BASELINE
                        + abs(computed_attention_velocity) * AROUSAL_VELOCITY_SCALE
                        + max(0.0, -blink_inhibition) * AROUSAL_INHIBITION_PENALTY,
                        0.0,
                        100.0,
                    )
                )
            ),
            novelty_proxy=(
                float(point.novelty_proxy)
                if point.novelty_proxy is not None
                else float(clamp(
                    NOVELTY_BASELINE + abs(computed_attention_velocity) * NOVELTY_VELOCITY_SCALE,
                    0.0, 100.0,
                ))
            ),
            tracking_confidence=(
                float(point.tracking_confidence)
                if point.tracking_confidence is not None
                else 1.0
            ),
        )
        enriched.append(enriched_point)
        previous_attention = attention
        previous_second = float(point.t_sec)

    return enriched


@dataclass(frozen=True)
class PredictExecution:
    predictions: List[PredictTracePoint]
    backend: str


def _heuristic_predictions(duration_seconds: int) -> List[PredictTracePoint]:
    """Generate deterministic fallback predictions for demo/dev availability."""

    if duration_seconds <= 0:
        duration_seconds = 60

    rows: List[PredictTracePoint] = []
    for t_sec in range(duration_seconds + 1):
        phase = t_sec / max(duration_seconds, 1)
        blink_rate_proxy = clamp(
            HEURISTIC_BLINK_RATE_BASELINE
            + 0.10 * math.sin(2.0 * math.pi * phase * 3.1)
            + 0.05 * math.cos(2.0 * math.pi * phase * 6.2),
            HEURISTIC_BLINK_RATE_MIN,
            HEURISTIC_BLINK_RATE_MAX,
        )
        blink_inhibition = clamp(
            100.0 * (1.0 - (blink_rate_proxy / HEURISTIC_BLINK_RATE_CEILING))
            + 5.0 * math.sin(2.0 * math.pi * phase * 2.4),
            0.0,
            100.0,
        )
        playback_continuity = clamp(
            1.0
            - 0.12 * max(0.0, math.sin(2.0 * math.pi * phase * 1.4 + 0.5)),
            0.65,
            1.0,
        )
        attention = clamp(
            HEURISTIC_ATTENTION_BASELINE
            + (HEURISTIC_ATTENTION_BLINK_WEIGHT * blink_inhibition)
            + (HEURISTIC_ATTENTION_CONTINUITY_WEIGHT * playback_continuity)
            + 4.0 * math.sin(2.0 * math.pi * phase * 4.8),
            0.0,
            100.0,
        )

        # Facial-coding proxy channels (AU-like dynamics) drive reward separately.
        au12 = clamp(0.34 + 0.30 * math.sin(2.0 * math.pi * phase * 2.1 + 0.4), 0.0, 1.0)
        au6 = clamp(0.22 + 0.26 * math.sin(2.0 * math.pi * phase * 1.7 + 1.2), 0.0, 1.0)
        au4 = clamp(0.16 + 0.24 * math.cos(2.0 * math.pi * phase * 2.8 + 0.9), 0.0, 1.0)
        novelty_pulse = max(0.0, math.sin(2.0 * math.pi * phase * 4.0))

        reward_proxy = clamp(
            HEURISTIC_REWARD_BASELINE
            + (HEURISTIC_REWARD_AU12_WEIGHT * au12)
            + (HEURISTIC_REWARD_AU6_WEIGHT * au6)
            - (HEURISTIC_REWARD_AU4_PENALTY * au4)
            + (HEURISTIC_REWARD_NOVELTY_WEIGHT * novelty_pulse),
            0.0,
            100.0,
        )
        dial = clamp(
            (HEURISTIC_DIAL_REWARD_WEIGHT * reward_proxy)
            + (HEURISTIC_DIAL_ATTENTION_WEIGHT * attention)
            + 6.0 * math.sin(2.0 * math.pi * phase * 1.7),
            0.0,
            100.0,
        )
        rows.append(
            PredictTracePoint(
                t_sec=float(t_sec),
                reward_proxy=float(reward_proxy),
                attention=float(attention),
                blink_inhibition=float(blink_inhibition),
                dial=float(dial),
            )
        )

    return _enrich_predict_trace_points(rows)


def predict_from_video_with_backend(video_path: Path, model_artifact_path: Path) -> PredictExecution:
    """Run model inference for uploaded video and return predicted traces + backend label.

    Fallback behavior:
    - If the trained model artifact is missing, return heuristic predictions.
    - If ml_pipeline is unavailable in the runtime image, return heuristic predictions.
    """

    if not model_artifact_path.exists():
        return PredictExecution(
            predictions=_heuristic_predictions(_estimate_duration_seconds(video_path)),
            backend="heuristic_fallback_missing_artifact",
        )

    try:
        from ml_pipeline.infer import predict_video_file, predictions_to_records
    except ImportError:  # pragma: no cover - environment-dependent
        logger.info("ml_pipeline not available; falling back to heuristic predictions")
        return PredictExecution(
            predictions=_heuristic_predictions(_estimate_duration_seconds(video_path)),
            backend="heuristic_fallback_missing_ml_pipeline",
        )

    try:
        prediction_frame = predict_video_file(video_path=video_path, model_artifact_path=model_artifact_path)
        records = predictions_to_records(prediction_frame)
    except Exception:
        logger.warning("ML pipeline inference failed for %s; falling back to heuristics", video_path, exc_info=True)
        return PredictExecution(
            predictions=_heuristic_predictions(_estimate_duration_seconds(video_path)),
            backend="heuristic_fallback_inference_error",
        )

    return PredictExecution(
        predictions=_enrich_predict_trace_points(
            [PredictTracePoint.model_validate(record) for record in records]
        ),
        backend="ml_pipeline_artifact",
    )


def predict_from_video(video_path: Path, model_artifact_path: Path) -> List[PredictTracePoint]:
    """Backward-compatible helper that returns only prediction rows."""

    return predict_from_video_with_backend(
        video_path=video_path,
        model_artifact_path=model_artifact_path,
    ).predictions
