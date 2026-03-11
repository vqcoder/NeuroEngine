"""Shared Pydantic contract for product-facing rollup presentations."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from .neuro_score_taxonomy import NeuroScoreStatus
from .readout_aggregate_metrics import SyntheticLiftCalibrationStatus


class ProductRollupMode(str, Enum):
    creator = "creator"
    enterprise = "enterprise"


class ProductRollupWarningSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ProductLiftTruthStatus(str, Enum):
    unavailable = "unavailable"
    pending = "pending"
    measured = "measured"


class ProductScoreSummary(BaseModel):
    metric_key: str = Field(min_length=1, max_length=64)
    display_label: str = Field(min_length=1)
    scalar_value: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: NeuroScoreStatus
    explanation: str = Field(min_length=1)
    source_metrics: List[str] = Field(default_factory=list)


class ProductRollupWarning(BaseModel):
    warning_key: str = Field(min_length=1, max_length=128)
    severity: ProductRollupWarningSeverity
    message: str = Field(min_length=1)
    source_metrics: List[str] = Field(default_factory=list)


class CreatorProductRollups(BaseModel):
    reception_score: ProductScoreSummary
    organic_reach_prior: ProductScoreSummary
    explanations: List[str] = Field(default_factory=list)
    warnings: List[ProductRollupWarning] = Field(default_factory=list)


class ProductLiftComparison(BaseModel):
    synthetic_lift_prior: ProductScoreSummary
    predicted_incremental_lift_pct: Optional[float] = None
    predicted_iroas: Optional[float] = None
    predicted_incremental_lift_ci_low: Optional[float] = None
    predicted_incremental_lift_ci_high: Optional[float] = None
    measured_lift_status: ProductLiftTruthStatus = ProductLiftTruthStatus.unavailable
    measured_incremental_lift_pct: Optional[float] = None
    measured_iroas: Optional[float] = None
    calibration_status: Optional[SyntheticLiftCalibrationStatus] = None
    note: str = Field(min_length=1)


class EnterpriseDecisionSupport(BaseModel):
    media_team_summary: str = Field(min_length=1)
    creative_team_summary: str = Field(min_length=1)


class EnterpriseProductRollups(BaseModel):
    paid_lift_prior: ProductScoreSummary
    brand_memory_prior: ProductScoreSummary
    cta_reception_score: ProductScoreSummary
    synthetic_lift_prior: ProductScoreSummary
    synthetic_vs_measured_lift: ProductLiftComparison
    decision_support: EnterpriseDecisionSupport


class ProductRollupPresentation(BaseModel):
    mode: ProductRollupMode
    workspace_tier: str = Field(min_length=1, max_length=64)
    enabled_modes: List[ProductRollupMode] = Field(default_factory=list)
    mode_resolution_note: Optional[str] = None
    source_schema_version: str = Field(min_length=1)
    creator: Optional[CreatorProductRollups] = None
    enterprise: Optional[EnterpriseProductRollups] = None

    @model_validator(mode="after")
    def validate_mode_payload(self) -> "ProductRollupPresentation":
        if self.mode not in self.enabled_modes:
            raise ValueError("mode must be present in enabled_modes")
        if self.mode == ProductRollupMode.creator and self.creator is None:
            raise ValueError("creator payload must be provided when mode=creator")
        if self.mode == ProductRollupMode.enterprise and self.enterprise is None:
            raise ValueError("enterprise payload must be provided when mode=enterprise")
        return self


for _model in (
    ProductScoreSummary,
    ProductLiftComparison,
    CreatorProductRollups,
    EnterpriseProductRollups,
    ProductRollupPresentation,
):
    _model.model_rebuild()
