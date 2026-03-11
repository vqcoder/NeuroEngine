"""Integration tests for reusable video timeline analysis and feature queries."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.config import get_settings


def _build_synthetic_video(video_path: Path, *, tone_hz: int = 440) -> None:
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        pytest.skip("ffmpeg is required for timeline analysis test")

    command = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=160x90:d=1:r=10",
        "-f",
        "lavfi",
        "-i",
        "color=c=white:s=160x90:d=1:r=10",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=160x90:d=1:r=10",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={tone_hz}:duration=3",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(video_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - environment codec variance
        pytest.skip(f"Unable to generate synthetic video fixture: {exc.stderr}")


def _create_study_and_video(client, video_path: Path, *, asset_id: str) -> tuple[str, str]:
    study_resp = client.post("/studies", json={"name": "Timeline Study", "description": "test"})
    assert study_resp.status_code == 201, study_resp.text
    study_id = study_resp.json()["id"]

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study_id,
            "title": "Synthetic Timeline Video",
            "source_url": str(video_path),
            "duration_ms": 3000,
            "metadata": {
                "asset_id": asset_id,
                "text_overlays": [
                    {
                        "start_ms": 1200,
                        "end_ms": 2000,
                        "text": "Try it now",
                        "confidence": 0.88,
                    }
                ],
            },
            "cta_markers": [
                {
                    "cta_id": "cta-main",
                    "start_ms": 1800,
                    "end_ms": 2600,
                    "label": "Primary CTA",
                }
            ],
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video_id = video_resp.json()["id"]
    return study_id, video_id


def test_timeline_analysis_pipeline_and_windowed_query(client, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TIMELINE_ANALYSIS_RETENTION_LIMIT", "2")
    get_settings.cache_clear()
    video_path = tmp_path / "timeline_synthetic.mp4"
    _build_synthetic_video(video_path)

    asset_id = "asset-timeline-synthetic"
    _, video_id = _create_study_and_video(client, video_path, asset_id=asset_id)

    run_resp = client.post(
        f"/videos/{video_id}/timeline-analysis",
        json={
            "sample_interval_ms": 500,
            "scene_threshold": 0.25,
        },
    )
    assert run_resp.status_code == 200, run_resp.text
    run_payload = run_resp.json()
    assert run_payload["status"] == "completed"
    assert run_payload["asset_id"] == asset_id
    assert run_payload["metadata"]["segment_count"] > 0
    assert run_payload["metadata"]["feature_track_count"] > 0
    assert run_payload["reused_existing"] is False

    query_resp = client.get(
        f"/timeline-features/{asset_id}",
        params={"start_ms": 0, "end_ms": 3000},
    )
    assert query_resp.status_code == 200, query_resp.text
    payload = query_resp.json()
    segment_types = {segment["segment_type"] for segment in payload["segments"]}
    track_names = {track["track_name"] for track in payload["feature_tracks"]}

    assert "frame_sample" in segment_types
    assert "shot_boundary" in segment_types
    assert "scene_block" in segment_types
    assert "cta_window" in segment_types
    assert "text_overlay" in segment_types
    assert "luminance_mean" in track_names
    assert "cut_cadence" in track_names
    assert "audio_intensity_rms" in track_names
    assert payload["window_start_ms"] == 0
    assert payload["window_end_ms"] == 3000

    filtered_resp = client.get(
        f"/timeline-features/{asset_id}",
        params=[
            ("start_ms", 0),
            ("end_ms", 2000),
            ("track_name", "luminance_mean"),
            ("segment_type", "shot_boundary"),
        ],
    )
    assert filtered_resp.status_code == 200, filtered_resp.text
    filtered_payload = filtered_resp.json()
    assert all(
        track["track_name"] == "luminance_mean"
        for track in filtered_payload["feature_tracks"]
    )
    assert all(
        segment["segment_type"] == "shot_boundary"
        for segment in filtered_payload["segments"]
    )

    rerun_resp = client.post(
        f"/videos/{video_id}/timeline-analysis",
        json={
            "sample_interval_ms": 500,
            "scene_threshold": 0.25,
        },
    )
    assert rerun_resp.status_code == 200, rerun_resp.text
    rerun_payload = rerun_resp.json()
    assert rerun_payload["reused_existing"] is True
    assert rerun_payload["analysis_id"] == run_payload["analysis_id"]

    force_resp = client.post(
        f"/videos/{video_id}/timeline-analysis",
        json={
            "sample_interval_ms": 500,
            "scene_threshold": 0.25,
            "force_recompute": True,
        },
    )
    assert force_resp.status_code == 200, force_resp.text
    force_payload = force_resp.json()
    assert force_payload["status"] == "completed"
    assert force_payload["reused_existing"] is False

    extra_force_ids = [force_payload["analysis_id"]]
    for index, tone_hz in enumerate((550, 660, 770), start=1):
        variant_path = tmp_path / f"timeline_variant_{index}.mp4"
        _build_synthetic_video(variant_path, tone_hz=tone_hz)
        extra_force_resp = client.post(
            f"/videos/{video_id}/timeline-analysis",
            json={
                "sample_interval_ms": 500,
                "scene_threshold": 0.25,
                "force_recompute": True,
                "source_ref": str(variant_path),
            },
        )
        assert extra_force_resp.status_code == 200, extra_force_resp.text
        extra_force_ids.append(extra_force_resp.json()["analysis_id"])

    oldest_status = client.get(f"/timeline-analysis/{run_payload['analysis_id']}")
    assert oldest_status.status_code == 404, oldest_status.text

    latest_status = client.get(f"/timeline-analysis/{extra_force_ids[-1]}")
    assert latest_status.status_code == 200, latest_status.text
    assert latest_status.json()["status"] == "completed"

    _, async_video_id = _create_study_and_video(
        client,
        video_path,
        asset_id="asset-timeline-async",
    )
    async_resp = client.post(
        f"/videos/{async_video_id}/timeline-analysis",
        json={
            "sample_interval_ms": 500,
            "scene_threshold": 0.25,
            "run_async": True,
        },
    )
    assert async_resp.status_code == 200, async_resp.text
    async_payload = async_resp.json()
    analysis_id = async_payload["analysis_id"]
    assert async_payload["status"] in {"running", "completed"}

    terminal = None
    for _ in range(20):
        status_resp = client.get(f"/timeline-analysis/{analysis_id}")
        assert status_resp.status_code == 200, status_resp.text
        status_payload = status_resp.json()
        if status_payload["status"] in {"completed", "failed"}:
            terminal = status_payload
            break
        time.sleep(0.05)

    assert terminal is not None, "async timeline analysis did not finish in time"
    assert terminal["status"] == "completed"

    async_query = client.get(
        "/timeline-features/asset-timeline-async",
        params={"start_ms": 0, "end_ms": 3000},
    )
    assert async_query.status_code == 200, async_query.text

    get_settings.cache_clear()
