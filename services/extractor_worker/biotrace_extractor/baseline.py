"""Per-participant baseline computation and AU normalization."""

from __future__ import annotations

from typing import Dict, MutableMapping, Sequence

from .schemas import AU_KEYS


def compute_au_baseline(
    rows: Sequence[MutableMapping[str, object]], baseline_window_ms: int = 10_000
) -> Dict[str, float]:
    """Compute mean AU baseline from rows in the initial baseline window.

    Only rows with `landmarks_ok=True` are included.
    """

    sums = {key: 0.0 for key in AU_KEYS}
    counts = {key: 0 for key in AU_KEYS}

    for row in rows:
        t_ms = int(row.get("t_ms", 0))
        landmarks_ok = bool(row.get("landmarks_ok", False))
        if t_ms > baseline_window_ms or not landmarks_ok:
            continue

        au = row.get("au")
        if not isinstance(au, dict):
            continue

        for key in AU_KEYS:
            value = au.get(key, 0.0)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = 0.0
            sums[key] += numeric
            counts[key] += 1

    baseline: Dict[str, float] = {}
    for key in AU_KEYS:
        if counts[key] == 0:
            baseline[key] = 0.0
        else:
            baseline[key] = sums[key] / float(counts[key])

    return baseline


def normalize_au(au: Dict[str, float], baseline: Dict[str, float]) -> Dict[str, float]:
    """Baseline-correct raw AU dictionary."""

    return {
        key: round(float(au.get(key, 0.0)) - float(baseline.get(key, 0.0)), 6)
        for key in AU_KEYS
    }


def apply_baseline_correction(
    rows: Sequence[MutableMapping[str, object]], baseline: Dict[str, float]
) -> None:
    """Mutate rows in-place to append `au_norm`."""

    for row in rows:
        au = row.get("au")
        if not isinstance(au, dict):
            row["au_norm"] = {key: 0.0 for key in AU_KEYS}
            continue

        numeric_au = {key: float(au.get(key, 0.0)) for key in AU_KEYS}
        row["au_norm"] = normalize_au(numeric_au, baseline)
