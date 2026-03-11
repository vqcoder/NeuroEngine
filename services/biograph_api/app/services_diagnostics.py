"""Frontend diagnostic service helpers.

Extracted from services.py -- functions that record, list, and summarise
frontend diagnostic events surfaced by the client application.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import FrontendDiagnosticEvent
from .schemas import (
    FrontendDiagnosticErrorCount,
    FrontendDiagnosticEventIn,
    FrontendDiagnosticEventRead,
    FrontendDiagnosticEventsResponse,
    FrontendDiagnosticSummaryResponse,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_diagnostic_text(value: Optional[str], *, max_length: int) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:max_length]


def _to_frontend_diagnostic_event_read(
    event: FrontendDiagnosticEvent,
) -> FrontendDiagnosticEventRead:
    return FrontendDiagnosticEventRead(
        id=event.id,
        surface=event.surface,
        page=event.page,
        route=event.route,
        severity=event.severity,
        event_type=event.event_type,
        error_code=event.error_code,
        message=event.message,
        context=event.context_json if isinstance(event.context_json, dict) else None,
        session_id=event.session_id,
        video_id=event.video_id,
        study_id=event.study_id,
        created_at=event.created_at,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_frontend_diagnostic_event(
    db: Session,
    payload: FrontendDiagnosticEventIn,
) -> FrontendDiagnosticEventRead:
    event = FrontendDiagnosticEvent(
        surface=payload.surface,
        page=payload.page,
        route=_normalize_diagnostic_text(payload.route, max_length=512),
        severity=payload.severity,
        event_type=_normalize_diagnostic_text(payload.event_type, max_length=64) or "unknown_event",
        error_code=_normalize_diagnostic_text(payload.error_code, max_length=128),
        message=_normalize_diagnostic_text(payload.message, max_length=2048),
        context_json=payload.context if isinstance(payload.context, dict) else None,
        session_id=payload.session_id,
        video_id=payload.video_id,
        study_id=_normalize_diagnostic_text(payload.study_id, max_length=128),
        created_at=payload.created_at or datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()
    db.refresh(event)
    return _to_frontend_diagnostic_event_read(event)


def list_frontend_diagnostic_events(
    db: Session,
    *,
    limit: int = 50,
    surface: Optional[str] = None,
    page: Optional[str] = None,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
) -> FrontendDiagnosticEventsResponse:
    bounded_limit = max(1, min(int(limit), 200))
    query = select(FrontendDiagnosticEvent).order_by(FrontendDiagnosticEvent.created_at.desc())
    if surface:
        query = query.where(FrontendDiagnosticEvent.surface == surface)
    if page:
        query = query.where(FrontendDiagnosticEvent.page == page)
    if severity:
        query = query.where(FrontendDiagnosticEvent.severity == severity)
    if event_type:
        query = query.where(FrontendDiagnosticEvent.event_type == event_type)
    rows = db.execute(query.limit(bounded_limit)).scalars().all()
    return FrontendDiagnosticEventsResponse(
        items=[_to_frontend_diagnostic_event_read(row) for row in rows]
    )


def build_frontend_diagnostic_summary(
    db: Session,
    *,
    window_hours: int = 24,
    top_n: int = 8,
) -> FrontendDiagnosticSummaryResponse:
    bounded_window = max(1, int(window_hours))
    bounded_top_n = max(1, min(int(top_n), 20))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=bounded_window)

    severity_rows = db.execute(
        select(FrontendDiagnosticEvent.severity, func.count(FrontendDiagnosticEvent.id))
        .where(FrontendDiagnosticEvent.created_at >= cutoff)
        .group_by(FrontendDiagnosticEvent.severity)
    ).all()
    severity_counts = {
        str(severity).strip().lower(): int(count or 0) for severity, count in severity_rows
    }

    error_count = severity_counts.get("error", 0)
    warning_count = severity_counts.get("warning", 0)
    info_count = severity_counts.get("info", 0)
    total_events = error_count + warning_count + info_count

    if total_events == 0:
        total_events = int(
            db.scalar(
                select(func.count(FrontendDiagnosticEvent.id)).where(
                    FrontendDiagnosticEvent.created_at >= cutoff
                )
            )
            or 0
        )

    page_rows = db.execute(
        select(FrontendDiagnosticEvent.page, func.count(FrontendDiagnosticEvent.id))
        .where(FrontendDiagnosticEvent.created_at >= cutoff)
        .group_by(FrontendDiagnosticEvent.page)
        .order_by(func.count(FrontendDiagnosticEvent.id).desc(), FrontendDiagnosticEvent.page.asc())
        .limit(16)
    ).all()
    active_pages = [page for page, _count in page_rows if isinstance(page, str) and page]

    normalized_error_code = func.coalesce(
        FrontendDiagnosticEvent.error_code,
        "unknown_error",
    ).label("normalized_error_code")
    top_error_rows = db.execute(
        select(
            FrontendDiagnosticEvent.event_type,
            normalized_error_code,
            func.count(FrontendDiagnosticEvent.id),
        )
        .where(
            FrontendDiagnosticEvent.created_at >= cutoff,
            FrontendDiagnosticEvent.severity == "error",
        )
        .group_by(
            FrontendDiagnosticEvent.event_type,
            FrontendDiagnosticEvent.error_code,
        )
        .order_by(
            func.count(FrontendDiagnosticEvent.id).desc(),
            FrontendDiagnosticEvent.event_type.asc(),
        )
        .limit(bounded_top_n)
    ).all()

    last_event_at = db.scalar(
        select(func.max(FrontendDiagnosticEvent.created_at)).where(
            FrontendDiagnosticEvent.created_at >= cutoff
        )
    )

    warnings: List[str] = []
    if total_events == 0:
        warnings.append("no_frontend_diagnostics_in_window")
    elif error_count > 0:
        error_share = error_count / float(total_events)
        if error_share >= 0.5:
            warnings.append("frontend_error_share_high")

    status = "ok"
    if total_events == 0:
        status = "no_data"
    elif error_count > 0:
        status = "alert"

    return FrontendDiagnosticSummaryResponse(
        status=status,
        window_hours=bounded_window,
        total_events=total_events,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        active_pages=active_pages,
        last_event_at=last_event_at,
        top_errors=[
            FrontendDiagnosticErrorCount(
                event_type=str(event_type),
                error_code=str(error_code),
                count=int(count or 0),
            )
            for event_type, error_code, count in top_error_rows
        ],
        warnings=warnings,
    )
