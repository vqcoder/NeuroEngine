"""add video_synchrony_cache table for pre-computed synchrony results"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_video_synchrony_cache"
down_revision = "0012_pupil_dilation_proxy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_synchrony_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False),
        sa.Column("window_ms", sa.Integer(), nullable=False),
        sa.Column("windows", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("video_id", "window_ms"),
    )


def downgrade() -> None:
    op.drop_table("video_synchrony_cache")
