"""Prediction routes and helpers — extracted from main.py."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy.orm import Session, sessionmaker

from .active_learning import build_testing_queue
from .config import get_settings
from .db import get_db, engine as _db_engine
from .download_service import (
    _cleanup_temp_file,
    _download_predict_video,
    _persist_predict_upload,
    _validate_predict_video_url,
)
from .models import Study, Video
from .predict_service import predict_from_video_with_backend
from .schemas import (
    PredictJobsObservabilityStatus,
    PredictJobStatus,
    PredictResponse,
    TestingQueueResponse,
)

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

# Async predict job store — keyed by job_id, expires after 2 hours
_PREDICT_JOB_TTL = 7200
_MAX_PREDICT_JOBS = 1000
_predict_job_lock = Lock()
# NOTE(Q17): Module-level mutable state — single-worker only.  Under multiple
# workers each process holds its own job map; migrate to Redis/DB if scaling.
_predict_jobs: dict[str, tuple[float, PredictJobStatus]] = {}  # job_id → (expires_at, status)

# Predict job stats — shared via runtime_stats to avoid route cross-imports
from .runtime_stats import predict_stats_lock as _predict_stats_lock, predict_stats as _predict_stats

# ---------------------------------------------------------------------------
# Catalog / job-store helpers
# ---------------------------------------------------------------------------


def _upsert_predict_catalog_entry(
    db: Session,
    *,
    source_url: Optional[str],
    hosted_url: Optional[str],
    title: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> Optional[str]:
    """Create (or find) a Study+Video record for a predicted video. Returns video UUID string."""
    try:
        # Search by ALL candidate URLs — the original source URL is the stable
        # dedup key since hosted URLs change with each upload.
        candidate_urls = [u for u in (source_url, hosted_url) if u and not u.startswith("upload://")]
        existing = None
        for url in candidate_urls:
            existing = (
                db.query(Video)
                .filter(Video.source_url == url)
                .first()
            )
            if existing is not None:
                break
        # Also search by title derived from source_url — catches records whose
        # source_url was already upgraded to a hosted URL on a previous run.
        if existing is None and source_url and not source_url.startswith("upload://"):
            from urllib.parse import urlparse as _urlp
            _parsed = _urlp(source_url)
            _path_parts = [p for p in _parsed.path.rstrip("/").split("/") if p]
            _readable = [
                p for p in _path_parts
                if len(p) > 3 and not p.replace("-", "").replace("_", "").isdigit()
            ]
            slug = (_readable[-1] if _readable else _path_parts[-1] if _path_parts else "").rsplit(".", 1)[0]
            if slug:
                title_candidate = slug.replace("-", " ").replace("_", " ").title()
                existing = (
                    db.query(Video)
                    .filter(Video.title == title_candidate)
                    .first()
                )
        if existing is not None:
            changed = False
            # Upgrade to hosted URL if we now have one
            if hosted_url and existing.source_url != hosted_url:
                existing.source_url = hosted_url
                changed = True
            # Backfill duration if we now know it and the record lacks it
            if duration_ms and not existing.duration_ms:
                existing.duration_ms = duration_ms
                changed = True
            if changed:
                db.commit()
            return str(existing.id)

        # Derive a title from the URL if not explicitly provided
        resolved_title = title
        if not resolved_title and source_url and not source_url.startswith("upload://"):
            try:
                from urllib.parse import urlparse as _urlparse
                _parsed = _urlparse(source_url)
                _host = _parsed.hostname or ""
                _path_parts = [p for p in _parsed.path.rstrip("/").split("/") if p]
                # Try meaningful path segments (skip single-segment hash-like names)
                # Prefer longer readable slug-like segments; fall back to host + last segment
                _readable_parts = [
                    p for p in _path_parts
                    if len(p) > 3 and not p.replace("-", "").replace("_", "").isdigit()
                    and not (len(p) <= 24 and p.replace("-", "").replace("_", "").isalnum() and p.lower() == p.replace("-", "").replace("_", ""))
                ]
                if _readable_parts:
                    slug = _readable_parts[-1]
                    resolved_title = slug.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
                elif _path_parts:
                    slug = _path_parts[-1].rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
                    host_label = _host.replace("www.", "").split(".")[0].title() if _host else ""
                    resolved_title = f"{host_label} — {slug}".strip(" —") if host_label else slug
                elif _host:
                    resolved_title = _host.replace("www.", "").split(".")[0].title()
            except (ValueError, IndexError, AttributeError):
                logger.debug("URL title resolution failed for %s", source_url, exc_info=True)
        if not resolved_title:
            resolved_title = "Predicted Video"

        study = Study(name=resolved_title)
        db.add(study)
        db.flush()

        video = Video(
            study_id=study.id,
            title=resolved_title,
            source_url=hosted_url or (source_url if source_url and not source_url.startswith("upload://") else None),
            duration_ms=duration_ms,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return str(video.id)
    except Exception as _e:
        db.rollback()
        logger.error("Failed to create catalog entry for predicted video", extra={"error": str(_e), "source_url": source_url})
        return None


def _predict_job_set(job_id: str, status: PredictJobStatus) -> None:
    with _predict_job_lock:
        _predict_jobs[job_id] = (monotonic() + _PREDICT_JOB_TTL, status)
        # Evict expired jobs first
        now = monotonic()
        expired = [k for k, (exp, _) in _predict_jobs.items() if now >= exp]
        for k in expired:
            _predict_jobs.pop(k, None)
        # If still over capacity, evict oldest entries by expiry time
        if len(_predict_jobs) > _MAX_PREDICT_JOBS:
            sorted_keys = sorted(
                _predict_jobs.keys(),
                key=lambda k: _predict_jobs[k][0],
            )
            excess = len(_predict_jobs) - _MAX_PREDICT_JOBS
            for k in sorted_keys[:excess]:
                _predict_jobs.pop(k, None)


def _predict_job_get(job_id: str) -> Optional[PredictJobStatus]:
    with _predict_job_lock:
        entry = _predict_jobs.get(job_id)
        if entry is None:
            return None
        exp, status = entry
        if monotonic() >= exp:
            _predict_jobs.pop(job_id, None)
            return None
        return status


def _validate_predict_output(predictions: list) -> None:
    """Raise ValueError if the predict output contains non-finite or out-of-range values."""
    import math as _math
    if not predictions:
        raise ValueError("Predict output has zero rows — model produced no predictions")
    prev_t: Optional[float] = None
    for i, pt in enumerate(predictions):
        t = float(pt.t_sec)
        if not _math.isfinite(t):
            raise ValueError(f"Non-finite t_sec at row {i}: {t}")
        if prev_t is not None and t < prev_t:
            raise ValueError(f"t_sec not monotonic at row {i}: {t} < {prev_t}")
        prev_t = t
        rp = float(pt.reward_proxy)
        if not _math.isfinite(rp) or not (0.0 <= rp <= 100.0):
            raise ValueError(f"reward_proxy out of range at row {i}: {rp}")
        if pt.blink_rate is not None:
            br = float(pt.blink_rate)
            if not _math.isfinite(br) or br < 0.0:
                raise ValueError(f"blink_rate invalid at row {i}: {br}")
        att = float(pt.attention)
        if not _math.isfinite(att) or not (0.0 <= att <= 100.0):
            raise ValueError(f"attention out of range at row {i}: {att}")
        if not _math.isfinite(float(pt.blink_inhibition)):
            raise ValueError(f"blink_inhibition non-finite at row {i}: {pt.blink_inhibition}")
        if not _math.isfinite(float(pt.dial)):
            raise ValueError(f"dial non-finite at row {i}: {pt.dial}")


# ---------------------------------------------------------------------------
# Background predict job runner
# ---------------------------------------------------------------------------


def _run_predict_job(
    job_id: str,
    temp_path: Path,
    original_video_url: Optional[str],
    resolved_video_url: Optional[str],
    upload_filename: Optional[str],
    is_file_upload: bool,
) -> None:
    """Full predict pipeline — runs as a background task after the HTTP response is returned."""
    from .routes_assets import _github_upload_video

    SessionLocal = sessionmaker(bind=_db_engine)
    db = SessionLocal()
    with _predict_stats_lock:
        _predict_stats["active"] += 1

    def _update(status: str, label: str) -> None:
        current = _predict_job_get(job_id)
        if current:
            _predict_job_set(job_id, PredictJobStatus(
                job_id=job_id, status=status, stage_label=label,
                result=current.result, error=current.error,
            ))

    try:
        if not is_file_upload:
            _update("downloading", "Downloading video…")
            _temp_path, _resolved = _download_predict_video(original_video_url or "")
            temp_path = _temp_path  # capture immediately so finally always cleans it up
            resolved_video_url = _resolved
            if original_video_url:
                _update("uploading", "Storing video to permanent URL…")
                hosted = _github_upload_video(_temp_path, original_video_url)
                if hosted:
                    resolved_video_url = hosted

        _update("running", "Running model inference…")
        try:
            prediction_run = predict_from_video_with_backend(
                video_path=temp_path,
                model_artifact_path=Path(settings.model_artifact_path),
            )
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

        if is_file_upload and temp_path and temp_path.exists():
            _update("uploading", "Storing video to permanent URL…")
            file_hash = __import__("hashlib").sha256(temp_path.read_bytes()[:65536]).hexdigest()[:16]
            synthetic_source_key = f"upload://{upload_filename}/{file_hash}"
            hosted = _github_upload_video(temp_path, synthetic_source_key)
            if hosted:
                resolved_video_url = hosted
                original_video_url = synthetic_source_key

        _validate_predict_output(prediction_run.predictions)

        from .predict_service import _estimate_duration_seconds as _est_dur
        video_duration_ms = _est_dur(temp_path) * 1000 if temp_path and temp_path.exists() else None

        catalog_video_id = _upsert_predict_catalog_entry(
            db,
            source_url=original_video_url,
            hosted_url=resolved_video_url,
            title=upload_filename.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title() if upload_filename else None,
            duration_ms=video_duration_ms,
        )

        result = PredictResponse(
            model_artifact=settings.model_artifact_path,
            predictions=prediction_run.predictions,
            resolved_video_url=resolved_video_url,
            prediction_backend=prediction_run.backend,
            video_id=catalog_video_id,
        )
        _predict_job_set(job_id, PredictJobStatus(
            job_id=job_id, status="done", stage_label="Complete.", result=result,
        ))
        with _predict_stats_lock:
            _predict_stats["active"] = max(0, _predict_stats["active"] - 1)
            _predict_stats["completed"] += 1
    except Exception as exc:
        logger.error("Predict job failed", extra={"job_id": job_id, "error": str(exc)})
        # Surface actionable error messages for known domain/download exceptions;
        # use a generic message only for truly unexpected internal errors.
        from .domain_exceptions import DomainError  # noqa: PLC0415
        from .download_service import _YouTubeRateLimitError, InsufficientDiskSpaceError  # noqa: PLC0415

        if isinstance(exc, (DomainError, _YouTubeRateLimitError, InsufficientDiskSpaceError)):
            error_detail = str(exc)
        else:
            error_detail = "Prediction failed. Check server logs for details."
        _predict_job_set(job_id, PredictJobStatus(
            job_id=job_id, status="failed", stage_label="Failed.", error=error_detail,
        ))
        with _predict_stats_lock:
            _predict_stats["active"] = max(0, _predict_stats["active"] - 1)
            _predict_stats["failed"] += 1
    finally:
        _cleanup_temp_file(temp_path)
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/predict", response_model=PredictJobStatus)
async def predict_traces(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(default=None),
    video_url: Optional[str] = Form(default=None),
) -> PredictJobStatus:
    """Enqueue a prediction job and return immediately. Poll GET /predict/{job_id} for status."""
    if file is None and video_url is None:
        raise HTTPException(status_code=400, detail="Provide either file or video_url")
    if file is not None and video_url is not None:
        raise HTTPException(status_code=400, detail="Provide only one of file or video_url")

    import uuid as _uuid
    job_id = str(_uuid.uuid4())
    is_file_upload = file is not None

    # Validate URL immediately — fail fast before accepting the job
    resolved_video_url: Optional[str] = None
    original_video_url: Optional[str] = video_url
    upload_filename: Optional[str] = None
    temp_path: Optional[Path] = None

    if is_file_upload:
        upload_filename = file.filename or "upload.mp4"  # type: ignore[union-attr]
        temp_path = await _persist_predict_upload(file)  # type: ignore[arg-type]
    else:
        # Validate URL synchronously so bad inputs fail immediately
        _validate_predict_video_url(video_url or "")

    initial_status = PredictJobStatus(
        job_id=job_id,
        status="pending",
        stage_label="Queued — starting soon…",
    )
    _predict_job_set(job_id, initial_status)
    with _predict_stats_lock:
        _predict_stats["queued"] += 1

    background_tasks.add_task(
        _run_predict_job,
        job_id=job_id,
        temp_path=temp_path or Path("/dev/null"),
        original_video_url=original_video_url,
        resolved_video_url=resolved_video_url,
        upload_filename=upload_filename,
        is_file_upload=is_file_upload,
    )

    return initial_status


@router.get("/predict/{job_id}", response_model=PredictJobStatus)
def get_predict_job(job_id: str) -> PredictJobStatus:
    """Poll prediction job status. Status: pending -> downloading -> running -> uploading -> done | failed."""
    status = _predict_job_get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Prediction job not found or expired")
    return status


@router.get("/observability/predict-jobs", response_model=PredictJobsObservabilityStatus)
def get_predict_jobs_observability() -> PredictJobsObservabilityStatus:
    """Return predict job queue stats and GitHub upload health."""
    from .runtime_stats import github_upload_stats_lock as _github_upload_stats_lock, github_upload_stats as _github_upload_stats

    with _predict_stats_lock:
        stats = dict(_predict_stats)
    with _github_upload_stats_lock:
        upload = dict(_github_upload_stats)
    attempts = upload["attempts"]
    successes = upload["successes"]
    success_rate = round(successes / attempts, 4) if attempts > 0 else None
    return PredictJobsObservabilityStatus(
        active_jobs=stats["active"],
        queued_total=stats["queued"],
        completed_total=stats["completed"],
        failed_total=stats["failed"],
        github_upload_attempts=attempts,
        github_upload_successes=successes,
        github_upload_failures=upload["failures"],
        github_upload_success_rate=success_rate,
    )


@router.get("/testing-queue", response_model=TestingQueueResponse)
def get_testing_queue(
    queue_size: int = Query(default=10, ge=1, le=50),
    target_sessions_per_video: int = Query(default=3, ge=1, le=100),
    segment_length_sec: int = Query(default=6, ge=1, le=60),
    per_video_segments: int = Query(default=3, ge=1, le=10),
    early_hook_half_life_sec: float = Query(default=20.0, gt=0.0, le=600.0),
    uncertainty_samples: int = Query(default=16, ge=2, le=64),
    seed: int = Query(default=42, ge=0),
    db: Session = Depends(get_db),
) -> TestingQueueResponse:
    try:
        return build_testing_queue(
            db,
            model_artifact_path=Path(settings.model_artifact_path),
            queue_size=queue_size,
            target_sessions_per_video=target_sessions_per_video,
            segment_length_sec=segment_length_sec,
            per_video_segments=per_video_segments,
            early_hook_half_life_sec=early_hook_half_life_sec,
            uncertainty_samples=uncertainty_samples,
            seed=seed,
        )
    except Exception as exc:
        logger.error("Testing queue build error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Internal server error") from exc
