"""Validation helpers for approved training metadata used by readout guardian updates."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

METADATA_SCHEMA_VERSION = "1.0.0"


class ReadoutLearningMetadataError(ValueError):
    """Raised when training metadata is missing required approval gates."""


def _require_dict(payload: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ReadoutLearningMetadataError(f"{field_name} must be an object")
    return payload


def _require_non_empty_string(payload: Dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ReadoutLearningMetadataError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _require_iso_datetime(payload: Dict[str, Any], field_name: str) -> str:
    value = _require_non_empty_string(payload, field_name)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadoutLearningMetadataError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    return value


def load_and_validate_approved_training_metadata(
    metadata_path: str | Path,
) -> Dict[str, Any]:
    path = Path(metadata_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReadoutLearningMetadataError(
            f"training metadata file not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReadoutLearningMetadataError(
            f"training metadata is not valid JSON: {path} ({exc})"
        ) from exc

    if payload.get("schema_version") != METADATA_SCHEMA_VERSION:
        raise ReadoutLearningMetadataError(
            "training metadata schema_version mismatch: "
            f"expected {METADATA_SCHEMA_VERSION}, got {payload.get('schema_version')}"
        )

    training = _require_dict(payload.get("training"), "training")
    run_id = _require_non_empty_string(training, "run_id")
    run_status = _require_non_empty_string(training, "status").lower()
    if run_status not in {"completed", "succeeded"}:
        raise ReadoutLearningMetadataError(
            f"training.status must be completed/succeeded, got {run_status}"
        )
    _require_non_empty_string(training, "pipeline")
    _require_non_empty_string(training, "model_family")

    approval = _require_dict(payload.get("approval"), "approval")
    approval_status = _require_non_empty_string(approval, "status").lower()
    if approval_status != "approved":
        raise ReadoutLearningMetadataError(
            f"approval.status must be approved, got {approval_status}"
        )
    _require_non_empty_string(approval, "approved_by")
    _require_iso_datetime(approval, "approved_at")

    guardian = _require_dict(payload.get("guardian"), "guardian")
    allow_baseline_refresh = guardian.get("allow_baseline_refresh")
    if allow_baseline_refresh is not True:
        raise ReadoutLearningMetadataError(
            "guardian.allow_baseline_refresh must be true"
        )
    target_metrics = guardian.get("target_metrics")
    if not isinstance(target_metrics, list) or not target_metrics:
        raise ReadoutLearningMetadataError(
            "guardian.target_metrics must be a non-empty list"
        )
    required_metrics = {"attention_score", "reward_proxy"}
    if not required_metrics.issubset({str(item) for item in target_metrics}):
        raise ReadoutLearningMetadataError(
            "guardian.target_metrics must include attention_score and reward_proxy"
        )

    return {
        "metadata_path": str(path),
        "run_id": run_id,
        "approved_at": approval["approved_at"],
        "approved_by": approval["approved_by"],
    }
