"""add frontend diagnostic events table for cross-page failure observability"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_frontend_diagnostic_events"
down_revision = "0010_capture_archive_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frontend_diagnostic_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("page", sa.String(length=32), nullable=False),
        sa.Column("route", sa.String(length=512), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="error"),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("study_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_frontend_diagnostic_events_created_at",
        "frontend_diagnostic_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_frontend_diagnostic_events_surface_page_created_at",
        "frontend_diagnostic_events",
        ["surface", "page", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_frontend_diagnostic_events_severity_created_at",
        "frontend_diagnostic_events",
        ["severity", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_frontend_diagnostic_events_event_type_created_at",
        "frontend_diagnostic_events",
        ["event_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_frontend_diagnostic_events_event_type_created_at",
        table_name="frontend_diagnostic_events",
    )
    op.drop_index(
        "ix_frontend_diagnostic_events_severity_created_at",
        table_name="frontend_diagnostic_events",
    )
    op.drop_index(
        "ix_frontend_diagnostic_events_surface_page_created_at",
        table_name="frontend_diagnostic_events",
    )
    op.drop_index(
        "ix_frontend_diagnostic_events_created_at",
        table_name="frontend_diagnostic_events",
    )
    op.drop_table("frontend_diagnostic_events")
