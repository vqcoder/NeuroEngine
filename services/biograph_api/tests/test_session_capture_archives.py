"""Integration coverage for session capture archive ingestion."""

from __future__ import annotations

from uuid import uuid4

from app.config import get_settings


def _create_session(client) -> tuple[dict, dict, dict]:
    study_resp = client.post(
        "/studies",
        json={"name": "Capture Study", "description": "Capture archive test"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Capture Video",
            "source_url": "/sample.mp4",
            "duration_ms": 60_000,
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": {"external_id": "capture-participant-1"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()
    return study, video, session


def _capture_payload(video_id: str) -> dict:
    return {
        "video_id": video_id,
        "frames": [
            {
                "id": str(uuid4()),
                "timestamp_ms": 1200,
                "video_time_ms": 1100,
                "jpeg_base64": "dGVzdC1mcmFtZS1iYXNlNjQ=",
            },
            {
                "id": str(uuid4()),
                "timestamp_ms": 2400,
                "video_time_ms": 2300,
                "jpeg_base64": "dGVzdC1mcmFtZS1iYXNlNjQtMg==",
            },
        ],
        "frame_pointers": [
            {
                "id": str(uuid4()),
                "timestamp_ms": 3600,
                "video_time_ms": 3500,
                "pointer": "memory-frame-1",
            }
        ],
    }


def test_capture_ingest_upserts_session_archive(client) -> None:
    _, video, session = _create_session(client)

    first_resp = client.post(
        f"/sessions/{session['id']}/captures",
        json=_capture_payload(video["id"]),
    )
    assert first_resp.status_code == 200, first_resp.text
    first_payload = first_resp.json()
    assert first_payload["session_id"] == session["id"]
    assert first_payload["video_id"] == video["id"]
    assert first_payload["frame_count"] == 2
    assert first_payload["frame_pointer_count"] == 1
    assert first_payload["compressed_bytes"] > 0
    assert first_payload["uncompressed_bytes"] >= first_payload["compressed_bytes"]
    assert first_payload["encryption_mode"] == "none"
    assert first_payload["encryption_key_id"] is None

    replacement_payload = {
        "video_id": video["id"],
        "frames": [
            {
                "id": str(uuid4()),
                "timestamp_ms": 8000,
                "video_time_ms": 7800,
                "jpeg_base64": "cmVwbGFjZW1lbnQtZnJhbWU=",
            }
        ],
        "frame_pointers": [],
    }
    second_resp = client.post(
        f"/sessions/{session['id']}/captures",
        json=replacement_payload,
    )
    assert second_resp.status_code == 200, second_resp.text
    second_payload = second_resp.json()
    assert second_payload["capture_archive_id"] == first_payload["capture_archive_id"]
    assert second_payload["frame_count"] == 1
    assert second_payload["frame_pointer_count"] == 0
    assert second_payload["payload_sha256"] != first_payload["payload_sha256"]
    assert second_payload["encryption_mode"] == "none"


def test_capture_ingest_rejects_video_mismatch(client) -> None:
    _, video, session = _create_session(client)
    payload = _capture_payload(video["id"])
    payload["video_id"] = str(uuid4())
    response = client.post(
        f"/sessions/{session['id']}/captures",
        json=payload,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Capture video_id does not match target session video"


def test_capture_ingest_respects_feature_flag(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBCAM_CAPTURE_ARCHIVE_ENABLED", "false")
    get_settings.cache_clear()
    try:
        _, video, session = _create_session(client)
        response = client.post(
            f"/sessions/{session['id']}/captures",
            json=_capture_payload(video["id"]),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Session capture archive endpoint is disabled"
    finally:
        get_settings.cache_clear()


def test_capture_ingest_enforces_frame_limit(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBCAM_CAPTURE_ARCHIVE_MAX_FRAMES", "1")
    get_settings.cache_clear()
    try:
        _, video, session = _create_session(client)
        response = client.post(
            f"/sessions/{session['id']}/captures",
            json=_capture_payload(video["id"]),
        )
        assert response.status_code == 413
        assert "exceeds configured limit" in response.json()["detail"]
    finally:
        get_settings.cache_clear()
