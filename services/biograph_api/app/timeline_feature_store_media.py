"""Source resolution and media I/O for timeline feature store."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import httpx

from .http_client import get_sync_client, TIMEOUT_TIMELINE_DOWNLOAD
from .services_math import to_float_optional
from .timeline_feature_store_utils import _run_subprocess, _parse_rational, _to_int

from fastapi import HTTPException

logger = logging.getLogger(__name__)

SOURCE_DOWNLOAD_TIMEOUT_SECONDS = 30
SOURCE_DOWNLOAD_MAX_BYTES = 512 * 1024 * 1024
FFPROBE_TIMEOUT_SECONDS = 60
FFMPEG_TIMEOUT_SECONDS = 180

SHOWINFO_FRAME_PATTERN = re.compile(
    r"pts_time:(?P<pts>[0-9]+(?:\.[0-9]+)?)"
    r".*?mean:\[(?P<y>[0-9]+) (?P<u>[0-9]+) (?P<v>[0-9]+)\]"
)
SHOWINFO_STDEV_PATTERN = re.compile(
    r"stdev:\[(?P<sy>[0-9]+(?:\.[0-9]+)?) (?P<su>[0-9]+(?:\.[0-9]+)?) (?P<sv>[0-9]+(?:\.[0-9]+)?)\]"
)
SHOWINFO_TIME_PATTERN = re.compile(r"pts_time:(?P<pts>[0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True)
class _ResolvedSource:
    path: Path
    source_ref: str
    source_kind: str
    is_temporary: bool


def _resolve_source_asset(video, override_source_ref: Optional[str]) -> _ResolvedSource:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}

    candidates: List[str] = []
    if override_source_ref:
        candidates.append(str(override_source_ref))
    if video.source_url:
        candidates.append(str(video.source_url))
    for key in (
        "source_path",
        "local_path",
        "asset_path",
        "video_path",
        "source_url",
        "video_url",
    ):
        value = metadata.get(key)
        if value:
            candidates.append(str(value))

    for candidate in candidates:
        cleaned = candidate.strip()
        if not cleaned:
            continue

        parsed = urlparse(cleaned)
        if parsed.scheme in {"http", "https"}:
            downloaded = _download_source_asset(cleaned)
            return _ResolvedSource(
                path=downloaded,
                source_ref=cleaned,
                source_kind="http_download",
                is_temporary=True,
            )

        if parsed.scheme == "file":
            local_path = Path(unquote(parsed.path))
            if local_path.exists():
                return _ResolvedSource(
                    path=local_path,
                    source_ref=str(local_path),
                    source_kind="file_url",
                    is_temporary=False,
                )

        local_path = Path(cleaned).expanduser()
        if local_path.exists():
            return _ResolvedSource(
                path=local_path,
                source_ref=str(local_path),
                source_kind="local_path",
                is_temporary=False,
            )

    raise HTTPException(
        status_code=400,
        detail="No readable source asset found; provide source_ref or set video source_url to a local path/http(s) URL",
    )


def _download_source_asset(source_url: str) -> Path:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="source_ref URL must use http or https")

    suffix = Path(parsed.path).suffix or ".mp4"
    try:
        client = get_sync_client()
        with client.stream(
            "GET",
            source_url,
            headers={
                "User-Agent": "AlphaEngineTimeline/1.0",
                "Accept": "video/*,*/*;q=0.8",
            },
            timeout=TIMEOUT_TIMELINE_DOWNLOAD,
        ) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                total_bytes = 0
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > SOURCE_DOWNLOAD_MAX_BYTES:
                        temp_path = Path(temp_file.name)
                        temp_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=400,
                            detail=f"source_ref exceeds byte limit ({SOURCE_DOWNLOAD_MAX_BYTES})",
                        )
                    temp_file.write(chunk)
                return Path(temp_file.name)
    except HTTPException:
        raise
    except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Unable to download source_ref: {exc}") from exc


def _cleanup_source_asset(resolved_source: _ResolvedSource) -> None:
    if resolved_source.is_temporary:
        resolved_source.path.unlink(missing_ok=True)


def _resolve_asset_id(video) -> str:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    for key in ("asset_id", "assetId", "video_asset_id", "videoAssetId"):
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(video.id)


def _compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _probe_video(path: Path) -> Dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = _run_subprocess(command, timeout_seconds=FFPROBE_TIMEOUT_SECONDS, text=True)
    payload = json.loads(result.stdout or "{}")

    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}

    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), None)

    duration_sec = to_float_optional(format_info.get("duration"))
    if duration_sec is None:
        duration_sec = to_float_optional(video_stream.get("duration"))
    duration_ms = int(round(max(duration_sec or 0.0, 0.0) * 1000.0))

    fps = _parse_rational(video_stream.get("avg_frame_rate")) or _parse_rational(
        video_stream.get("r_frame_rate")
    )

    return {
        "duration_ms": duration_ms,
        "width": _to_int(video_stream.get("width")),
        "height": _to_int(video_stream.get("height")),
        "fps": fps,
        "audio_stream_present": audio_stream is not None,
    }


def _extract_sampled_frames(source_path: Path, sample_interval_ms: int) -> List[Dict[str, Any]]:
    fps = 1000.0 / float(max(sample_interval_ms, 1))
    command = [
        "ffmpeg",
        "-v",
        "info",
        "-i",
        str(source_path),
        "-vf",
        f"fps={fps:.6f},showinfo",
        "-f",
        "null",
        "-",
    ]
    result = _run_subprocess(command, timeout_seconds=FFMPEG_TIMEOUT_SECONDS, text=True, check=False)
    output = f"{result.stdout}\n{result.stderr}"

    seen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    for line in output.splitlines():
        if "showinfo" not in line or "pts_time" not in line:
            continue
        frame_match = SHOWINFO_FRAME_PATTERN.search(line)
        if frame_match is None:
            continue
        timestamp_ms = int(round(float(frame_match.group("pts")) * 1000.0))
        if timestamp_ms in seen:
            continue
        seen.add(timestamp_ms)
        row: Dict[str, Any] = {
            "start_ms": max(timestamp_ms, 0),
            "end_ms": max(timestamp_ms + 1, 1),
            "y": int(frame_match.group("y")),
            "u": int(frame_match.group("u")),
            "v": int(frame_match.group("v")),
        }
        stdev_match = SHOWINFO_STDEV_PATTERN.search(line)
        if stdev_match is not None:
            row["std_y"] = float(stdev_match.group("sy"))
            row["std_u"] = float(stdev_match.group("su"))
            row["std_v"] = float(stdev_match.group("sv"))
        rows.append(row)

    return sorted(rows, key=lambda item: item["start_ms"])


def _extract_keyframes(source_path: Path) -> List[Dict[str, Any]]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-skip_frame",
        "nokey",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,pkt_dts_time,pkt_pts_time,pict_type",
        "-of",
        "json",
        str(source_path),
    ]
    result = _run_subprocess(command, timeout_seconds=FFPROBE_TIMEOUT_SECONDS, text=True)
    payload = json.loads(result.stdout or "{}")
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []

    keyframes: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        timestamp_sec = (
            to_float_optional(frame.get("best_effort_timestamp_time"))
            or to_float_optional(frame.get("pkt_pts_time"))
            or to_float_optional(frame.get("pkt_dts_time"))
        )
        if timestamp_sec is None:
            continue
        timestamp_ms = int(round(timestamp_sec * 1000.0))
        if timestamp_ms in seen:
            continue
        seen.add(timestamp_ms)
        pict_type = str(frame.get("pict_type") or "I")
        keyframes.append(
            {
                "start_ms": max(timestamp_ms, 0),
                "end_ms": max(timestamp_ms + 1, 1),
                "label": f"keyframe_{pict_type.lower()}",
                "details": {"pict_type": pict_type},
            }
        )
    return sorted(keyframes, key=lambda item: item["start_ms"])


def _extract_shot_boundaries(source_path: Path, scene_threshold: float) -> List[int]:
    command = [
        "ffmpeg",
        "-v",
        "info",
        "-i",
        str(source_path),
        "-filter:v",
        f"select='gt(scene,{scene_threshold:.3f})',showinfo",
        "-f",
        "null",
        "-",
    ]
    result = _run_subprocess(command, timeout_seconds=FFMPEG_TIMEOUT_SECONDS, text=True, check=False)
    output = f"{result.stdout}\n{result.stderr}"

    boundaries: set[int] = set()
    for line in output.splitlines():
        if "showinfo" not in line or "pts_time" not in line:
            continue
        match = SHOWINFO_TIME_PATTERN.search(line)
        if match is None:
            continue
        timestamp_ms = int(round(float(match.group("pts")) * 1000.0))
        if timestamp_ms > 0:
            boundaries.add(timestamp_ms)

    return sorted(boundaries)
