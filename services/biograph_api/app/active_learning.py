"""Active learning queue construction and simulation helpers."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Session as SessionModel
from .models import Video
from .readout_metrics import mean

from .schemas import (
    TestingQueueAssignment,
    TestingQueueItem,
    TestingQueueResponse,
    TestingQueueSegment,
    TestingUncertaintyPoint,
)



def _resolve_video_path(source_url: Optional[str]) -> Optional[Path]:
    if not source_url:
        return None
    if source_url.startswith("file://"):
        candidate = Path(source_url[len("file://") :])
    else:
        candidate = Path(source_url)
    return candidate if candidate.exists() else None


def _hook_weight(t_sec: float, half_life_sec: float) -> float:
    """Return an early-hook weighting factor in (0, 1]."""

    safe_half_life = max(half_life_sec, 0.001)
    return float(1.0 / (1.0 + max(t_sec, 0.0) / safe_half_life))


def _overlaps(a: TestingQueueSegment, b: TestingQueueSegment) -> bool:
    return not (a.end_sec <= b.start_sec or b.end_sec <= a.start_sec)


def _select_top_segments(
    points: Sequence[TestingUncertaintyPoint],
    segment_length_sec: int,
    per_video_segments: int,
    early_hook_half_life_sec: float,
) -> List[TestingQueueSegment]:
    if not points:
        return []
    if segment_length_sec <= 0:
        raise ValueError("segment_length_sec must be > 0")

    sorted_points = sorted(points, key=lambda row: row.t_sec)
    start_sec = sorted_points[0].t_sec
    end_sec = sorted_points[-1].t_sec
    by_second: Dict[int, TestingUncertaintyPoint] = {row.t_sec: row for row in sorted_points}

    candidates: List[TestingQueueSegment] = []
    for window_start in range(start_sec, end_sec + 1):
        window_end = window_start + segment_length_sec
        window_values = [
            row.uncertainty
            for second, row in by_second.items()
            if window_start <= second < window_end
        ]
        if not window_values:
            continue
        mean_uncertainty = mean(window_values)
        center = window_start + (segment_length_sec / 2.0)
        hook_weight = _hook_weight(center, early_hook_half_life_sec)
        impact_score = mean_uncertainty * hook_weight
        candidates.append(
            TestingQueueSegment(
                start_sec=window_start,
                end_sec=window_end,
                mean_uncertainty=mean_uncertainty,
                hook_weight=hook_weight,
                impact_score=impact_score,
            )
        )

    selected: List[TestingQueueSegment] = []
    for candidate in sorted(candidates, key=lambda row: row.impact_score, reverse=True):
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= per_video_segments:
            break

    return selected


def _predict_with_uncertainty(
    *,
    video_path: Path,
    model_artifact_path: Path,
    uncertainty_samples: int,
    seed: int,
) -> List[TestingUncertaintyPoint]:
    try:
        from ml_pipeline.infer import predict_video_with_uncertainty
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "ml_pipeline is not installed. Install ../ml (pip install ../ml)."
        ) from exc

    prediction_frame = predict_video_with_uncertainty(
        video_path=video_path,
        model_artifact_path=model_artifact_path,
        n_samples=uncertainty_samples,
        seed=seed,
    )

    rows: List[TestingUncertaintyPoint] = []
    for _, row in prediction_frame.iterrows():
        rows.append(
            TestingUncertaintyPoint(
                t_sec=int(math.floor(float(row.get("second", 0.0)))),
                attention=float(row.get("attention", 0.0)),
                blink_inhibition=float(row.get("blink_inhibition", 0.0)),
                dial=float(row.get("dial", 0.0)),
                uncertainty=max(float(row.get("uncertainty", 0.0)), 0.0),
            )
        )
    return rows


def pull_pending_videos(
    db: Session,
    *,
    target_sessions_per_video: int,
    max_candidates: int,
) -> List[Tuple[Video, int]]:
    """Return videos that still need additional sessions."""

    if target_sessions_per_video <= 0:
        raise ValueError("target_sessions_per_video must be > 0")

    session_counts = (
        select(
            SessionModel.video_id.label("video_id"),
            func.count(SessionModel.id).label("session_count"),
        )
        .group_by(SessionModel.video_id)
        .subquery()
    )

    query = (
        select(
            Video,
            func.coalesce(session_counts.c.session_count, 0).label("session_count"),
        )
        .outerjoin(session_counts, Video.id == session_counts.c.video_id)
        .where(func.coalesce(session_counts.c.session_count, 0) < target_sessions_per_video)
        .order_by(
            func.coalesce(session_counts.c.session_count, 0).asc(),
            Video.created_at.asc(),
        )
        .limit(max_candidates)
    )

    rows = db.execute(query).all()
    return [(row[0], int(row[1])) for row in rows]


def build_testing_queue(
    db: Session,
    *,
    model_artifact_path: Path,
    queue_size: int = 10,
    target_sessions_per_video: int = 3,
    segment_length_sec: int = 6,
    per_video_segments: int = 3,
    early_hook_half_life_sec: float = 20.0,
    uncertainty_samples: int = 16,
    seed: int = 42,
) -> TestingQueueResponse:
    """Build queue prioritized by uncertainty and expected early-hook impact."""

    pending_videos = pull_pending_videos(
        db,
        target_sessions_per_video=target_sessions_per_video,
        max_candidates=max(queue_size * 4, queue_size),
    )

    queue_items: List[TestingQueueItem] = []
    for video, existing_sessions in pending_videos:
        video_path = _resolve_video_path(video.source_url)
        if video_path is None:
            continue

        uncertainty_trace = _predict_with_uncertainty(
            video_path=video_path,
            model_artifact_path=model_artifact_path,
            uncertainty_samples=uncertainty_samples,
            seed=seed,
        )
        if not uncertainty_trace:
            continue

        segments = _select_top_segments(
            uncertainty_trace,
            segment_length_sec=segment_length_sec,
            per_video_segments=per_video_segments,
            early_hook_half_life_sec=early_hook_half_life_sec,
        )
        top_impact_score = segments[0].impact_score if segments else 0.0

        queue_items.append(
            TestingQueueItem(
                study_id=video.study_id,
                video_id=video.id,
                title=video.title,
                source_url=video.source_url,
                duration_ms=video.duration_ms,
                existing_sessions=existing_sessions,
                pending_sessions=max(target_sessions_per_video - existing_sessions, 0),
                mean_uncertainty=mean([point.uncertainty for point in uncertainty_trace]),
                top_impact_score=top_impact_score,
                uncertainty_trace=uncertainty_trace,
                recommended_segments=segments,
            )
        )

    queue_items.sort(
        key=lambda item: (
            item.top_impact_score,
            item.mean_uncertainty,
            item.pending_sessions,
        ),
        reverse=True,
    )
    queue_items = queue_items[:queue_size]

    next_assignment: Optional[TestingQueueAssignment] = None
    if queue_items:
        top_item = queue_items[0]
        if top_item.recommended_segments:
            top_segment = top_item.recommended_segments[0]
        else:
            top_segment = TestingQueueSegment(
                start_sec=0,
                end_sec=max(int((top_item.duration_ms or 1000) / 1000), 1),
                mean_uncertainty=top_item.mean_uncertainty,
                hook_weight=1.0,
                impact_score=top_item.mean_uncertainty,
            )
        next_assignment = TestingQueueAssignment(
            study_id=top_item.study_id,
            video_id=top_item.video_id,
            start_sec=top_segment.start_sec,
            end_sec=top_segment.end_sec,
            rationale="Highest uncertainty and expected early-hook impact",
        )

    return TestingQueueResponse(
        generated_at=datetime.now(timezone.utc),
        queue_size=max(queue_size, 1),
        target_sessions_per_video=target_sessions_per_video,
        items=queue_items,
        next_assignment=next_assignment,
    )


def _sampling_curve(
    *,
    true_error: Sequence[float],
    uncertainty_score: Sequence[float],
    strategy: str,
    steps: int,
    batch_size: int,
    seed: int,
) -> List[float]:
    """Return remaining mean error after each sampling step."""

    if len(true_error) != len(uncertainty_score):
        raise ValueError("true_error and uncertainty_score must have equal length")
    if strategy not in {"uncertainty", "random"}:
        raise ValueError("strategy must be 'uncertainty' or 'random'")

    rng = random.Random(seed)
    n = len(true_error)
    if n == 0:
        return [0.0]

    unlabeled = set(range(n))
    curve = [mean(list(true_error))]

    for _ in range(max(steps, 0)):
        if not unlabeled:
            curve.append(0.0)
            continue

        k = min(max(batch_size, 1), len(unlabeled))
        if strategy == "uncertainty":
            picked = sorted(
                unlabeled,
                key=lambda idx: uncertainty_score[idx],
                reverse=True,
            )[:k]
        else:
            picked = rng.sample(list(unlabeled), k=k)

        for idx in picked:
            unlabeled.discard(idx)

        remaining = [true_error[idx] for idx in unlabeled]
        curve.append(mean(remaining))

    return curve


def simulate_uncertainty_sampling_advantage(
    *,
    n_points: int = 500,
    steps: int = 30,
    batch_size: int = 8,
    random_trials: int = 40,
    seed: int = 42,
) -> Dict[str, float]:
    """Simulate and compare uncertainty-driven vs random active sampling."""

    rng = random.Random(seed)
    true_error = [rng.random() ** 0.45 for _ in range(max(n_points, 1))]
    uncertainty = [
        min(max((err * 0.9) + rng.gauss(0.0, 0.06), 0.0), 1.0)
        for err in true_error
    ]

    uncertainty_curve = _sampling_curve(
        true_error=true_error,
        uncertainty_score=uncertainty,
        strategy="uncertainty",
        steps=steps,
        batch_size=batch_size,
        seed=seed,
    )

    random_curves: List[List[float]] = []
    for trial_idx in range(max(random_trials, 1)):
        random_curves.append(
            _sampling_curve(
                true_error=true_error,
                uncertainty_score=uncertainty,
                strategy="random",
                steps=steps,
                batch_size=batch_size,
                seed=seed + trial_idx + 1,
            )
        )

    random_curve_mean = [
        mean([curve[position] for curve in random_curves])
        for position in range(len(uncertainty_curve))
    ]

    uncertainty_auc = float(sum(uncertainty_curve))
    random_auc = float(sum(random_curve_mean))
    return {
        "uncertainty_auc": uncertainty_auc,
        "random_auc": random_auc,
        "improvement_ratio": (random_auc - uncertainty_auc) / random_auc if random_auc > 0 else 0.0,
        "uncertainty_final_error": float(uncertainty_curve[-1]),
        "random_final_error": float(random_curve_mean[-1]),
    }
