"""Self-relevance diagnostics from direct-address and context-safe personalization cues."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import to_float

from .schemas import (
    ReadoutCtaMarker,
    SelfRelevanceDiagnostics,
    SelfRelevancePathway,
    SelfRelevanceTimelineWindow,
    SelfRelevanceWarning,
    SelfRelevanceWarningSeverity,
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
_DIRECT_ADDRESS_TOKENS = {"you", "your", "yours", "yourself"}
_PERSONALIZATION_PHRASES = (
    "for you",
    "your team",
    "your workflow",
    "your business",
    "your goals",
    "built for",
    "tailored for",
    "for busy",
)
_AUDIENCE_METADATA_KEYS = (
    "target_audience",
    "targetAudience",
    "target_audience_tags",
    "targetAudienceTags",
    "audience_keywords",
    "audienceKeywords",
    "intended_audience",
    "intendedAudience",
    "persona_keywords",
    "personaKeywords",
    "niche",
    "niche_tags",
    "nicheTags",
    "use_case",
    "useCase",
)
_PROTECTED_TRAIT_TOKENS = {
    "race",
    "ethnicity",
    "religion",
    "muslim",
    "christian",
    "jewish",
    "hindu",
    "buddhist",
    "black",
    "white",
    "asian",
    "latino",
    "latina",
    "gay",
    "lesbian",
    "bisexual",
    "trans",
    "transgender",
    "pregnant",
    "disability",
    "disabled",
}
_STOPWORD_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "your",
    "you",
    "our",
    "are",
    "will",
    "can",
    "just",
    "into",
    "about",
    "more",
}


@dataclass(frozen=True)
class SelfRelevanceConfig:
    direct_address_weight: float = 0.28
    audience_match_weight: float = 0.24
    niche_specificity_weight: float = 0.2
    personalization_hook_weight: float = 0.14
    resonance_weight: float = 0.14
    min_tracking_confidence: float = 0.3
    min_quality_score: float = 0.25
    direct_address_floor_for_context: float = 0.08
    personalization_floor_for_context: float = 0.08
    top_window_limit: int = 5
    fallback_confidence_cap: float = 0.48
    context_confidence_cap: float = 0.86


def resolve_self_relevance_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> SelfRelevanceConfig:
    """Build self-relevance settings from env + optional per-video metadata."""

    config = SelfRelevanceConfig()
    settings_overrides = _parse_override_payload(get_settings().self_relevance_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("self_relevance_config", "selfRelevanceConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def compute_self_relevance_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    survey_rows: Sequence[Mapping[str, Any]] = (),
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]] = (),
    cta_markers: Sequence[ReadoutCtaMarker] | Sequence[Dict[str, Any]] = (),
    video_metadata: Optional[Mapping[str, Any]] = None,
    window_ms: int,
    config: Optional[SelfRelevanceConfig] = None,
) -> SelfRelevanceDiagnostics:
    """Estimate self-relevance while avoiding protected-trait inference."""

    resolved = config or SelfRelevanceConfig()
    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    reliable_rows = [
        row
        for row in rows
        if to_float(row.get("tracking_confidence"), 1.0) >= float(resolved.min_tracking_confidence)
        and to_float(row.get("quality_score"), 1.0) >= float(resolved.min_quality_score)
    ]
    rows_for_signals = reliable_rows or rows

    text_windows = _extract_text_windows(timeline_segments, cta_markers)
    survey_signals = _survey_signals(survey_rows)
    creative_tokens = _tokenize(" ".join(text for _, _, text in text_windows))
    audience_tokens, filtered_protected_terms = _collect_audience_tokens(video_metadata)

    if not rows_for_signals and not text_windows and survey_signals["resonance_signal"] is None:
        return SelfRelevanceDiagnostics(
            pathway=SelfRelevancePathway.insufficient_data,
            evidence_summary="No personalization context signals were available for self-relevance diagnostics.",
            signals_used=[],
        )

    direct_address = _direct_address_signal(text_windows)
    personalization_hook = _personalization_hook_signal(text_windows)
    audience_match = _audience_match_signal(creative_tokens, audience_tokens)
    niche_specificity = _niche_specificity_signal(creative_tokens, audience_tokens)
    resonance_signal = survey_signals["resonance_signal"]
    if resonance_signal is None:
        resonance_signal = _fallback_resonance_from_rows(rows_for_signals)

    component_values = {
        "direct_address": direct_address,
        "audience_match": audience_match,
        "niche_specificity": niche_specificity,
        "personalization_hook": personalization_hook,
        "resonance": resonance_signal,
    }
    component_weights = {
        "direct_address": float(resolved.direct_address_weight),
        "audience_match": float(resolved.audience_match_weight),
        "niche_specificity": float(resolved.niche_specificity_weight),
        "personalization_hook": float(resolved.personalization_hook_weight),
        "resonance": float(resolved.resonance_weight),
    }

    weighted_sum = 0.0
    total_weight = 0.0
    available_components = 0
    for key, weight in component_weights.items():
        value = component_values.get(key)
        if value is None:
            value = 0.4
        else:
            available_components += 1
        weighted_sum += float(value) * max(weight, 0.0)
        total_weight += max(weight, 0.0)
    global_unit = (weighted_sum / total_weight) if total_weight > 0 else 0.0

    lacks_personalization_context = (
        not audience_tokens
        and (direct_address or 0.0) < float(resolved.direct_address_floor_for_context)
        and (personalization_hook or 0.0) < float(resolved.personalization_floor_for_context)
    )

    if audience_tokens and (audience_match or 0.0) > 0.0:
        pathway = SelfRelevancePathway.contextual_personalization
    elif survey_signals["resonance_signal"] is not None:
        pathway = SelfRelevancePathway.survey_augmented
    else:
        pathway = SelfRelevancePathway.fallback_proxy

    context_coverage = mean_optional(
        [
            1.0 if (direct_address or 0.0) > 0.05 else 0.0,
            1.0 if (personalization_hook or 0.0) > 0.05 else 0.0,
            1.0 if audience_tokens else 0.0,
            1.0 if survey_signals["resonance_signal"] is not None else 0.0,
        ]
    ) or 0.0
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
    signal_coverage = float(available_components) / 5.0
    confidence = clamp(
        (0.35 * quality_mean) + (0.35 * signal_coverage) + (0.3 * context_coverage),
        0.0,
        1.0,
    )
    if pathway == SelfRelevancePathway.fallback_proxy or lacks_personalization_context:
        confidence = min(confidence, float(resolved.fallback_confidence_cap))
    else:
        confidence = min(confidence, float(resolved.context_confidence_cap))

    warnings: List[SelfRelevanceWarning] = []
    if lacks_personalization_context:
        warnings.append(
            SelfRelevanceWarning(
                warning_key="limited_personalization_context",
                severity=SelfRelevanceWarningSeverity.medium,
                message=(
                    "Personalization context was limited, so self-relevance uses a conservative, lower-confidence estimate."
                ),
                start_ms=0 if rows_for_signals else None,
                end_ms=(
                    int(rows_for_signals[-1]["bucket_start"]) + max(int(window_ms), 1)
                    if rows_for_signals
                    else None
                ),
            )
        )
    if not audience_tokens:
        warnings.append(
            SelfRelevanceWarning(
                warning_key="audience_metadata_missing",
                severity=SelfRelevanceWarningSeverity.low,
                message="Audience-match signal was limited because no explicit audience metadata was provided.",
            )
        )
    if survey_signals["resonance_signal"] is None:
        warnings.append(
            SelfRelevanceWarning(
                warning_key="sparse_survey_context",
                severity=SelfRelevanceWarningSeverity.low,
                message="Survey-based resonance support was sparse; timeline cues carried more weight.",
            )
        )
    if filtered_protected_terms > 0:
        warnings.append(
            SelfRelevanceWarning(
                warning_key="protected_traits_ignored",
                severity=SelfRelevanceWarningSeverity.low,
                message=(
                    "Potential protected-trait terms were excluded from audience matching to preserve privacy and compliance boundaries."
                ),
                metric_value=float(filtered_protected_terms),
            )
        )

    segment_scores = _build_segment_scores(
        rows=rows_for_signals,
        text_windows=text_windows,
        window_ms=max(int(window_ms), 1),
        config=resolved,
        direct_address=direct_address or 0.35,
        personalization_hook=personalization_hook or 0.35,
        audience_match=audience_match or 0.3,
        niche_specificity=niche_specificity or 0.4,
        resonance_signal=resonance_signal or 0.45,
    )

    signals_used: List[str] = []
    if direct_address is not None:
        signals_used.append("direct_address_cues")
    if personalization_hook is not None:
        signals_used.append("personalization_hook_cues")
    if audience_match is not None:
        signals_used.append("audience_metadata_token_overlap")
    if niche_specificity is not None:
        signals_used.append("niche_specificity_proxy")
    if survey_signals["resonance_signal"] is not None:
        signals_used.append("survey_resonance_signal")
    elif resonance_signal is not None:
        signals_used.append("attention_engagement_fallback_resonance")

    evidence_summary = (
        "Self relevance combines direct-address cues, optional audience metadata overlap, "
        "niche specificity, personalization hooks, and survey-supported resonance when available."
    )
    if lacks_personalization_context:
        evidence_summary += " Personalization context was limited, so confidence is intentionally reduced."

    return SelfRelevanceDiagnostics(
        pathway=pathway,
        global_score=round(clamp(global_unit, 0.0, 1.0) * 100.0, 6),
        confidence=round(confidence, 6),
        segment_scores=segment_scores,
        warnings=warnings,
        direct_address_signal=round(direct_address, 6) if direct_address is not None else None,
        audience_match_signal=round(audience_match, 6) if audience_match is not None else None,
        niche_specificity_signal=round(niche_specificity, 6) if niche_specificity is not None else None,
        personalization_hook_signal=(
            round(personalization_hook, 6) if personalization_hook is not None else None
        ),
        resonance_signal=round(resonance_signal, 6) if resonance_signal is not None else None,
        context_coverage=round(context_coverage, 6),
        evidence_summary=evidence_summary,
        signals_used=signals_used,
    )


def _build_segment_scores(
    *,
    rows: Sequence[Dict[str, object]],
    text_windows: Sequence[Tuple[int, int, str]],
    window_ms: int,
    config: SelfRelevanceConfig,
    direct_address: float,
    personalization_hook: float,
    audience_match: float,
    niche_specificity: float,
    resonance_signal: float,
) -> List[SelfRelevanceTimelineWindow]:
    score_rows: List[SelfRelevanceTimelineWindow] = []
    for row in rows:
        start_ms = int(to_float(row.get("bucket_start"), 0.0))
        end_ms = start_ms + window_ms
        direct_local = _window_direct_address_signal(text_windows, start_ms, end_ms)
        if direct_local is None:
            direct_local = direct_address
        hook_local = _window_personalization_signal(text_windows, start_ms, end_ms)
        if hook_local is None:
            hook_local = personalization_hook
        attention_local = clamp(to_float(row.get("attention_score"), resonance_signal * 100.0) / 100.0, 0.0, 1.0)

        local_unit = clamp(
            (0.32 * direct_local)
            + (0.18 * hook_local)
            + (0.2 * audience_match)
            + (0.15 * niche_specificity)
            + (0.15 * mean_optional([attention_local, resonance_signal]) or 0.45),
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
        confidence = clamp((0.55 * quality) + (0.45 * (0.2 + 0.8 * local_unit)), 0.0, 1.0)
        dominant = max(
            {
                "direct address": direct_local,
                "personalization hooks": hook_local,
                "audience-match overlap": audience_match,
                "niche specificity": niche_specificity,
                "resonance support": resonance_signal,
            }.items(),
            key=lambda item: item[1],
        )[0]

        score_rows.append(
            SelfRelevanceTimelineWindow(
                start_ms=start_ms,
                end_ms=end_ms,
                score=round(local_unit * 100.0, 6),
                confidence=round(confidence, 6),
                reason=f"Window emphasized {dominant} as the strongest self-relevance driver.",
                direct_address_signal=round(direct_local, 6),
                personalization_hook_signal=round(hook_local, 6),
            )
        )

    if not score_rows and text_windows:
        for start_ms, end_ms, text in text_windows[: max(int(config.top_window_limit), 1)]:
            direct_local = _direct_address_text_signal(text)
            hook_local = _personalization_text_signal(text)
            unit = clamp((0.55 * direct_local) + (0.45 * hook_local), 0.0, 1.0)
            score_rows.append(
                SelfRelevanceTimelineWindow(
                    start_ms=int(start_ms),
                    end_ms=max(int(end_ms), int(start_ms) + 1),
                    score=round(unit * 100.0, 6),
                    confidence=0.38,
                    reason="Text window carried self-referential or personalization cues.",
                    direct_address_signal=round(direct_local, 6),
                    personalization_hook_signal=round(hook_local, 6),
                )
            )

    score_rows = sorted(score_rows, key=lambda item: float(item.score), reverse=True)
    return score_rows[: max(int(config.top_window_limit), 1)]


def _direct_address_signal(text_windows: Sequence[Tuple[int, int, str]]) -> Optional[float]:
    tokens = _tokenize(" ".join(text for _, _, text in text_windows))
    if not tokens:
        return None
    hits = sum(1 for token in tokens if token in _DIRECT_ADDRESS_TOKENS)
    return clamp((hits / float(len(tokens))) * 6.0, 0.0, 1.0)


def _personalization_hook_signal(text_windows: Sequence[Tuple[int, int, str]]) -> Optional[float]:
    texts = [text.lower() for _, _, text in text_windows if text]
    if not texts:
        return None
    phrase_hits = 0
    for text in texts:
        if any(phrase in text for phrase in _PERSONALIZATION_PHRASES):
            phrase_hits += 1
    return clamp((phrase_hits / float(len(texts))) * 2.2, 0.0, 1.0)


def _audience_match_signal(
    creative_tokens: Sequence[str],
    audience_tokens: Sequence[str],
) -> Optional[float]:
    if not creative_tokens or not audience_tokens:
        return None
    creative_set = set(creative_tokens)
    overlap = [token for token in audience_tokens if token in creative_set]
    if not overlap:
        return 0.0
    precision = len(overlap) / float(max(len(audience_tokens), 1))
    recall = len(overlap) / float(max(len(creative_set), 1))
    return clamp((0.75 * precision) + (0.25 * (recall * 4.0)), 0.0, 1.0)


def _niche_specificity_signal(
    creative_tokens: Sequence[str],
    audience_tokens: Sequence[str],
) -> Optional[float]:
    if not creative_tokens and not audience_tokens:
        return None
    long_tail = [
        token
        for token in creative_tokens
        if len(token) >= 6 and token not in _STOPWORD_TOKENS
    ]
    long_tail_ratio = len(set(long_tail)) / float(max(len(set(creative_tokens)), 1))
    audience_density = min(len(set(audience_tokens)) / 8.0, 1.0)
    return clamp((0.6 * long_tail_ratio) + (0.4 * audience_density), 0.0, 1.0)


def _survey_signals(survey_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Optional[float]]:
    values: List[float] = []
    question_groups = {
        "overall_interest_likert",
        "overall_interest",
        "interest_likert",
        "recall_comprehension_likert",
        "recall_comprehension",
        "comprehension_recall_likert",
        "desire_to_continue_or_take_action_likert",
        "desire_to_continue_likert",
        "desire_to_take_action_likert",
    }
    for item in survey_rows:
        question_key = str(item.get("question_key") or "")
        if question_key not in question_groups:
            continue
        raw_number = item.get("response_number")
        if raw_number is None:
            continue
        numeric = to_float(raw_number, 0.0)
        if numeric <= 5.0:
            values.append(clamp((numeric - 1.0) / 4.0, 0.0, 1.0))
        else:
            values.append(clamp(numeric / 100.0, 0.0, 1.0))
    return {
        "resonance_signal": mean_optional(values),
    }


def _fallback_resonance_from_rows(rows: Sequence[Dict[str, object]]) -> Optional[float]:
    if not rows:
        return None
    attention_values = [
        to_float(row.get("attention_score"), 0.0)
        for row in rows
        if row.get("attention_score") is not None
    ]
    reward_values = [
        to_float(row.get("reward_proxy"), 0.0)
        for row in rows
        if row.get("reward_proxy") is not None
    ]
    if not attention_values and not reward_values:
        return None
    return clamp(
        (0.55 * (mean_optional([value / 100.0 for value in attention_values]) or 0.45))
        + (0.45 * (mean_optional([value / 100.0 for value in reward_values]) or 0.45)),
        0.0,
        1.0,
    )


def _extract_text_windows(
    timeline_segments: Sequence[TimelineSegmentRead] | Sequence[Dict[str, Any]],
    cta_markers: Sequence[ReadoutCtaMarker] | Sequence[Dict[str, Any]],
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

    for marker in cta_markers:
        if isinstance(marker, ReadoutCtaMarker):
            text = marker.label or ""
            start_ms = int(marker.start_ms or marker.video_time_ms)
            end_ms = int(marker.end_ms or marker.video_time_ms + 1000)
        else:
            text = str(marker.get("label") or "")
            start_ms = int(to_float(marker.get("start_ms"), to_float(marker.get("video_time_ms"), 0.0)))
            end_ms = int(to_float(marker.get("end_ms"), start_ms + 1000))
        if not text.strip():
            continue
        windows.append((start_ms, max(end_ms, start_ms + 1), text.strip()))
    return windows


def _collect_audience_tokens(
    video_metadata: Optional[Mapping[str, Any]],
) -> Tuple[List[str], int]:
    if not isinstance(video_metadata, Mapping):
        return [], 0

    raw_tokens: List[str] = []
    for key in _AUDIENCE_METADATA_KEYS:
        value = video_metadata.get(key)
        if isinstance(value, str):
            raw_tokens.extend(_tokenize(value))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, str):
                    raw_tokens.extend(_tokenize(item))
        elif isinstance(value, Mapping):
            for nested in value.values():
                if isinstance(nested, str):
                    raw_tokens.extend(_tokenize(nested))

    filtered_tokens: List[str] = []
    filtered_protected_terms = 0
    for token in raw_tokens:
        if token in _PROTECTED_TRAIT_TOKENS:
            filtered_protected_terms += 1
            continue
        if token in _STOPWORD_TOKENS or len(token) < 3:
            continue
        filtered_tokens.append(token)
    return sorted(set(filtered_tokens)), filtered_protected_terms


def _window_direct_address_signal(
    text_windows: Sequence[Tuple[int, int, str]],
    start_ms: int,
    end_ms: int,
) -> Optional[float]:
    values = [
        _direct_address_text_signal(text)
        for item_start, item_end, text in text_windows
        if not (item_end <= start_ms or item_start >= end_ms)
    ]
    if not values:
        return None
    return clamp(mean_optional(values) or 0.0, 0.0, 1.0)


def _window_personalization_signal(
    text_windows: Sequence[Tuple[int, int, str]],
    start_ms: int,
    end_ms: int,
) -> Optional[float]:
    values = [
        _personalization_text_signal(text)
        for item_start, item_end, text in text_windows
        if not (item_end <= start_ms or item_start >= end_ms)
    ]
    if not values:
        return None
    return clamp(mean_optional(values) or 0.0, 0.0, 1.0)


def _direct_address_text_signal(text: str) -> float:
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in _DIRECT_ADDRESS_TOKENS)
    return clamp((hits / float(len(tokens))) * 6.0, 0.0, 1.0)


def _personalization_text_signal(text: str) -> float:
    lowered = text.lower()
    phrase_hits = sum(1 for phrase in _PERSONALIZATION_PHRASES if phrase in lowered)
    return clamp(phrase_hits * 0.45, 0.0, 1.0)


def _tokenize(text: str) -> List[str]:
    return [token for token in _TOKEN_PATTERN.findall(text.lower()) if token]



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
    config: SelfRelevanceConfig,
    overrides: Mapping[str, Any],
) -> SelfRelevanceConfig:
    allowed_fields = {field.name for field in fields(config)}
    updates: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in allowed_fields:
            continue
        updates[key] = value
    if not updates:
        return config
    return replace(config, **updates)

