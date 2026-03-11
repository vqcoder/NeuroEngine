"""Calibration routes for synthetic-lift prior."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .schemas import (
    SyntheticLiftCalibrationStateRead,
    SyntheticLiftCalibrationStatusResponse,
    SyntheticLiftCalibrationSyncRequest,
    SyntheticLiftCalibrationSyncResponse,
)
from .synthetic_lift_prior import (
    SyntheticLiftCalibrationState,
    get_incrementality_experiment_store_counts,
    get_last_calibration_applied_at,
    ingest_incrementality_experiment_results,
    load_synthetic_lift_calibration_state,
    reconcile_incrementality_calibration_store,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_calibration_state_read(
    state: SyntheticLiftCalibrationState,
) -> SyntheticLiftCalibrationStateRead:
    updated_at: Optional[datetime] = None
    if state.updated_at:
        normalized = str(state.updated_at).replace("Z", "+00:00")
        try:
            updated_at = datetime.fromisoformat(normalized)
        except ValueError:
            updated_at = None
    return SyntheticLiftCalibrationStateRead(
        model_version=state.model_version,
        truth_layer=state.truth_layer,
        observation_count=max(int(state.observation_count), 0),
        lift_bias_pct=float(state.lift_bias_pct),
        iroas_bias=float(state.iroas_bias),
        uncertainty_scale=float(state.uncertainty_scale),
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/calibration/synthetic-lift/experiments",
    response_model=SyntheticLiftCalibrationSyncResponse,
)
def sync_synthetic_lift_calibration_experiments(
    payload: SyntheticLiftCalibrationSyncRequest,
    db: Session = Depends(get_db),
) -> SyntheticLiftCalibrationSyncResponse:
    logger.info("sync_synthetic_lift_calibration_experiments count=%d", len(payload.experiments))
    ingest_result = ingest_incrementality_experiment_results(
        db,
        experiment_results=[
            item.model_dump(exclude_none=True)
            for item in payload.experiments
        ],
    )
    db.flush()

    if payload.apply_calibration_updates:
        reconciliation = reconcile_incrementality_calibration_store(db)
        calibration_state = reconciliation.calibration_state
        applied_count = reconciliation.applied_count
        pending_before = reconciliation.pending_before
        pending_after = reconciliation.pending_after
    else:
        calibration_state = load_synthetic_lift_calibration_state()
        _, pending_count = get_incrementality_experiment_store_counts(db)
        applied_count = 0
        pending_before = pending_count
        pending_after = pending_count

    db.flush()
    total_experiments, pending_count = get_incrementality_experiment_store_counts(db)
    db.commit()

    return SyntheticLiftCalibrationSyncResponse(
        ingested_count=ingest_result.ingested_count,
        duplicate_count=ingest_result.duplicate_count,
        applied_count=applied_count,
        pending_before=pending_before,
        pending_after=pending_after if payload.apply_calibration_updates else pending_count,
        total_experiments=total_experiments,
        calibration_state=_to_calibration_state_read(calibration_state),
    )


@router.get(
    "/calibration/synthetic-lift/status",
    response_model=SyntheticLiftCalibrationStatusResponse,
)
def get_synthetic_lift_calibration_status(
    db: Session = Depends(get_db),
) -> SyntheticLiftCalibrationStatusResponse:
    total_experiments, pending_experiments = get_incrementality_experiment_store_counts(db)
    state = load_synthetic_lift_calibration_state()
    return SyntheticLiftCalibrationStatusResponse(
        total_experiments=total_experiments,
        pending_experiments=pending_experiments,
        last_calibration_applied_at=get_last_calibration_applied_at(db),
        calibration_state=_to_calibration_state_read(state),
    )
