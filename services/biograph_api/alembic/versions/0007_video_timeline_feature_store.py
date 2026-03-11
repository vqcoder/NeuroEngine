"""add reusable video timeline analyses and feature tracks"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_video_timeline_feature_store"
down_revision = "0006_scene_graph_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_timeline_analyses",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(length=128), nullable=False),
        sa.Column("analysis_version", sa.String(length=64), nullable=False, server_default="timeline_v1"),
        sa.Column("asset_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "video_id",
            "analysis_version",
            "asset_fingerprint",
            name="uq_video_timeline_analyses_video_version_fingerprint",
        ),
    )
    op.create_index(
        "ix_video_timeline_analyses_asset_id",
        "video_timeline_analyses",
        ["asset_id"],
    )
    op.create_index(
        "ix_video_timeline_analyses_status",
        "video_timeline_analyses",
        ["status"],
    )

    op.create_table(
        "video_timeline_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("video_timeline_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(length=128), nullable=False),
        sa.Column("segment_type", sa.String(length=64), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_video_timeline_segments_asset_window",
        "video_timeline_segments",
        ["asset_id", "start_ms", "end_ms"],
    )
    op.create_index(
        "ix_video_timeline_segments_type",
        "video_timeline_segments",
        ["segment_type"],
    )

    op.create_table(
        "video_feature_tracks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("video_timeline_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(length=128), nullable=False),
        sa.Column("track_name", sa.String(length=128), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_video_feature_tracks_asset_window",
        "video_feature_tracks",
        ["asset_id", "start_ms", "end_ms"],
    )
    op.create_index(
        "ix_video_feature_tracks_track_name",
        "video_feature_tracks",
        ["track_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_feature_tracks_track_name", table_name="video_feature_tracks")
    op.drop_index("ix_video_feature_tracks_asset_window", table_name="video_feature_tracks")
    op.drop_table("video_feature_tracks")

    op.drop_index("ix_video_timeline_segments_type", table_name="video_timeline_segments")
    op.drop_index("ix_video_timeline_segments_asset_window", table_name="video_timeline_segments")
    op.drop_table("video_timeline_segments")

    op.drop_index("ix_video_timeline_analyses_status", table_name="video_timeline_analyses")
    op.drop_index("ix_video_timeline_analyses_asset_id", table_name="video_timeline_analyses")
    op.drop_table("video_timeline_analyses")

