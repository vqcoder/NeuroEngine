"""Integration test: ingest synthetic passive session and validate summary outputs."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "synthetic_session.json"


def _jsonl_rows(rows):
    return "\n".join(json.dumps(row) for row in rows)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_ingest_and_summary_aggregation(client):
    fixture = _load_fixture()

    study_resp = client.post("/studies", json=fixture["study"])
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_payload = dict(fixture["video"])
    video_payload["study_id"] = study["id"]
    video_resp = client.post("/videos", json=video_payload)
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

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(fixture["trace_rows"]),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["inserted"] == len(fixture["trace_rows"])

    survey_resp = client.post(
        f"/sessions/{session['id']}/survey",
        json={
            "responses": [
                {"question_key": "overall_interest_likert", "response_number": 4},
                {
                    "question_key": "post_annotation_comment",
                    "response_text": "Strong ending and clear CTA.",
                },
            ]
        },
    )
    assert survey_resp.status_code == 200, survey_resp.text
    assert survey_resp.json()["inserted"] == 2

    annotations_resp = client.post(
        f"/sessions/{session['id']}/annotations",
        json={
            "annotation_skipped": False,
            "annotations": [
                {
                    "session_id": session["id"],
                    "video_id": video["id"],
                    "marker_type": annotation["marker_type"],
                    "video_time_ms": annotation["video_time_ms"],
                    "note": annotation["note"],
                    "created_at": annotation["created_at"],
                }
                for annotation in fixture["annotations"]
            ],
        },
    )
    assert annotations_resp.status_code == 200, annotations_resp.text
    assert annotations_resp.json()["inserted"] == len(fixture["annotations"])
    assert annotations_resp.json()["annotation_skipped"] is False

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
    payload = summary_resp.json()

    qc = payload["qc_stats"]
    assert qc["sessions_count"] == 1
    assert qc["participants_count"] == 1
    assert qc["total_trace_points"] == 6
    assert qc["missing_trace_sessions"] == 0
    assert abs(qc["face_ok_rate"] - (5 / 6)) < 1e-6

    scene_metrics = payload["scene_metrics"]
    assert len(scene_metrics) == 2
    assert scene_metrics[0]["label"] == "intro"
    assert scene_metrics[0]["scene_id"] == "scene-1"
    assert scene_metrics[0]["cut_id"] == "cut-1"
    assert scene_metrics[0]["cta_id"] == "cta-prep"
    assert scene_metrics[0]["samples"] == 3

    assert scene_metrics[1]["label"] == "cta"
    assert scene_metrics[1]["scene_id"] == "scene-2"
    assert scene_metrics[1]["cut_id"] == "cut-2"
    assert scene_metrics[1]["cta_id"] == "cta-main"
    assert scene_metrics[1]["samples"] == 3

    trace_buckets = payload["trace_buckets"]
    assert len(trace_buckets) == 6
    assert trace_buckets[0]["bucket_start_ms"] == 0
    assert trace_buckets[0]["samples"] == 1
    assert abs(trace_buckets[0]["mean_reward_proxy"] - 58.0) < 1e-6
    assert trace_buckets[0]["scene_id"] == "scene-1"
    assert trace_buckets[3]["scene_id"] == "scene-2"
    # Schema/API should expose reward_proxy naming only.
    assert "dopamine" not in trace_buckets[0]

    assert len(payload["passive_traces"]) == 6
    assert len(payload["quality_overlays"]) == 6
    assert len(payload["scene_aligned_summaries"]) == 2

    low_light_overlay = payload["quality_overlays"][0]
    assert low_light_overlay["mean_brightness"] < 20
    assert (low_light_overlay["mean_quality_score"] or 0) < 0.5

    annotations = payload["annotations"]
    assert len(annotations) == 3
    assert annotations[0]["marker_type"] == "engaging_moment"
    assert annotations[1]["marker_type"] == "confusing_moment"
    assert annotations[2]["marker_type"] == "cta_landed_moment"
    assert annotations[2]["cta_id"] == "cta-main"
    assert len(payload["explicit_labels"]) == 3

    assert len(payload["survey_responses"]) == 2
    assert payload["survey_responses"][0]["question_key"] == "overall_interest_likert"

    telemetry = payload["playback_telemetry"]
    assert len(telemetry) == len(fixture["telemetry_events"])

    expected_event_types = {
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
    observed_event_types = {event["event_type"] for event in telemetry}
    assert expected_event_types.issubset(observed_event_types)

    for event in telemetry:
        assert isinstance(event["video_time_ms"], int)
        assert event["video_time_ms"] >= 0

    # Scene/CTA alignment is preserved on telemetry windows.
    fullscreen_enter = next(item for item in telemetry if item["event_type"] == "fullscreen_enter")
    assert fullscreen_enter["scene_id"] == "scene-2"
    assert fullscreen_enter["cta_id"] == "cta-main"
