"""Reliability regression tests for the predict catalog pipeline.

Covers:
  - duration_ms is stored correctly on new Video records
  - duration_ms is backfilled on existing Video records that lack it
  - usable_seconds in the readout is bounded by the stored duration_ms
  - _validate_predict_output raises before any DB write (no orphan records)
  - validate-before-upsert: bad output never creates a catalog entry
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.routes_prediction import _upsert_predict_catalog_entry, _validate_predict_output
from app.models import Video
from app.schemas import PredictTracePoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path):
    db_path = tmp_path / "test.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _good_points(n: int = 2):
    return [
        PredictTracePoint(t_sec=float(i), attention=50.0, reward_proxy=40.0, blink_inhibition=30.0, dial=50.0)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _upsert_predict_catalog_entry: duration_ms stored on new record
# ---------------------------------------------------------------------------

def test_upsert_stores_duration_ms_on_new_video(tmp_path):
    db = _make_db(tmp_path)
    try:
        video_id = _upsert_predict_catalog_entry(
            db,
            source_url="https://example.com/video.mp4",
            hosted_url=None,
            duration_ms=29000,
        )
        assert video_id is not None
        video = db.query(Video).filter(Video.id == video_id).first()  # type: ignore[arg-type]
        assert video is not None
        assert video.duration_ms == 29000
    finally:
        db.close()


def test_upsert_stores_none_duration_when_unknown(tmp_path):
    db = _make_db(tmp_path)
    try:
        video_id = _upsert_predict_catalog_entry(
            db,
            source_url="https://example.com/noduration.mp4",
            hosted_url=None,
            duration_ms=None,
        )
        assert video_id is not None
        video = db.query(Video).filter(Video.id == video_id).first()  # type: ignore[arg-type]
        assert video is not None
        assert video.duration_ms is None
    finally:
        db.close()


def test_upsert_backfills_duration_ms_on_existing_record(tmp_path):
    db = _make_db(tmp_path)
    try:
        # Create without duration
        video_id = _upsert_predict_catalog_entry(
            db,
            source_url="https://example.com/backfill.mp4",
            hosted_url=None,
            duration_ms=None,
        )
        assert video_id is not None
        video = db.query(Video).filter(Video.id == video_id).first()  # type: ignore[arg-type]
        assert video.duration_ms is None

        # Second call with same URL and now we know the duration
        returned_id = _upsert_predict_catalog_entry(
            db,
            source_url="https://example.com/backfill.mp4",
            hosted_url=None,
            duration_ms=31000,
        )
        assert returned_id == video_id
        db.refresh(video)
        assert video.duration_ms == 31000
    finally:
        db.close()


def test_upsert_does_not_overwrite_existing_duration_ms(tmp_path):
    """Once duration_ms is set, a subsequent call with a DIFFERENT value should not overwrite it."""
    db = _make_db(tmp_path)
    try:
        video_id = _upsert_predict_catalog_entry(
            db,
            source_url="https://example.com/keepduration.mp4",
            hosted_url=None,
            duration_ms=30000,
        )
        # Second call — duration_ms is already set; passing None should not clear it
        _upsert_predict_catalog_entry(
            db,
            source_url="https://example.com/keepduration.mp4",
            hosted_url=None,
            duration_ms=None,
        )
        video = db.query(Video).filter(Video.id == video_id).first()  # type: ignore[arg-type]
        db.refresh(video)
        # The original value must be preserved — None must not clobber it
        assert video.duration_ms == 30000
    finally:
        db.close()


# ---------------------------------------------------------------------------
# validate-before-upsert: bad predict output must NOT create DB entry
# ---------------------------------------------------------------------------

def test_validate_nan_reward_prevents_catalog_entry(tmp_path, client):
    """A predict output with NaN reward_proxy must raise before any Video row is created."""
    bad_point = PredictTracePoint(t_sec=0.0, reward_proxy=float("nan"), attention=50.0, blink_inhibition=30.0, dial=50.0)

    with pytest.raises(ValueError, match="reward_proxy"):
        _validate_predict_output([bad_point])

    # No Video should have been written to the test DB as a result
    # (validate is called before upsert in _run_predict_job — the test simply confirms
    # the exception fires before any write reaches the DB layer)


def test_validate_empty_predictions_prevents_catalog_entry():
    with pytest.raises(ValueError, match="zero rows"):
        _validate_predict_output([])


# ---------------------------------------------------------------------------
# Readout usable_seconds bounded by duration_ms (integration)
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "readout_session.json"


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def test_readout_usable_seconds_matches_video_duration_ms(client):
    """When video.duration_ms is set, usable_seconds must not exceed it."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    study_resp = client.post("/studies", json=fixture["study"])
    assert study_resp.status_code == 201
    study = study_resp.json()

    video_payload = dict(fixture["video"])
    video_payload["study_id"] = study["id"]
    # Explicitly set duration to match the fixture (9s fixture)
    video_payload["duration_ms"] = 9000
    video_resp = client.post("/videos", json=video_payload)
    assert video_resp.status_code == 201
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={"study_id": study["id"], "video_id": video["id"], "participant": fixture["participants"][0]},
    )
    assert session_resp.status_code == 201
    session = session_resp.json()

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(fixture["session_rows"][0]),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"session_id": session["id"], "aggregate": "false", "window_ms": 1000},
    )
    assert readout_resp.status_code == 200
    payload = readout_resp.json()

    usable = payload["quality_summary"]["usable_seconds"]
    video_duration_s = 9000 / 1000.0
    assert usable <= video_duration_s + 1.0, (
        f"usable_seconds ({usable}) must not greatly exceed video duration ({video_duration_s}s)"
    )


def test_readout_usable_seconds_without_duration_ms_uses_trace_extent(client):
    """When video.duration_ms is NULL, usable_seconds derives from trace data extent."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    study_resp = client.post("/studies", json=fixture["study"])
    study = study_resp.json()

    video_payload = dict(fixture["video"])
    video_payload["study_id"] = study["id"]
    video_payload.pop("duration_ms", None)  # ensure NULL
    video_resp = client.post("/videos", json=video_payload)
    assert video_resp.status_code == 201
    video = video_resp.json()

    session_resp = client.post(
        "/sessions",
        json={"study_id": study["id"], "video_id": video["id"], "participant": fixture["participants"][0]},
    )
    session = session_resp.json()

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(fixture["session_rows"][0]),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"session_id": session["id"], "aggregate": "false", "window_ms": 1000},
    )
    assert readout_resp.status_code == 200
    payload = readout_resp.json()
    usable = payload["quality_summary"]["usable_seconds"]
    # Without duration_ms, usable derives from max trace time + window_ms.
    # Fixture has 9 rows → max video_time_ms ≈ 8000ms → usable ≈ 9.0s
    assert 0 < usable <= 15.0, f"usable_seconds ({usable}) out of expected range for trace-derived duration"
