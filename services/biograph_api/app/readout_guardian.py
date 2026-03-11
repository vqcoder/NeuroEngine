"""Guardrails that lock readout metric behavior to an approved design baseline."""

from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
from dataclasses import asdict, fields
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional

from .readout_learning_metadata import (
    ReadoutLearningMetadataError,
    load_and_validate_approved_training_metadata,
)
from .readout_metrics import (
    ReadoutMetricConfig,
    clamp,
    compute_attention_score,
    compute_attention_velocity,
    compute_quality_weight,
    compute_reward_proxy_decomposition,
    mean,
)

GUARDIAN_SCHEMA_VERSION = "1.0.0"
FLOAT_TOLERANCE = 1e-6
DEFAULT_BASELINE_PATH = Path(__file__).with_name("readout_guardian_baseline.json")


class ReadoutGuardianError(RuntimeError):
    """Raised when readout design verification fails."""


def _stable_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _function_ast_signature(func: Any) -> str:
    source = dedent(inspect.getsource(func))
    # Normalize: strip trailing whitespace per line, drop blank lines.
    # Uses raw source text so the fingerprint is Python-version-independent
    # (unlike ast.dump which changes output across CPython releases).
    lines = [line.rstrip() for line in source.splitlines()]
    normalized = "\n".join(line for line in lines if line.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _formula_functions() -> List[Any]:
    return [
        compute_quality_weight,
        compute_attention_velocity,
        compute_attention_score,
        compute_reward_proxy_decomposition,
    ]


def config_fields_used_by_formulas() -> List[str]:
    used: set[str] = set()
    for func in _formula_functions():
        source = dedent(inspect.getsource(func))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "config"
            ):
                used.add(node.attr)
    return sorted(used)


def unused_config_weight_fields() -> List[str]:
    config = ReadoutMetricConfig()
    defined_weight_fields = {
        field.name for field in fields(config) if field.name.endswith("_weight")
    }
    used_weight_fields = {
        field_name
        for field_name in config_fields_used_by_formulas()
        if field_name.endswith("_weight")
    }
    return sorted(defined_weight_fields - used_weight_fields)


def _validate_no_unused_config_weights() -> None:
    unused_weights = unused_config_weight_fields()
    if unused_weights:
        raise ReadoutGuardianError(
            "Readout metric config contains unused *_weight fields: "
            + ", ".join(unused_weights)
        )


def _config_defaults() -> Dict[str, float | int]:
    config = ReadoutMetricConfig()
    used_fields = set(config_fields_used_by_formulas())
    return {
        field.name: getattr(config, field.name)
        for field in fields(config)
        if field.name in used_fields
    }


def _algorithm_fingerprint_payload() -> Dict[str, Any]:
    return {
        "config_defaults": _config_defaults(),
        "function_ast_signatures": {
            "clamp": _function_ast_signature(clamp),
            "mean": _function_ast_signature(mean),
            "compute_quality_weight": _function_ast_signature(compute_quality_weight),
            "compute_attention_velocity": _function_ast_signature(
                compute_attention_velocity
            ),
            "compute_attention_score": _function_ast_signature(compute_attention_score),
            "compute_reward_proxy_decomposition": _function_ast_signature(
                compute_reward_proxy_decomposition
            ),
        },
    }


def compute_algorithm_fingerprint() -> str:
    payload = _stable_json(_algorithm_fingerprint_payload()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _attention_case_inputs() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "attention_behavioral_focus_high_quality",
            "inputs": {
                "face_presence": 0.94,
                "head_pose_stability": 0.88,
                "gaze_on_screen": 0.82,
                "eye_openness": 0.79,
                "blink_inhibition": 0.32,
                "playback_continuity": 0.98,
                "au12": 0.45,
                "au6": 0.22,
                "au4": 0.04,
                "tracking_confidence": 0.93,
                "quality_score": 0.91,
            },
        },
        {
            "case_id": "attention_behavioral_focus_low_quality",
            "inputs": {
                "face_presence": 0.94,
                "head_pose_stability": 0.88,
                "gaze_on_screen": 0.82,
                "eye_openness": 0.79,
                "blink_inhibition": 0.32,
                "playback_continuity": 0.98,
                "au12": 0.45,
                "au6": 0.22,
                "au4": 0.04,
                "tracking_confidence": 0.28,
                "quality_score": 0.33,
            },
        },
        {
            "case_id": "attention_au_invariance_low_au",
            "inputs": {
                "face_presence": 0.86,
                "head_pose_stability": 0.81,
                "gaze_on_screen": 0.74,
                "eye_openness": 0.72,
                "blink_inhibition": 0.18,
                "playback_continuity": 0.94,
                "au12": 0.04,
                "au6": 0.02,
                "au4": 0.52,
                "tracking_confidence": 0.9,
                "quality_score": 0.9,
            },
        },
        {
            "case_id": "attention_au_invariance_high_au",
            "inputs": {
                "face_presence": 0.86,
                "head_pose_stability": 0.81,
                "gaze_on_screen": 0.74,
                "eye_openness": 0.72,
                "blink_inhibition": 0.18,
                "playback_continuity": 0.94,
                "au12": 0.63,
                "au6": 0.41,
                "au4": 0.03,
                "tracking_confidence": 0.9,
                "quality_score": 0.9,
            },
        },
    ]


def _reward_case_inputs() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "reward_scene_change_off",
            "inputs": {
                "attention_score": 61.0,
                "attention_velocity": 1.8,
                "au12": 0.24,
                "au6": 0.14,
                "au4": 0.08,
                "blink_rate": 0.18,
                "blink_baseline_rate": 0.2,
                "blink_inhibition": 0.1,
                "label_signal": 0.0,
                "dial": None,
                "playback_continuity": 0.96,
                "scene_change_signal": 0.0,
                "telemetry_disruption": 0.04,
                "tracking_confidence": 0.92,
                "quality_score": 0.9,
            },
        },
        {
            "case_id": "reward_scene_change_on",
            "inputs": {
                "attention_score": 61.0,
                "attention_velocity": 1.8,
                "au12": 0.24,
                "au6": 0.14,
                "au4": 0.08,
                "blink_rate": 0.18,
                "blink_baseline_rate": 0.2,
                "blink_inhibition": 0.1,
                "label_signal": 0.0,
                "dial": None,
                "playback_continuity": 0.96,
                "scene_change_signal": 1.0,
                "telemetry_disruption": 0.04,
                "tracking_confidence": 0.92,
                "quality_score": 0.9,
            },
        },
        {
            "case_id": "reward_negative_label_low_dial",
            "inputs": {
                "attention_score": 58.0,
                "attention_velocity": 0.9,
                "au12": 0.18,
                "au6": 0.1,
                "au4": 0.16,
                "blink_rate": 0.3,
                "blink_baseline_rate": 0.2,
                "blink_inhibition": -0.2,
                "label_signal": -0.6,
                "dial": 20.0,
                "playback_continuity": 0.78,
                "scene_change_signal": 0.0,
                "telemetry_disruption": 0.28,
                "tracking_confidence": 0.86,
                "quality_score": 0.8,
            },
        },
        {
            "case_id": "reward_positive_label_high_dial",
            "inputs": {
                "attention_score": 58.0,
                "attention_velocity": 0.9,
                "au12": 0.34,
                "au6": 0.2,
                "au4": 0.04,
                "blink_rate": 0.16,
                "blink_baseline_rate": 0.2,
                "blink_inhibition": 0.35,
                "label_signal": 0.7,
                "dial": 82.0,
                "playback_continuity": 0.95,
                "scene_change_signal": 0.0,
                "telemetry_disruption": 0.05,
                "tracking_confidence": 0.86,
                "quality_score": 0.8,
            },
        },
    ]


def _build_expected_cases() -> Dict[str, List[Dict[str, Any]]]:
    config = ReadoutMetricConfig()

    attention_cases: List[Dict[str, Any]] = []
    for case in _attention_case_inputs():
        expected = compute_attention_score(config=config, **case["inputs"])
        attention_cases.append(
            {
                "case_id": case["case_id"],
                "inputs": case["inputs"],
                "expected": expected,
            }
        )

    reward_cases: List[Dict[str, Any]] = []
    for case in _reward_case_inputs():
        expected = asdict(
            compute_reward_proxy_decomposition(config=config, **case["inputs"])
        )
        reward_cases.append(
            {
                "case_id": case["case_id"],
                "inputs": case["inputs"],
                "expected": expected,
            }
        )

    return {
        "attention_cases": attention_cases,
        "reward_cases": reward_cases,
    }


def build_guardian_baseline(learning_run_id: str) -> Dict[str, Any]:
    run_id = learning_run_id.strip()
    if not run_id:
        raise ValueError("learning_run_id must be a non-empty string")

    return {
        "schema_version": GUARDIAN_SCHEMA_VERSION,
        "algorithm_fingerprint": compute_algorithm_fingerprint(),
        "learning_approval": {
            "run_id": run_id,
        },
        **_build_expected_cases(),
    }


def _resolve_baseline_path(
    baseline_path: Optional[str | Path] = None,
) -> Path:
    if baseline_path is not None:
        return Path(baseline_path)
    env_path = os.getenv("READOUT_GUARDIAN_BASELINE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_BASELINE_PATH


def load_guardian_baseline(baseline_path: Optional[str | Path] = None) -> Dict[str, Any]:
    resolved_path = _resolve_baseline_path(baseline_path)
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReadoutGuardianError(
            f"Readout guardian baseline file not found: {resolved_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReadoutGuardianError(
            f"Readout guardian baseline file is invalid JSON: {resolved_path} ({exc})"
        ) from exc

    if payload.get("schema_version") != GUARDIAN_SCHEMA_VERSION:
        raise ReadoutGuardianError(
            "Readout guardian baseline schema_version mismatch: "
            f"expected {GUARDIAN_SCHEMA_VERSION}, got {payload.get('schema_version')}"
        )
    return payload


def _float_close(left: float, right: float, tolerance: float = FLOAT_TOLERANCE) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def _validate_design_invariants(config: ReadoutMetricConfig) -> None:
    attention_low_au = compute_attention_score(
        face_presence=0.9,
        head_pose_stability=0.84,
        gaze_on_screen=0.76,
        eye_openness=0.74,
        blink_inhibition=0.24,
        playback_continuity=0.95,
        au12=0.03,
        au6=0.02,
        au4=0.51,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )
    attention_high_au = compute_attention_score(
        face_presence=0.9,
        head_pose_stability=0.84,
        gaze_on_screen=0.76,
        eye_openness=0.74,
        blink_inhibition=0.24,
        playback_continuity=0.95,
        au12=0.61,
        au6=0.39,
        au4=0.03,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )
    if not _float_close(attention_low_au, attention_high_au):
        raise ReadoutGuardianError(
            "Design invariant failed: attention score changed with AU-only perturbation."
        )

    attention_low_quality = compute_attention_score(
        face_presence=0.95,
        head_pose_stability=0.9,
        gaze_on_screen=0.82,
        eye_openness=0.81,
        blink_inhibition=0.2,
        playback_continuity=1.0,
        au12=0.4,
        au6=0.2,
        au4=0.1,
        tracking_confidence=0.25,
        quality_score=0.3,
        config=config,
    )
    attention_high_quality = compute_attention_score(
        face_presence=0.95,
        head_pose_stability=0.9,
        gaze_on_screen=0.82,
        eye_openness=0.81,
        blink_inhibition=0.2,
        playback_continuity=1.0,
        au12=0.4,
        au6=0.2,
        au4=0.1,
        tracking_confidence=0.95,
        quality_score=0.95,
        config=config,
    )
    if attention_high_quality <= attention_low_quality:
        raise ReadoutGuardianError(
            "Design invariant failed: higher quality/confidence did not increase attention score."
        )

    reward_scene_base = compute_reward_proxy_decomposition(
        attention_score=59.0,
        attention_velocity=1.4,
        au12=0.22,
        au6=0.12,
        au4=0.07,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.08,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.97,
        scene_change_signal=0.0,
        telemetry_disruption=0.03,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )
    reward_scene_changed = compute_reward_proxy_decomposition(
        attention_score=59.0,
        attention_velocity=1.4,
        au12=0.22,
        au6=0.12,
        au4=0.07,
        blink_rate=0.18,
        blink_baseline_rate=0.2,
        blink_inhibition=0.08,
        label_signal=0.0,
        dial=None,
        playback_continuity=0.97,
        scene_change_signal=1.0,
        telemetry_disruption=0.03,
        tracking_confidence=0.9,
        quality_score=0.9,
        config=config,
    )
    if reward_scene_changed.novelty_proxy <= reward_scene_base.novelty_proxy:
        raise ReadoutGuardianError(
            "Design invariant failed: scene-change signal did not raise novelty proxy."
        )

    reward_negative = compute_reward_proxy_decomposition(
        attention_score=56.0,
        attention_velocity=1.2,
        au12=0.16,
        au6=0.09,
        au4=0.17,
        blink_rate=0.31,
        blink_baseline_rate=0.2,
        blink_inhibition=-0.25,
        label_signal=-0.7,
        dial=18.0,
        playback_continuity=0.74,
        scene_change_signal=0.0,
        telemetry_disruption=0.3,
        tracking_confidence=0.88,
        quality_score=0.83,
        config=config,
    )
    reward_positive = compute_reward_proxy_decomposition(
        attention_score=56.0,
        attention_velocity=1.2,
        au12=0.38,
        au6=0.24,
        au4=0.03,
        blink_rate=0.14,
        blink_baseline_rate=0.2,
        blink_inhibition=0.4,
        label_signal=0.7,
        dial=88.0,
        playback_continuity=0.95,
        scene_change_signal=0.0,
        telemetry_disruption=0.04,
        tracking_confidence=0.88,
        quality_score=0.83,
        config=config,
    )
    if reward_positive.reward_proxy <= reward_negative.reward_proxy:
        raise ReadoutGuardianError(
            "Design invariant failed: positive reward signals did not increase reward proxy."
        )


def validate_readout_guardian(
    *,
    baseline: Optional[Dict[str, Any]] = None,
    baseline_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    payload = baseline if baseline is not None else load_guardian_baseline(baseline_path)
    _validate_no_unused_config_weights()
    expected_fingerprint = str(payload.get("algorithm_fingerprint", ""))
    current_fingerprint = compute_algorithm_fingerprint()

    if expected_fingerprint != current_fingerprint:
        raise ReadoutGuardianError(
            "Readout guardian fingerprint mismatch. "
            f"expected={expected_fingerprint} current={current_fingerprint}. "
            "Only update baseline from approved learning runs."
        )

    config = ReadoutMetricConfig()
    attention_cases = payload.get("attention_cases")
    reward_cases = payload.get("reward_cases")
    if not isinstance(attention_cases, list) or not isinstance(reward_cases, list):
        raise ReadoutGuardianError(
            "Readout guardian baseline is missing attention_cases or reward_cases."
        )

    for case in attention_cases:
        case_id = str(case.get("case_id", "unknown_attention_case"))
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or expected is None:
            raise ReadoutGuardianError(f"Invalid attention case payload for {case_id}.")
        observed = compute_attention_score(config=config, **inputs)
        if not _float_close(float(observed), float(expected)):
            raise ReadoutGuardianError(
                f"Readout guardian attention case mismatch for {case_id}: "
                f"expected={expected} observed={observed}"
            )

    for case in reward_cases:
        case_id = str(case.get("case_id", "unknown_reward_case"))
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ReadoutGuardianError(f"Invalid reward case payload for {case_id}.")

        observed = asdict(compute_reward_proxy_decomposition(config=config, **inputs))
        for metric_name in (
            "reward_proxy",
            "valence_proxy",
            "arousal_proxy",
            "novelty_proxy",
            "quality_weight",
        ):
            expected_value = expected.get(metric_name)
            observed_value = observed.get(metric_name)
            if expected_value is None or observed_value is None:
                raise ReadoutGuardianError(
                    f"Invalid reward case metric payload for {case_id}:{metric_name}."
                )
            if not _float_close(float(observed_value), float(expected_value)):
                raise ReadoutGuardianError(
                    f"Readout guardian reward case mismatch for {case_id}:{metric_name}: "
                    f"expected={expected_value} observed={observed_value}"
                )

    _validate_design_invariants(config)

    return {
        "schema_version": GUARDIAN_SCHEMA_VERSION,
        "algorithm_fingerprint": current_fingerprint,
        "validated_attention_cases": len(attention_cases),
        "validated_reward_cases": len(reward_cases),
    }


def enforce_readout_guardian() -> Dict[str, Any] | None:
    enabled_flag = os.getenv("READOUT_GUARDIAN_ENABLED", "true").strip().lower()
    if enabled_flag in {"0", "false", "no"}:
        return None
    return validate_readout_guardian()


def write_guardian_baseline(
    learning_run_id: str,
    *,
    learning_metadata: Optional[Dict[str, Any]] = None,
    baseline_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    payload = build_guardian_baseline(learning_run_id)
    if learning_metadata is not None:
        payload["learning_approval"].update(
            {
                "approved_at": learning_metadata["approved_at"],
                "approved_by": learning_metadata["approved_by"],
            }
        )
    resolved_path = _resolve_baseline_path(baseline_path)
    resolved_path.write_text(
        _stable_json(payload) + "\n",
        encoding="utf-8",
    )
    return payload


def write_guardian_baseline_from_training_metadata(
    training_metadata_path: str | Path,
    *,
    baseline_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    metadata = load_and_validate_approved_training_metadata(training_metadata_path)
    return write_guardian_baseline(
        metadata["run_id"],
        learning_metadata=metadata,
        baseline_path=baseline_path,
    )


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or update readout guardian baseline."
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write a new baseline snapshot from approved training metadata.",
    )
    parser.add_argument(
        "--training-metadata",
        type=str,
        default="",
        help="Path to approved training metadata json.",
    )
    parser.add_argument(
        "--baseline-path",
        type=str,
        default="",
        help="Optional override path to baseline json file.",
    )
    parser.add_argument(
        "--print-report",
        action="store_true",
        help="Print validation report json on success.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    baseline_path = args.baseline_path or None

    if args.update_baseline:
        if not args.training_metadata.strip():
            print("error: --training-metadata is required when --update-baseline is used")
            return 2
        try:
            payload = write_guardian_baseline_from_training_metadata(
                args.training_metadata,
                baseline_path=baseline_path,
            )
        except ReadoutLearningMetadataError as exc:
            print(f"readout guardian baseline update blocked: {exc}")
            return 2
        print(
            "readout guardian baseline updated",
            payload["algorithm_fingerprint"],
        )
        return 0

    try:
        report = validate_readout_guardian(baseline_path=baseline_path)
    except ReadoutGuardianError as exc:
        print(f"readout guardian validation failed: {exc}")
        return 1

    if args.print_report:
        print(json.dumps(report, sort_keys=True))
    else:
        print("readout guardian validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
