"""Lightweight circuit breaker for external service calls."""

from __future__ import annotations

import logging
from threading import Lock
from time import monotonic
from typing import Callable, TypeVar

from .domain_exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitOpenError(ServiceUnavailableError):
    """Raised when a circuit breaker is open and calls are being rejected."""
    def __init__(self, service: str) -> None:
        super().__init__(f"Service '{service}' circuit breaker is open — try again later")
        self.service = service


class CircuitBreaker:
    """Simple three-state circuit breaker (closed -> open -> half-open -> closed)."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None  # monotonic timestamp
        self._state: str = "closed"  # "closed" | "open" | "half_open"

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._state == "open"

    def __call__(self, fn: Callable[..., T], *args, **kwargs) -> T:
        with self._lock:
            if self._state == "open":
                if monotonic() - (self._opened_at or 0) >= self.cooldown_seconds:
                    self._state = "half_open"
                    logger.info("Circuit %s -> half_open (testing recovery)", self.name)
                else:
                    raise CircuitOpenError(self.name)
            # Allow call in closed or half_open state

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        else:
            self._record_success()
            return result

    def _record_success(self) -> None:
        with self._lock:
            if self._state == "half_open":
                logger.info("Circuit %s -> closed (recovery succeeded)", self.name)
            self._consecutive_failures = 0
            self._state = "closed"
            self._opened_at = None

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = monotonic()
                logger.warning("Circuit %s -> open (half_open test failed)", self.name)
            elif self._consecutive_failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = monotonic()
                logger.warning(
                    "Circuit %s -> open (threshold %d reached)",
                    self.name, self.failure_threshold,
                )


# ---------------------------------------------------------------------------
# Pre-configured breakers for known external services
# ---------------------------------------------------------------------------
github_breaker = CircuitBreaker("github_api", failure_threshold=5, cooldown_seconds=60)
video_resolve_breaker = CircuitBreaker("video_resolve", failure_threshold=3, cooldown_seconds=30)
