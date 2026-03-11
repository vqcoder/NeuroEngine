"""Asset routes – GitHub video upload helpers and video-asset proxy endpoints."""
# Convention: Use `def` for sync routes (standard DB ops via SQLAlchemy).
# Use `async def` only when the handler must `await` (streaming bodies, async HTTP).

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from time import monotonic
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .circuit_breaker import github_breaker
from .http_client import (
    TIMEOUT_GITHUB_API,
    TIMEOUT_GITHUB_UPLOAD,
    TIMEOUT_HEAD_CHECK,
    get_async_client,
    get_sync_client,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# GitHub upload constants
# ---------------------------------------------------------------------------
_GITHUB_API = "https://api.github.com"
_GITHUB_UPLOADS = "https://uploads.github.com"

_GITHUB_UPLOAD_MAX_ATTEMPTS = 3
_GITHUB_UPLOAD_RETRY_BASE_DELAY = 2.0  # seconds; doubles each attempt

# GitHub upload stats — shared via runtime_stats to avoid route cross-imports
from .runtime_stats import github_upload_stats_lock as _github_upload_stats_lock, github_upload_stats as _github_upload_stats

# ---------------------------------------------------------------------------
# Video-asset proxy constants / cache
# ---------------------------------------------------------------------------
_VIDEO_ASSET_FILENAME_RE = re.compile(r'^[\w-]+\.(mp4|webm|mov|m4v)$')
# Cache: (repo/tag) -> (expires_at, {name: id})
_VIDEO_ASSET_CACHE_TTL = 3600  # 1 hour
_VIDEO_ASSET_CACHE_MAX_SIZE = 500
# NOTE(Q17): Module-level mutable state — single-worker only.  Duplicate per
# worker under multi-process deployments; migrate to shared cache if needed.
_video_asset_id_cache: dict[str, tuple[float, dict[str, int]]] = {}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _github_upload_video(local_path: Path, source_url: str) -> Optional[str]:
    """Upload a video file to the GitHub Release video-assets tag and return the stable proxy URL.
    Retries up to 3x with exponential backoff. Returns None if not configured or all attempts fail."""
    import time as _time

    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    tag = os.getenv("GITHUB_RELEASE_TAG", "video-assets")
    if not token or not repo:
        return None

    with _github_upload_stats_lock:
        _github_upload_stats["attempts"] += 1
    try:
        if github_breaker.is_open:
            logger.warning("GitHub upload skipped — circuit breaker is open")
            with _github_upload_stats_lock:
                _github_upload_stats["failures"] += 1
            return None

        url_hash = __import__("hashlib").sha256(source_url.encode()).hexdigest()[:16]
        ext = local_path.suffix.lstrip(".") or "mp4"
        asset_name = f"predict-{url_hash}.{ext}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        # Get or create release
        client = get_sync_client()
        rel_resp = client.get(
            f"{_GITHUB_API}/repos/{repo}/releases/tags/{tag}",
            headers=headers,
            timeout=TIMEOUT_GITHUB_API,
        )
        if rel_resp.status_code == 200:
            release_id = rel_resp.json()["id"]
        else:
            import json as _json

            body = _json.dumps({"tag_name": tag, "name": "WatchLab Video Assets", "body": "Stable hosted videos."}).encode()
            create_resp = client.post(
                f"{_GITHUB_API}/repos/{repo}/releases",
                content=body,
                headers={**headers, "Content-Type": "application/json"},
                timeout=TIMEOUT_GITHUB_API,
            )
            create_resp.raise_for_status()
            release_id = create_resp.json()["id"]

        # Check if already uploaded — return immediately if so
        assets_resp = client.get(
            f"{_GITHUB_API}/repos/{repo}/releases/{release_id}/assets",
            headers=headers,
            timeout=TIMEOUT_GITHUB_API,
        )
        assets_resp.raise_for_status()
        assets = assets_resp.json()
        for asset in assets:
            if asset.get("name") == asset_name:
                proxy_url = _make_proxy_video_url(asset_name)
                if _verify_proxy_url_reachable(proxy_url):
                    return proxy_url
                # Asset exists on GitHub but proxy can't reach it — bust the cache and fall through
                cache_key = f"{repo}/{tag}"
                _video_asset_id_cache.pop(cache_key, None)

        # Upload with retry
        file_size = local_path.stat().st_size
        upload_url = f"{_GITHUB_UPLOADS}/repos/{repo}/releases/{release_id}/assets?name={quote(asset_name)}"
        last_exc: Optional[Exception] = None
        for attempt in range(_GITHUB_UPLOAD_MAX_ATTEMPTS):
            if attempt > 0:
                _time.sleep(_GITHUB_UPLOAD_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            try:
                with open(local_path, "rb") as fh:
                    upload_resp = client.post(
                        upload_url,
                        content=fh,
                        headers={
                            **headers,
                            "Content-Type": "video/mp4",
                            "Content-Length": str(file_size),
                        },
                        timeout=TIMEOUT_GITHUB_UPLOAD,
                    )
                upload_resp.raise_for_status()
                result = upload_resp.json()
                if result.get("browser_download_url"):
                    proxy_url = _make_proxy_video_url(asset_name)
                    # Bust the asset ID cache so the proxy can find the new asset immediately
                    cache_key = f"{repo}/{tag}"
                    _video_asset_id_cache.pop(cache_key, None)
                    github_breaker._record_success()
                    with _github_upload_stats_lock:
                        _github_upload_stats["successes"] += 1
                    return proxy_url
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning(
                    "GitHub video upload attempt failed",
                    extra={"attempt": attempt + 1, "asset": asset_name, "error": str(exc), "http_code": exc.response.status_code},
                )
                if exc.response.status_code in (429, 403):
                    retry_after_raw = exc.response.headers.get("Retry-After")
                    try:
                        rate_limit_delay = float(retry_after_raw) if retry_after_raw else _GITHUB_UPLOAD_RETRY_BASE_DELAY * (2 ** attempt)
                    except (TypeError, ValueError):
                        rate_limit_delay = _GITHUB_UPLOAD_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "GitHub rate-limited — sleeping before retry",
                        extra={"delay_s": rate_limit_delay, "attempt": attempt + 1},
                    )
                    _time.sleep(rate_limit_delay)
            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "GitHub video upload attempt failed",
                    extra={"attempt": attempt + 1, "asset": asset_name, "error": str(exc)},
                )
        logger.error(
            "GitHub video upload failed after all attempts",
            extra={"asset": asset_name, "error": str(last_exc)},
        )
        github_breaker._record_failure()
        with _github_upload_stats_lock:
            _github_upload_stats["failures"] += 1
        return None
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("GitHub video upload failed", extra={"error": str(exc)})
        with _github_upload_stats_lock:
            _github_upload_stats["failures"] += 1
        return None


def _verify_proxy_url_reachable(proxy_url: str) -> bool:
    """HEAD-check the proxy URL to confirm the asset is accessible before storing it."""
    try:
        client = get_sync_client()
        resp = client.head(proxy_url, timeout=TIMEOUT_HEAD_CHECK)
        return resp.status_code < 400
    except (httpx.HTTPError, OSError):
        logger.debug("Proxy URL reachability check failed for %s", proxy_url, exc_info=True)
        return False


def _make_proxy_video_url(filename: str) -> str:
    """Build the public proxy URL for a GitHub release video asset."""
    base = os.getenv("API_PUBLIC_URL", "").rstrip("/")
    if not base:
        base = "https://biograph-api-production.up.railway.app"
    return f"{base}/video-assets/{quote(filename)}"


async def _get_github_asset_id(repo: str, tag: str, filename: str, token: str) -> Optional[int]:
    """Return the GitHub asset ID for a given filename in a release, using a TTL-bounded cache."""
    cache_key = f"{repo}/{tag}"
    now = monotonic()
    cached = _video_asset_id_cache.get(cache_key)
    if cached is None or now >= cached[0] or filename not in cached[1]:
        api_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        client = get_async_client()
        rel_resp = await client.get(
            f"{_GITHUB_API}/repos/{repo}/releases/tags/{tag}",
            headers=api_headers,
            timeout=TIMEOUT_GITHUB_API,
        )
        if rel_resp.status_code != 200:
            return None
        release_id = rel_resp.json()["id"]
        assets_resp = await client.get(
            f"{_GITHUB_API}/repos/{repo}/releases/{release_id}/assets",
            headers=api_headers,
            timeout=TIMEOUT_GITHUB_API,
        )
        if assets_resp.status_code != 200:
            return None
        mapping = {a["name"]: a["id"] for a in assets_resp.json()}
        _video_asset_id_cache[cache_key] = (now + _VIDEO_ASSET_CACHE_TTL, mapping)
        # Evict expired entries, then oldest if still over capacity
        expired = [k for k, (exp, _) in _video_asset_id_cache.items() if now >= exp and k != cache_key]
        for k in expired:
            _video_asset_id_cache.pop(k, None)
        if len(_video_asset_id_cache) > _VIDEO_ASSET_CACHE_MAX_SIZE:
            sorted_keys = sorted(
                (k for k in _video_asset_id_cache if k != cache_key),
                key=lambda k: _video_asset_id_cache[k][0],
            )
            excess = len(_video_asset_id_cache) - _VIDEO_ASSET_CACHE_MAX_SIZE
            for k in sorted_keys[:excess]:
                _video_asset_id_cache.pop(k, None)
    return _video_asset_id_cache[cache_key][1].get(filename)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.head("/video-assets/{filename}")
async def proxy_video_asset_head(filename: str, request: Request):
    """HEAD support for video asset proxy — lets browsers verify range support without downloading."""
    if not _VIDEO_ASSET_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    tag = os.getenv("GITHUB_RELEASE_TAG", "video-assets")
    if not token or not repo:
        raise HTTPException(status_code=503, detail="Video proxy not configured")
    asset_id = await _get_github_asset_id(repo, tag, filename, token)
    if asset_id is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return Response(
        status_code=200,
        headers={
            "Content-Type": "video/mp4",
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/video-assets/{filename}")
async def proxy_video_asset(filename: str, request: Request) -> StreamingResponse:
    """Proxy GitHub Release video assets via the GitHub API (handles private repo auth)."""
    if not _VIDEO_ASSET_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    tag = os.getenv("GITHUB_RELEASE_TAG", "video-assets")
    if not token or not repo:
        raise HTTPException(status_code=503, detail="Video proxy not configured")

    asset_id = await _get_github_asset_id(repo, tag, filename, token)
    if asset_id is None:
        raise HTTPException(status_code=404, detail="Video asset not found")

    # Use the GitHub API asset download endpoint — returns 302 to a self-signed CDN URL
    api_asset_url = f"{_GITHUB_API}/repos/{repo}/releases/assets/{asset_id}"
    api_headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/octet-stream",
        "User-Agent": "biograph-api-proxy/1.0",
    }
    range_header = request.headers.get("range")
    if range_header:
        api_headers["Range"] = range_header

    try:
        # Step 1: resolve the signed CDN URL from the GitHub API redirect
        async_client = get_async_client()
        redirect_resp = await async_client.get(
            api_asset_url,
            headers=api_headers,
            follow_redirects=False,
            timeout=TIMEOUT_GITHUB_API,
        )
        if redirect_resp.status_code not in (301, 302, 303, 307, 308):
            raise HTTPException(status_code=502, detail=f"Expected redirect, got {redirect_resp.status_code}")
        cdn_url = redirect_resp.headers.get("location")
        if not cdn_url:
            raise HTTPException(status_code=502, detail="No redirect location from GitHub")

        # Step 2: open a streaming connection to the CDN — do NOT buffer the full body
        cdn_req_headers: dict[str, str] = {}
        if range_header:
            cdn_req_headers["Range"] = range_header

        cdn_client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(connect=10, read=300, write=10, pool=5))
        upstream = await cdn_client.send(
            cdn_client.build_request("GET", cdn_url, headers=cdn_req_headers),
            stream=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Video proxy error", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail="Video proxy error") from exc

    if upstream.status_code not in (200, 206):
        await upstream.aclose()
        await cdn_client.aclose()
        raise HTTPException(status_code=502, detail="Upstream error fetching video")

    response_headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }
    if upstream.headers.get("Content-Length"):
        response_headers["Content-Length"] = upstream.headers["Content-Length"]
    if upstream.headers.get("Content-Range"):
        response_headers["Content-Range"] = upstream.headers["Content-Range"]

    async def _stream_and_close():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=256 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await cdn_client.aclose()

    return StreamingResponse(
        _stream_and_close(),
        status_code=upstream.status_code,
        headers=response_headers,
    )
