"""Ensure readout config weights stay aligned with executable formula code."""

from __future__ import annotations

from app.readout_guardian import (
    config_fields_used_by_formulas,
    unused_config_weight_fields,
)
from app.readout_metrics import ReadoutMetricConfig


def test_no_unused_weight_fields_in_readout_metric_config() -> None:
    assert unused_config_weight_fields() == []


def test_formula_config_fields_exist_in_dataclass() -> None:
    config = ReadoutMetricConfig()
    valid_fields = set(config.__dataclass_fields__.keys())
    used_fields = set(config_fields_used_by_formulas())

    assert used_fields
    assert used_fields.issubset(valid_fields)
