"""CTA reception diagnostics from multi-signal readiness and timeline placement quality."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import get_settings
from .readout_metrics import clamp, mean_optional
from .services_math import to_float

from .schemas import (
    AttentionalSynchronyDiagnostics,
    BlinkTransportDiagnostics,
    BoundaryEncodingDiagnostics,
    CtaReceptionDiagnostics,
    CtaReceptionFlag,
    CtaReceptionFlagSeverity,
    CtaReceptionPathway,
    CtaReceptionTimelineWindow,
    NarrativeControlDiagnostics,
    ReadoutCtaMarker,
    RewardAnticipationDiagnostics,
)


_CTA_URL_PATTERN = re.compile(r"(https?://|www\.|\.com|\.io|\.ai|\.app)", re.IGNORECASE)
_CTA_TYPE_KEYWORDS = {
    "brand_reveal": ("brand", "logo", "introducing", "remember"),
    "offer": ("offer", "save", "discount", "deal", "promo", "coupon"),
    "url": ("visit", "link", "url", "learn more"),
    "app_install": ("install", "download", "app"),
    "sign_up": ("sign up", "signup", "register", "join", "subscribe"),
    "add_to_cart": ("add to cart", "checkout", "buy now", "purchase"),
}


@dataclass(frozen=True)
class CtaReceptionConfig:
    pre_window_ms: int = 2500
    post_window_ms: int = 2500
    collapse_drop_threshold: float = 8.0
    blink_through_threshold: float = 0.42
    fragmentation_penalty_threshold: float = 2.5
    early_fraction: float = 0.2
    late_fraction: float = 0.88
    payoff_proximity_ms: int = 1400
    overload_proximity_ms: int = 1500
    max_flag_penalty: float = 0.35
    fallback_confidence_cap: float = 0.6
    top_window_limit: int = 8


def resolve_cta_reception_config(
    video_metadata: Optional[Mapping[str, Any]] = None,
) -> CtaReceptionConfig:
    """Build CTA reception settings from env + optional per-video metadata."""

    config = CtaReceptionConfig()
    settings_overrides = _parse_override_payload(get_settings().cta_reception_config_json)
    if settings_overrides:
        config = _apply_overrides(config, settings_overrides)

    if isinstance(video_metadata, Mapping):
        for key in ("cta_reception_config", "ctaReceptionConfig"):
            value = video_metadata.get(key)
            if isinstance(value, Mapping):
                config = _apply_overrides(config, value)
                break
    return config


def compute_cta_reception_diagnostics(
    *,
    bucket_rows: Sequence[Dict[str, object]],
    cta_markers: Sequence[ReadoutCtaMarker],
    attentional_synchrony: Optional[AttentionalSynchronyDiagnostics],
    narrative_control: Optional[NarrativeControlDiagnostics],
    blink_transport: Optional[BlinkTransportDiagnostics],
    reward_anticipation: Optional[RewardAnticipationDiagnostics],
    boundary_encoding: Optional[BoundaryEncodingDiagnostics],
    window_ms: int,
    config: Optional[CtaReceptionConfig] = None,
) -> CtaReceptionDiagnostics:
    """Estimate CTA landing quality from synchrony, engagement, and timing readiness cues."""

    resolved = config or CtaReceptionConfig()
    if not cta_markers:
        return CtaReceptionDiagnostics(
            pathway=CtaReceptionPathway.insufficient_data,
            evidence_summary="No CTA markers were available for CTA reception diagnostics.",
            signals_used=[],
        )

    rows = sorted(
        [row for row in bucket_rows if row.get("bucket_start") is not None],
        key=lambda row: int(row["bucket_start"]),
    )
    if not rows and all(
        item is None
        for item in (
            attentional_synchrony,
            narrative_control,
            blink_transport,
            reward_anticipation,
            boundary_encoding,
        )
    ):
        return CtaReceptionDiagnostics(
            pathway=CtaReceptionPathway.insufficient_data,
            evidence_summary="No CTA timeline rows or upstream diagnostics were available for CTA reception diagnostics.",
            signals_used=[],
        )

    duration_ms = (
        int(rows[-1]["bucket_start"]) + max(int(window_ms), 1)
        if rows
        else max(
            (
                int(marker.end_ms or marker.video_time_ms + max(int(window_ms), 1))
                for marker in cta_markers
            ),
            default=max(int(window_ms), 1),
        )
    )

    global_flags: List[CtaReceptionFlag] = []
    windows: List[CtaReceptionTimelineWindow] = []
    sync_values: List[float] = []
    narrative_values: List[float] = []
    blink_values: List[float] = []
    reward_values: List[float] = []
    boundary_values: List[float] = []
    overload_support_values: List[float] = []

    for marker in cta_markers:
        start_ms = int(marker.start_ms or marker.video_time_ms)
        end_ms = int(marker.end_ms or (start_ms + max(int(window_ms), 1)))
        cta_type = _classify_cta_type(marker)

        pre_rows = _rows_in_window(rows, start_ms - int(resolved.pre_window_ms), start_ms)
        on_rows = _rows_in_window(rows, start_ms, end_ms)
        post_rows = _rows_in_window(rows, end_ms, end_ms + int(resolved.post_window_ms))

        pre_attention = _rowmean_optional(pre_rows, "attention_score")
        post_attention = _rowmean_optional(post_rows, "attention_score")
        collapse_after_cta = (
            pre_attention is not None
            and post_attention is not None
            and (pre_attention - post_attention) >= float(resolved.collapse_drop_threshold)
        )

        synchrony_support = _cta_synchrony_support(attentional_synchrony, start_ms, end_ms)
        narrative_support, fragmentation_penalty = _cta_narrative_support(
            narrative_control,
            start_ms=start_ms,
            end_ms=end_ms,
            threshold=float(resolved.fragmentation_penalty_threshold),
        )
        blink_support = _cta_blink_support(blink_transport, start_ms, end_ms)
        reward_support, payoff_overlap = _cta_reward_support(
            reward_anticipation,
            start_ms=start_ms,
            end_ms=end_ms,
            proximity_ms=int(resolved.payoff_proximity_ms),
        )
        boundary_support, overload_risk = _cta_boundary_support(
            boundary_encoding,
            start_ms=start_ms,
            end_ms=end_ms,
            proximity_ms=int(resolved.overload_proximity_ms),
        )
        overload_support = clamp(1.0 - overload_risk, 0.0, 1.0)

        timing_fit = _cta_timing_fit(
            start_ms=start_ms,
            duration_ms=max(duration_ms, 1),
            payoff_overlap=payoff_overlap,
            collapse_after_cta=collapse_after_cta,
            overload_risk=overload_risk,
            fragmentation_penalty=fragmentation_penalty,
            early_fraction=float(resolved.early_fraction),
            late_fraction=float(resolved.late_fraction),
        )

        flag_keys: List[str] = []
        if start_ms <= int(duration_ms * float(resolved.early_fraction)) and payoff_overlap < 0.4:
            flag_keys.append("cta_too_early")
            global_flags.append(
                CtaReceptionFlag(
                    flag_key="cta_too_early",
                    severity=CtaReceptionFlagSeverity.medium,
                    message="CTA appears early before engagement and payoff readiness are established.",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    cta_id=marker.cta_id,
                    cta_type=cta_type,
                )
            )
        if start_ms >= int(duration_ms * float(resolved.late_fraction)) or collapse_after_cta:
            flag_keys.append("cta_too_late")
            global_flags.append(
                CtaReceptionFlag(
                    flag_key="cta_too_late",
                    severity=CtaReceptionFlagSeverity.high if collapse_after_cta else CtaReceptionFlagSeverity.medium,
                    message="CTA arrives after attention has weakened or too close to the end of the video.",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    cta_id=marker.cta_id,
                    cta_type=cta_type,
                    metric_value=round((pre_attention or 0.0) - (post_attention or 0.0), 6)
                    if collapse_after_cta
                    else None,
                )
            )
        if blink_support < float(resolved.blink_through_threshold):
            flag_keys.append("cta_blinked_through")
            global_flags.append(
                CtaReceptionFlag(
                    flag_key="cta_blinked_through",
                    severity=CtaReceptionFlagSeverity.high,
                    message="CTA window coincides with elevated blink-through risk.",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    cta_id=marker.cta_id,
                    cta_type=cta_type,
                    metric_value=round(blink_support, 6),
                )
            )
        if fragmentation_penalty > 0.0:
            flag_keys.append("cta_after_fragmentation")
            global_flags.append(
                CtaReceptionFlag(
                    flag_key="cta_after_fragmentation",
                    severity=CtaReceptionFlagSeverity.medium,
                    message="CTA follows disruptive transitions that may reduce comprehension continuity.",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    cta_id=marker.cta_id,
                    cta_type=cta_type,
                    metric_value=round(fragmentation_penalty, 6),
                )
            )
        if reward_support < 0.45:
            flag_keys.append("cta_missed_reward_window")
            global_flags.append(
                CtaReceptionFlag(
                    flag_key="cta_missed_reward_window",
                    severity=CtaReceptionFlagSeverity.medium,
                    message="CTA is weakly aligned with anticipation or payoff windows.",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    cta_id=marker.cta_id,
                    cta_type=cta_type,
                    metric_value=round(reward_support, 6),
                )
            )
        if overload_risk > 0.4:
            flag_keys.append("cta_cognitive_overload")
            global_flags.append(
                CtaReceptionFlag(
                    flag_key="cta_cognitive_overload",
                    severity=CtaReceptionFlagSeverity.high if overload_risk > 0.65 else CtaReceptionFlagSeverity.medium,
                    message="CTA appears in a cognitively overloaded moment with dense payload competition.",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    cta_id=marker.cta_id,
                    cta_type=cta_type,
                    metric_value=round(overload_risk, 6),
                )
            )

        score_unit = clamp(
            (0.19 * synchrony_support)
            + (0.16 * narrative_support)
            + (0.2 * blink_support)
            + (0.23 * reward_support)
            + (0.14 * boundary_support)
            + (0.08 * timing_fit),
            0.0,
            1.0,
        )
        if flag_keys:
            score_unit = clamp(
                score_unit - min(len(flag_keys) * 0.05, float(resolved.max_flag_penalty)),
                0.0,
                1.0,
            )

        confidence = _cta_confidence(
            on_rows=on_rows,
            components=[
                synchrony_support,
                narrative_support,
                blink_support,
                reward_support,
                boundary_support,
            ],
            fallback_cap=float(resolved.fallback_confidence_cap),
        )

        windows.append(
            CtaReceptionTimelineWindow(
                cta_id=marker.cta_id,
                cta_type=cta_type,
                start_ms=start_ms,
                end_ms=max(end_ms, start_ms + 1),
                score=round(score_unit * 100.0, 6),
                confidence=round(confidence, 6),
                reason=_cta_reason(
                    synchrony=synchrony_support,
                    blink=blink_support,
                    reward=reward_support,
                    boundary=boundary_support,
                    timing=timing_fit,
                ),
                synchrony_support=round(synchrony_support, 6),
                narrative_support=round(narrative_support, 6),
                blink_receptivity_support=round(blink_support, 6),
                reward_timing_support=round(reward_support, 6),
                boundary_coherence_support=round(boundary_support, 6),
                timing_fit_support=round(timing_fit, 6),
                flag_keys=flag_keys,
            )
        )

        sync_values.append(synchrony_support)
        narrative_values.append(narrative_support)
        blink_values.append(blink_support)
        reward_values.append(reward_support)
        boundary_values.append(boundary_support)
        overload_support_values.append(overload_support)

    windows = sorted(windows, key=lambda item: float(item.score), reverse=True)[
        : max(int(resolved.top_window_limit), 1)
    ]

    if not windows:
        return CtaReceptionDiagnostics(
            pathway=CtaReceptionPathway.insufficient_data,
            evidence_summary="CTA markers were present but insufficient timeline overlap was available to score CTA reception.",
            signals_used=[],
        )

    available_upstream = sum(
        1
        for item in (
            attentional_synchrony,
            narrative_control,
            blink_transport,
            reward_anticipation,
            boundary_encoding,
        )
        if item is not None and getattr(item, "pathway", "insufficient_data") != "insufficient_data"
    )
    pathway = (
        CtaReceptionPathway.multi_signal_model
        if available_upstream >= 3
        else CtaReceptionPathway.fallback_proxy
    )

    global_score = _weighted_window_score(windows)
    global_confidence = mean_optional([float(item.confidence) for item in windows]) or 0.45
    if pathway == CtaReceptionPathway.fallback_proxy:
        global_confidence = min(global_confidence, float(resolved.fallback_confidence_cap))

    signals_used = [
        "attentional_synchrony_index",
        "narrative_control_score",
        "blink_transport_score",
        "reward_anticipation_index",
        "boundary_encoding_score",
        "cta_marker_timeline_alignment",
    ]

    evidence_summary = (
        "CTA reception combines synchrony, narrative coherence, blink receptivity, reward timing, and boundary alignment "
        "to estimate whether CTA moments land while viewers remain ready to act."
    )
    if global_flags:
        evidence_summary += " Flags highlight timing or overload risks that can reduce CTA uptake."

    return CtaReceptionDiagnostics(
        pathway=pathway,
        global_score=round(global_score, 6),
        confidence=round(global_confidence, 6),
        cta_windows=windows,
        flags=global_flags,
        synchrony_support=round(mean_optional(sync_values) or 0.0, 6),
        narrative_support=round(mean_optional(narrative_values) or 0.0, 6),
        blink_receptivity_support=round(mean_optional(blink_values) or 0.0, 6),
        reward_timing_support=round(mean_optional(reward_values) or 0.0, 6),
        boundary_coherence_support=round(mean_optional(boundary_values) or 0.0, 6),
        overload_risk_support=round(mean_optional(overload_support_values) or 0.0, 6),
        evidence_summary=evidence_summary,
        signals_used=signals_used,
    )


def _classify_cta_type(marker: ReadoutCtaMarker) -> str:
    label = (marker.label or "").strip().lower()
    marker_id = (marker.cta_id or "").strip().lower()
    sample = f"{label} {marker_id}".strip()
    if _CTA_URL_PATTERN.search(sample):
        return "url"
    for cta_type, terms in _CTA_TYPE_KEYWORDS.items():
        for term in terms:
            if term in sample:
                return cta_type
    return "generic_cta"


def _cta_synchrony_support(
    diagnostics: Optional[AttentionalSynchronyDiagnostics],
    start_ms: int,
    end_ms: int,
) -> float:
    if diagnostics is None:
        return 0.5
    window_scores = [
        float(item.score) / 100.0
        for item in diagnostics.segment_scores
        if _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms))
    ]
    if window_scores:
        return clamp(mean_optional(window_scores) or 0.5, 0.0, 1.0)
    if diagnostics.global_score is not None:
        return clamp(float(diagnostics.global_score) / 100.0, 0.0, 1.0)
    return 0.45


def _cta_narrative_support(
    diagnostics: Optional[NarrativeControlDiagnostics],
    *,
    start_ms: int,
    end_ms: int,
    threshold: float,
) -> Tuple[float, float]:
    if diagnostics is None:
        return 0.5, 0.0
    scene_scores = [
        float(item.score) / 100.0
        for item in diagnostics.scene_scores
        if _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms))
    ]
    support = mean_optional(scene_scores)
    if support is None and diagnostics.global_score is not None:
        support = float(diagnostics.global_score) / 100.0
    support = clamp(support or 0.45, 0.0, 1.0)

    nearby_disruptions = [
        abs(float(item.contribution))
        for item in diagnostics.disruption_penalties
        if _distance_between_windows(start_ms, end_ms, int(item.start_ms), int(item.end_ms)) <= 1500
    ]
    disruption_score = mean_optional(nearby_disruptions) or 0.0
    fragmentation_penalty = clamp(disruption_score / max(threshold, 1e-6), 0.0, 1.0)
    support = clamp(support - (0.25 * fragmentation_penalty), 0.0, 1.0)
    return support, fragmentation_penalty


def _cta_blink_support(
    diagnostics: Optional[BlinkTransportDiagnostics],
    start_ms: int,
    end_ms: int,
) -> float:
    if diagnostics is None:
        return 0.5
    local_scores = []
    for item in diagnostics.segment_scores:
        if not _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms)):
            continue
        if item.cta_avoidance_signal is not None:
            local_scores.append(float(item.cta_avoidance_signal))
        else:
            local_scores.append(float(item.score) / 100.0)
    if local_scores:
        return clamp(mean_optional(local_scores) or 0.5, 0.0, 1.0)
    if diagnostics.cta_avoidance_score is not None:
        return clamp(float(diagnostics.cta_avoidance_score), 0.0, 1.0)
    if diagnostics.global_score is not None:
        return clamp(float(diagnostics.global_score) / 100.0, 0.0, 1.0)
    return 0.45


def _cta_reward_support(
    diagnostics: Optional[RewardAnticipationDiagnostics],
    *,
    start_ms: int,
    end_ms: int,
    proximity_ms: int,
) -> Tuple[float, float]:
    if diagnostics is None:
        return 0.5, 0.0

    payoff_scores = [
        float(item.score) / 100.0
        for item in diagnostics.payoff_windows
        if _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms))
    ]
    if payoff_scores:
        return clamp(mean_optional(payoff_scores) or 0.5, 0.0, 1.0), 1.0

    near_payoff = [
        float(item.score) / 100.0
        for item in diagnostics.payoff_windows
        if _distance_to_window(start_ms, end_ms, int(item.start_ms), int(item.end_ms)) <= proximity_ms
    ]
    if near_payoff:
        return clamp((mean_optional(near_payoff) or 0.5) * 0.88, 0.0, 1.0), 0.8

    ramp_scores = [
        float(item.score) / 100.0
        for item in diagnostics.anticipation_ramps
        if _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms))
    ]
    if ramp_scores:
        return clamp((mean_optional(ramp_scores) or 0.5) * 0.82, 0.0, 1.0), 0.65

    if diagnostics.global_score is not None:
        return clamp((float(diagnostics.global_score) / 100.0) * 0.7, 0.0, 1.0), 0.25
    return 0.4, 0.1


def _cta_boundary_support(
    diagnostics: Optional[BoundaryEncodingDiagnostics],
    *,
    start_ms: int,
    end_ms: int,
    proximity_ms: int,
) -> Tuple[float, float]:
    if diagnostics is None:
        return 0.5, 0.0

    strong_scores = [
        float(item.score) / 100.0
        for item in diagnostics.strong_windows
        if _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms))
    ]
    weak_scores = [
        float(item.score) / 100.0
        for item in diagnostics.weak_windows
        if _overlaps(start_ms, end_ms, int(item.start_ms), int(item.end_ms))
    ]
    support = 0.5
    if strong_scores:
        support = clamp(mean_optional(strong_scores) or 0.75, 0.0, 1.0)
    elif weak_scores:
        support = clamp((mean_optional(weak_scores) or 0.35) * 0.75, 0.0, 1.0)
    elif diagnostics.boundary_alignment_score is not None:
        support = clamp(float(diagnostics.boundary_alignment_score), 0.0, 1.0)

    overload_risk = 0.0
    for flag in diagnostics.flags:
        if flag.flag_key != "payload_overload_at_boundary":
            continue
        if flag.start_ms is None or flag.end_ms is None:
            overload_risk = max(overload_risk, 0.35)
            continue
        if _distance_to_window(start_ms, end_ms, int(flag.start_ms), int(flag.end_ms)) <= proximity_ms:
            overload_risk = max(
                overload_risk,
                0.75 if flag.severity.value == "high" else 0.55 if flag.severity.value == "medium" else 0.35,
            )
    if diagnostics.overload_risk_score is not None:
        overload_risk = max(overload_risk, float(diagnostics.overload_risk_score))

    support = clamp(support - (0.22 * overload_risk), 0.0, 1.0)
    return support, overload_risk


def _cta_timing_fit(
    *,
    start_ms: int,
    duration_ms: int,
    payoff_overlap: float,
    collapse_after_cta: bool,
    overload_risk: float,
    fragmentation_penalty: float,
    early_fraction: float,
    late_fraction: float,
) -> float:
    timing = 0.78
    early_cutoff = int(duration_ms * early_fraction)
    late_cutoff = int(duration_ms * late_fraction)
    if start_ms <= early_cutoff and payoff_overlap < 0.4:
        timing -= 0.24
    if start_ms >= late_cutoff:
        timing -= 0.18
    if collapse_after_cta:
        timing -= 0.2
    timing -= 0.16 * overload_risk
    timing -= 0.14 * fragmentation_penalty
    return clamp(timing, 0.0, 1.0)


def _cta_confidence(
    *,
    on_rows: Sequence[Dict[str, object]],
    components: Sequence[float],
    fallback_cap: float,
) -> float:
    quality = mean_optional(
        [
            to_float(row.get("tracking_confidence"))
            for row in on_rows
            if row.get("tracking_confidence") is not None
        ]
        + [
            to_float(row.get("quality_score"))
            for row in on_rows
            if row.get("quality_score") is not None
        ]
    ) or 0.45
    component_coverage = len([item for item in components if item is not None]) / float(max(len(components), 1))
    confidence = clamp((0.38 * quality) + (0.42 * component_coverage) + (0.2 * (1.0 if on_rows else 0.55)), 0.0, 1.0)
    if component_coverage < 0.6:
        confidence = min(confidence, fallback_cap)
    return confidence


def _cta_reason(
    *,
    synchrony: float,
    blink: float,
    reward: float,
    boundary: float,
    timing: float,
) -> str:
    factors = {
        "synchrony": synchrony,
        "blink receptivity": blink,
        "reward timing": reward,
        "boundary coherence": boundary,
        "timing fit": timing,
    }
    best = max(factors.items(), key=lambda item: item[1])[0]
    worst = min(factors.items(), key=lambda item: item[1])[0]
    return f"CTA window was strongest on {best} and weakest on {worst}."


def _weighted_window_score(windows: Sequence[CtaReceptionTimelineWindow]) -> float:
    weighted_sum = 0.0
    weight_total = 0.0
    for item in windows:
        confidence = float(item.confidence)
        weighted_sum += float(item.score) * confidence
        weight_total += confidence
    if weight_total <= 0.0:
        return mean_optional([float(item.score) for item in windows]) or 0.0
    return weighted_sum / weight_total


def _rows_in_window(
    rows: Sequence[Dict[str, object]],
    start_ms: int,
    end_ms: int,
) -> List[Dict[str, object]]:
    if not rows:
        return []
    normalized_start = int(start_ms)
    normalized_end = max(int(end_ms), normalized_start + 1)
    result = []
    for row in rows:
        bucket_start = int(to_float(row.get("bucket_start"), 0.0))
        if normalized_start <= bucket_start < normalized_end:
            result.append(row)
    return result


def _rowmean_optional(rows: Sequence[Dict[str, object]], key: str) -> Optional[float]:
    values = [
        to_float(row.get(key))
        for row in rows
        if row.get(key) is not None
    ]
    return mean_optional(values)


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return not (end_a <= start_b or end_b <= start_a)


def _distance_to_window(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    if _overlaps(start_a, end_a, start_b, end_b):
        return 0
    if end_a <= start_b:
        return start_b - end_a
    return start_a - end_b


def _distance_between_windows(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return _distance_to_window(start_a, end_a, start_b, end_b)



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
    config: CtaReceptionConfig,
    overrides: Mapping[str, Any],
) -> CtaReceptionConfig:
    allowed_fields = {field.name for field in fields(config)}
    updates: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in allowed_fields:
            continue
        updates[key] = value
    if not updates:
        return config
    return replace(config, **updates)

