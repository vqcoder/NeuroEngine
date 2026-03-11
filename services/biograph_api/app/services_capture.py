"""Capture archive service functions for session webcam ingest, observability, and purge."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from .domain_exceptions import PayloadTooLargeError, ServiceUnavailableError, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    Session as SessionModel,
    SessionCaptureArchive,
    SessionCaptureIngestEvent,
)
from .schemas import (
    CaptureArchiveFailureCodeCount,
    CaptureArchiveObservabilityStatusResponse,
    CaptureArchivePurgeResponse,
    SessionCaptureIngestRequest,
    SessionCaptureIngestResponse,
)


def _normalize_capture_encryption_mode(raw_mode: str) -> str:
    mode = raw_mode.strip().lower()
    if mode in {"", "none"}:
        return "none"
    if mode == "fernet":
        return "fernet"
    return mode


def _encrypt_capture_payload(
    compressed_payload: bytes,
    *,
    settings,
) -> tuple[bytes, str, Optional[str]]:
    mode = _normalize_capture_encryption_mode(settings.webcam_capture_archive_encryption_mode)
    if mode == "none":
        return compressed_payload, "none", None

    if mode != "fernet":
        raise ValidationError(f"Unsupported capture encryption mode '{mode}'")

    key = settings.webcam_capture_archive_encryption_key.strip()
    if not key:
        raise ServiceUnavailableError("Capture archive encryption key is required for fernet mode")

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise ServiceUnavailableError("cryptography package is required for capture archive fernet encryption") from exc

    try:
        encrypted_payload = Fernet(key.encode("utf-8")).encrypt(compressed_payload)
    except Exception as exc:  # pragma: no cover - depends on runtime key state
        raise ServiceUnavailableError(f"Capture archive encryption failed: {exc}") from exc

    key_id = settings.webcam_capture_archive_encryption_key_id.strip() or None
    return encrypted_payload, "fernet", key_id


def upsert_session_capture_archive(
    db: Session,
    session_model: SessionModel,
    payload: SessionCaptureIngestRequest,
) -> SessionCaptureIngestResponse:
    """Persist raw capture payload for a session in compressed form."""

    if payload.video_id != session_model.video_id:
        raise ValidationError("Capture video_id does not match target session video")

    settings = get_settings()
    max_frames = max(1, settings.webcam_capture_archive_max_frames)
    frame_count = len(payload.frames)
    frame_pointer_count = len(payload.frame_pointers)

    if frame_count > max_frames:
        raise PayloadTooLargeError(f"Capture frame count {frame_count} exceeds configured limit {max_frames}")

    capture_payload = {
        "session_id": str(session_model.id),
        "video_id": str(payload.video_id),
        "frames": [frame.model_dump(mode="json") for frame in payload.frames],
        "frame_pointers": [frame.model_dump(mode="json") for frame in payload.frame_pointers],
    }
    raw_payload = json.dumps(
        capture_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    max_payload_bytes = max(1024, settings.webcam_capture_archive_max_payload_bytes)
    if len(raw_payload) > max_payload_bytes:
        raise PayloadTooLargeError(
            "Capture payload exceeds configured byte limit "
            f"({len(raw_payload)} > {max_payload_bytes})"
        )

    compressed_payload = gzip.compress(raw_payload)
    stored_payload, encryption_mode, encryption_key_id = _encrypt_capture_payload(
        compressed_payload,
        settings=settings,
    )
    payload_sha256 = hashlib.sha256(raw_payload).hexdigest()

    archive = db.scalar(
        select(SessionCaptureArchive).where(
            SessionCaptureArchive.session_id == session_model.id,
        )
    )
    now = datetime.now(timezone.utc)
    if archive is None:
        archive = SessionCaptureArchive(
            session_id=session_model.id,
            video_id=session_model.video_id,
            created_at=now,
            updated_at=now,
            frame_count=frame_count,
            frame_pointer_count=frame_pointer_count,
            uncompressed_bytes=len(raw_payload),
            compressed_bytes=len(stored_payload),
            payload_sha256=payload_sha256,
            payload_gzip=stored_payload,
            encryption_mode=encryption_mode,
            encryption_key_id=encryption_key_id,
        )
        db.add(archive)
    else:
        archive.video_id = session_model.video_id
        archive.frame_count = frame_count
        archive.frame_pointer_count = frame_pointer_count
        archive.uncompressed_bytes = len(raw_payload)
        archive.compressed_bytes = len(stored_payload)
        archive.payload_sha256 = payload_sha256
        archive.payload_gzip = stored_payload
        archive.encryption_mode = encryption_mode
        archive.encryption_key_id = encryption_key_id
        archive.updated_at = now

    db.flush()
    created_at = archive.created_at or now
    updated_at = archive.updated_at or now
    return SessionCaptureIngestResponse(
        capture_archive_id=archive.id,
        session_id=archive.session_id,
        video_id=archive.video_id,
        frame_count=archive.frame_count,
        frame_pointer_count=archive.frame_pointer_count,
        uncompressed_bytes=archive.uncompressed_bytes,
        compressed_bytes=archive.compressed_bytes,
        payload_sha256=archive.payload_sha256,
        encryption_mode=archive.encryption_mode,
        encryption_key_id=archive.encryption_key_id,
        created_at=created_at,
        updated_at=updated_at,
    )


def derive_capture_ingest_error_code(status_code: int, detail: Optional[str]) -> str:
    detail_text = (detail or "").lower()
    if status_code == 404 and "disabled" in detail_text:
        return "endpoint_disabled"
    if status_code == 404 and "session not found" in detail_text:
        return "session_not_found"
    if status_code == 400 and "video_id does not match" in detail_text:
        return "video_mismatch"
    if status_code == 400 and "unsupported capture encryption mode" in detail_text:
        return "unsupported_encryption_mode"
    if status_code == 413 and "frame count" in detail_text:
        return "frame_limit_exceeded"
    if status_code == 413 and "byte limit" in detail_text:
        return "payload_limit_exceeded"
    if status_code == 503 and "encryption" in detail_text:
        return "encryption_unavailable"
    if status_code == 422:
        return "payload_validation_error"
    if status_code >= 500:
        return "server_error"
    return "capture_ingest_error"


def record_capture_ingest_event(
    db: Session,
    *,
    session_id: Optional[UUID],
    video_id: Optional[UUID],
    outcome: str,
    status_code: Optional[int],
    error_code: Optional[str],
    frame_count: int,
    frame_pointer_count: int,
    payload_bytes: int,
) -> None:
    outcome_value = outcome.strip().lower()
    if outcome_value not in {"success", "failure"}:
        outcome_value = "failure"
    db.add(
        SessionCaptureIngestEvent(
            session_id=session_id,
            video_id=video_id,
            outcome=outcome_value,
            status_code=status_code,
            error_code=error_code,
            frame_count=max(0, frame_count),
            frame_pointer_count=max(0, frame_pointer_count),
            payload_bytes=max(0, payload_bytes),
            created_at=datetime.now(timezone.utc),
        )
    )


def build_capture_archive_observability_status(
    db: Session,
) -> CaptureArchiveObservabilityStatusResponse:
    settings = get_settings()
    enabled = bool(settings.webcam_capture_archive_enabled)
    purge_enabled = bool(settings.webcam_capture_archive_purge_enabled)
    retention_days = max(1, int(settings.webcam_capture_archive_retention_days))
    purge_batch_size = max(1, int(settings.webcam_capture_archive_purge_batch_size))
    recent_window_hours = max(1, int(settings.webcam_capture_archive_observability_window_hours))
    encryption_mode = _normalize_capture_encryption_mode(settings.webcam_capture_archive_encryption_mode)

    (
        total_archives,
        total_frames,
        total_pointers,
        total_uncompressed_bytes,
        total_compressed_bytes,
        oldest_archive_at,
        newest_archive_at,
    ) = db.execute(
        select(
            func.count(SessionCaptureArchive.id),
            func.coalesce(func.sum(SessionCaptureArchive.frame_count), 0),
            func.coalesce(func.sum(SessionCaptureArchive.frame_pointer_count), 0),
            func.coalesce(func.sum(SessionCaptureArchive.uncompressed_bytes), 0),
            func.coalesce(func.sum(SessionCaptureArchive.compressed_bytes), 0),
            func.min(SessionCaptureArchive.created_at),
            func.max(SessionCaptureArchive.created_at),
        )
    ).one()

    total_success_count = int(
        db.scalar(
            select(func.count(SessionCaptureIngestEvent.id)).where(
                SessionCaptureIngestEvent.outcome == "success"
            )
        )
        or 0
    )
    total_failure_count = int(
        db.scalar(
            select(func.count(SessionCaptureIngestEvent.id)).where(
                SessionCaptureIngestEvent.outcome == "failure"
            )
        )
        or 0
    )
    ingestion_event_count = total_success_count + total_failure_count
    failure_rate = (
        round(total_failure_count / ingestion_event_count, 6)
        if ingestion_event_count > 0
        else None
    )

    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=recent_window_hours)
    recent_success_count = int(
        db.scalar(
            select(func.count(SessionCaptureIngestEvent.id)).where(
                SessionCaptureIngestEvent.outcome == "success",
                SessionCaptureIngestEvent.created_at >= recent_cutoff,
            )
        )
        or 0
    )
    recent_failure_count = int(
        db.scalar(
            select(func.count(SessionCaptureIngestEvent.id)).where(
                SessionCaptureIngestEvent.outcome == "failure",
                SessionCaptureIngestEvent.created_at >= recent_cutoff,
            )
        )
        or 0
    )
    recent_total = recent_success_count + recent_failure_count
    recent_failure_rate = (
        round(recent_failure_count / recent_total, 6) if recent_total > 0 else None
    )

    failure_rows = db.execute(
        select(
            SessionCaptureIngestEvent.error_code,
            func.count(SessionCaptureIngestEvent.id),
        )
        .where(SessionCaptureIngestEvent.outcome == "failure")
        .group_by(SessionCaptureIngestEvent.error_code)
        .order_by(func.count(SessionCaptureIngestEvent.id).desc())
        .limit(5)
    ).all()
    top_failure_codes = [
        CaptureArchiveFailureCodeCount(error_code=str(code) if code is not None else "unknown_error", count=int(count))
        for code, count in failure_rows
    ]

    warnings: List[str] = []
    if not enabled:
        warnings.append("capture_archive_ingest_disabled")
    if not purge_enabled:
        warnings.append("capture_archive_purge_disabled")
    if encryption_mode not in {"none", "fernet"}:
        warnings.append("unsupported_capture_encryption_mode")
    if ingestion_event_count == 0:
        warnings.append("capture_ingest_history_empty")
    if failure_rate is not None and failure_rate >= 0.2:
        warnings.append("capture_ingest_failure_rate_high")
    if recent_failure_rate is not None and recent_failure_rate >= 0.25:
        warnings.append("capture_ingest_recent_failure_rate_high")

    if not enabled:
        status = "disabled"
    elif ingestion_event_count == 0 and int(total_archives or 0) == 0:
        status = "no_data"
    elif "unsupported_capture_encryption_mode" in warnings:
        status = "alert"
    elif "capture_ingest_failure_rate_high" in warnings or "capture_ingest_recent_failure_rate_high" in warnings:
        status = "alert"
    else:
        status = "ok"

    return CaptureArchiveObservabilityStatusResponse(
        status=status,
        enabled=enabled,
        purge_enabled=purge_enabled,
        retention_days=retention_days,
        purge_batch_size=purge_batch_size,
        encryption_mode=encryption_mode,
        ingestion_event_count=ingestion_event_count,
        success_count=total_success_count,
        failure_count=total_failure_count,
        failure_rate=failure_rate,
        recent_window_hours=recent_window_hours,
        recent_success_count=recent_success_count,
        recent_failure_count=recent_failure_count,
        recent_failure_rate=recent_failure_rate,
        total_archives=int(total_archives or 0),
        total_frames=int(total_frames or 0),
        total_frame_pointers=int(total_pointers or 0),
        total_uncompressed_bytes=int(total_uncompressed_bytes or 0),
        total_compressed_bytes=int(total_compressed_bytes or 0),
        oldest_archive_at=oldest_archive_at,
        newest_archive_at=newest_archive_at,
        top_failure_codes=top_failure_codes,
        warnings=warnings,
    )


def purge_expired_capture_archives(
    db: Session,
    *,
    dry_run: bool = True,
) -> CaptureArchivePurgeResponse:
    settings = get_settings()
    enabled = bool(settings.webcam_capture_archive_purge_enabled)
    retention_days = max(1, int(settings.webcam_capture_archive_retention_days))
    purge_batch_size = max(1, int(settings.webcam_capture_archive_purge_batch_size))
    cutoff_at = datetime.now(timezone.utc) - timedelta(days=retention_days)
    warnings: List[str] = []

    if not enabled:
        warnings.append("capture_archive_purge_disabled")
        return CaptureArchivePurgeResponse(
            enabled=False,
            dry_run=dry_run,
            retention_days=retention_days,
            cutoff_at=cutoff_at,
            candidate_count=0,
            deleted_count=0,
            deleted_uncompressed_bytes=0,
            deleted_compressed_bytes=0,
            warnings=warnings,
        )

    candidates = db.scalars(
        select(SessionCaptureArchive)
        .where(SessionCaptureArchive.updated_at < cutoff_at)
        .order_by(SessionCaptureArchive.updated_at.asc())
        .limit(purge_batch_size)
    ).all()

    candidate_count = len(candidates)
    deleted_count = 0
    deleted_uncompressed_bytes = 0
    deleted_compressed_bytes = 0

    if dry_run:
        warnings.append("dry_run_only_no_rows_deleted")
    else:
        for row in candidates:
            deleted_count += 1
            deleted_uncompressed_bytes += max(int(row.uncompressed_bytes or 0), 0)
            deleted_compressed_bytes += max(int(row.compressed_bytes or 0), 0)
            db.delete(row)

    return CaptureArchivePurgeResponse(
        enabled=True,
        dry_run=dry_run,
        retention_days=retention_days,
        cutoff_at=cutoff_at,
        candidate_count=candidate_count,
        deleted_count=deleted_count,
        deleted_uncompressed_bytes=deleted_uncompressed_bytes,
        deleted_compressed_bytes=deleted_compressed_bytes,
        warnings=warnings,
    )
