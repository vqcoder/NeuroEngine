"""Reliability Score Engine.

Examines every model score in a ReadoutPayload against its original design
specification and returns a structured reliability report.

Score breakdown (total 100 pts):
  availability_score   30 pts  — what % of neuro scores computed vs insufficient_data
  range_validity_score 20 pts  — all available scores within designed bounds (0-100 scalar, 0-1 confidence)
  pathway_quality_score 20 pts — direct pathways vs fallback proxies (direct = higher quality)
  signal_health_score  15 pts  — raw traces are non-flat and in physiological range
  duration_accuracy_score 10 pts — usable_seconds bounded correctly by video duration
  rollup_integrity_score   5 pts — rollups present whenever their component scores are available

A score of 100 means every score is computed accurately on a direct pathway with
healthy underlying signals. A score of 0 means nothing could be computed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .readout_metrics import clamp

# ---------------------------------------------------------------------------
# Public data classes — framework-independent so this can run anywhere
# ---------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "availability": 30,
    "range_validity": 20,
    "pathway_quality": 20,
    "signal_health": 15,
    "duration_accuracy": 10,
    "rollup_integrity": 5,
}

INDIVIDUAL_SCORE_NAMES = [
    "arrest_score",
    "attentional_synchrony_index",
    "narrative_control_score",
    "blink_transport_score",
    "boundary_encoding_score",
    "reward_anticipation_index",
    "social_transmission_score",
    "self_relevance_score",
    "cta_reception_score",
    "synthetic_lift_prior",
    "au_friction_score",
]

ROLLUP_NAMES = [
    "organic_reach_prior",
    "paid_lift_prior",
    "brand_memory_prior",
]

# Pathway labels that count as "direct" quality (vs fallback proxies)
_DIRECT_PATHWAY_LABELS = frozenset({
    "direct_panel_blink",
    "direct_panel_gaze",
    "timeline_grammar",
    "timeline_dynamics",
    "timeline_boundary_model",
    "annotation_augmented",
    "timeline_signal_model",
    "contextual_personalization",
    "survey_augmented",
    "multi_signal_model",
    "au_signal_model",
    "taxonomy_regression",
})

# Physiological blink rate range (blinks/second)
_BLINK_RATE_MIN = 0.05   # ~3 blinks/min
_BLINK_RATE_MAX = 0.70   # ~42 blinks/min
_BLINK_RATE_MIN_RANGE = 0.04  # minimum visible variation

# Minimum reward proxy and attention variation to be considered non-flat
_REWARD_MIN_RANGE = 5.0
_ATTENTION_MIN_RANGE = 3.0


@dataclass
class ScoreReliabilityDetail:
    machine_name: str
    status: str  # "available" | "insufficient_data" | "unavailable" | "missing"
    scalar_value: Optional[float]
    confidence: Optional[float]
    pathway: Optional[str]
    issues: List[str] = field(default_factory=list)
    # Derived per-score reliability sub-score (0-1)
    score_reliability: float = 0.0


@dataclass
class ReliabilityScore:
    """Full reliability report for one readout."""

    # Overall score 0-100
    overall: float

    # Sub-dimension scores 0-100 each
    availability_score: float
    range_validity_score: float
    pathway_quality_score: float
    signal_health_score: float
    duration_accuracy_score: float
    rollup_integrity_score: float

    # Individual score details
    score_details: List[ScoreReliabilityDetail]

    # High-level issues list
    issues: List[str]

    # Metadata
    scores_available: int
    scores_total: int
    model_version: str = "reliability_v1"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _series_values(points: Sequence[Any]) -> List[float]:
    """Extract non-None float values from trace point dicts or objects."""
    out: List[float] = []
    for p in points:
        v = p.get("value") if isinstance(p, dict) else getattr(p, "value", None)
        if v is not None:
            try:
                fv = float(v)
                if math.isfinite(fv):
                    out.append(fv)
            except (ValueError, TypeError):
                pass
    return out


def _provenance(score: Any) -> Optional[str]:
    return getattr(score, "provenance", None) or (score.get("provenance") if isinstance(score, dict) else None)


def _get_score_field(score: Any, field: str) -> Any:
    if isinstance(score, dict):
        return score.get(field)
    return getattr(score, field, None)


# ---------------------------------------------------------------------------
# Core reliability computation
# ---------------------------------------------------------------------------

def compute_reliability_score(payload: Any) -> ReliabilityScore:
    """Compute a ReliabilityScore from a ReadoutPayload (Pydantic model or dict)."""

    def _get(obj: Any, *keys: str, default: Any = None) -> Any:
        for key in keys:
            if obj is None:
                return default
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                obj = getattr(obj, key, None)
        return obj if obj is not None else default

    issues: List[str] = []

    # ------------------------------------------------------------------
    # 1. AVAILABILITY — what % of neuro scores were computed
    # ------------------------------------------------------------------
    neuro_scores = _get(payload, "neuro_scores")
    scores_dict = _get(neuro_scores, "scores") or {}
    rollups_dict = _get(neuro_scores, "rollups") or {}

    score_details: List[ScoreReliabilityDetail] = []
    available_count = 0

    def _extract_score(name: str, container: Any) -> ScoreReliabilityDetail:
        if isinstance(container, dict):
            entry = container.get(name)
        else:
            entry = getattr(container, name, None) if container else None

        if entry is None:
            return ScoreReliabilityDetail(
                machine_name=name, status="missing",
                scalar_value=None, confidence=None, pathway=None,
                issues=[f"{name} missing from neuro_scores entirely"],
            )

        _raw_status = _get_score_field(entry, "status")
        # Handle enum values like NeuroScoreStatus.available → "available"
        if hasattr(_raw_status, "value"):
            status = str(_raw_status.value)
        elif _raw_status is not None:
            raw = str(_raw_status)
            status = raw.rsplit(".", 1)[-1] if "." in raw else raw
        else:
            status = "missing"
        sv = _get_score_field(entry, "scalar_value")
        conf = _get_score_field(entry, "confidence")
        prov = _get_score_field(entry, "provenance")
        # Extract pathway label from provenance string like "pathway=direct_panel_blink ..."
        pathway: Optional[str] = None
        if prov:
            for word in str(prov).replace(",", " ").split():
                if "=" in word:
                    k, _, v = word.partition("=")
                    if k.strip() == "pathway":
                        pathway = v.strip()
                        break
                # Also check if provenance directly is a pathway label
                if word in _DIRECT_PATHWAY_LABELS or word.startswith("fallback") or word.startswith("insufficient"):
                    pathway = word

        detail_issues: List[str] = []
        score_reliability = 0.0

        if status == "available":
            if sv is None:
                detail_issues.append(f"{name}: status=available but scalar_value is None")
            elif not (0.0 <= float(sv) <= 100.0):
                detail_issues.append(f"{name}: scalar_value {sv:.2f} outside [0, 100]")
            if conf is None:
                detail_issues.append(f"{name}: status=available but confidence is None")
            elif not (0.0 <= float(conf) <= 1.0):
                detail_issues.append(f"{name}: confidence {conf:.4f} outside [0, 1]")
            if not detail_issues:
                score_reliability = 1.0
            else:
                score_reliability = 0.4
        elif status == "insufficient_data":
            score_reliability = 0.0
        elif status == "unavailable":
            score_reliability = 0.2  # acceptable for disabled features

        return ScoreReliabilityDetail(
            machine_name=name, status=status,
            scalar_value=float(sv) if sv is not None else None,
            confidence=float(conf) if conf is not None else None,
            pathway=pathway,
            issues=detail_issues,
            score_reliability=score_reliability,
        )

    all_score_names = INDIVIDUAL_SCORE_NAMES + ROLLUP_NAMES
    score_details = [
        _extract_score(name, scores_dict if name in INDIVIDUAL_SCORE_NAMES else rollups_dict)
        for name in all_score_names
    ]

    individual_details = [d for d in score_details if d.machine_name in INDIVIDUAL_SCORE_NAMES]
    available_count = sum(1 for d in individual_details if d.status == "available")
    total_individual = len(INDIVIDUAL_SCORE_NAMES)
    availability_score = clamp((available_count / max(total_individual, 1)) * 100.0, 0.0, 100.0)

    if available_count == 0:
        issues.append("No individual neuro scores are available — check if recording has sufficient watch data.")
    elif available_count < total_individual // 2:
        issues.append(f"Only {available_count}/{total_individual} neuro scores available — limited data quality.")

    # ------------------------------------------------------------------
    # 2. RANGE VALIDITY — available scores within designed bounds
    # ------------------------------------------------------------------
    range_issues: List[str] = []
    range_valid = 0
    range_checked = 0

    for d in score_details:
        if d.status != "available":
            continue
        range_checked += 1
        ok = True
        if d.scalar_value is not None and not (0.0 <= d.scalar_value <= 100.0):
            range_issues.append(f"{d.machine_name}: scalar_value {d.scalar_value:.2f} OOB")
            ok = False
        if d.confidence is not None and not (0.0 <= d.confidence <= 1.0):
            range_issues.append(f"{d.machine_name}: confidence {d.confidence:.4f} OOB")
            ok = False
        if ok:
            range_valid += 1

    range_validity_score = (
        clamp((range_valid / max(range_checked, 1)) * 100.0, 0.0, 100.0) if range_checked > 0 else 100.0
    )
    issues.extend(range_issues)

    # ------------------------------------------------------------------
    # 3. PATHWAY QUALITY — direct vs fallback pathways
    # ------------------------------------------------------------------
    pathway_scores: List[float] = []

    for d in individual_details:
        if d.status not in ("available", "unavailable"):
            continue
        prov = None
        # Re-read provenance from original entry for more detail
        if isinstance(scores_dict, dict):
            entry = scores_dict.get(d.machine_name)
        else:
            entry = getattr(scores_dict, d.machine_name, None)
        if entry is not None:
            prov = str(_get_score_field(entry, "provenance") or "")

        if not prov:
            continue

        if any(label in prov for label in _DIRECT_PATHWAY_LABELS):
            pathway_scores.append(1.0)
        elif "fallback" in prov or "sparse" in prov or "proxy" in prov:
            pathway_scores.append(0.5)
        elif "insufficient" in prov:
            pathway_scores.append(0.0)
        else:
            pathway_scores.append(0.75)  # unknown but computed

    pathway_quality_score = (
        clamp((sum(pathway_scores) / max(len(pathway_scores), 1)) * 100.0, 0.0, 100.0)
        if pathway_scores else 50.0
    )

    fallback_count = sum(1 for s in pathway_scores if s < 0.75)
    if fallback_count > len(INDIVIDUAL_SCORE_NAMES) // 2:
        issues.append(
            f"{fallback_count} scores are on fallback pathways — higher quality data would improve accuracy."
        )

    # ------------------------------------------------------------------
    # 4. SIGNAL HEALTH — raw trace variation
    # ------------------------------------------------------------------
    traces = _get(payload, "traces") or {}

    def _trace_vals(key: str) -> List[float]:
        pts = traces.get(key, []) if isinstance(traces, dict) else getattr(traces, key, [])
        return _series_values(pts or [])

    blink_vals = _trace_vals("blink_rate")
    reward_vals = _trace_vals("reward_proxy")
    attention_vals = _trace_vals("attention_score")

    signal_sub_scores: List[float] = []
    signal_issues: List[str] = []

    # Blink rate: range and physiological bounds
    if blink_vals:
        blink_range = max(blink_vals) - min(blink_vals)
        blink_in_bounds = all(_BLINK_RATE_MIN <= v <= _BLINK_RATE_MAX for v in blink_vals)
        if blink_range < _BLINK_RATE_MIN_RANGE:
            signal_sub_scores.append(0.3)
            signal_issues.append(
                f"Blink rate is nearly flat (range={blink_range:.4f}) — variance correction may not be sufficient."
            )
        elif not blink_in_bounds:
            out_pct = sum(1 for v in blink_vals if not (_BLINK_RATE_MIN <= v <= _BLINK_RATE_MAX)) / len(blink_vals)
            signal_sub_scores.append(max(0.5, 1.0 - out_pct))
            signal_issues.append(f"Blink rate has {out_pct:.0%} of values outside physiological range.")
        else:
            signal_sub_scores.append(1.0)
    else:
        signal_sub_scores.append(0.0)
        signal_issues.append("No blink_rate trace data.")

    # Reward proxy variation
    if reward_vals:
        reward_range = max(reward_vals) - min(reward_vals)
        if reward_range < _REWARD_MIN_RANGE:
            signal_sub_scores.append(0.3)
            signal_issues.append(f"Reward proxy is nearly flat (range={reward_range:.2f}).")
        else:
            signal_sub_scores.append(1.0)
    else:
        signal_sub_scores.append(0.0)
        signal_issues.append("No reward_proxy trace data.")

    # Attention variation
    if attention_vals:
        attention_range = max(attention_vals) - min(attention_vals)
        if attention_range < _ATTENTION_MIN_RANGE:
            signal_sub_scores.append(0.4)
            signal_issues.append(f"Attention is nearly flat (range={attention_range:.2f}).")
        else:
            signal_sub_scores.append(1.0)
    else:
        signal_sub_scores.append(0.0)
        signal_issues.append("No attention_score trace data.")

    signal_health_score = clamp(
        (sum(signal_sub_scores) / max(len(signal_sub_scores), 1)) * 100.0, 0.0, 100.0
    )
    issues.extend(signal_issues)

    # ------------------------------------------------------------------
    # 5. DURATION ACCURACY — usable_seconds vs trace extent
    # ------------------------------------------------------------------
    quality_summary = _get(payload, "quality_summary") or {}
    usable_seconds = _get(quality_summary, "usable_seconds")
    total_trace_points = _get(quality_summary, "total_trace_points") or 0
    duration_ms_payload = _get(payload, "duration_ms")

    duration_accuracy_score = 100.0
    if usable_seconds is not None and attention_vals:
        # Estimate how many seconds of data we actually have from trace windows
        # Each trace window is 1s by default; len(attention_vals) = number of windows
        estimated_data_seconds = len(attention_vals)
        reported_usable = float(usable_seconds)

        if estimated_data_seconds > 0 and reported_usable > estimated_data_seconds * 2.5:
            duration_accuracy_score = 30.0
            issues.append(
                f"usable_seconds ({reported_usable:.1f}s) is {reported_usable / estimated_data_seconds:.1f}× "
                f"the trace data extent ({estimated_data_seconds}s) — duration_ms may be incorrectly set."
            )
        elif estimated_data_seconds > 0 and reported_usable > estimated_data_seconds * 1.5:
            duration_accuracy_score = 65.0
            issues.append(
                f"usable_seconds ({reported_usable:.1f}s) slightly exceeds trace extent ({estimated_data_seconds}s)."
            )

    # ------------------------------------------------------------------
    # 6. ROLLUP INTEGRITY — rollups present when components available
    # ------------------------------------------------------------------
    rollup_component_map = {
        "organic_reach_prior": ["arrest_score", "narrative_control_score", "self_relevance_score",
                                 "social_transmission_score", "cta_reception_score"],
        "paid_lift_prior": ["synthetic_lift_prior", "cta_reception_score", "reward_anticipation_index",
                            "attentional_synchrony_index", "arrest_score"],
        "brand_memory_prior": ["boundary_encoding_score", "narrative_control_score", "self_relevance_score",
                               "reward_anticipation_index", "blink_transport_score"],
    }

    available_individuals = {d.machine_name for d in individual_details if d.status == "available"}
    rollup_sub: List[float] = []

    for rollup_name, components in rollup_component_map.items():
        rollup_detail = next((d for d in score_details if d.machine_name == rollup_name), None)
        components_available = sum(1 for c in components if c in available_individuals)
        if components_available >= 2:
            if rollup_detail is None or rollup_detail.status != "available":
                rollup_sub.append(0.0)
                issues.append(
                    f"{rollup_name} should be available ({components_available}/{len(components)} "
                    f"components computed) but is {rollup_detail.status if rollup_detail else 'missing'}."
                )
            else:
                rollup_sub.append(1.0)
        else:
            rollup_sub.append(0.8)  # insufficient components — acceptable

    rollup_integrity_score = clamp(
        (sum(rollup_sub) / max(len(rollup_sub), 1)) * 100.0, 0.0, 100.0
    ) if rollup_sub else 100.0

    # ------------------------------------------------------------------
    # OVERALL SCORE
    # ------------------------------------------------------------------
    overall = clamp(
        (availability_score * SCORE_WEIGHTS["availability"] / 100.0)
        + (range_validity_score * SCORE_WEIGHTS["range_validity"] / 100.0)
        + (pathway_quality_score * SCORE_WEIGHTS["pathway_quality"] / 100.0)
        + (signal_health_score * SCORE_WEIGHTS["signal_health"] / 100.0)
        + (duration_accuracy_score * SCORE_WEIGHTS["duration_accuracy"] / 100.0)
        + (rollup_integrity_score * SCORE_WEIGHTS["rollup_integrity"] / 100.0),
        0.0,
        100.0,
    )

    return ReliabilityScore(
        overall=round(overall, 2),
        availability_score=round(availability_score, 2),
        range_validity_score=round(range_validity_score, 2),
        pathway_quality_score=round(pathway_quality_score, 2),
        signal_health_score=round(signal_health_score, 2),
        duration_accuracy_score=round(duration_accuracy_score, 2),
        rollup_integrity_score=round(rollup_integrity_score, 2),
        score_details=score_details,
        issues=issues,
        scores_available=available_count,
        scores_total=total_individual,
    )
