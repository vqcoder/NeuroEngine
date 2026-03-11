"""add capture archive encryption metadata and ingest event telemetry table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_capture_archive_ops"
down_revision = "0009_session_capture_archives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_capture_archives",
        sa.Column(
            "encryption_mode",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "session_capture_archives",
        sa.Column(
            "encryption_key_id",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.create_table(
        "session_capture_ingest_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frame_pointer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_capture_ingest_events_created_at",
        "session_capture_ingest_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_session_capture_ingest_events_outcome_created_at",
        "session_capture_ingest_events",
        ["outcome", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_capture_ingest_events_outcome_created_at",
        table_name="session_capture_ingest_events",
    )
    op.drop_index(
        "ix_session_capture_ingest_events_created_at",
        table_name="session_capture_ingest_events",
    )
    op.drop_table("session_capture_ingest_events")
    op.drop_column("session_capture_archives", "encryption_key_id")
    op.drop_column("session_capture_archives", "encryption_mode")
