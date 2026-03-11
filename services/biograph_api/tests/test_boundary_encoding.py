"""Unit tests for boundary encoding diagnostics from timeline payload placement."""

from __future__ import annotations

from app.boundary_encoding import (
    BoundaryEncodingConfig,
    compute_boundary_encoding_diagnostics,
    resolve_boundary_encoding_config,
)
from app.config import get_settings
from app.schemas import ReadoutCtaMarker, ReadoutCut, ReadoutScene


def _scene_graph() -> tuple[list[ReadoutScene], list[ReadoutCut]]:
    scenes = [
        ReadoutScene(scene_index=1, start_ms=0, end_ms=4000, scene_id="scene-1", label="setup"),
        ReadoutScene(scene_index=2, start_ms=4000, end_ms=8000, scene_id="scene-2", label="proof"),
        ReadoutScene(scene_index=3, start_ms=8000, end_ms=12000, scene_id="scene-3", label="offer"),
    ]
    cuts = [
        ReadoutCut(cut_id="cut-1", start_ms=3000, end_ms=3001, scene_id="scene-1"),
        ReadoutCut(cut_id="cut-2", start_ms=6000, end_ms=6001, scene_id="scene-2"),
        ReadoutCut(cut_id="cut-3", start_ms=9000, end_ms=9001, scene_id="scene-3"),
    ]
    return scenes, cuts


def _bucket_rows(novelty: list[float], attention: list[float]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, novelty_value in enumerate(novelty):
        start_ms = index * 1000
        attention_value = attention[index]
        prev_attention = attention[index - 1] if index > 0 else attention_value
        rows.append(
            {
                "bucket_start": start_ms,
                "scene_id": "scene-1" if start_ms < 4000 else ("scene-2" if start_ms < 8000 else "scene-3"),
                "attention_score": attention_value,
                "attention_velocity": attention_value - prev_attention,
                "novelty_proxy": novelty_value,
                "tracking_confidence": 0.86,
                "quality_score": 0.84,
            }
        )
    return rows


def _timeline_segments(
    *,
    overlay_windows: list[tuple[int, int, str]],
    cta_windows: list[tuple[int, int, str]],
) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    for boundary in [3000, 6000, 9000]:
        segments.append(
            {
                "segment_type": "shot_boundary",
                "start_ms": boundary,
                "end_ms": boundary + 1,
                "label": "cut",
            }
        )
    segments.extend(
        [
            {"segment_type": "scene_block", "start_ms": 0, "end_ms": 4000, "label": "setup"},
            {"segment_type": "scene_block", "start_ms": 4000, "end_ms": 8000, "label": "proof"},
            {"segment_type": "scene_block", "start_ms": 8000, "end_ms": 12000, "label": "offer"},
        ]
    )
    for start_ms, end_ms, label in overlay_windows:
        segments.append(
            {
                "segment_type": "text_overlay",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": label,
            }
        )
    for start_ms, end_ms, label in cta_windows:
        segments.append(
            {
                "segment_type": "cta_window",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": label,
            }
        )
    return segments


def _timeline_tracks() -> list[dict[str, object]]:
    return [
        {
            "track_name": "cut_cadence",
            "start_ms": index * 1000,
            "end_ms": (index * 1000) + 1000,
            "numeric_value": value,
        }
        for index, value in enumerate([0.45, 0.5, 0.52, 0.47, 0.48, 0.51, 0.46, 0.49, 0.5, 0.47, 0.45, 0.44])
    ]


def test_boundary_encoding_higher_for_well_placed_payload_timing() -> None:
    scenes, cuts = _scene_graph()
    cta_markers = [ReadoutCtaMarker(cta_id="cta-main", video_time_ms=9050, start_ms=8900, end_ms=9800)]

    well_placed = compute_boundary_encoding_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta_markers,
        bucket_rows=_bucket_rows(
            [30, 32, 36, 71, 42, 68, 44, 47, 73, 56, 52, 50],
            [58, 60, 62, 69, 64, 71, 67, 66, 72, 68, 66, 64],
        ),
        timeline_segments=_timeline_segments(
            overlay_windows=[
                (2750, 3400, "Brand claim: proven durability"),
                (5750, 6350, "Product proof"),
                (8750, 9450, "Offer ends tonight"),
            ],
            cta_windows=[(8850, 9800, "Primary CTA")],
        ),
        timeline_feature_tracks=_timeline_tracks(),
        window_ms=1000,
    )

    poorly_timed = compute_boundary_encoding_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=cta_markers,
        bucket_rows=_bucket_rows(
            [34, 36, 40, 43, 45, 47, 49, 50, 52, 53, 51, 49],
            [58, 59, 60, 61, 62, 63, 62, 61, 60, 59, 58, 57],
        ),
        timeline_segments=_timeline_segments(
            overlay_windows=[
                (4200, 5000, "Brand claim"),
                (7400, 8100, "Product proof"),
                (10800, 11600, "Offer details"),
            ],
            cta_windows=[(10800, 11800, "Primary CTA")],
        ),
        timeline_feature_tracks=_timeline_tracks(),
        window_ms=1000,
    )

    assert well_placed.pathway.value == "timeline_boundary_model"
    assert poorly_timed.pathway.value == "timeline_boundary_model"
    assert well_placed.global_score is not None
    assert poorly_timed.global_score is not None
    assert well_placed.global_score > poorly_timed.global_score + 10.0
    assert len(well_placed.strong_windows) >= 1
    assert len(poorly_timed.weak_windows) >= 1


def test_boundary_encoding_flags_payload_overload_and_poor_timing() -> None:
    scenes, cuts = _scene_graph()

    diagnostics = compute_boundary_encoding_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=[ReadoutCtaMarker(cta_id="cta-main", video_time_ms=9000, start_ms=8900, end_ms=9800)],
        bucket_rows=_bucket_rows(
            [30, 33, 36, 62, 58, 61, 57, 45, 44, 43, 42, 40],
            [56, 58, 59, 63, 62, 64, 63, 58, 54, 50, 47, 45],
        ),
        timeline_segments=_timeline_segments(
            overlay_windows=[
                (2800, 3300, "Brand claim"),
                (2900, 3500, "Offer proof"),
                (2950, 3600, "Product demo"),
                (3000, 3650, "Save now"),
                (11200, 11800, "Late claim recap"),
            ],
            cta_windows=[(2900, 3700, "Primary CTA"), (11200, 11900, "Late CTA")],
        ),
        timeline_feature_tracks=_timeline_tracks(),
        window_ms=1000,
        config=BoundaryEncodingConfig(overload_payload_threshold=2, poor_timing_distance_ms=1200),
    )

    flag_keys = {item.flag_key for item in diagnostics.flags}
    assert "payload_overload_at_boundary" in flag_keys
    assert "poor_payload_timing" in flag_keys


def test_boundary_timed_reveal_scores_higher_than_buried_mid_flow_reveal() -> None:
    scenes, cuts = _scene_graph()
    strict_timing = BoundaryEncodingConfig(poor_timing_distance_ms=900)

    boundary_reveal = compute_boundary_encoding_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=[],
        bucket_rows=_bucket_rows(
            [32, 34, 37, 72, 40, 69, 43, 46, 74, 55, 52, 50],
            [57, 59, 62, 70, 65, 72, 66, 65, 73, 68, 66, 63],
        ),
        timeline_segments=_timeline_segments(
            overlay_windows=[(2850, 3400, "Brand reveal"), (5850, 6400, "Claim reveal")],
            cta_windows=[],
        ),
        timeline_feature_tracks=_timeline_tracks(),
        window_ms=1000,
        config=strict_timing,
    )

    buried_mid_flow_reveal = compute_boundary_encoding_diagnostics(
        scenes=scenes,
        cuts=cuts,
        cta_markers=[],
        bucket_rows=_bucket_rows(
            [35, 36, 39, 43, 44, 46, 47, 48, 49, 50, 49, 47],
            [57, 58, 60, 61, 62, 63, 62, 61, 60, 59, 58, 56],
        ),
        timeline_segments=_timeline_segments(
            overlay_windows=[(4700, 5300, "Brand reveal"), (6700, 7300, "Claim reveal")],
            cta_windows=[],
        ),
        timeline_feature_tracks=_timeline_tracks(),
        window_ms=1000,
        config=strict_timing,
    )

    assert boundary_reveal.global_score is not None
    assert buried_mid_flow_reveal.global_score is not None
    assert boundary_reveal.global_score > buried_mid_flow_reveal.global_score + 6.0
    assert len(boundary_reveal.strong_windows) >= 1
    assert len(buried_mid_flow_reveal.weak_windows) >= 1
    assert any(item.flag_key == "poor_payload_timing" for item in buried_mid_flow_reveal.flags)


def test_boundary_encoding_config_honors_metadata_override(monkeypatch) -> None:
    monkeypatch.setenv("BOUNDARY_ENCODING_CONFIG_JSON", '{"payload_boundary_distance_ms": 1300}')
    get_settings.cache_clear()

    config = resolve_boundary_encoding_config(
        {"boundaryEncodingConfig": {"payload_boundary_distance_ms": 700}}
    )
    assert config.payload_boundary_distance_ms == 700

    get_settings.cache_clear()
