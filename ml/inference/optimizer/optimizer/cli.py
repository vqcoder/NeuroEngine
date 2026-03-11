"""CLI entrypoint for the edit optimizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import OptimizerConfig, optimize_video_summary
from .io_utils import load_video_summary, save_edit_suggestions


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate edit suggestions from a video summary")
    parser.add_argument("--input", type=Path, required=True, help="Path to video_summary.json")
    parser.add_argument("--output", type=Path, required=True, help="Path to write edit_suggestions.json")
    parser.add_argument(
        "--dead-zone-threshold",
        type=float,
        default=40.0,
        help="Attention threshold for dead-zone detection (0-100)",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    summary = load_video_summary(args.input)
    config = OptimizerConfig(dead_zone_attention_threshold=args.dead_zone_threshold)
    result = optimize_video_summary(summary, config=config)

    save_edit_suggestions(args.output, result)
    print(f"Generated {len(result.suggestions)} suggestions -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
