"""Domain exceptions for the biograph_api service layer.

These exceptions decouple business logic from the HTTP transport layer.
Route modules (or a central FastAPI exception handler) map them to HTTP responses.
Service functions should raise these instead of ``fastapi.HTTPException``.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level errors."""


class NotFoundError(DomainError):
    """A requested resource does not exist."""

    def __init__(self, resource: str = "Resource", detail: str | None = None) -> None:
        self.resource = resource
        self.detail = detail or f"{resource} not found"
        super().__init__(self.detail)


class ValidationError(DomainError):
    """A business-rule or input validation constraint was violated (HTTP 400)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class UnprocessableError(DomainError):
    """The payload is syntactically valid but semantically wrong (HTTP 422)."""

    def __init__(self, detail: str | dict) -> None:  # noqa: PYI041
        self.detail = detail
        super().__init__(str(detail))


class PayloadTooLargeError(DomainError):
    """The request body exceeds a configured size/count limit (HTTP 413)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ServiceUnavailableError(DomainError):
    """A required external dependency or configuration is missing (HTTP 503)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
