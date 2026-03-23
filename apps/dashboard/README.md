# biotrace_dashboard

React dashboard for visualizing `/videos/{id}/readout` from `biograph_api`.

## Features

- Video player synced with timeline chart
- Analyst home catalog that auto-lists recorded videos/sessions from `GET /videos`
- Dedicated predictor page (`/predictor`) to submit a video URL and preview model-predicted reaction traces
- Dedicated observability page (`/observability`) for drift/fallback/missing-signal monitoring plus capture-archive ingest/storage health
- Versioned scene-first timeline report (`/videos/<id>/timeline-report`) with togglable neuro-score evidence tracks
- Product rollup panels:
  - Creator mode: `Reception Score` + `Organic Reach Prior` + concise creator warnings
  - Enterprise mode: `Paid Lift Prior`, `Brand Memory Prior`, `CTA Reception Score`, and synthetic-vs-measured lift distinction
- Multi-trace chart:
  - attention_score
  - attention_velocity
  - blink_rate
  - blink_inhibition
  - reward_proxy
  - tracking_confidence
  - selectable AU channels
- Overlays for scenes, cuts, CTA markers, annotations, and low-confidence windows
- Click chart point to seek video
- Computed insights:
  - Golden Scenes
  - Dead Zones
  - Attention Gains
  - Attention Losses
  - Confusion / Friction Moments
- Export button downloads:
  - readout CSV traces
  - readout JSON payload
  - edit suggestions stub JSON (candidate trims/reorder/CTA timing)
- Export package button downloads:
  - per-timepoint metrics CSV
  - scene/segment/diagnostic JSON export object
  - compact report JSON for downstream PDF rendering
- Playwright e2e test coverage

## Interpretation guardrails

- `reward_proxy` and `attention` are model proxies, not direct dopamine or biochemical measurements.
- Gaze values are coarse webcam-based on-screen probabilities, not precise fixation coordinates.
- Face-derived traces should be interpreted with confidence/quality gating context; low-confidence windows are explicitly shaded.

## Run

```bash
npm install
npm run dev
```

Open: `http://127.0.0.1:5173/videos/<videoId>`
or use landing page: `http://127.0.0.1:5173/` and open from the recordings catalog.
Predictor page: `http://127.0.0.1:5173/predictor`
Observability page: `http://127.0.0.1:5173/observability`
Timeline-first report: `http://127.0.0.1:5173/videos/<videoId>/timeline-report`

Default API base: `http://127.0.0.1:8000`.
Override with:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## e2e

```bash
npx playwright install chromium
npm run test:e2e
```

## Unit snapshots

```bash
npm run test:unit
```

## JS Mirror Sync

- TypeScript files are the source of truth for mirrored `src/**/*.js` artifacts used by Node-only tests.
- Check mirror parity:

```bash
npm run check:js-mirrors
```

- Regenerate mirrors after TS edits:

```bash
npm run sync:js-mirrors
```

## Build

```bash
npm run build
```

## Docker / Cloud

- Dockerfile is included for managed cloud deploys.
- Set `VITE_API_BASE_URL` to your deployed `biograph_api` URL.


