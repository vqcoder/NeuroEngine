"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import get_settings
from .domain_exceptions import (
    DomainError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    UnprocessableError,
    ValidationError,
)
from .db import wait_for_db
from .http_client import close_async_client, close_sync_client
from .migrate import run_migrations_with_lock
from .readout_guardian import ReadoutGuardianError, enforce_readout_guardian

settings = get_settings()

# Disable interactive docs in production (when auth is required)
_docs_url = "/docs" if not settings.api_token_required else None
_redoc_url = "/redoc" if not settings.api_token_required else None
_openapi_url = "/openapi.json" if not settings.api_token_required else None


# ---------------------------------------------------------------------------
# Lifespan — ensures shared HTTP clients are closed on shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    # Startup: ensure DB is reachable, then run migrations safely
    wait_for_db()
    run_migrations_with_lock()
    # Validate readout guardian at startup — fail-fast logging so operators
    # see the problem immediately in Railway logs rather than waiting for the
    # first /readout request or health check cycle.
    try:
        enforce_readout_guardian()
        logger.info("Readout guardian validated at startup")
    except ReadoutGuardianError as exc:
        logger.error("READOUT GUARDIAN FAILED AT STARTUP: %s", exc)
        raise  # Crash fast — don't start a service that will fail every health check
    yield
    # Shutdown: close shared httpx clients to release connections
    close_sync_client()
    await close_async_client()


app = FastAPI(
    title="biograph_api",
    version="0.1.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    lifespan=_lifespan,
)
cors_origins = settings.cors_origins or ["http://localhost:3000"]
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_rpm}/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Domain exception → HTTP response mapping
# ---------------------------------------------------------------------------
_DOMAIN_STATUS_MAP: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ValidationError: 400,
    UnprocessableError: 422,
    PayloadTooLargeError: 413,
    ServiceUnavailableError: 503,
}


@app.exception_handler(DomainError)
async def _domain_error_handler(request: Request, exc: DomainError):  # noqa: ARG001
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    status = _DOMAIN_STATUS_MAP.get(type(exc), 500)
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse({"detail": detail}, status_code=status)


@app.exception_handler(ReadoutGuardianError)
async def _guardian_error_handler(request: Request, exc: ReadoutGuardianError):  # noqa: ARG001
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    logger.error("ReadoutGuardianError: %s", exc)
    return JSONResponse(
        {"detail": "Readout guardian validation failed. Service temporarily unavailable.", "code": "guardian_mismatch"},
        status_code=503,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=settings.cors_allow_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------
_API_TOKEN = os.getenv("API_TOKEN", "").strip()
_SUPABASE_URL = settings.supabase_url.strip()
_SUPABASE_JWKS_CLIENT = None

if _SUPABASE_URL:
    try:
        from jwt import PyJWKClient  # noqa: PLC0415

        _jwks_url = f"{_SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _SUPABASE_JWKS_CLIENT = PyJWKClient(_jwks_url)
        logger.info("Supabase JWKS client initialised: %s", _jwks_url)
    except Exception:
        logger.warning("Failed to initialise Supabase JWKS client. JWT auth disabled.")

_UNAUTHED_PATHS = {"/health"}
if _docs_url:
    _UNAUTHED_PATHS |= {_docs_url, _redoc_url, _openapi_url}

if not _API_TOKEN and settings.api_token_required:
    logger.warning(
        "API_TOKEN is not set but api_token_required=True. "
        "Set API_TOKEN env var or set API_TOKEN_REQUIRED=false for local dev."
    )


def _verify_supabase_jwt(token: str) -> dict | None:
    """Verify a Supabase ES256 JWT via JWKS and return the payload, or None."""
    if not _SUPABASE_JWKS_CLIENT:
        return None
    try:
        import jwt  # noqa: PLC0415

        signing_key = _SUPABASE_JWKS_CLIENT.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return payload
    except Exception:
        return None


@app.middleware("http")
async def _token_auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in _UNAUTHED_PATHS:
        return await call_next(request)
    if not _API_TOKEN and not _SUPABASE_JWKS_CLIENT:
        if settings.api_token_required:
            from fastapi.responses import JSONResponse  # noqa: PLC0415

            return JSONResponse({"detail": "Server misconfigured: auth token not set"}, status_code=503)
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    token = auth_header[7:]

    # Check static API_TOKEN first (Railway internal calls, backward compat)
    if _API_TOKEN and token == _API_TOKEN:
        return await call_next(request)

    # Check Supabase JWT (ES256 via JWKS)
    jwt_payload = _verify_supabase_jwt(token)
    if jwt_payload is not None:
        request.state.user_id = jwt_payload.get("sub")
        return await call_next(request)

    from fastapi.responses import JSONResponse  # noqa: PLC0415

    return JSONResponse({"detail": "Unauthorized"}, status_code=401)


# ---------------------------------------------------------------------------
# Route modules
# ---------------------------------------------------------------------------
from .routes_health import router as _health_router  # noqa: E402
from .routes_videos import router as _videos_router  # noqa: E402
from .routes_sessions import router as _sessions_router  # noqa: E402
from .routes_readout import router as _readout_router  # noqa: E402
from .routes_assets import router as _assets_router  # noqa: E402
from .routes_prediction import router as _prediction_router  # noqa: E402
from .routes_observability import router as _observability_router  # noqa: E402
from .routes_timeline import router as _timeline_router  # noqa: E402
from .routes_calibration import router as _calibration_router  # noqa: E402
from .routes_analyst import router as _analyst_router  # noqa: E402

app.include_router(_health_router)
app.include_router(_videos_router)
app.include_router(_sessions_router)
app.include_router(_readout_router)
app.include_router(_assets_router)
app.include_router(_prediction_router)
app.include_router(_observability_router)
app.include_router(_timeline_router)
app.include_router(_calibration_router)
app.include_router(_analyst_router)


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
def run() -> None:
    """CLI runner for `biograph-api`."""
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
