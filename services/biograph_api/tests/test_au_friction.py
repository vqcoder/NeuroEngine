"""Unit tests for AU friction diagnostics and quality-aware degradation."""

from __future__ import annotations

from app.au_friction import compute_au_friction_diagnostics


def _rows(
    *,
    face_presence: list[float],
    head_pose_stability: list[float],
    tracking_confidence: list[float],
    quality_score: list[float],
    brightness: list[float],
    occlusion: list[float],
    quality_flags: list[list[str]],
    au4: list[float],
    au6: list[float],
    au12: list[float],
    au25: list[float],
    au26: list[float],
    au45: list[float],
    scene_ids: list[str] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    scene_series = scene_ids or ["scene-1" for _ in face_presence]
    for index in range(len(face_presence)):
        rows.append(
            {
                "bucket_start": index * 1000,
                "scene_id": scene_series[index],
                "cut_id": f"cut-{index}" if index in {3, 6} else "cut-static",
                "attention_velocity": -2.4 if index in {3, 4} else 0.9,
                "playback_continuity": 0.88,
                "face_presence": face_presence[index],
                "head_pose_stability": head_pose_stability[index],
                "tracking_confidence": tracking_confidence[index],
                "quality_score": quality_score[index],
                "mean_brightness": brightness[index],
                "mean_occlusion_score": occlusion[index],
                "quality_flags": quality_flags[index],
                "au4": au4[index],
                "au6": au6[index],
                "au12": au12[index],
                "au_norm": {
                    "AU04": au4[index],
                    "AU06": au6[index],
                    "AU12": au12[index],
                    "AU25": au25[index],
                    "AU26": au26[index],
                    "AU45": au45[index],
                },
            }
        )
    return rows


def test_au_friction_gracefully_degrades_with_occlusion_and_poor_lighting() -> None:
    high_quality = compute_au_friction_diagnostics(
        bucket_rows=_rows(
            face_presence=[0.82, 0.84, 0.8, 0.78, 0.81, 0.83, 0.8, 0.79],
            head_pose_stability=[0.8, 0.82, 0.81, 0.79, 0.8, 0.83, 0.8, 0.8],
            tracking_confidence=[0.87, 0.88, 0.89, 0.86, 0.88, 0.89, 0.87, 0.86],
            quality_score=[0.84, 0.86, 0.85, 0.83, 0.85, 0.86, 0.84, 0.83],
            brightness=[68, 69, 70, 71, 70, 69, 68, 69],
            occlusion=[0.11, 0.1, 0.12, 0.13, 0.12, 0.1, 0.11, 0.12],
            quality_flags=[[], [], [], [], [], [], [], []],
            au4=[0.16, 0.18, 0.22, 0.36, 0.31, 0.2, 0.17, 0.15],
            au6=[0.22, 0.2, 0.18, 0.14, 0.16, 0.2, 0.23, 0.24],
            au12=[0.2, 0.22, 0.24, 0.18, 0.17, 0.23, 0.25, 0.24],
            au25=[0.12, 0.13, 0.14, 0.24, 0.22, 0.15, 0.13, 0.12],
            au26=[0.1, 0.11, 0.12, 0.2, 0.18, 0.13, 0.12, 0.11],
            au45=[0.12, 0.1, 0.13, 0.22, 0.2, 0.12, 0.11, 0.1],
        ),
        window_ms=1000,
    )
    degraded = compute_au_friction_diagnostics(
        bucket_rows=_rows(
            face_presence=[0.24, 0.22, 0.2, 0.18, 0.21, 0.19, 0.2, 0.18],
            head_pose_stability=[0.4, 0.38, 0.35, 0.34, 0.36, 0.33, 0.35, 0.32],
            tracking_confidence=[0.32, 0.3, 0.29, 0.27, 0.3, 0.28, 0.27, 0.26],
            quality_score=[0.34, 0.31, 0.28, 0.26, 0.29, 0.27, 0.26, 0.24],
            brightness=[18, 82, 17, 79, 16, 76, 15, 80],
            occlusion=[0.72, 0.78, 0.74, 0.8, 0.76, 0.79, 0.75, 0.81],
            quality_flags=[
                ["low_light", "face_lost", "high_yaw_pitch"],
                ["face_lost", "high_yaw_pitch"],
                ["low_light", "face_lost", "high_yaw_pitch"],
                ["face_lost", "high_yaw_pitch"],
                ["low_light", "face_lost", "high_yaw_pitch"],
                ["face_lost", "high_yaw_pitch"],
                ["low_light", "face_lost", "high_yaw_pitch"],
                ["face_lost", "high_yaw_pitch"],
            ],
            au4=[0.16, 0.18, 0.22, 0.36, 0.31, 0.2, 0.17, 0.15],
            au6=[0.22, 0.2, 0.18, 0.14, 0.16, 0.2, 0.23, 0.24],
            au12=[0.2, 0.22, 0.24, 0.18, 0.17, 0.23, 0.25, 0.24],
            au25=[0.12, 0.13, 0.14, 0.24, 0.22, 0.15, 0.13, 0.12],
            au26=[0.1, 0.11, 0.12, 0.2, 0.18, 0.13, 0.12, 0.11],
            au45=[0.12, 0.1, 0.13, 0.22, 0.2, 0.12, 0.11, 0.1],
        ),
        window_ms=1000,
    )

    assert high_quality.pathway.value == "au_signal_model"
    assert degraded.pathway.value == "fallback_proxy"
    assert high_quality.confidence is not None
    assert degraded.confidence is not None
    assert high_quality.confidence > degraded.confidence
    warning_keys = {item.warning_key for item in degraded.warnings}
    assert "missing_face_windows" in warning_keys
    assert "unstable_head_pose" in warning_keys
    assert "high_occlusion" in warning_keys
    assert "high_lighting_variance" in warning_keys


def test_au_friction_maps_confusion_spike_after_scene_transition() -> None:
    diagnostics = compute_au_friction_diagnostics(
        bucket_rows=_rows(
            face_presence=[0.8, 0.79, 0.8, 0.78, 0.8, 0.81, 0.8, 0.79],
            head_pose_stability=[0.78, 0.79, 0.8, 0.77, 0.79, 0.8, 0.79, 0.78],
            tracking_confidence=[0.86, 0.85, 0.87, 0.84, 0.86, 0.87, 0.86, 0.85],
            quality_score=[0.84, 0.83, 0.85, 0.82, 0.84, 0.85, 0.84, 0.83],
            brightness=[66, 67, 68, 67, 66, 67, 68, 67],
            occlusion=[0.12, 0.11, 0.13, 0.12, 0.11, 0.12, 0.12, 0.11],
            quality_flags=[[], [], [], [], [], [], [], []],
            au4=[0.14, 0.16, 0.19, 0.58, 0.52, 0.24, 0.18, 0.16],
            au6=[0.24, 0.22, 0.2, 0.1, 0.12, 0.2, 0.23, 0.24],
            au12=[0.22, 0.24, 0.23, 0.1, 0.12, 0.22, 0.24, 0.23],
            au25=[0.12, 0.14, 0.15, 0.36, 0.31, 0.16, 0.13, 0.12],
            au26=[0.1, 0.12, 0.13, 0.34, 0.29, 0.14, 0.12, 0.11],
            au45=[0.12, 0.11, 0.12, 0.27, 0.24, 0.14, 0.12, 0.11],
            scene_ids=["scene-1", "scene-1", "scene-1", "scene-2", "scene-2", "scene-2", "scene-2", "scene-2"],
        ),
        window_ms=1000,
    )

    assert any(
        item.transition_context == "post_transition_spike"
        for item in diagnostics.segment_scores
    )
    assert any(
        item.warning_key == "post_transition_confusion_spike"
        for item in diagnostics.warnings
    )
