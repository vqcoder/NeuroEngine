"""Typed models for optimizer input normalization and output suggestions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SceneBoundary:
    """Scene interval in seconds."""

    start_sec: int
    end_sec: int
    label: Optional[str] = None


@dataclass(frozen=True)
class TracePoint:
    """Per-second normalized trace point."""

    t_sec: int
    attention: float
    blink_rate: float
    au4: float
    au6: float
    au12: float
    motion: float
    brightness: float
    reward_proxy: float


@dataclass
class Suggestion:
    """Single edit suggestion candidate."""

    id: str
    rule: str
    label: str
    start_sec: int
    end_sec: int
    scene_label: Optional[str]
    recommendation: str
    rationale: str
    severity: float
    confidence: float
    predicted_delta_engagement: float
    priority: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizationResult:
    """Top-level optimizer output payload."""

    video_id: str
    generated_at: str
    scoring_model: Dict[str, Any]
    baseline_metrics: Dict[str, float]
    engagement_score_before: float
    predicted_total_delta_engagement: float
    engagement_score_after: float
    suggestions: List[Suggestion]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["suggestions"] = [suggestion.to_dict() for suggestion in self.suggestions]
        return payload
