# Cloud Deploy (Railway)

Project name: **cheerful-flexibility**

This project runs as 4 Railway services:

| Service | Railway name | Domain | Root directory |
|---|---|---|---|
| PostgreSQL | (managed) | — | — |
| Biograph API | biograph-api | api.alpha-engine.ai | `services/biograph_api` |
| WatchLab | poetic-nature | lab.alpha-engine.ai | `apps/watchlab` |
| Dashboard | hearty-optimism | app.alpha-engine.ai | `apps/dashboard` |

Each app/service folder includes a `railway.json` for Dockerfile deploy.

## 1. Create services

1. Push this repo to GitHub.
2. In Railway, create a new project from the GitHub repo.
3. Add a Postgres service.
4. Add three web services from the same repo with these root directories:
   - `neurotrace/services/biograph_api`
   - `neurotrace/apps/watchlab`
   - `neurotrace/apps/dashboard`

## 2. Configure environment variables

### `biograph-api` (REQUIRED)

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | Reference Railway Postgres URL | Startup fails without it |
| `API_TOKEN` | Any secret string | Required when `API_TOKEN_REQUIRED=true` |
| `API_TOKEN_REQUIRED` | `true` | Set `false` only for local dev |
| `CORS_ALLOW_ORIGINS` | `https://lab.alpha-engine.ai,https://app.alpha-engine.ai` | Must include WatchLab + Dashboard |
| `WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE` | `none` | Default is `fernet` which 503s without a key |

### `biograph-api` (VIDEO PIPELINE — CRITICAL)

| Variable | Value | Notes |
|---|---|---|
| `YOUTUBE_COOKIES_NETSCAPE` | Full Netscape cookies.txt content | For age-restricted/auth videos |
| `YTDLP_PROXY` | `socks5://user:pass@gate.decodo.com:10001` | Residential proxy to avoid IP blocks |

### `poetic-nature` / WatchLab (REQUIRED)

| Variable | Value | Notes |
|---|---|---|
| `BIOGRAPH_API_BASE_URL` | `https://api.alpha-engine.ai` | API service URL |
| `GITHUB_TOKEN` | GitHub PAT with repo scope | For video asset uploads |
| `VIDEO_ASSETS_REPO` | `johnvqcapital/neurotrace` | GitHub repo for assets |
| `VIDEO_ASSETS_TAG` | `video-assets` | Release tag for assets |
| `YOUTUBE_COOKIES_NETSCAPE` | Same as biograph-api | Must be set on BOTH services |
| `YTDLP_PROXY` | Same as biograph-api | Must be set on BOTH services |

### `hearty-optimism` / Dashboard

| Variable | Value | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `https://api.alpha-engine.ai` | API service URL |

## 3. Deploy and verify

1. Deploy all services.
2. Confirm API health:
   ```bash
   curl -sf https://api.alpha-engine.ai/health | python3 -m json.tool
   ```
   Verify: `ok: true`, `checks.readout_guardian: "ok"`, `youtube_download.status: "ok"`

3. Test video prediction:
   ```bash
   curl -sf -X POST https://api.alpha-engine.ai/predict \
     -F "video_url=https://www.youtube.com/watch?v=pPHI2zNf_ww"
   ```
   Should return `{"job_id": "...", "status": "pending", ...}`

4. Open WatchLab: `https://lab.alpha-engine.ai/study/demo`
5. Complete consent, run the video, click `Finish`.
6. Open Dashboard: `https://app.alpha-engine.ai`

## Notes

- Migrations run automatically at app startup via `run_migrations_with_lock()` in the FastAPI lifespan handler (NOT in Dockerfile CMD).
- `DATABASE_URL` values like `postgres://...` are normalized automatically to `postgresql+psycopg://...`.
- CORS must include both WatchLab and Dashboard origins.
- The Dockerfile pins `python:3.11.11-slim` and installs Node.js 20 via NodeSource. When upgrading either, regenerate `readout_guardian_baseline.json` and verify the deploy-gate CI job passes.
- `YOUTUBE_COOKIES_NETSCAPE` and `YTDLP_PROXY` must be set on **both** biograph-api and WatchLab — both services run yt-dlp independently.
- The residential proxy can cause `SSL: UNEXPECTED_EOF_WHILE_READING` on long downloads. Both services handle this by retrying without the proxy automatically.
