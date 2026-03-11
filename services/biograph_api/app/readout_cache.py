"""Shared readout cache utilities used across multiple route modules."""

from __future__ import annotations

import os
from threading import Event, Lock
from time import monotonic
from typing import Callable, Optional
from uuid import UUID

from fastapi import HTTPException

from .schemas import ProductRollupMode, ReadoutPayload


READOUT_CACHE_TTL_SECONDS = max(int(os.getenv("READOUT_CACHE_TTL_SECONDS", "30")), 0)
_READOUT_CACHE_MAX_SIZE = 512
_COALESCE_WAIT_TIMEOUT_SECONDS = 60

CacheKey = tuple[str, str, str, bool, int, str, str]

# NOTE(Q17): Module-level mutable state — single-worker only.  If the API is
# scaled to multiple workers (e.g. gunicorn --workers >1), this in-process
# cache will be duplicated per worker.  Migrate to Redis or similar when needed.
_readout_cache_lock = Lock()
_readout_cache: dict[CacheKey, tuple[float, ReadoutPayload]] = {}

# R16: single-flight / coalescing state — prevents thundering herd when many
# threads request the same readout key simultaneously.
_inflight_lock = Lock()
_inflight_events: dict[CacheKey, Event] = {}


def resolve_dual_query_param(
    canonical_value,
    legacy_value,
    canonical_name: str,
    legacy_name: str,
):
    """Return whichever query param the client supplied, preferring *canonical_value*.

    Background (Q15): the API originally used camelCase query parameter names
    (e.g. ``productRollupMode``).  We introduced snake_case aliases as the
    canonical forms and kept the camelCase names for backward-compatibility.
    This helper collapses the two into a single resolved value and raises
    ``HTTPException(400)`` when both are supplied with conflicting values.

    TODO(Q15): Once all clients have migrated to snake_case params, remove the
    legacy aliases and this helper entirely.
    """
    if canonical_value is not None and legacy_value is not None and canonical_value != legacy_value:
        raise HTTPException(
            status_code=400,
            detail=f"Conflicting query params: {canonical_name} and {legacy_name}",
        )
    return canonical_value if canonical_value is not None else legacy_value


def build_readout_cache_key(
    video_id: UUID,
    session_id: Optional[UUID],
    variant_id: Optional[str],
    aggregate: bool,
    window_ms: int,
    product_mode: Optional[ProductRollupMode],
    workspace_tier: Optional[str],
) -> CacheKey:
    return (
        str(video_id),
        str(session_id) if session_id is not None else "",
        variant_id or "",
        aggregate,
        int(window_ms),
        product_mode.value if product_mode is not None else "",
        workspace_tier or "",
    )


def read_readout_cache(
    key: CacheKey,
) -> Optional[ReadoutPayload]:
    if READOUT_CACHE_TTL_SECONDS <= 0:
        return None
    now = monotonic()
    with _readout_cache_lock:
        cached = _readout_cache.get(key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _readout_cache.pop(key, None)
            return None
        return payload.model_copy(deep=True)


def write_readout_cache(
    key: CacheKey,
    payload: ReadoutPayload,
) -> None:
    if READOUT_CACHE_TTL_SECONDS <= 0:
        return
    with _readout_cache_lock:
        _readout_cache[key] = (monotonic() + READOUT_CACHE_TTL_SECONDS, payload.model_copy(deep=True))
        if len(_readout_cache) > _READOUT_CACHE_MAX_SIZE:
            oldest_key = min(_readout_cache.items(), key=lambda item: item[1][0])[0]
            _readout_cache.pop(oldest_key, None)


def invalidate_readout_cache(video_id: Optional[UUID] = None) -> None:
    if READOUT_CACHE_TTL_SECONDS <= 0:
        return
    with _readout_cache_lock:
        if video_id is None:
            _readout_cache.clear()
            return
        video_id_value = str(video_id)
        keys_to_drop = [key for key in _readout_cache if key[0] == video_id_value]
        for key in keys_to_drop:
            _readout_cache.pop(key, None)


# ---------------------------------------------------------------------------
# R16: Single-flight / coalescing pattern
# ---------------------------------------------------------------------------

def coalesce_readout_compute(
    key: CacheKey,
    compute_fn: Callable[[], ReadoutPayload],
) -> ReadoutPayload:
    """Execute *compute_fn* at most once per *key* even under concurrent access.

    The "single-flight" pattern prevents a thundering-herd problem where many
    threads simultaneously trigger the same expensive readout computation.

    Flow:
    1. Check the cache — return immediately on hit.
    2. Check ``_inflight_events`` to see if another thread is already computing
       for *key*.
       a. If yes, wait for that thread's ``Event`` to be set, then read from
          the cache.
       b. If no, register a new ``Event``, run *compute_fn*, write the result
          to cache, signal all waiters, and clean up.
    3. On error the event is removed so waiting threads don't hang forever; the
       exception is re-raised.
    """

    # --- fast path: cache hit ---
    cached = read_readout_cache(key)
    if cached is not None:
        return cached

    # If caching is disabled, just compute directly — no coalescing needed.
    if READOUT_CACHE_TTL_SECONDS <= 0:
        return compute_fn()

    # --- check for an in-flight computation ---
    with _inflight_lock:
        event = _inflight_events.get(key)
        if event is not None:
            # Another thread is already computing this key — wait for it.
            pass  # will wait below, outside the lock
        else:
            # We are the first — register our Event so others can wait on us.
            event = Event()
            _inflight_events[key] = event
            event = None  # sentinel: *we* are the leader

    if event is not None:
        # --- follower path: wait for the leader to finish ---
        signalled = event.wait(timeout=_COALESCE_WAIT_TIMEOUT_SECONDS)
        if not signalled:
            # Timeout — fall through and compute ourselves rather than hanging.
            pass
        else:
            cached = read_readout_cache(key)
            if cached is not None:
                return cached
            # Cache was evicted between signal and our read — fall through and
            # compute ourselves.

        # Compute directly as a fallback (no coalescing registration; other
        # threads that arrive now will start their own Event).
        result = compute_fn()
        write_readout_cache(key, result)
        return result

    # --- leader path: compute, cache, signal ---
    try:
        # Double-check cache after acquiring leader role (another leader may
        # have just finished between our first check and the lock acquisition).
        cached = read_readout_cache(key)
        if cached is not None:
            return cached

        result = compute_fn()
        write_readout_cache(key, result)
        return result
    finally:
        with _inflight_lock:
            finished_event = _inflight_events.pop(key, None)
        if finished_event is not None:
            finished_event.set()
