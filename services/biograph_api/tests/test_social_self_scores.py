"""Unit tests for social transmission and self-relevance diagnostics separation."""

from __future__ import annotations

from app.self_relevance import compute_self_relevance_diagnostics
from app.social_transmission import compute_social_transmission_diagnostics
from app.schemas import ReadoutCtaMarker


def _bucket_rows(
    *,
    novelty: list[float],
    arousal: list[float],
    reward: list[float],
    attention: list[float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, novelty_value in enumerate(novelty):
        start_ms = index * 1000
        attention_value = float(attention[index])
        prev_attention = float(attention[index - 1]) if index > 0 else attention_value
        rows.append(
            {
                "bucket_start": start_ms,
                "attention_score": attention_value,
                "attention_velocity": attention_value - prev_attention,
                "reward_proxy": float(reward[index]),
                "arousal_proxy": float(arousal[index]),
                "novelty_proxy": float(novelty_value),
                "tracking_confidence": 0.86,
                "quality_score": 0.84,
            }
        )
    return rows


def test_high_novelty_low_self_relevance_example() -> None:
    rows = _bucket_rows(
        novelty=[75, 78, 84, 88, 79, 72],
        arousal=[62, 65, 71, 74, 68, 63],
        reward=[59, 63, 69, 71, 66, 61],
        attention=[60, 64, 69, 72, 67, 62],
    )
    timeline_segments = [
        {"segment_type": "text_overlay", "start_ms": 1000, "end_ms": 2400, "label": "\"You won't believe this!\""},
        {"segment_type": "text_overlay", "start_ms": 3200, "end_ms": 4700, "label": "Three moves everyone is talking about"},
        {"segment_type": "cta_window", "start_ms": 4500, "end_ms": 5600, "label": "Share this with your friends"},
    ]
    annotations = [
        {"marker_type": "engaging_moment", "video_time_ms": 2000, "note": "Unexpected reveal"},
        {"marker_type": "engaging_moment", "video_time_ms": 4000, "note": "Memorable punchline"},
    ]

    social = compute_social_transmission_diagnostics(
        bucket_rows=rows,
        annotation_rows=annotations,
        timeline_segments=timeline_segments,
        timeline_feature_tracks=[
            {"track_name": "cut_cadence", "start_ms": 0, "end_ms": 1000, "numeric_value": 0.8},
            {"track_name": "cut_cadence", "start_ms": 1000, "end_ms": 2000, "numeric_value": 1.4},
            {"track_name": "cut_cadence", "start_ms": 2000, "end_ms": 3000, "numeric_value": 0.9},
        ],
        window_ms=1000,
    )
    self_relevance = compute_self_relevance_diagnostics(
        bucket_rows=rows,
        survey_rows=[],
        timeline_segments=timeline_segments,
        cta_markers=[],
        video_metadata={},
        window_ms=1000,
    )

    assert social.global_score is not None
    assert self_relevance.global_score is not None
    assert social.global_score > self_relevance.global_score + 8.0
    assert social.pathway.value in {"annotation_augmented", "timeline_signal_model"}
    assert self_relevance.pathway.value == "fallback_proxy"
    assert self_relevance.confidence is not None
    assert self_relevance.confidence <= 0.48
    assert any(item.warning_key == "audience_metadata_missing" for item in self_relevance.warnings)


def test_high_self_relevance_low_shareability_example() -> None:
    rows = _bucket_rows(
        novelty=[34, 35, 37, 38, 36, 35],
        arousal=[44, 45, 47, 46, 45, 44],
        reward=[48, 49, 50, 51, 49, 48],
        attention=[61, 63, 65, 66, 64, 62],
    )
    timeline_segments = [
        {
            "segment_type": "text_overlay",
            "start_ms": 500,
            "end_ms": 2200,
            "label": "For your RevOps team: clean handoff logic in 15 minutes",
        },
        {
            "segment_type": "text_overlay",
            "start_ms": 2400,
            "end_ms": 4200,
            "label": "Your pipeline, your owners, your SLA checkpoints",
        },
    ]
    survey_rows = [
        {"question_key": "overall_interest_likert", "response_number": 4.0},
        {"question_key": "recall_comprehension_likert", "response_number": 4.0},
        {"question_key": "desire_to_continue_or_take_action_likert", "response_number": 5.0},
    ]

    social = compute_social_transmission_diagnostics(
        bucket_rows=rows,
        annotation_rows=[],
        timeline_segments=timeline_segments,
        timeline_feature_tracks=[],
        window_ms=1000,
    )
    self_relevance = compute_self_relevance_diagnostics(
        bucket_rows=rows,
        survey_rows=survey_rows,
        timeline_segments=timeline_segments,
        cta_markers=[
            ReadoutCtaMarker(
                cta_id="cta-revops",
                video_time_ms=4300,
                start_ms=4200,
                end_ms=5200,
                label="Book your RevOps review",
            )
        ],
        video_metadata={
            "target_audience_tags": ["revops", "salesops", "b2b pipeline teams"],
            "use_case": "lead routing and handoff QA",
        },
        window_ms=1000,
    )

    assert social.global_score is not None
    assert self_relevance.global_score is not None
    assert self_relevance.global_score > social.global_score + 8.0
    assert self_relevance.pathway.value in {"contextual_personalization", "survey_augmented"}
    assert self_relevance.audience_match_signal is not None
    assert self_relevance.audience_match_signal > 0.2
