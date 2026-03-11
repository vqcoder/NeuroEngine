# NeuroTrace

Consent-first reaction intelligence stack for video studies.

## Principles

- Privacy-first: webcam is opt-in via consent and quality-gated when enabled; study configs can require webcam eligibility.
- Scientific honesty: no direct dopamine claims; use a learned `Reward Proxy` trace.
- Monorepo architecture: aligned apps/services/ml/shared contracts.

## Default Study Flow

1. Consent.
2. Camera quality check.
3. Passive first viewing (no continuous tapping).
4. Post-view timeline annotation.
5. Short survey.

## Laptop Webcam Measurement Boundaries

- Supports coarse passive signals: AU traces, blink dynamics, face presence, head pose, coarse gaze-on-screen proxy, and quality/confidence metrics.
- Does not claim precise fixation maps, microsaccades, or research-grade eye tracking from laptop webcams.
- Face signals and gaze proxies are quality-dependent model estimates, not standalone emotion truth labels.

## Reward Proxy Definition

- `reward_proxy` is a calibrated engagement target.
- It is derived from multiple signals (not a single AU or blink rule): AU/blink dynamics, playback behavior, explicit timeline annotations, and survey labels.
- `dopamine` is treated only as a deprecated ingest alias for backward compatibility.

## Telemetry And Label Entry Points

- `apps/watchlab`: collects playback telemetry and post-view labels aligned to `video_time_ms`.
- `services/biograph_api`: ingests telemetry, traces, annotations, and survey responses; produces scene-aligned summaries.
- `services/extractor_worker`: emits passive face/blink/gaze/quality traces with confidence fields.
- `ml/training`: builds training targets/features using passive traces plus explicit labels.
- `apps/dashboard`: renders timeline layers, quality badges, and scene-level diagnostics for editors.

## Monorepo layout

- `apps/watchlab` -> Next.js study player and consent flow.
- `apps/dashboard` -> React dashboard for trace visualization.
- `services/biograph_api` -> FastAPI + Postgres ingest/summary API.
- `services/extractor_worker` -> Python extraction worker scaffold.
- `packages/common` -> shared Zod + Pydantic schema parity.
- `ml/training` -> feature extraction, training, MLflow logging.
- `ml/inference` -> inference utilities and optimizer heuristics.
- `infra/docker-compose.yml` -> local orchestration for full stack.
- `docs/` -> `SPEC.md`, `DATA_DICTIONARY.md`, `PRIVACY.md`.
  - Governance add-ons: `neuro_eval_observability.md`, `neuro_red_team_checklist.md`.
  - Integration docs: `alphaengine_neuro_migration_guide.md`, `alphaengine_release_checklist.md`.

## End-to-end hello trace (Docker)

1. Start stack:

```bash
cd infra
docker compose up --build
```

2. Open watchlab:
   - [http://localhost:3000/study/demo](http://localhost:3000/study/demo)
3. Complete consent, play video, click `Finish`.
4. Copy/open the dashboard URL shown in upload status.
5. Confirm timeline traces render in dashboard.

## What hello trace captures

- playback telemetry (`play`/`pause`/`seek`/`mute`/focus/visibility/completion)
- placeholder AU/blink dynamics for scaffold validation
- post-view timeline annotation markers + survey labels
- optional dial replay samples (calibration mode only)
- API session/trace ingestion and summary rendering

## Local tests

- Watchlab unit tests:

```bash
cd apps/watchlab
npm test
```

- Biograph API tests:

```bash
cd services/biograph_api
.venv/bin/python3 -m pytest -q tests
```

- Optimizer tests:

```bash
cd ml/inference/optimizer
../../training/.venv/bin/python3 -m pytest -q tests
```

## Cloud deploy

Railway deployment guide:

- [docs/CLOUD_RAILWAY.md](/Users/johnkim/Documents/Personal CRM and Project management app/Alpha Engine/Alpha Engine/neurotrace/docs/CLOUD_RAILWAY.md)
