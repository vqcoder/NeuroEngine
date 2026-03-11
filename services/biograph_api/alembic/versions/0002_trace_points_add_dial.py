"""add dial field to trace_points"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_trace_points_add_dial"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trace_points", sa.Column("dial", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trace_points", "dial")
