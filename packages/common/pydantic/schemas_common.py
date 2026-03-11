"""Common base mixins and shared types used across pydantic schema modules."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class TimeRangeMixin(BaseModel):
    """Mixin providing start_ms/end_ms validation (strict: end > start)."""
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @field_validator("end_ms")
    @classmethod
    def validate_end_after_start(cls, value: int, info):
        start = info.data.get("start_ms")
        if start is not None and value <= start:
            raise ValueError("end_ms must be greater than start_ms")
        return value


class OptionalTimeWindowMixin(BaseModel):
    """Mixin validating optional start_ms/end_ms (strict: end > start when both present)."""

    @model_validator(mode="after")
    def validate_window(self):
        start = getattr(self, "start_ms", None)
        end = getattr(self, "end_ms", None)
        if start is not None and end is not None and end <= start:
            raise ValueError("end_ms must be greater than start_ms when window is provided")
        return self
