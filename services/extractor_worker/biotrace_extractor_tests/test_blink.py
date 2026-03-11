"""Unit tests for blink detection."""

from __future__ import annotations

import unittest

from biotrace_extractor.blink import (
    BlinkDetector,
    LEFT_EYE_IDX,
    RIGHT_EYE_IDX,
    compute_eye_aspect_ratio,
)


def _build_landmarks(vertical_aperture: float):
    landmarks = [(0.0, 0.0)] * 468

    def set_eye(indices, x_offset: float, y_offset: float) -> None:
        p1 = (x_offset + 0.0, y_offset + 0.0)
        p2 = (x_offset + 2.0, y_offset + vertical_aperture / 2.0)
        p3 = (x_offset + 8.0, y_offset + vertical_aperture / 2.0)
        p4 = (x_offset + 10.0, y_offset + 0.0)
        p5 = (x_offset + 8.0, y_offset - vertical_aperture / 2.0)
        p6 = (x_offset + 2.0, y_offset - vertical_aperture / 2.0)
        points = (p1, p2, p3, p4, p5, p6)
        for index, point in zip(indices, points):
            landmarks[index] = point

    set_eye(LEFT_EYE_IDX, x_offset=10.0, y_offset=10.0)
    set_eye(RIGHT_EYE_IDX, x_offset=40.0, y_offset=10.0)
    return landmarks


class BlinkDetectorTests(unittest.TestCase):
    def test_ear_open_higher_than_closed(self) -> None:
        open_landmarks = _build_landmarks(vertical_aperture=4.0)
        closed_landmarks = _build_landmarks(vertical_aperture=0.8)

        open_ear = compute_eye_aspect_ratio(open_landmarks)
        closed_ear = compute_eye_aspect_ratio(closed_landmarks)

        self.assertIsNotNone(open_ear)
        self.assertIsNotNone(closed_ear)
        assert open_ear is not None
        assert closed_ear is not None
        self.assertGreater(open_ear, closed_ear)

    def test_blink_threshold_with_min_closed_frames(self) -> None:
        detector = BlinkDetector(threshold=0.20, min_closed_frames=2)

        signal = [0.31, 0.19, 0.18, 0.30, 0.17, 0.16]
        output = [detector.update(value) for value in signal]

        self.assertEqual(output, [0, 0, 1, 0, 0, 1])

    def test_none_resets_closed_state(self) -> None:
        detector = BlinkDetector(threshold=0.20, min_closed_frames=2)

        self.assertEqual(detector.update(0.19), 0)
        self.assertEqual(detector.update(None), 0)
        self.assertEqual(detector.update(0.19), 0)
        self.assertEqual(detector.update(0.19), 1)


if __name__ == "__main__":
    unittest.main()
