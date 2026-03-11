"""Provider-selection tests for timeline ASR/OCR extraction hooks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.config import get_settings
from app.timeline_feature_store import _extract_text_overlay_segments, _extract_transcript_segments


def test_extract_transcript_segments_uses_whisper_provider_when_configured(monkeypatch):
    monkeypatch.setenv("TIMELINE_ASR_PROVIDER", "whisper_cli")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.timeline_feature_store._extract_transcript_with_whisper_cli",
        lambda source_path, duration_ms: [
            {
                "segment_type": "speech_token",
                "start_ms": 100,
                "end_ms": 300,
                "label": "hello",
                "details": {"source": "whisper_cli_word"},
            }
        ],
    )

    video = SimpleNamespace(video_metadata={})
    segments, available, provider = _extract_transcript_segments(
        video=video,
        source_path=Path("/tmp/fake.mp4"),
        duration_ms=2000,
    )
    assert available is True
    assert provider == "whisper_cli"
    assert segments[0]["segment_type"] == "speech_token"
    assert segments[0]["label"] == "hello"

    get_settings.cache_clear()


def test_extract_text_overlay_segments_uses_tesseract_provider_when_configured(monkeypatch):
    monkeypatch.setenv("TIMELINE_OCR_PROVIDER", "tesseract_cli")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.timeline_feature_store._extract_text_overlays_with_tesseract_cli",
        lambda source_path, duration_ms: [
            {
                "segment_type": "text_overlay",
                "start_ms": 0,
                "end_ms": 900,
                "label": "Buy now",
                "details": {"source": "tesseract_cli"},
            }
        ],
    )

    video = SimpleNamespace(video_metadata={})
    segments, available, provider = _extract_text_overlay_segments(
        video=video,
        source_path=Path("/tmp/fake.mp4"),
        duration_ms=2000,
    )
    assert available is True
    assert provider == "tesseract_cli"
    assert segments[0]["segment_type"] == "text_overlay"
    assert segments[0]["label"] == "Buy now"

    get_settings.cache_clear()


def test_metadata_transcript_precedence_over_provider(monkeypatch):
    monkeypatch.setenv("TIMELINE_ASR_PROVIDER", "whisper_cli")
    get_settings.cache_clear()

    video = SimpleNamespace(video_metadata={"transcript": "metadata transcript"})
    segments, available, provider = _extract_transcript_segments(
        video=video,
        source_path=Path("/tmp/fake.mp4"),
        duration_ms=2000,
    )
    assert available is True
    assert provider == "metadata_transcript"
    assert segments[0]["segment_type"] == "speech_transcript"

    get_settings.cache_clear()

