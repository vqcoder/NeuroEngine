# Readout Dashboard Implementation Plan

## Milestone 0: Spec and contract lock
- Finalize metrics, naming, and acceptance criteria in `docs/readout_dashboard_spec.md`.
- Confirm canonical naming (`reward_proxy`) and deprecation handling for legacy aliases.
- Confirm dashboard dependencies on `video_time_ms`, scene IDs, annotations, telemetry, and quality overlays.

Validation commands:
- `cd neurotrace && rg -n "dopamine|reward_proxy|video_time_ms" docs apps services ml`
- `cd neurotrace && rg -n "scene_id|cut_id|cta_id|tracking_confidence|session_quality" docs apps services`

## Milestone 1: Backend summary contract hardening
- Ensure `GET /videos/{id}/summary` exposes required metric/time-series fields for Readout Dashboard.
- Verify scene-aware IDs are propagated where available.
- Verify annotations + playback telemetry are queryable for dashboard read models.
- Ensure quality/confidence fields are included for webcam-derived signals.

Validation commands:
- `cd neurotrace/services/biograph_api && .venv/bin/python3 -m pytest -q tests/test_integration_summary.py tests/test_playback_telemetry.py tests/test_trace_extra_fields.py`
- `cd neurotrace/services/biograph_api && .venv/bin/python3 -m pytest -q tests/test_migrations.py`

## Milestone 2: Dashboard data adapter and timeline layers
- Normalize incoming summary payload into dashboard timeline models keyed on `video_time_ms`.
- Add/update layers for required metrics and markers.
- Render quality/confidence warnings and coarse-gaze explanatory note.
- Keep scene-level overlays and player seek interactions.

Validation commands:
- `cd neurotrace/apps/dashboard && npm run build`
- `cd neurotrace/apps/dashboard && npm run test:e2e`

## Milestone 3: Export and scene diagnostics
- Ensure CSV/JSON exports include required metric fields, quality/confidence, annotations, and scene IDs.
- Validate Golden Scenes / Dead Zones rely on backend summary outputs (no duplicate business logic drift).

Validation commands:
- `cd neurotrace/apps/dashboard && npm run test:e2e`
- `cd neurotrace && rg -n "reward_proxy|attention_score|blink_inhibition|tracking_confidence|session_quality" apps/dashboard/src`

## Milestone 4: Copy and governance pass
- Remove/replace any overclaiming copy in UI, docs, and schema descriptions.
- Ensure UI labels use `Reward Proxy` wording with estimate/proxy clarification where useful.
- Verify no direct dopamine measurement or precise eye-tracking claims remain.

Validation commands:
- `cd neurotrace && rg -n "measured dopamine|direct dopamine|fixation|microsaccade|pupilometry|precise eye tracking" README.md docs apps services ml packages`
- `cd neurotrace && rg -n "Reward Proxy|reward_proxy|deprecated alias" docs apps services ml packages`

## Milestone 5: End-to-end verification and rollout checklist
- Validate watchlab -> API -> dashboard readout path for one representative session.
- Confirm trace alignment and annotation/telemetry visibility in dashboard.
- Document release notes, migration notes, and fallback behavior.

Validation commands:
- `cd neurotrace/apps/watchlab && npm test -- --runInBand`
- `cd neurotrace/apps/watchlab && npm run test:e2e`
- `cd neurotrace/services/biograph_api && .venv/bin/python3 -m pytest -q tests`
- `cd neurotrace/apps/dashboard && npm run build && npm run test:e2e`
