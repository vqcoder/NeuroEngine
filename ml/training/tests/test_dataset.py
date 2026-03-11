from __future__ import annotations

import math

import pandas as pd

from ml_pipeline.dataset import (
    _aggregate_trace_per_second,
    _compose_reward_proxy_target,
    _extract_survey_signals,
)


def test_aggregate_trace_per_second_includes_alignment_and_reward_fields() -> None:
    frame = pd.DataFrame(
        [
            {
                "video_time_ms": 100,
                "blink": 0,
                "blink_inhibition_score": 0.2,
                "reward_proxy": 30.0,
                "dial": 50.0,
                "face_ok": True,
                "brightness": 70.0,
                "blur": 2.0,
                "au_norm": {"AU12": 0.1, "AU06": 0.08, "AU04": 0.02},
                "head_pose": {"yaw": 5.0, "pitch": 2.0, "roll": 1.0},
                "scene_id": "scene_1",
                "cut_id": "cut_1",
                "cta_id": None,
            },
            {
                "video_time_ms": 800,
                "blink": 1,
                "blink_inhibition_score": 0.2,
                "reward_proxy": 50.0,
                "dial": 55.0,
                "face_ok": True,
                "brightness": 72.0,
                "blur": 2.5,
                "au_norm": {"AU12": 0.12, "AU06": 0.09, "AU04": 0.03},
                "head_pose": {"yaw": 6.0, "pitch": 2.5, "roll": 1.2},
                "scene_id": "scene_1",
                "cut_id": "cut_1",
                "cta_id": None,
            },
            {
                "video_time_ms": 1200,
                "blink": 0,
                "blink_inhibition_score": 0.6,
                "reward_proxy": 90.0,
                "dial": 60.0,
                "face_ok": True,
                "brightness": 75.0,
                "blur": 2.2,
                "au_norm": {"AU12": 0.2, "AU06": 0.1, "AU04": 0.01},
                "head_pose": {"yaw": 4.0, "pitch": 1.5, "roll": 0.8},
                "scene_id": "scene_2",
                "cut_id": "cut_2",
                "cta_id": "cta_1",
            },
        ]
    )

    second_frame = _aggregate_trace_per_second(frame)

    assert list(second_frame["second"]) == [0, 1]
    assert math.isclose(float(second_frame.loc[0, "observed_reward_proxy"]), 40.0, rel_tol=1e-6)
    assert math.isclose(float(second_frame.loc[1, "observed_reward_proxy"]), 90.0, rel_tol=1e-6)
    assert float(second_frame.loc[0, "scene_transition"]) == 0.0
    assert float(second_frame.loc[1, "scene_transition"]) == 1.0
    assert float(second_frame.loc[1, "cut_transition"]) == 1.0
    assert float(second_frame.loc[1, "cta_active"]) == 1.0


def test_reward_proxy_composite_uses_multiple_signal_types() -> None:
    frame = pd.DataFrame(
        {
            "au12_norm": [0.1, 0.1],
            "au6_norm": [0.06, 0.06],
            "au4_norm": [0.02, 0.02],
            "blink_inhibition": [0.7, 0.7],
            "blink_rate": [0.05, 0.05],
            "rolling_blink_rate": [0.04, 0.04],
            "playback_friction_count": [0.0, 4.0],
            "playback_session_incomplete_count": [0.0, 1.0],
            "playback_play_count": [1.0, 0.0],
            "engaging_marker_count": [1.0, 0.0],
            "confusing_marker_count": [0.0, 1.0],
            "stop_marker_count": [0.0, 1.0],
            "cta_marker_count": [1.0, 0.0],
            "survey_overall_interest": [85.0, 20.0],
            "survey_recall_comprehension": [80.0, 25.0],
            "survey_desire_to_continue": [90.0, 15.0],
            "dial": [70.0, 30.0],
            "quality_score": [0.9, 0.4],
            "face_ok_rate": [0.95, 0.5],
        }
    )

    reward = _compose_reward_proxy_target(frame)

    assert reward.iloc[0] > reward.iloc[1]
    assert reward.iloc[0] - reward.iloc[1] >= 20.0


def test_extract_survey_signals_normalizes_likert_scale() -> None:
    survey_frame = pd.DataFrame(
        [
            {"question_key": "overall_interest_likert", "response_number": 4},
            {"question_key": "recall_comprehension_likert", "response_number": 5},
            {"question_key": "desire_to_continue_or_take_action_likert", "response_number": 3},
            {
                "question_key": "session_completion_status",
                "response_json": {"status": "completed"},
            },
            {
                "question_key": "annotation_status",
                "response_json": {"annotation_skipped": False},
            },
        ]
    )

    signals = _extract_survey_signals(survey_frame)

    assert math.isclose(signals["survey_overall_interest"], 75.0, rel_tol=1e-6)
    assert math.isclose(signals["survey_recall_comprehension"], 100.0, rel_tol=1e-6)
    assert math.isclose(signals["survey_desire_to_continue"], 50.0, rel_tol=1e-6)
    assert math.isclose(signals["survey_completion_score"], 100.0, rel_tol=1e-6)
    assert math.isclose(signals["survey_annotation_completion_score"], 100.0, rel_tol=1e-6)
