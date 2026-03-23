from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _create_study(client: TestClient, name: str = "Catalog Study") -> str:
    response = client.post(
        "/studies",
        json={"name": name, "description": "catalog integration test"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_video(client: TestClient, study_id: str, title: str) -> str:
    response = client.post(
        "/videos",
        json={
            "study_id": study_id,
            "title": title,
            "source_url": "https://cdn.example.com/video.mp4",
            "duration_ms": 12_000,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_session(client: TestClient, study_id: str, video_id: str, participant_external_id: str, status: str) -> str:
    response = client.post(
        "/sessions",
        json={
            "study_id": study_id,
            "video_id": video_id,
            "participant": {"external_id": participant_external_id},
            "status": status,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_video_catalog_lists_recordings_with_recent_session_metadata(client: TestClient) -> None:
    study_id = _create_study(client)
    video_a_id = _create_video(client, study_id, "Video A")
    video_b_id = _create_video(client, study_id, "Video B")

    session_a1 = _create_session(client, study_id, video_a_id, "p-1", "created")
    session_a2 = _create_session(client, study_id, video_a_id, "p-2", "completed")

    # Catalog requires >= 10 trace points per video to be visible
    trace_rows = []
    for i in range(12):
        trace_rows.append({
            "video_time_ms": i * 1_000,
            "face_ok": True,
            "brightness": 91.2,
            "landmarks_ok": True,
            "blink": 0,
            "au": {"AU04": 0.01, "AU06": 0.02, "AU12": 0.04, "AU45": 0, "AU25": 0.01, "AU26": 0.01},
            "au_norm": {"AU04": 0.01, "AU06": 0.02, "AU12": 0.04, "AU45": 0, "AU25": 0.01, "AU26": 0.01},
            "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        })
    ingest_response = client.post(
        f"/sessions/{session_a2}/trace",
        content="\n".join(json.dumps(row) for row in trace_rows) + "\n",
        headers={"content-type": "application/x-ndjson"},
    )
    assert ingest_response.status_code == 200

    catalog_response = client.get("/videos?limit=10")
    assert catalog_response.status_code == 200
    payload = catalog_response.json()
    assert "items" in payload
    # Catalog filters out videos with zero sessions or < 10 trace points.
    # Only Video A (with 2 sessions and 12 trace rows) should appear.
    assert len(payload["items"]) >= 1

    items_by_video = {item["video_id"]: item for item in payload["items"]}
    assert video_a_id in items_by_video

    video_a = items_by_video[video_a_id]
    assert video_a["title"] == "Video A"
    assert video_a["sessions_count"] == 2
    assert video_a["completed_sessions_count"] == 1
    assert video_a["participants_count"] == 2
    assert video_a["last_session_id"] == session_a2
    assert video_a["last_session_status"] == "completed"
    assert video_a["latest_trace_at"] is not None
    assert [session["id"] for session in video_a["recent_sessions"]] == [session_a2, session_a1]

    # Video B has zero sessions and is excluded from the catalog
    assert video_b_id not in items_by_video


def _seed_video_with_trace(client: TestClient, study_id: str, title: str) -> str:
    """Create a video with a session and enough trace points to pass catalog filters."""
    video_id = _create_video(client, study_id, title)
    session_resp = client.post(
        "/sessions",
        json={"study_id": study_id, "video_id": video_id, "participant": {"external_id": f"p-{title}"}},
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]
    trace_rows = [
        {
            "video_time_ms": i * 1_000,
            "face_ok": True,
            "brightness": 90.0,
            "landmarks_ok": True,
            "blink": 0,
            "au": {"AU04": 0.01, "AU06": 0.02, "AU12": 0.04, "AU45": 0, "AU25": 0.01, "AU26": 0.01},
            "au_norm": {"AU04": 0.01, "AU06": 0.02, "AU12": 0.04, "AU45": 0, "AU25": 0.01, "AU26": 0.01},
            "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        }
        for i in range(12)
    ]
    ingest_resp = client.post(
        f"/sessions/{session_id}/trace",
        content="\n".join(json.dumps(row) for row in trace_rows) + "\n",
        headers={"content-type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200
    return video_id


def test_video_catalog_limit_is_applied(client: TestClient) -> None:
    study_id = _create_study(client, name="Limit Study")
    _seed_video_with_trace(client, study_id, "Video 1")
    _seed_video_with_trace(client, study_id, "Video 2")
    _seed_video_with_trace(client, study_id, "Video 3")

    response = client.get("/videos?limit=2")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
