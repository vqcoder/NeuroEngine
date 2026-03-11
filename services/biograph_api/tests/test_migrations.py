"""Migration tests for passive measurement model schema updates."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings


def _build_alembic_config() -> Config:
    service_root = Path(__file__).resolve().parents[1]
    config = Config(str(service_root / "alembic.ini"))
    config.set_main_option("script_location", str(service_root / "alembic"))
    return config


def test_alembic_head_includes_passive_measurement_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_schema.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    config = _build_alembic_config()
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    tables = set(inspector.get_table_names())
    assert "trace_points" in tables
    assert "session_annotations" in tables
    assert "session_playback_events" in tables
    assert "video_scenes" in tables
    assert "video_cuts" in tables
    assert "video_cta_markers" in tables
    assert "video_timeline_analyses" in tables
    assert "video_timeline_segments" in tables
    assert "video_feature_tracks" in tables
    assert "incrementality_experiment_results" in tables
    assert "session_capture_archives" in tables
    assert "session_capture_ingest_events" in tables
    assert "frontend_diagnostic_events" in tables

    trace_columns = {column["name"] for column in inspector.get_columns("trace_points")}
    assert "video_time_ms" in trace_columns
    assert "reward_proxy" in trace_columns
    assert "rolling_blink_rate" in trace_columns
    assert "blink_inhibition_score" in trace_columns
    assert "gaze_on_screen_proxy" in trace_columns
    assert "quality_confidence" in trace_columns
    assert "scene_id" in trace_columns
    assert "cut_id" in trace_columns
    assert "cta_id" in trace_columns

    annotation_columns = {
        column["name"] for column in inspector.get_columns("session_annotations")
    }
    assert "scene_id" in annotation_columns
    assert "cut_id" in annotation_columns
    assert "cta_id" in annotation_columns

    playback_columns = {
        column["name"] for column in inspector.get_columns("session_playback_events")
    }
    assert "session_id" in playback_columns
    assert "video_id" in playback_columns
    assert "event_type" in playback_columns
    assert "video_time_ms" in playback_columns
    assert "wall_time_ms" in playback_columns
    assert "client_monotonic_ms" in playback_columns
    assert "scene_id" in playback_columns
    assert "cut_id" in playback_columns
    assert "cta_id" in playback_columns

    scene_columns = {column["name"] for column in inspector.get_columns("video_scenes")}
    assert "video_id" in scene_columns
    assert "variant_id" in scene_columns
    assert "scene_id" in scene_columns
    assert "start_ms" in scene_columns
    assert "end_ms" in scene_columns

    cut_columns = {column["name"] for column in inspector.get_columns("video_cuts")}
    assert "video_id" in cut_columns
    assert "variant_id" in cut_columns
    assert "cut_id" in cut_columns
    assert "video_time_ms" in cut_columns

    cta_columns = {column["name"] for column in inspector.get_columns("video_cta_markers")}
    assert "video_id" in cta_columns
    assert "variant_id" in cta_columns
    assert "cta_id" in cta_columns
    assert "start_ms" in cta_columns
    assert "end_ms" in cta_columns

    timeline_analysis_columns = {
        column["name"] for column in inspector.get_columns("video_timeline_analyses")
    }
    assert "video_id" in timeline_analysis_columns
    assert "asset_id" in timeline_analysis_columns
    assert "analysis_version" in timeline_analysis_columns
    assert "asset_fingerprint" in timeline_analysis_columns
    assert "status" in timeline_analysis_columns
    assert "metadata" in timeline_analysis_columns

    timeline_segment_columns = {
        column["name"] for column in inspector.get_columns("video_timeline_segments")
    }
    assert "analysis_id" in timeline_segment_columns
    assert "asset_id" in timeline_segment_columns
    assert "segment_type" in timeline_segment_columns
    assert "start_ms" in timeline_segment_columns
    assert "end_ms" in timeline_segment_columns

    feature_track_columns = {
        column["name"] for column in inspector.get_columns("video_feature_tracks")
    }
    assert "analysis_id" in feature_track_columns
    assert "asset_id" in feature_track_columns
    assert "track_name" in feature_track_columns
    assert "start_ms" in feature_track_columns
    assert "end_ms" in feature_track_columns

    incrementality_columns = {
        column["name"] for column in inspector.get_columns("incrementality_experiment_results")
    }
    assert "experiment_id" in incrementality_columns
    assert "source" in incrementality_columns
    assert "measured_incremental_lift_pct" in incrementality_columns
    assert "measured_iroas" in incrementality_columns
    assert "predicted_incremental_lift_pct" in incrementality_columns
    assert "predicted_iroas" in incrementality_columns
    assert "completed_at" in incrementality_columns
    assert "calibration_applied_at" in incrementality_columns
    assert "calibration_run_id" in incrementality_columns

    capture_columns = {
        column["name"] for column in inspector.get_columns("session_capture_archives")
    }
    assert "session_id" in capture_columns
    assert "video_id" in capture_columns
    assert "frame_count" in capture_columns
    assert "frame_pointer_count" in capture_columns
    assert "uncompressed_bytes" in capture_columns
    assert "compressed_bytes" in capture_columns
    assert "payload_sha256" in capture_columns
    assert "payload_gzip" in capture_columns
    assert "encryption_mode" in capture_columns
    assert "encryption_key_id" in capture_columns

    capture_event_columns = {
        column["name"] for column in inspector.get_columns("session_capture_ingest_events")
    }
    assert "session_id" in capture_event_columns
    assert "video_id" in capture_event_columns
    assert "outcome" in capture_event_columns
    assert "status_code" in capture_event_columns
    assert "error_code" in capture_event_columns
    assert "frame_count" in capture_event_columns
    assert "frame_pointer_count" in capture_event_columns
    assert "payload_bytes" in capture_event_columns

    frontend_event_columns = {
        column["name"] for column in inspector.get_columns("frontend_diagnostic_events")
    }
    assert "surface" in frontend_event_columns
    assert "page" in frontend_event_columns
    assert "route" in frontend_event_columns
    assert "severity" in frontend_event_columns
    assert "event_type" in frontend_event_columns
    assert "error_code" in frontend_event_columns
    assert "message" in frontend_event_columns
    assert "context" in frontend_event_columns
    assert "session_id" in frontend_event_columns
    assert "video_id" in frontend_event_columns
    assert "study_id" in frontend_event_columns

    get_settings.cache_clear()
