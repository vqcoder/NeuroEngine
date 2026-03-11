"""Observability, diagnostics, and frontend error reporting schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Neuro Observability
# ---------------------------------------------------------------------------


class NeuroObservabilityLatestSnapshot(BaseModel):
    recorded_at: Optional[str] = None
    video_id: Optional[str] = None
    variant_id: Optional[str] = None
    model_signature: Optional[str] = None
    drift_status: Optional[str] = None
    missing_signal_rate: Optional[float] = Field(default=None, ge=0, le=1)
    fallback_rate: Optional[float] = Field(default=None, ge=0, le=1)
    confidence_mean: Optional[float] = Field(default=None, ge=0, le=1)
    metrics_exceeding_threshold: List[str] = Field(default_factory=list)


class NeuroObservabilityStatusResponse(BaseModel):
    status: str = Field(min_length=1, max_length=64)
    enabled: bool
    history_enabled: bool
    history_entry_count: int = Field(ge=0)
    history_max_entries: int = Field(ge=1)
    drift_alert_threshold: float = Field(ge=0)
    recent_window: int = Field(ge=1)
    recent_snapshot_count: int = Field(ge=0)
    recent_drift_alert_count: int = Field(ge=0)
    recent_drift_alert_rate: Optional[float] = Field(default=None, ge=0, le=1)
    mean_missing_signal_rate: Optional[float] = Field(default=None, ge=0, le=1)
    mean_fallback_rate: Optional[float] = Field(default=None, ge=0, le=1)
    mean_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    latest_snapshot: Optional[NeuroObservabilityLatestSnapshot] = None
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Capture Archive Observability
# ---------------------------------------------------------------------------


class CaptureArchiveFailureCodeCount(BaseModel):
    error_code: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=0)


class CaptureArchiveObservabilityStatusResponse(BaseModel):
    status: str = Field(min_length=1, max_length=64)
    enabled: bool
    purge_enabled: bool
    retention_days: int = Field(ge=1)
    purge_batch_size: int = Field(ge=1)
    encryption_mode: str = Field(min_length=1, max_length=32)
    ingestion_event_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    failure_rate: Optional[float] = Field(default=None, ge=0, le=1)
    recent_window_hours: int = Field(ge=1)
    recent_success_count: int = Field(ge=0)
    recent_failure_count: int = Field(ge=0)
    recent_failure_rate: Optional[float] = Field(default=None, ge=0, le=1)
    total_archives: int = Field(ge=0)
    total_frames: int = Field(ge=0)
    total_frame_pointers: int = Field(ge=0)
    total_uncompressed_bytes: int = Field(ge=0)
    total_compressed_bytes: int = Field(ge=0)
    oldest_archive_at: Optional[datetime] = None
    newest_archive_at: Optional[datetime] = None
    top_failure_codes: List[CaptureArchiveFailureCodeCount] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class CaptureArchivePurgeResponse(BaseModel):
    enabled: bool
    dry_run: bool
    retention_days: int = Field(ge=1)
    cutoff_at: datetime
    candidate_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    deleted_uncompressed_bytes: int = Field(ge=0)
    deleted_compressed_bytes: int = Field(ge=0)
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontend Diagnostics
# ---------------------------------------------------------------------------


class FrontendDiagnosticEventIn(BaseModel):
    surface: Literal["watchlab", "dashboard", "unknown"] = "unknown"
    page: Literal["study", "readout", "predictor", "observability", "upload", "unknown"] = "unknown"
    route: Optional[str] = Field(default=None, max_length=512)
    severity: Literal["info", "warning", "error"] = "error"
    event_type: str = Field(min_length=1, max_length=64)
    error_code: Optional[str] = Field(default=None, max_length=128)
    message: Optional[str] = Field(default=None, max_length=2048)
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[UUID] = None
    video_id: Optional[UUID] = None
    study_id: Optional[str] = Field(default=None, max_length=128)
    created_at: Optional[datetime] = None


class FrontendDiagnosticEventRead(BaseModel):
    id: UUID
    surface: str
    page: str
    route: Optional[str]
    severity: str
    event_type: str
    error_code: Optional[str]
    message: Optional[str]
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[UUID]
    video_id: Optional[UUID]
    study_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class FrontendDiagnosticEventsResponse(BaseModel):
    items: List[FrontendDiagnosticEventRead] = Field(default_factory=list)


class FrontendDiagnosticErrorCount(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    error_code: str = Field(min_length=1, max_length=128)
    count: int = Field(ge=0)


class FrontendDiagnosticSummaryResponse(BaseModel):
    status: str = Field(min_length=1, max_length=64)
    window_hours: int = Field(ge=1)
    total_events: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    active_pages: List[str] = Field(default_factory=list)
    last_event_at: Optional[datetime] = None
    top_errors: List[FrontendDiagnosticErrorCount] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
