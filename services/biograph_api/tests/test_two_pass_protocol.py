"""Integration test coverage for two-pass annotation + survey persistence."""

from __future__ import annotations


def test_two_pass_marker_and_survey_rows_persist(client):
    study_resp = client.post(
        "/studies",
        json={"name": "Two-pass Study", "description": "two-pass protocol validation"},
    )
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_resp = client.post(
        "/videos",
        json={
            "study_id": study["id"],
            "title": "Two-pass stimulus",
            "duration_ms": 30_000,
            "scene_boundaries": [
                {
                    "scene_index": 0,
                    "start_ms": 0,
                    "end_ms": 30_000,
                    "label": "full",
                    "scene_id": "scene-1",
                    "cut_id": "cut-1",
                }
            ],
        },
    )
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study["id"],
            "video_id": video["id"],
            "participant": {"external_id": "p-two-pass"},
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
                    "event_type": "play",
                    "video_time_ms": 0,
                },
                {
                    "session_id": session["id"],
                    "video_id": video["id"],
                    "event_type": "ended",
                    "video_time_ms": 9000,
                },
            ]
        },
    )
    assert telemetry_resp.status_code == 200, telemetry_resp.text
    assert telemetry_resp.json()["inserted"] == 2

    annotations_resp = client.post(
        f"/sessions/{session['id']}/annotations",
        json={
            "annotation_skipped": False,
            "annotations": [
                {
                    "session_id": session["id"],
                    "video_id": video["id"],
                    "marker_type": "engaging_moment",
                    "video_time_ms": 4200,
                    "note": "Hook landed strongly.",
                }
            ],
        },
    )
    assert annotations_resp.status_code == 200, annotations_resp.text
    assert annotations_resp.json()["inserted"] == 1
    assert annotations_resp.json()["annotation_skipped"] is False

    survey_resp = client.post(
        f"/sessions/{session['id']}/survey",
        json={
            "responses": [
                {"question_key": "overall_interest_likert", "response_number": 4},
                {"question_key": "recall_comprehension_likert", "response_number": 3},
                {
                    "question_key": "desire_to_continue_or_take_action_likert",
                    "response_number": 5,
                },
            ]
        },
    )
    assert survey_resp.status_code == 200, survey_resp.text
    assert survey_resp.json()["inserted"] == 3

    summary_resp = client.get(f"/videos/{video['id']}/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary_payload = summary_resp.json()

    assert len(summary_payload["annotations"]) == 1
    assert summary_payload["annotations"][0]["marker_type"] == "engaging_moment"
    assert summary_payload["annotations"][0]["video_time_ms"] == 4200

    survey_rows = summary_payload["survey_responses"]
    assert len(survey_rows) == 3
    survey_keys = {row["question_key"] for row in survey_rows}
    assert {
        "overall_interest_likert",
        "recall_comprehension_likert",
        "desire_to_continue_or_take_action_likert",
    }.issubset(survey_keys)

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "true", "windowMs": 1000},
    )
    assert readout_resp.status_code == 200, readout_resp.text
    readout_payload = readout_resp.json()

    assert len(readout_payload["labels"]["annotations"]) == 1
    assert readout_payload["labels"]["annotations"][0]["marker_type"] == "engaging_moment"
    assert readout_payload["labels"]["survey_summary"]["responses_count"] == 3
