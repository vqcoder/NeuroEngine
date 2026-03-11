"""Integration test: trace ingest tolerates richer extractor fields."""

from __future__ import annotations

import json

from app.config import get_settings
from app.schemas import TracePointIn


def test_trace_schema_prefers_reward_proxy_field_name():
    assert "reward_proxy" in TracePointIn.model_fields
    assert "dopamine" not in TracePointIn.model_fields


def test_trace_ingest_accepts_deprecated_dopamine_score_alias(client):
    study_resp = client.post(
        "/studies",
        json={"name": "Deprecated Alias Study", "description": "dopamine_score alias"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Deprecated alias clip",
            "source_url": "https://cdn.example.com/alias.mp4",
            "duration_ms": 2000,
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": {"external_id": "p-alias"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()

    row = {
        "video_time_ms": 0,
        "face_ok": True,
        "brightness": 80.0,
        "landmarks_ok": True,
        "blink": 0,
        "dopamine_score": 61.0,
        "au": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.0, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
        "au_norm": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.0, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
        "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
    }

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=json.dumps(row),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["inserted"] == 1


def test_trace_ingest_rejects_alias_only_reward_fields_in_strict_mode(client, monkeypatch):
    monkeypatch.setenv("STRICT_CANONICAL_TRACE_FIELDS", "true")
    get_settings.cache_clear()

    try:
        study_resp = client.post(
            "/studies",
            json={"name": "Strict Canonical Study", "description": "strict alias rejection"},
        )
        assert study_resp.status_code == 201, study_resp.text
        study = study_resp.json()

        video_resp = client.post(
            "/videos",
            json={
                "study_id": study["id"],
                "title": "Strict canonical clip",
                "source_url": "https://cdn.example.com/strict.mp4",
                "duration_ms": 2000,
            },
        )
        assert video_resp.status_code == 201, video_resp.text
        video = video_resp.json()

        session_resp = client.post(
            "/sessions",
            json={
                "study_id": study["id"],
                "video_id": video["id"],
                "participant": {"external_id": "p-strict"},
            },
        )
        assert session_resp.status_code == 201, session_resp.text
        session = session_resp.json()

        row = {
            "video_time_ms": 0,
            "face_ok": True,
            "brightness": 80.0,
            "landmarks_ok": True,
            "blink": 0,
            "dopamine_score": 61.0,
            "au": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.0, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
            "au_norm": {"AU04": 0.0, "AU06": 0.0, "AU12": 0.0, "AU45": 0.0, "AU25": 0.0, "AU26": 0.0},
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
        assert "dopamine_score" in detail["rejected_aliases"]
        assert detail["required_canonical_fields"] == ["reward_proxy", "video_time_ms"]
    finally:
        get_settings.cache_clear()


def test_trace_ingest_accepts_extended_extractor_fields(client):
    study_resp = client.post(
        "/studies",
        json={"name": "Extended Extractor Study", "description": "extra field ingest"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Stimulus extended",
            "source_url": "https://cdn.example.com/extended.mp4",
            "duration_ms": 2000,
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": {"external_id": "p-extra"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()

    row = {
        "t_ms": 0,
        "video_time_ms": 0,
        "face_ok": True,
        "brightness": 82.4,
        "landmarks_ok": True,
        "blink": 0,
        "au": {"AU04": 0.1, "AU06": 0.2, "AU12": 0.3, "AU45": 0.0, "AU25": 0.1, "AU26": 0.1},
        "au_norm": {
            "AU04": 0.01,
            "AU06": 0.02,
            "AU12": 0.03,
            "AU45": 0.0,
            "AU25": 0.01,
            "AU26": 0.01,
        },
        "head_pose": {"yaw": 2.1, "pitch": -1.2, "roll": 0.4},
        # Extended extractor fields (must be accepted, even if not persisted yet).
        "face_presence_confidence": 0.92,
        "landmarks_confidence": 0.88,
        "blink_confidence": 0.81,
        "head_pose_confidence": 0.79,
        "au_confidence": 0.85,
        "eye_openness": 0.73,
        "rolling_blink_rate": 0.12,
        "blink_baseline_rate": 0.28,
        "blink_inhibition_score": 0.57,
        "blink_inhibition_active": True,
        "gaze_on_screen_proxy": 0.74,
        "gaze_on_screen_confidence": 0.79,
        "blur": 145.0,
        "fps": 10.0,
        "fps_stability": 0.91,
        "face_visible_pct": 0.95,
        "occlusion_score": 0.1,
        "head_pose_valid_pct": 0.94,
        "quality_score": 0.83,
        "quality_confidence": 0.87,
        "tracking_confidence": 0.44,
        "quality_flags": ["low_light", "blur"],
    }

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=json.dumps(row),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["inserted"] == 1

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "false", "sessionId": session["id"], "windowMs": 1000},
    )
    assert readout_resp.status_code == 200, readout_resp.text
    payload = readout_resp.json()

    assert len(payload["traces"]["tracking_confidence"]) == 1
    assert payload["traces"]["tracking_confidence"][0]["value"] == 0.44
    assert payload["quality"]["session_quality_summary"]["low_confidence_windows"] == 1
    assert payload["quality"]["session_quality_summary"]["quality_badge"] == "low"

    low_windows = payload["quality"]["low_confidence_windows"]
    assert len(low_windows) == 1
    assert sorted(low_windows[0]["quality_flags"]) == ["blur", "low_light"]
