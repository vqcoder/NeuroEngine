"""Social transmission diagnostics from timeline cues and annotation support."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import to_float

from .schemas import (
    FeatureTrackRead,
    SocialTransmissionDiagnostics,
    SocialTransmissionPathway,
    SocialTransmissionTimelineWindow,
    TimelineSegmentRead,
)


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_TEXT_SEGMENT_TYPES = {
    "text_overlay",
    "cta_window",
    "scene_block",
    "speech_span",
    "audio_event",
}
_IDENTITY_TOKENS = {
    "we",
    "our",
    "us",
    "community",
    "team",
    "teams",
    "creators",
    "builder",
    "builders",
    "operators",
    "founders",
    "marketers",
    "fans",
}
_USEFULNESS_TOKENS = {
    "how",
    "guide",
    "tips",
    "checklist",
    "learn",
    "save",
    "avoid",
    "compare",
    "demo",
    "template",
    "strategy",
    "benefit",
    "proof",
}


@dataclass(frozen=True)
class SocialTransmissionConfig:
    novelty_weight: float = 0.2
    identity_weight: float = 0.14
    usefulness_weight: float = 0.16
    quote_worthiness_weight: float = 0.16
    emotional_activation_weight: float = 0.16
    memorability_weight: float = 0.18
    annotation_support_weight: float = 0.1
    min_tracking_confidence: float = 0.3
    min_quality_score: float = 0.25
    novelty_peak_threshold: float = 68.0
    top_window_limit: int = 5
    fallback_confidence_cap: float = 0.62
    timeline_confidence_cap: float = 0.86


def resolve_social_transmission_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> SocialTransmissionConfig:
    """Build social transmission settings from env + optional per-video metadata."""

    config = SocialTransmissionConfig()
    settings_overrides = _parse_override_payload(get_settings().social_transmission_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("social_transmission_config", "socialTransmissionConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def compute_social_transmission_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    annotation_rows: Sequence[Mapping[str, Any]] = (),
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]] = (),
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]] = (),
    window_ms: int,
    config: Optional[SocialTransmissionConfig] = None,
) -> SocialTransmissionDiagnostics:
    """Estimate social transmission from novelty, quote-worthiness, and identity-safe cues."""

    resolved = config or SocialTransmissionConfig()
    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    normalized_annotations = _normalize_annotation_rows(annotation_rows)
    text_windows = _extract_text_windows(timeline_segments)

    if not rows and not normalized_annotations and not text_windows:
        return SocialTransmissionDiagnostics(
            pathway=SocialTransmissionPathway.insufficient_data,
            evidence_summary="No timeline or annotation signals were available for social transmission diagnostics.",
            signals_used=[],
        )

    reliable_rows = [
        row
        for row in rows
        if to_float(row.get("tracking_confidence"), 1.0) >= float(resolved.min_tracking_confidence)
        and to_float(row.get("quality_score"), 1.0) >= float(resolved.min_quality_score)
    ]
    rows_for_signals = reliable_rows or rows

    novelty_signal = _novelty_signal(rows_for_signals, resolved)
    emotional_signal = _emotional_activation_signal(rows_for_signals)
    identity_signal = _identity_signal(text_windows)
    usefulness_signal = _usefulness_signal(text_windows)
    quote_signal = _quote_worthiness_signal(text_windows, normalized_annotations)
    memorability_signal = _memorability_signal(
        rows_for_signals,
        timeline_feature_tracks=timeline_feature_tracks,
        novelty_signal=novelty_signal,
        annotations=normalized_annotations,
    )
    annotation_support = _annotation_support_signal(normalized_annotations)

    component_values = {
        "novelty_signal": novelty_signal,
        "identity_signal": identity_signal,
        "usefulness_signal": usefulness_signal,
        "quote_worthiness_signal": quote_signal,
        "emotional_activation_signal": emotional_signal,
        "memorability_signal": memorability_signal,
    }
    component_weights = {
        "novelty_signal": float(resolved.novelty_weight),
        "identity_signal": float(resolved.identity_weight),
        "usefulness_signal": float(resolved.usefulness_weight),
        "quote_worthiness_signal": float(resolved.quote_worthiness_weight),
        "emotional_activation_signal": float(resolved.emotional_activation_weight),
        "memorability_signal": float(resolved.memorability_weight),
    }

    weighted_sum = 0.0
    total_weight = 0.0
    available_components = 0
    for key, weight in component_weights.items():
        value = component_values.get(key)
        if value is None:
            value = 0.45
        else:
            available_components += 1
        weighted_sum += float(value) * max(weight, 0.0)
        total_weight += max(weight, 0.0)
    global_unit = (weighted_sum / total_weight) if total_weight > 0 else 0.0
    if annotation_support is not None:
        global_unit = clamp(
            global_unit + (float(resolved.annotation_support_weight) * (annotation_support - 0.5)),
            0.0,
            1.0,
        )

    has_timeline_signals = bool(rows_for_signals or text_windows)
    has_annotations = bool(normalized_annotations)
    if has_timeline_signals and has_annotations:
        pathway = SocialTransmissionPathway.annotation_augmented
    elif has_timeline_signals:
        pathway = SocialTransmissionPathway.timeline_signal_model
    elif has_annotations:
        pathway = SocialTransmissionPathway.fallback_proxy
    else:
        pathway = SocialTransmissionPathway.insufficient_data

    quality_mean = mean_optional(
        [
            to_float(row.get("tracking_confidence"))
            for row in rows_for_signals
            if row.get("tracking_confidence") is not None
        ]
        + [
            to_float(row.get("quality_score"))
            for row in rows_for_signals
            if row.get("quality_score") is not None
        ]
    ) or 0.45
    signal_coverage = float(available_components) / 6.0
    annotation_coverage = clamp(len(normalized_annotations) / 10.0, 0.0, 1.0)
    confidence = clamp(
        (0.35 * quality_mean) + (0.4 * signal_coverage) + (0.25 * annotation_coverage),
        0.0,
        1.0,
    )
    if pathway == SocialTransmissionPathway.fallback_proxy:
        confidence = min(confidence, float(resolved.fallback_confidence_cap))
    elif pathway == SocialTransmissionPathway.timeline_signal_model:
        confidence = min(confidence, float(resolved.timeline_confidence_cap))

    segment_scores = _build_segment_scores(
        rows=rows_for_signals,
        text_windows=text_windows,
        window_ms=max(int(window_ms), 1),
        config=resolved,
        novelty_signal=novelty_signal or 0.45,
        emotional_signal=emotional_signal or 0.45,
        quote_signal=quote_signal or 0.45,
        usefulness_signal=usefulness_signal or 0.45,
    )

    signals_used: List[str] = []
    if novelty_signal is not None:
        signals_used.append("novelty_proxy")
    if emotional_signal is not None:
        signals_used.append("reward_and_arousal_proxies")
    if identity_signal is not None:
        signals_used.append("identity_signaling_language")
    if usefulness_signal is not None:
        signals_used.append("usefulness_tell_a_friend_language")
    if quote_signal is not None:
        signals_used.append("quote_comment_worthiness_language")
    if memorability_signal is not None:
        signals_used.append("distinctiveness_and_cadence_variation")
    if normalized_annotations:
        signals_used.append("annotation_marker_support")

    evidence_summary = (
        "Social transmission combines novelty, identity-safe signaling cues, usefulness language, "
        "quote/comment worthiness, emotional activation, and memorability proxies."
    )
    if pathway == SocialTransmissionPathway.fallback_proxy:
        evidence_summary += " Confidence is downweighted because timeline signal coverage was limited."
    elif pathway == SocialTransmissionPathway.annotation_augmented:
        evidence_summary += " Annotation markers were used to reinforce timeline-derived estimates."

    if pathway == SocialTransmissionPathway.insufficient_data:
        return SocialTransmissionDiagnostics(
            pathway=SocialTransmissionPathway.insufficient_data,
            evidence_summary="Insufficient signals were available to estimate social transmission.",
            signals_used=[],
        )

    return SocialTransmissionDiagnostics(
        pathway=pathway,
        global_score=round(global_unit * 100.0, 6),
        confidence=round(confidence, 6),
        segment_scores=segment_scores,
        novelty_signal=round(novelty_signal, 6) if novelty_signal is not None else None,
        identity_signal=round(identity_signal, 6) if identity_signal is not None else None,
        usefulness_signal=round(usefulness_signal, 6) if usefulness_signal is not None else None,
        quote_worthiness_signal=round(quote_signal, 6) if quote_signal is not None else None,
        emotional_activation_signal=round(emotional_signal, 6) if emotional_signal is not None else None,
        memorability_signal=round(memorability_signal, 6) if memorability_signal is not None else None,
        evidence_summary=evidence_summary,
        signals_used=signals_used,
    )


def _build_segment_scores(
    *,
    rows: Sequence[Dict[str, object]],
    text_windows: Sequence[Tuple[int, int, str]],
    window_ms: int,
    config: SocialTransmissionConfig,
    novelty_signal: float,
    emotional_signal: float,
    quote_signal: float,
    usefulness_signal: float,
) -> List[SocialTransmissionTimelineWindow]:
    score_rows: List[SocialTransmissionTimelineWindow] = []
    for row in rows:
        start_ms = int(to_float(row.get("bucket_start"), 0.0))
        end_ms = start_ms + int(window_ms)
        novelty_local = clamp(to_float(row.get("novelty_proxy"), novelty_signal * 100.0) / 100.0, 0.0, 1.0)
        arousal_value = row.get("arousal_proxy")
        reward_value = row.get("reward_proxy")
        velocity_value = abs(to_float(row.get("attention_velocity"), 0.0))
        emotional_local = mean_optional(
            [
                clamp(to_float(arousal_value, emotional_signal * 100.0) / 100.0, 0.0, 1.0),
                clamp(to_float(reward_value, emotional_signal * 100.0) / 100.0, 0.0, 1.0),
                clamp(velocity_value / 10.0, 0.0, 1.0),
            ]
        ) or emotional_signal
        text_quote = _window_text_quote_signal(text_windows, start_ms, end_ms)
        quote_local = text_quote if text_quote is not None else quote_signal
        usefulness_local = _window_text_usefulness_signal(text_windows, start_ms, end_ms)
        if usefulness_local is None:
            usefulness_local = usefulness_signal

        local_unit = clamp(
            (0.35 * novelty_local)
            + (0.3 * emotional_local)
            + (0.2 * quote_local)
            + (0.15 * usefulness_local),
            0.0,
            1.0,
        )
        quality = mean_optional(
            [
                to_float(row.get("tracking_confidence"))
                if row.get("tracking_confidence") is not None
                else None,
                to_float(row.get("quality_score"))
                if row.get("quality_score") is not None
                else None,
            ]
        ) or 0.45
        confidence = clamp((0.55 * quality) + (0.45 * (local_unit * 0.9 + 0.1)), 0.0, 1.0)

        dominant = max(
            {
                "novelty concentration": novelty_local,
                "emotional activation": emotional_local,
                "quote-worthiness": quote_local,
                "usefulness language": usefulness_local,
            }.items(),
            key=lambda item: item[1],
        )[0]

        score_rows.append(
            SocialTransmissionTimelineWindow(
                start_ms=start_ms,
                end_ms=end_ms,
                score=round(local_unit * 100.0, 6),
                confidence=round(confidence, 6),
                reason=f"Window showed stronger {dominant} support for social handoff potential.",
                novelty_signal=round(novelty_local, 6),
                emotional_activation_signal=round(emotional_local, 6),
                quote_worthiness_signal=round(quote_local, 6),
            )
        )

    if not score_rows and text_windows:
        for start_ms, end_ms, text in text_windows[: max(int(config.top_window_limit), 1)]:
            text_quote = _quote_text_signal(text)
            text_useful = _usefulness_text_signal(text)
            unit = clamp((0.55 * text_quote) + (0.45 * text_useful), 0.0, 1.0)
            score_rows.append(
                SocialTransmissionTimelineWindow(
                    start_ms=int(start_ms),
                    end_ms=max(int(end_ms), int(start_ms) + 1),
                    score=round(unit * 100.0, 6),
                    confidence=0.4,
                    reason="Text payload carried quote/comment or tell-a-friend support signals.",
                    novelty_signal=None,
                    emotional_activation_signal=None,
                    quote_worthiness_signal=round(text_quote, 6),
                )
            )

    score_rows = sorted(score_rows, key=lambda item: float(item.score), reverse=True)
    return score_rows[: max(int(config.top_window_limit), 1)]


def _novelty_signal(rows: Sequence[Dict[str, object]], config: SocialTransmissionConfig) -> Optional[float]:
    novelty_values = [
        to_float(row.get("novelty_proxy"))
        for row in rows
        if row.get("novelty_proxy") is not None
    ]
    if novelty_values:
        novelty_unit = mean_optional([clamp(value / 100.0, 0.0, 1.0) for value in novelty_values])
        peak_ratio = (
            sum(1 for value in novelty_values if value >= float(config.novelty_peak_threshold))
            / float(len(novelty_values))
        )
        return clamp((0.75 * (novelty_unit or 0.0)) + (0.25 * peak_ratio), 0.0, 1.0)

    velocity_values = [
        abs(to_float(row.get("attention_velocity"), 0.0))
        for row in rows
        if row.get("attention_velocity") is not None
    ]
    if velocity_values:
        return clamp((mean_optional(velocity_values) or 0.0) / 9.0, 0.0, 1.0)
    return None


def _emotional_activation_signal(rows: Sequence[Dict[str, object]]) -> Optional[float]:
    arousal_values = [
        clamp(to_float(row.get("arousal_proxy"), 0.0) / 100.0, 0.0, 1.0)
        for row in rows
        if row.get("arousal_proxy") is not None
    ]
    reward_values = [
        clamp(to_float(row.get("reward_proxy"), 0.0) / 100.0, 0.0, 1.0)
        for row in rows
        if row.get("reward_proxy") is not None
    ]
    velocity_values = [
        clamp(abs(to_float(row.get("attention_velocity"), 0.0)) / 10.0, 0.0, 1.0)
        for row in rows
        if row.get("attention_velocity") is not None
    ]
    if not arousal_values and not reward_values and not velocity_values:
        return None
    return clamp(
        (0.4 * (mean_optional(arousal_values) or 0.45))
        + (0.4 * (mean_optional(reward_values) or 0.45))
        + (0.2 * (mean_optional(velocity_values) or 0.45)),
        0.0,
        1.0,
    )


def _identity_signal(text_windows: Sequence[Tuple[int, int, str]]) -> Optional[float]:
    texts = [text for _, _, text in text_windows if text]
    if not texts:
        return None
    tokens = _tokenize(" ".join(texts))
    if not tokens:
        return None
    identity_hits = sum(1 for token in tokens if token in _IDENTITY_TOKENS)
    phrase_hits = sum(1 for text in texts if "for " in text.lower() and "you" not in text.lower())
    unit = clamp((identity_hits / float(len(tokens))) * 5.0 + (0.18 * phrase_hits), 0.0, 1.0)
    return unit


def _usefulness_signal(text_windows: Sequence[Tuple[int, int, str]]) -> Optional[float]:
    texts = [text for _, _, text in text_windows if text]
    if not texts:
        return None
    hits = sum(_usefulness_text_signal(text) for text in texts)
    return clamp(hits / float(max(len(texts), 1)), 0.0, 1.0)


def _quote_worthiness_signal(
    text_windows: Sequence[Tuple[int, int, str]],
    annotations: Sequence[Dict[str, Any]],
) -> Optional[float]:
    text_scores = [_quote_text_signal(text) for _, _, text in text_windows if text]
    note_scores = [_quote_text_signal(str(item.get("note", ""))) for item in annotations if item.get("note")]
    values = [value for value in [*text_scores, *note_scores] if value > 0]
    if not values:
        return None
    return clamp(mean_optional(values) or 0.0, 0.0, 1.0)


def _memorability_signal(
    rows: Sequence[Dict[str, object]],
    *,
    timeline_feature_tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    novelty_signal: Optional[float],
    annotations: Sequence[Dict[str, Any]],
) -> Optional[float]:
    cadence_values = _track_values(timeline_feature_tracks, "cut_cadence")
    cadence_variance = _variance(cadence_values) if cadence_values else None
    cadence_unit = clamp((cadence_variance or 0.0) / 0.4, 0.0, 1.0)
    engaging_count = sum(
        1
        for item in annotations
        if str(item.get("marker_type") or "") in {"engaging_moment", "cta_landed_moment"}
    )
    total_annotations = len(annotations)
    annotation_unit = (
        clamp(engaging_count / float(total_annotations), 0.0, 1.0)
        if total_annotations > 0
        else 0.45
    )

    local_novelty = novelty_signal
    if local_novelty is None:
        novelty_values = [
            to_float(row.get("novelty_proxy"))
            for row in rows
            if row.get("novelty_proxy") is not None
        ]
        if novelty_values:
            local_novelty = clamp((mean_optional(novelty_values) or 0.0) / 100.0, 0.0, 1.0)

    if local_novelty is None and cadence_variance is None and total_annotations == 0:
        return None
    return clamp(
        (0.55 * (local_novelty if local_novelty is not None else 0.45))
        + (0.25 * cadence_unit)
        + (0.2 * annotation_unit),
        0.0,
        1.0,
    )


def _annotation_support_signal(annotations: Sequence[Dict[str, Any]]) -> Optional[float]:
    if not annotations:
        return None
    engaging = 0
    friction = 0
    for item in annotations:
        marker_type = str(item.get("marker_type") or "")
        if marker_type in {"engaging_moment", "cta_landed_moment"}:
            engaging += 1
        elif marker_type in {"confusing_moment", "stop_watching_moment"}:
            friction += 1
    unit = clamp(0.5 + ((engaging - (0.75 * friction)) / float(max(len(annotations), 1))) * 0.6, 0.0, 1.0)
    return unit


def _extract_text_windows(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
) -> List[Tuple[int, int, str]]:
    windows: List[Tuple[int, int, str]] = []
    for segment in timeline_segments:
        if isinstance(segment, TimelineSegmentRead):
            segment_type = segment.segment_type
            start_ms = int(segment.start_ms)
            end_ms = int(segment.end_ms)
            label = segment.label or ""
            details = segment.details or {}
        else:
            segment_type = str(segment.get("segment_type") or "")
            start_ms = int(to_float(segment.get("start_ms"), 0.0))
            end_ms = int(to_float(segment.get("end_ms"), start_ms))
            label = str(segment.get("label") or "")
            details = segment.get("details") if isinstance(segment.get("details"), Mapping) else {}
        if segment_type not in _TEXT_SEGMENT_TYPES:
            continue
        detail_text = ""
        if isinstance(details, Mapping):
            for key in ("text", "content", "transcript", "utterance"):
                value = details.get(key)
                if isinstance(value, str) and value.strip():
                    detail_text = value.strip()
                    break
        payload = detail_text or label
        if not payload.strip():
            continue
        windows.append((start_ms, max(end_ms, start_ms + 1), payload.strip()))
    return windows


def _normalize_annotation_rows(annotation_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in annotation_rows:
        marker_type = str(row.get("marker_type") or "").strip()
        if not marker_type:
            continue
        normalized.append(
            {
                "marker_type": marker_type,
                "video_time_ms": int(to_float(row.get("video_time_ms"), 0.0)),
                "note": str(row.get("note") or "").strip(),
            }
        )
    return normalized


def _window_text_quote_signal(
    text_windows: Sequence[Tuple[int, int, str]],
    start_ms: int,
    end_ms: int,
) -> Optional[float]:
    values = [
        _quote_text_signal(text)
        for item_start, item_end, text in text_windows
        if not (item_end <= start_ms or item_start >= end_ms)
    ]
    if not values:
        return None
    return clamp(mean_optional(values) or 0.0, 0.0, 1.0)


def _window_text_usefulness_signal(
    text_windows: Sequence[Tuple[int, int, str]],
    start_ms: int,
    end_ms: int,
) -> Optional[float]:
    values = [
        _usefulness_text_signal(text)
        for item_start, item_end, text in text_windows
        if not (item_end <= start_ms or item_start >= end_ms)
    ]
    if not values:
        return None
    return clamp(mean_optional(values) or 0.0, 0.0, 1.0)


def _quote_text_signal(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    tokens = _tokenize(stripped)
    if not tokens:
        return 0.0
    punctuation_signal = 1.0 if any(symbol in stripped for symbol in ("?", "!", "\"", "'")) else 0.0
    concise_signal = 1.0 if 3 <= len(tokens) <= 16 else 0.5 if len(tokens) <= 24 else 0.2
    return clamp((0.55 * punctuation_signal) + (0.45 * concise_signal), 0.0, 1.0)


def _usefulness_text_signal(text: str) -> float:
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in _USEFULNESS_TOKENS)
    return clamp((hits / float(len(tokens))) * 5.0, 0.0, 1.0)


def _track_values(
    tracks: Sequence[FeatureTrackRead] | Sequence[Dict[str, Any]],
    track_name: str,
) -> List[float]:
    values: List[float] = []
    for item in tracks:
        if isinstance(item, FeatureTrackRead):
            if item.track_name != track_name or item.numeric_value is None:
                continue
            values.append(float(item.numeric_value))
            continue
        if str(item.get("track_name") or "") != track_name:
            continue
        numeric_value = item.get("numeric_value")
        if numeric_value is None:
            continue
        values.append(to_float(numeric_value, 0.0))
    return values


def _tokenize(text: str) -> List[str]:
    return [token for token in _TOKEN_PATTERN.findall(text.lower()) if token]


def _variance(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    avg = mean_optional(values)
    if avg is None:
        return None
    return sum((value - avg) ** 2 for value in values) / float(len(values))



def _parse_override_payload(raw: object) -> Optional[Mapping[str, Any]]:
    if raw in (None, ""):
        return None
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping):
        return payload
    return None


def _apply_overrides(
    config: SocialTransmissionConfig,
    overrides: Mapping[str, Any],
) -> SocialTransmissionConfig:
    allowed_fields = {field.name for field in fields(config)}
    updates: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in allowed_fields:
            continue
        updates[key] = value
    if not updates:
        return config
    return replace(config, **updates)

