"""add persisted incrementality experiment results for calibration reconciliation"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_incrementality_experiment_results"
down_revision = "0007_video_timeline_feature_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incrementality_experiment_results",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("experiment_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("measured_incremental_lift_pct", sa.Float(), nullable=False),
        sa.Column("measured_iroas", sa.Float(), nullable=False),
        sa.Column("predicted_incremental_lift_pct", sa.Float(), nullable=True),
        sa.Column("predicted_iroas", sa.Float(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_run_id", sa.Uuid(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "experiment_id",
            name="uq_incrementality_experiment_results_experiment_id",
        ),
    )
    op.create_index(
        "ix_incrementality_experiment_results_pending",
        "incrementality_experiment_results",
        ["calibration_applied_at"],
    )
    op.create_index(
        "ix_incrementality_experiment_results_completed_at",
        "incrementality_experiment_results",
        ["completed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_incrementality_experiment_results_completed_at",
        table_name="incrementality_experiment_results",
    )
    op.drop_index(
        "ix_incrementality_experiment_results_pending",
        table_name="incrementality_experiment_results",
    )
    op.drop_table("incrementality_experiment_results")

