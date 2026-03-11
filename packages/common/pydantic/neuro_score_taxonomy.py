"""Shared Pydantic contract for the neuro-score taxonomy payload."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .schemas_common import TimeRangeMixin


class NeuroScoreStatus(str, Enum):
    available = "available"
    unavailable = "unavailable"
    insufficient_data = "insufficient_data"


class NeuroScoreMachineName(str, Enum):
    arrest_score = "arrest_score"
    attentional_synchrony_index = "attentional_synchrony_index"
    narrative_control_score = "narrative_control_score"
    blink_transport_score = "blink_transport_score"
    boundary_encoding_score = "boundary_encoding_score"
    reward_anticipation_index = "reward_anticipation_index"
    social_transmission_score = "social_transmission_score"
    self_relevance_score = "self_relevance_score"
    cta_reception_score = "cta_reception_score"
    synthetic_lift_prior = "synthetic_lift_prior"
    au_friction_score = "au_friction_score"


class NeuroRollupMachineName(str, Enum):
    organic_reach_prior = "organic_reach_prior"
    paid_lift_prior = "paid_lift_prior"
    brand_memory_prior = "brand_memory_prior"


class NeuroEvidenceWindow(TimeRangeMixin):
    reason: str = Field(min_length=1)


class NeuroFeatureContribution(BaseModel):
    feature_name: str = Field(min_length=1)
    contribution: float
    rationale: Optional[str] = Field(default=None, min_length=1)


class NeuroScoreContract(BaseModel):
    machine_name: NeuroScoreMachineName
    display_label: str = Field(min_length=1)
    scalar_value: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: NeuroScoreStatus
    evidence_windows: List[NeuroEvidenceWindow] = Field(default_factory=list)
    top_feature_contributions: List[NeuroFeatureContribution] = Field(default_factory=list)
    model_version: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    claim_safe_description: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_available_payload(self) -> "NeuroScoreContract":
        if self.status == NeuroScoreStatus.available:
            if self.scalar_value is None:
                raise ValueError("scalar_value must be provided when status=available")
            if self.confidence is None:
                raise ValueError("confidence must be provided when status=available")
        return self


class NeuroCompositeRollup(BaseModel):
    machine_name: NeuroRollupMachineName
    display_label: str = Field(min_length=1)
    scalar_value: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: NeuroScoreStatus
    component_scores: List[NeuroScoreMachineName] = Field(default_factory=list)
    component_weights: Dict[str, float] = Field(default_factory=dict)
    model_version: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    claim_safe_description: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_available_payload(self) -> "NeuroCompositeRollup":
        if self.status == NeuroScoreStatus.available:
            if self.scalar_value is None:
                raise ValueError("scalar_value must be provided when status=available")
            if self.confidence is None:
                raise ValueError("confidence must be provided when status=available")
        return self


class LegacyScoreAdapter(BaseModel):
    legacy_output: Literal["emotion", "attention"]
    mapped_machine_name: NeuroScoreMachineName
    scalar_value: Optional[float] = Field(default=None, ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: NeuroScoreStatus
    notes: Optional[str] = None


class NeuroScoreRegistryEntry(BaseModel):
    machine_name: NeuroScoreMachineName
    display_label: str = Field(min_length=1)
    claim_safe_description: str = Field(min_length=1)
    builder_key: str = Field(min_length=1)


class NeuroRollupRegistryEntry(BaseModel):
    machine_name: NeuroRollupMachineName
    display_label: str = Field(min_length=1)
    claim_safe_description: str = Field(min_length=1)
    builder_key: str = Field(min_length=1)


class NeuroScoreFamilies(BaseModel):
    arrest_score: NeuroScoreContract
    attentional_synchrony_index: NeuroScoreContract
    narrative_control_score: NeuroScoreContract
    blink_transport_score: NeuroScoreContract
    boundary_encoding_score: NeuroScoreContract
    reward_anticipation_index: NeuroScoreContract
    social_transmission_score: NeuroScoreContract
    self_relevance_score: NeuroScoreContract
    cta_reception_score: NeuroScoreContract
    synthetic_lift_prior: NeuroScoreContract
    au_friction_score: NeuroScoreContract

    @model_validator(mode="after")
    def validate_family_machine_names(self) -> "NeuroScoreFamilies":
        expected = {
            "arrest_score": NeuroScoreMachineName.arrest_score,
            "attentional_synchrony_index": NeuroScoreMachineName.attentional_synchrony_index,
            "narrative_control_score": NeuroScoreMachineName.narrative_control_score,
            "blink_transport_score": NeuroScoreMachineName.blink_transport_score,
            "boundary_encoding_score": NeuroScoreMachineName.boundary_encoding_score,
            "reward_anticipation_index": NeuroScoreMachineName.reward_anticipation_index,
            "social_transmission_score": NeuroScoreMachineName.social_transmission_score,
            "self_relevance_score": NeuroScoreMachineName.self_relevance_score,
            "cta_reception_score": NeuroScoreMachineName.cta_reception_score,
            "synthetic_lift_prior": NeuroScoreMachineName.synthetic_lift_prior,
            "au_friction_score": NeuroScoreMachineName.au_friction_score,
        }
        for field_name, expected_name in expected.items():
            if getattr(self, field_name).machine_name != expected_name:
                raise ValueError(f"{field_name}.machine_name must be '{expected_name.value}'")
        return self


class NeuroRollupFamilies(BaseModel):
    organic_reach_prior: NeuroCompositeRollup
    paid_lift_prior: NeuroCompositeRollup
    brand_memory_prior: NeuroCompositeRollup

    @model_validator(mode="after")
    def validate_rollup_machine_names(self) -> "NeuroRollupFamilies":
        expected = {
            "organic_reach_prior": NeuroRollupMachineName.organic_reach_prior,
            "paid_lift_prior": NeuroRollupMachineName.paid_lift_prior,
            "brand_memory_prior": NeuroRollupMachineName.brand_memory_prior,
        }
        for field_name, expected_name in expected.items():
            if getattr(self, field_name).machine_name != expected_name:
                raise ValueError(f"{field_name}.machine_name must be '{expected_name.value}'")
        return self


class NeuroScoreTaxonomy(BaseModel):
    schema_version: str = Field(min_length=1)
    scores: NeuroScoreFamilies
    rollups: NeuroRollupFamilies
    registry: List[NeuroScoreRegistryEntry] = Field(default_factory=list)
    rollup_registry: List[NeuroRollupRegistryEntry] = Field(default_factory=list)
    legacy_score_adapters: List[LegacyScoreAdapter] = Field(default_factory=list)


for _model in (
    NeuroScoreContract,
    NeuroCompositeRollup,
    NeuroScoreFamilies,
    NeuroRollupFamilies,
    NeuroScoreTaxonomy,
):
    _model.model_rebuild()
