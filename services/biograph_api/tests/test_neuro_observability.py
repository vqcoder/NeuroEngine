"""Tests for neuro score observability snapshots and drift tracking."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import get_settings
from app.neuro_observability import (
    build_neuro_observability_snapshot,
    build_score_observations,
    compute_confidence_distribution,
    compute_fallback_path_usage,
    compute_missing_signal_rates,
    compute_score_drift,
    emit_neuro_observability_snapshot,
)
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


def _load_quality_summary():
    payload = ReadoutPayload.model_validate(
        json.loads(READOUT_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    return payload.quality_summary


def test_score_observation_rates_and_confidence_distribution() -> None:
    taxonomy = _load_taxonomy()
    observations = build_score_observations(taxonomy)
    missing = compute_missing_signal_rates(observations)
    confidence = compute_confidence_distribution(observations)

    assert missing["total_scores"] == 11
    assert missing["available_scores"] == 11
    assert missing["missing_signal_rate"] == 0.0
    assert confidence["count"] == 11
    assert confidence["mean"] is not None
    assert sum(confidence["histogram"].values()) == 11


def test_fallback_path_usage_detects_fallback_modules() -> None:
    aggregate = _load_aggregate_metrics()
    usage = compute_fallback_path_usage(aggregate)

    assert usage["modules_evaluated"] >= 9
    assert "blink_transport" in usage["fallback_modules"]
    assert usage["fallback_rate"] is not None
    assert usage["fallback_rate"] > 0.0


def test_score_drift_flags_alert_when_threshold_exceeded() -> None:
    current = {
        "arrest_score": {"scalar_value": 80.0, "status": "available", "confidence": 0.8, "model_version": "v2"},
        "cta_reception_score": {
            "scalar_value": 70.0,
            "status": "available",
            "confidence": 0.75,
            "model_version": "v2",
        },
    }
    reference = {
        "arrest_score": {"scalar_value": 60.0, "status": "available", "confidence": 0.8, "model_version": "v1"},
        "cta_reception_score": {
            "scalar_value": 69.0,
            "status": "available",
            "confidence": 0.75,
            "model_version": "v1",
        },
    }

    drift = compute_score_drift(
        current_scores=current,
        reference_scores=reference,
        alert_threshold=12.0,
    )

    assert drift["status"] == "alert"
    assert "arrest_score" in drift["metrics_exceeding_threshold"]
    assert drift["max_abs_delta"] is not None
    assert float(drift["max_abs_delta"]) >= 20.0


def test_observability_snapshot_uses_history_reference_for_drift() -> None:
    taxonomy = _load_taxonomy()
    observations = build_score_observations(taxonomy)
    reference = dict(observations)
    reference["arrest_score"] = dict(reference["arrest_score"])
    reference["arrest_score"]["scalar_value"] = 52.0
    reference["arrest_score"]["model_version"] = "neuro_taxonomy_prev"

    snapshot = build_neuro_observability_snapshot(
        video_id="video-observability",
        variant_id="default",
        aggregate=True,
        included_sessions=3,
        taxonomy=taxonomy,
        aggregate_metrics=_load_aggregate_metrics(),
        quality_summary=_load_quality_summary(),
        drift_alert_threshold=12.0,
        history_entries=[
            {
                "recorded_at": "2026-03-01T00:00:00Z",
                "video_id": "video-observability",
                "model_signature": "neuro_taxonomy_prev",
                "scores": reference,
            }
        ],
    )

    assert snapshot["drift"]["status"] == "alert"
    assert snapshot["drift"]["reference_model_signature"] == "neuro_taxonomy_prev"
    assert "arrest_score" in snapshot["drift"]["metrics_exceeding_threshold"]


def test_emit_observability_snapshot_appends_history_entry(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "neuro_observability_history.jsonl"
    monkeypatch.setenv("NEURO_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("NEURO_OBSERVABILITY_HISTORY_PATH", str(history_path))
    monkeypatch.setenv("NEURO_OBSERVABILITY_HISTORY_MAX_ENTRIES", "10")
    monkeypatch.setenv("NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD", "10")
    get_settings.cache_clear()

    taxonomy = _load_taxonomy()
    snapshot = emit_neuro_observability_snapshot(
        logger=logging.getLogger("test-neuro-observability"),
        video_id="video-history",
        variant_id="default",
        aggregate=True,
        included_sessions=4,
        taxonomy=taxonomy,
        aggregate_metrics=_load_aggregate_metrics(),
        quality_summary=_load_quality_summary(),
    )

    assert snapshot is not None
    assert history_path.exists()
    lines = [line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "neuro_score_observability"
    assert payload["video_id"] == "video-history"

    get_settings.cache_clear()

