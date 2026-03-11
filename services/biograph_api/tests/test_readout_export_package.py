"""Integration tests for readout export package endpoint."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "readout_session.json"


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


def _seed_readout_data(client, fixture: dict) -> tuple[dict, dict, list[dict]]:
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

    annotations_one = [
        {
            "session_id": sessions[0]["id"],
            "video_id": video["id"],
            **annotation,
        }
        for annotation in fixture["annotations"]
    ]
    annotations_two = [
        {
            "session_id": sessions[1]["id"],
            "video_id": video["id"],
            "marker_type": "engaging_moment",
            "video_time_ms": 4100,
            "note": "Second viewer engagement",
            "created_at": "2026-03-05T16:11:01Z",
        },
        {
            "session_id": sessions[1]["id"],
            "video_id": video["id"],
            "marker_type": "stop_watching_moment",
            "video_time_ms": 7300,
            "note": "Second viewer drop-off",
            "created_at": "2026-03-05T16:11:03Z",
        },
    ]
    annotations_resp_one = client.post(
        f"/sessions/{sessions[0]['id']}/annotations",
        json={"annotation_skipped": False, "annotations": annotations_one},
    )
    annotations_resp_two = client.post(
        f"/sessions/{sessions[1]['id']}/annotations",
        json={"annotation_skipped": False, "annotations": annotations_two},
    )
    assert annotations_resp_one.status_code == 200, annotations_resp_one.text
    assert annotations_resp_two.status_code == 200, annotations_resp_two.text

    survey_one = client.post(
        f"/sessions/{sessions[0]['id']}/survey",
        json={
            "responses": [
                {"question_key": "overall_interest_likert", "response_number": 4},
                {"question_key": "recall_comprehension_likert", "response_number": 3},
                {
                    "question_key": "desire_to_continue_or_take_action_likert",
                    "response_number": 5,
                },
                {
                    "question_key": "post_annotation_comment",
                    "response_text": "Great middle section",
                },
            ]
        },
    )
    survey_two = client.post(
        f"/sessions/{sessions[1]['id']}/survey",
        json={
            "responses": [
                {"question_key": "overall_interest_likert", "response_number": 2},
                {"question_key": "recall_comprehension_likert", "response_number": 4},
                {
                    "question_key": "desire_to_continue_or_take_action_likert",
                    "response_number": 3,
                },
                {
                    "question_key": "post_annotation_comment",
                    "response_text": "Ending was confusing",
                },
            ]
        },
    )
    assert survey_one.status_code == 200, survey_one.text
    assert survey_two.status_code == 200, survey_two.text
    return study, video, sessions


def test_readout_export_package_schema_stability(client):
    fixture = _load_fixture()
    _, video, _ = _seed_readout_data(client, fixture)

    response = client.get(
        f"/videos/{video['id']}/readout/export-package",
        params={"aggregate": "true", "windowMs": 1000, "variantId": "variant-a"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert set(payload.keys()) == {
        "video_metadata",
        "per_timepoint_csv",
        "readout_json",
        "compact_report",
    }

    metadata = payload["video_metadata"]
    assert set(metadata.keys()) == {
        "video_id",
        "study_id",
        "study_name",
        "title",
        "source_url",
        "duration_ms",
        "variant_id",
        "aggregate",
        "session_id",
        "window_ms",
        "generated_at",
    }
    assert metadata["video_id"] == video["id"]
    assert metadata["aggregate"] is True
    assert metadata["window_ms"] == 1000

    readout_json = payload["readout_json"]
    assert set(readout_json.keys()) == {
        "video_metadata",
        "scenes",
        "cta_markers",
        "segments",
        "diagnostics",
        "reward_proxy_peaks",
        "quality_summary",
        "annotation_summary",
        "survey_summary",
        "neuro_scores",
        "product_rollups",
        "legacy_score_adapters",
    }
    assert len(readout_json["reward_proxy_peaks"]) > 0
    assert "video_time_ms" in readout_json["reward_proxy_peaks"][0]
    assert "reward_proxy" in readout_json["reward_proxy_peaks"][0]

    compact = payload["compact_report"]
    assert set(compact.keys()) == {
        "video_metadata",
        "scenes",
        "cta_markers",
        "attention_gain_segments",
        "attention_loss_segments",
        "golden_scenes",
        "dead_zones",
        "reward_proxy_peaks",
        "quality_summary",
        "annotation_summary",
        "survey_summary",
        "highlights",
        "neuro_scores",
        "product_rollups",
        "legacy_score_adapters",
    }
    assert compact["highlights"]["top_reward_proxy_peak"] is not None
    assert compact["highlights"]["top_golden_scene"] is not None
    assert compact["neuro_scores"] is not None
    assert compact["product_rollups"] is not None
    assert len(compact["legacy_score_adapters"]) == 2

    csv_payload = payload["per_timepoint_csv"]
    csv_rows = list(csv.reader(StringIO(csv_payload)))
    assert len(csv_rows) == 10  # 9 time windows + header
    header = csv_rows[0]
    assert header[:14] == [
        "video_time_ms",
        "second",
        "scene_id",
        "cut_id",
        "cta_id",
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


def test_readout_export_package_fixture_sample_content(client, tmp_path: Path):
    fixture = _load_fixture()
    _, video, _ = _seed_readout_data(client, fixture)

    response = client.get(
        f"/videos/{video['id']}/readout/export-package",
        params={"aggregate": "true", "windowMs": 1000, "variantId": "variant-a"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    package_path = tmp_path / "readout_export_package.json"
    package_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert package_path.exists()

    loaded = json.loads(package_path.read_text(encoding="utf-8"))
    assert loaded["video_metadata"]["title"] == fixture["video"]["title"]
    assert loaded["video_metadata"]["source_url"] == fixture["video"]["source_url"]
    assert len(loaded["readout_json"]["scenes"]) == 3
    assert len(loaded["readout_json"]["cta_markers"]) == 1
    assert len(loaded["readout_json"]["segments"]["attention_gain_segments"]) > 0
    assert len(loaded["readout_json"]["segments"]["attention_loss_segments"]) > 0
    assert len(loaded["readout_json"]["segments"]["golden_scenes"]) > 0
    assert "dead_zones" in loaded["readout_json"]["segments"]
    assert isinstance(loaded["readout_json"]["segments"]["dead_zones"], list)
    assert len(loaded["readout_json"]["reward_proxy_peaks"]) > 0
    assert loaded["readout_json"]["product_rollups"] is not None
    assert loaded["compact_report"]["product_rollups"] is not None
    assert loaded["compact_report"]["annotation_summary"]["engaging_moment_count"] == 2
    assert loaded["compact_report"]["survey_summary"]["responses_count"] == 8
