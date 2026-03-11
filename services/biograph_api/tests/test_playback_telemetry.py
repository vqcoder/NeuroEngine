"""Integration tests for playback telemetry ingestion."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "synthetic_session.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_playback_telemetry_rejects_video_mismatch(client):
    study_resp = client.post(
        "/studies",
        json={"name": "Telemetry Study", "description": "telemetry validation"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={"study_id": study["id"], "title": "Primary video"},
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    other_video_resp = client.post(
        "/videos",
        json={"study_id": study["id"], "title": "Other video"},
    )
    assert other_video_resp.status_code == 201, other_video_resp.text
    other_video = other_video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": {"external_id": "p-telemetry"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()

    telemetry_resp = client.post(
        f"/sessions/{session['id']}/telemetry",
        json={
            "events": [
                {
                    "session_id": session["id"],
                    "video_id": other_video["id"],
                    "event_type": "play",
                    "video_time_ms": 0,
                }
            ]
        },
    )
    assert telemetry_resp.status_code == 400, telemetry_resp.text
    assert "video_id does not match" in telemetry_resp.text


def test_playback_telemetry_event_set_aligns_to_video_time_ms(client):
    fixture = _load_fixture()

    study_resp = client.post("/studies", json=fixture["study"])
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            **fixture["video"],
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": fixture["participant"],
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()

    telemetry_resp = client.post(
        f"/sessions/{session['id']}/telemetry",
        json={
            "events": [
                {
                    "session_id": session["id"],
                    "video_id": video["id"],
                    **event,
                }
                for event in fixture["telemetry_events"]
            ]
        },
    )
    assert telemetry_resp.status_code == 200, telemetry_resp.text
    assert telemetry_resp.json()["inserted"] == len(fixture["telemetry_events"])

    summary_resp = client.get(f"/videos/{video['id']}/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    telemetry = summary["playback_telemetry"]

    expected_types = {
        "play",
        "pause",
        "seek_start",
        "seek_end",
        "seek",
        "rewind",
        "mute",
        "unmute",
        "volume_change",
        "fullscreen_enter",
        "fullscreen_exit",
        "visibility_hidden",
        "visibility_visible",
        "window_blur",
        "window_focus",
        "abandonment",
    }
    observed_types = {event["event_type"] for event in telemetry}
    assert expected_types.issubset(observed_types)

    timestamps = [event["video_time_ms"] for event in telemetry]
    assert timestamps == sorted(timestamps)
    for value in timestamps:
        assert isinstance(value, int)
        assert value >= 0

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "true", "windowMs": 1000},
    )
    assert readout_resp.status_code == 200, readout_resp.text
    readout = readout_resp.json()
    readout_event_types = {event["event_type"] for event in readout["playback_telemetry"]}
    assert {"pause", "seek_end", "abandonment"}.issubset(readout_event_types)
