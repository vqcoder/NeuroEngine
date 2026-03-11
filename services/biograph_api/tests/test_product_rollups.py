"""Unit tests for product-facing rollup presentation layer."""

from __future__ import annotations

import json
from pathlib import Path

from app.product_rollups import build_product_rollup_presentation
from app.schemas import (
    NeuroScoreTaxonomy,
    ProductRollupPresentation,
    ProductRollupMode,
    ReadoutAggregateMetrics,
    ReadoutPayload,
)


READOUT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "readout_payload.sample.json"
)
AGGREGATE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "readout_aggregate_metrics.sample.json"
)
TAXONOMY_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "neuro_score_taxonomy.sample.json"
)
CREATOR_PRODUCT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "product_rollups_creator.sample.json"
)
ENTERPRISE_PRODUCT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "product_rollups_enterprise.sample.json"
)


def _load_taxonomy() -> NeuroScoreTaxonomy:
    return NeuroScoreTaxonomy.model_validate(
        json.loads(TAXONOMY_FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _load_aggregate_metrics() -> ReadoutAggregateMetrics:
    return ReadoutAggregateMetrics.model_validate(
        json.loads(AGGREGATE_FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _load_diagnostics() -> list:
    payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    return payload.diagnostics


def test_creator_product_rollup_mode_builds_simple_surface() -> None:
    presentation = build_product_rollup_presentation(
        taxonomy=_load_taxonomy(),
        aggregate_metrics=_load_aggregate_metrics(),
        diagnostics=_load_diagnostics(),
        video_metadata={"workspace_tier": "creator"},
    )

    assert presentation is not None
    assert presentation.mode == ProductRollupMode.creator
    assert presentation.creator is not None
    assert presentation.enterprise is None
    assert presentation.creator.reception_score.metric_key == "reception_score"
    assert presentation.creator.organic_reach_prior.metric_key == "organic_reach_prior"
    assert presentation.creator.explanations


def test_enterprise_product_rollup_mode_builds_rich_surface() -> None:
    presentation = build_product_rollup_presentation(
        taxonomy=_load_taxonomy(),
        aggregate_metrics=_load_aggregate_metrics(),
        diagnostics=_load_diagnostics(),
        video_metadata={"workspace_tier": "enterprise"},
    )

    assert presentation is not None
    assert presentation.mode == ProductRollupMode.enterprise
    assert presentation.creator is None
    assert presentation.enterprise is not None
    assert presentation.enterprise.paid_lift_prior.metric_key == "paid_lift_prior"
    assert presentation.enterprise.brand_memory_prior.metric_key == "brand_memory_prior"
    assert (
        presentation.enterprise.synthetic_vs_measured_lift.synthetic_lift_prior.metric_key
        == "synthetic_lift_prior"
    )


def test_requested_mode_is_gated_by_workspace_tier() -> None:
    presentation = build_product_rollup_presentation(
        taxonomy=_load_taxonomy(),
        aggregate_metrics=_load_aggregate_metrics(),
        diagnostics=_load_diagnostics(),
        requested_mode=ProductRollupMode.enterprise,
        video_metadata={"workspace_tier": "creator"},
    )

    assert presentation is not None
    assert presentation.mode == ProductRollupMode.creator
    assert presentation.creator is not None
    assert presentation.mode_resolution_note is not None
    assert "disabled" in presentation.mode_resolution_note


def test_product_rollup_fixtures_validate() -> None:
    creator_payload = json.loads(CREATOR_PRODUCT_FIXTURE_PATH.read_text(encoding="utf-8"))
    enterprise_payload = json.loads(
        ENTERPRISE_PRODUCT_FIXTURE_PATH.read_text(encoding="utf-8")
    )

    creator = ProductRollupPresentation.model_validate(creator_payload)
    enterprise = ProductRollupPresentation.model_validate(enterprise_payload)

    assert creator.mode == ProductRollupMode.creator
    assert creator.creator is not None
    assert enterprise.mode == ProductRollupMode.enterprise
    assert enterprise.enterprise is not None
