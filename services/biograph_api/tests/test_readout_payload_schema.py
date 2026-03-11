"""Schema validation tests for versioned ReadoutPayload contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import ReadoutAggregateMetrics, ReadoutPayload


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "readout_payload.sample.json"
)
AGGREGATE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "readout_aggregate_metrics.sample.json"
)


def test_readout_payload_fixture_validates() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    parsed = ReadoutPayload.model_validate(payload)

    assert parsed.schema_version == "1.0.0"
    assert parsed.timebase.window_ms == parsed.timebase.step_ms
    assert len(parsed.traces.reward_proxy) > 0
    assert len(parsed.traces.valence_proxy) == len(parsed.traces.reward_proxy)
    assert len(parsed.context.scenes) >= 1


def test_readout_payload_rejects_missing_schema_version() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload.pop("schema_version", None)

    with pytest.raises(ValidationError):
        ReadoutPayload.model_validate(payload)


def _collect_dict_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            keys.update(_collect_dict_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_dict_keys(item))
    return keys


def test_readout_payload_uses_reward_proxy_naming_only() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    parsed = ReadoutPayload.model_validate(payload)
    dumped = parsed.model_dump(mode="json", exclude_none=True)

    keys = _collect_dict_keys(dumped)
    assert "reward_proxy" in keys
    assert "dopamine" not in keys


def test_readout_aggregate_fixture_with_blink_transport_validates() -> None:
    payload = json.loads(AGGREGATE_FIXTURE_PATH.read_text(encoding="utf-8"))
    parsed = ReadoutAggregateMetrics.model_validate(payload)

    assert parsed.attentional_synchrony is not None
    assert parsed.narrative_control is not None
    assert parsed.blink_transport is not None
    assert parsed.blink_transport.pathway.value == "fallback_proxy"
    assert parsed.blink_transport.global_score is not None
    assert len(parsed.blink_transport.segment_scores) >= 1
    assert parsed.reward_anticipation is not None
    assert parsed.reward_anticipation.pathway.value in {"timeline_dynamics", "fallback_proxy"}
    assert len(parsed.reward_anticipation.anticipation_ramps) >= 1
    assert parsed.boundary_encoding is not None
    assert parsed.boundary_encoding.pathway.value in {"timeline_boundary_model", "fallback_proxy"}
    assert len(parsed.boundary_encoding.strong_windows) >= 1
    assert parsed.au_friction is not None
    assert parsed.au_friction.pathway.value in {"au_signal_model", "fallback_proxy"}
    assert len(parsed.au_friction.segment_scores) >= 1
    assert parsed.cta_reception is not None
    assert parsed.cta_reception.pathway.value in {"multi_signal_model", "fallback_proxy"}
    assert len(parsed.cta_reception.cta_windows) >= 1
    assert parsed.social_transmission is not None
    assert parsed.social_transmission.pathway.value in {
        "annotation_augmented",
        "timeline_signal_model",
        "fallback_proxy",
    }
    assert len(parsed.social_transmission.segment_scores) >= 1
    assert parsed.self_relevance is not None
    assert parsed.self_relevance.pathway.value in {
        "contextual_personalization",
        "survey_augmented",
        "fallback_proxy",
    }
    assert len(parsed.self_relevance.segment_scores) >= 1
    assert parsed.synthetic_lift_prior is not None
    assert parsed.synthetic_lift_prior.pathway.value in {
        "taxonomy_regression",
        "fallback_proxy",
        "insufficient_data",
    }
    if parsed.synthetic_lift_prior.pathway.value != "insufficient_data":
        assert parsed.synthetic_lift_prior.predicted_incremental_lift_pct is not None
        assert parsed.synthetic_lift_prior.predicted_iroas is not None
