"""Shared HTTP client instances with centralized timeout and retry configuration.

Provides:
- ``get_sync_client()`` — returns a module-level ``httpx.Client`` for use in
  sync functions that run in the FastAPI threadpool (BackgroundTasks, sync routes).
- ``get_async_client()`` — returns a module-level ``httpx.AsyncClient`` for use
  in async route handlers.
- ``close_sync_client()`` / ``close_async_client()`` — cleanup helpers called
  from the FastAPI lifespan handler.
- ``check_url_reachable()`` — shared HEAD-check helper used by services.py
  and services_readout.py.

All clients use connection pooling and consistent User-Agent headers.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Residential proxy for outbound HTTP requests (video downloads).
# Same env var used by yt-dlp in download_service.py for consistency.
_HTTP_PROXY: Optional[str] = os.getenv("YTDLP_PROXY", "").strip() or None

# ---------------------------------------------------------------------------
# Timeout presets — named constants replace magic numbers scattered across
# urlopen(timeout=...) call sites.
# ---------------------------------------------------------------------------

TIMEOUT_DEFAULT = httpx.Timeout(connect=10, read=30, write=10, pool=5)
TIMEOUT_GITHUB_API = httpx.Timeout(connect=10, read=15, write=10, pool=5)
TIMEOUT_GITHUB_UPLOAD = httpx.Timeout(connect=10, read=180, write=180, pool=5)
TIMEOUT_HEAD_CHECK = httpx.Timeout(connect=5, read=5, write=5, pool=5)
TIMEOUT_PREDICT_DOWNLOAD = httpx.Timeout(connect=10, read=120, write=10, pool=5)
TIMEOUT_TIMELINE_DOWNLOAD = httpx.Timeout(connect=10, read=30, write=10, pool=5)

_USER_AGENT = "biograph_api/0.1"

# ---------------------------------------------------------------------------
# Connection pool limits
# ---------------------------------------------------------------------------
_POOL_LIMITS = httpx.Limits(
    max_connections=40,
    max_keepalive_connections=10,
    keepalive_expiry=30,
)

# ---------------------------------------------------------------------------
# Lazy singleton clients
# ---------------------------------------------------------------------------
_sync_client: httpx.Client | None = None
_async_client: httpx.AsyncClient | None = None


def get_sync_client() -> httpx.Client:
    """Return (or lazily create) the shared sync httpx.Client.

    Thread-safe: ``httpx.Client`` is safe for concurrent use from multiple
    threads in the FastAPI threadpool.  Routes through YTDLP_PROXY when set.
    """
    global _sync_client
    if _sync_client is None or _sync_client.is_closed:
        kwargs: dict = dict(
            timeout=TIMEOUT_DEFAULT,
            limits=_POOL_LIMITS,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if _HTTP_PROXY:
            kwargs["proxy"] = _HTTP_PROXY
            logger.info("Sync HTTP client using proxy: %s", _HTTP_PROXY.split("@")[-1])
        _sync_client = httpx.Client(**kwargs)
    return _sync_client


def get_async_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared async httpx.AsyncClient."""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        kwargs: dict = dict(
            timeout=TIMEOUT_DEFAULT,
            limits=_POOL_LIMITS,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if _HTTP_PROXY:
            kwargs["proxy"] = _HTTP_PROXY
            logger.info("Async HTTP client using proxy: %s", _HTTP_PROXY.split("@")[-1])
        _async_client = httpx.AsyncClient(**kwargs)
    return _async_client


def close_sync_client() -> None:
    """Close the shared sync client. Called during application shutdown."""
    global _sync_client
    if _sync_client is not None and not _sync_client.is_closed:
        _sync_client.close()
        _sync_client = None


async def close_async_client() -> None:
    """Close the shared async client. Called during application shutdown."""
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None


# ---------------------------------------------------------------------------
# Shared HEAD-check helper (deduplicates services.py + services_readout.py)
# ---------------------------------------------------------------------------


def check_url_reachable(source_url: Optional[str]) -> Optional[bool]:
    """HEAD-check *source_url* with a short timeout.

    Returns ``True`` if the URL responds with status < 400, ``False`` on
    any error, or ``None`` if the URL is absent / not HTTP(S).
    """
    if not source_url:
        return None
    if not source_url.startswith(("http://", "https://")):
        return None
    try:
        client = get_sync_client()
        resp = client.head(source_url, timeout=TIMEOUT_HEAD_CHECK)
        return resp.status_code < 400
    except (httpx.HTTPError, OSError):
        logger.debug(
            "Source URL reachability check failed for %s", source_url, exc_info=True
        )
        return False
