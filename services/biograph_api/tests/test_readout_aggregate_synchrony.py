"""Aggregate-mode synchrony and confidence-weighting tests for readout payloads."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "readout_synchrony_sessions.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def _build_trace_rows(session_payload: dict, timestamps_ms: list[int]) -> list[dict]:
    rows: list[dict] = []
    for index, time_ms in enumerate(timestamps_ms):
        tracking_confidence = float(session_payload["tracking_confidence"][index])
        quality_score = float(session_payload["quality_score"][index])
        brightness = float(session_payload["brightness"][index])
        blur = float(session_payload["blur"][index])
        blink_inhibition = float(session_payload["blink_inhibition"][index])
        blink = 1 if blink_inhibition < -0.05 else 0
        rolling_blink_rate = round(max(0.01, 0.12 - (blink_inhibition * 0.1)), 6)
        yaw = float(session_payload["head_yaw"][index])
        head_pose_valid_pct = round(max(0.0, 1.0 - (abs(yaw) / 50.0)), 6)
        face_ok = tracking_confidence >= 0.35
        landmarks_ok = tracking_confidence >= 0.35
        gaze = float(session_payload["gaze"][index])
        au04 = float(session_payload["au04"][index])
        au06 = float(session_payload["au06"][index])
        au12 = float(session_payload["au12"][index])
        reward_proxy = float(session_payload["reward_proxy"][index])

        au_payload = {
            "AU04": au04,
            "AU06": au06,
            "AU12": au12,
            "AU45": float(blink),
            "AU25": 0.08,
            "AU26": 0.06,
        }

        rows.append(
            {
                "t_ms": int(time_ms),
                "video_time_ms": int(time_ms),
                "face_ok": face_ok,
                "face_presence_confidence": round(tracking_confidence, 6),
                "brightness": brightness,
                "blur": blur,
                "landmarks_ok": landmarks_ok,
                "landmarks_confidence": round(tracking_confidence, 6),
                "eye_openness": 0.22 if blink else 0.82,
                "blink": blink,
                "blink_confidence": round(tracking_confidence, 6),
                "rolling_blink_rate": rolling_blink_rate,
                "blink_inhibition_score": round(blink_inhibition, 6),
                "blink_inhibition_active": blink_inhibition > 0.05,
                "blink_baseline_rate": 0.14,
                "reward_proxy": reward_proxy,
                "au": au_payload,
                "au_norm": au_payload,
                "au_confidence": round(tracking_confidence, 6),
                "head_pose": {"yaw": yaw, "pitch": 0.0, "roll": 0.0},
                "head_pose_confidence": round(tracking_confidence, 6),
                "head_pose_valid_pct": head_pose_valid_pct,
                "gaze_on_screen_proxy": round(gaze, 6),
                "gaze_on_screen_confidence": round(tracking_confidence, 6),
                "fps": 29.5,
                "fps_stability": round(quality_score, 6),
                "face_visible_pct": round(tracking_confidence, 6),
                "occlusion_score": round(max(0.0, 1.0 - quality_score), 6),
                "quality_score": round(quality_score, 6),
                "quality_confidence": round(quality_score, 6),
                "tracking_confidence": round(tracking_confidence, 6),
                "quality_flags": (
                    ["low_light", "blur", "high_yaw_pitch"] if tracking_confidence < 0.4 else []
                ),
            }
        )
    return rows


def _create_study_video(client, fixture: dict) -> tuple[dict, dict]:
    study_resp = client.post("/studies", json=fixture["study"])
    assert study_resp.status_code == 201, study_resp.text
    study = study_resp.json()

    payload = dict(fixture["video"])
    payload["study_id"] = study["id"]
    video_resp = client.post("/videos", json=payload)
    assert video_resp.status_code == 201, video_resp.text
    video = video_resp.json()
    return study, video


def _create_session(client, study_id: str, video_id: str, participant: dict) -> dict:
    session_resp = client.post(
        "/sessions",
        json={
            "study_id": study_id,
            "video_id": video_id,
            "participant": participant,
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    return session_resp.json()


def _ingest_panel_sessions(
    client,
    *,
    study_id: str,
    video_id: str,
    participants: list[dict],
    sessions: list[dict],
    timestamps_ms: list[int],
) -> None:
    for session_index, session_payload in enumerate(sessions):
        participant = (
            participants[session_index]
            if session_index < len(participants)
            else {"external_id": f"synthetic-{session_index}"}
        )
        session = _create_session(client, study_id, video_id, participant)
        session_rows = _build_trace_rows(session_payload, timestamps_ms)
        trace_resp = client.post(
            f"/sessions/{session['id']}/trace",
            content=_jsonl_rows(session_rows),
            headers={"Content-Type": "application/x-ndjson"},
        )
        assert trace_resp.status_code == 200, trace_resp.text
        assert trace_resp.json()["inserted"] == len(session_rows)


def _readout_aggregate(client, video_id: str) -> dict:
    readout_resp = client.get(
        f"/videos/{video_id}/readout",
        params={"aggregate": "true", "windowMs": 1000, "variantId": "variant-sync"},
    )
    assert readout_resp.status_code == 200, readout_resp.text
    return readout_resp.json()


def test_readout_aggregate_synchrony_with_quality_downweighting(client):
    fixture = _load_fixture()
    study, video = _create_study_video(client, fixture)

    timestamps_ms = [int(item) for item in fixture["timestamps_ms"]]
    assert len(fixture["participants"]) == 5
    assert len(fixture["sessions"]) == 5

    _ingest_panel_sessions(
        client,
        study_id=study["id"],
        video_id=video["id"],
        participants=fixture["participants"],
        sessions=fixture["sessions"],
        timestamps_ms=timestamps_ms,
    )
    payload = _readout_aggregate(client, video["id"])

    assert payload["aggregate"] is True
    assert payload["timebase"]["window_ms"] == 1000
    assert payload["aggregate_metrics"] is not None
    aggregate_metrics = payload["aggregate_metrics"]
    assert aggregate_metrics["included_sessions"] == 5
    assert aggregate_metrics["downweighted_sessions"] >= 2
    assert aggregate_metrics["attention_synchrony"] is not None
    assert aggregate_metrics["attention_synchrony"] > 0.65
    assert aggregate_metrics["blink_synchrony"] is not None
    assert aggregate_metrics["blink_synchrony"] > 0.4
    assert aggregate_metrics["grip_control_score"] is not None
    assert aggregate_metrics["grip_control_score"] > 0.45
    assert aggregate_metrics["attentional_synchrony"] is not None
    synchrony = aggregate_metrics["attentional_synchrony"]
    assert synchrony["pathway"] == "direct_panel_gaze"
    assert synchrony["global_score"] > 65.0
    assert synchrony["confidence"] > 0.7
    assert len(synchrony["segment_scores"]) >= 3
    assert len(synchrony["peaks"]) >= 1
    assert len(synchrony["valleys"]) >= 1
    assert "primary pathway" in synchrony["evidence_summary"].lower()
    assert aggregate_metrics["blink_transport"] is not None
    blink_transport = aggregate_metrics["blink_transport"]
    assert blink_transport["pathway"] in {
        "direct_panel_blink",
        "fallback_proxy",
        "sparse_fallback",
        "insufficient_data",
        "disabled",
    }
    assert "segment_scores" in blink_transport
    assert aggregate_metrics["reward_anticipation"] is not None
    reward_anticipation = aggregate_metrics["reward_anticipation"]
    assert reward_anticipation["pathway"] in {
        "timeline_dynamics",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "anticipation_ramps" in reward_anticipation
    assert "payoff_windows" in reward_anticipation
    assert aggregate_metrics["boundary_encoding"] is not None
    boundary_encoding = aggregate_metrics["boundary_encoding"]
    assert boundary_encoding["pathway"] in {
        "timeline_boundary_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "strong_windows" in boundary_encoding
    assert "weak_windows" in boundary_encoding
    assert "flags" in boundary_encoding
    assert aggregate_metrics["au_friction"] is not None
    au_friction = aggregate_metrics["au_friction"]
    assert au_friction["pathway"] in {
        "au_signal_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "segment_scores" in au_friction
    assert "warnings" in au_friction
    assert aggregate_metrics["cta_reception"] is not None
    cta_reception = aggregate_metrics["cta_reception"]
    assert cta_reception["pathway"] in {
        "multi_signal_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "cta_windows" in cta_reception
    assert "flags" in cta_reception
    assert aggregate_metrics["social_transmission"] is not None
    social_transmission = aggregate_metrics["social_transmission"]
    assert social_transmission["pathway"] in {
        "annotation_augmented",
        "timeline_signal_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "segment_scores" in social_transmission
    assert aggregate_metrics["self_relevance"] is not None
    self_relevance = aggregate_metrics["self_relevance"]
    assert self_relevance["pathway"] in {
        "contextual_personalization",
        "survey_augmented",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "segment_scores" in self_relevance
    assert aggregate_metrics["synthetic_lift_prior"] is not None
    synthetic_lift = aggregate_metrics["synthetic_lift_prior"]
    assert synthetic_lift["pathway"] in {
        "taxonomy_regression",
        "fallback_proxy",
        "insufficient_data",
    }
    if synthetic_lift["pathway"] != "insufficient_data":
        assert synthetic_lift["predicted_incremental_lift_pct"] is not None
        assert synthetic_lift["predicted_iroas"] is not None

    attention_series = payload["traces"]["attention_score"]
    reward_series = payload["traces"]["reward_proxy"]
    assert len(attention_series) == len(timestamps_ms)
    assert len(reward_series) == len(timestamps_ms)

    # Low-confidence noisy sessions are downweighted, so aggregate attention should
    # stay close to the aligned high-confidence panel profile.
    assert attention_series[0]["value"] > 62.0

    for point in attention_series:
        assert point["median"] is not None
        assert point["ci_low"] is not None
        assert point["ci_high"] is not None
        assert point["ci_low"] <= point["value"] <= point["ci_high"]

    for point in reward_series:
        assert point["median"] is not None
        assert point["ci_low"] is not None
        assert point["ci_high"] is not None
        assert point["ci_low"] <= point["value"] <= point["ci_high"]

    assert any(
        point["ci_high"] > point["ci_low"] for point in attention_series
    )
    assert any(
        point["ci_high"] > point["ci_low"] for point in reward_series
    )


def test_attentional_synchrony_higher_for_controlled_than_noisy_panel(client):
    fixture = _load_fixture()
    timestamps_ms = [int(item) for item in fixture["timestamps_ms"]]

    controlled_fixture = {
        "study": {"name": "Controlled Synchrony", "description": "High convergence panel"},
        "video": fixture["video"],
    }
    controlled_study, controlled_video = _create_study_video(client, controlled_fixture)
    _ingest_panel_sessions(
        client,
        study_id=controlled_study["id"],
        video_id=controlled_video["id"],
        participants=fixture["participants"][:3],
        sessions=fixture["sessions"][:3],
        timestamps_ms=timestamps_ms,
    )
    controlled_payload = _readout_aggregate(client, controlled_video["id"])
    controlled_sync = controlled_payload["aggregate_metrics"]["attentional_synchrony"]

    noisy_fixture = {
        "study": {"name": "Noisy Synchrony", "description": "Low convergence panel"},
        "video": fixture["video"],
    }
    noisy_study, noisy_video = _create_study_video(client, noisy_fixture)
    _ingest_panel_sessions(
        client,
        study_id=noisy_study["id"],
        video_id=noisy_video["id"],
        participants=fixture["participants"][:2],
        sessions=fixture["sessions"][3:],
        timestamps_ms=timestamps_ms,
    )
    noisy_payload = _readout_aggregate(client, noisy_video["id"])
    noisy_sync = noisy_payload["aggregate_metrics"]["attentional_synchrony"]

    assert controlled_sync["global_score"] > noisy_sync["global_score"]
    assert controlled_sync["confidence"] > noisy_sync["confidence"]
    assert controlled_sync["pathway"] == "direct_panel_gaze"
    assert noisy_sync["pathway"] in {"fallback_proxy", "insufficient_data"}
