# NeuroTrace Full Repository Audit
**Date:** 2026-03-11 | **Scope:** All files across monorepo | **Findings:** 95

---

## Executive Summary

| Dimension | CRITICAL | HIGH | MEDIUM | LOW | Total |
|-----------|----------|------|--------|-----|-------|
| 🔒 Security | 0 | 4 | 4 | 1 | **9** |
| 🏗️ Architecture | 4 | 7 | 12 | 4 | **27** |
| 🧹 Code Quality | 0 | 3 | 10 | 5 | **18** |
| 📦 Dependencies | 0 | 4 | 8 | 0 | **12** |
| ⚡ Reliability | 1 | 12 | 16 | 0 | **29** |
| **Total** | **5** | **30** | **50** | **10** | **95** |

### Effort Key
- **S** = Small (< 1 hour, isolated change, low risk)
- **M** = Medium (1–4 hours, touches multiple files, moderate risk)
- **L** = Large (4+ hours, architectural change, high coordination)

---

# 🔒 SECURITY (9 findings)

## Small Effort (4)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| S1 | HIGH | **SSRF in HLS proxy** — fetches arbitrary URLs with no private-IP block or domain allowlist | `apps/watchlab/app/api/video/hls-proxy/route.ts:66` | Add `isPrivateIp()` check + allowlist of known CDN domains |
| S2 | MEDIUM | **CORS overly permissive** — `allow_methods=["*"]`, `allow_headers=["*"]` with `credentials=True` | `services/biograph_api/app/main.py:30-37` | Restrict to `GET,POST,PATCH,DELETE,OPTIONS` and explicit headers |
| S3 | MEDIUM | **FastAPI docs exposed in production** — `/docs`, `/redoc`, `/openapi.json` unauthenticated | `services/biograph_api/app/main.py:18,55` | Set `docs_url=None, redoc_url=None` when not in debug mode |
| S4 | MEDIUM | **Postgres port exposed to host** in docker-compose | `infra/docker-compose.yml:12` | Change `ports:` to `expose:` |

## Medium Effort (4)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| S5 | HIGH | **Open proxy in video resolve** — fetches arbitrary URLs when `WATCHLAB_API_TOKEN` not set | `apps/watchlab/app/api/video/resolve/route.ts:366` | Require auth + private IP validation |
| S6 | HIGH | **WatchLab→biograph API calls missing auth** — no `Authorization` header on server-to-server calls | `apps/watchlab/app/api/upload/route.ts` | Add `BIOGRAPH_API_TOKEN` env var, include in all fetch calls |
| S7 | HIGH | **`VITE_API_TOKEN` baked into JS bundle** — visible in browser DevTools | `apps/dashboard/Dockerfile:15-22` | Document as public credential OR implement BFF proxy |
| S8 | MEDIUM | **API destination hijacking** — `?api_base_url` query param redirects bearer token to arbitrary URL | `apps/dashboard/src/api.ts:80` | Validate against allowlist of known domains |

## Low (1)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| S9 | LOW | **yt-dlp URL handling** — WatchLab download route lacks private IP validation (Python backend has it) | `apps/watchlab/app/api/video/download/route.ts:155` | Port Python's `_validate_predict_video_url` to TypeScript |

---

# 🏗️ ARCHITECTURE (27 findings)

## Small Effort (8)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| A1 | CRITICAL | **20 stale `.js` mirror files** diverged from TypeScript sources, confusing imports | `apps/dashboard/src/**/*.js` | Delete all `.js` siblings of `.tsx`/`.ts` files, remove `sync-js-mirrors.mjs` |
| A2 | HIGH | **33 identical `validate_end_after_start`** Pydantic validators copy-pasted | `schemas.py` (20×), `readout_aggregate_metrics.py` (13×) | Create `TimeRangeMixin(BaseModel)` with shared validator |
| A3 | HIGH | **Route-to-route cross-imports** — observability imports from prediction + assets | `routes_observability.py:32-33` | Extract `_predict_stats`, `_github_upload_stats` to `runtime_stats.py` |
| A4 | MEDIUM | **`datetime.utcnow()` deprecated** — 47 occurrences across 8 files | `models.py` (24×), `services.py` (9×), others | Replace with `datetime.now(datetime.UTC)` |
| A5 | MEDIUM | **`Promise<any>` return types** — 3 API functions bypass TypeScript safety | `apps/dashboard/src/api.ts:216,229,252` | Add proper return types from `types.ts` |
| A6 | MEDIUM | **Inconsistent path parameter naming** — `{id}` vs `{video_id}` on same resource | `routes_videos.py` vs `routes_readout.py` | Standardize on `{video_id}` |
| A7 | MEDIUM | **Duplicate `_normalize_au_payload`** in two files | `services.py:522`, `services_ingestion.py:45` | Delete from `services.py`, import from `services_ingestion.py` |
| A8 | LOW | **Duplicate Docker Compose files** with overlapping services | `infra/docker-compose.yml` + `services/biograph_api/docker-compose.yml` | Use single compose file with profiles |

## Medium Effort (11)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| A9 | HIGH | **`HTTPException` in service layer** — 21+ occurrences couple services to web framework | `services.py`, `services_readout.py`, `services_ingestion.py` | Define domain exceptions, map to HTTP in routes/handler |
| A10 | HIGH | **No CI workflows** — 44 backend tests, 7 WatchLab tests, 0 dashboard tests all run manually only | `.github/workflows/` | Add pytest, vitest, jest, `tsc --noEmit` CI jobs |
| A11 | HIGH | **`routes_prediction.py` at 1,425 lines** — mixes HTTP download/yt-dlp/cookie logic with route handlers | `routes_prediction.py` | Extract download engine to `download_service.py` |
| A12 | MEDIUM | **`@neurotrace/common` JS package unused** — declared in workspaces but never imported by any app | `packages/common/package.json` | Wire into dashboard/watchlab OR remove JS version |
| A13 | MEDIUM | **Legacy camelCase query params** — `sessionId`/`session_id` duplication repeated 10+ times | `routes_readout.py:44-61` | Deprecate camelCase, add auto-convert middleware |
| A14 | MEDIUM | **No state management library** — raw `useState`/`useEffect` everywhere, no request dedup/caching | Both frontend apps | Adopt React Query (TanStack Query) |
| A15 | MEDIUM | **No shared UI components** between dashboard (MUI) and WatchLab (custom) | Both apps | Create shared component package or accept divergence |
| A16 | MEDIUM | **No API client abstraction in WatchLab** — raw `fetch` with string concatenation | `apps/watchlab/app/api/upload/route.ts` | Create typed biograph API client |
| A17 | MEDIUM | **Configuration sprawl** — 40+ settings, many JSON-encoded env vars | `config.py` | Consider TOML/YAML config files with env var overrides |
| A18 | MEDIUM | **Hardcoded Railway production URLs** in 3 source files | `services.py:192`, `routes_assets.py:176`, `upload/route.ts:49` | Consolidate into single config setting |
| A19 | LOW | **Sync vs async route handler inconsistency** — most `def`, one `async def` | Various route modules | Document convention, consider standardizing |

## Large Effort (8)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| A20 | CRITICAL | **`services.py` still 5,213 lines** — decomposition started but routes still import from original | `services/biograph_api/app/services.py` | Complete extraction, rewire all route imports, make `services.py` a re-export shim |
| A21 | CRITICAL | **`study-client.tsx` at 4,502 lines** — entire study UX in one component | `apps/watchlab/app/study/[studyId]/study-client.tsx` | Decompose into hooks (`useWebcam`, `useTraceCollection`, `useSessionState`) + components (`VideoPlayer`, `SurveyForm`, `AnnotationMode`) |
| A22 | CRITICAL | **Dashboard has zero unit tests** — 1 snapshot test total | `apps/dashboard/` | Set up vitest, prioritize testing `utils/`, `api.ts`, `schemas/` |
| A23 | HIGH | **`services_readout.py` at 2,572 lines** | `services/biograph_api/app/services_readout.py` | Split into readout computation, export packaging, and timeline modules |
| A24 | HIGH | **`schemas.py` at 2,383 lines** | `services/biograph_api/app/schemas.py` | Split by domain (video schemas, session schemas, readout schemas) |
| A25 | HIGH | **`PredictorPage.tsx` at 1,454 lines** | `apps/dashboard/src/pages/PredictorPage.tsx` | Extract hooks + sub-components |
| A26 | LOW | **`HomePage.tsx` at 859 lines** | `apps/dashboard/src/pages/HomePage.tsx` | Extract sub-sections |
| A27 | LOW | **`VideoTimelineReportPage.tsx` at 804 lines** | `apps/dashboard/src/pages/VideoTimelineReportPage.tsx` | Extract sub-sections |

---

# 🧹 CODE QUALITY (18 findings)

## Small Effort (8)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| Q1 | HIGH | **`_clamp()` duplicated 16 times** across Python modules | 14 files in `app/` | Replace all with `from .readout_metrics import clamp` |
| Q2 | HIGH | **`_mean()` / `_mean_optional()` duplicated 15+ times** | Same 14 files | Consolidate into shared math module |
| Q3 | HIGH | **`services_math.py` extraction incomplete** — identical functions in both `services.py` and `services_math.py` | `services.py` + `services_math.py` | Delete duplicates from `services.py`, import from `services_math.py` |
| Q4 | MEDIUM | **`isHttpUrl()` duplicated 7 times** across frontend | 7 files across dashboard + watchlab | Import from `utils/videoDashboard.ts` or `packages/common` |
| Q5 | MEDIUM | **Reliability score mapping boilerplate** copy-pasted 4 times | `routes_readout.py` (2×), `services.py`, `services_readout.py` | Extract `build_reliability_schema()` helper |
| Q6 | MEDIUM | **Unbounded in-memory caches** — predict jobs, asset IDs grow forever | `routes_prediction.py:94`, `routes_assets.py:44` | Add `maxsize` + TTL-based eviction |
| Q7 | LOW | **Magic numbers in heuristic code** — dozens of unexplained coefficients | `predict_service.py:122-183` | Extract named constants, document source |
| Q8 | LOW | **Inline style duplication** — identical MUI `sx` objects repeated in header nav | `App.tsx:68-131` | Extract to shared style constant |

## Medium Effort (8)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| Q9 | ✅ DONE | **25+ bare `except Exception:` blocks** — many still swallow silently | Various backend files | Narrowed ~15 handlers to specific types (httpx.HTTPError, OSError, SQLAlchemyError, ImportError, etc.) |
| Q10 | MEDIUM | **No React ErrorBoundary** anywhere in either frontend app | Both apps | Add top-level `ErrorBoundary` around `<Routes>` and study client |
| Q11 | ✅ DONE | **Synchronous `urlopen()` blocking worker threads** — 5s to 180s timeouts | `services.py:2542`, `routes_assets.py:77-113` | Replaced last 2 urlopen refs: Dockerfile HEALTHCHECK → httpx, stale test mock → httpx |
| Q12 | ✅ DONE | **N+1 query in catalog reliability report** — 50 videos × ~5 queries each | `routes_readout.py:327-389` | Added 60s response-level cache with thread-safe locking |
| Q13 | MEDIUM | **No fetch timeouts / AbortController** in dashboard API client | `apps/dashboard/src/api.ts` | Add `AbortController` with configurable timeout to `fetchApi` |
| Q14 | ✅ DONE | **Multiple `db.commit()` per request** — partial commit risk on failure | `routes_sessions.py` | Collapsed to single conditional commit in _upsert_predict_catalog_entry |
| Q15 | LOW | **Dual camelCase/snake_case query params** — `resolve_dual_query_param()` repeated 10+ times | `routes_readout.py` | Extract to decorator or middleware |
| Q16 | LOW | **Missing logs on mutation endpoints** — no logging on study/video/session creation | `routes_sessions.py`, `routes_videos.py` | Add structured logging with entity ID + row count |

## Large Effort (2)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| Q17 | LOW | **Global mutable state breaks multi-worker** — `_predict_jobs`, `_predict_stats`, `_video_asset_id_cache` | `routes_prediction.py`, `routes_assets.py` | Migrate to Redis for shared state, or document single-worker assumption |
| Q18 | LOW | **Zero TODO/FIXME markers** despite known tech debt | Entire repo | Add targeted markers to guide future contributors |

---

# 📦 DEPENDENCIES (12 findings)

## Small Effort (5)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| D1 | HIGH | **`@aws-sdk/client-s3` + `@aws-sdk/lib-storage` unused** — adds ~30MB, never imported | `apps/watchlab/package.json` | `npm uninstall @aws-sdk/client-s3 @aws-sdk/lib-storage` |
| D2 | MEDIUM | **`scikit-learn` declared but never imported** | `ml/training/pyproject.toml` | Remove from dependencies |
| D3 | MEDIUM | **Python `requires-python >= 3.9` is EOL** (Oct 2025) | All `pyproject.toml` files | Raise to `>=3.11` |
| D4 | MEDIUM | **React/TypeScript version pinning inconsistency** — caret vs exact across apps | Multiple `package.json` files | Align all to same convention |
| D5 | MEDIUM | **Missing lock files** for 2 Python packages | `ml/inference/optimizer/`, `packages/common/` | Run `uv lock` in each directory |

## Medium Effort (6)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| D6 | HIGH | **Redundant `package-lock.json` files** — root + 3 per-app locks conflict with npm workspaces | Root + `apps/dashboard/` + `apps/watchlab/` + `apps/alpha-engine/` | Choose: single root lock (delete per-app) OR abandon workspaces |
| D7 | HIGH | **Dockerfiles ignore workspace structure** — run independent `npm ci` against local manifests | `apps/dashboard/Dockerfile`, `apps/watchlab/Dockerfile` | Restructure Dockerfiles to use workspace-aware installs |
| D8 | HIGH | **`yt-dlp` has recurring CVEs** — fast security advisory cadence | `services/biograph_api/pyproject.toml` | Pin narrow version range, set up automated update schedule |
| D9 | MEDIUM | **`mlflow` is heavyweight** (~50MB+ with transitive deps) | `ml/training/pyproject.toml` | Switch to `mlflow-skinny` (~5MB) if only local tracking is used |
| D10 | MEDIUM | **`@neurotrace/common` JS package unused** by any frontend app | `packages/common/package.json` | Wire into consuming apps or remove JS version |
| D11 | MEDIUM | **`serve` in production deps** causes full devDependencies in Docker image | `apps/dashboard/package.json` | Use `npm ci --omit=dev` + global `serve`, or switch to nginx |

## Large Effort (1)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| D12 | MEDIUM | **`mediapipe` at risk of abandonment** — Google transitioning to new SDK | `services/extractor_worker/pyproject.toml` | Plan migration path to `mediapipe-genai` or direct TFLite calls |

---

# ⚡ RELIABILITY (29 findings)

## Small Effort (8)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| R1 | HIGH | **No Docker HEALTHCHECK** in any of 4 Dockerfiles | All Dockerfiles | Add `HEALTHCHECK --interval=30s CMD curl -f http://localhost:PORT/health || exit 1` |
| R2 | HIGH | **Health check is shallow** — always returns `{"ok": true}` with no DB check | `routes_health.py` | Add `SELECT 1`, report cache status + dependency health |
| R3 | HIGH | **No DB connection pool configuration** — using SQLAlchemy defaults | `db.py` | Add `pool_size=10`, `max_overflow=20`, `pool_recycle=1800` |
| R4 | HIGH | **`docker-compose depends_on` without health conditions** | `infra/docker-compose.yml` | Add healthcheck to Postgres, use `condition: service_healthy` |
| R5 | MEDIUM | **No startup config validation** — empty `database_url` passes silently | `config.py` | Add `@model_validator` that raises on missing critical settings |
| R6 | MEDIUM | **In-memory predict job store without eviction** | `routes_prediction.py:94` | Add TTL-based cleanup for completed/failed jobs |
| R7 | MEDIUM | **Prediction polling has no maximum timeout** — polls forever if backend stuck | `apps/dashboard/src/api.ts:307-320` | Add max timeout (10 min) + max poll attempts |
| R8 | MEDIUM | **Extractor worker runs as root** in docker-compose | `infra/docker-compose.yml:64-71` | Add non-root user like other services |

## Medium Effort (14)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| R9 | CRITICAL | **Synchronous `urlopen` with 120s timeouts** blocks thread pool, can make entire API unresponsive | `routes_prediction.py`, `routes_assets.py` | Replace with `httpx.AsyncClient` for all external HTTP calls |
| R10 | HIGH | **No circuit breakers** on any external call (YouTube, Vimeo, GitHub, yt-dlp) | Entire backend | Add `tenacity` with circuit-breaker semantics around external calls |
| R11 | HIGH | **No DB connection retry at startup** — crashes immediately if Postgres not ready | `db.py` | Add 5-attempt retry loop with 2s backoff |
| R12 | HIGH | **No trace ingestion idempotency** — client retry = duplicate trace points = corrupted readouts | `routes_sessions.py` | Add `idempotency_key` (hash of session_id + content) |
| R13 | HIGH | **Entire video file read into memory** for GitHub upload — OOM risk | `routes_assets.py` | Use streaming upload with chunked transfer |
| R14 | HIGH | **Inline `alembic upgrade head` at startup** — race condition with multiple replicas | `Dockerfile` CMD | Separate migration init container/job |
| R15 | HIGH | **`async def` with synchronous DB ops** blocks event loop | `routes_sessions.py` (`ingest_trace_jsonl`) | Change to `def` (let FastAPI use threadpool) or use `AsyncSession` |
| R16 | HIGH | **Readout cache thundering herd** — concurrent requests all compute same readout | `readout_cache.py` | Implement single-flight pattern |
| R17 | MEDIUM | **Race condition on participant creation** — no `ON CONFLICT` handling | `services_ingestion.py` | Use `INSERT ... ON CONFLICT DO NOTHING RETURNING` |
| R18 | MEDIUM | **No structured logging (JSON)** — makes log aggregation/search difficult | Entire backend | Configure `structlog` or `python-json-logger` |
| R19 | MEDIUM | **No graceful shutdown handlers** — in-flight background tasks killed on SIGTERM | `main.py` | Add `lifespan` context manager to drain tasks + close pools |
| R20 | MEDIUM | **No AbortController** on any dashboard fetch call — memory leaks on unmount | `apps/dashboard/src/api.ts` | Add `AbortController` support to `fetchApi` |
| R21 | MEDIUM | **Generic error messages** — no `error_code`, no `retryable` flag in responses | Various backend routes | Standardize error envelope with classification fields |
| R22 | MEDIUM | **Readout computation not idempotent** under concurrent writes — partial data included | `services_readout.py` | Use `SELECT ... FOR SHARE` or compute from snapshot |

## Large Effort (7)

| ID | Sev | Finding | Location | Fix |
|----|-----|---------|----------|-----|
| R23 | HIGH | **Non-atomic 6-step upload pipeline** — partial failure leaves inconsistent state | WatchLab `upload/route.ts` | Implement saga pattern or single transactional backend endpoint |
| R24 | MEDIUM | **No Prometheus metrics** or instrumentation | Entire backend | Add `prometheus-fastapi-instrumentator` + custom counters |
| R25 | MEDIUM | **No database backup configuration** in docker-compose | `infra/docker-compose.yml` | Add pg_dump schedule for local dev; verify PITR in production |
| R26 | MEDIUM | **No zero-downtime deployment strategy** | Infrastructure layer | Separate migrations from startup; configure rolling deploys |
| R27 | MEDIUM | **Trace ingestion no durability guarantee** — no durable queue between client and DB | `routes_sessions.py` | Add write-ahead to durable queue (Redis/SQS) before processing |
| R28 | MEDIUM | **No offline handling in dashboard** — no `navigator.onLine` detection or request queuing | `apps/dashboard/src/api.ts` | Add offline detection + retry queue + UI indicator |
| R29 | MEDIUM | **Multiple `db.commit()` per request** — partial commits on failure | `routes_sessions.py` | Refactor to single terminal commit or savepoints |

---

# ✅ POSITIVE FINDINGS (15)

| # | Finding | Location |
|---|---------|----------|
| ✅ | No hardcoded secrets in source code | Entire repo |
| ✅ | No SQL injection vectors (SQLAlchemy ORM throughout) | Backend |
| ✅ | No XSS vectors (`dangerouslySetInnerHTML` not used) | Frontend |
| ✅ | Non-root Docker containers in all production Dockerfiles | All Dockerfiles |
| ✅ | `.env` files properly gitignored | `.gitignore` |
| ✅ | Dependabot configured for automated updates | `.github/dependabot.yml` |
| ✅ | Request ID middleware in place | `main.py` |
| ✅ | 44 backend test files with clean SQLite-backed test client | `tests/` |
| ✅ | WatchLab structured error taxonomy with `retryable` classification | `lib/errors.ts` |
| ✅ | Predict service graceful degradation (heuristic fallback when model unavailable) | `predict_service.py` |
| ✅ | GitHub upload retry with exponential backoff | `routes_assets.py` |
| ✅ | Dashboard multi-candidate API URL resolution with localStorage persistence | `api.ts` |
| ✅ | WatchLab upload retry (3 attempts with backoff) | `study-client.tsx` |
| ✅ | Alembic migrations well-structured (11 versions) | `alembic/versions/` |
| ✅ | Input validation on predict URLs (private IP blocking, hostname blocklist) | `routes_prediction.py` |

---

# 📊 EFFORT BREAKDOWN

| Effort | Security | Architecture | Code Quality | Dependencies | Reliability | **Total** |
|--------|----------|-------------|--------------|-------------|-------------|-----------|
| **Small** | 4 | 8 | 8 | 5 | 8 | **33** |
| **Medium** | 4 | 11 | 8 | 6 | 14 | **43** |
| **Large** | 1 | 8 | 2 | 1 | 7 | **19** |
| **Total** | **9** | **27** | **18** | **12** | **29** | **95** |

### Quick Win Summary (33 Small items)
If all Small-effort items are addressed, you eliminate:
- **1 CRITICAL** (stale JS mirrors)
- **10 HIGH** (SSRF, clamp/mean dedup, healthchecks, pool config, etc.)
- **16 MEDIUM**
- **6 LOW**

### Highest-Impact Sequence
1. **S1** — Fix SSRF (security, small)
2. **R1+R2** — Docker healthcheck + deep health (reliability, small)
3. **A1** — Delete stale JS mirrors (architecture, small)
4. **Q1+Q2+Q3** — Consolidate 31+ duplicated functions (quality, small)
5. **D1** — Remove unused AWS SDK (dependencies, small)
6. **R3+R11** — DB pool config + startup retry (reliability, small+medium)
7. **R9** — Replace urlopen with httpx (reliability, medium)
8. **A20** — Complete services.py decomposition (architecture, large)
9. **A21** — Decompose study-client.tsx (architecture, large)
10. **A10** — Add CI workflows (architecture, medium)
