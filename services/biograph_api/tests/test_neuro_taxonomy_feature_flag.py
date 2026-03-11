"""Feature-flag coverage for neuro taxonomy/product rollup composition."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.schemas import ReadoutPayload


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "readout_session.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def test_readout_omits_neuro_taxonomy_when_feature_flag_disabled(client, monkeypatch) -> None:
    monkeypatch.setenv("NEURO_SCORE_TAXONOMY_ENABLED", "false")
    get_settings.cache_clear()
    try:
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
                "participant": fixture["participants"][0],
            },
        )
        assert session_resp.status_code == 201, session_resp.text
        session = session_resp.json()

        ingest_resp = client.post(
            f"/sessions/{session['id']}/trace",
            content=_jsonl_rows(fixture["session_rows"][0]),
            headers={"Content-Type": "application/x-ndjson"},
        )
        assert ingest_resp.status_code == 200, ingest_resp.text

        readout_resp = client.get(
            f"/videos/{video['id']}/readout",
            params={"aggregate": "true", "window_ms": 1000},
        )
        assert readout_resp.status_code == 200, readout_resp.text
        payload = readout_resp.json()
        ReadoutPayload.model_validate(payload)

        assert payload["neuro_scores"] is None
        assert payload.get("product_rollups") is None
        assert payload.get("legacy_score_adapters") == []
    finally:
        get_settings.cache_clear()
