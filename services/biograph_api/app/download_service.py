"""Video download, resolution, and validation logic for the prediction pipeline.

Extracted from routes_prediction.py to decouple download orchestration from HTTP
route handling.  Functions raise domain exceptions (ValidationError, etc.) instead
of ``fastapi.HTTPException`` so they can be reused outside the web layer.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from json import JSONDecodeError, dumps, loads
from pathlib import Path
from threading import Lock
from typing import Optional
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

import httpx
from fastapi import UploadFile

from .config import get_settings
from .domain_exceptions import UnprocessableError, ValidationError
from .http_client import TIMEOUT_PREDICT_DOWNLOAD, get_sync_client

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Prediction constants
# ---------------------------------------------------------------------------

_PREDICT_DOWNLOAD_TIMEOUT_SECONDS = 120
_PREDICT_DOWNLOAD_CHUNK_SIZE = 1024 * 1024

# YouTube cookies — written once from YOUTUBE_COOKIES_NETSCAPE env var
_YOUTUBE_COOKIES_PATH = "/tmp/yt-cookies.txt"
_youtube_cookies_lock = Lock()
_youtube_cookies_ready: Optional[bool] = None  # None=unchecked, True=ready, False=not configured

# Residential proxy — set YTDLP_PROXY to route yt-dlp through a residential proxy.
# Accepts any protocol yt-dlp supports: socks5://host:port, http://user:pass@host:port, etc.
_YTDLP_PROXY: Optional[str] = os.getenv("YTDLP_PROXY", "").strip() or None


def _ensure_youtube_cookies() -> Optional[str]:
    """Write YOUTUBE_COOKIES_NETSCAPE env var to a Netscape cookies file on first call.
    Returns the path to the cookies file, or None if the env var is not set."""
    global _youtube_cookies_ready
    with _youtube_cookies_lock:
        if _youtube_cookies_ready is True:
            return _YOUTUBE_COOKIES_PATH
        if _youtube_cookies_ready is False:
            return None
        content = os.getenv("YOUTUBE_COOKIES_NETSCAPE", "").strip()
        if not content:
            _youtube_cookies_ready = False
            return None
        try:
            with open(_YOUTUBE_COOKIES_PATH, "w") as _f:
                _f.write(content)
                if not content.endswith("\n"):
                    _f.write("\n")
            _youtube_cookies_ready = True
            logger.info("YouTube cookies written to %s", _YOUTUBE_COOKIES_PATH)
            return _YOUTUBE_COOKIES_PATH
        except Exception as _exc:
            logger.warning("Failed to write YouTube cookies file: %s", _exc)
            _youtube_cookies_ready = False
            return None


def check_youtube_download_readiness() -> dict:
    """Return a diagnostic dict describing cookie + proxy readiness for YouTube downloads.
    Used by the /health endpoint to surface misconfigurations early."""
    cookies_ok = _ensure_youtube_cookies() is not None
    proxy_ok = _YTDLP_PROXY is not None
    status = "ok" if (cookies_ok and proxy_ok) else "degraded"
    if not cookies_ok and not proxy_ok:
        status = "not_configured"
    detail: dict = {
        "status": status,
        "cookies_configured": cookies_ok,
        "proxy_configured": proxy_ok,
    }
    if proxy_ok and _YTDLP_PROXY:
        # Reveal host:port only (mask credentials)
        from urllib.parse import urlparse as _up
        _parsed = _up(_YTDLP_PROXY)
        detail["proxy_host"] = _parsed.hostname or "unknown"
        detail["proxy_port"] = _parsed.port
    return detail


_PREDICT_DOWNLOAD_MAX_BYTES = max(int(os.getenv("PREDICT_DOWNLOAD_MAX_BYTES", "262144000")), 1)
_PREDICT_HTML_MAX_BYTES = max(int(os.getenv("PREDICT_HTML_MAX_BYTES", "5242880")), 1024)
_PREDICT_YTDLP_TIMEOUT_SECONDS = max(int(os.getenv("PREDICT_YTDLP_TIMEOUT_SECONDS", "25")), 5)

_PREDICT_META_VIDEO_KEYS = {
    "og:video",
    "og:video:url",
    "og:video:secure_url",
    "twitter:player:stream",
    "twitter:video",
    "twitter:video:src",
    "video_src",
}

_PREDICT_VIDEO_URL_KEYS = {"contenturl", "url", "embedurl", "streamurl", "sourceurl"}

_PREDICT_CONTENT_TYPE_TO_SUFFIX = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
_PREDICT_MEDIA_PATH_PATTERN = re.compile(r"\.(?:mp4|mov|m4v|webm|m3u8|mpd)(?:$|[/?#])", re.IGNORECASE)
_PREDICT_VIMEO_CONFIG_URL_PATTERN = re.compile(
    r"https://player\.vimeo\.com/video/\d+/config[^\"'<\s]*",
    re.IGNORECASE,
)
_PREDICT_VIMEO_CONFIG_CAPTURE_PATTERNS = (
    re.compile(r'"config_url"\s*:\s*"([^"]+)"', re.IGNORECASE),
    re.compile(r"data-config-url=['\"]([^'\"]+)['\"]", re.IGNORECASE),
)
_PREDICT_VIMEO_ID_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:player\.)?vimeo\.com/(?:video/)?(?:.*?/)?(\d+)(?:$|[/?#])",
    re.IGNORECASE,
)

_PREDICT_MIN_FREE_DISK_BYTES = 500 * 1024 * 1024  # 500 MB


class _YouTubeRateLimitError(RuntimeError):
    """Raised when yt-dlp is rate-limited (HTTP 429) by YouTube."""


# ---------------------------------------------------------------------------
# _PredictVideoSourceParser
# ---------------------------------------------------------------------------


class _PredictVideoSourceParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._candidates: list[str] = []
        self._capture_json_ld = False
        self._json_ld_buffer: list[str] = []

    @property
    def candidates(self) -> list[str]:
        return self._candidates

    def _add_candidate(self, raw_url: str | None) -> None:
        if raw_url is None:
            return
        candidate = raw_url.strip()
        if not candidate:
            return
        resolved = urljoin(self._base_url, candidate)
        parsed = urlparse(resolved)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            self._candidates.append(resolved)

    def _extract_from_json_ld(self, value) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.lower() in _PREDICT_VIDEO_URL_KEYS and isinstance(nested, str):
                    self._add_candidate(nested)
                self._extract_from_json_ld(nested)
            return
        if isinstance(value, list):
            for nested in value:
                self._extract_from_json_ld(nested)

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = {k.lower(): v for k, v in attrs if k}
        if tag == "meta":
            meta_key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if meta_key in _PREDICT_META_VIDEO_KEYS:
                self._add_candidate(attr_map.get("content"))
        elif tag == "video":
            self._add_candidate(attr_map.get("src"))
        elif tag == "source":
            self._add_candidate(attr_map.get("src"))
        elif tag == "link":
            rel = (attr_map.get("rel") or "").lower()
            if "video" in rel:
                self._add_candidate(attr_map.get("href"))
        elif tag == "script":
            script_type = (attr_map.get("type") or "").split(";", maxsplit=1)[0].strip().lower()
            if script_type == "application/ld+json":
                self._capture_json_ld = True
                self._json_ld_buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._json_ld_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._capture_json_ld:
            return
        json_blob = "".join(self._json_ld_buffer).strip()
        self._capture_json_ld = False
        self._json_ld_buffer = []
        if not json_blob:
            return
        try:
            parsed = loads(json_blob)
        except JSONDecodeError:
            return
        self._extract_from_json_ld(parsed)


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _cleanup_temp_file(path: Optional[Path]) -> None:
    if path is None:
        return
    if path.exists():
        path.unlink()


# Known video container magic bytes (first 8 bytes sufficient for all formats we accept).
_VIDEO_MAGIC: list[tuple[bytes, bytes]] = [
    (b"\x00\x00\x00", b"ftyp"),   # MP4 / MOV — 4-byte box size + "ftyp"
    (b"\x1aE\xdf\xa3", b""),      # WebM / MKV EBML header
    (b"RIFF", b"AVI "),           # AVI
]
_VIDEO_MIN_BYTES = 10 * 1024  # 10 KB — anything smaller is certainly truncated or an error page


def _assert_downloaded_video_valid(path: Path) -> None:
    """Raise ValidationError if the downloaded file is too small or not a recognisable video."""
    try:
        size = path.stat().st_size
    except OSError:
        raise ValidationError("Downloaded video file is missing or unreadable")
    if size < _VIDEO_MIN_BYTES:
        _cleanup_temp_file(path)
        raise ValidationError(
            f"Downloaded file is too small ({size} bytes) — likely an error page or empty response, not a video",
        )
    try:
        header = path.read_bytes()[:12]
    except OSError:
        _cleanup_temp_file(path)
        raise ValidationError("Could not read downloaded video file")
    # MP4/MOV: bytes 4–7 must be "ftyp", "moov", "mdat", "free", or "wide"
    mp4_markers = {b"ftyp", b"moov", b"mdat", b"free", b"wide", b"skip"}
    is_mp4 = len(header) >= 8 and header[4:8] in mp4_markers
    is_webm = header[:4] == b"\x1aE\xdf\xa3"
    is_riff = header[:4] == b"RIFF"
    if not (is_mp4 or is_webm or is_riff):
        _cleanup_temp_file(path)
        raise ValidationError(
            "Downloaded file does not appear to be a valid video (unrecognised container format). Provide a direct .mp4, .mov, or .webm URL",
        )


# ---------------------------------------------------------------------------
# Platform blocking & SSRF
# ---------------------------------------------------------------------------

_PLATFORM_BLOCKED_HOSTNAMES = re.compile(
    r"(?:^|\.)"
    r"(?:tiktok\.com|"
    r"instagram\.com|"
    r"twitter\.com|x\.com|"
    r"facebook\.com|fb\.watch|fb\.me|"
    r"linkedin\.com|"
    r"snapchat\.com)$",
    re.IGNORECASE,
)

_PLATFORM_BLOCKED_DETAIL = (
    "This URL points to a platform that blocks server-side video downloads "
    "(TikTok, Instagram, Twitter/X, Facebook, LinkedIn, Snapchat). "
    "Download the video file and upload it directly instead."
)


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private/reserved IP range (SSRF protection)."""
    import ipaddress
    import socket
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                return True
    except (socket.gaierror, OSError):
        pass
    return False


def _validate_predict_video_url(video_url: str) -> str:
    candidate = video_url.strip()
    if not candidate:
        raise ValidationError("video_url cannot be empty")

    candidate = _normalize_predict_video_url(candidate)
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError("video_url must use http or https")

    hostname = (parsed.hostname or "").lower()
    if _PLATFORM_BLOCKED_HOSTNAMES.search(hostname):
        raise UnprocessableError(_PLATFORM_BLOCKED_DETAIL)

    if _is_private_ip(hostname):
        raise UnprocessableError("URLs pointing to private/internal networks are not allowed")

    return candidate


def _normalize_predict_video_url(video_url: str) -> str:
    """Normalize known malformed share URLs without broad URL rewriting.

    iSpot links are frequently copied with campaign descriptors appended as
    encoded whitespace in the slug segment (e.g. `%20origin%20main`), which
    leads to 404 responses. Keep only the first slug token for this host.
    """

    parsed = urlparse(video_url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if not hostname.endswith("ispot.tv"):
        return video_url

    segments = parsed.path.split("/")
    if len(segments) < 4 or segments[1].lower() != "ad":
        return video_url

    slug = segments[3]
    decoded_slug = unquote(slug)
    if not any(char.isspace() for char in decoded_slug):
        return video_url

    normalized_slug = decoded_slug.split()[0].strip()
    if not normalized_slug:
        return video_url

    segments[3] = quote(normalized_slug, safe="-._~")
    normalized_path = "/".join(segments)
    return urlunparse(parsed._replace(path=normalized_path))


# ---------------------------------------------------------------------------
# HTML / video-source resolution helpers
# ---------------------------------------------------------------------------


def _resolve_predict_video_source_from_html(html: str, page_url: str) -> Optional[str]:
    parser = _PredictVideoSourceParser(page_url)
    parser.feed(html)

    for match in _PREDICT_VIMEO_CONFIG_URL_PATTERN.findall(html):
        parser.candidates.append(match)

    url_patterns = (
        re.compile(r"https?://[^\s\"'<>]+"),
        re.compile(r"https?:\\\/\\\/[^\s\"'<>]+"),
    )
    for pattern in url_patterns:
        for match in pattern.findall(html):
            parser.candidates.append(match)

    seen: set[str] = set()
    deduped: list[str] = []
    for candidate in parser.candidates:
        normalized = _predict_decode_candidate(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    def score(url: str) -> tuple[int, int]:
        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parsed.query.lower()
        full = f"{path}?{query}"
        if "/config" in path and "player.vimeo.com" in (parsed.netloc or "").lower():
            return (5, -len(url))
        if ".mp4" in full:
            return (4, -len(url))
        if any(ext in full for ext in (".mov", ".m4v", ".webm")):
            return (3, -len(url))
        if ".m3u8" in full or ".mpd" in full:
            return (1, -len(url))
        return (2, -len(url))

    def is_media_like(url: str) -> bool:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
        path = parsed.path or ""
        if _PREDICT_MEDIA_PATH_PATTERN.search(path):
            return True
        if "player.vimeo.com" in netloc and path.endswith("/config"):
            return True
        return False

    valid = [
        candidate
        for candidate in deduped
        if urlparse(candidate).scheme in {"http", "https"} and urlparse(candidate).netloc
        and is_media_like(candidate)
    ]
    if not valid:
        return None

    best = max(valid, key=score)
    return best


def _is_predict_media_or_config_url(candidate_url: str) -> bool:
    parsed = urlparse(candidate_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = parsed.path or ""
    if _PREDICT_MEDIA_PATH_PATTERN.search(path):
        return True
    netloc = (parsed.netloc or "").lower()
    if "player.vimeo.com" in netloc and path.endswith("/config"):
        return True
    return False


def _predict_external_resolver_urls() -> list[str]:
    raw = os.getenv("PREDICT_EXTERNAL_RESOLVER_URLS", "").strip()
    if not raw:
        return []
    candidates = []
    for entry in raw.split(","):
        value = entry.strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            candidates.append(value)
    return candidates


def _resolve_predict_video_source_via_external_resolvers(video_url: str) -> Optional[str]:
    resolver_urls = _predict_external_resolver_urls()
    if not resolver_urls:
        return None

    payload_bytes = dumps({"url": video_url}).encode("utf-8")
    timeout_seconds = max(_PREDICT_DOWNLOAD_TIMEOUT_SECONDS, 10)
    for resolver_url in resolver_urls:
        try:
            client = get_sync_client()
            response = client.post(
                resolver_url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=TIMEOUT_PREDICT_DOWNLOAD,
            )
            content_type = (response.headers.get("content-type") or "").lower()
            if "json" not in content_type:
                continue
            body = response.content
            if len(body) > _PREDICT_HTML_MAX_BYTES:
                continue
        except (httpx.HTTPError, OSError):
            logger.debug("Failed to fetch JSON endpoint %s", resolver_url, exc_info=True)
            continue

        try:
            parsed_payload = loads(body.decode("utf-8", errors="replace"))
        except (JSONDecodeError, UnicodeDecodeError):
            logger.debug("Failed to parse JSON from %s", resolver_url, exc_info=True)
            continue
        if not isinstance(parsed_payload, dict):
            continue

        for key in ("videoUrl", "resolvedUrl", "video_url", "resolved_url"):
            candidate = parsed_payload.get(key)
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            normalized = _predict_decode_candidate(candidate)
            absolute = urljoin(resolver_url, normalized)
            parsed = urlparse(absolute)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return absolute
    return None


def _predict_resolver_error_detail(base_message: str, diagnostics: list[str]) -> str:
    cleaned = [entry.strip() for entry in diagnostics if entry and entry.strip()]
    if not cleaned:
        return base_message
    joined = "; ".join(cleaned[:8])
    return f"{base_message} [{joined}]"


def _resolve_predict_video_suffix(file_name_or_url: str, content_type: Optional[str] = None) -> str:
    suffix = Path(urlparse(file_name_or_url).path).suffix.lower()
    if suffix and 1 < len(suffix) <= 10:
        return suffix
    normalized_content_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if normalized_content_type in _PREDICT_CONTENT_TYPE_TO_SUFFIX:
        return _PREDICT_CONTENT_TYPE_TO_SUFFIX[normalized_content_type]
    return ".mp4"


def _resolve_from_vimeo_config_payload(payload: dict) -> Optional[str]:
    request_payload = payload.get("request") if isinstance(payload, dict) else None
    files_payload = request_payload.get("files") if isinstance(request_payload, dict) else None
    if not isinstance(files_payload, dict):
        return None

    progressive = files_payload.get("progressive")
    best_mp4: Optional[str] = None
    best_score = -1
    if isinstance(progressive, list):
        for item in progressive:
            if not isinstance(item, dict):
                continue
            candidate = item.get("url")
            if not isinstance(candidate, str):
                continue
            parsed = urlparse(candidate.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            width = int(item.get("width", 0) or 0)
            height = int(item.get("height", 0) or 0)
            score = width * max(height, 1)
            if score > best_score:
                best_score = score
                best_mp4 = candidate

    if best_mp4:
        return best_mp4

    hls_payload = files_payload.get("hls")
    if isinstance(hls_payload, dict):
        default_cdn = hls_payload.get("default_cdn")
        cdns = hls_payload.get("cdns")
        if isinstance(cdns, dict):
            if isinstance(default_cdn, str):
                default_entry = cdns.get(default_cdn)
                if isinstance(default_entry, dict):
                    candidate = default_entry.get("url")
                    if isinstance(candidate, str):
                        parsed = urlparse(candidate.strip())
                        if parsed.scheme in {"http", "https"} and parsed.netloc:
                            return candidate
            for entry in cdns.values():
                if not isinstance(entry, dict):
                    continue
                candidate = entry.get("url")
                if not isinstance(candidate, str):
                    continue
                parsed = urlparse(candidate.strip())
                if parsed.scheme in {"http", "https"} and parsed.netloc:
                    return candidate
    return None


def _predict_decode_candidate(value: str) -> str:
    return (
        value.replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\/", "/")
        .replace("&amp;", "&")
        .strip()
    )


def _predict_headers_for_request(target_url: str, *, referer: Optional[str] = None) -> dict[str, str]:
    parsed = urlparse(target_url)
    hostname = (parsed.hostname or "").lower()
    headers: dict[str, str] = {"User-Agent": "biograph_api/0.1"}
    if "vimeo.com" in hostname:
        headers["Referer"] = referer or "https://vimeo.com"
        headers["Origin"] = "https://vimeo.com"
    return headers


def _extract_vimeo_config_url_from_html(html: str, base_url: str) -> Optional[str]:
    for pattern in _PREDICT_VIMEO_CONFIG_CAPTURE_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        normalized = _predict_decode_candidate(match.group(1))
        if not normalized:
            continue
        absolute = urljoin(base_url, normalized)
        parsed = urlparse(absolute)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return absolute

    direct_match = _PREDICT_VIMEO_CONFIG_URL_PATTERN.search(html)
    if direct_match:
        normalized = _predict_decode_candidate(direct_match.group(0))
        parsed = urlparse(normalized)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return normalized
    return None


# ---------------------------------------------------------------------------
# yt-dlp resolution / download
# ---------------------------------------------------------------------------


def _resolve_predict_video_source_with_yt_dlp(video_url: str) -> Optional[str]:
    safe_url = _validate_predict_video_url(video_url)
    command = [
        "--no-playlist",
        "--get-url",
        "--format",
        "best[ext=mp4]/best",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        safe_url,
    ]
    hostname = (urlparse(safe_url).hostname or "").lower()
    if "vimeo.com" in hostname:
        command.extend(["--referer", "https://vimeo.com/"])
    if "youtube.com" in hostname or "youtu.be" in hostname:
        cookies_path = _ensure_youtube_cookies()
        if cookies_path:
            command.extend(["--cookies", cookies_path])
    # Route through residential proxy when configured
    if _YTDLP_PROXY:
        command.extend(["--proxy", _YTDLP_PROXY])

    def _run(command_args: list[str]) -> Optional[subprocess.CompletedProcess[str]]:
        try:
            return subprocess.run(
                command_args,
                capture_output=True,
                text=True,
                timeout=_PREDICT_YTDLP_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            return None

    def _exec_yt_dlp(cmd: list[str]) -> Optional[subprocess.CompletedProcess[str]]:
        r = _run(["yt-dlp", *cmd])
        if r is None:
            r = _run([sys.executable, "-m", "yt_dlp", *cmd])
        return r

    result = _exec_yt_dlp(command)
    try:
        if result is None:
            raise FileNotFoundError("yt-dlp executable and module launcher not found")
    except FileNotFoundError:
        logger.warning("yt-dlp binary is unavailable for predictor URL resolution")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out while resolving predictor URL", extra={"video_url": safe_url})
        return None

    # Retry without proxy on SSL/connection errors — residential proxies can
    # drop long-lived streams causing SSL: UNEXPECTED_EOF_WHILE_READING.
    if result.returncode != 0 and _YTDLP_PROXY:
        stderr_lower = (result.stderr or "").lower()
        if any(tok in stderr_lower for tok in ("ssl", "unexpected_eof", "connection reset", "timed out", "urlopen error")):
            logger.info("Retrying yt-dlp resolve WITHOUT proxy after SSL/connection error")
            no_proxy_cmd = [arg for arg in command if arg != "--proxy" and arg != _YTDLP_PROXY]
            result = _exec_yt_dlp(no_proxy_cmd)
            if result is None:
                return None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.warning(
            "yt-dlp failed to resolve predictor URL (rc=%d): %s",
            result.returncode,
            stderr[:500],
            extra={"video_url": safe_url, "stderr": stderr[:800]},
        )
        return None

    for line in (result.stdout or "").splitlines():
        candidate = line.strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return None


def _download_predict_video_with_yt_dlp(video_url: str) -> Optional[Path]:
    safe_url = _validate_predict_video_url(video_url)
    workdir = Path(tempfile.mkdtemp(prefix="predict-yt-dlp-"))
    output_template = str(workdir / "video.%(ext)s")
    command = [
        "--no-playlist",
        "--no-progress",
        "--format",
        "best[ext=mp4]/best",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-o",
        output_template,
        safe_url,
    ]
    hostname = (urlparse(safe_url).hostname or "").lower()
    if "vimeo.com" in hostname:
        command.extend(["--referer", "https://vimeo.com/"])
    if "youtube.com" in hostname or "youtu.be" in hostname:
        # Pick the best single-file mp4 up to 1080p; merge audio+video if needed
        fmt_idx = command.index("best[ext=mp4]/best")
        command[fmt_idx] = "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]/best"
        command.extend(["--merge-output-format", "mp4"])
        cookies_path = _ensure_youtube_cookies()
        if cookies_path:
            command.extend(["--cookies", cookies_path])
    # Route through residential proxy when configured
    if _YTDLP_PROXY:
        command.extend(["--proxy", _YTDLP_PROXY])

    def _run(command_args: list[str], timeout_seconds: int) -> Optional[subprocess.CompletedProcess[str]]:
        try:
            return subprocess.run(
                command_args,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return None

    timeout_seconds = max(_PREDICT_YTDLP_TIMEOUT_SECONDS * 4, 45)

    def _exec_dl(cmd: list[str]) -> Optional[subprocess.CompletedProcess[str]]:
        r = _run(["yt-dlp", *cmd], timeout_seconds=timeout_seconds)
        if r is None:
            r = _run([sys.executable, "-m", "yt_dlp", *cmd], timeout_seconds=timeout_seconds)
        return r

    try:
        result = _exec_dl(command)
        if result is None:
            raise FileNotFoundError("yt-dlp executable and module launcher not found")
    except FileNotFoundError:
        logger.warning("yt-dlp binary is unavailable for predictor direct download fallback")
        shutil.rmtree(workdir, ignore_errors=True)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out while downloading predictor source", extra={"video_url": safe_url})
        shutil.rmtree(workdir, ignore_errors=True)
        return None

    # Retry without proxy on SSL/connection errors — residential proxies can
    # drop long-lived video download streams causing SSL: UNEXPECTED_EOF_WHILE_READING.
    if result.returncode != 0 and _YTDLP_PROXY:
        stderr_lower = (result.stderr or "").lower()
        if any(tok in stderr_lower for tok in ("ssl", "unexpected_eof", "connection reset", "timed out", "urlopen error")):
            logger.info("Retrying yt-dlp download WITHOUT proxy after SSL/connection error")
            no_proxy_cmd = [arg for arg in command if arg != "--proxy" and arg != _YTDLP_PROXY]
            # Clean partial download before retry
            for partial in workdir.glob("*"):
                partial.unlink(missing_ok=True)
            try:
                result = _exec_dl(no_proxy_cmd)
                if result is None:
                    shutil.rmtree(workdir, ignore_errors=True)
                    return None
            except subprocess.TimeoutExpired:
                logger.warning("yt-dlp timed out on retry without proxy", extra={"video_url": safe_url})
                shutil.rmtree(workdir, ignore_errors=True)
                return None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.warning(
            "yt-dlp direct download fallback failed (rc=%d): %s",
            result.returncode,
            stderr[:500],
            extra={"video_url": safe_url, "stderr": stderr[:800]},
        )
        shutil.rmtree(workdir, ignore_errors=True)
        if "429" in stderr or "too many requests" in stderr.lower():
            raise _YouTubeRateLimitError(
                "YouTube is rate-limiting downloads from this server (HTTP 429). "
                "Upload the video file directly using the file upload button instead."
            )
        return None

    candidates = [path for path in workdir.glob("video.*") if path.is_file() and path.stat().st_size > 0]
    if not candidates:
        shutil.rmtree(workdir, ignore_errors=True)
        return None
    source_path = max(candidates, key=lambda item: item.stat().st_size)

    suffix = source_path.suffix.lower()
    if not suffix or len(suffix) > 10:
        suffix = ".mp4"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
    shutil.copyfile(source_path, temp_path)
    shutil.rmtree(workdir, ignore_errors=True)
    return temp_path


# ---------------------------------------------------------------------------
# Vimeo config resolution
# ---------------------------------------------------------------------------


def _predict_resolution_visit_key(video_url: str) -> str:
    parsed = urlparse(video_url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
        if not path:
            path = "/"
    return f"{scheme}://{netloc}{path}"


def _extract_vimeo_video_id(video_url: str) -> Optional[str]:
    match = _PREDICT_VIMEO_ID_PATTERN.search(video_url)
    if not match:
        return None
    return match.group(1)


def _resolve_predict_video_source_from_vimeo_config(video_url: str) -> Optional[str]:
    video_id = _extract_vimeo_video_id(video_url)
    if not video_id:
        return None

    def _fetch_vimeo_config(config_url: str, *, referer: str) -> Optional[dict]:
        client = get_sync_client()
        response = client.get(
            config_url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": referer,
                "Origin": "https://vimeo.com",
            },
            timeout=TIMEOUT_PREDICT_DOWNLOAD,
        )
        content_type = (response.headers.get("content-type") or "").lower()
        if "json" not in content_type:
            return None
        body = response.content
        if len(body) > _PREDICT_HTML_MAX_BYTES:
            return None
        payload = loads(body.decode("utf-8", errors="replace"))
        if isinstance(payload, dict):
            return payload
        return None

    config_url = f"https://player.vimeo.com/video/{video_id}/config"
    try:
        payload = _fetch_vimeo_config(config_url, referer=video_url)
        if payload:
            direct = _resolve_from_vimeo_config_payload(payload)
            if direct:
                return direct
    except (httpx.HTTPError, JSONDecodeError, OSError):
        logger.debug("Vimeo config fetch failed for %s", config_url, exc_info=True)

    player_url = f"https://player.vimeo.com/video/{video_id}"
    try:
        client = get_sync_client()
        response = client.get(
            player_url,
            headers={
                **_predict_headers_for_request(player_url, referer=video_url),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=TIMEOUT_PREDICT_DOWNLOAD,
        )
        content_type = (response.headers.get("content-type") or "").lower()
        if "html" not in content_type:
            return None
        html = response.text
        if len(html) > _PREDICT_HTML_MAX_BYTES:
            return None
    except (httpx.HTTPError, OSError):
        logger.debug("Vimeo player HTML fetch failed for %s", player_url, exc_info=True)
        return None

    config_candidate = _extract_vimeo_config_url_from_html(html, player_url)
    if config_candidate:
        try:
            payload = _fetch_vimeo_config(config_candidate, referer=video_url)
            if payload:
                direct = _resolve_from_vimeo_config_payload(payload)
                if direct:
                    return direct
        except (httpx.HTTPError, JSONDecodeError, OSError):
            logger.debug("Vimeo config fallback fetch failed for %s", config_candidate, exc_info=True)

    fallback = _resolve_predict_video_source_from_html(html, player_url)
    if fallback and _PREDICT_MEDIA_PATH_PATTERN.search(urlparse(fallback).path or ""):
        return fallback
    return None


# ---------------------------------------------------------------------------
# Upload persistence
# ---------------------------------------------------------------------------


async def _persist_predict_upload(file: UploadFile) -> Path:
    suffix = _resolve_predict_video_suffix(file.filename or "upload.mp4")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        while True:
            chunk = await file.read(_PREDICT_DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            temp_file.write(chunk)
        temp_path = Path(temp_file.name)
    await file.close()
    return temp_path


# ---------------------------------------------------------------------------
# Core download orchestrator
# ---------------------------------------------------------------------------


class InsufficientDiskSpaceError(Exception):
    """Raised when there is not enough free disk space to download a video."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _download_predict_video(
    video_url: str,
    *,
    _depth: int = 0,
    _visited: Optional[set[str]] = None,
) -> tuple[Path, str]:
    safe_url = _validate_predict_video_url(video_url)
    if _depth == 0:
        free_bytes = shutil.disk_usage(tempfile.gettempdir()).free
        if free_bytes < _PREDICT_MIN_FREE_DISK_BYTES:
            raise InsufficientDiskSpaceError(
                f"Insufficient disk space: {free_bytes // (1024*1024)}MB free, need {_PREDICT_MIN_FREE_DISK_BYTES // (1024*1024)}MB",
            )
    if _depth > 4:
        raise ValidationError("Unable to resolve an embedded video source from video_url")
    visited = _visited or set()
    visit_key = _predict_resolution_visit_key(safe_url)
    if visit_key in visited:
        raise ValidationError("Circular redirect while resolving video_url")
    visited.add(visit_key)

    # YouTube blocks yt-dlp on shared server IPs via bot-detection.
    # Allow if EITHER cookies or a residential proxy (or both) are configured.
    if _depth == 0:
        _hostname = (urlparse(safe_url).hostname or "").lower()
        if "youtube.com" in _hostname or "youtu.be" in _hostname:
            has_cookies = _ensure_youtube_cookies() is not None
            has_proxy = _YTDLP_PROXY is not None
            if not has_cookies and not has_proxy:
                raise UnprocessableError(
                    "YouTube blocks server-side downloads on shared hosting IPs. "
                    "Configure YOUTUBE_COOKIES_NETSCAPE (browser cookies) and/or "
                    "YTDLP_PROXY (residential proxy) to enable YouTube downloads, "
                    "or download the video file locally and upload it.",
                )

    try:
        diagnostics: list[str] = []
        vimeo_direct_source = _resolve_predict_video_source_from_vimeo_config(safe_url)
        if vimeo_direct_source and vimeo_direct_source != safe_url:
            return _download_predict_video(vimeo_direct_source, _depth=_depth + 1, _visited=visited)
        if not vimeo_direct_source:
            diagnostics.append("vimeo_config:none")

        client = get_sync_client()
        with client.stream(
            "GET",
            safe_url,
            headers=_predict_headers_for_request(safe_url, referer=safe_url),
            timeout=TIMEOUT_PREDICT_DOWNLOAD,
        ) as response:
            content_type = (response.headers.get("content-type") or "").split(";", maxsplit=1)[0].strip().lower()
            if content_type in {"text/html", "application/xhtml+xml"}:
                html_bytes = response.read()
                if len(html_bytes) > _PREDICT_HTML_MAX_BYTES:
                    raise ValidationError(
                        f"video_url page exceeds {_PREDICT_HTML_MAX_BYTES} byte parsing limit",
                    )
                html_text = html_bytes.decode("utf-8", errors="replace")
                resolved_source = _resolve_predict_video_source_from_html(html_text, safe_url)
                if not resolved_source:
                    diagnostics.append("html_candidate:none")
                    resolved_source = _resolve_predict_video_source_from_vimeo_config(safe_url)
                if not resolved_source:
                    diagnostics.append("vimeo_config_fallback:none")
                    resolved_source = _resolve_predict_video_source_with_yt_dlp(safe_url)
                if not resolved_source:
                    diagnostics.append("yt_dlp_url:none")
                    resolved_source = _resolve_predict_video_source_via_external_resolvers(safe_url)
                if not resolved_source:
                    diagnostics.append("external_resolver:none")
                if resolved_source and not _is_predict_media_or_config_url(resolved_source):
                    diagnostics.append("candidate_non_media")
                    resolved_source = None
                if not resolved_source:
                    downloaded_path = _download_predict_video_with_yt_dlp(safe_url)
                    if downloaded_path is not None:
                        _assert_downloaded_video_valid(downloaded_path)
                        return downloaded_path, safe_url
                    diagnostics.append("yt_dlp_download:none")
                    raise ValidationError(
                        _predict_resolver_error_detail(
                            "video_url points to a webpage but no downloadable embedded video source was found. "
                            "Provide a direct .mp4/.mov/.webm URL or upload a file.",
                            diagnostics,
                        ),
                    )
                return _download_predict_video(resolved_source, _depth=_depth + 1, _visited=visited)

            if content_type in {"application/json", "text/json"}:
                body = response.read()
                if len(body) > _PREDICT_HTML_MAX_BYTES:
                    raise ValidationError(
                        f"video_url page exceeds {_PREDICT_HTML_MAX_BYTES} byte parsing limit",
                    )
                try:
                    payload = loads(body.decode("utf-8", errors="replace"))
                except JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    resolved_from_json = _resolve_from_vimeo_config_payload(payload)
                    if resolved_from_json and resolved_from_json != safe_url:
                        return _download_predict_video(
                            resolved_from_json,
                            _depth=_depth + 1,
                            _visited=visited,
                        )
                downloaded_path = _download_predict_video_with_yt_dlp(safe_url)
                if downloaded_path is not None:
                    _assert_downloaded_video_valid(downloaded_path)
                    return downloaded_path, safe_url
                diagnostics.append("json_config:none")
                diagnostics.append("yt_dlp_download:none")
                raise ValidationError(
                    _predict_resolver_error_detail(
                        "Unable to resolve an embedded video source from video_url",
                        diagnostics,
                    ),
                )

            content_length_header = response.headers.get("content-length")
            if content_length_header:
                try:
                    if int(content_length_header) > _PREDICT_DOWNLOAD_MAX_BYTES:
                        raise ValidationError(
                            f"video_url file exceeds {_PREDICT_DOWNLOAD_MAX_BYTES} byte limit",
                        )
                except ValueError:
                    pass

            suffix = _resolve_predict_video_suffix(safe_url, content_type=content_type)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = Path(temp_file.name)
                total_bytes = 0
                for chunk in response.iter_bytes(chunk_size=_PREDICT_DOWNLOAD_CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > _PREDICT_DOWNLOAD_MAX_BYTES:
                        _cleanup_temp_file(temp_path)
                        raise ValidationError(
                            f"video_url file exceeds {_PREDICT_DOWNLOAD_MAX_BYTES} byte limit",
                        )
                    temp_file.write(chunk)
            _assert_downloaded_video_valid(temp_path)
            return temp_path, safe_url
    except (ValidationError, UnprocessableError, InsufficientDiskSpaceError):
        raise
    except _YouTubeRateLimitError:
        raise
    except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException, TimeoutError, ValueError) as exc:
        diagnostics = [f"request_error:{type(exc).__name__}"]
        downloaded_path = _download_predict_video_with_yt_dlp(safe_url)
        if downloaded_path is not None:
            _assert_downloaded_video_valid(downloaded_path)
            return downloaded_path, safe_url
        diagnostics.append("yt_dlp_download:none")
        resolved_source = _resolve_predict_video_source_from_vimeo_config(safe_url)
        if not resolved_source:
            diagnostics.append("vimeo_config:none")
            resolved_source = _resolve_predict_video_source_with_yt_dlp(safe_url)
        if not resolved_source:
            diagnostics.append("yt_dlp_url:none")
            resolved_source = _resolve_predict_video_source_via_external_resolvers(safe_url)
        if not resolved_source:
            diagnostics.append("external_resolver:none")
        if resolved_source and _is_predict_media_or_config_url(resolved_source):
            return _download_predict_video(resolved_source, _depth=_depth + 1, _visited=visited)
        raise ValidationError(
            _predict_resolver_error_detail(f"Unable to download video_url: {exc}", diagnostics),
        ) from exc
