"""Unit tests for narrative control scoring from synthetic edit patterns."""

from __future__ import annotations

from app.config import get_settings
from app.narrative_control import (
    NarrativeControlConfig,
    compute_narrative_control_diagnostics,
    resolve_narrative_control_config,
)
from app.schemas import ReadoutCtaMarker, ReadoutCut, ReadoutScene


def _scene_graph() -> tuple[list[ReadoutScene], list[ReadoutCut]]:
    scenes = [
        ReadoutScene(scene_index=1, start_ms=0, end_ms=4000, scene_id="scene-1", label="setup"),
        ReadoutScene(scene_index=2, start_ms=4000, end_ms=8000, scene_id="scene-2", label="middle"),
        ReadoutScene(scene_index=3, start_ms=8000, end_ms=12000, scene_id="scene-3", label="payoff"),
    ]
    cuts = [
        ReadoutCut(cut_id="cut-1", start_ms=1200, end_ms=1201, scene_id="scene-1"),
        ReadoutCut(cut_id="cut-2", start_ms=2600, end_ms=2601, scene_id="scene-1"),
        ReadoutCut(cut_id="cut-3", start_ms=4700, end_ms=4701, scene_id="scene-2"),
        ReadoutCut(cut_id="cut-4", start_ms=6700, end_ms=6701, scene_id="scene-2"),
        ReadoutCut(cut_id="cut-5", start_ms=9100, end_ms=9101, scene_id="scene-3"),
    ]
    return scenes, cuts


def _bucket_rows(attention: list[float], playback: float = 0.94) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, score in enumerate(attention):
        start_ms = index * 1000
        scene_id = "scene-1" if start_ms < 4000 else ("scene-2" if start_ms < 8000 else "scene-3")
        previous = attention[index - 1] if index > 0 else score
        rows.append(
            {
                "bucket_start": start_ms,
                "scene_id": scene_id,
                "attention_score": score,
                "attention_velocity": score - previous,
                "tracking_confidence": 0.84,
                "playback_continuity": playback,
            }
        )
    return rows


def _timeline_tracks(
    *,
    cut_cadence: list[float],
    shot_duration_ms: list[float],
    motion_proxy: list[float],
    face_presence: list[float],
    subject_persistence: float,
) -> list[dict[str, object]]:
    tracks: list[dict[str, object]] = []
    for index, value in enumerate(cut_cadence):
        start_ms = index * 1000
        end_ms = start_ms + 1000
        tracks.append(
            {
                "track_name": "cut_cadence",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": value,
            }
        )
    for index, value in enumerate(shot_duration_ms):
        start_ms = index * 1000
        end_ms = start_ms + 1000
        tracks.append(
            {
                "track_name": "shot_duration_ms",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": value,
            }
        )
    for index, value in enumerate(motion_proxy):
        start_ms = index * 1000
        end_ms = start_ms + 1000
        tracks.append(
            {
                "track_name": "camera_motion_proxy",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": value,
            }
        )
    for index, value in enumerate(face_presence):
        start_ms = index * 1000
        end_ms = start_ms + 1000
        tracks.append(
            {
                "track_name": "face_presence_rate",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "numeric_value": value,
            }
        )
    tracks.append(
        {
            "track_name": "primary_subject_persistence",
            "start_ms": 0,
            "end_ms": len(cut_cadence) * 1000,
            "numeric_value": subject_persistence,
        }
    )
    return tracks


def _timeline_segments(cut_starts: list[int], cta_start: int) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    for cut_start in cut_starts:
        segments.append(
            {
                "segment_type": "shot_boundary",
                "start_ms": cut_start,
                "end_ms": cut_start + 1,
                "label": "cut_event",
            }
        )
    segments.extend(
        [
            {
                "segment_type": "scene_block",
                "start_ms": 0,
                "end_ms": 4000,
                "label": "setup",
            },
            {
                "segment_type": "scene_block",
                "start_ms": 4000,
                "end_ms": 8000,
                "label": "middle",
            },
            {
                "segment_type": "scene_block",
                "start_ms": 8000,
                "end_ms": 12000,
                "label": "payoff",
            },
            {
                "segment_type": "text_overlay",
                "start_ms": 4300,
                "end_ms": 5200,
                "label": "Introducing the core idea",
            },
            {
                "segment_type": "cta_window",
                "start_ms": cta_start,
                "end_ms": cta_start + 1400,
                "label": "Primary CTA",
            },
        ]
    )
    return segments


def test_narrative_control_higher_for_continuity_than_fragmentation() -> None:
    scenes, cuts = _scene_graph()

    controlled = compute_narrative_control_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=9600, start_ms=9600, end_ms=11000)],
        bucket_rows=_bucket_rows([66, 68, 70, 72, 74, 76, 78, 80, 79, 81, 84, 86]),
        window_ms=1000,
        timeline_segments=_timeline_segments([1200, 2600, 4700, 6700, 9100], 9600),
        timeline_feature_tracks=_timeline_tracks(
            cut_cadence=[0.35, 0.45, 0.40, 0.38, 0.42, 0.36, 0.33, 0.41, 0.44, 0.40, 0.39, 0.37],
            shot_duration_ms=[1400, 1500, 1300, 1450, 1350, 1420, 1380, 1460, 1520, 1480, 1390, 1410],
            motion_proxy=[1.8, 2.0, 2.1, 2.0, 2.2, 2.3, 2.1, 2.0, 2.2, 2.4, 2.2, 2.1],
            face_presence=[0.72, 0.74, 0.76, 0.78, 0.82, 0.84, 0.85, 0.86, 0.88, 0.87, 0.89, 0.90],
            subject_persistence=0.87,
        ),
    )

    fragmented_cuts = [
        ReadoutCut(cut_id=f"cut-{index}", start_ms=900 + (index * 700), end_ms=901 + (index * 700))
        for index in range(12)
    ]
    fragmented = compute_narrative_control_diagnostics(
        scenes=scenes,
        cuts=fragmented_cuts,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=5200, start_ms=5200, end_ms=6400)],
        bucket_rows=_bucket_rows([64, 57, 52, 49, 46, 44, 42, 39, 37, 35, 33, 31], playback=0.72),
        window_ms=1000,
        timeline_segments=_timeline_segments([900 + (index * 700) for index in range(12)], 5200),
        timeline_feature_tracks=_timeline_tracks(
            cut_cadence=[2.1, 2.4, 2.2, 2.6, 2.5, 2.8, 2.7, 2.3, 2.9, 2.4, 2.6, 2.8],
            shot_duration_ms=[420, 380, 360, 410, 340, 390, 330, 370, 350, 320, 360, 345],
            motion_proxy=[2.0, 9.5, 3.1, 10.4, 2.4, 11.2, 2.8, 10.9, 3.0, 9.8, 2.2, 11.0],
            face_presence=[0.70, 0.32, 0.66, 0.28, 0.61, 0.30, 0.58, 0.26, 0.56, 0.29, 0.54, 0.24],
            subject_persistence=0.33,
        ),
    )

    assert controlled.pathway.value == "timeline_grammar"
    assert controlled.global_score is not None
    assert fragmented.global_score is not None
    assert controlled.global_score > fragmented.global_score + 12.0


def test_narrative_control_penalizes_excessive_fragmentation() -> None:
    scenes, _ = _scene_graph()
    fragmented_cuts = [
        ReadoutCut(cut_id=f"cut-{index}", start_ms=800 + (index * 600), end_ms=801 + (index * 600))
        for index in range(13)
    ]
    diagnostics = compute_narrative_control_diagnostics(
        scenes=scenes,
        cuts=fragmented_cuts,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=5200, start_ms=5200, end_ms=6100)],
        bucket_rows=_bucket_rows([63, 56, 51, 47, 45, 43, 40, 38, 36, 34, 32, 31], playback=0.7),
        window_ms=1000,
        timeline_segments=_timeline_segments([800 + (index * 600) for index in range(13)], 5200),
        timeline_feature_tracks=_timeline_tracks(
            cut_cadence=[2.4, 2.8, 2.6, 2.9, 2.7, 3.1, 2.8, 2.9, 3.0, 2.7, 2.8, 2.9],
            shot_duration_ms=[360, 340, 320, 350, 330, 310, 300, 340, 320, 330, 300, 310],
            motion_proxy=[2.1, 10.8, 2.9, 11.3, 2.7, 10.6, 3.0, 11.1, 2.8, 10.9, 2.6, 11.0],
            face_presence=[0.66, 0.28, 0.63, 0.25, 0.60, 0.23, 0.57, 0.20, 0.55, 0.22, 0.53, 0.19],
            subject_persistence=0.31,
        ),
    )

    penalty_total = sum(item.contribution for item in diagnostics.disruption_penalties)
    assert penalty_total < 0.0
    assert any(item.category == "disruptive_transition" for item in diagnostics.disruption_penalties)
    cta_check = next(
        item
        for item in diagnostics.heuristic_checks
        if item.heuristic_key == "cta_not_after_disorienting_transition"
    )
    assert cta_check.passed is False


def test_narrative_control_rewards_clean_payoff_structure() -> None:
    scenes, cuts = _scene_graph()
    diagnostics = compute_narrative_control_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=10000, start_ms=10000, end_ms=11300)],
        bucket_rows=_bucket_rows([65, 64, 63, 60, 57, 50, 43, 41, 48, 56, 65, 72]),
        window_ms=1000,
        timeline_segments=_timeline_segments([1200, 2600, 4700, 6700, 9100], 10000),
        timeline_feature_tracks=_timeline_tracks(
            cut_cadence=[0.42, 0.46, 0.44, 0.40, 0.43, 0.47, 0.41, 0.39, 0.38, 0.36, 0.34, 0.35],
            shot_duration_ms=[1500, 1450, 1420, 1380, 1400, 1440, 1460, 1480, 1510, 1490, 1470, 1450],
            motion_proxy=[2.2, 2.3, 2.4, 2.1, 2.2, 2.5, 2.3, 2.2, 2.1, 2.0, 1.9, 1.8],
            face_presence=[0.74, 0.75, 0.77, 0.79, 0.81, 0.82, 0.83, 0.84, 0.86, 0.87, 0.88, 0.90],
            subject_persistence=0.85,
        ),
    )

    payoff_check = next(
        item
        for item in diagnostics.heuristic_checks
        if item.heuristic_key == "payoff_not_buried_after_attention_collapse"
    )
    assert payoff_check.passed is True
    assert payoff_check.score_delta > 0
    assert len(diagnostics.reveal_structure_bonuses) >= 1


def test_narrative_control_thresholds_are_configurable() -> None:
    scenes, cuts = _scene_graph()
    rows = _bucket_rows([64, 60, 56, 53, 50, 48, 46, 44, 42, 40, 38, 36], playback=0.78)
    tracks = _timeline_tracks(
        cut_cadence=[1.4, 1.5, 1.45, 1.55, 1.5, 1.6, 1.52, 1.48, 1.5, 1.55, 1.58, 1.6],
        shot_duration_ms=[740, 720, 700, 760, 730, 710, 690, 700, 720, 710, 705, 700],
        motion_proxy=[2.8, 4.9, 3.1, 5.3, 3.4, 5.0, 3.2, 5.1, 3.0, 5.2, 3.3, 5.4],
        face_presence=[0.68, 0.55, 0.66, 0.54, 0.64, 0.52, 0.63, 0.51, 0.62, 0.50, 0.60, 0.49],
        subject_persistence=0.49,
    )
    segments = _timeline_segments([1200, 2600, 4700, 6700, 9100], 9500)
    cta = [ReadoutCtaMarker(cta_id="cta-main", video_time_ms=9500, start_ms=9500, end_ms=10800)]

    default_diag = compute_narrative_control_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta,
        bucket_rows=rows,
        window_ms=1000,
        timeline_segments=segments,
        timeline_feature_tracks=tracks,
    )
    strict_diag = compute_narrative_control_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta,
        bucket_rows=rows,
        window_ms=1000,
        timeline_segments=segments,
        timeline_feature_tracks=tracks,
        config=NarrativeControlConfig(fragmentation_cut_cadence_threshold=1.0),
    )

    assert default_diag.global_score is not None
    assert strict_diag.global_score is not None
    assert strict_diag.global_score < default_diag.global_score


def test_narrative_control_config_honors_metadata_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "NARRATIVE_CONTROL_CONFIG_JSON",
        '{"fragmentation_cut_cadence_threshold": 1.15}',
    )
    get_settings.cache_clear()

    config = resolve_narrative_control_config(
        {"narrative_control_config": {"fragmentation_cut_cadence_threshold": 0.95}}
    )
    assert config.fragmentation_cut_cadence_threshold == 0.95

    get_settings.cache_clear()
