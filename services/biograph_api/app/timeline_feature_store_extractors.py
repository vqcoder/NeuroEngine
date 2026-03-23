"""Feature extraction pipelines for timeline feature store."""

from __future__ import annotations

import json
import logging
import math
import shutil
import statistics
import tempfile
from array import array
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Session as SessionModel, TracePoint, Video
from .config import get_settings
from .services_math import to_float_optional
from .timeline_feature_store_utils import _run_subprocess, _percentile, _to_int

logger = logging.getLogger(__name__)

AUDIO_SAMPLE_RATE = 16000
CUT_CADENCE_WINDOW_MS = 5000
FFMPEG_TIMEOUT_SECONDS = 180
OCR_MAX_FRAMES = 240


def _extract_audio_rms(source_path: Path) -> Dict[int, float]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-f",
        "s16le",
        "-",
    ]
    result = _run_subprocess(command, timeout_seconds=FFMPEG_TIMEOUT_SECONDS, check=False)
    if result.returncode != 0 or not result.stdout:
        return {}

    samples = array("h")
    samples.frombytes(result.stdout)
    if not samples:
        return {}

    per_second = AUDIO_SAMPLE_RATE
    total_seconds = int(math.ceil(len(samples) / float(per_second)))
    rms_map: Dict[int, float] = {}
    for second in range(total_seconds):
        start = second * per_second
        end = min((second + 1) * per_second, len(samples))
        if end <= start:
            continue
        chunk = samples[start:end]
        mean_square = sum((sample / 32768.0) ** 2 for sample in chunk) / float(len(chunk))
        rms_map[second] = round(math.sqrt(mean_square), 6)
    return rms_map


def _build_frame_level_outputs(
    sampled_frames: Sequence[Dict[str, Any]],
    *,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []

    if not sampled_frames:
        return segments, tracks

    previous = None
    motion_labels: List[str] = []
    for index, frame in enumerate(sampled_frames):
        start_ms = int(frame["start_ms"])
        next_start_ms = (
            int(sampled_frames[index + 1]["start_ms"])
            if index + 1 < len(sampled_frames)
            else min(start_ms + 1000, duration_ms)
        )
        end_ms = max(next_start_ms, start_ms + 1)

        segments.append(
            {
                "segment_type": "frame_sample",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": f"sample_{index}",
                "details": {
                    "mean_y": frame.get("y"),
                    "mean_u": frame.get("u"),
                    "mean_v": frame.get("v"),
                    "std_y": frame.get("std_y"),
                    "std_u": frame.get("std_u"),
                    "std_v": frame.get("std_v"),
                },
            }
        )
        tracks.append(
            {
                "track_name": "luminance_mean",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(frame.get("y", 0.0)),
                "unit": "yuv_y",
                "details": {"source": "ffmpeg_showinfo"},
            }
        )
        tracks.append(
            {
                "track_name": "color_u_mean",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(frame.get("u", 0.0)),
                "unit": "yuv_u",
                "details": {"source": "ffmpeg_showinfo"},
            }
        )
        tracks.append(
            {
                "track_name": "color_v_mean",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(frame.get("v", 0.0)),
                "unit": "yuv_v",
                "details": {"source": "ffmpeg_showinfo"},
            }
        )

        if previous is not None:
            luminance_delta = abs(float(frame.get("y", 0.0)) - float(previous.get("y", 0.0)))
            color_delta = math.sqrt(
                (float(frame.get("u", 0.0)) - float(previous.get("u", 0.0))) ** 2
                + (float(frame.get("v", 0.0)) - float(previous.get("v", 0.0))) ** 2
            )
            motion_proxy = round((0.7 * luminance_delta) + (0.3 * color_delta), 6)
            motion_label = "dynamic" if motion_proxy >= 6.0 else "steady"
            motion_labels.append(motion_label)

            tracks.append(
                {
                    "track_name": "luminance_delta",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "numeric_value": round(luminance_delta, 6),
                    "unit": "delta_y",
                    "details": {"source": "frame_delta"},
                }
            )
            tracks.append(
                {
                    "track_name": "color_delta",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "numeric_value": round(color_delta, 6),
                    "unit": "delta_uv",
                    "details": {"source": "frame_delta"},
                }
            )
            tracks.append(
                {
                    "track_name": "camera_motion_proxy",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "numeric_value": motion_proxy,
                    "unit": "proxy",
                    "details": {
                        "method": "luminance_chroma_delta_proxy",
                        "claim_safe": "heuristic camera motion class",
                    },
                }
            )
            tracks.append(
                {
                    "track_name": "camera_motion_class",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text_value": motion_label,
                    "details": {"method": "camera_motion_proxy_threshold"},
                }
            )

        previous = frame

    if motion_labels:
        dynamic_ratio = motion_labels.count("dynamic") / float(len(motion_labels))
        summary_label = "dynamic" if dynamic_ratio >= 0.5 else "steady"
        tracks.append(
            {
                "track_name": "camera_motion_class_summary",
                "start_ms": 0,
                "end_ms": max(duration_ms, 1),
                "text_value": summary_label,
                "details": {
                    "dynamic_ratio": round(dynamic_ratio, 6),
                    "method": "camera_motion_proxy_ratio",
                },
            }
        )

    return segments, tracks


def _build_keyframe_segments(
    keyframes: Sequence[Dict[str, Any]],
    *,
    duration_ms: int,
) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for keyframe in keyframes:
        start_ms = int(keyframe.get("start_ms", 0))
        end_ms = int(keyframe.get("end_ms", start_ms + 1))
        segments.append(
            {
                "segment_type": "keyframe",
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "label": keyframe.get("label"),
                "details": keyframe.get("details") or {"source": "ffprobe_skip_frame_nokey"},
            }
        )
    if not segments:
        segments.append(
            {
                "segment_type": "keyframe",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "keyframe_unavailable",
                "details": {"status": "unavailable", "reason": "No keyframe metadata extracted"},
            }
        )
    return segments


def _build_shot_outputs(
    *,
    shot_boundaries: Sequence[int],
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []

    boundaries = sorted(
        value for value in {int(item) for item in shot_boundaries} if 0 < value < duration_ms
    )
    cut_points = [0, *boundaries, duration_ms]

    shot_durations: List[int] = []
    for index in range(len(cut_points) - 1):
        start_ms = int(cut_points[index])
        end_ms = int(cut_points[index + 1])
        if end_ms <= start_ms:
            continue
        duration = end_ms - start_ms
        shot_durations.append(duration)
        segments.append(
            {
                "segment_type": "shot",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": f"shot_{index + 1}",
                "details": {"duration_ms": duration},
            }
        )
        tracks.append(
            {
                "track_name": "shot_duration_ms",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": float(duration),
                "unit": "ms",
                "details": {"shot_index": index + 1},
            }
        )

    for boundary in boundaries:
        segments.append(
            {
                "segment_type": "shot_boundary",
                "start_ms": boundary,
                "end_ms": boundary + 1,
                "label": "cut_event",
                "details": {"method": "ffmpeg_scene_detect"},
            }
        )

    for window_start in range(0, max(duration_ms, 1), CUT_CADENCE_WINDOW_MS):
        window_end = min(window_start + CUT_CADENCE_WINDOW_MS, duration_ms)
        if window_end <= window_start:
            continue
        cuts_in_window = sum(
            1 for boundary in boundaries if window_start <= boundary < window_end
        )
        window_seconds = max((window_end - window_start) / 1000.0, 0.001)
        tracks.append(
            {
                "track_name": "cut_cadence",
                "start_ms": window_start,
                "end_ms": window_end,
                "numeric_value": round(cuts_in_window / window_seconds, 6),
                "unit": "cuts_per_second",
                "details": {"cut_count": cuts_in_window, "window_ms": CUT_CADENCE_WINDOW_MS},
            }
        )

    if shot_durations:
        tracks.extend(
            [
                {
                    "track_name": "shot_duration_mean_ms",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "numeric_value": round(sum(shot_durations) / float(len(shot_durations)), 6),
                    "unit": "ms",
                    "details": {"sample_count": len(shot_durations)},
                },
                {
                    "track_name": "shot_duration_p50_ms",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "numeric_value": _percentile(shot_durations, 0.5),
                    "unit": "ms",
                    "details": {"sample_count": len(shot_durations)},
                },
                {
                    "track_name": "shot_duration_p90_ms",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "numeric_value": _percentile(shot_durations, 0.9),
                    "unit": "ms",
                    "details": {"sample_count": len(shot_durations)},
                },
            ]
        )

    return segments, tracks


def _build_scene_segments(
    *,
    video: Video,
    shot_segments: Sequence[Dict[str, Any]],
    duration_ms: int,
) -> List[Dict[str, Any]]:
    scene_rows = sorted(
        list(video.scene_graph_scenes or []),
        key=lambda row: (int(row.sort_index), int(row.start_ms), int(row.end_ms)),
    )

    segments: List[Dict[str, Any]] = []
    if scene_rows:
        for row in scene_rows:
            segments.append(
                {
                    "segment_type": "scene_block",
                    "start_ms": int(row.start_ms),
                    "end_ms": int(row.end_ms),
                    "label": row.label or row.scene_id,
                    "details": {
                        "scene_id": row.scene_id,
                        "cut_id": row.cut_id,
                        "cta_id": row.cta_id,
                        "source": "scene_graph",
                    },
                }
            )
        return segments

    # Fallback: contiguous blocks grouped from shot-level segmentation.
    ordered_shots = sorted(
        (segment for segment in shot_segments if segment.get("segment_type") == "shot"),
        key=lambda item: (int(item["start_ms"]), int(item["end_ms"])),
    )
    if not ordered_shots:
        return [
            {
                "segment_type": "scene_block",
                "start_ms": 0,
                "end_ms": duration_ms,
                "label": "scene_1",
                "details": {"source": "fallback_full_duration"},
            }
        ]

    block_size = 3
    block_index = 0
    for start in range(0, len(ordered_shots), block_size):
        chunk = ordered_shots[start : start + block_size]
        if not chunk:
            continue
        block_index += 1
        segments.append(
            {
                "segment_type": "scene_block",
                "start_ms": int(chunk[0]["start_ms"]),
                "end_ms": int(chunk[-1]["end_ms"]),
                "label": f"scene_{block_index}",
                "details": {"source": "heuristic_shot_grouping", "shot_count": len(chunk)},
            }
        )
    return segments


def _build_cta_segments(video: Video, *, duration_ms: int) -> List[Dict[str, Any]]:
    markers = sorted(
        list(video.scene_graph_cta_markers or []),
        key=lambda row: (int(row.start_ms), int(row.end_ms)),
    )
    segments: List[Dict[str, Any]] = []
    for marker in markers:
        start_ms = int(marker.start_ms)
        end_ms = int(marker.end_ms)
        segments.append(
            {
                "segment_type": "cta_window",
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "label": marker.label or marker.cta_id,
                "details": {
                    "cta_id": marker.cta_id,
                    "scene_id": marker.scene_id,
                    "cut_id": marker.cut_id,
                    "source": "scene_graph",
                },
            }
        )
    if not segments:
        segments.append(
            {
                "segment_type": "cta_window",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "cta_unavailable",
                "details": {"status": "unavailable", "reason": "No CTA markers configured"},
            }
        )
    return segments


def _build_audio_outputs(
    *,
    audio_rms: Dict[int, float],
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: List[Dict[str, Any]] = []
    tracks: List[Dict[str, Any]] = []
    if not audio_rms:
        tracks.append(
            {
                "track_name": "audio_intensity_rms",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "numeric_value": None,
                "unit": "rms",
                "details": {"status": "unavailable", "reason": "Audio stream unavailable or extraction failed"},
            }
        )
        return segments, tracks

    ordered_seconds = sorted(audio_rms.items(), key=lambda item: item[0])
    for second, rms in ordered_seconds:
        start_ms = int(second * 1000)
        end_ms = min(start_ms + 1000, duration_ms)
        tracks.append(
            {
                "track_name": "audio_intensity_rms",
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "numeric_value": float(rms),
                "unit": "rms",
                "details": {"source": "ffmpeg_pcm_rms"},
            }
        )

    rms_values = [value for _, value in ordered_seconds]
    baseline = statistics.median(rms_values) if rms_values else 0.0
    previous = ordered_seconds[0][1]
    for second, rms in ordered_seconds[1:]:
        delta = rms - previous
        onset_threshold = max(previous * 1.5, baseline * 1.2)
        if rms >= onset_threshold and delta > 0.015:
            start_ms = int(second * 1000)
            segments.append(
                {
                    "segment_type": "audio_event",
                    "start_ms": start_ms,
                    "end_ms": min(start_ms + 1000, duration_ms),
                    "label": "music_onset_proxy",
                    "confidence": 0.55,
                    "details": {
                        "rms": round(rms, 6),
                        "delta_rms": round(delta, 6),
                        "baseline_rms": round(baseline, 6),
                        "method": "rms_jump_proxy",
                    },
                }
            )
        previous = rms

    return segments, tracks


def _extract_transcript_segments(
    video: Video,
    *,
    source_path: Path,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], bool, str]:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    token_fields = ("speech_tokens", "asr_tokens", "transcript_tokens")
    for field in token_fields:
        raw_tokens = metadata.get(field)
        if not isinstance(raw_tokens, list):
            continue
        tokens: List[Dict[str, Any]] = []
        for token in raw_tokens:
            if not isinstance(token, dict):
                continue
            start_ms = _to_int(token.get("start_ms"))
            end_ms = _to_int(token.get("end_ms"))
            text = token.get("token") or token.get("text")
            if start_ms is None or end_ms is None or text is None:
                continue
            tokens.append(
                {
                    "segment_type": "speech_token",
                    "start_ms": start_ms,
                    "end_ms": max(end_ms, start_ms + 1),
                    "label": str(text),
                    "confidence": to_float_optional(token.get("confidence")),
                    "details": {"source": field},
                }
            )
        if tokens:
            return tokens, True, "metadata_tokens"

    transcript_text = metadata.get("transcript") or metadata.get("asr_transcript")
    if isinstance(transcript_text, str) and transcript_text.strip():
        return (
            [
                {
                    "segment_type": "speech_transcript",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "label": transcript_text.strip()[:120],
                    "details": {"source": "metadata_transcript", "text_length": len(transcript_text.strip())},
                }
            ],
            True,
            "metadata_transcript",
        )

    configured_provider = (get_settings().timeline_asr_provider or "metadata").strip().lower()
    if configured_provider == "whisper_cli":
        whisper_segments = _extract_transcript_with_whisper_cli(source_path, duration_ms=duration_ms)
        if whisper_segments:
            return whisper_segments, True, "whisper_cli"

    return (
        [
            {
                "segment_type": "speech_token",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "speech_unavailable",
                "details": {
                    "status": "unavailable",
                    "reason": "No ASR transcript/token payload configured",
                },
            }
        ],
        False,
        configured_provider,
    )


def _extract_text_overlay_segments(
    video: Video,
    *,
    source_path: Path,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], bool, str]:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    overlay_fields = ("text_overlays", "ocr_overlays")
    for field in overlay_fields:
        raw_overlays = metadata.get(field)
        if not isinstance(raw_overlays, list):
            continue
        overlays: List[Dict[str, Any]] = []
        for item in raw_overlays:
            if not isinstance(item, dict):
                continue
            start_ms = _to_int(item.get("start_ms"))
            end_ms = _to_int(item.get("end_ms"))
            text = item.get("text")
            if start_ms is None or end_ms is None or text is None:
                continue
            overlays.append(
                {
                    "segment_type": "text_overlay",
                    "start_ms": start_ms,
                    "end_ms": max(end_ms, start_ms + 1),
                    "label": str(text),
                    "confidence": to_float_optional(item.get("confidence")),
                    "details": {"source": field},
                }
            )
        if overlays:
            return overlays, True, "metadata_overlays"

    configured_provider = (get_settings().timeline_ocr_provider or "metadata").strip().lower()
    if configured_provider == "tesseract_cli":
        ocr_segments = _extract_text_overlays_with_tesseract_cli(source_path, duration_ms=duration_ms)
        if ocr_segments:
            return ocr_segments, True, "tesseract_cli"

    return (
        [
            {
                "segment_type": "text_overlay",
                "start_ms": 0,
                "end_ms": min(max(duration_ms, 1), 1000),
                "label": "text_overlay_unavailable",
                "details": {
                    "status": "unavailable",
                    "reason": "No OCR/text overlay payload configured",
                },
            }
        ],
        False,
        configured_provider,
    )


def _extract_transcript_with_whisper_cli(
    source_path: Path,
    *,
    duration_ms: int,
) -> List[Dict[str, Any]]:
    whisper_bin = shutil.which("whisper")
    ffmpeg_bin = shutil.which("ffmpeg")
    if whisper_bin is None or ffmpeg_bin is None:
        return []

    try:
        with tempfile.TemporaryDirectory(prefix="alphaengine_asr_") as temp_dir:
            temp_root = Path(temp_dir)
            audio_path = temp_root / "audio.wav"
            ffmpeg_result = _run_subprocess(
                [
                    ffmpeg_bin,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(source_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    str(AUDIO_SAMPLE_RATE),
                    str(audio_path),
                ],
                timeout_seconds=FFMPEG_TIMEOUT_SECONDS,
                check=False,
                text=True,
            )
            if ffmpeg_result.returncode != 0 or not audio_path.exists():
                return []

            whisper_result = _run_subprocess(
                [
                    whisper_bin,
                    str(audio_path),
                    "--model",
                    "tiny",
                    "--output_format",
                    "json",
                    "--output_dir",
                    str(temp_root),
                    "--fp16",
                    "False",
                    "--word_timestamps",
                    "True",
                ],
                timeout_seconds=max(FFMPEG_TIMEOUT_SECONDS, 300),
                check=False,
                text=True,
            )
            if whisper_result.returncode != 0:
                return []

            output_path = temp_root / f"{audio_path.stem}.json"
            if not output_path.exists():
                json_files = sorted(temp_root.glob("*.json"))
                if not json_files:
                    return []
                output_path = json_files[0]

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            segments: List[Dict[str, Any]] = []
            for segment in payload.get("segments", []):
                if not isinstance(segment, dict):
                    continue
                start_ms = int(round(max(to_float_optional(segment.get("start")) or 0.0, 0.0) * 1000.0))
                end_ms = int(round(max(to_float_optional(segment.get("end")) or 0.0, 0.0) * 1000.0))
                text = str(segment.get("text") or "").strip()
                if text:
                    segments.append(
                        {
                            "segment_type": "speech_transcript",
                            "start_ms": start_ms,
                            "end_ms": max(min(end_ms, duration_ms), start_ms + 1),
                            "label": text[:200],
                            "details": {"source": "whisper_cli"},
                        }
                    )
                words = segment.get("words")
                if isinstance(words, list):
                    for word in words:
                        if not isinstance(word, dict):
                            continue
                        token_text = str(word.get("word") or "").strip()
                        token_start = to_float_optional(word.get("start"))
                        token_end = to_float_optional(word.get("end"))
                        if not token_text or token_start is None or token_end is None:
                            continue
                        token_start_ms = int(round(max(token_start, 0.0) * 1000.0))
                        token_end_ms = int(round(max(token_end, 0.0) * 1000.0))
                        segments.append(
                            {
                                "segment_type": "speech_token",
                                "start_ms": token_start_ms,
                                "end_ms": max(min(token_end_ms, duration_ms), token_start_ms + 1),
                                "label": token_text,
                                "confidence": to_float_optional(word.get("probability")),
                                "details": {"source": "whisper_cli_word"},
                            }
                        )

            if segments:
                return sorted(
                    segments,
                    key=lambda item: (
                        int(item.get("start_ms", 0)),
                        int(item.get("end_ms", 0)),
                        str(item.get("segment_type", "")),
                    ),
                )

            transcript_text = str(payload.get("text") or "").strip()
            if transcript_text:
                return [
                    {
                        "segment_type": "speech_transcript",
                        "start_ms": 0,
                        "end_ms": max(duration_ms, 1),
                        "label": transcript_text[:200],
                        "details": {"source": "whisper_cli"},
                    }
                ]
    except Exception:
        logger.exception("whisper_cli provider failed for %s", source_path)
    return []


def _extract_text_overlays_with_tesseract_cli(
    source_path: Path,
    *,
    duration_ms: int,
) -> List[Dict[str, Any]]:
    tesseract_bin = shutil.which("tesseract")
    ffmpeg_bin = shutil.which("ffmpeg")
    if tesseract_bin is None or ffmpeg_bin is None:
        return []

    try:
        with tempfile.TemporaryDirectory(prefix="alphaengine_ocr_") as temp_dir:
            frames_dir = Path(temp_dir) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            frame_pattern = frames_dir / "frame_%06d.png"
            ffmpeg_result = _run_subprocess(
                [
                    ffmpeg_bin,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(source_path),
                    "-vf",
                    "fps=1",
                    str(frame_pattern),
                ],
                timeout_seconds=FFMPEG_TIMEOUT_SECONDS,
                check=False,
                text=True,
            )
            if ffmpeg_result.returncode != 0:
                return []

            overlays: List[Dict[str, Any]] = []
            frames = sorted(frames_dir.glob("frame_*.png"))[:OCR_MAX_FRAMES]
            for index, frame_path in enumerate(frames):
                start_ms = index * 1000
                if start_ms >= duration_ms:
                    break
                tesseract_result = _run_subprocess(
                    [tesseract_bin, str(frame_path), "stdout", "--psm", "6"],
                    timeout_seconds=30,
                    check=False,
                    text=True,
                )
                if tesseract_result.returncode != 0:
                    continue
                raw_text = tesseract_result.stdout if isinstance(tesseract_result.stdout, str) else ""
                normalized = " ".join(raw_text.split()).strip()
                if len(normalized) < 2:
                    continue
                overlays.append(
                    {
                        "segment_type": "text_overlay",
                        "start_ms": start_ms,
                        "end_ms": max(min(start_ms + 1000, duration_ms), start_ms + 1),
                        "label": normalized[:200],
                        "details": {
                            "source": "tesseract_cli",
                            "frame_index": index,
                        },
                    }
                )
            return overlays
    except Exception:
        logger.exception("tesseract_cli provider failed for %s", source_path)
    return []


def _build_trace_outputs(
    *,
    db: Session,
    video_id: UUID,
    duration_ms: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = db.execute(
        select(
            TracePoint.video_time_ms,
            TracePoint.face_ok,
            TracePoint.face_presence_confidence,
            TracePoint.head_pose_confidence,
        )
        .join(SessionModel, SessionModel.id == TracePoint.session_id)
        .where(
            SessionModel.video_id == video_id,
            TracePoint.video_time_ms.is_not(None),
        )
        .order_by(TracePoint.video_time_ms.asc())
    ).all()

    if not rows:
        return (
            [],
            [
                {
                    "track_name": "face_presence_rate",
                    "start_ms": 0,
                    "end_ms": min(max(duration_ms, 1), 1000),
                    "numeric_value": None,
                    "unit": "ratio",
                    "details": {
                        "status": "unavailable",
                        "reason": "No trace_points available for face/subject features",
                    },
                },
                {
                    "track_name": "face_count_proxy",
                    "start_ms": 0,
                    "end_ms": min(max(duration_ms, 1), 1000),
                    "numeric_value": None,
                    "unit": "proxy_count",
                    "details": {
                        "status": "unavailable",
                        "reason": "No trace_points available for face count proxy",
                    },
                },
                {
                    "track_name": "primary_subject_persistence",
                    "start_ms": 0,
                    "end_ms": max(duration_ms, 1),
                    "numeric_value": None,
                    "unit": "ratio",
                    "details": {
                        "status": "unavailable",
                        "reason": "No trace_points available for subject persistence proxy",
                    },
                },
            ],
        )

    buckets: Dict[int, Dict[str, float]] = {}
    for row in rows:
        video_time_ms = int(row.video_time_ms or 0)
        bucket_ms = (video_time_ms // 1000) * 1000
        acc = buckets.setdefault(
            bucket_ms,
            {
                "count": 0.0,
                "face_ok_sum": 0.0,
                "face_conf_sum": 0.0,
                "face_conf_count": 0.0,
                "head_conf_sum": 0.0,
                "head_conf_count": 0.0,
            },
        )
        acc["count"] += 1.0
        acc["face_ok_sum"] += 1.0 if bool(row.face_ok) else 0.0
        if row.face_presence_confidence is not None:
            acc["face_conf_sum"] += float(row.face_presence_confidence)
            acc["face_conf_count"] += 1.0
        if row.head_pose_confidence is not None:
            acc["head_conf_sum"] += float(row.head_pose_confidence)
            acc["head_conf_count"] += 1.0

    tracks: List[Dict[str, Any]] = []
    stable_windows: List[tuple[int, int]] = []
    ordered_bucket_times = sorted(buckets.keys())
    active_window_start: Optional[int] = None
    stable_bucket_count = 0

    for bucket_ms in ordered_bucket_times:
        acc = buckets[bucket_ms]
        count = max(acc["count"], 1.0)
        presence_rate = acc["face_ok_sum"] / count
        face_conf = (
            acc["face_conf_sum"] / acc["face_conf_count"]
            if acc["face_conf_count"] > 0
            else None
        )
        head_conf = (
            acc["head_conf_sum"] / acc["head_conf_count"]
            if acc["head_conf_count"] > 0
            else None
        )
        window_end = min(bucket_ms + 1000, duration_ms)
        tracks.append(
            {
                "track_name": "face_presence_rate",
                "start_ms": bucket_ms,
                "end_ms": max(window_end, bucket_ms + 1),
                "numeric_value": round(presence_rate, 6),
                "unit": "ratio",
                "details": {"mean_face_presence_confidence": round(face_conf, 6) if face_conf is not None else None},
            }
        )
        tracks.append(
            {
                "track_name": "face_count_proxy",
                "start_ms": bucket_ms,
                "end_ms": max(window_end, bucket_ms + 1),
                "numeric_value": round(presence_rate, 6),
                "unit": "proxy_count",
                "details": {
                    "method": "single_viewer_face_presence_proxy",
                    "note": "Not a multi-person detector count.",
                },
            }
        )

        is_stable = presence_rate >= 0.7 and (head_conf is None or head_conf >= 0.5)
        if is_stable:
            stable_bucket_count += 1
            if active_window_start is None:
                active_window_start = bucket_ms
        elif active_window_start is not None:
            stable_windows.append((active_window_start, bucket_ms))
            active_window_start = None

    if active_window_start is not None:
        stable_windows.append((active_window_start, min(duration_ms, active_window_start + 1000)))

    persistence_ratio = stable_bucket_count / float(max(len(ordered_bucket_times), 1))
    tracks.append(
        {
            "track_name": "primary_subject_persistence",
            "start_ms": 0,
            "end_ms": max(duration_ms, 1),
            "numeric_value": round(persistence_ratio, 6),
            "unit": "ratio",
            "details": {
                "stable_bucket_count": stable_bucket_count,
                "bucket_count": len(ordered_bucket_times),
                "method": "face_presence_head_pose_proxy",
            },
        }
    )

    segments = [
        {
            "segment_type": "primary_subject_window",
            "start_ms": start_ms,
            "end_ms": max(end_ms, start_ms + 1),
            "label": "subject_persistence_window",
            "confidence": 0.6,
            "details": {"method": "face_presence_head_pose_proxy"},
        }
        for start_ms, end_ms in stable_windows
    ]
    return segments, tracks


def _build_object_salience_tracks(video: Video, *, duration_ms: int) -> List[Dict[str, Any]]:
    metadata = video.video_metadata if isinstance(video.video_metadata, dict) else {}
    raw_candidates = (
        metadata.get("object_salience_candidates")
        or metadata.get("object_labels")
        or metadata.get("salient_objects")
    )
    tracks: List[Dict[str, Any]] = []
    if isinstance(raw_candidates, list) and raw_candidates:
        for index, candidate in enumerate(raw_candidates):
            if isinstance(candidate, dict):
                label = candidate.get("label") or candidate.get("name")
                score = to_float_optional(candidate.get("score") or candidate.get("confidence"))
            else:
                label = str(candidate)
                score = None
            if label is None or not str(label).strip():
                continue
            tracks.append(
                {
                    "track_name": "object_salience_candidate",
                    "start_ms": 0,
                    "end_ms": max(duration_ms, 1),
                    "numeric_value": score,
                    "text_value": str(label).strip(),
                    "details": {"rank": index + 1, "source": "metadata"},
                }
            )
    if tracks:
        return tracks
    return [
        {
            "track_name": "object_salience_candidate",
            "start_ms": 0,
            "end_ms": max(duration_ms, 1),
            "text_value": None,
            "numeric_value": None,
            "details": {
                "status": "unavailable",
                "reason": "Object salience candidates were not provided by upstream detection.",
            },
        }
    ]
