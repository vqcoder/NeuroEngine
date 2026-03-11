"""Unit tests for scene-level narrative diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from app.readout_metrics import (
    DiagnosticCtaMarker,
    DiagnosticPoint,
    DiagnosticScene,
    DiagnosticSegment,
    build_scene_diagnostic_cards,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scene_diagnostics_fixture.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_scene_diagnostic_classification_covers_all_required_cards() -> None:
    fixture = _load_fixture()

    cards = build_scene_diagnostic_cards(
        scenes=[DiagnosticScene(**item) for item in fixture["scenes"]],
        points=[DiagnosticPoint(**item) for item in fixture["points"]],
        attention_gain_segments=[DiagnosticSegment(**item) for item in fixture["attention_gain_segments"]],
        attention_loss_segments=[DiagnosticSegment(**item) for item in fixture["attention_loss_segments"]],
        confusion_segments=[DiagnosticSegment(**item) for item in fixture["confusion_segments"]],
        cta_markers=[DiagnosticCtaMarker(**item) for item in fixture["cta_markers"]],
        window_ms=fixture["window_ms"],
    )

    cards_by_type = {card.card_type: card for card in cards}
    assert {
        "golden_scene",
        "hook_strength",
        "cta_receptivity",
        "attention_drop_scene",
        "confusion_scene",
        "recovery_scene",
    }.issubset(cards_by_type.keys())

    assert cards_by_type["golden_scene"].scene_id == "scene-2"
    assert cards_by_type["hook_strength"].scene_id == "scene-1"
    assert cards_by_type["cta_receptivity"].cta_id == "cta-main"
    assert cards_by_type["attention_drop_scene"].scene_id == "scene-3"
    assert cards_by_type["confusion_scene"].scene_id == "scene-3"
    assert cards_by_type["recovery_scene"].scene_id == "scene-4"

    assert cards_by_type["hook_strength"].scene_thumbnail_url is not None
    assert cards_by_type["golden_scene"].start_video_time_ms < cards_by_type["golden_scene"].end_video_time_ms
    assert cards_by_type["attention_drop_scene"].primary_metric == "attention_drop_magnitude"
    assert cards_by_type["recovery_scene"].confidence is not None
