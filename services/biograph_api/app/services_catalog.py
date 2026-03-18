"""Scene graph, catalog, and CTA marker service functions."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain_exceptions import NotFoundError
from .models import (
    Participant,
    Session as SessionModel,
    Study,
    TracePoint,
    Video,
    VideoCtaMarker,
    VideoCut,
    VideoScene,
)
from .schemas import (
    ReadoutCtaMarker,
    ReadoutCut,
    ReadoutScene,
    VideoCatalogItem,
    VideoCatalogResponse,
    VideoCatalogSession,
    VideoCtaMarkerIn,
    VideoCtaMarkerRead,
    VideoCtaMarkersResponse,
    VideoCutIn,
    VideoCutRead,
    VideoSceneGraphResponse,
    VideoSceneIn,
    VideoSceneRead,
)

DEFAULT_VARIANT_ID = "default"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneGraphContext:
    variant_id: str
    scenes: List[ReadoutScene]
    cuts: List[ReadoutCut]
    cta_markers: List[ReadoutCtaMarker]


def list_video_catalog(db: Session, limit: int = 50) -> VideoCatalogResponse:
    """Return newest videos with recording/session catalog metadata for analyst discovery."""

    video_rows = db.execute(
        select(Video, Study.name)
        .join(Study, Video.study_id == Study.id)
        .order_by(Video.created_at.desc())
        .limit(max(limit, 1))
    ).all()

    if not video_rows:
        return VideoCatalogResponse(items=[])

    ordered_video_ids = [video.id for video, _ in video_rows]
    sessions = db.execute(
        select(SessionModel)
        .where(SessionModel.video_id.in_(ordered_video_ids))
        .order_by(SessionModel.video_id.asc(), SessionModel.created_at.desc())
    ).scalars().all()

    sessions_by_video: Dict[UUID, List[SessionModel]] = defaultdict(list)
    for session in sessions:
        sessions_by_video[session.video_id].append(session)

    # Batch-fetch participants for recent sessions
    all_participant_ids = {s.participant_id for s in sessions}
    participants = (
        db.execute(
            select(Participant).where(Participant.id.in_(all_participant_ids))
        ).scalars().all()
        if all_participant_ids
        else []
    )
    participant_map: Dict[UUID, Participant] = {p.id: p for p in participants}

    latest_trace_rows = db.execute(
        select(SessionModel.video_id, func.max(TracePoint.created_at))
        .join(TracePoint, TracePoint.session_id == SessionModel.id)
        .where(SessionModel.video_id.in_(ordered_video_ids))
        .group_by(SessionModel.video_id)
    ).all()
    latest_trace_by_video = {video_id: latest for video_id, latest in latest_trace_rows}

    # Count trace points per video so we can hide recordings with no real data.
    _MIN_TRACE_POINTS_FOR_CATALOG = 10
    trace_count_rows = db.execute(
        select(SessionModel.video_id, func.count(TracePoint.id))
        .join(TracePoint, TracePoint.session_id == SessionModel.id)
        .where(SessionModel.video_id.in_(ordered_video_ids))
        .group_by(SessionModel.video_id)
    ).all()
    trace_counts_by_video: Dict[UUID, int] = {
        video_id: count for video_id, count in trace_count_rows
    }

    items: List[VideoCatalogItem] = []
    for video, study_name in video_rows:
        video_sessions = sessions_by_video.get(video.id, [])
        if not video_sessions:
            # Skip orphaned videos with zero sessions — these are artifacts of
            # failed uploads, duplicate creation, or abandoned recording flows.
            continue
        if trace_counts_by_video.get(video.id, 0) < _MIN_TRACE_POINTS_FOR_CATALOG:
            # Skip videos whose sessions have insufficient trace data — these
            # are abandoned or broken recordings that produce empty timelines.
            continue
        last_session = video_sessions[0] if video_sessions else None
        participant_ids = {session.participant_id for session in video_sessions}
        completed_sessions = sum(1 for session in video_sessions if session.status == "completed")
        abandoned_sessions = sum(
            1 for session in video_sessions
            if session.status in ("abandoned", "incomplete", "aborted")
        )

        items.append(
            VideoCatalogItem(
                video_id=video.id,
                study_id=video.study_id,
                study_name=study_name,
                title=video.title,
                source_url=video.source_url,
                duration_ms=video.duration_ms,
                created_at=video.created_at,
                sessions_count=len(video_sessions),
                completed_sessions_count=completed_sessions,
                abandoned_sessions_count=abandoned_sessions,
                participants_count=len(participant_ids),
                last_session_id=last_session.id if last_session else None,
                last_session_at=last_session.created_at if last_session else None,
                last_session_status=last_session.status if last_session else None,
                latest_trace_at=latest_trace_by_video.get(video.id),
                recent_sessions=[
                    VideoCatalogSession(
                        id=session.id,
                        participant_id=session.participant_id,
                        participant_external_id=(
                            participant_map[session.participant_id].external_id
                            if session.participant_id in participant_map
                            else None
                        ),
                        participant_demographics=(
                            participant_map[session.participant_id].demographics
                            if session.participant_id in participant_map
                            else None
                        ),
                        status=session.status,
                        created_at=session.created_at,
                    )
                    for session in video_sessions[:5]
                ],
            )
        )

    return VideoCatalogResponse(items=items)


def _normalize_variant_id(value: Optional[str]) -> str:
    if value is None:
        return DEFAULT_VARIANT_ID
    cleaned = str(value).strip()
    return cleaned if cleaned else DEFAULT_VARIANT_ID


def _variant_id_from_video(video: Video) -> str:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    variant = metadata.get("variant_id") or metadata.get("variantId")
    return _normalize_variant_id(str(variant) if variant is not None else None)


def _scene_for_time(
    scenes: Sequence[ReadoutScene],
    video_time_ms: int,
) -> Optional[ReadoutScene]:
    if not scenes:
        return None
    for scene in scenes:
        if int(scene.start_ms) <= int(video_time_ms) < int(scene.end_ms):
            return scene
    if int(video_time_ms) < int(scenes[0].start_ms):
        return scenes[0]
    return scenes[-1]


def _ensure_unique_id(candidate: str, existing: set[str], prefix: str, index: int) -> str:
    base = candidate.strip() if candidate.strip() else f"{prefix}-{index}"
    next_value = base
    suffix = 2
    while next_value in existing:
        next_value = f"{base}-{suffix}"
        suffix += 1
    existing.add(next_value)
    return next_value


def _normalize_scene_inputs(
    scenes: Optional[Sequence[VideoSceneIn]],
    scene_boundaries: Optional[Sequence[dict]],
    duration_ms: Optional[int],
) -> List[VideoSceneRead]:
    normalized: List[VideoSceneRead] = []
    source_items: List[dict] = []
    if scenes:
        for scene in scenes:
            source_items.append(scene.model_dump())
    elif scene_boundaries:
        for boundary in scene_boundaries:
            if isinstance(boundary, dict):
                source_items.append(boundary)

    if not source_items:
        fallback_end = int(duration_ms or 0)
        if fallback_end <= 0:
            fallback_end = 1000
        source_items = [
            {
                "scene_id": "scene-1",
                "start_ms": 0,
                "end_ms": fallback_end,
                "label": "Scene 1",
            }
        ]

    source_items.sort(key=lambda item: int(item.get("start_ms", 0)))
    seen_scene_ids: set[str] = set()
    for idx, item in enumerate(source_items, start=1):
        start_ms = max(int(item.get("start_ms", 0)), 0)
        raw_end = int(item.get("end_ms", start_ms))
        end_ms = raw_end if raw_end > start_ms else start_ms + 1
        scene_id = _ensure_unique_id(
            str(item.get("scene_id", "") or ""),
            seen_scene_ids,
            "scene",
            idx,
        )
        normalized.append(
            VideoSceneRead(
                scene_id=scene_id,
                scene_index=idx - 1,
                start_ms=start_ms,
                end_ms=end_ms,
                label=str(item.get("label")) if item.get("label") is not None else None,
                thumbnail_url=(
                    str(
                        item.get("thumbnail_url")
                        or item.get("thumbnailUrl")
                        or item.get("thumbnail")
                    )
                    if (
                        item.get("thumbnail_url")
                        or item.get("thumbnailUrl")
                        or item.get("thumbnail")
                    )
                    is not None
                    else None
                ),
                cut_id=str(item.get("cut_id")) if item.get("cut_id") is not None else None,
                cta_id=str(item.get("cta_id")) if item.get("cta_id") is not None else None,
            )
        )
    return normalized


def _normalize_cut_inputs(
    cuts: Optional[Sequence[VideoCutIn]],
    scenes: Sequence[VideoSceneRead],
) -> List[VideoCutRead]:
    normalized: List[VideoCutRead] = []
    seen_cut_ids: set[str] = set()

    if cuts:
        sorted_cuts = sorted(cuts, key=lambda item: int(item.video_time_ms))
        for idx, cut in enumerate(sorted_cuts, start=1):
            cut_id = _ensure_unique_id(
                cut.cut_id or "",
                seen_cut_ids,
                "cut",
                idx,
            )
            scene = _scene_for_time(
                [ReadoutScene(**scene.model_dump()) for scene in scenes],
                int(cut.video_time_ms),
            )
            normalized.append(
                VideoCutRead(
                    cut_id=cut_id,
                    video_time_ms=int(cut.video_time_ms),
                    scene_id=cut.scene_id or (scene.scene_id if scene is not None else None),
                    label=cut.label,
                )
            )
    else:
        for idx, scene in enumerate(scenes, start=1):
            cut_id = _ensure_unique_id(scene.cut_id or "", seen_cut_ids, "cut", idx)
            normalized.append(
                VideoCutRead(
                    cut_id=cut_id,
                    video_time_ms=int(scene.start_ms),
                    scene_id=scene.scene_id,
                    label=scene.label,
                )
            )

    normalized.sort(key=lambda item: int(item.video_time_ms))
    return normalized


def _normalize_cta_inputs(
    cta_markers: Optional[Sequence[VideoCtaMarkerIn]],
    scene_boundaries: Optional[Sequence[dict]],
    scenes: Sequence[VideoSceneRead],
    cuts: Sequence[VideoCutRead],
    metadata: Optional[Dict[str, object]],
) -> List[VideoCtaMarkerRead]:
    normalized: List[VideoCtaMarkerRead] = []
    seen_cta_ids: set[str] = set()

    def _scene_id_for_time(time_ms: int) -> Optional[str]:
        scene = _scene_for_time(
            [ReadoutScene(**scene_item.model_dump()) for scene_item in scenes],
            int(time_ms),
        )
        return scene.scene_id if scene is not None else None

    def _cut_id_for_time(time_ms: int) -> Optional[str]:
        candidate: Optional[VideoCutRead] = None
        for cut in cuts:
            if int(cut.video_time_ms) <= int(time_ms):
                candidate = cut
            else:
                break
        return candidate.cut_id if candidate is not None else None

    if cta_markers:
        source_items = [item.model_dump() for item in cta_markers]
    else:
        source_items = []
        metadata_markers = metadata.get("cta_markers") if isinstance(metadata, dict) else None
        if isinstance(metadata_markers, list):
            for marker in metadata_markers:
                if isinstance(marker, dict):
                    source_items.append(marker)
        if not source_items and scene_boundaries:
            for boundary in scene_boundaries:
                if not isinstance(boundary, dict) or boundary.get("cta_id") is None:
                    continue
                start_ms = int(boundary.get("cta_ms", boundary.get("start_ms", 0)))
                end_ms = int(boundary.get("end_ms", start_ms + 1))
                source_items.append(
                    {
                        "cta_id": boundary.get("cta_id"),
                        "start_ms": start_ms,
                        "end_ms": max(end_ms, start_ms + 1),
                        "label": boundary.get("label"),
                        "scene_id": boundary.get("scene_id"),
                        "cut_id": boundary.get("cut_id"),
                    }
                )

    source_items.sort(key=lambda item: int(item.get("start_ms", 0)))
    for idx, item in enumerate(source_items, start=1):
        start_ms = max(int(item.get("start_ms", 0)), 0)
        raw_end = int(item.get("end_ms", start_ms + 1))
        end_ms = raw_end if raw_end > start_ms else start_ms + 1
        cta_id = _ensure_unique_id(
            str(item.get("cta_id", "") or ""),
            seen_cta_ids,
            "cta",
            idx,
        )
        scene_id = str(item.get("scene_id")) if item.get("scene_id") is not None else _scene_id_for_time(start_ms)
        cut_id = str(item.get("cut_id")) if item.get("cut_id") is not None else _cut_id_for_time(start_ms)
        normalized.append(
            VideoCtaMarkerRead(
                cta_id=cta_id,
                start_ms=start_ms,
                end_ms=end_ms,
                label=str(item.get("label")) if item.get("label") is not None else None,
                scene_id=scene_id,
                cut_id=cut_id,
                video_time_ms=int((start_ms + end_ms) / 2),
            )
        )

    return normalized


def _build_legacy_scene_boundaries(
    scenes: Sequence[VideoSceneRead],
    cuts: Sequence[VideoCutRead],
    cta_markers: Sequence[VideoCtaMarkerRead],
) -> List[Dict[str, object]]:
    scene_cut_map: Dict[str, str] = {}
    for cut in cuts:
        if cut.scene_id and cut.scene_id not in scene_cut_map:
            scene_cut_map[cut.scene_id] = cut.cut_id

    scene_cta_map: Dict[str, VideoCtaMarkerRead] = {}
    for marker in cta_markers:
        if marker.scene_id and marker.scene_id not in scene_cta_map:
            scene_cta_map[marker.scene_id] = marker

    boundaries: List[Dict[str, object]] = []
    for scene in scenes:
        cta_marker = scene_cta_map.get(scene.scene_id)
        boundaries.append(
            {
                "start_ms": int(scene.start_ms),
                "end_ms": int(scene.end_ms),
                "label": scene.label,
                "scene_id": scene.scene_id,
                "cut_id": scene.cut_id or scene_cut_map.get(scene.scene_id),
                "cta_id": scene.cta_id or (cta_marker.cta_id if cta_marker else None),
                "cta_ms": cta_marker.video_time_ms if cta_marker else None,
                "thumbnail_url": scene.thumbnail_url,
            }
        )
    return boundaries


def _build_scene_graph_context(
    video: Video,
    variant_id: Optional[str] = None,
) -> SceneGraphContext:
    variant_key = _normalize_variant_id(variant_id or _variant_id_from_video(video))

    scene_rows = [
        row for row in (video.scene_graph_scenes or []) if row.variant_id == variant_key
    ]
    cut_rows = [
        row for row in (video.scene_graph_cuts or []) if row.variant_id == variant_key
    ]
    cta_rows = [
        row for row in (video.scene_graph_cta_markers or []) if row.variant_id == variant_key
    ]

    scenes: List[ReadoutScene] = []
    cuts: List[ReadoutCut] = []
    cta_markers: List[ReadoutCtaMarker] = []

    if scene_rows:
        ordered_scenes = sorted(
            scene_rows,
            key=lambda item: (int(item.sort_index), int(item.start_ms), int(item.end_ms)),
        )
        for idx, row in enumerate(ordered_scenes):
            scenes.append(
                ReadoutScene(
                    scene_index=idx,
                    start_ms=int(row.start_ms),
                    end_ms=int(row.end_ms),
                    label=row.label,
                    thumbnail_url=row.thumbnail_url,
                    scene_id=row.scene_id,
                    cut_id=row.cut_id,
                    cta_id=row.cta_id,
                )
            )
    else:
        boundaries = [
            item
            for item in (video.scene_boundaries or [])
            if isinstance(item, dict)
        ]
        normalized_scenes = _normalize_scene_inputs(None, boundaries, video.duration_ms)
        for scene in normalized_scenes:
            scenes.append(
                ReadoutScene(
                    scene_index=scene.scene_index,
                    start_ms=scene.start_ms,
                    end_ms=scene.end_ms,
                    label=scene.label,
                    thumbnail_url=scene.thumbnail_url,
                    scene_id=scene.scene_id,
                    cut_id=scene.cut_id,
                    cta_id=scene.cta_id,
                )
            )
        normalized_cuts = _normalize_cut_inputs(None, normalized_scenes)
        for idx, cut in enumerate(normalized_cuts):
            next_time = (
                normalized_cuts[idx + 1].video_time_ms
                if idx + 1 < len(normalized_cuts)
                else (
                    scenes[-1].end_ms
                    if scenes
                    else int(video.duration_ms or (cut.video_time_ms + 1))
                )
            )
            cuts.append(
                ReadoutCut(
                    cut_id=cut.cut_id,
                    start_ms=cut.video_time_ms,
                    end_ms=max(int(next_time), int(cut.video_time_ms) + 1),
                    scene_id=cut.scene_id,
                    label=cut.label,
                )
            )
        normalized_ctas = _normalize_cta_inputs(
            None,
            boundaries,
            normalized_scenes,
            normalized_cuts,
            video.video_metadata if isinstance(video.video_metadata, dict) else {},
        )
        for marker in normalized_ctas:
            cta_markers.append(
                ReadoutCtaMarker(
                    cta_id=marker.cta_id,
                    video_time_ms=marker.video_time_ms,
                    start_ms=marker.start_ms,
                    end_ms=marker.end_ms,
                    scene_id=marker.scene_id,
                    cut_id=marker.cut_id,
                    label=marker.label,
                )
            )

    if cut_rows:
        ordered_cuts = sorted(
            cut_rows,
            key=lambda item: (int(item.sort_index), int(item.video_time_ms)),
        )
        for idx, cut in enumerate(ordered_cuts):
            next_start = (
                int(ordered_cuts[idx + 1].video_time_ms)
                if idx + 1 < len(ordered_cuts)
                else (
                    _scene_for_time(scenes, int(cut.video_time_ms)).end_ms
                    if _scene_for_time(scenes, int(cut.video_time_ms)) is not None
                    else int(video.duration_ms or (int(cut.video_time_ms) + 1))
                )
            )
            cuts.append(
                ReadoutCut(
                    cut_id=cut.cut_id,
                    start_ms=int(cut.video_time_ms),
                    end_ms=max(next_start, int(cut.video_time_ms) + 1),
                    scene_id=cut.scene_id,
                    label=cut.label,
                )
            )
    if not cuts:
        seen_cuts: set[str] = set()
        for idx, scene in enumerate(scenes, start=1):
            cut_id = scene.cut_id or f"cut-{idx}"
            if cut_id in seen_cuts:
                continue
            seen_cuts.add(cut_id)
            end_ms = (
                scenes[idx].start_ms
                if idx < len(scenes)
                else int(video.duration_ms or scene.end_ms or (scene.start_ms + 1))
            )
            cuts.append(
                ReadoutCut(
                    cut_id=cut_id,
                    start_ms=int(scene.start_ms),
                    end_ms=max(int(end_ms), int(scene.start_ms) + 1),
                    scene_id=scene.scene_id,
                    cta_id=scene.cta_id,
                    label=scene.label,
                )
            )

    if cta_rows:
        ordered_ctas = sorted(cta_rows, key=lambda item: int(item.start_ms))
        for marker in ordered_ctas:
            start_ms = int(marker.start_ms)
            end_ms = int(marker.end_ms)
            cta_markers.append(
                ReadoutCtaMarker(
                    cta_id=marker.cta_id,
                    video_time_ms=int((start_ms + end_ms) / 2),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    scene_id=marker.scene_id,
                    cut_id=marker.cut_id,
                    label=marker.label,
                )
            )
    if not cta_markers:
        seen_ctas: set[str] = set()
        for scene in scenes:
            if not scene.cta_id:
                continue
            if scene.cta_id in seen_ctas:
                continue
            seen_ctas.add(scene.cta_id)
            start_ms = int(scene.start_ms)
            end_ms = int(scene.end_ms)
            cta_markers.append(
                ReadoutCtaMarker(
                    cta_id=scene.cta_id,
                    video_time_ms=int((start_ms + end_ms) / 2),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    scene_id=scene.scene_id,
                    cut_id=scene.cut_id,
                    label=scene.label,
                )
            )

    cuts = sorted(cuts, key=lambda item: (int(item.start_ms), item.cut_id))
    cta_markers = sorted(cta_markers, key=lambda item: (int(item.start_ms or item.video_time_ms), item.cta_id))
    scenes = sorted(scenes, key=lambda item: (int(item.start_ms), int(item.end_ms)))
    for index, scene in enumerate(scenes):
        scene.scene_index = index

    return SceneGraphContext(
        variant_id=variant_key,
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta_markers,
    )


def _resolve_scene_alignment(
    scene_graph: SceneGraphContext,
    video_time_ms: int,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    timestamp = int(video_time_ms)
    scene = _scene_for_time(scene_graph.scenes, timestamp)
    scene_id = scene.scene_id if scene is not None else None

    cut_id: Optional[str] = None
    for cut in scene_graph.cuts:
        if int(cut.start_ms) <= timestamp < int(cut.end_ms):
            cut_id = cut.cut_id
            break
        if int(cut.start_ms) <= timestamp:
            cut_id = cut.cut_id

    cta_id: Optional[str] = None
    for marker in scene_graph.cta_markers:
        marker_start = int(marker.start_ms if marker.start_ms is not None else marker.video_time_ms)
        marker_end = int(marker.end_ms if marker.end_ms is not None else marker_start + 1)
        if marker_start <= timestamp < marker_end:
            cta_id = marker.cta_id
            break

    return scene_id, cut_id, cta_id


def upsert_video_scene_graph(
    db: Session,
    video: Video,
    *,
    variant_id: Optional[str],
    scenes: Optional[Sequence[VideoSceneIn]],
    cuts: Optional[Sequence[VideoCutIn]],
    cta_markers: Optional[Sequence[VideoCtaMarkerIn]],
    scene_boundaries: Optional[Sequence[dict]],
) -> SceneGraphContext:
    variant_key = _normalize_variant_id(variant_id or _variant_id_from_video(video))
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}

    normalized_scenes = _normalize_scene_inputs(scenes, scene_boundaries, video.duration_ms)
    normalized_cuts = _normalize_cut_inputs(cuts, normalized_scenes)
    normalized_ctas = _normalize_cta_inputs(
        cta_markers,
        scene_boundaries,
        normalized_scenes,
        normalized_cuts,
        metadata,
    )

    cut_by_scene: Dict[str, str] = {}
    for cut in normalized_cuts:
        if cut.scene_id and cut.scene_id not in cut_by_scene:
            cut_by_scene[cut.scene_id] = cut.cut_id

    cta_by_scene: Dict[str, str] = {}
    for cta in normalized_ctas:
        if cta.scene_id and cta.scene_id not in cta_by_scene:
            cta_by_scene[cta.scene_id] = cta.cta_id

    for scene in normalized_scenes:
        if scene.cut_id is None:
            scene.cut_id = cut_by_scene.get(scene.scene_id)
        if scene.cta_id is None:
            scene.cta_id = cta_by_scene.get(scene.scene_id)

    existing_scenes = db.scalars(
        select(VideoScene).where(
            VideoScene.video_id == video.id,
            VideoScene.variant_id == variant_key,
        )
    ).all()
    for row in existing_scenes:
        db.delete(row)

    existing_cuts = db.scalars(
        select(VideoCut).where(
            VideoCut.video_id == video.id,
            VideoCut.variant_id == variant_key,
        )
    ).all()
    for row in existing_cuts:
        db.delete(row)

    existing_ctas = db.scalars(
        select(VideoCtaMarker).where(
            VideoCtaMarker.video_id == video.id,
            VideoCtaMarker.variant_id == variant_key,
        )
    ).all()
    for row in existing_ctas:
        db.delete(row)

    # Ensure old rows are removed before re-inserting stable IDs in the same flush
    # cycle (notably for SQLite unique constraints on replacement updates).
    db.flush()

    for scene in normalized_scenes:
        db.add(
            VideoScene(
                video_id=video.id,
                variant_id=variant_key,
                scene_id=scene.scene_id,
                sort_index=scene.scene_index,
                start_ms=scene.start_ms,
                end_ms=scene.end_ms,
                label=scene.label,
                thumbnail_url=scene.thumbnail_url,
                cut_id=scene.cut_id,
                cta_id=scene.cta_id,
            )
        )

    for idx, cut in enumerate(normalized_cuts):
        db.add(
            VideoCut(
                video_id=video.id,
                variant_id=variant_key,
                cut_id=cut.cut_id,
                sort_index=idx,
                video_time_ms=cut.video_time_ms,
                scene_id=cut.scene_id,
                label=cut.label,
            )
        )

    for marker in normalized_ctas:
        db.add(
            VideoCtaMarker(
                video_id=video.id,
                variant_id=variant_key,
                cta_id=marker.cta_id,
                start_ms=marker.start_ms,
                end_ms=marker.end_ms,
                label=marker.label,
                scene_id=marker.scene_id,
                cut_id=marker.cut_id,
            )
        )

    video.scene_boundaries = _build_legacy_scene_boundaries(
        normalized_scenes,
        normalized_cuts,
        normalized_ctas,
    )
    db.flush()
    db.refresh(video)
    return _build_scene_graph_context(video, variant_key)


def get_video_scene_graph(
    db: Session,
    video_id: UUID,
    variant_id: Optional[str] = None,
) -> VideoSceneGraphResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise NotFoundError("Video")

    if variant_id is not None:
        variant_key = _normalize_variant_id(variant_id)
        has_variant_rows = bool(
            db.scalar(
                select(func.count(VideoScene.id)).where(
                    VideoScene.video_id == video.id,
                    VideoScene.variant_id == variant_key,
                )
            )
            or 0
        )
        metadata_variant = _variant_id_from_video(video)
        if not has_variant_rows and metadata_variant != variant_key:
            raise NotFoundError("Video variant")

    scene_graph = _build_scene_graph_context(video, variant_id)
    return VideoSceneGraphResponse(
        video_id=video.id,
        variant_id=scene_graph.variant_id,
        scenes=[
            VideoSceneRead(
                scene_id=scene.scene_id or f"scene-{scene.scene_index + 1}",
                scene_index=scene.scene_index,
                start_ms=scene.start_ms,
                end_ms=scene.end_ms,
                label=scene.label,
                thumbnail_url=scene.thumbnail_url,
                cut_id=scene.cut_id,
                cta_id=scene.cta_id,
            )
            for scene in scene_graph.scenes
        ],
        cuts=[
            VideoCutRead(
                cut_id=cut.cut_id,
                video_time_ms=cut.start_ms,
                scene_id=cut.scene_id,
                label=cut.label,
            )
            for cut in scene_graph.cuts
        ],
        cta_markers=[
            VideoCtaMarkerRead(
                cta_id=marker.cta_id,
                start_ms=marker.start_ms if marker.start_ms is not None else marker.video_time_ms,
                end_ms=(
                    marker.end_ms
                    if marker.end_ms is not None
                    else (marker.start_ms if marker.start_ms is not None else marker.video_time_ms) + 1
                ),
                label=marker.label,
                scene_id=marker.scene_id,
                cut_id=marker.cut_id,
                video_time_ms=marker.video_time_ms,
            )
            for marker in scene_graph.cta_markers
        ],
    )


def replace_video_cta_markers(
    db: Session,
    video_id: UUID,
    *,
    variant_id: Optional[str],
    cta_markers: Sequence[VideoCtaMarkerIn],
) -> VideoCtaMarkersResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise NotFoundError("Video")

    existing_graph = _build_scene_graph_context(video, variant_id)
    updated_graph = upsert_video_scene_graph(
        db,
        video,
        variant_id=existing_graph.variant_id,
        scenes=[
            VideoSceneIn(
                scene_id=scene.scene_id,
                start_ms=scene.start_ms,
                end_ms=scene.end_ms,
                label=scene.label,
                thumbnail_url=scene.thumbnail_url,
                cut_id=scene.cut_id,
                cta_id=scene.cta_id,
            )
            for scene in existing_graph.scenes
        ],
        cuts=[
            VideoCutIn(
                cut_id=cut.cut_id,
                video_time_ms=cut.start_ms,
                scene_id=cut.scene_id,
                label=cut.label,
            )
            for cut in existing_graph.cuts
        ],
        cta_markers=cta_markers,
        scene_boundaries=None,
    )

    return VideoCtaMarkersResponse(
        video_id=video.id,
        variant_id=updated_graph.variant_id,
        cta_markers=[
            VideoCtaMarkerRead(
                cta_id=marker.cta_id,
                start_ms=marker.start_ms if marker.start_ms is not None else marker.video_time_ms,
                end_ms=(
                    marker.end_ms
                    if marker.end_ms is not None
                    else (marker.start_ms if marker.start_ms is not None else marker.video_time_ms) + 1
                ),
                label=marker.label,
                scene_id=marker.scene_id,
                cut_id=marker.cut_id,
                video_time_ms=marker.video_time_ms,
            )
            for marker in updated_graph.cta_markers
        ],
    )
