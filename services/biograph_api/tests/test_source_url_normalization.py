from __future__ import annotations

from app.services_readout import _normalize_readout_source_url


def test_normalize_readout_source_url_handles_video_asset_proxy(monkeypatch):
    monkeypatch.setenv("API_PUBLIC_URL", "https://biograph-api.example.com")
    assert (
        _normalize_readout_source_url("/api/video-assets/demo.mp4")
        == "https://biograph-api.example.com/video-assets/demo.mp4"
    )


def test_normalize_readout_source_url_handles_public_video_asset_path(monkeypatch):
    monkeypatch.setenv("API_PUBLIC_URL", "https://biograph-api.example.com/")
    assert (
        _normalize_readout_source_url("/video-assets/demo.mp4")
        == "https://biograph-api.example.com/video-assets/demo.mp4"
    )


def test_normalize_readout_source_url_unwraps_hls_proxy():
    assert (
        _normalize_readout_source_url(
            "/api/video/hls-proxy?url=https%3A%2F%2Fcdn.example.com%2Fstream.m3u8"
        )
        == "https://cdn.example.com/stream.m3u8"
    )


def test_normalize_readout_source_url_leaves_absolute_url_unchanged():
    source_url = "https://cdn.example.com/video.mp4"
    assert _normalize_readout_source_url(source_url) == source_url
