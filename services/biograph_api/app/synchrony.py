"""Cross-participant AU04 synchrony computation.

Computes per-second inter-participant AU04 correlation across sessions
to detect narrative tension peaks.  Only activates when 2+ sessions
exist for the same video; gracefully returns empty results otherwise.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional


def _pearson_correlation(x: List[float], y: List[float]) -> float:
    """Pearson correlation coefficient for two equal-length lists.

    Returns 0.0 when inputs are degenerate (length < 2, zero variance).
    """

    n = len(x)
    if n < 2 or n != len(y):
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    denom = math.sqrt(var_x * var_y)
    if denom < 1e-12:
        return 0.0

    return cov / denom


def _pairwise_mean_correlation(session_values: List[List[float]]) -> float:
    """Mean Pearson correlation across all unique session pairs."""

    n = len(session_values)
    if n < 2:
        return 0.0

    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += _pearson_correlation(session_values[i], session_values[j])
            count += 1

    return total / count if count > 0 else 0.0


def compute_au04_synchrony(
    session_traces: List[List[Dict[str, Any]]],
    window_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """Compute per-window inter-participant AU04 correlation.

    Parameters
    ----------
    session_traces:
        One list of trace-point dicts per session.  Each dict must have
        ``video_time_ms`` (int) and ``au`` (dict with ``"AU04"`` key).
    window_ms:
        Time-bin width in milliseconds.

    Returns
    -------
    List of window dicts with ``video_time_ms``, ``synchrony_score``,
    ``session_count``, and ``is_tension_peak``.
    """

    if len(session_traces) < 2:
        return []

    # Bin AU04 values by time window per session.
    # bins[bucket_key][session_index] -> list of AU04 values
    bins: Dict[int, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))

    for session_idx, traces in enumerate(session_traces):
        for tp in traces:
            vt = tp.get("video_time_ms")
            au = tp.get("au")
            if vt is None or au is None:
                continue
            au04 = au.get("AU04")
            if au04 is None:
                continue
            bucket = (int(vt) // window_ms) * window_ms
            bins[bucket][session_idx].append(float(au04))

    results: List[Dict[str, Any]] = []
    for bucket in sorted(bins.keys()):
        session_map = bins[bucket]
        # Only consider buckets with 2+ sessions contributing
        sessions_with_data = {
            sid: vals for sid, vals in session_map.items() if len(vals) > 0
        }
        if len(sessions_with_data) < 2:
            continue

        # Use the mean AU04 per session per bucket for correlation
        session_means = [sum(v) / len(v) for v in sessions_with_data.values()]

        # For a single bucket, we can't compute temporal correlation.
        # Instead, compute the coefficient of variation to measure agreement.
        # When all sessions agree (low CV), synchrony is high.
        mean_val = sum(session_means) / len(session_means)
        if abs(mean_val) < 1e-9:
            # All near-zero — sessions agree on no AU04 activation
            synchrony = 1.0 if all(abs(v) < 1e-6 for v in session_means) else 0.0
        else:
            variance = sum((v - mean_val) ** 2 for v in session_means) / len(session_means)
            cv = math.sqrt(variance) / abs(mean_val) if abs(mean_val) > 1e-9 else 0.0
            # Map CV to synchrony: CV=0 → synchrony=1, CV≥2 → synchrony=0
            synchrony = max(0.0, min(1.0, 1.0 - cv / 2.0))

        synchrony = round(synchrony, 6)
        session_count = len(sessions_with_data)
        is_peak = synchrony > 0.65 and session_count >= 2

        results.append({
            "video_time_ms": bucket,
            "synchrony_score": synchrony,
            "session_count": session_count,
            "is_tension_peak": is_peak,
        })

    return results


def compute_narrative_tension_summary(
    synchrony_windows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarise synchrony windows into a narrative tension report."""

    if not synchrony_windows:
        return {
            "peak_count": 0,
            "mean_synchrony": None,
            "max_synchrony": None,
            "tension_peaks": [],
        }

    scores = [w["synchrony_score"] for w in synchrony_windows]
    peaks = sorted(
        [w for w in synchrony_windows if w.get("is_tension_peak")],
        key=lambda w: w["synchrony_score"],
        reverse=True,
    )[:10]

    return {
        "peak_count": len(peaks),
        "mean_synchrony": round(sum(scores) / len(scores), 6),
        "max_synchrony": round(max(scores), 6),
        "tension_peaks": peaks,
    }
