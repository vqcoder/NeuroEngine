"""Unit tests for prediction service fallback behavior."""

from __future__ import annotations

from pathlib import Path

from app.predict_service import (
    _estimate_duration_seconds,
    predict_from_video,
    predict_from_video_with_backend,
)


def test_estimate_duration_seconds_fallback_without_ffprobe(tmp_path: Path, monkeypatch):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")

    def fake_subprocess_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise FileNotFoundError("ffprobe missing")

    monkeypatch.setattr("app.predict_service.subprocess.run", fake_subprocess_run)

    assert _estimate_duration_seconds(video_path) == 60


def test_predict_from_video_uses_heuristic_when_model_missing(tmp_path: Path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")
    missing_model_path = tmp_path / "missing.joblib"

    predictions = predict_from_video(video_path=video_path, model_artifact_path=missing_model_path)

    assert len(predictions) > 1
    assert predictions[0].reward_proxy is not None
    assert predictions[0].attention is not None
    assert 0.0 <= predictions[0].blink_inhibition <= 100.0
    assert predictions[0].reward_proxy != predictions[0].attention
    assert predictions[0].attention_velocity is not None
    assert predictions[0].blink_rate is not None
    assert predictions[0].valence_proxy is not None
    assert predictions[0].arousal_proxy is not None
    assert predictions[0].novelty_proxy is not None
    assert predictions[0].tracking_confidence is not None


def test_predict_from_video_with_backend_reports_fallback_reason(tmp_path: Path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")
    missing_model_path = tmp_path / "missing.joblib"

    execution = predict_from_video_with_backend(video_path=video_path, model_artifact_path=missing_model_path)

    assert execution.backend == "heuristic_fallback_missing_artifact"
    assert execution.predictions
