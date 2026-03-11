"""Pydantic mirror of the shared session upload schema."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class Viewport(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class BrowserMetadata(BaseModel):
    userAgent: str
    platform: str
    language: str
    viewport: Viewport
    timezone: str
    hardwareConcurrency: int = Field(ge=0)


class EventItem(BaseModel):
    type: Literal[
        "consent_accepted",
        "webcam_granted",
        "webcam_denied",
        "quality_check",
        "playback_started",
        "survey_answered",
        "play",
        "pause",
        "seek_start",
        "seek_end",
        "seek",
        "rewind",
        "mute",
        "unmute",
        "volume_change",
        "fullscreen_enter",
        "fullscreen_exit",
        "visibility_hidden",
        "visibility_visible",
        "window_blur",
        "window_focus",
        "annotation_mode_entered",
        "annotation_mode_skipped",
        "annotation_tag_set",
        "ended",
        "abandonment",
        "session_incomplete",
        "finish_clicked",
        "upload_success",
        "upload_failed",
    ]
    sessionId: UUID
    videoId: str = Field(min_length=1)
    wallTimeMs: int = Field(ge=0)
    clientMonotonicMs: int = Field(ge=0)
    videoTimeMs: int = Field(ge=0)
    details: Optional[Dict[str, Any]] = None


class DialSample(BaseModel):
    id: UUID
    wallTimeMs: int = Field(ge=0)
    videoTimeMs: int = Field(ge=0)
    value: float = Field(ge=0, le=100)


class AnnotationMarker(BaseModel):
    id: UUID
    sessionId: UUID
    videoId: str = Field(min_length=1)
    markerType: Literal[
        "engaging_moment",
        "confusing_moment",
        "stop_watching_moment",
        "cta_landed_moment",
    ]
    videoTimeMs: int = Field(ge=0)
    note: Optional[str] = Field(default=None, max_length=2000)
    createdAt: str


class SurveyResponse(BaseModel):
    questionKey: str = Field(min_length=1)
    responseText: Optional[str] = None
    responseNumber: Optional[float] = None
    responseJson: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_response_shape(self) -> "SurveyResponse":
        if (
            self.responseText is None
            and self.responseNumber is None
            and self.responseJson is None
        ):
            raise ValueError(
                "Survey response must include a number, text, or JSON payload."
            )
        return self


class FrameItem(BaseModel):
    id: UUID
    timestampMs: int = Field(ge=0)
    videoTimeMs: Optional[int] = Field(default=None, ge=0)
    jpegBase64: str = Field(min_length=16)


class FramePointer(BaseModel):
    id: UUID
    timestampMs: int = Field(ge=0)
    videoTimeMs: Optional[int] = Field(default=None, ge=0)
    pointer: str = Field(min_length=1)


class SessionBundle(BaseModel):
    studyId: str = Field(min_length=1)
    videoId: str = Field(min_length=1)
    participantId: UUID
    browserMetadata: BrowserMetadata
    eventTimeline: List[EventItem]
    dialSamples: List[DialSample] = Field(default_factory=list)
    annotations: List[AnnotationMarker] = Field(default_factory=list)
    annotationSkipped: bool = False
    surveyResponses: List[SurveyResponse] = Field(default_factory=list)
    frames: List[FrameItem] = Field(default_factory=list)
    framePointers: List[FramePointer] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_video_capture_payload(self) -> "SessionBundle":
        if len(self.frames) == 0 and len(self.framePointers) == 0:
            raise ValueError("Payload must include frames or frame pointers.")
        return self
