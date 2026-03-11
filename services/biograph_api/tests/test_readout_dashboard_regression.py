"""End-to-end regression coverage for readout dashboard payload behavior."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "readout_dashboard_regression.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def _create_study_video(client, fixture: dict) -> tuple[dict, dict]:
    study_resp = client.post("/studies", json=fixture["study"])
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    payload = dict(fixture["video"])
    payload["study_id"] = study["id"]
    video_resp = client.post("/videos", json=payload)
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()
    return study, video


def _create_session(client, study_id: str, video_id: str, participant: dict) -> dict:
    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study_id,
            "video_id": video_id,
            "participant": participant,
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    return session_resp.json()


def _seed_fixture(client, fixture: dict) -> tuple[dict, dict, list[dict]]:
    study, video = _create_study_video(client, fixture)
    sessions: list[dict] = []
    for index, participant in enumerate(fixture["participants"]):
        session = _create_session(client, study["id"], video["id"], participant)
        sessions.append(session)
        trace_resp = client.post(
            f"/sessions/{session['id']}/trace",
            content=_jsonl_rows(fixture["session_rows"][index]),
            headers={"Content-Type": "application/x-ndjson"},
        )
        assert trace_resp.status_code == 200, trace_resp.text
        assert trace_resp.json()["inserted"] == len(fixture["session_rows"][index])

    annotation_resp = client.post(
        f"/sessions/{sessions[0]['id']}/annotations",
        json={
            "annotation_skipped": False,
            "annotations": [
                {
                    "session_id": sessions[0]["id"],
                    "video_id": video["id"],
                    **annotation,
                }
                for annotation in fixture["annotations"]
            ],
        },
    )
    assert annotation_resp.status_code == 200, annotation_resp.text
    return study, video, sessions


def _assert_trace_alignment(payload: dict) -> None:
    trace_keys = [
        "attention_score",
        "attention_velocity",
        "blink_rate",
        "blink_inhibition",
        "reward_proxy",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
        "tracking_confidence",
    ]
    time_axes: list[list[int]] = []
    for key in trace_keys:
        series = payload["traces"][key]
        times = [int(point["video_time_ms"]) for point in series]
        assert times == sorted(times), f"{key} is not monotonically sorted"
        assert all(time_ms % 1000 == 0 for time_ms in times), f"{key} is not on 1000ms buckets"
        time_axes.append(times)

    # All primary traces must align to the same time axis.
    reference_axis = time_axes[0]
    for axis in time_axes[1:]:
        assert axis == reference_axis


def test_readout_dashboard_regression_aggregate_mode(client):
    fixture = _load_fixture()
    _, video, _ = _seed_fixture(client, fixture)

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "true", "windowMs": 1000, "variantId": "variant-regression"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["schema_version"] == "1.0.0"
    assert payload["aggregate"] is True
    assert payload["timebase"]["window_ms"] == 1000
    assert payload["context"]["scenes"] == payload["scenes"]
    assert payload["video_id"] == video["id"]
    assert len(payload["scenes"]) == 4
    assert payload["scenes"][0]["scene_id"] == "scene-1"
    assert payload["scenes"][3]["scene_id"] == "scene-4"
    assert len(payload["cta_markers"]) == 1
    assert payload["cta_markers"][0]["cta_id"] == "cta-main"
    assert payload["cta_markers"][0]["video_time_ms"] == 4500

    # Backend returns reward_proxy naming only in readout traces.
    assert "reward_proxy" in payload["traces"]
    assert "valence_proxy" in payload["traces"]
    assert "arousal_proxy" in payload["traces"]
    assert "novelty_proxy" in payload["traces"]
    assert "dopamine" not in payload["traces"]

    _assert_trace_alignment(payload)

    attention_by_time = {
        point["video_time_ms"]: point["value"] for point in payload["traces"]["attention_score"]
    }
    assert (
        (attention_by_time[0] + attention_by_time[1000] + attention_by_time[2000]) / 3.0
        > (attention_by_time[6000] + attention_by_time[7000] + attention_by_time[8000]) / 3.0
    ), "strong hook should outscore mid-video drop"
    assert (
        (attention_by_time[9000] + attention_by_time[10000] + attention_by_time[11000]) / 3.0
        > (attention_by_time[6000] + attention_by_time[7000] + attention_by_time[8000]) / 3.0
    ), "late scene should recover from drop"

    segments = payload["segments"]
    assert len(segments["attention_gain_segments"]) > 0
    assert len(segments["attention_loss_segments"]) > 0
    assert len(segments["golden_scenes"]) > 0
    assert len(segments["confusion_segments"]) > 0

    assert any(
        segment.get("scene_id") == "scene-3"
        and int(segment["start_video_time_ms"]) <= 7000 <= int(segment["end_video_time_ms"])
        for segment in segments["attention_loss_segments"]
    )
    assert any(
        segment.get("scene_id") == "scene-4" for segment in segments["golden_scenes"]
    )
    assert any(
        segment.get("scene_id") == "scene-3" for segment in segments["confusion_segments"]
    )

    quality_summary = payload["quality_summary"]
    assert quality_summary["sessions_count"] == 2
    assert quality_summary["low_confidence_windows"] > 0
    assert quality_summary["mean_tracking_confidence"] is not None


def test_readout_dashboard_regression_single_session_mode(client):
    fixture = _load_fixture()
    _, video, sessions = _seed_fixture(client, fixture)

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={
            "aggregate": "false",
            "sessionId": sessions[0]["id"],
            "windowMs": 1000,
            "variantId": "variant-regression",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["schema_version"] == "1.0.0"
    assert payload["aggregate"] is False
    assert payload["quality_summary"]["sessions_count"] == 1
    assert payload["quality_summary"]["low_confidence_windows"] > 0
    assert len(payload["scenes"]) == 4
    assert len(payload["cta_markers"]) == 1
    _assert_trace_alignment(payload)
