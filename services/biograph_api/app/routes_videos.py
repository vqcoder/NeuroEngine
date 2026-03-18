"""Video and study routes."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Session as SessionModel, Study, TracePoint, Video
from .readout_cache import invalidate_readout_cache
from .schemas import (
    StudyCreate,
    StudyRead,
    VideoCatalogResponse,
    VideoCreate,
    VideoCtaMarkersResponse,
    VideoCtaMarkersUpdateRequest,
    VideoRead,
    VideoSceneGraphResponse,
    VideoSummaryResponse,
    VideoUpdate,
)
from .services_catalog import (
    get_video_scene_graph,
    list_video_catalog,
    replace_video_cta_markers,
    upsert_video_scene_graph,
)
from .services_summary import build_video_summary
from .synchrony import compute_au04_synchrony, compute_narrative_tension_summary

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/studies", response_model=StudyRead, status_code=201)
def create_study(payload: StudyCreate, db: Session = Depends(get_db)) -> Study:
    logger.info("create_study name=%s", payload.name)
    study = Study(name=payload.name, description=payload.description)
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


@router.post("/videos", response_model=VideoRead, status_code=201)
def create_video(payload: VideoCreate, db: Session = Depends(get_db)) -> VideoRead:
    logger.info("create_video study_id=%s", payload.study_id)
    study = db.get(Study, payload.study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Study not found")

    video_metadata = dict(payload.metadata) if isinstance(payload.metadata, dict) else payload.metadata
    if isinstance(video_metadata, dict) and payload.variant_id and (
        video_metadata.get("variant_id") is None and video_metadata.get("variantId") is None
    ):
        video_metadata["variant_id"] = payload.variant_id

    video = Video(
        study_id=payload.study_id,
        title=payload.title,
        source_url=payload.source_url,
        duration_ms=payload.duration_ms,
        video_metadata=video_metadata,
        scene_boundaries=[scene.model_dump() for scene in (payload.scene_boundaries or [])],
    )
    db.add(video)
    db.flush()

    scene_graph = upsert_video_scene_graph(
        db,
        video,
        variant_id=payload.variant_id,
        scenes=payload.scenes,
        cuts=payload.cuts,
        cta_markers=payload.cta_markers,
        scene_boundaries=[scene.model_dump() for scene in (payload.scene_boundaries or [])],
    )
    db.commit()
    db.refresh(video)
    invalidate_readout_cache(video.id)

    return VideoRead(
        id=video.id,
        study_id=video.study_id,
        title=video.title,
        source_url=video.source_url,
        duration_ms=video.duration_ms,
        variant_id=scene_graph.variant_id,
        metadata=video.video_metadata,
        scene_boundaries=video.scene_boundaries,
        scenes=[
            {
                "scene_id": scene.scene_id or f"scene-{scene.scene_index + 1}",
                "scene_index": scene.scene_index,
                "start_ms": scene.start_ms,
                "end_ms": scene.end_ms,
                "label": scene.label,
                "thumbnail_url": scene.thumbnail_url,
                "cut_id": scene.cut_id,
                "cta_id": scene.cta_id,
            }
            for scene in scene_graph.scenes
        ],
        cuts=[
            {
                "cut_id": cut.cut_id,
                "video_time_ms": cut.start_ms,
                "scene_id": cut.scene_id,
                "label": cut.label,
            }
            for cut in scene_graph.cuts
        ],
        cta_markers=[
            {
                "cta_id": marker.cta_id,
                "start_ms": marker.start_ms if marker.start_ms is not None else marker.video_time_ms,
                "end_ms": (
                    marker.end_ms
                    if marker.end_ms is not None
                    else (marker.start_ms if marker.start_ms is not None else marker.video_time_ms) + 1
                ),
                "label": marker.label,
                "scene_id": marker.scene_id,
                "cut_id": marker.cut_id,
                "video_time_ms": marker.video_time_ms,
            }
            for marker in scene_graph.cta_markers
        ],
        created_at=video.created_at,
    )


@router.patch("/videos/{video_id}", response_model=VideoRead)
def update_video(
    video_id: UUID,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
) -> VideoRead:
    logger.info("update_video video_id=%s", video_id)
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if payload.title is not None:
        video.title = payload.title
    if payload.source_url is not None:
        video.source_url = payload.source_url
    if payload.duration_ms is not None:
        video.duration_ms = payload.duration_ms
        invalidate_readout_cache(video_id=video_id)
    db.commit()
    db.refresh(video)
    return VideoRead.model_validate(video)


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: UUID, db: Session = Depends(get_db)) -> None:
    logger.info("delete_video video_id=%s", video_id)
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    db.delete(video)
    db.commit()


@router.get("/videos", response_model=VideoCatalogResponse)
def get_video_catalog(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> VideoCatalogResponse:
    return list_video_catalog(db, limit=limit)


@router.get("/videos/{video_id}/scene-graph", response_model=VideoSceneGraphResponse)
def get_scene_graph(
    video_id: UUID,
    variant_id: Optional[str] = Query(default=None, alias="variantId"),
    db: Session = Depends(get_db),
) -> VideoSceneGraphResponse:
    return get_video_scene_graph(db, video_id, variant_id=variant_id)


@router.get("/videos/{video_id}/cta-markers", response_model=VideoCtaMarkersResponse)
def get_cta_markers(
    video_id: UUID,
    variant_id: Optional[str] = Query(default=None, alias="variantId"),
    db: Session = Depends(get_db),
) -> VideoCtaMarkersResponse:
    scene_graph = get_video_scene_graph(db, video_id, variant_id=variant_id)
    return VideoCtaMarkersResponse(
        video_id=scene_graph.video_id,
        variant_id=scene_graph.variant_id,
        cta_markers=scene_graph.cta_markers,
    )


@router.put("/videos/{video_id}/cta-markers", response_model=VideoCtaMarkersResponse)
def update_cta_markers(
    video_id: UUID,
    payload: VideoCtaMarkersUpdateRequest,
    variant_id: Optional[str] = Query(default=None, alias="variantId"),
    db: Session = Depends(get_db),
) -> VideoCtaMarkersResponse:
    logger.info("update_cta_markers video_id=%s", video_id)
    response = replace_video_cta_markers(
        db,
        video_id,
        variant_id=variant_id,
        cta_markers=payload.cta_markers,
    )
    db.commit()
    invalidate_readout_cache(video_id)
    return response


@router.get("/videos/{video_id}/summary", response_model=VideoSummaryResponse)
def get_video_summary(video_id: UUID, db: Session = Depends(get_db)) -> VideoSummaryResponse:
    return build_video_summary(db, video_id)


@router.get("/videos/{video_id}/synchrony")
def get_video_synchrony(
    video_id: UUID,
    window_ms: int = Query(default=1000, ge=100, le=10_000),
    min_sessions: int = Query(default=2, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.synchrony_analysis_enabled:
        return {"available": False, "reason": "synchrony_analysis_disabled"}

    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.video_id == video_id, SessionModel.status == "completed")
        .all()
    )
    session_count = len(sessions)

    if session_count < min_sessions:
        return {
            "available": False,
            "reason": "insufficient_sessions",
            "session_count": session_count,
        }

    session_traces = []
    for sess in sessions:
        traces = (
            db.query(TracePoint.video_time_ms, TracePoint.au)
            .filter(TracePoint.session_id == sess.id)
            .order_by(TracePoint.video_time_ms)
            .all()
        )
        session_traces.append([
            {"video_time_ms": tp.video_time_ms, "au": tp.au}
            for tp in traces
        ])

    windows = compute_au04_synchrony(session_traces, window_ms=window_ms)
    summary = compute_narrative_tension_summary(windows)

    return {
        "available": True,
        "session_count": session_count,
        "window_ms": window_ms,
        "windows": windows,
        "summary": summary,
    }
