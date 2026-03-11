"""Unit tests for optimizer rules and scoring."""

from __future__ import annotations

import json
from pathlib import Path

from optimizer.engine import optimize_video_summary


def _make_summary(
    *,
    attention,
    blink,
    au4,
    motion,
    au6=None,
    au12=None,
    scene_cuts_sec=None,
):
    au6 = au6 or [0.03 for _ in attention]
    au12 = au12 or [0.05 for _ in attention]
    scene_cuts_sec = scene_cuts_sec or [0, len(attention)]

    buckets = []
    for second, value in enumerate(attention):
        buckets.append(
            {
                "bucket_start_ms": second * 1000,
                "attention": value,
                "blink_rate": blink[second],
                "mean_brightness": 70 - (second % 3),
                "motion_magnitude": motion[second],
                "mean_au_norm": {
                    "AU04": au4[second],
                    "AU06": au6[second],
                    "AU12": au12[second],
                },
            }
        )

    scene_boundaries = []
    for i in range(len(scene_cuts_sec) - 1):
        scene_boundaries.append(
            {
                "start_ms": scene_cuts_sec[i] * 1000,
                "end_ms": scene_cuts_sec[i + 1] * 1000,
                "label": f"Scene {i + 1}",
            }
        )

    return {
        "video_id": "unit-test-video",
        "scene_boundaries": scene_boundaries,
        "trace_buckets": buckets,
    }


def test_dead_zone_rule_flags_sustained_attention_drop():
    summary = _make_summary(
        attention=[62, 60, 36, 33, 35, 58, 61],
        blink=[0.05, 0.05, 0.09, 0.1, 0.1, 0.06, 0.05],
        au4=[0.01, 0.01, 0.04, 0.05, 0.04, 0.02, 0.01],
        motion=[0.2] * 7,
    )

    result = optimize_video_summary(summary)
    dead_zone = [item for item in result.suggestions if item.rule == "dead_zone"]

    assert len(dead_zone) == 1
    assert dead_zone[0].start_sec == 2
    assert dead_zone[0].end_sec == 4


def test_confusion_rule_requires_blink_and_au4_rise_together():
    summary = _make_summary(
        attention=[58, 57, 59, 56, 55, 57, 58, 59],
        blink=[0.04, 0.04, 0.04, 0.12, 0.2, 0.08, 0.06, 0.05],
        au4=[0.01, 0.01, 0.01, 0.06, 0.12, 0.03, 0.01, 0.01],
        motion=[0.2] * 8,
    )

    result = optimize_video_summary(summary)
    friction = [item for item in result.suggestions if item.rule == "confusion_friction"]

    assert len(friction) == 1
    assert friction[0].start_sec <= 3
    assert friction[0].end_sec >= 4


def test_late_hook_rule_detects_late_reward_peak():
    attention = [56, 57, 58, 56, 55, 54, 55, 56, 57, 58, 59, 92, 70, 66, 64]
    au12 = [0.05] * len(attention)
    au12[11] = 0.25

    summary = _make_summary(
        attention=attention,
        blink=[0.05] * len(attention),
        au4=[0.01] * len(attention),
        au12=au12,
        motion=[0.2] * len(attention),
        scene_cuts_sec=[0, 5, 10, 15],
    )

    result = optimize_video_summary(summary)
    late_hook = [item for item in result.suggestions if item.rule == "late_hook"]

    assert len(late_hook) == 1
    assert late_hook[0].start_sec == 11


def test_cut_realignment_rule_flags_boundary_mismatch():
    summary = _make_summary(
        attention=[60] * 15,
        blink=[0.05, 0.05, 0.05, 0.06, 0.06, 0.06, 0.05, 0.06, 0.05, 0.06, 0.07, 0.35, 0.07, 0.05, 0.05],
        au4=[0.01] * 15,
        motion=[0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 2.1, 0.2, 0.2],
        scene_cuts_sec=[0, 5, 10, 15],
    )

    result = optimize_video_summary(summary)
    cut_adjust = [item for item in result.suggestions if item.rule == "cut_realignment"]

    assert len(cut_adjust) >= 1
    assert any(entry.evidence.get("distance_sec", 0) >= 2 for entry in cut_adjust)


def test_scoring_system_outputs_positive_predicted_delta_and_sorted_suggestions():
    input_path = Path(__file__).resolve().parents[1] / "examples" / "video_summary.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    result = optimize_video_summary(payload)

    assert result.predicted_total_delta_engagement > 0
    assert result.engagement_score_after >= result.engagement_score_before

    deltas = [item.predicted_delta_engagement for item in result.suggestions]
    assert deltas == sorted(deltas, reverse=True)
