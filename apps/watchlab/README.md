# watchlab

`watchlab` is a Next.js web app for running a consent-first video study with optional webcam capture.

## Features

- Route: `/study/[studyId]`
- Library upload route: `/upload`
- Video library manager stores uploaded study-video links in browser local storage
- Sequence launch links include `video_url` and title overrides per study
- One-click next-study CTA appears after first-pass playback ends (when launched from library sequence)
- Consent gate with explicit `I agree` action
- Consent copy distinguishes:
  - optional participation
  - raw webcam capture vs derived features
  - retention/deletion policy handling
- Staged participant flow:
  - onboarding consent
  - camera readiness check
  - passive first viewing (no in-play tapping)
  - post-view timeline annotation with scrubber + timestamp markers
  - post-video GPT reflection chat survey + quick ratings
- Webcam collection requirements are study-configurable; default demo flow allows continue-without-webcam while preserving camera quality gating when webcam is enabled
- Camera readiness step includes audio confirmation before study playback
- Continuous webcam quality checks:
  - average brightness
  - face detection (via browser `FaceDetector` API when available)
  - FPS estimate
- Capability boundaries are explicit in UI copy:
  - reward/attention outputs are proxies
  - gaze is coarse webcam proxy, not precise eye tracking
- Study video playback from study config endpoint (`/api/study/[studyId]/config`)
- Event timeline with `sessionId`, `videoId`, `videoTimeMs`, wall clock ms, and client monotonic ms
- Playback telemetry includes:
  - `play` / `pause` / `seek` / `rewind` / `ended`
  - `mute` / `unmute`
  - fullscreen enter/exit
  - document visibility and window focus/blur
  - incomplete-session markers
- `videoTimeMs` playback clock kept in sync with video playback
- Continuous dial mode (`0-100`) is optional and only shown in post-view annotation replay
- Annotation markers support:
  - `engaging_moment`
  - `confusing_moment`
  - `stop_watching_moment`
  - `cta_landed_moment`
  - optional note text
- First-pass webcam capture stops automatically when playback ends
- Post-video survey uses a guided reflection chat:
  - GPT (elite neuroscientist interviewer persona) asks one question at a time
  - question selection is adaptive per viewing signal coverage and user responses
  - events are grounded in playback telemetry, annotation markers, and quality windows
  - interviewer language is proxy-safe (no direct dopamine claim)
  - plus quick rating sliders for aggregate scoring
- Webcam frame capture at `224x224` JPEG every `200ms`
- Finish gating so submit unlocks only after full video completion
- Upload endpoint (`/api/upload`) with Zod validation

## Session Upload Schema

On `Finish`, the app posts to `/api/upload` with:

- `studyId`
- `participantId` (UUID)
- `browserMetadata`
- `eventTimeline`
- `dialSamples`
- `traceRows` (canonical passive trace rows aligned to `video_time_ms`; required for non-demo studies)
- `annotations`
- `annotationSkipped`
- `surveyResponses`
- `frames` and/or `framePointers`

Validation schema lives in [lib/schema.ts](/Users/johnkim/Documents/Personal CRM and Project management app/Alpha Engine/Alpha Engine/neurotrace/apps/watchlab/lib/schema.ts).

## Local Development

1. Install dependencies:

```bash
npm install
```

2. Run dev server:

```bash
npm run dev
```

3. Open [http://localhost:3000/study/demo](http://localhost:3000/study/demo).
   or [http://localhost:3000/upload](http://localhost:3000/upload) to build a study sequence.

## Tests

- Jest unit tests (schema + video clock):

```bash
npm test
```

- Playwright smoke tests:

```bash
npx playwright install chromium
npm run test:e2e
```

- Run all tests:

```bash
npm run test:all
```

## Docker Compose (Local Dev)

```bash
cd ../../infra
docker compose up --build
```

App will be available at [http://localhost:3000](http://localhost:3000).

## API Routes

- `GET /api/study/[studyId]/config`
  - returns the study config including MP4 URL
  - uses `DEFAULT_STUDY_VIDEO_URL` (defaults to `/sample.mp4`)
  - accepts optional query overrides:
    - `video_url` (http/https or local `/...`)
    - `title`
    - `video_id`

- `POST /api/upload`
  - validates payload with Zod
  - returns generated `sessionId` on success
  - forwards provided `traceRows` directly to `biograph_api` when present
  - forwards `frames`/`framePointers` to `biograph_api` capture archive endpoint when available
  - rejects uploads that omit `traceRows` unless synthetic fallback is explicitly allowed
  - synthetic fallback is allowed for `studyId=demo` or when `WATCHLAB_ALLOW_SYNTHETIC_TRACE_FALLBACK=true`
  - auto-provisions a study/video in `biograph_api` if IDs are not preconfigured
  - gracefully continues when legacy `biograph_api` deployments do not expose telemetry/capture endpoints
  - returns a dashboard URL (when `DASHBOARD_BASE_URL` is set) to inspect traces

## Cloud

Set these env vars for deployed watchlab:

- `BIOGRAPH_API_BASE_URL`
- `DASHBOARD_BASE_URL`
- `DEFAULT_STUDY_VIDEO_URL` (can stay `/sample.mp4` for demo)
- `STUDY_DIAL_ENABLED` (`false` for passive viewer sessions, `true` for calibration studies)
- `STUDY_REQUIRE_WEBCAM` (`false` default; set `true` for strict legacy studies that require webcam)
- `WATCHLAB_ALLOW_SYNTHETIC_TRACE_FALLBACK` (`false` default; set `true` only for demo/scaffold sessions)
