"""Integration tests for canonical video_time_ms alignment."""

from __future__ import annotations

import json

from app.config import get_settings


def _create_study_video_session(client):
    study_resp = client.post(
        "/studies",
        json={"name": "Video Time Canonical", "description": "alignment checks"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Canonical timeline stimulus",
            "duration_ms": 8000,
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": {"external_id": "p-canonical"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()

    return study, video, session


def test_trace_ingest_flags_rows_missing_video_time_ms_and_normalizes_alignment(client):
    _, video, session = _create_study_video_session(client)

    base_row = {
        "face_ok": True,
        "brightness": 80.0,
        "landmarks_ok": True,
        "blink": 0,
        "au": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.1, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
        "au_norm": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.1, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
        "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
    }

    rows = [
        {"t_ms": 1250, **base_row},
        {"t_ms": 2400, "video_time_ms": 2400, **base_row},
    ]

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content="\n".join(json.dumps(row) for row in rows),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    payload = ingest_resp.json()
    assert payload["inserted"] == 2
    assert payload["flagged_missing_video_time_ms"] == 1

    summary_resp = client.get(f"/videos/{video['id']}/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    bucket_starts = [bucket["bucket_start_ms"] for bucket in summary["trace_buckets"]]
    assert bucket_starts == [1000, 2000]


def test_telemetry_ingest_rejects_missing_video_time_ms_and_persists_integer_alignment(client):
    _, video, session = _create_study_video_session(client)

    invalid_telemetry_resp = client.post(
        f"/sessions/{session['id']}/telemetry",
        json={
            "events": [
                {
                    "session_id": session["id"],
                    "video_id": video["id"],
                    "event_type": "play",
                }
            ]
        },
    )
    assert invalid_telemetry_resp.status_code == 422, invalid_telemetry_resp.text

    valid_telemetry_resp = client.post(
        f"/sessions/{session['id']}/telemetry",
        json={
            "events": [
                {
                    "session_id": session["id"],
                    "video_id": video["id"],
                    "event_type": "play",
                    "video_time_ms": 1250,
                    "client_monotonic_ms": 1255,
                    "wall_time_ms": 1700000000123,
                }
            ]
        },
    )
    assert valid_telemetry_resp.status_code == 200, valid_telemetry_resp.text
    assert valid_telemetry_resp.json()["inserted"] == 1

    summary_resp = client.get(f"/videos/{video['id']}/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert len(summary["playback_telemetry"]) == 1
    assert isinstance(summary["playback_telemetry"][0]["video_time_ms"], int)
    assert summary["playback_telemetry"][0]["video_time_ms"] == 1250


def test_trace_ingest_rejects_t_ms_alias_only_rows_in_strict_mode(client, monkeypatch):
    _, _, session = _create_study_video_session(client)

    monkeypatch.setenv("STRICT_CANONICAL_TRACE_FIELDS", "true")
    get_settings.cache_clear()
    try:
        row = {
            "t_ms": 1500,
            "face_ok": True,
            "brightness": 81.0,
            "landmarks_ok": True,
            "blink": 0,
            "reward_proxy": 48.0,
            "au": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.1, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
            "au_norm": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.1, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
            "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        }

        ingest_resp = client.post(
            f"/sessions/{session['id']}/trace",
            content=json.dumps(row),
            headers={"Content-Type": "application/x-ndjson"},
        )
        assert ingest_resp.status_code == 422, ingest_resp.text
        detail = ingest_resp.json()["detail"]
        assert detail["strict_canonical_trace_fields"] is True
        assert detail["line_number"] == 1
        assert "t_ms" in detail["rejected_aliases"]
        assert detail["required_canonical_fields"] == ["reward_proxy", "video_time_ms"]
    finally:
        get_settings.cache_clear()
