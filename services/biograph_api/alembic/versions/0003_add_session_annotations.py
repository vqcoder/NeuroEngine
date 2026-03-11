"""add session annotations table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_session_annotations"
down_revision = "0002_trace_points_add_dial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_annotations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("marker_type", sa.String(length=64), nullable=False),
        sa.Column("video_time_ms", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_annotations_session_id",
        "session_annotations",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_annotations_video_id",
        "session_annotations",
        ["video_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_annotations_video_time_ms",
        "session_annotations",
        ["video_time_ms"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_session_annotations_video_time_ms", table_name="session_annotations")
    op.drop_index("ix_session_annotations_video_id", table_name="session_annotations")
    op.drop_index("ix_session_annotations_session_id", table_name="session_annotations")
    op.drop_table("session_annotations")
