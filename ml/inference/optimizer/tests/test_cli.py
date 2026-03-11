"""CLI-level tests for optimizer."""

from __future__ import annotations

import json
from pathlib import Path

from optimizer.cli import main


def test_cli_writes_edit_suggestions_file(monkeypatch, tmp_path):
    input_path = Path(__file__).resolve().parents[1] / "examples" / "video_summary.json"
    output_path = tmp_path / "edit_suggestions.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "optimize-edits",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    exit_code = main()
    assert exit_code == 0
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["video_id"] == "demo-video-001"
    assert isinstance(payload["suggestions"], list)
