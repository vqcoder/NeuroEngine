"""API test for /predict endpoint with patched inference backend."""

from __future__ import annotations

from pathlib import Path

from app.download_service import (
    _download_predict_video_with_yt_dlp,
    _extract_vimeo_video_id,
    _resolve_predict_video_source_from_html,
    _resolve_predict_video_source_from_vimeo_config,
    _resolve_predict_video_source_with_yt_dlp,
    _validate_predict_video_url,
)
from app.predict_service import PredictExecution
from app.schemas import PredictTracePoint


def test_predict_endpoint_returns_predicted_traces(client, monkeypatch):
    def fake_predict_from_video_with_backend(video_path: Path, model_artifact_path: Path):
        assert video_path.exists()
        assert str(model_artifact_path)
        return PredictExecution(
            predictions=[
                PredictTracePoint(t_sec=0.0, attention=42.0, blink_inhibition=0.7, dial=50.0),
                PredictTracePoint(t_sec=1.0, attention=45.0, blink_inhibition=0.75, dial=52.0),
            ],
            backend="ml_pipeline_artifact",
        )

    monkeypatch.setattr("app.routes_prediction.predict_from_video_with_backend", fake_predict_from_video_with_backend)

    response = client.post(
        "/predict",
        files={"file": ("sample.mp4", b"fake-video-bytes", "video/mp4")},
    )

    assert response.status_code == 200, response.text
    job = response.json()
    assert "job_id" in job

    # Background task runs synchronously in TestClient — poll the result immediately.
    result_response = client.get(f"/predict/{job['job_id']}")
    assert result_response.status_code == 200, result_response.text
    status = result_response.json()
    assert status["status"] == "done", f"Job not done: {status}"
    result = status["result"]
    assert "model_artifact" in result
    assert len(result["predictions"]) == 2
    assert result["predictions"][0]["attention"] == 42.0
    assert result["predictions"][0]["dopamine_score"] == result["predictions"][0]["reward_proxy"]
    assert result["prediction_backend"] == "ml_pipeline_artifact"
    assert result["resolved_video_url"] is None


def test_predict_endpoint_accepts_video_url(client, monkeypatch, tmp_path):
    downloaded_video = tmp_path / "downloaded.mp4"
    downloaded_video.write_bytes(b"fake-video-bytes")

    def fake_download_predict_video(video_url: str) -> tuple[Path, str]:
        assert video_url == "https://example.com/video.mp4"
        return downloaded_video, video_url

    def fake_predict_from_video_with_backend(video_path: Path, model_artifact_path: Path):
        assert video_path == downloaded_video
        assert str(model_artifact_path)
        return PredictExecution(
            predictions=[
                PredictTracePoint(t_sec=0.0, reward_proxy=55.0, blink_inhibition=0.6, dial=40.0),
            ],
            backend="ml_pipeline_artifact",
        )

    monkeypatch.setattr("app.routes_prediction._download_predict_video", fake_download_predict_video)
    monkeypatch.setattr("app.routes_prediction.predict_from_video_with_backend", fake_predict_from_video_with_backend)

    response = client.post(
        "/predict",
        data={"video_url": "https://example.com/video.mp4"},
    )

    assert response.status_code == 200, response.text
    job = response.json()
    assert "job_id" in job

    result_response = client.get(f"/predict/{job['job_id']}")
    assert result_response.status_code == 200, result_response.text
    status = result_response.json()
    assert status["status"] == "done", f"Job not done: {status}"
    result = status["result"]
    assert result["predictions"][0]["reward_proxy"] == 55.0
    assert result["predictions"][0]["dopamine_score"] == 55.0
    assert result["prediction_backend"] == "ml_pipeline_artifact"
    assert result["resolved_video_url"] == "https://example.com/video.mp4"
    assert not downloaded_video.exists()


def test_predict_endpoint_rejects_invalid_video_url_scheme(client):
    response = client.post(
        "/predict",
        data={"video_url": "ftp://example.com/video.mp4"},
    )

    assert response.status_code == 400, response.text
    assert "http or https" in response.json()["detail"]


def test_resolve_predict_video_source_from_html_prefers_meta_og_video():
    html = """
    <html>
      <head>
        <meta property="og:video" content="https://cdn.example.com/primary.mp4" />
      </head>
      <body>
        <video src="https://cdn.example.com/fallback.mp4"></video>
      </body>
    </html>
    """

    resolved = _resolve_predict_video_source_from_html(html, "https://example.com/ad/123")
    assert resolved == "https://cdn.example.com/primary.mp4"


def test_resolve_predict_video_source_from_html_supports_relative_video_source():
    html = """
    <html>
      <body>
        <video controls>
          <source src="/media/trailer/final-cut.mp4" type="video/mp4" />
        </video>
      </body>
    </html>
    """

    resolved = _resolve_predict_video_source_from_html(html, "https://example.com/videos/landing")
    assert resolved == "https://example.com/media/trailer/final-cut.mp4"


def test_resolve_predict_video_source_from_html_supports_json_ld_content_url():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "VideoObject",
          "name": "Sample",
          "contentUrl": "https://media.example.com/ads/spot.mp4"
        }
        </script>
      </head>
    </html>
    """

    resolved = _resolve_predict_video_source_from_html(html, "https://example.com/videos/sample")
    assert resolved == "https://media.example.com/ads/spot.mp4"


def test_resolve_predict_video_source_from_html_supports_escaped_mp4_urls():
    html = r"""
    <html>
      <body>
        <script>
          window.__PLAYER__ = {
            progressive_url: "https:\/\/vod.example.com\/path\/clip-1080.mp4?token=abc"
          };
        </script>
      </body>
    </html>
    """

    resolved = _resolve_predict_video_source_from_html(html, "https://example.com/watch")
    assert resolved is not None
    assert resolved.startswith("https://vod.example.com/path/clip-1080.mp4")


def test_validate_predict_video_url_normalizes_ispot_slug_with_encoded_whitespace():
    malformed = "https://www.ispot.tv/ad/ZSMK/vrbo-stop-searchingpush%20origin%20main"
    normalized = _validate_predict_video_url(malformed)
    assert normalized == "https://www.ispot.tv/ad/ZSMK/vrbo-stop-searchingpush"


def test_validate_predict_video_url_keeps_non_ispot_urls_unchanged():
    original = "https://example.com/video%20file.mp4"
    normalized = _validate_predict_video_url(original)
    assert normalized == original


def test_resolve_predict_video_source_with_yt_dlp_parses_first_http_candidate(monkeypatch):
    class FakeRunResult:
        returncode = 0
        stdout = "not-a-url\nhttps://cdn.example.com/video.mp4\nhttps://backup.example.com/video.webm\n"
        stderr = ""

    def fake_run(*_args, **_kwargs):
        return FakeRunResult()

    monkeypatch.setattr("app.download_service.subprocess.run", fake_run)

    resolved = _resolve_predict_video_source_with_yt_dlp("https://example.com/watch")
    assert resolved == "https://cdn.example.com/video.mp4"


def test_resolve_predict_video_source_with_yt_dlp_returns_none_when_binary_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("yt-dlp missing")

    monkeypatch.setattr("app.download_service.subprocess.run", fake_run)

    resolved = _resolve_predict_video_source_with_yt_dlp("https://example.com/watch")
    assert resolved is None


def test_extract_vimeo_video_id_supports_common_patterns():
    assert _extract_vimeo_video_id("https://vimeo.com/176228082") == "176228082"
    assert _extract_vimeo_video_id("https://player.vimeo.com/video/176228082") == "176228082"
    assert _extract_vimeo_video_id("https://vimeo.com/channels/staffpicks/176228082") == "176228082"
    assert _extract_vimeo_video_id("https://example.com/video/176228082") is None


def test_resolve_predict_video_source_from_vimeo_config_prefers_largest_progressive(monkeypatch):
    import json
    import httpx

    payload = {
        "request": {
            "files": {
                "progressive": [
                    {"url": "https://cdn.example.com/540.mp4", "width": 960, "height": 540},
                    {"url": "https://cdn.example.com/1080.mp4", "width": 1920, "height": 1080},
                ]
            }
        }
    }

    body = json.dumps(payload).encode("utf-8")

    fake_response = httpx.Response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        content=body,
    )

    class FakeClient:
        def get(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            return fake_response

    monkeypatch.setattr("app.download_service.get_sync_client", lambda: FakeClient())
    resolved = _resolve_predict_video_source_from_vimeo_config("https://vimeo.com/176228082")
    assert resolved == "https://cdn.example.com/1080.mp4"


def test_download_predict_video_with_yt_dlp_returns_downloaded_file(monkeypatch):
    class FakeRunResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **_kwargs):  # noqa: ANN001, ANN202
        output_index = args.index("-o") + 1
        output_template = args[output_index]
        output_path = output_template.replace("%(ext)s", "mp4")
        Path(output_path).write_bytes(b"fake-video-bytes")
        return FakeRunResult()

    monkeypatch.setattr("app.download_service.subprocess.run", fake_run)

    downloaded = _download_predict_video_with_yt_dlp("https://vimeo.com/176228082")
    assert downloaded is not None
    assert downloaded.exists()
    assert downloaded.stat().st_size > 0
    downloaded.unlink(missing_ok=True)


def test_download_predict_video_with_yt_dlp_returns_none_when_binary_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):  # noqa: ANN001, ANN202
        raise FileNotFoundError("yt-dlp missing")

    monkeypatch.setattr("app.download_service.subprocess.run", fake_run)

    downloaded = _download_predict_video_with_yt_dlp("https://vimeo.com/176228082")
    assert downloaded is None
