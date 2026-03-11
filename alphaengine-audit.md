# AlphaEngine Platform Audit

Date: 2026-03-10
Codebase: `github.com/johnvqcapital/neurotrace` (commit `a0d619a`, branch `main`)

---

## 1. App Architecture & Tech Stack

### Product Identity

AlphaEngine is a consent-first reaction intelligence platform for video studies. The internal codebase is called NeuroTrace. The product captures synchronized biometric viewing signals (attention proxies, blink dynamics, action unit traces, quality/confidence metrics, and survey/annotation labels) during consented video viewing sessions and computes a taxonomy of neuroscience-grounded engagement scores with actionable editorial recommendations.

**Brand**: Lime green (#c8f031) alpha symbol (α) on dark (#08080a) background. Fonts: JetBrains Mono (code/UI), DM Sans (body), Instrument Serif (display). Dark-mode-first design.

### Monorepo Layout

```
neurotrace-main/
├── apps/
│   ├── watchlab/          # Study runner — Next.js 15 (React 19)
│   └── dashboard/         # Analytics dashboard — React 19 + Vite + MUI 7
├── services/
│   ├── biograph_api/      # Core API — FastAPI + PostgreSQL + SQLAlchemy
│   └── extractor_worker/  # Biometric extraction — Python + MediaPipe + OpenCV
├── packages/
│   └── common/            # Shared schema contracts (Zod + Pydantic)
├── ml/
│   ├── training/          # XGBoost training pipeline + MLflow
│   └── inference/         # Heuristic edit suggestion optimizer
├── infra/                 # Docker Compose + Terraform (stub)
├── .github/workflows/     # CI: Guardian checks, contract validation, weekly audit
└── docs/                  # SPEC, DATA_DICTIONARY, migration guides
```

### Technology Stack

| Layer | Technology | Details |
|-------|-----------|---------|
| **WatchLab** (study runner) | Next.js 15.5, React 19, HLS.js, Zod, AWS S3 SDK | App Router, server-side API routes, browser FaceDetection API |
| **Dashboard** (analytics) | React 19, Vite 6, MUI 7, Recharts, React Router 7, Zod | SPA with synchronized video-chart playback |
| **Biograph API** (backend) | FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, psycopg 3, httpx | 52+ REST endpoints, Bearer token auth |
| **Extractor Worker** | Python, MediaPipe FaceMesh, OpenCV, NumPy | Frame-level biometric extraction CLI |
| **ML Training** | XGBoost, scikit-learn, pandas, MLflow | Per-second feature models (4 targets) |
| **ML Inference** | Pure Python heuristic engine | Edit suggestion generation |
| **Database** | PostgreSQL 16 | 16 tables, UUID PKs, Alembic migrations |
| **Infrastructure** | Docker Compose (5 services), Railway (cloud), Vercel (dashboard) | GitHub Actions CI (4 workflows) |
| **External APIs** | OpenAI (GPT-4.1-mini for survey chat), GitHub Releases (video asset hosting), Vimeo API, yt-dlp, ffprobe/ffmpeg | |

### Deployment

- **Production**: Railway (biograph_api, watchlab, PostgreSQL), Vercel (dashboard)
- **CORS**: `*.railway.app`, `*.vercel.app`, `*.alphaengine.ai`, `*.alpha-engine.ai`
- **Local dev**: Docker Compose with 5 services (db, api, watchlab, dashboard, extractor_worker)

---

## 2. Complete Module Inventory

### Module 1: WatchLab — Study Player & Consent Flow
**Purpose**: Participant-facing video study runner with consent, webcam capture, passive viewing, post-view annotation, and AI-powered survey.
**Key files**: `apps/watchlab/app/study/[studyId]/study-client.tsx` (state machine: onboarding → camera → watch → annotation → survey → next_video → complete), `apps/watchlab/lib/schema.ts` (255 lines, Zod schemas for all data types)
**State**: Production-ready

### Module 2: Video Upload & Library
**Purpose**: Video library management with URL-based import, GitHub Release hosting, and study sequence generation.
**Key files**: `apps/watchlab/app/upload/page.tsx`, `apps/watchlab/lib/videoLibrary.ts`
**State**: Production-ready

### Module 3: Video URL Resolution
**Purpose**: Multi-strategy URL resolution: Vimeo config API → HTML scraping (og:video, JSON-LD) → yt-dlp fallback. Platform blocking for TikTok, Instagram, Twitter/X, Facebook, LinkedIn, Snapchat.
**Key files**: `apps/watchlab/app/api/video/resolve/route.ts`, `services/biograph_api/app/main.py` (lines 261–625)
**State**: Production-ready

### Module 4: HLS Streaming Proxy
**Purpose**: Proxies HLS manifests and segments to bypass third-party CORS restrictions.
**Key files**: `apps/watchlab/app/api/video/hls-proxy/route.ts`
**State**: Production-ready

### Module 5: Webcam Capture & Quality Gating
**Purpose**: Browser-side webcam capture with real-time quality scoring (brightness, blur, FPS, face confidence). Pre-study camera quality check gate.
**Key files**: `apps/watchlab/lib/qualityMetrics.ts`, `packages/common/quality_thresholds.json`
**State**: Production-ready

### Module 6: Session Telemetry
**Purpose**: Collects 28+ event types during viewing: playback (play/pause/seek/stall), attention (tab visibility, window focus), and engagement (mute, fullscreen, volume). All timestamped to `video_time_ms`.
**Key files**: `apps/watchlab/lib/schema.ts` (event type enums), `services/biograph_api/app/models.py` (SessionPlaybackEvent)
**State**: Production-ready

### Module 7: Timeline Annotation
**Purpose**: Post-view marker placement: `engaging_moment`, `confusing_moment`, `stop_watching_moment`, `cta_landed_moment`.
**State**: Production-ready

### Module 8: AI Survey Chat
**Purpose**: OpenAI GPT-4.1-mini "Dr. NeuroTrace" interviewer with adaptive focus selection across 6 categories (engagement, drop, confusion, CTA, playback, quality). Deterministic fallback when no API key configured.
**Key files**: `apps/watchlab/app/api/survey-chat/route.ts`
**State**: Production-ready

### Module 9: Biometric Trace Extraction (Extractor Worker)
**Purpose**: Frame-level extraction via MediaPipe FaceMesh: face presence, 468 landmarks, eye openness (EAR), blink detection, AU proxies (AU04/AU06/AU12/AU25/AU26/AU45), head pose (PnP solve), gaze-on-screen proxy, quality scoring. Outputs ~35 fields per frame as JSONL.
**Key files**: `services/extractor_worker/biotrace_extractor/extractor.py` (pipeline), `blink.py`, `head_pose.py`, `au_proxy.py`, `quality.py`, `rolling.py`
**State**: Production-ready

### Module 10: Biograph API — Core Backend
**Purpose**: Central API with 52+ endpoints for study/video/session management, trace ingestion, readout computation, prediction, and observability.
**Key files**: `services/biograph_api/app/main.py` (2,887 lines), `services.py` (5,211 lines), `models.py` (523 lines), `config.py`
**State**: Production-ready (monolithic — services.py is a god file)

### Module 11: Readout Dashboard
**Purpose**: Interactive analytics: video catalog, multi-trace charts synchronized with video playback, neuro scorecards, product rollup panels, export (CSV/JSON/edit suggestions).
**Key files**: `apps/dashboard/src/pages/VideoDashboardPage.tsx` (2,071 lines), `VideoTimelineReportPage.tsx` (804 lines), `PredictorPage.tsx`, `ObservabilityPage.tsx`
**Navigation**: Library (external) → Catalog → Predictor → Observability
**Routes**: `/`, `/videos/:id`, `/videos/:id/timeline-report`, `/predictor`, `/observability`
**State**: Production-ready

### Module 12: Neuro Score Taxonomy
**Purpose**: Self-registering score builder system computing 11 individual scores and 3 composite rollups with confidence values, evidence windows, feature attributions, and claim-safe descriptions.
**Key files**: `services/biograph_api/app/neuro_score_taxonomy.py` (2,092 lines)
**State**: Production-ready

### Module 13: Neuro Score Diagnostic Modules (8 modules)
**Purpose**: Specialized analysis for each score dimension.
**Files and line counts**:
- `synthetic_lift_prior.py` (1,012 lines) — Incrementality calibration
- `timeline_feature_store.py` (2,068 lines) — Scene/shot/audio feature extraction
- `neuro_observability.py` (616 lines) — Drift tracking
- `neuro_eval_runner.py` (333 lines) — Evaluation orchestration
- `claim_safety.py` (62 lines) — Overclaim regex blocking
- Plus: `au_friction.py`, `blink_transport.py`, `boundary_encoding.py`, `cta_reception.py`, `narrative_control.py`, `reward_anticipation.py`, `self_relevance.py`, `social_transmission.py`
**State**: Production-ready

### Module 14: Product Rollups
**Purpose**: Tier-aware presentation: Creator mode (Reception + Organic Reach) vs Enterprise mode (Paid Lift + Brand Memory + CTA + Synthetic Lift).
**Key files**: `services/biograph_api/app/product_rollups.py` (584 lines), `apps/dashboard/src/components/ProductRollupPanel.tsx`
**State**: Production-ready

### Module 15: Predictor / ML Inference
**Purpose**: Predict biometric traces from video content alone using XGBoost models. Async job queue with in-memory storage (2-hour TTL).
**Training**: 4 targets (reward_proxy, blink_inhibition, dial, attention), 4 features (shot_change_rate, brightness, motion_magnitude, audio_rms), XGBRegressor (n=200, depth=4, lr=0.06).
**Key files**: `services/biograph_api/app/predict_service.py`, `ml/training/ml_pipeline/` (11 Python files)
**State**: Working (requires pre-trained artifact; heuristic fallback available)

### Module 16: Edit Suggestion Optimizer
**Purpose**: Heuristic editorial recommendations from readout analysis: dead zone cuts, confusion reorders, late peak restructuring.
**Key files**: `ml/inference/optimizer/engine.py`, `scoring.py`, `models.py`
**State**: Working (offline pipeline, not yet an API endpoint)

### Module 17: Readout Guardian
**Purpose**: AST-hashing integrity checker preventing unauthorized readout formula changes. CI-enforced with PR checks, weekly audits, and controlled baseline updates.
**Key files**: `services/biograph_api/app/readout_guardian.py`, `readout_guardian_baseline.json`, 3 GitHub Actions workflows
**State**: Production-ready

### Module 18: Reliability Engine
**Purpose**: 100-point reliability score across 6 dimensions: availability (30pts), range_validity (20), pathway_quality (20), signal_health (15), duration_accuracy (10), rollup_integrity (5).
**Key files**: `services/biograph_api/app/reliability_engine.py`
**State**: Production-ready

### Module 19: Observability & Drift Tracking
**Purpose**: Monitors neuro pipeline health: confidence distributions, 10 signal pathways (biometric vs non-biometric), drift detection, frontend diagnostic event ingestion.
**Key files**: `services/biograph_api/app/neuro_observability.py`, `apps/dashboard/src/pages/ObservabilityPage.tsx`
**State**: Production-ready

### Module 20: Active Learning
**Purpose**: Uncertainty-based session ranking for targeted re-evaluation. Early-segment weighting for attention capture importance.
**Key files**: `services/biograph_api/app/active_learning.py`
**State**: Working (queue construction; manual model retraining integration)

### Module 21: Shared Schema Contracts
**Purpose**: Dual-language (Zod + Pydantic) schema parity for 4 contract domains: session bundle, neuro score taxonomy, readout aggregate metrics, product rollups. CI-validated.
**Key files**: `packages/common/zod/` (4 files), `packages/common/pydantic/` (4 files + `__init__.py`)
**State**: Production-ready

### Module 22: Database & Migrations
**Purpose**: PostgreSQL 16, SQLAlchemy ORM, 16 tables, 11 Alembic migration versions.
**State**: Production-ready

### Module 23: CI/CD
**Purpose**: 4 GitHub Actions workflows: readout-guardian-check, shared-contracts-check, readout-guardian-weekly-audit, readout-guardian-baseline-update.
**State**: Production-ready

---

## 3. Scores & Metrics — Complete Taxonomy

### 11 Individual Neuro Scores (all 0–100 scale, 0–1 confidence)

| # | Score | Description | Formula / Pathway |
|---|-------|-------------|-------------------|
| 1 | **Arrest Score** | Opening stop-power proxy. How strongly the first seconds hold attention before the skip/abandon decision. | `0.65 × opening_attention + 0.35 × opening_reward_proxy` (first 3 buckets) |
| 2 | **Attentional Synchrony Index** | Cross-viewer focus convergence. High = viewers attend the same moments simultaneously. | Signed synchrony → 0–100 via `(x + 1) × 50`. Prefers direct panel gaze; fallback: aggregate synchrony proxy. |
| 3 | **Narrative Control Score** | Cinematic grammar and transition structure consistency. High = structure feels intentional. | Prefers diagnostics global score. Fallback: grip-control transform → attention-velocity stability. |
| 4 | **Blink Transport Score** | Blink suppression alignment with scene transitions. High = viewers pulled through cuts without friction. | Prefers diagnostics score. Uses suppression/rebound/CTA avoidance/synchrony features. Fallback: blink inhibition mean → 0–100. |
| 5 | **Boundary Encoding Score** | Scene boundary registration effectiveness. High = cuts feel purposeful. | Prefers diagnostics score. Fallback: attention near cut boundaries, penalizing overload, rewarding aligned novelty. |
| 6 | **Reward Anticipation Index** | Anticipatory pull into payoff moments. Do viewers lean in before rewards land? | Prefers diagnostics score. Uses ramp strength + payoff release + tension-release balance − warning penalty. Fallback: reward proxy mean. |
| 7 | **Social Transmission Score** | Shareability proxy separating "worth sharing" from self-relevance. | `0.45 × engage_density + 0.30 × synchrony_component + 0.25 × reward_component → scaled 0–100` |
| 8 | **Self-Relevance Score** | How personally meaningful the content felt. Primarily survey-derived. | Survey scale 1–5 → `(avg − 1) / 4 × 100`. Confidence rises with response count. |
| 9 | **CTA Reception Score** | Viewer receptivity at the call-to-action moment. | Prefers CTA diagnostics score. Fallback: cta_receptivity card metric → mean reward proxy near CTA markers. |
| 10 | **Synthetic Lift Prior** | Predictive estimate of media performance lift. A prior, NOT measured incrementality. | Prefers diagnostics score × pathway weight × calibration weight. Fallback: `50 + (golden_mean − dead_mean) × 5`, clamped 0–100. |
| 11 | **AU Friction Score** | Facial coding friction detector: confusion, strain, tension, resistance signals. | Features: confusion/strain/tension/resistance/amusement + quality modifier. Fallback: confusion segments + AU04 trace. Diagnostic scope only. |

### 3 Composite Rollups

| Rollup | Formula | Description |
|--------|---------|-------------|
| **Organic Reach Prior** | `0.25 arrest + 0.20 narrative_control + 0.20 self_relevance + 0.20 social_transmission + 0.15 cta_reception` | Predicted organic distribution potential |
| **Paid Lift Prior** | `0.30 synthetic_lift_prior + 0.25 cta_reception + 0.20 reward_anticipation + 0.15 synchrony + 0.10 arrest` | Predicted paid media performance lift |
| **Brand Memory Prior** | `0.25 boundary_encoding + 0.25 narrative_control + 0.20 self_relevance + 0.15 reward_anticipation + 0.15 blink_transport` | Predicted brand recall and memory encoding potential |

### Product Modes

**Creator Mode** (default tier):
- **Reception Score**: `0.45 cta_reception + 0.20 arrest + 0.20 synchrony + 0.15 reward_anticipation`
- **Organic Reach Prior** (composite rollup above)
- Warnings: weak hook, low synchrony, poor payoff timing, CTA collapse

**Enterprise Mode**:
- **Paid Lift Prior** (composite rollup above)
- **Brand Memory Prior** (composite rollup above)
- **CTA Reception Score** (individual score)
- **Synthetic Lift Prior** (individual score)
- Synthetic vs. measured lift comparison
- Decision support summaries (media team + creative team)

### Score Infrastructure

Each score produces a `NeuroScoreContract` containing:
- `machine_name`, `scalar_value` (0–100), `confidence` (0–1)
- `status`: available | insufficient_data | unavailable
- `evidence_windows`: timestamped ranges that drove the score
- `top_feature_contributions`: signal features with contribution weights (+/−)
- `model_version`: `neuro_taxonomy_v1`
- `provenance`: preferred_diagnostic | fallback_proxy | synthetic_fallback
- `claim_safe_description`: regex-validated description preventing overclaims

### Client-Side Attention Computation (Dashboard)

```
raw_attention = AU12 × 0.5 + AU06 × 0.25 − AU04 × 0.2 − blinkRate × 0.35 + rewardSignal × 0.4
```
Scaled to 0–100 via min-max normalization.

**Golden scene scoring**: `attention × 0.7 + rewardSignal × 0.3 + localityBoost(4)`

**Dead zone detection**: 30th percentile attention threshold + 70th percentile blink/AU4 friction threshold. Minimum 2 consecutive buckets.

### 9 Trace Layers (time-series signals)

| Trace | Description |
|-------|-------------|
| Attention Score | Blink-dynamics and passive playback continuity proxy (0–100) |
| Attention Velocity | Rate of change in attention. Positive = rising, negative = dropping. |
| Blink Rate | Rolling blink frequency. Lower = higher cognitive engagement. |
| Blink Inhibition | Blink suppression relative to baseline. High = visually captured. |
| Reward Proxy | AU-derived reward signal (0–100). Proxy for positive engagement. |
| Valence Proxy | Positive/negative affective tone from AU signals. Directional only. |
| Arousal Proxy | Activation/energy level from AU + blink dynamics. |
| Novelty Proxy | Novelty response from attention velocity + blink patterns. |
| Tracking Confidence | Quality/confidence for webcam-derived traces. Below ~0.6 = unreliable. |

### Scene Diagnostics (6 card types)

Hook Strength, Golden Scene, CTA Receptivity, Attention Drop Scene, Confusion Scene, Recovery Scene — each with timestamped windows pointing to specific video moments.

### Segment Types

Golden Scenes (peak engagement), Dead Zones (sustained low attention + friction), Attention Gains (rising engagement), Attention Losses (declining engagement), Confusion Segments (blink/AU/velocity friction patterns).

---

## 4. Data Flow Pipeline

### End-to-End Flow

```
1. ASSET UPLOAD
   Researcher adds video URL → multi-strategy resolution → GitHub Release hosting

2. STUDY SESSION
   Participant: consent → camera check → passive viewing → annotation → survey

   During viewing, WatchLab captures:
   - Webcam frames (JPEG, ~30fps)
   - 28+ timeline events (play/pause/seek/visibility/focus)
   - Quality samples (brightness, blur, FPS, face confidence)
   - Dial samples (optional continuous rating)

3. SESSION UPLOAD (WatchLab → Biograph API)
   forwardToBiograph() orchestrates:
   POST /studies           → Study record
   POST /videos            → Video + scene graph (scenes, cuts, CTA markers)
   POST /sessions          → Session + participant (upsert by study_id + external_id)
   POST /sessions/{id}/trace       → Trace JSONL (~35 fields per frame)
   POST /sessions/{id}/telemetry   → Playback events
   POST /sessions/{id}/annotations → Annotation markers
   POST /sessions/{id}/survey      → Survey responses
   POST /sessions/{id}/captures    → Webcam archive (gzip + SHA256)

4. TRACE EXTRACTION (Extractor Worker)
   MediaPipe FaceMesh → face landmarks → blink/AU/head-pose/gaze/quality
   Output: ~35 biometric columns per frame aligned to video_time_ms

5. TIMELINE ANALYSIS
   POST /videos/{id}/timeline-analysis → ffprobe/ffmpeg analysis
   Shot detection, cut cadence, audio RMS, ASR/OCR metadata
   Stored as VideoTimelineAnalysis + segments + feature tracks

6. READOUT COMPUTATION (GET /videos/{id}/readout)
   a. Aggregate all sessions for the video
   b. Bucket trace points per second
   c. Compute per-bucket metrics (mean attention, reward, blink, AU, quality)
   d. Generate scene diagnostic cards
   e. Detect attention change segments
   f. Run 8 diagnostic modules (synchrony, narrative, blink transport, etc.)
   g. Compose 11-score neuro taxonomy via build_neuro_score_taxonomy()
   h. Derive 3 composite rollups
   i. Build product rollups (creator or enterprise tier)
   j. Run reliability engine (100-point score)
   k. Run claim safety validation
   l. Cache result (in-memory, 30s TTL, max 512 entries)

7. ML PREDICTION (POST /predict)
   Video URL → download → per-second features (shot_change, brightness, motion, audio_rms)
   → XGBoost inference → 4 predicted targets → enrichment (velocity, valence, arousal, novelty)
   Backends: ml_pipeline_artifact | heuristic_fallback_*

8. OPTIMIZATION (offline)
   Readout → optimizer engine → edit suggestions with predicted engagement deltas
   (Dead zone cuts, confusion reorders, late peak restructuring)

9. DASHBOARD CONSUMPTION
   API discovery: env var → URL param → localStorage → Railway auto-detection → production default
   Catalog → Video Detail → Multi-trace Chart + Scorecards + Rollups + Export
```

### Database Schema (16 tables)

**Core entities**: `studies`, `videos`, `participants`, `sessions`
**Video structure**: `video_scenes`, `video_cuts`, `video_cta_markers`
**Biometric data**: `trace_points` (~35 biometric columns per row)
**Session data**: `survey_responses`, `session_annotations`, `session_playback_events`, `session_capture_archives`, `session_capture_ingest_events`
**Analysis**: `video_timeline_analyses`, `video_timeline_segments`, `video_feature_tracks`
**Calibration**: `incrementality_experiment_results`
**Observability**: `frontend_diagnostic_events`

### Key API Surface

| Category | Endpoints | Purpose |
|----------|-----------|---------|
| Health | `GET /health` | Health check |
| Videos | `POST/GET/PATCH/DELETE /videos` | Video CRUD + catalog |
| Scene Graph | `GET /videos/{id}/scene-graph`, `GET/PUT /videos/{id}/cta-markers` | Structure metadata |
| Sessions | `POST /sessions`, `POST /sessions/{id}/trace\|survey\|annotations\|telemetry\|captures` | Data ingestion |
| Readout | `GET /videos/{id}/readout`, `/readout/check`, `/readout/reliability`, `/readout/export-package` | Core analytics |
| Prediction | `POST /predict`, `GET /predict/{job_id}` | ML prediction |
| Timeline | `POST /videos/{id}/timeline-analysis`, `GET /timeline-features/{asset_id}` | Content analysis |
| Calibration | `POST/GET /calibration/synthetic-lift/*` | Incrementality |
| Observability | `GET /observability/neuro\|capture-archives\|predict-jobs\|frontend-diagnostics/*` | System monitoring |
| Active Learning | `GET /testing-queue` | Uncertainty sampling |

### Legacy Compatibility

- `dopamine`, `dopamine_score`, `dopamineScore` → mapped to `reward_proxy` server-side
- `t_ms` → mapped to `video_time_ms`
- `STRICT_CANONICAL_TRACE_FIELDS=false` (default) keeps aliases accepted
- Strict mode (`=true`) rejects alias-only rows with HTTP 422

### Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `neuro_score_taxonomy_enabled` | true | Gates 11-score taxonomy |
| `product_rollups_enabled` | true | Gates creator/enterprise rollups |
| `blink_transport_enabled` | true | Gates blink transport diagnostics |
| `geox_calibration_enabled` | false | Gates GeoX incrementality calibration |
| `neuro_observability_enabled` | true | Gates observability snapshots |
| `webcam_capture_archive_enabled` | true | Gates capture archive ingestion |
| `strict_canonical_trace_fields` | false | Enforces strict trace field validation |

---

## 5. Current State Assessment

### What is Built and Working

The core loop is fully operational: a participant can complete a consented study session in WatchLab (consent → camera check → passive viewing → annotation → AI survey), data flows through the API into PostgreSQL, the readout engine computes all 11 neuro scores with 3 composite rollups, and the dashboard renders interactive analytics with synchronized video-chart playback.

**Production-ready modules** (22 of 23):
- WatchLab study flow, video library, URL resolution, HLS proxy, webcam capture, telemetry, annotation, AI survey
- Biograph API (52+ endpoints), trace extraction (extractor worker)
- Dashboard (catalog, readout, timeline report, predictor, observability)
- Neuro score taxonomy (11 scores + 3 rollups), all 8 diagnostic modules
- Product rollups (creator + enterprise modes)
- Readout Guardian (CI-enforced formula integrity)
- Reliability engine, claim safety, observability & drift tracking
- Shared schema contracts (Zod + Pydantic, CI-validated)
- Database + migrations, Docker orchestration, CI/CD workflows

**Working but partial** (1):
- ML prediction (requires artifact; heuristic fallback functional)
- Edit suggestion optimizer (offline pipeline only, not API-integrated)
- Active learning (queue logic only; manual retraining)

### Architecture Concerns

1. **God files**: `services.py` (5,211 lines) and `main.py` (2,887 lines) are monolithic
2. **Synchronous DB**: SQLAlchemy used synchronously despite FastAPI's async framework
3. **In-memory caching**: Readout cache and predict job queue are in-memory (not shared across workers, lost on restart)
4. **No auth by default**: Bearer token auth is optional, disabled when `API_TOKEN` is unset
5. **Hardcoded production URLs**: Railway URLs embedded in dashboard API auto-discovery
6. **Missing lock files**: No `pnpm-lock.yaml` or `yarn.lock` in apps/
7. **No monorepo orchestrator**: No turborepo/nx/lerna; manual dependency management

### Security Findings

- **Critical**: Auth disabled by default; SSRF potential in video URL resolution; unauthenticated WatchLab routes
- **High**: Unencrypted webcam data at rest (encryption_mode defaults to "none"); root Docker containers; hardcoded DB credentials in docker-compose; no CSP headers
- **Medium**: Verbose error responses in production; no rate limiting; yt-dlp in production dependency chain; webcam frames stored as gzip binary blobs without at-rest encryption

### Measurement Boundaries (documented and enforced)

- `reward_proxy` is a calibrated engagement proxy — NOT a direct dopamine measurement
- Gaze output is a coarse on-screen webcam proxy — NOT precise fixation mapping
- Face/AU/blink traces are model signals with confidence context — NOT definitive emotion truth labels
- All claim-safe descriptions are regex-validated against 6 blocked overclaim categories
- AGENTS.md instructs AI agents to never expose "measured dopamine" language

---

## 6. Positioning & Marketing Copy

### Extracted Copy

- **Primary**: "Consent-first reaction intelligence stack for video studies"
- **WatchLab**: "Build a video library, then run sequential studies with clear one-click handoff between videos"
- **Upload**: "Add study videos once, then run participants through the sequence with one click"
- **Dashboard title**: "AlphaEngine — Readout Dashboard"
- **WatchLab title**: "AlphaEngine — WatchLab"

### Design Principles (from README)

- Privacy-first: Consent gates before any biometric capture
- Scientific honesty: Explicit measurement boundaries, claim safety enforcement
- Passive-first viewing: Biometric capture during natural viewing, annotation after
- Confidence-aware: Every score carries confidence, quality badges, and provenance

### Product Positioning

AlphaEngine sits at the intersection of creative testing and neuroscience-grounded analytics. It is NOT a neuromarketing tool that claims to read minds or measure dopamine. It is a biometric signal intelligence platform that:

1. Captures webcam-based facial signals during consented video viewing
2. Computes a grounded taxonomy of engagement proxies (not emotions or neurochemistry)
3. Produces actionable editorial recommendations with confidence and evidence
4. Separates measured signals from predicted priors explicitly
5. Serves two audiences: Creators (organic reach optimization) and Enterprises (paid lift + brand memory)

### Key Differentiators

- **Consent-first**: Every session begins with explicit consent and camera quality gating
- **Claim-safe**: Regex-enforced language controls prevent overclaiming about what signals mean
- **Transparent provenance**: Every score shows preferred pathway vs fallback proxy vs synthetic fallback
- **Dual-tier product**: Creator mode vs Enterprise mode with appropriate metric surfaces
- **Guardian-protected**: AST-hashed formula integrity prevents silent computation drift
- **Reliability-scored**: 100-point reliability engine quantifies readout confidence

---

## 7. User-Facing Features & UX Flow

### Researcher Flow

1. **Video Library** (`/upload`): Add videos by URL, preview, rehost to GitHub Releases, arrange study sequence
2. **Generate Study Link**: One-click link generation encoding library + sequence parameters
3. **Share Link**: Send study URL to participants

### Participant Flow

1. **Onboarding**: Study introduction and consent gate
2. **Camera Check**: Webcam permission → real-time quality assessment (brightness, blur, face detection) → pass/fail gate
3. **Passive Viewing**: Full video playback with background webcam capture, timeline event collection, quality sampling. Optional engagement dial overlay.
4. **Timeline Annotation**: Post-view timeline scrub with 4 marker types (engaging, confusing, stop-watching, CTA-landed)
5. **AI Survey**: Conversational interview with "Dr. NeuroTrace" (adaptive focus based on viewing patterns) or deterministic questions as fallback
6. **Next Video**: "Start next study" handoff for multi-video sequences
7. **Completion**: Session data uploaded to Biograph API

### Analyst Flow

1. **Catalog** (`/`): Browse analyzed videos, search, sort (newest/oldest/alpha/sessions), delete
2. **Video Dashboard** (`/videos/:id`): Multi-trace chart synchronized with video playback, scene overlays, engagement segments, neuro scorecards, product rollup panels
3. **Timeline Report** (`/videos/:id/timeline-report`): Scene-first timeline analysis with multi-track feature lanes
4. **Predictor** (`/predictor`): Submit URL or upload file → receive predicted attention/engagement/reward traces without live participants
5. **Observability** (`/observability`): Pipeline health monitoring, confidence distributions, drift detection, diagnostic event history
6. **Export**: CSV trace data, JSON readout package, edit suggestions, full export package

### Dashboard Navigation

```
[α AlphaEngine]  Library | Catalog | Predictor | Observability
```

- **Library**: External link to WatchLab upload page (production Railway URL)
- **Catalog**: Video catalog with search and sort (`/`)
- **Predictor**: ML prediction interface (`/predictor`)
- **Observability**: System monitoring (`/observability`)
