"""Integration tests for capture archive observability and retention operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config import get_settings


def _create_session(client) -> tuple[dict, dict, dict]:
    study_resp = client.post(
        "/studies",
        json={"name": "Capture Ops Study", "description": "Capture ops test"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Capture Ops Video",
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
            "participant": {"external_id": "capture-ops-user"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()
    return study, video, session


def _payload(video_id: str) -> dict:
    return {
        "video_id": video_id,
        "frames": [
            {
                "id": str(uuid4()),
                "timestamp_ms": 1000,
                "video_time_ms": 900,
                "jpeg_base64": "Y2FwdHVyZS1hcmNoaXZlLWZyYW1l",
            }
        ],
        "frame_pointers": [],
    }


def test_capture_observability_reports_success_and_failure(client) -> None:
    _, video, session = _create_session(client)

    ok_response = client.post(f"/sessions/{session['id']}/captures", json=_payload(video["id"]))
    assert ok_response.status_code == 200, ok_response.text

    bad_payload = _payload(video["id"])
    bad_payload["video_id"] = str(uuid4())
    bad_response = client.post(f"/sessions/{session['id']}/captures", json=bad_payload)
    assert bad_response.status_code == 400

    status_response = client.get("/observability/capture-archives")
    assert status_response.status_code == 200, status_response.text
    payload = status_response.json()
    assert payload["enabled"] is True
    assert payload["ingestion_event_count"] == 2
    assert payload["success_count"] == 1
    assert payload["failure_count"] == 1
    assert payload["total_archives"] == 1
    assert payload["status"] in {"ok", "alert"}
    assert any(item["error_code"] == "video_mismatch" for item in payload["top_failure_codes"])


def test_capture_archive_purge_dry_run_and_delete(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBCAM_CAPTURE_ARCHIVE_RETENTION_DAYS", "1")
    monkeypatch.setenv("WEBCAM_CAPTURE_ARCHIVE_PURGE_BATCH_SIZE", "10")
    get_settings.cache_clear()
    try:
        _, video, session = _create_session(client)
        ingest_response = client.post(f"/sessions/{session['id']}/captures", json=_payload(video["id"]))
        assert ingest_response.status_code == 200, ingest_response.text

        class _FutureDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(timezone.utc) + timedelta(days=2)

        monkeypatch.setattr("app.services_capture.datetime", _FutureDateTime)

        dry_run = client.post("/maintenance/capture-archives/purge", params={"dry_run": "true"})
        assert dry_run.status_code == 200, dry_run.text
        dry_payload = dry_run.json()
        assert dry_payload["enabled"] is True
        assert dry_payload["dry_run"] is True
        assert dry_payload["candidate_count"] >= 1
        assert dry_payload["deleted_count"] == 0
        assert "dry_run_only_no_rows_deleted" in dry_payload["warnings"]

        apply_run = client.post("/maintenance/capture-archives/purge", params={"dry_run": "false"})
        assert apply_run.status_code == 200, apply_run.text
        apply_payload = apply_run.json()
        assert apply_payload["enabled"] is True
        assert apply_payload["dry_run"] is False
        assert apply_payload["deleted_count"] >= 1

        status_response = client.get("/observability/capture-archives")
        assert status_response.status_code == 200, status_response.text
        status_payload = status_response.json()
        assert status_payload["total_archives"] == 0
    finally:
        get_settings.cache_clear()


def test_capture_observability_flags_unsupported_encryption_mode(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE", "invalid_mode")
    get_settings.cache_clear()
    try:
        _, video, session = _create_session(client)
        response = client.post(f"/sessions/{session['id']}/captures", json=_payload(video["id"]))
        assert response.status_code == 400

        status_response = client.get("/observability/capture-archives")
        assert status_response.status_code == 200, status_response.text
        payload = status_response.json()
        assert payload["status"] == "alert"
        assert "unsupported_capture_encryption_mode" in payload["warnings"]
        assert payload["failure_count"] >= 1
        assert any(
            item["error_code"] == "unsupported_encryption_mode"
            for item in payload["top_failure_codes"]
        )
    finally:
        get_settings.cache_clear()
