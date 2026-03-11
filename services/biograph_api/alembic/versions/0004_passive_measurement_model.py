"""extend schema for passive measurement model"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_passive_measurement_model"
down_revision = "0003_add_session_annotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trace_points", sa.Column("video_time_ms", sa.Integer(), nullable=True))
    op.add_column("trace_points", sa.Column("scene_id", sa.String(length=128), nullable=True))
    op.add_column("trace_points", sa.Column("cut_id", sa.String(length=128), nullable=True))
    op.add_column("trace_points", sa.Column("cta_id", sa.String(length=128), nullable=True))
    op.add_column("trace_points", sa.Column("face_presence_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("blur", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("landmarks_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("eye_openness", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("blink_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("rolling_blink_rate", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("blink_inhibition_score", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("blink_inhibition_active", sa.Boolean(), nullable=True))
    op.add_column("trace_points", sa.Column("blink_baseline_rate", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("reward_proxy", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("au_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("head_pose_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("head_pose_valid_pct", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("gaze_on_screen_proxy", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("gaze_on_screen_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("fps", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("fps_stability", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("face_visible_pct", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("occlusion_score", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("quality_confidence", sa.Float(), nullable=True))

    op.create_index("ix_trace_points_video_time_ms", "trace_points", ["video_time_ms"], unique=False)
    op.create_index("ix_trace_points_scene_id", "trace_points", ["scene_id"], unique=False)
    op.create_index("ix_trace_points_cut_id", "trace_points", ["cut_id"], unique=False)
    op.create_index("ix_trace_points_cta_id", "trace_points", ["cta_id"], unique=False)

    op.add_column("session_annotations", sa.Column("scene_id", sa.String(length=128), nullable=True))
    op.add_column("session_annotations", sa.Column("cut_id", sa.String(length=128), nullable=True))
    op.add_column("session_annotations", sa.Column("cta_id", sa.String(length=128), nullable=True))
    op.create_index(
        "ix_session_annotations_scene_id",
        "session_annotations",
        ["scene_id"],
        unique=False,
    )
    op.create_index("ix_session_annotations_cut_id", "session_annotations", ["cut_id"], unique=False)
    op.create_index("ix_session_annotations_cta_id", "session_annotations", ["cta_id"], unique=False)

    op.create_table(
        "session_playback_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("video_time_ms", sa.Integer(), nullable=False),
        sa.Column("wall_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("client_monotonic_ms", sa.BigInteger(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("scene_id", sa.String(length=128), nullable=True),
        sa.Column("cut_id", sa.String(length=128), nullable=True),
        sa.Column("cta_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_playback_events_session_id",
        "session_playback_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_playback_events_video_id",
        "session_playback_events",
        ["video_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_playback_events_video_time_ms",
        "session_playback_events",
        ["video_time_ms"],
        unique=False,
    )
    op.create_index(
        "ix_session_playback_events_event_type",
        "session_playback_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_session_playback_events_scene_id",
        "session_playback_events",
        ["scene_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_playback_events_cut_id",
        "session_playback_events",
        ["cut_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_playback_events_cta_id",
        "session_playback_events",
        ["cta_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_session_playback_events_cta_id", table_name="session_playback_events")
    op.drop_index("ix_session_playback_events_cut_id", table_name="session_playback_events")
    op.drop_index("ix_session_playback_events_scene_id", table_name="session_playback_events")
    op.drop_index("ix_session_playback_events_event_type", table_name="session_playback_events")
    op.drop_index("ix_session_playback_events_video_time_ms", table_name="session_playback_events")
    op.drop_index("ix_session_playback_events_video_id", table_name="session_playback_events")
    op.drop_index("ix_session_playback_events_session_id", table_name="session_playback_events")
    op.drop_table("session_playback_events")

    op.drop_index("ix_session_annotations_cta_id", table_name="session_annotations")
    op.drop_index("ix_session_annotations_cut_id", table_name="session_annotations")
    op.drop_index("ix_session_annotations_scene_id", table_name="session_annotations")
    op.drop_column("session_annotations", "cta_id")
    op.drop_column("session_annotations", "cut_id")
    op.drop_column("session_annotations", "scene_id")

    op.drop_index("ix_trace_points_cta_id", table_name="trace_points")
    op.drop_index("ix_trace_points_cut_id", table_name="trace_points")
    op.drop_index("ix_trace_points_scene_id", table_name="trace_points")
    op.drop_index("ix_trace_points_video_time_ms", table_name="trace_points")

    op.drop_column("trace_points", "quality_confidence")
    op.drop_column("trace_points", "quality_score")
    op.drop_column("trace_points", "occlusion_score")
    op.drop_column("trace_points", "face_visible_pct")
    op.drop_column("trace_points", "fps_stability")
    op.drop_column("trace_points", "fps")
    op.drop_column("trace_points", "gaze_on_screen_confidence")
    op.drop_column("trace_points", "gaze_on_screen_proxy")
    op.drop_column("trace_points", "head_pose_valid_pct")
    op.drop_column("trace_points", "head_pose_confidence")
    op.drop_column("trace_points", "au_confidence")
    op.drop_column("trace_points", "reward_proxy")
    op.drop_column("trace_points", "blink_baseline_rate")
    op.drop_column("trace_points", "blink_inhibition_active")
    op.drop_column("trace_points", "blink_inhibition_score")
    op.drop_column("trace_points", "rolling_blink_rate")
    op.drop_column("trace_points", "blink_confidence")
    op.drop_column("trace_points", "eye_openness")
    op.drop_column("trace_points", "landmarks_confidence")
    op.drop_column("trace_points", "blur")
    op.drop_column("trace_points", "face_presence_confidence")
    op.drop_column("trace_points", "cta_id")
    op.drop_column("trace_points", "cut_id")
    op.drop_column("trace_points", "scene_id")
    op.drop_column("trace_points", "video_time_ms")
