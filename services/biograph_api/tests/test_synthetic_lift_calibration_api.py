"""Integration tests for synthetic lift calibration experiment persistence/reconciliation APIs."""

from __future__ import annotations

from app.config import get_settings


def _payload() -> dict[str, object]:
    return {
        "experiments": [
            {
                "experiment_id": "exp-1001",
                "measured_incremental_lift_pct": 9.5,
                "measured_iroas": 2.25,
                "predicted_incremental_lift_pct": 6.0,
                "predicted_iroas": 1.7,
                "source": "geox_holdout",
                "completed_at": "2026-03-08T00:00:00Z",
            },
            {
                "experiment_id": "exp-1002",
                "measured_incremental_lift_pct": 7.2,
                "measured_iroas": 2.05,
                "predicted_incremental_lift_pct": 5.4,
                "predicted_iroas": 1.6,
                "source": "incrementality_feed",
                "completed_at": "2026-03-08T01:00:00Z",
            },
        ],
        "apply_calibration_updates": True,
    }


def test_synthetic_lift_calibration_sync_is_idempotent(client, tmp_path, monkeypatch):
    calibration_path = tmp_path / "synthetic_lift_calibration.json"
    monkeypatch.setenv("SYNTHETIC_LIFT_PRIOR_CALIBRATION_PATH", str(calibration_path))
    get_settings.cache_clear()

    first = client.post("/calibration/synthetic-lift/experiments", json=_payload())
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["ingested_count"] == 2
    assert first_payload["duplicate_count"] == 0
    assert first_payload["applied_count"] == 2
    assert first_payload["pending_after"] == 0
    assert first_payload["total_experiments"] == 2
    assert first_payload["calibration_state"]["observation_count"] == 2

    second = client.post("/calibration/synthetic-lift/experiments", json=_payload())
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["ingested_count"] == 0
    assert second_payload["duplicate_count"] == 2
    assert second_payload["applied_count"] == 0
    assert second_payload["pending_after"] == 0
    assert second_payload["total_experiments"] == 2
    assert second_payload["calibration_state"]["observation_count"] == 2

    status = client.get("/calibration/synthetic-lift/status")
    assert status.status_code == 200, status.text
    status_payload = status.json()
    assert status_payload["total_experiments"] == 2
    assert status_payload["pending_experiments"] == 0
    assert status_payload["last_calibration_applied_at"] is not None
    assert status_payload["calibration_state"]["observation_count"] == 2

    get_settings.cache_clear()


def test_synthetic_lift_calibration_sync_can_defer_apply(client, tmp_path, monkeypatch):
    calibration_path = tmp_path / "synthetic_lift_calibration.json"
    monkeypatch.setenv("SYNTHETIC_LIFT_PRIOR_CALIBRATION_PATH", str(calibration_path))
    get_settings.cache_clear()

    ingest_only = client.post(
        "/calibration/synthetic-lift/experiments",
        json={
            "experiments": [_payload()["experiments"][0]],
            "apply_calibration_updates": False,
        },
    )
    assert ingest_only.status_code == 200, ingest_only.text
    ingest_payload = ingest_only.json()
    assert ingest_payload["ingested_count"] == 1
    assert ingest_payload["applied_count"] == 0
    assert ingest_payload["pending_after"] == 1
    assert ingest_payload["calibration_state"]["observation_count"] == 0

    apply_later = client.post(
        "/calibration/synthetic-lift/experiments",
        json={"experiments": [], "apply_calibration_updates": True},
    )
    assert apply_later.status_code == 200, apply_later.text
    apply_payload = apply_later.json()
    assert apply_payload["ingested_count"] == 0
    assert apply_payload["applied_count"] == 1
    assert apply_payload["pending_after"] == 0
    assert apply_payload["calibration_state"]["observation_count"] == 1

    get_settings.cache_clear()

