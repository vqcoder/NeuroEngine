"""Tests for active learning queue + simulation behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.active_learning import simulate_uncertainty_sampling_advantage
from app import schemas


def test_uncertainty_sampling_reduces_error_faster_than_random():
    result = simulate_uncertainty_sampling_advantage(
        n_points=700,
        steps=28,
        batch_size=10,
        random_trials=50,
        seed=7,
    )

    assert result["uncertainty_auc"] < result["random_auc"] * 0.98
    assert result["uncertainty_final_error"] < result["random_final_error"]
    assert result["improvement_ratio"] > 0.01


def test_testing_queue_endpoint_returns_next_assignment(client, monkeypatch):
    study_id = uuid4()
    video_id = uuid4()

    fake_response = schemas.TestingQueueResponse(
        generated_at=datetime.now(timezone.utc),
        queue_size=10,
        target_sessions_per_video=3,
        items=[
            schemas.TestingQueueItem(
                study_id=study_id,
                video_id=video_id,
                title="High-Uncertainty Clip",
                source_url="file:///tmp/demo.mp4",
                duration_ms=45_000,
                existing_sessions=1,
                pending_sessions=2,
                mean_uncertainty=0.42,
                top_impact_score=0.36,
                uncertainty_trace=[
                    schemas.TestingUncertaintyPoint(
                        t_sec=0,
                        attention=52.0,
                        blink_inhibition=0.78,
                        dial=48.0,
                        uncertainty=0.5,
                    )
                ],
                recommended_segments=[
                    schemas.TestingQueueSegment(
                        start_sec=0,
                        end_sec=6,
                        mean_uncertainty=0.5,
                        hook_weight=1.0,
                        impact_score=0.5,
                    )
                ],
            )
        ],
        next_assignment=schemas.TestingQueueAssignment(
            study_id=study_id,
            video_id=video_id,
            start_sec=0,
            end_sec=6,
            rationale="Highest uncertainty and expected early-hook impact",
        ),
    )

    monkeypatch.setattr("app.routes_prediction.build_testing_queue", lambda *args, **kwargs: fake_response)

    response = client.get("/testing-queue")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["next_assignment"]["video_id"] == str(video_id)
    assert payload["items"][0]["recommended_segments"][0]["impact_score"] == 0.5
