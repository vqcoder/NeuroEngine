"""Tests for shared extractor quality-threshold loading."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from biotrace_extractor.quality import derive_quality_flags
from biotrace_extractor.quality_thresholds import get_extractor_quality_thresholds


class ExtractorQualityThresholdTests(unittest.TestCase):
    def test_extractor_quality_thresholds_load_defaults(self) -> None:
        get_extractor_quality_thresholds.cache_clear()
        thresholds = get_extractor_quality_thresholds()

        self.assertEqual(thresholds.low_light_max_brightness, 45.0)
        self.assertEqual(thresholds.blur_min_quality_score, 0.4)
        self.assertEqual(thresholds.face_visible_pct_min, 0.5)
        self.assertEqual(thresholds.head_pose_valid_pct_min, 0.6)

    def test_extractor_quality_thresholds_honor_override(self) -> None:
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(
                {
                    "extractor": {
                        "quality_flags": {
                            "low_light_max_brightness": 70.0,
                            "blur_min_quality_score": 0.8,
                            "face_visible_pct_min": 0.7,
                            "head_pose_valid_pct_min": 0.75,
                        }
                    }
                },
                handle,
            )
            handle.flush()
            handle.close()

            os.environ["QUALITY_THRESHOLDS_PATH"] = handle.name
            get_extractor_quality_thresholds.cache_clear()
            thresholds = get_extractor_quality_thresholds()

            self.assertEqual(thresholds.low_light_max_brightness, 70.0)
            self.assertEqual(thresholds.blur_min_quality_score, 0.8)
            self.assertEqual(thresholds.face_visible_pct_min, 0.7)
            self.assertEqual(thresholds.head_pose_valid_pct_min, 0.75)

            flags = derive_quality_flags(
                brightness=65.0,
                blur=132.0,  # blur score ~= 0.6 < custom 0.8 threshold
                face_visible_pct=0.69,
                head_pose_valid_pct=0.74,
            )
            self.assertEqual(
                flags,
                ["blur", "face_lost", "high_yaw_pitch", "low_light"],
            )
        finally:
            if "QUALITY_THRESHOLDS_PATH" in os.environ:
                del os.environ["QUALITY_THRESHOLDS_PATH"]
            get_extractor_quality_thresholds.cache_clear()
            try:
                os.unlink(handle.name)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
