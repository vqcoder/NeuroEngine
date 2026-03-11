"""add session capture archive table for persisted webcam payloads"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_session_capture_archives"
down_revision = "0008_incrementality_experiment_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_capture_archives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frame_pointer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uncompressed_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compressed_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_gzip", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            name="uq_session_capture_archives_session_id",
        ),
    )
    op.create_index(
        "ix_session_capture_archives_video_id_created_at",
        "session_capture_archives",
        ["video_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_capture_archives_video_id_created_at",
        table_name="session_capture_archives",
    )
    op.drop_table("session_capture_archives")
