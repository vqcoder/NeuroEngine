"""add pupil dilation proxy columns to trace_points"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_pupil_dilation_proxy"
down_revision = "0011_frontend_diagnostic_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trace_points", sa.Column("pupil_dilation_proxy", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("pupil_dilation_proxy_raw", sa.Float(), nullable=True))
    op.add_column("trace_points", sa.Column("pupil_baseline_normalised", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trace_points", "pupil_baseline_normalised")
    op.drop_column("trace_points", "pupil_dilation_proxy_raw")
    op.drop_column("trace_points", "pupil_dilation_proxy")
