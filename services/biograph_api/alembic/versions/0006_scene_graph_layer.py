"""add scene graph tables for scenes/cuts/cta markers"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa

revision = "0006_scene_graph_layer"
down_revision = "0005_trace_points_tracking_confidence_flags"
branch_labels = None
depends_on = None


def _variant_from_metadata(metadata: object) -> str:
    if isinstance(metadata, dict):
        variant = metadata.get("variant_id") or metadata.get("variantId")
        if variant is not None and str(variant).strip():
            return str(variant).strip()
    return "default"


def upgrade() -> None:
    op.create_table(
        "video_scenes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("scene_id", sa.String(length=128), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1024), nullable=True),
        sa.Column("cut_id", sa.String(length=128), nullable=True),
        sa.Column("cta_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "video_id",
            "variant_id",
            "scene_id",
            name="uq_video_scenes_video_variant_scene_id",
        ),
    )
    op.create_table(
        "video_cuts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("cut_id", sa.String(length=128), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("video_time_ms", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.String(length=128), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "video_id",
            "variant_id",
            "cut_id",
            name="uq_video_cuts_video_variant_cut_id",
        ),
    )
    op.create_table(
        "video_cta_markers",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("cta_id", sa.String(length=128), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("scene_id", sa.String(length=128), nullable=True),
        sa.Column("cut_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "video_id",
            "variant_id",
            "cta_id",
            name="uq_video_cta_markers_video_variant_cta_id",
        ),
    )

    connection = op.get_bind()
    videos = sa.table(
        "videos",
        sa.column("id", sa.Uuid()),
        sa.column("metadata", sa.JSON()),
        sa.column("scene_boundaries", sa.JSON()),
        sa.column("duration_ms", sa.Integer()),
    )
    scenes = sa.table(
        "video_scenes",
        sa.column("id", sa.Uuid()),
        sa.column("video_id", sa.Uuid()),
        sa.column("variant_id", sa.String()),
        sa.column("scene_id", sa.String()),
        sa.column("sort_index", sa.Integer()),
        sa.column("start_ms", sa.Integer()),
        sa.column("end_ms", sa.Integer()),
        sa.column("label", sa.String()),
        sa.column("thumbnail_url", sa.String()),
        sa.column("cut_id", sa.String()),
        sa.column("cta_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    cuts = sa.table(
        "video_cuts",
        sa.column("id", sa.Uuid()),
        sa.column("video_id", sa.Uuid()),
        sa.column("variant_id", sa.String()),
        sa.column("cut_id", sa.String()),
        sa.column("sort_index", sa.Integer()),
        sa.column("video_time_ms", sa.Integer()),
        sa.column("scene_id", sa.String()),
        sa.column("label", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    ctas = sa.table(
        "video_cta_markers",
        sa.column("id", sa.Uuid()),
        sa.column("video_id", sa.Uuid()),
        sa.column("variant_id", sa.String()),
        sa.column("cta_id", sa.String()),
        sa.column("start_ms", sa.Integer()),
        sa.column("end_ms", sa.Integer()),
        sa.column("label", sa.String()),
        sa.column("scene_id", sa.String()),
        sa.column("cut_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    rows = connection.execute(
        sa.select(
            videos.c.id,
            videos.c.metadata,
            videos.c.scene_boundaries,
            videos.c.duration_ms,
        )
    ).mappings()
    for row in rows:
        variant_id = _variant_from_metadata(row["metadata"])
        boundaries = row["scene_boundaries"] if isinstance(row["scene_boundaries"], list) else []
        if not boundaries:
            fallback_end = int(row["duration_ms"] or 0)
            if fallback_end <= 0:
                fallback_end = 1000
            boundaries = [
                {
                    "scene_id": "scene-1",
                    "start_ms": 0,
                    "end_ms": fallback_end,
                    "label": "Scene 1",
                }
            ]
        boundaries = sorted(boundaries, key=lambda item: int(item.get("start_ms", 0)))

        for index, boundary in enumerate(boundaries, start=1):
            start_ms = max(int(boundary.get("start_ms", 0)), 0)
            raw_end = int(boundary.get("end_ms", start_ms + 1))
            end_ms = raw_end if raw_end > start_ms else start_ms + 1
            scene_id = str(boundary.get("scene_id") or f"scene-{index}")
            cut_id = str(boundary.get("cut_id") or f"cut-{index}")
            cta_id = str(boundary.get("cta_id")) if boundary.get("cta_id") is not None else None
            label = str(boundary.get("label")) if boundary.get("label") is not None else None
            thumbnail_url = (
                str(boundary.get("thumbnail_url"))
                if boundary.get("thumbnail_url") is not None
                else (
                    str(boundary.get("thumbnailUrl"))
                    if boundary.get("thumbnailUrl") is not None
                    else None
                )
            )
            connection.execute(
                sa.insert(scenes).values(
                    id=uuid.uuid4(),
                    video_id=row["id"],
                    variant_id=variant_id,
                    scene_id=scene_id,
                    sort_index=index - 1,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    label=label,
                    thumbnail_url=thumbnail_url,
                    cut_id=cut_id,
                    cta_id=cta_id,
                )
            )
            connection.execute(
                sa.insert(cuts).values(
                    id=uuid.uuid4(),
                    video_id=row["id"],
                    variant_id=variant_id,
                    cut_id=cut_id,
                    sort_index=index - 1,
                    video_time_ms=start_ms,
                    scene_id=scene_id,
                    label=label,
                )
            )
            if cta_id:
                cta_start = int(boundary.get("cta_ms", start_ms))
                cta_end = max(end_ms, cta_start + 1)
                connection.execute(
                    sa.insert(ctas).values(
                        id=uuid.uuid4(),
                        video_id=row["id"],
                        variant_id=variant_id,
                        cta_id=cta_id,
                        start_ms=cta_start,
                        end_ms=cta_end,
                        label=label,
                        scene_id=scene_id,
                        cut_id=cut_id,
                    )
                )


def downgrade() -> None:
    op.drop_table("video_cta_markers")
    op.drop_table("video_cuts")
    op.drop_table("video_scenes")
