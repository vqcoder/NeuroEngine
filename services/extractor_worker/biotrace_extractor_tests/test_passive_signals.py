"""Fixture-driven tests for passive-signal and quality proxy behavior."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from biotrace_extractor.quality import (
    blur_quality_score,
    compose_quality_score,
    compose_tracking_confidence,
    derive_quality_flags,
    estimate_gaze_on_screen_proxy,
    estimate_head_pose_confidence,
)
from biotrace_extractor.rolling import RollingSignalTracker


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class PassiveSignalFixtureTests(unittest.TestCase):
    def test_low_light_fixture_reduces_quality_score(self) -> None:
        payload = _load_fixture("quality_cases.json")
        low_light = payload["low_light"]
        well_lit = payload["well_lit"]

        low_score = compose_quality_score(**low_light)
        well_lit_score = compose_quality_score(**well_lit)

        self.assertLess(low_score, well_lit_score)
        self.assertLess(low_score, 0.5)

    def test_blur_fixture_penalizes_blurry_frames(self) -> None:
        payload = _load_fixture("quality_cases.json")
        values = payload["blur_proxy_values"]

        sharp_score = blur_quality_score(values["sharp"])
        blurry_score = blur_quality_score(values["blurry"])

        self.assertGreater(sharp_score, blurry_score)
        self.assertLess(blurry_score, 0.2)

    def test_large_head_rotation_reduces_coarse_gaze_proxy(self) -> None:
        payload = _load_fixture("quality_cases.json")
        frontal = payload["frontal_pose"]
        rotated = payload["large_rotation_pose"]

        frontal_prob, frontal_conf = estimate_gaze_on_screen_proxy(
            head_pose=frontal["head_pose"],
            center_offset=frontal["center_offset"],
            eye_openness=frontal["eye_openness"],
            face_presence_confidence=frontal["face_presence_confidence"],
        )
        rotated_prob, rotated_conf = estimate_gaze_on_screen_proxy(
            head_pose=rotated["head_pose"],
            center_offset=rotated["center_offset"],
            eye_openness=rotated["eye_openness"],
            face_presence_confidence=rotated["face_presence_confidence"],
        )

        self.assertIsNotNone(frontal_prob)
        self.assertIsNotNone(rotated_prob)
        assert frontal_prob is not None
        assert rotated_prob is not None
        self.assertGreater(frontal_prob, rotated_prob)
        self.assertGreater(frontal_conf, 0.7)
        self.assertGreater(rotated_conf, 0.7)
        self.assertLess(rotated_prob, 0.45)

    def test_large_head_rotation_reduces_head_pose_confidence(self) -> None:
        payload = _load_fixture("quality_cases.json")
        frontal = payload["frontal_pose"]
        rotated = payload["large_rotation_pose"]

        frontal_confidence = estimate_head_pose_confidence(
            head_pose=frontal["head_pose"],
            face_presence_confidence=frontal["face_presence_confidence"],
        )
        rotated_confidence = estimate_head_pose_confidence(
            head_pose=rotated["head_pose"],
            face_presence_confidence=rotated["face_presence_confidence"],
        )

        self.assertGreater(frontal_confidence, rotated_confidence)

    def test_zero_face_presence_disables_gaze_proxy(self) -> None:
        probability, confidence = estimate_gaze_on_screen_proxy(
            head_pose={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            center_offset=0.0,
            eye_openness=0.75,
            face_presence_confidence=0.0,
        )
        self.assertIsNone(probability)
        self.assertEqual(confidence, 0.0)

    def test_face_lost_sequence_lowers_visibility_and_window_confidence(self) -> None:
        payload = _load_fixture("rolling_sequences.json")
        sequence = payload["face_lost_sequence"]
        tracker = RollingSignalTracker(window_ms=10_000, baseline_window_ms=10_000)

        snapshot = None
        for item in sequence:
            snapshot = tracker.update(
                t_ms=item["t_ms"],
                blink=item["blink"],
                face_visible=item["face_visible"],
                head_pose_valid=item["head_pose_valid"],
            )

        assert snapshot is not None
        self.assertLess(snapshot["face_visible_pct"], 0.6)
        self.assertLess(snapshot["head_pose_valid_pct"], 0.6)
        self.assertLess(snapshot["window_confidence"], 0.65)

    def test_blink_inhibition_sequence_detects_inhibition_window(self) -> None:
        payload = _load_fixture("rolling_sequences.json")
        sequence = payload["blink_inhibition_sequence"]
        tracker = RollingSignalTracker(
            window_ms=10_000,
            baseline_window_ms=10_000,
            inhibition_threshold=0.35,
        )

        snapshot = None
        for item in sequence:
            snapshot = tracker.update(
                t_ms=item["t_ms"],
                blink=item["blink"],
                face_visible=item["face_visible"],
                head_pose_valid=item["head_pose_valid"],
            )

        assert snapshot is not None
        self.assertGreater(snapshot["blink_baseline_rate"], snapshot["rolling_blink_rate"])
        self.assertGreater(snapshot["blink_inhibition_score"], 0.35)
        self.assertTrue(snapshot["blink_inhibition_active"])

    def test_blink_events_feed_rolling_blink_rate(self) -> None:
        tracker = RollingSignalTracker(window_ms=4_000, baseline_window_ms=4_000)
        timestamps = [0, 1000, 2000, 3000, 4000]
        blink_values = [0, 1, 0, 1, 0]

        snapshots = []
        for t_ms, blink in zip(timestamps, blink_values):
            snapshots.append(
                tracker.update(
                    t_ms=t_ms,
                    blink=blink,
                    face_visible=True,
                    head_pose_valid=True,
                )
            )

        final_snapshot = snapshots[-1]
        self.assertGreater(final_snapshot["rolling_blink_rate"], 0.0)
        self.assertGreater(final_snapshot["blink_baseline_rate"], 0.0)

    def test_quality_flag_thresholds(self) -> None:
        low_quality_flags = derive_quality_flags(
            brightness=30.0,
            blur=18.0,
            face_visible_pct=0.32,
            head_pose_valid_pct=0.38,
        )
        self.assertEqual(
            low_quality_flags,
            ["blur", "face_lost", "high_yaw_pitch", "low_light"],
        )

        high_quality_flags = derive_quality_flags(
            brightness=118.0,
            blur=260.0,
            face_visible_pct=0.92,
            head_pose_valid_pct=0.9,
        )
        self.assertEqual(high_quality_flags, [])

    def test_tracking_confidence_weighting_penalizes_low_quality_inputs(self) -> None:
        strong_confidence = compose_tracking_confidence(
            quality_confidence=0.9,
            face_presence_confidence=0.92,
            landmarks_confidence=0.9,
            head_pose_confidence=0.88,
            gaze_on_screen_confidence=0.87,
            au_confidence=0.86,
        )
        weak_confidence = compose_tracking_confidence(
            quality_confidence=0.3,
            face_presence_confidence=0.25,
            landmarks_confidence=0.22,
            head_pose_confidence=0.2,
            gaze_on_screen_confidence=0.18,
            au_confidence=0.15,
        )

        self.assertGreater(strong_confidence, weak_confidence)
        self.assertLess(weak_confidence, 0.35)


if __name__ == "__main__":
    unittest.main()
