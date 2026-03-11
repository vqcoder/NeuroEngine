# Cloud Deploy (Railway)

This project is set up to run as 4 Railway services:

- Postgres
- `biograph_api` (`services/biograph_api`)
- `watchlab` (`apps/watchlab`)
- `dashboard` (`apps/dashboard`)

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

Set the following variables in Railway:

### `biograph_api`

- `DATABASE_URL`: reference the Postgres connection URL from Railway.
- `CORS_ALLOW_ORIGINS`: comma-separated origins, for example:
  - `https://watchlab-production.up.railway.app,https://dashboard-production.up.railway.app`
- `API_HOST`: `0.0.0.0` (optional, default already set)
- `API_PORT`: `8000` (optional, Railway provides `PORT` automatically)

### `watchlab`

- `BIOGRAPH_API_BASE_URL`: public URL of `biograph_api` service.
- `DASHBOARD_BASE_URL`: public URL of `dashboard` service.
- `DEFAULT_STUDY_VIDEO_URL`: `/sample.mp4`

### `dashboard`

- `VITE_API_BASE_URL`: public URL of `biograph_api` service.

## 3. Deploy and verify

1. Deploy all services.
2. Confirm API health:
   - `GET https://<biograph_api_domain>/health` returns `{"ok": true}`.
3. Open watchlab:
   - `https://<watchlab_domain>/study/demo`
4. Complete consent, run the video, and click `Finish`.
5. Open dashboard via link shown by watchlab upload result, or:
   - `https://<dashboard_domain>/videos/<video_id>`

## Notes

- The API container runs migrations on startup (`alembic upgrade head`).
- `DATABASE_URL` values such as `postgres://...` are normalized automatically.
- CORS must include your deployed dashboard origin.
