"""add tracking confidence and quality flags to trace_points"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_trace_points_tracking_confidence_flags"
down_revision = "0004_passive_measurement_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # Railway Postgres instances often keep Alembic's default VARCHAR(32)
        # for version_num. This revision id exceeds 32 chars, so widen before
        # Alembic updates alembic_version at the end of the migration.
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    op.add_column("trace_points", sa.Column("tracking_confidence", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("quality_flags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trace_points", "quality_flags")
    op.drop_column("trace_points", "tracking_confidence")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
