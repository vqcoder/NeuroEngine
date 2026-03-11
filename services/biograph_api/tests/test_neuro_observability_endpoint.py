"""Integration tests for neuro observability status endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings


def _write_history(path: Path, entries: list[dict]) -> None:
    payload = "\n".join(json.dumps(entry, sort_keys=True) for entry in entries)
    path.write_text(f"{payload}\n", encoding="utf-8")


def test_observability_status_endpoint_reports_missing_history_path(client, monkeypatch) -> None:
    monkeypatch.setenv("NEURO_OBSERVABILITY_ENABLED", "true")
    monkeypatch.delenv("NEURO_OBSERVABILITY_HISTORY_PATH", raising=False)
    monkeypatch.setenv("NEURO_OBSERVABILITY_HISTORY_MAX_ENTRIES", "50")
    monkeypatch.setenv("NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD", "12.0")
    get_settings.cache_clear()

    response = client.get("/observability/neuro")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["history_enabled"] is False
    assert payload["status"] == "no_history_config"
    assert payload["history_entry_count"] == 0
    assert "history_path_not_configured" in payload["warnings"]
    assert payload["latest_snapshot"] is None

    get_settings.cache_clear()


def test_observability_status_endpoint_aggregates_history_snapshot_metrics(
    client, tmp_path, monkeypatch
) -> None:
    history_path = tmp_path / "neuro_observability_history.jsonl"
    _write_history(
        history_path,
        [
            {
                "recorded_at": "2026-03-08T01:00:00Z",
                "video_id": "video-1",
                "variant_id": "variant-a",
                "model_signature": "neuro_taxonomy_v1",
                "missing_signal_rates": {"missing_signal_rate": 0.2},
                "pathway_usage": {"fallback_rate": 0.1},
                "confidence_distribution": {"mean": 0.72},
                "drift": {"status": "ok", "metrics_exceeding_threshold": []},
            },
            {
                "recorded_at": "2026-03-08T01:10:00Z",
                "video_id": "video-2",
                "variant_id": "variant-b",
                "model_signature": "neuro_taxonomy_v2",
                "missing_signal_rates": {"missing_signal_rate": 0.4},
                "pathway_usage": {"fallback_rate": 0.3},
                "confidence_distribution": {"mean": 0.64},
                "drift": {
                    "status": "alert",
                    "metrics_exceeding_threshold": ["arrest_score", "cta_reception_score"],
                },
            },
        ],
    )

    monkeypatch.setenv("NEURO_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("NEURO_OBSERVABILITY_HISTORY_PATH", str(history_path))
    monkeypatch.setenv("NEURO_OBSERVABILITY_HISTORY_MAX_ENTRIES", "10")
    monkeypatch.setenv("NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD", "12.0")
    get_settings.cache_clear()

    response = client.get("/observability/neuro")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["enabled"] is True
    assert payload["history_enabled"] is True
    assert payload["status"] == "alert"
    assert payload["history_entry_count"] == 2
    assert payload["recent_snapshot_count"] == 2
    assert payload["recent_drift_alert_count"] == 1
    assert payload["recent_drift_alert_rate"] == 0.5
    assert abs(payload["mean_missing_signal_rate"] - 0.3) < 1e-9
    assert abs(payload["mean_fallback_rate"] - 0.2) < 1e-9
    assert abs(payload["mean_confidence"] - 0.68) < 1e-9
    assert "recent_drift_alerts_present" in payload["warnings"]

    latest = payload["latest_snapshot"]
    assert latest is not None
    assert latest["recorded_at"] == "2026-03-08T01:10:00Z"
    assert latest["video_id"] == "video-2"
    assert latest["variant_id"] == "variant-b"
    assert latest["model_signature"] == "neuro_taxonomy_v2"
    assert latest["drift_status"] == "alert"
    assert latest["missing_signal_rate"] == 0.4
    assert latest["fallback_rate"] == 0.3
    assert latest["confidence_mean"] == 0.64
    assert latest["metrics_exceeding_threshold"] == [
        "arrest_score",
        "cta_reception_score",
    ]

    get_settings.cache_clear()
