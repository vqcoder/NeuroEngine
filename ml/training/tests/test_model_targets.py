from __future__ import annotations

from ml_pipeline.model import LEGACY_TARGET_COLUMNS, PRIMARY_TARGET_COLUMNS, TARGET_COLUMNS


def test_reward_proxy_is_primary_target() -> None:
    assert PRIMARY_TARGET_COLUMNS[0] == "reward_proxy"
    assert "reward_proxy" in TARGET_COLUMNS


def test_attention_retained_as_legacy_alias_target() -> None:
    assert "attention" in LEGACY_TARGET_COLUMNS
    assert TARGET_COLUMNS[-1] == "attention"
