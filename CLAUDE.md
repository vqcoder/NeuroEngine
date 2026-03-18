# CLAUDE.md — NeuroTrace Operational Knowledge

This file is read by Claude Code at the start of every session. It captures
architecture, configuration, and hard-won operational lessons so that future
sessions don't repeat past mistakes.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Railway project: cheerful-flexibility                  │
│                                                         │
│  biograph-api  (api.alpha-engine.ai)                    │
│    Python 3.11 / FastAPI / PostgreSQL                   │
│    Root: services/biograph_api                          │
│    Handles: predictions, readouts, sessions, captures   │
│                                                         │
│  poetic-nature  (lab.alpha-engine.ai)                   │
│    Node 20 / Next.js — WatchLab                         │
│    Root: apps/watchlab                                  │
│    Handles: study sessions, video library, uploads      │
│                                                         │
│  hearty-optimism  (app.alpha-engine.ai)                 │
│    Node 20 / Vite + React — Dashboard                   │
│    Root: apps/dashboard                                 │
│    Handles: catalog, timeline reports, analyst view     │
│                                                         │
│  PostgreSQL (Railway managed)                           │
└─────────────────────────────────────────────────────────┘
```

---

## Critical Environment Variables

### Video Download Pipeline (biograph-api AND WatchLab)

Both services run yt-dlp to download YouTube videos. These env vars must be
set on **both** Railway services (biograph-api AND poetic-nature):

| Variable | Purpose | Example |
|---|---|---|
| `YOUTUBE_COOKIES_NETSCAPE` | Netscape-format cookies for age-restricted/auth-required YouTube videos. Paste the full cookies.txt content. | `# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\t...` |
| `YTDLP_PROXY` | Residential proxy for yt-dlp. Prevents IP-based blocking by YouTube. | `socks5://user:pass@gate.decodo.com:10001` |

### Video Pipeline — biograph-api only

| Variable | Purpose | Value |
|---|---|---|
| `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE` | Capture archive encryption. Must be `none` unless a Fernet key is configured. Default is `fernet` which will 503 without a key. | `none` |

### Standard config (biograph-api)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string. Startup fails without it. |
| `API_TOKEN` | Required when `API_TOKEN_REQUIRED=true`. |
| `API_TOKEN_REQUIRED` | Set `false` for local dev / CI. |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed origins. Must include dashboard and WatchLab domains. |
| `MODEL_ARTIFACT_PATH` | Path to XGBoost model. Falls back to heuristic predictor if missing. |

### WatchLab (poetic-nature)

| Variable | Purpose |
|---|---|
| `BIOGRAPH_API_BASE_URL` | URL of biograph-api service (e.g., `https://api.alpha-engine.ai`) |
| `GITHUB_TOKEN` | GitHub PAT for uploading video assets to release storage |
| `VIDEO_ASSETS_REPO` | GitHub repo for video asset storage (e.g., `johnvqcapital/neurotrace`) |
| `VIDEO_ASSETS_TAG` | Release tag for video assets (e.g., `video-assets`) |

---

## yt-dlp Requirements (IMPORTANT)

Both WatchLab and biograph-api spawn yt-dlp as a child process. The following
requirements were discovered through production failures and must be maintained:

1. **yt-dlp >= 2025.11.12** — Older versions lack `--remote-components` which
   is needed for YouTube's n-parameter EJS challenge solver.

2. **Node.js >= 20** — YouTube's EJS challenges require a modern JS runtime.
   Debian Bookworm ships Node 18 which is too old. The Dockerfile installs
   Node 20 via NodeSource.

3. **`--js-runtimes node`** — The runtime name is `node`, NOT `nodejs`.
   yt-dlp uses this to find the Node.js binary.

4. **`--remote-components ejs:github`** — Downloads the EJS challenge solver
   from GitHub. Without this, YouTube downloads fail with "no downloadable
   embedded video source."

5. **Proxy retry** — The residential proxy (Decodo) drops long-lived SSL
   streams during full video downloads, causing `SSL: UNEXPECTED_EOF_WHILE_READING`.
   Both services retry WITHOUT the proxy when SSL/connection errors occur.
   The proxy is still tried first because it helps avoid YouTube IP blocks.

### yt-dlp command structure (both services)

```
yt-dlp --no-playlist --format 'best[ext=mp4]/best' \
  --merge-output-format mp4 \
  --js-runtimes node \
  --remote-components ejs:github \
  [--cookies /tmp/yt-cookies.txt]     # if YOUTUBE_COOKIES_NETSCAPE is set
  [--proxy socks5://...]              # if YTDLP_PROXY is set
  <video_url>
```

---

## Readout Guardian

The readout guardian validates that the neuro algorithm code hasn't changed
unexpectedly. It hashes the source code of key functions and compares against
a checked-in baseline.

- **Baseline file**: `services/biograph_api/app/readout_guardian_baseline.json`
- **Uses source-text hashing** (not `ast.dump`) — produces identical hashes
  across Python versions (3.11, 3.14, etc.).
- **Crash-fast at startup** — if the guardian fails, the service refuses to
  start. This is intentional: a service that fails every health check wastes
  120s before Railway kills it.
- **To regenerate baseline after code changes**:
  ```bash
  cd services/biograph_api
  uv run --python 3.11 python -m app.readout_guardian \
    --update-baseline \
    --training-metadata ../../ml/training/approved_runs/mlflow-readout-guardian-2026-03-07.json
  ```

---

## Common Failure Modes & Fixes

### "SSL: UNEXPECTED_EOF_WHILE_READING" during YouTube download
- **Cause**: Residential proxy (Decodo) drops long video download streams.
- **Fix**: Already handled — code retries without `--proxy` on SSL errors.
- **If it persists**: Check if `YTDLP_PROXY` value is correct, or temporarily
  unset it on the affected Railway service.

### "no downloadable embedded video source" for YouTube
- **Cause**: yt-dlp version too old OR Node.js < 20 OR missing `--remote-components`.
- **Fix**: Ensure Dockerfile installs Node 20 via NodeSource, yt-dlp >= 2025.11.12,
  and commands include `--js-runtimes node --remote-components ejs:github`.

### "Capture archive encryption key is required for fernet mode"
- **Cause**: `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE` defaults to `fernet`
  but no key is configured.
- **Fix**: Set `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE=none` on Railway.

### Readout guardian mismatch after code change
- **Cause**: Algorithm source code changed but baseline wasn't regenerated.
- **Fix**: Regenerate baseline (see Readout Guardian section above).
- **Verify**: Run on both Python 3.11 and your local Python to confirm the
  hash is version-independent.

### Config validation crash at startup
- **Cause**: `config.py` raises `ValueError` on missing `DATABASE_URL` or
  `API_TOKEN` (when required). This is intentional — fail-fast, not fail-slow.
- **Fix**: Ensure all required env vars are set on Railway before deploying.

### Biograph forwarding failures on session upload
- **Cause**: Various — encryption keys, batch ingest schema, network issues.
- **Architecture**: Session upload (WatchLab → biograph-api) is **non-fatal**.
  The upload route validates the payload client-side and always returns 200
  to the participant. Biograph sync failures are logged but don't block.
- **Fallback chain**: batch-ingest → legacy multi-step → log warning.

---

## Deployment

- **Migrations**: Run automatically at startup via `run_migrations_with_lock()`
  in the FastAPI lifespan handler. NOT in Dockerfile CMD.
- **Health check**: `GET /health` — checks database, readout guardian, and
  YouTube download readiness. Docker HEALTHCHECK polls this every 30s.
- **CI deploy-gate**: Builds the real Dockerfile, boots against PostgreSQL,
  and verifies `/health` returns 200 with guardian OK.
- **Railway restart policy**: `ON_FAILURE` with 10 retries. Crash-fast startup
  means failures are visible instantly in logs.

---

## Key File Locations

| File | Purpose |
|---|---|
| `services/biograph_api/Dockerfile` | Biograph API container (Python 3.11.11-slim + Node 20 + ffmpeg) |
| `services/biograph_api/app/download_service.py` | All yt-dlp video download logic (extracted from routes_prediction.py) |
| `services/biograph_api/app/readout_guardian.py` | Algorithm integrity validation |
| `services/biograph_api/app/config.py` | Settings with fail-fast validation |
| `services/biograph_api/app/main.py` | FastAPI app with crash-fast startup |
| `apps/watchlab/app/api/video/download/route.ts` | WatchLab video download (yt-dlp + GitHub release upload) |
| `apps/watchlab/app/api/upload/route.ts` | Session upload with non-fatal biograph forwarding |
| `apps/watchlab/lib/videoLibrary.ts` | Default video library + localStorage management |
| `.github/workflows/ci.yml` | CI pipeline: tests, guardian, typecheck, deploy-gate |
| `docs/CLOUD_RAILWAY.md` | Railway deployment guide |

---

## Video Assets

Hosted on GitHub Releases at `johnvqcapital/neurotrace` under the `video-assets` tag.
WatchLab proxies these through `/api/video-assets/[filename]` to avoid CORS issues.

Default video library entries are defined in `apps/watchlab/lib/videoLibrary.ts`.
To add a new default video:
1. Upload the video via the WatchLab Video Library Upload page
2. Add the entry to `DEFAULT_VIDEO_LIBRARY` in `videoLibrary.ts`
3. Use the proxy path format: `/api/video-assets/<filename>.mp4`
