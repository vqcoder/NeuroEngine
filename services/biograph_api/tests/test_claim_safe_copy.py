"""Claim-safe copy guardrails for registry/API/UI-facing text templates."""

from __future__ import annotations

import json
from pathlib import Path

from app.claim_safety import find_claim_safety_violations, scan_texts_for_claim_safety
from app.neuro_score_taxonomy import list_rollup_registry_entries, list_score_registry_entries
from app.product_rollups import build_product_rollup_presentation
from app.schemas import NeuroScoreTaxonomy, ReadoutAggregateMetrics, ReadoutPayload


TAXONOMY_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "neuro_score_taxonomy.sample.json"
)
AGGREGATE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "readout_aggregate_metrics.sample.json"
)
READOUT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "readout_payload.sample.json"
)


def _load_taxonomy() -> NeuroScoreTaxonomy:
    return NeuroScoreTaxonomy.model_validate(
        json.loads(TAXONOMY_FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _load_aggregate_metrics() -> ReadoutAggregateMetrics:
    return ReadoutAggregateMetrics.model_validate(
        json.loads(AGGREGATE_FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _load_diagnostics():
    payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    return payload.diagnostics


def test_claim_safety_checker_flags_unsupported_copy() -> None:
    violations = find_claim_safety_violations(
        "This is a direct dopamine measurement and predicts sales with certainty."
    )
    assert "direct_dopamine_measurement" in violations
    assert "sales_certainty_claim" in violations


def test_registry_claim_safe_descriptions_have_no_unsupported_claims() -> None:
    texts = {
        f"score_registry:{entry.machine_name.value}": entry.claim_safe_description
        for entry in list_score_registry_entries()
    }
    texts.update(
        {
            f"rollup_registry:{entry.machine_name.value}": entry.claim_safe_description
            for entry in list_rollup_registry_entries()
        }
    )
    violations = scan_texts_for_claim_safety(texts)
    assert violations == {}


def test_product_rollup_copy_has_no_unsupported_claims() -> None:
    taxonomy = _load_taxonomy()
    aggregate_metrics = _load_aggregate_metrics()
    diagnostics = _load_diagnostics()

    creator = build_product_rollup_presentation(
        taxonomy=taxonomy,
        aggregate_metrics=aggregate_metrics,
        diagnostics=diagnostics,
        requested_workspace_tier="creator",
    )
    enterprise = build_product_rollup_presentation(
        taxonomy=taxonomy,
        aggregate_metrics=aggregate_metrics,
        diagnostics=diagnostics,
        requested_workspace_tier="enterprise",
    )

    assert creator is not None
    assert enterprise is not None
    assert creator.creator is not None
    assert enterprise.enterprise is not None

    texts = {}
    for index, line in enumerate(creator.creator.explanations):
        texts[f"creator_explanation:{index}"] = line
    for warning in creator.creator.warnings:
        texts[f"creator_warning:{warning.warning_key}"] = warning.message
    texts["enterprise_media_summary"] = enterprise.enterprise.decision_support.media_team_summary
    texts["enterprise_creative_summary"] = enterprise.enterprise.decision_support.creative_team_summary
    texts["enterprise_lift_note"] = enterprise.enterprise.synthetic_vs_measured_lift.note

    violations = scan_texts_for_claim_safety(texts)
    assert violations == {}


def test_ui_and_api_docs_have_no_unsupported_claim_phrases() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    target_paths = [
        repo_root / "docs" / "readout_payload.md",
        repo_root / "docs" / "product_rollup_modes.md",
        repo_root / "apps" / "dashboard" / "src" / "components" / "NeuroScorecards.tsx",
        repo_root / "apps" / "dashboard" / "src" / "components" / "ProductRollupPanel.tsx",
        repo_root / "services" / "biograph_api" / "app" / "schemas.py",
    ]

    texts = {
        str(path.relative_to(repo_root)): path.read_text(encoding="utf-8")
        for path in target_paths
        if path.exists()
    }
    violations = scan_texts_for_claim_safety(texts)
    assert violations == {}
