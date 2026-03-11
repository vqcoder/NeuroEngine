"""Integration tests for scene-aligned readout endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas import ReadoutPayload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "readout_session.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _jsonl_rows(rows) -> str:
    return "\n".join(json.dumps(row) for row in rows)


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


def test_readout_endpoint_returns_scene_aligned_aggregate_payload(client):
    fixture = _load_fixture()
    study, video = _create_study_video(client, fixture)

    sessions = []
    for index, participant in enumerate(fixture["participants"]):
        session = _create_session(client, study["id"], video["id"], participant)
        sessions.append(session)
        ingest_resp = client.post(
            f"/sessions/{session['id']}/trace",
            content=_jsonl_rows(fixture["session_rows"][index]),
            headers={"Content-Type": "application/x-ndjson"},
        )
        assert ingest_resp.status_code == 200, ingest_resp.text
        assert ingest_resp.json()["inserted"] == len(fixture["session_rows"][index])

    annotations_resp = client.post(
        f"/sessions/{sessions[0]['id']}/annotations",
        json={
            "annotation_skipped": False,
            "annotations": [
                {
                    "session_id": sessions[0]["id"],
                    "video_id": video["id"],
                    **annotation,
                }
                for annotation in fixture["annotations"]
            ],
        },
    )
    assert annotations_resp.status_code == 200, annotations_resp.text
    assert annotations_resp.json()["inserted"] == len(fixture["annotations"])
    second_annotations_resp = client.post(
        f"/sessions/{sessions[1]['id']}/annotations",
        json={
            "annotation_skipped": False,
            "annotations": [
                {
                    "session_id": sessions[1]["id"],
                    "video_id": video["id"],
                    "marker_type": "engaging_moment",
                    "video_time_ms": 4100,
                    "note": "Second viewer engagement peak",
                    "created_at": "2026-03-05T16:11:01Z",
                },
                {
                    "session_id": sessions[1]["id"],
                    "video_id": video["id"],
                    "marker_type": "stop_watching_moment",
                    "video_time_ms": 7300,
                    "note": "Second viewer drop-off",
                    "created_at": "2026-03-05T16:11:03Z",
                },
            ],
        },
    )
    assert second_annotations_resp.status_code == 200, second_annotations_resp.text
    assert second_annotations_resp.json()["inserted"] == 2

    survey_session_one = client.post(
        f"/sessions/{sessions[0]['id']}/survey",
        json={
            "responses": [
                {"question_key": "overall_interest_likert", "response_number": 4},
                {"question_key": "recall_comprehension_likert", "response_number": 3},
                {
                    "question_key": "desire_to_continue_or_take_action_likert",
                    "response_number": 5,
                },
                {
                    "question_key": "post_annotation_comment",
                    "response_text": "Great middle section",
                },
            ]
        },
    )
    assert survey_session_one.status_code == 200, survey_session_one.text
    assert survey_session_one.json()["inserted"] == 4

    survey_session_two = client.post(
        f"/sessions/{sessions[1]['id']}/survey",
        json={
            "responses": [
                {"question_key": "overall_interest_likert", "response_number": 2},
                {"question_key": "recall_comprehension_likert", "response_number": 4},
                {
                    "question_key": "desire_to_continue_or_take_action_likert",
                    "response_number": 3,
                },
                {
                    "question_key": "post_annotation_comment",
                    "response_text": "Ending was confusing",
                },
            ]
        },
    )
    assert survey_session_two.status_code == 200, survey_session_two.text
    assert survey_session_two.json()["inserted"] == 4

    for index, session in enumerate(sessions):
        offset = index * 120
        trace_source = "provided" if index == 0 else "synthetic_fallback"
        telemetry_resp = client.post(
            f"/sessions/{session['id']}/telemetry",
            json={
                "events": [
                    {
                        "session_id": session["id"],
                        "video_id": video["id"],
                        "event_type": "pause",
                        "video_time_ms": 1800 + offset,
                        "client_monotonic_ms": 1805 + offset,
                        "wall_time_ms": 1700000018000 + offset,
                    },
                    {
                        "session_id": session["id"],
                        "video_id": video["id"],
                        "event_type": "seek_start",
                        "video_time_ms": 3000 + offset,
                        "client_monotonic_ms": 3005 + offset,
                        "wall_time_ms": 1700000030000 + offset,
                        "details": {
                            "fromVideoTimeMs": 3000 + offset,
                            "toVideoTimeMs": 2200 + offset,
                        },
                    },
                    {
                        "session_id": session["id"],
                        "video_id": video["id"],
                        "event_type": "seek_end",
                        "video_time_ms": 2200 + offset,
                        "client_monotonic_ms": 3010 + offset,
                        "wall_time_ms": 1700000030100 + offset,
                        "details": {
                            "fromVideoTimeMs": 3000 + offset,
                            "toVideoTimeMs": 2200 + offset,
                        },
                    },
                    {
                        "session_id": session["id"],
                        "video_id": video["id"],
                        "event_type": "abandonment",
                        "video_time_ms": 7600 + offset,
                        "client_monotonic_ms": 7605 + offset,
                        "wall_time_ms": 1700000076000 + offset,
                        "details": {
                            "reason": "user_ended_early",
                            "lastVideoTimeMs": 7600 + offset,
                        },
                    },
                    {
                        "session_id": session["id"],
                        "video_id": video["id"],
                        "event_type": "trace_source",
                        "video_time_ms": 0,
                        "client_monotonic_ms": 0,
                        "wall_time_ms": 1700000000000 + offset,
                        "details": {
                            "trace_source": trace_source,
                        },
                    },
                ]
            },
        )
        assert telemetry_resp.status_code == 200, telemetry_resp.text
        assert telemetry_resp.json()["inserted"] == 5

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "true", "window_ms": 1000, "variant_id": "variant-a"},
    )
    assert readout_resp.status_code == 200, readout_resp.text
    payload = readout_resp.json()
    ReadoutPayload.model_validate(payload)

    assert payload["schema_version"] == "1.0.0"
    assert payload["video_id"] == video["id"]
    assert payload["duration_ms"] == 9000
    assert payload["aggregate"] is True
    assert payload["timebase"]["window_ms"] == 1000
    assert payload["timebase"]["step_ms"] == 1000
    assert payload["context"]["scenes"] == payload["scenes"]
    assert payload["context"]["cuts"] == payload["cuts"]
    assert payload["context"]["cta_markers"] == payload["cta_markers"]
    assert len(payload["scenes"]) == 3
    assert len(payload["cuts"]) == 3
    assert len(payload["cta_markers"]) == 1
    assert payload["cta_markers"][0]["cta_id"] == "cta-main"
    assert len(payload["playback_telemetry"]) == 10
    playback_types = {item["event_type"] for item in payload["playback_telemetry"]}
    assert {"pause", "seek_start", "seek_end", "abandonment"}.issubset(playback_types)
    assert all(
        isinstance(item["video_time_ms"], int) and item["video_time_ms"] >= 0
        for item in payload["playback_telemetry"]
    )

    traces = payload["traces"]
    expected_trace_keys = {
        "attention_score",
        "attention_velocity",
        "blink_rate",
        "blink_inhibition",
        "reward_proxy",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
        "tracking_confidence",
        "au_channels",
    }
    assert expected_trace_keys.issubset(traces.keys())
    assert payload["aggregate_metrics"] is not None
    aggregate_metrics = payload["aggregate_metrics"]
    assert aggregate_metrics["included_sessions"] == 2
    assert "attention_synchrony" in aggregate_metrics
    assert "blink_synchrony" in aggregate_metrics
    assert "grip_control_score" in aggregate_metrics
    assert "narrative_control" in aggregate_metrics
    assert "blink_transport" in aggregate_metrics
    assert "reward_anticipation" in aggregate_metrics
    assert "boundary_encoding" in aggregate_metrics
    narrative = aggregate_metrics["narrative_control"]
    assert narrative is not None
    assert narrative["pathway"] in {
        "timeline_grammar",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "scene_scores" in narrative
    assert "heuristic_checks" in narrative
    blink_transport = aggregate_metrics["blink_transport"]
    assert blink_transport is not None
    assert blink_transport["pathway"] in {
        "direct_panel_blink",
        "fallback_proxy",
        "sparse_fallback",
        "insufficient_data",
        "disabled",
    }
    assert "segment_scores" in blink_transport
    assert "engagement_warnings" in blink_transport
    reward_anticipation = aggregate_metrics["reward_anticipation"]
    assert reward_anticipation is not None
    assert reward_anticipation["pathway"] in {
        "timeline_dynamics",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "anticipation_ramps" in reward_anticipation
    assert "payoff_windows" in reward_anticipation
    boundary_encoding = aggregate_metrics["boundary_encoding"]
    assert boundary_encoding is not None
    assert boundary_encoding["pathway"] in {
        "timeline_boundary_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "strong_windows" in boundary_encoding
    assert "weak_windows" in boundary_encoding
    assert "flags" in boundary_encoding
    au_friction = aggregate_metrics["au_friction"]
    assert au_friction is not None
    assert au_friction["pathway"] in {
        "au_signal_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "segment_scores" in au_friction
    assert "warnings" in au_friction
    cta_reception = aggregate_metrics["cta_reception"]
    assert cta_reception is not None
    assert cta_reception["pathway"] in {
        "multi_signal_model",
        "fallback_proxy",
        "insufficient_data",
    }
    assert "cta_windows" in cta_reception
    assert "flags" in cta_reception
    synthetic_lift = aggregate_metrics["synthetic_lift_prior"]
    assert synthetic_lift is not None
    assert synthetic_lift["pathway"] in {
        "taxonomy_regression",
        "fallback_proxy",
        "insufficient_data",
    }
    if synthetic_lift["pathway"] != "insufficient_data":
        assert synthetic_lift["predicted_incremental_lift_pct"] is not None
        assert synthetic_lift["predicted_iroas"] is not None

    for key in [
        "attention_score",
        "attention_velocity",
        "blink_rate",
        "blink_inhibition",
        "reward_proxy",
        "valence_proxy",
        "arousal_proxy",
        "novelty_proxy",
        "tracking_confidence",
    ]:
        series = traces[key]
        assert len(series) == 9
        assert [point["video_time_ms"] for point in series] == sorted(
            point["video_time_ms"] for point in series
        )
        for point in series:
            assert isinstance(point["video_time_ms"], int)
            assert point["video_time_ms"] >= 0
            assert "median" in point
            assert "ci_low" in point
            assert "ci_high" in point

    au_channels = {channel["au_name"]: channel["points"] for channel in traces["au_channels"]}
    assert {"AU04", "AU06", "AU12", "AU45", "AU25", "AU26"}.issubset(au_channels.keys())
    assert len(au_channels["AU12"]) == 9

    segments = payload["segments"]
    expected_segment_keys = {
        "attention_gain_segments",
        "attention_loss_segments",
        "golden_scenes",
        "dead_zones",
        "confusion_segments",
    }
    assert expected_segment_keys.issubset(segments.keys())
    assert len(segments["golden_scenes"]) > 0
    assert len(segments["attention_gain_segments"]) > 0
    assert len(segments["attention_loss_segments"]) > 0

    all_segments = []
    for key in expected_segment_keys:
        all_segments.extend(segments[key])
    assert len(all_segments) > 0
    assert all(item.get("scene_id") is not None for item in all_segments)
    assert all(item.get("metric") for item in all_segments)
    assert all(isinstance(item.get("magnitude"), (int, float)) for item in all_segments)
    assert all(isinstance(item.get("reason_codes"), list) for item in all_segments)
    assert any(item.get("cta_window") in {"pre_cta", "on_cta", "post_cta"} for item in all_segments)
    assert any(isinstance(item.get("distance_to_cta_ms"), int) for item in all_segments)

    diagnostics = payload["diagnostics"]
    assert len(diagnostics) >= 5
    diagnostic_types = {item["card_type"] for item in diagnostics}
    assert {
        "golden_scene",
        "hook_strength",
        "cta_receptivity",
        "attention_drop_scene",
        "confusion_scene",
        "recovery_scene",
    }.issubset(diagnostic_types)
    for item in diagnostics:
        assert isinstance(item["start_video_time_ms"], int)
        assert isinstance(item["end_video_time_ms"], int)
        assert item["end_video_time_ms"] >= item["start_video_time_ms"]
        assert isinstance(item["primary_metric"], str)
        assert isinstance(item["primary_metric_value"], (int, float))
        assert isinstance(item["why_flagged"], str)
        assert isinstance(item["reason_codes"], list)

    quality_summary = payload["quality_summary"]
    assert quality_summary["sessions_count"] == 2
    assert quality_summary["participants_count"] == 2
    assert quality_summary["total_trace_points"] == 18
    assert quality_summary["mean_tracking_confidence"] is not None
    assert quality_summary["usable_seconds"] is not None
    assert quality_summary["quality_badge"] in {"high", "medium", "low"}
    assert quality_summary["trace_source"] == "mixed"
    assert payload["quality"]["session_quality_summary"] == quality_summary
    assert isinstance(payload["quality"]["low_confidence_windows"], list)
    for window in payload["quality"]["low_confidence_windows"]:
        assert isinstance(window["start_video_time_ms"], int)
        assert isinstance(window["end_video_time_ms"], int)
        assert window["end_video_time_ms"] >= window["start_video_time_ms"]
        assert isinstance(window.get("quality_flags", []), list)

    assert len(payload["annotations"]) == len(fixture["annotations"]) + 2
    assert payload["labels"]["annotations"] == payload["annotations"]

    annotation_summary = payload["annotation_summary"]
    assert annotation_summary["total_annotations"] == len(fixture["annotations"]) + 2
    assert annotation_summary["engaging_moment_count"] == 2
    assert annotation_summary["confusing_moment_count"] == 1
    assert annotation_summary["stop_watching_moment_count"] == 1
    assert annotation_summary["cta_landed_moment_count"] == 1
    assert len(annotation_summary["marker_density"]) >= 3
    assert annotation_summary["top_engaging_timestamps"][0]["video_time_ms"] == 4000
    assert annotation_summary["top_engaging_timestamps"][0]["count"] == 2
    assert annotation_summary["top_engaging_timestamps"][0]["density"] == 1.0
    assert annotation_summary["top_confusing_timestamps"][0]["video_time_ms"] == 7000
    assert payload["labels"]["annotation_summary"] == annotation_summary

    survey_summary = payload["survey_summary"]
    assert survey_summary["responses_count"] == 8
    assert survey_summary["overall_interest_mean"] == 3.0
    assert survey_summary["recall_comprehension_mean"] == 3.5
    assert survey_summary["desire_to_continue_or_take_action_mean"] == 4.0
    assert survey_summary["comment_count"] == 2
    assert payload["labels"]["survey_summary"] == survey_summary

    neuro_scores = payload.get("neuro_scores")
    assert neuro_scores is not None
    assert neuro_scores["scores"]["arrest_score"]["machine_name"] == "arrest_score"
    assert neuro_scores["scores"]["reward_anticipation_index"]["machine_name"] == "reward_anticipation_index"
    assert neuro_scores["rollups"]["organic_reach_prior"]["machine_name"] == "organic_reach_prior"
    assert len(neuro_scores["registry"]) >= 11
    assert len(neuro_scores["rollup_registry"]) >= 3
    assert "legacy_score_adapters" in neuro_scores

    legacy_adapters = payload.get("legacy_score_adapters", [])
    assert len(legacy_adapters) == 2
    legacy_outputs = {item["legacy_output"] for item in legacy_adapters}
    assert legacy_outputs == {"emotion", "attention"}
    product_rollups = payload.get("product_rollups")
    assert product_rollups is not None
    assert product_rollups["mode"] == "creator"
    assert product_rollups["creator"] is not None
    assert product_rollups["creator"]["reception_score"]["display_label"] == "Reception Score"
    assert product_rollups["creator"]["organic_reach_prior"]["display_label"] == "Organic Reach Prior"

    enterprise_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={
            "aggregate": "true",
            "window_ms": 1000,
            "variant_id": "variant-a",
            "product_mode": "enterprise",
            "workspace_tier": "enterprise",
        },
    )
    assert enterprise_resp.status_code == 200, enterprise_resp.text
    enterprise_payload = enterprise_resp.json()
    ReadoutPayload.model_validate(enterprise_payload)
    assert enterprise_payload["product_rollups"]["mode"] == "enterprise"
    assert enterprise_payload["product_rollups"]["enterprise"] is not None
    assert (
        enterprise_payload["product_rollups"]["enterprise"]["paid_lift_prior"]["display_label"]
        == "Paid Lift Prior"
    )
    assert (
        enterprise_payload["product_rollups"]["enterprise"]["synthetic_vs_measured_lift"][
            "measured_lift_status"
        ]
        in {"unavailable", "pending", "measured"}
    )


def test_readout_endpoint_supports_single_session_mode_and_alias_migration(client):
    fixture = _load_fixture()
    study, video = _create_study_video(client, fixture)

    session = _create_session(client, study["id"], video["id"], fixture["participants"][0])
    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(fixture["session_rows"][0]),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text

    readout_resp = client.get(
        f"/videos/{video['id']}/readout",
        params={
            "session_id": session["id"],
            "aggregate": "false",
            "window_ms": 1000,
            "variant_id": "variant-a",
        },
    )
    assert readout_resp.status_code == 200, readout_resp.text
    payload = readout_resp.json()
    ReadoutPayload.model_validate(payload)

    assert payload["schema_version"] == "1.0.0"
    assert payload["aggregate"] is False
    assert payload["session_id"] == session["id"]
    assert payload["timebase"]["window_ms"] == 1000
    assert payload["quality_summary"]["sessions_count"] == 1
    assert payload["quality"]["session_quality_summary"]["sessions_count"] == 1
    assert payload["quality_summary"]["trace_source"] == "unknown"
    assert payload["neuro_scores"] is not None
    assert payload["product_rollups"] is not None
    assert payload["product_rollups"]["mode"] == "creator"
    assert len(payload["legacy_score_adapters"]) == 2
    reward_series = payload["traces"]["reward_proxy"]
    attention_series = payload["traces"]["attention_score"]
    assert reward_series[0]["video_time_ms"] == 0
    # Legacy dopamine ingest is accepted, but readout rewards are recalibrated server-side.
    assert reward_series[0]["value"] is not None
    assert abs(float(reward_series[0]["value"]) - 34.0) > 1e-3
    assert attention_series[0]["value"] != reward_series[0]["value"]


def test_readout_endpoint_backfills_legacy_synchrony_fields_when_pairwise_unavailable(client):
    fixture = _load_fixture()
    study, video = _create_study_video(client, fixture)

    session = _create_session(client, study["id"], video["id"], fixture["participants"][0])
    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(fixture["session_rows"][0]),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "true", "window_ms": 1000, "variant_id": "variant-a"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    ReadoutPayload.model_validate(payload)

    aggregate_metrics = payload["aggregate_metrics"]
    assert aggregate_metrics is not None
    assert aggregate_metrics["blink_synchrony"] is None
    assert aggregate_metrics["attentional_synchrony"] is not None
    assert aggregate_metrics["attentional_synchrony"]["global_score"] is not None
    assert aggregate_metrics["attention_synchrony"] is not None
    assert aggregate_metrics["grip_control_score"] is not None

    global_score = float(aggregate_metrics["attentional_synchrony"]["global_score"])
    expected_signed = max(min((global_score / 50.0) - 1.0, 1.0), -1.0)
    assert abs(float(aggregate_metrics["attention_synchrony"]) - expected_signed) < 1e-6
    assert (
        abs(
            float(aggregate_metrics["grip_control_score"])
            - float(aggregate_metrics["attention_synchrony"])
        )
        < 1e-6
    )


def test_readout_endpoint_injects_variance_for_flat_blink_and_reward_series(client):
    fixture = _load_fixture()
    study, video = _create_study_video(client, fixture)

    session = _create_session(client, study["id"], video["id"], fixture["participants"][0])
    flat_rows = []
    for row in fixture["session_rows"][0]:
        au_payload = {
            "AU04": 0.03,
            "AU06": 0.06,
            "AU12": 0.16,
            "AU45": 0.0,
            "AU25": 0.03,
            "AU26": 0.03,
        }
        flat_rows.append(
            {
                "t_ms": int(row["t_ms"]),
                "face_ok": True,
                "brightness": 24.0,
                "landmarks_ok": True,
                "blink": 0,
                "rolling_blink_rate": 0.21,
                "blink_baseline_rate": 0.21,
                "blink_inhibition_score": 0.0,
                "reward_proxy": 35.0,
                "quality_confidence": 0.93,
                "quality_score": 0.91,
                "tracking_confidence": 0.94,
                "face_presence_confidence": 0.95,
                "gaze_on_screen_proxy": 0.88,
                "eye_openness": 0.82,
                "occlusion_score": 0.08,
                "head_pose_valid_pct": 0.95,
                "au": dict(au_payload),
                "au_norm": dict(au_payload),
                "head_pose": {"yaw": 0.01, "pitch": 0.0, "roll": 0.0},
            }
        )

    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(flat_rows),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["inserted"] == len(flat_rows)

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "true", "window_ms": 1000, "variant_id": "variant-a"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    ReadoutPayload.model_validate(payload)

    blink_values = [
        float(point["value"])
        for point in payload["traces"]["blink_rate"]
        if point.get("value") is not None
    ]
    reward_values = [
        float(point["value"])
        for point in payload["traces"]["reward_proxy"]
        if point.get("value") is not None
    ]
    assert len(blink_values) == len(flat_rows)
    assert len(reward_values) == len(flat_rows)
    assert max(blink_values) - min(blink_values) > 0.06  # half_span=0.10 → visible range
    assert max(reward_values) - min(reward_values) > 0.2

    aggregate_metrics = payload["aggregate_metrics"]
    assert aggregate_metrics is not None
    assert aggregate_metrics["narrative_control"] is not None
    assert aggregate_metrics["narrative_control"]["global_score"] is not None
    assert aggregate_metrics["attentional_synchrony"] is not None
    assert aggregate_metrics["attentional_synchrony"]["global_score"] is not None
    assert aggregate_metrics["grip_control_score"] is not None


def test_readout_endpoint_rejects_non_aggregate_without_session(client):
    fixture = _load_fixture()
    _, video = _create_study_video(client, fixture)

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={"aggregate": "false"},
    )
    assert response.status_code == 400, response.text
    assert "session_id" in response.text


def test_readout_endpoint_validates_variant_filter(client):
    fixture = _load_fixture()
    _, video = _create_study_video(client, fixture)

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={"variant_id": "variant-does-not-exist"},
    )
    assert response.status_code == 404, response.text


def test_readout_endpoint_supports_legacy_alias_params(client):
    fixture = _load_fixture()
    study, video = _create_study_video(client, fixture)

    session = _create_session(client, study["id"], video["id"], fixture["participants"][0])
    ingest_resp = client.post(
        f"/sessions/{session['id']}/trace",
        content=_jsonl_rows(fixture["session_rows"][0]),
        headers={"Content-Type": "application/x-ndjson"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text

    response = client.get(
        f"/videos/{video['id']}/readout",
        params={
            "sessionId": session["id"],
            "aggregate": "false",
            "windowMs": 1000,
            "variantId": "variant-a",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    ReadoutPayload.model_validate(payload)
    assert payload["session_id"] == session["id"]
