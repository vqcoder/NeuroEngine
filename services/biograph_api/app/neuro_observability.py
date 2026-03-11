"""Observability helpers for neuro score telemetry, drift tracking, and privacy checks."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .config import get_settings
from .readout_metrics import clamp, mean_optional

from .schemas import (
    NeuroScoreMachineName,
    NeuroScoreStatus,
    NeuroScoreTaxonomy,
    ReadoutAggregateMetrics,
    ReadoutQualitySummary,
)

_CONFIDENCE_BINS: tuple[tuple[float, float], ...] = (
    (0.0, 0.2),
    (0.2, 0.4),
    (0.4, 0.6),
    (0.6, 0.8),
    (0.8, 1.0),
)

_PATHWAY_FIELDS: tuple[str, ...] = (
    "attentional_synchrony",
    "narrative_control",
    "blink_transport",
    "reward_anticipation",
    "boundary_encoding",
    "social_transmission",
    "self_relevance",
    "synthetic_lift_prior",
    "au_friction",
    "cta_reception",
)

_BIOMETRIC_PATHWAY_FIELDS: frozenset[str] = frozenset(
    {"attentional_synchrony", "blink_transport", "au_friction", "reward_anticipation"}
)



def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(float(item) for item in values)
    q_clamped = clamp(float(q), 0.0, 1.0)
    index = q_clamped * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _confidence_bin_label(low: float, high: float) -> str:
    return f"{low:.1f}-{high:.1f}"


def build_score_observations(
    taxonomy: NeuroScoreTaxonomy,
) -> Dict[str, Dict[str, Any]]:
    """Return normalized score observations for telemetry and drift tracking."""

    observations: Dict[str, Dict[str, Any]] = {}
    for machine_name in NeuroScoreMachineName:
        score = getattr(taxonomy.scores, machine_name.value)
        observations[machine_name.value] = {
            "status": score.status.value,
            "scalar_value": round(float(score.scalar_value), 6)
            if score.scalar_value is not None
            else None,
            "confidence": round(float(score.confidence), 6)
            if score.confidence is not None
            else None,
            "model_version": score.model_version,
        }
    return observations


def compute_missing_signal_rates(
    score_observations: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    total = len(score_observations)
    available = 0
    unavailable = 0
    insufficient_data = 0
    for payload in score_observations.values():
        status = str(payload.get("status") or NeuroScoreStatus.insufficient_data.value)
        if status == NeuroScoreStatus.available.value:
            available += 1
        elif status == NeuroScoreStatus.unavailable.value:
            unavailable += 1
        else:
            insufficient_data += 1
    missing = unavailable + insufficient_data
    return {
        "total_scores": total,
        "available_scores": available,
        "unavailable_scores": unavailable,
        "insufficient_data_scores": insufficient_data,
        "missing_signal_rate": round((missing / total), 6) if total else None,
        "availability_rate": round((available / total), 6) if total else None,
    }


def compute_confidence_distribution(
    score_observations: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    confidences: List[float] = []
    for payload in score_observations.values():
        if str(payload.get("status")) != NeuroScoreStatus.available.value:
            continue
        confidence = payload.get("confidence")
        if confidence is None:
            continue
        confidences.append(clamp(float(confidence), 0.0, 1.0))

    histogram = {_confidence_bin_label(low, high): 0 for low, high in _CONFIDENCE_BINS}
    for value in confidences:
        assigned = False
        for index, (low, high) in enumerate(_CONFIDENCE_BINS):
            is_last = index == len(_CONFIDENCE_BINS) - 1
            if (value >= low and value < high) or (is_last and value <= high):
                histogram[_confidence_bin_label(low, high)] += 1
                assigned = True
                break
        if not assigned:
            histogram[_confidence_bin_label(_CONFIDENCE_BINS[-1][0], _CONFIDENCE_BINS[-1][1])] += 1

    if not confidences:
        return {
            "count": 0,
            "mean": None,
            "p10": None,
            "p50": None,
            "p90": None,
            "histogram": histogram,
        }

    return {
        "count": len(confidences),
        "mean": round(sum(confidences) / len(confidences), 6),
        "p10": round(float(_quantile(confidences, 0.10) or 0.0), 6),
        "p50": round(float(_quantile(confidences, 0.50) or 0.0), 6),
        "p90": round(float(_quantile(confidences, 0.90) or 0.0), 6),
        "histogram": histogram,
    }


def compute_fallback_path_usage(
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
) -> Dict[str, Any]:
    if aggregate_metrics is None:
        return {
            "modules_evaluated": 0,
            "fallback_modules": [],
            "insufficient_modules": [],
            "fallback_rate": None,
            "pathways": {},
        }

    pathways: Dict[str, str] = {}
    fallback_modules: List[str] = []
    insufficient_modules: List[str] = []
    for field_name in _PATHWAY_FIELDS:
        diagnostics = getattr(aggregate_metrics, field_name, None)
        if diagnostics is None:
            continue
        pathway = getattr(diagnostics, "pathway", None)
        if pathway is None:
            continue
        pathway_value = pathway.value if hasattr(pathway, "value") else str(pathway)
        pathway_text = str(pathway_value)
        pathways[field_name] = pathway_text
        if "fallback" in pathway_text:
            fallback_modules.append(field_name)
        if pathway_text in {"insufficient_data", "disabled"}:
            insufficient_modules.append(field_name)

    module_count = len(pathways)
    return {
        "modules_evaluated": module_count,
        "fallback_modules": sorted(fallback_modules),
        "insufficient_modules": sorted(insufficient_modules),
        "fallback_rate": round(len(fallback_modules) / module_count, 6) if module_count else None,
        "pathways": pathways,
    }


def compute_score_drift(
    *,
    current_scores: Mapping[str, Mapping[str, Any]],
    reference_scores: Mapping[str, Mapping[str, Any]],
    alert_threshold: float,
) -> Dict[str, Any]:
    metric_deltas: Dict[str, float] = {}
    for metric_name, payload in current_scores.items():
        ref_payload = reference_scores.get(metric_name)
        if not isinstance(ref_payload, Mapping):
            continue
        scalar_value = payload.get("scalar_value")
        reference_value = ref_payload.get("scalar_value")
        if scalar_value is None or reference_value is None:
            continue
        metric_deltas[metric_name] = abs(float(scalar_value) - float(reference_value))

    if not metric_deltas:
        return {
            "status": "insufficient_history",
            "compared_metrics": 0,
            "mean_abs_delta": None,
            "max_abs_delta": None,
            "metrics_exceeding_threshold": [],
        }

    deltas = list(metric_deltas.values())
    mean_abs_delta = sum(deltas) / len(deltas)
    max_abs_delta = max(deltas)
    threshold = max(float(alert_threshold), 0.0)
    exceeding = sorted(
        metric_name
        for metric_name, delta in metric_deltas.items()
        if delta >= threshold
    )
    status = "alert" if exceeding else "ok"
    return {
        "status": status,
        "compared_metrics": len(metric_deltas),
        "mean_abs_delta": round(mean_abs_delta, 6),
        "max_abs_delta": round(max_abs_delta, 6),
        "metrics_exceeding_threshold": exceeding,
    }


def _privacy_ethics_checks(
    *,
    quality_summary: Optional[ReadoutQualitySummary],
    pathway_usage: Mapping[str, Any],
) -> Dict[str, Any]:
    pathways = pathway_usage.get("pathways")
    pathway_map = pathways if isinstance(pathways, Mapping) else {}
    biometric_signals_active = any(
        field_name in pathway_map
        and str(pathway_map[field_name]) not in {"insufficient_data", "disabled"}
        for field_name in _BIOMETRIC_PATHWAY_FIELDS
    )
    warnings: List[str] = []

    if biometric_signals_active and quality_summary is None:
        warnings.append("missing_quality_summary_for_biometrics")
    if biometric_signals_active and quality_summary is not None:
        tracking_confidence = quality_summary.mean_tracking_confidence
        if tracking_confidence is None:
            warnings.append("missing_tracking_confidence_for_biometrics")
        elif float(tracking_confidence) < 0.45:
            warnings.append("low_tracking_confidence_for_biometrics")

    trace_source = quality_summary.trace_source if quality_summary is not None else None
    if trace_source in {"synthetic_fallback", "mixed"}:
        warnings.append("fallback_trace_source_present")

    return {
        "biometric_signals_active": biometric_signals_active,
        "trace_source": trace_source,
        "low_confidence_windows": quality_summary.low_confidence_windows if quality_summary else None,
        "warnings": warnings,
    }


def _model_signature(score_observations: Mapping[str, Mapping[str, Any]]) -> str:
    versions = sorted(
        {
            str(payload.get("model_version"))
            for payload in score_observations.values()
            if payload.get("model_version")
        }
    )
    return "+".join(versions) if versions else "unknown"


def _load_history_entries(path: str, max_entries: int) -> List[Dict[str, Any]]:
    resolved = Path(path)
    if not path.strip() or not resolved.exists() or max_entries <= 0:
        return []

    tail: deque[Dict[str, Any]] = deque(maxlen=max_entries)
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                tail.append(payload)
    return list(tail)


def _append_history_entry(path: str, entry: Mapping[str, Any]) -> None:
    resolved = Path(path)
    if not path.strip():
        return
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True))
        handle.write("\n")


def _resolve_reference_entry(
    *,
    history_entries: Sequence[Mapping[str, Any]],
    current_entry: Mapping[str, Any],
) -> Optional[Mapping[str, Any]]:
    if not history_entries:
        return None
    current_signature = str(current_entry.get("model_signature") or "")
    current_video_id = str(current_entry.get("video_id") or "")

    for payload in reversed(history_entries):
        payload_signature = str(payload.get("model_signature") or "")
        payload_video_id = str(payload.get("video_id") or "")
        if (
            payload_video_id == current_video_id
            and payload_signature
            and payload_signature != current_signature
        ):
            return payload

    for payload in reversed(history_entries):
        payload_signature = str(payload.get("model_signature") or "")
        if payload_signature and payload_signature != current_signature:
            return payload

    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None



def build_neuro_observability_status(
    *,
    enabled: bool,
    history_path: str,
    history_max_entries: int,
    drift_alert_threshold: float,
    recent_window: int = 25,
) -> Dict[str, Any]:
    normalized_path = history_path.strip()
    history_enabled = bool(normalized_path)
    max_entries = max(int(history_max_entries), 1)
    window = max(int(recent_window), 1)
    history_entries = (
        _load_history_entries(normalized_path, max_entries) if history_enabled else []
    )
    recent_entries = history_entries[-window:]

    drift_alert_count = 0
    missing_rates: List[float] = []
    fallback_rates: List[float] = []
    confidence_means: List[float] = []

    for entry in recent_entries:
        drift = entry.get("drift")
        if isinstance(drift, Mapping):
            if str(drift.get("status")) == "alert":
                drift_alert_count += 1

        missing_signal_rates = entry.get("missing_signal_rates")
        if isinstance(missing_signal_rates, Mapping):
            value = _safe_float(missing_signal_rates.get("missing_signal_rate"))
            if value is not None:
                missing_rates.append(clamp(value, 0.0, 1.0))

        pathway_usage = entry.get("pathway_usage")
        if isinstance(pathway_usage, Mapping):
            value = _safe_float(pathway_usage.get("fallback_rate"))
            if value is not None:
                fallback_rates.append(clamp(value, 0.0, 1.0))

        confidence_distribution = entry.get("confidence_distribution")
        if isinstance(confidence_distribution, Mapping):
            value = _safe_float(confidence_distribution.get("mean"))
            if value is not None:
                confidence_means.append(clamp(value, 0.0, 1.0))

    latest_snapshot = None
    if history_entries:
        latest = history_entries[-1]
        drift = latest.get("drift")
        drift_payload = drift if isinstance(drift, Mapping) else {}
        metric_list = drift_payload.get("metrics_exceeding_threshold")
        if isinstance(metric_list, list):
            metrics_exceeding_threshold = [str(item) for item in metric_list if item is not None]
        else:
            metrics_exceeding_threshold = []

        latest_missing = None
        missing_signal_rates = latest.get("missing_signal_rates")
        if isinstance(missing_signal_rates, Mapping):
            value = _safe_float(missing_signal_rates.get("missing_signal_rate"))
            if value is not None:
                latest_missing = clamp(value, 0.0, 1.0)

        latest_fallback = None
        pathway_usage = latest.get("pathway_usage")
        if isinstance(pathway_usage, Mapping):
            value = _safe_float(pathway_usage.get("fallback_rate"))
            if value is not None:
                latest_fallback = clamp(value, 0.0, 1.0)

        latest_confidence = None
        confidence_distribution = latest.get("confidence_distribution")
        if isinstance(confidence_distribution, Mapping):
            value = _safe_float(confidence_distribution.get("mean"))
            if value is not None:
                latest_confidence = clamp(value, 0.0, 1.0)

        latest_snapshot = {
            "recorded_at": latest.get("recorded_at"),
            "video_id": latest.get("video_id"),
            "variant_id": latest.get("variant_id"),
            "model_signature": latest.get("model_signature"),
            "drift_status": drift_payload.get("status"),
            "missing_signal_rate": latest_missing,
            "fallback_rate": latest_fallback,
            "confidence_mean": latest_confidence,
            "metrics_exceeding_threshold": metrics_exceeding_threshold,
        }

    warnings: List[str] = []
    if not enabled:
        warnings.append("observability_disabled")
    if not history_enabled:
        warnings.append("history_path_not_configured")
    elif not history_entries:
        warnings.append("no_history_entries")
    if drift_alert_count > 0:
        warnings.append("recent_drift_alerts_present")

    status = "ok"
    if not enabled:
        status = "disabled"
    elif not history_enabled:
        status = "no_history_config"
    elif not history_entries:
        status = "no_data"
    elif latest_snapshot is not None and latest_snapshot.get("drift_status") == "alert":
        status = "alert"

    return {
        "status": status,
        "enabled": bool(enabled),
        "history_enabled": history_enabled,
        "history_entry_count": len(history_entries),
        "history_max_entries": max_entries,
        "drift_alert_threshold": max(float(drift_alert_threshold), 0.0),
        "recent_window": window,
        "recent_snapshot_count": len(recent_entries),
        "recent_drift_alert_count": drift_alert_count,
        "recent_drift_alert_rate": (
            round(drift_alert_count / len(recent_entries), 6) if recent_entries else None
        ),
        "mean_missing_signal_rate": mean_optional(missing_rates),
        "mean_fallback_rate": mean_optional(fallback_rates),
        "mean_confidence": mean_optional(confidence_means),
        "latest_snapshot": latest_snapshot,
        "warnings": warnings,
    }


def build_neuro_observability_snapshot(
    *,
    video_id: str,
    variant_id: Optional[str],
    aggregate: bool,
    included_sessions: int,
    taxonomy: NeuroScoreTaxonomy,
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
    quality_summary: Optional[ReadoutQualitySummary],
    drift_alert_threshold: float,
    history_entries: Sequence[Mapping[str, Any]] = (),
    recorded_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    recorded = recorded_at or datetime.now(timezone.utc)
    score_observations = build_score_observations(taxonomy)
    pathway_usage = compute_fallback_path_usage(aggregate_metrics)
    confidence_distribution = compute_confidence_distribution(score_observations)
    missing_signal_rates = compute_missing_signal_rates(score_observations)
    privacy_ethics_checks = _privacy_ethics_checks(
        quality_summary=quality_summary,
        pathway_usage=pathway_usage,
    )

    snapshot: Dict[str, Any] = {
        "event_type": "neuro_score_observability",
        "recorded_at": _to_utc_iso(recorded),
        "video_id": str(video_id),
        "variant_id": variant_id,
        "aggregate": bool(aggregate),
        "included_sessions": max(int(included_sessions), 0),
        "schema_version": taxonomy.schema_version,
        "model_signature": _model_signature(score_observations),
        "model_versions": sorted(
            {
                str(item.get("model_version"))
                for item in score_observations.values()
                if item.get("model_version")
            }
        ),
        "scores": score_observations,
        "missing_signal_rates": missing_signal_rates,
        "confidence_distribution": confidence_distribution,
        "pathway_usage": pathway_usage,
        "privacy_ethics_checks": privacy_ethics_checks,
    }

    reference = _resolve_reference_entry(
        history_entries=history_entries,
        current_entry=snapshot,
    )
    if reference is None:
        snapshot["drift"] = {
            "status": "no_reference",
            "compared_metrics": 0,
            "mean_abs_delta": None,
            "max_abs_delta": None,
            "metrics_exceeding_threshold": [],
        }
        return snapshot

    reference_scores = reference.get("scores")
    if not isinstance(reference_scores, Mapping):
        snapshot["drift"] = {
            "status": "insufficient_history",
            "compared_metrics": 0,
            "mean_abs_delta": None,
            "max_abs_delta": None,
            "metrics_exceeding_threshold": [],
        }
        return snapshot

    drift = compute_score_drift(
        current_scores=score_observations,
        reference_scores=reference_scores,  # type: ignore[arg-type]
        alert_threshold=drift_alert_threshold,
    )
    drift["reference_model_signature"] = reference.get("model_signature")
    drift["reference_recorded_at"] = reference.get("recorded_at")
    snapshot["drift"] = drift
    return snapshot


def emit_neuro_observability_snapshot(
    *,
    logger,
    video_id: str,
    variant_id: Optional[str],
    aggregate: bool,
    included_sessions: int,
    taxonomy: Optional[NeuroScoreTaxonomy],
    aggregate_metrics: Optional[ReadoutAggregateMetrics],
    quality_summary: Optional[ReadoutQualitySummary],
) -> Optional[Dict[str, Any]]:
    """Emit low-overhead observability telemetry for neuro score stack behavior."""

    settings = get_settings()
    if not settings.neuro_observability_enabled or taxonomy is None:
        return None

    history_path = settings.neuro_observability_history_path.strip()
    max_entries = max(int(settings.neuro_observability_history_max_entries), 1)
    history_entries = _load_history_entries(history_path, max_entries) if history_path else []

    snapshot = build_neuro_observability_snapshot(
        video_id=video_id,
        variant_id=variant_id,
        aggregate=aggregate,
        included_sessions=included_sessions,
        taxonomy=taxonomy,
        aggregate_metrics=aggregate_metrics,
        quality_summary=quality_summary,
        drift_alert_threshold=float(settings.neuro_observability_drift_alert_threshold),
        history_entries=history_entries,
    )

    logger.info("neuro_score_observability %s", json.dumps(snapshot, sort_keys=True))
    if history_path:
        _append_history_entry(history_path, snapshot)
    return snapshot
