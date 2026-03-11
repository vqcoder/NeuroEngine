"""Unit tests for baseline computation and normalization."""

from __future__ import annotations

import unittest

from biotrace_extractor.baseline import apply_baseline_correction, compute_au_baseline
from biotrace_extractor.schemas import AU_KEYS


def _au(value: float):
    return {key: value for key in AU_KEYS}


class BaselineTests(unittest.TestCase):
    def test_compute_and_apply_baseline(self) -> None:
        rows = [
            {"t_ms": 0, "landmarks_ok": True, "au": _au(0.2)},
            {"t_ms": 5_000, "landmarks_ok": True, "au": _au(0.4)},
            {"t_ms": 9_000, "landmarks_ok": True, "au": _au(0.6)},
            {"t_ms": 11_000, "landmarks_ok": True, "au": _au(1.0)},
        ]

        baseline = compute_au_baseline(rows, baseline_window_ms=10_000)
        for key in AU_KEYS:
            self.assertAlmostEqual(baseline[key], 0.4)

        apply_baseline_correction(rows, baseline)

        self.assertAlmostEqual(rows[0]["au_norm"]["AU12"], -0.2)
        self.assertAlmostEqual(rows[1]["au_norm"]["AU12"], 0.0)
        self.assertAlmostEqual(rows[2]["au_norm"]["AU12"], 0.2)
        self.assertAlmostEqual(rows[3]["au_norm"]["AU12"], 0.6)

    def test_baseline_defaults_to_zero_when_no_valid_rows(self) -> None:
        rows = [
            {"t_ms": 0, "landmarks_ok": False, "au": _au(0.9)},
            {"t_ms": 12_000, "landmarks_ok": True, "au": _au(0.4)},
        ]

        baseline = compute_au_baseline(rows, baseline_window_ms=10_000)
        for key in AU_KEYS:
            self.assertAlmostEqual(baseline[key], 0.0)

        apply_baseline_correction(rows, baseline)
        self.assertAlmostEqual(rows[0]["au_norm"]["AU04"], 0.9)


if __name__ == "__main__":
    unittest.main()
