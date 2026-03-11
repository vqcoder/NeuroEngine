"""Integration tests for frontend diagnostics observability endpoints."""

from __future__ import annotations

from uuid import uuid4


def _create_session(client) -> tuple[dict, dict, dict]:
    study_resp = client.post(
        "/studies",
        json={"name": "Frontend Diagnostics Study", "description": "diagnostics integration test"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Frontend Diagnostics Video",
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
            "participant": {"external_id": "frontend-diagnostics-user"},
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session = session_resp.json()
    return study, video, session


def test_frontend_diagnostics_ingest_events_and_summary(client) -> None:
    study, video, session = _create_session(client)

    first_event = {
        "surface": "watchlab",
        "page": "study",
        "route": f"/study/{study['id']}",
        "severity": "error",
        "event_type": "video_playback_failed",
        "error_code": "no_supported_source",
        "message": "Video playback failed: no supported source was found.",
        "session_id": session["id"],
        "video_id": video["id"],
        "study_id": study["id"],
        "context": {"candidate_url": "https://example.com/landing-page"},
    }
    ingest_first = client.post("/observability/frontend-diagnostics/events", json=first_event)
    assert ingest_first.status_code == 201, ingest_first.text
    first_payload = ingest_first.json()
    assert first_payload["surface"] == "watchlab"
    assert first_payload["page"] == "study"
    assert first_payload["event_type"] == "video_playback_failed"
    assert first_payload["context"]["candidate_url"] == "https://example.com/landing-page"

    second_event = {
        "surface": "dashboard",
        "page": "predictor",
        "severity": "warning",
        "event_type": "prediction_url_blocked",
        "error_code": "platform_blocked",
        "message": "URL provider blocked server-side download.",
        "video_id": video["id"],
    }
    ingest_second = client.post("/observability/frontend-diagnostics/events", json=second_event)
    assert ingest_second.status_code == 201, ingest_second.text

    third_event = {
        "surface": "dashboard",
        "page": "readout",
        "severity": "info",
        "event_type": "video_playback_recovered",
        "video_id": video["id"],
        "study_id": study["id"],
    }
    ingest_third = client.post("/observability/frontend-diagnostics/events", json=third_event)
    assert ingest_third.status_code == 201, ingest_third.text

    events_response = client.get("/observability/frontend-diagnostics/events", params={"limit": 10})
    assert events_response.status_code == 200, events_response.text
    events_payload = events_response.json()
    assert len(events_payload["items"]) == 3
    assert events_payload["items"][0]["event_type"] == "video_playback_recovered"
    assert events_payload["items"][1]["event_type"] == "prediction_url_blocked"
    assert events_payload["items"][2]["event_type"] == "video_playback_failed"

    summary_response = client.get(
        "/observability/frontend-diagnostics/summary",
        params={"window_hours": 24, "top_n": 5},
    )
    assert summary_response.status_code == 200, summary_response.text
    summary_payload = summary_response.json()
    assert summary_payload["status"] == "alert"
    assert summary_payload["window_hours"] == 24
    assert summary_payload["total_events"] == 3
    assert summary_payload["error_count"] == 1
    assert summary_payload["warning_count"] == 1
    assert summary_payload["info_count"] == 1
    assert "study" in summary_payload["active_pages"]
    assert "predictor" in summary_payload["active_pages"]
    assert "readout" in summary_payload["active_pages"]
    assert summary_payload["top_errors"][0]["event_type"] == "video_playback_failed"
    assert summary_payload["top_errors"][0]["error_code"] == "no_supported_source"


def test_frontend_diagnostics_supports_filters(client) -> None:
    _, video, _session = _create_session(client)

    events = [
        {
            "surface": "dashboard",
            "page": "readout",
            "severity": "error",
            "event_type": "readout_fetch_failed",
            "error_code": "network_error",
            "video_id": video["id"],
        },
        {
            "surface": "dashboard",
            "page": "predictor",
            "severity": "error",
            "event_type": "prediction_failed",
            "error_code": "timeout",
            "video_id": video["id"],
        },
        {
            "surface": "watchlab",
            "page": "study",
            "severity": "warning",
            "event_type": "video_source_fallback",
            "error_code": "legacy_asset_fallback",
            "video_id": video["id"],
            "study_id": str(uuid4()),
        },
    ]
    for payload in events:
        response = client.post("/observability/frontend-diagnostics/events", json=payload)
        assert response.status_code == 201, response.text

    filtered_response = client.get(
        "/observability/frontend-diagnostics/events",
        params={"page": "readout", "severity": "error", "limit": 5},
    )
    assert filtered_response.status_code == 200, filtered_response.text
    items = filtered_response.json()["items"]
    assert len(items) == 1
    assert items[0]["event_type"] == "readout_fetch_failed"
    assert items[0]["page"] == "readout"
    assert items[0]["severity"] == "error"
