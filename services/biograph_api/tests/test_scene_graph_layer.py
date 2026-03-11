"""Scene graph persistence, CTA marker endpoints, and readout alignment tests."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scene_graph_fixture.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def test_scene_graph_endpoints_and_readout_alignment(client):
    fixture = _load_fixture()

    study_resp = client.post("/studies", json=fixture["study"])
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    video_payload = dict(fixture["video"])
    video_payload["study_id"] = study["id"]
    video_resp = client.post("/videos", json=video_payload)
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()
    assert video["variant_id"] == "variant-a"
    assert len(video["scenes"]) == 4
    assert len(video["cuts"]) == 8
    assert len(video["cta_markers"]) == 1

    graph_resp = client.get(f"/videos/{video['id']}/scene-graph", params={"variantId": "variant-a"})
    assert graph_resp.status_code == 200, graph_resp.text
    graph = graph_resp.json()
    assert graph["variant_id"] == "variant-a"
    assert len(graph["scenes"]) == 4
    assert len(graph["cuts"]) == 8
    assert len(graph["cta_markers"]) == 1
    assert graph["scenes"][0]["scene_id"] == "scene-1"
    assert graph["cuts"][3]["cut_id"] == "cut-4"
    assert graph["cta_markers"][0]["cta_id"] == "cta-main"
    assert graph["cta_markers"][0]["start_ms"] == 4300
    assert graph["cta_markers"][0]["end_ms"] == 5200

    cta_get_resp = client.get(f"/videos/{video['id']}/cta-markers", params={"variantId": "variant-a"})
    assert cta_get_resp.status_code == 200, cta_get_resp.text
    cta_payload = cta_get_resp.json()
    assert cta_payload["variant_id"] == "variant-a"
    assert cta_payload["cta_markers"][0]["cta_id"] == "cta-main"

    cta_update_resp = client.put(
        f"/videos/{video['id']}/cta-markers",
        params={"variantId": "variant-a"},
        json={
            "cta_markers": [
                {
                    "cta_id": "cta-main",
                    "start_ms": 4200,
                    "end_ms": 5400,
                    "label": "Primary CTA Updated",
                    "scene_id": "scene-2",
                    "cut_id": "cut-4",
                }
            ]
        },
    )
    assert cta_update_resp.status_code == 200, cta_update_resp.text
    updated = cta_update_resp.json()
    assert updated["cta_markers"][0]["start_ms"] == 4200
    assert updated["cta_markers"][0]["end_ms"] == 5400
    assert updated["cta_markers"][0]["label"] == "Primary CTA Updated"

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
    assert ingest_resp.json()["inserted"] == 1

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"sessionId": session["id"], "aggregate": "false"},
    )
    assert readout_resp.status_code == 200, readout_resp.text
    readout = readout_resp.json()
    assert len(readout["context"]["scenes"]) == 4
    assert len(readout["context"]["cuts"]) == 8
    assert len(readout["context"]["cta_markers"]) == 1
    assert readout["context"]["cta_markers"][0]["start_ms"] == 4200
    assert readout["context"]["cta_markers"][0]["end_ms"] == 5400

    attention_point = next(
        point
        for point in readout["traces"]["attention_score"]
        if point["video_time_ms"] == 4000
    )
    assert attention_point["scene_id"] == "scene-2"
    assert attention_point["cut_id"] == "cut-4"
    assert attention_point["cta_id"] == "cta-main"
