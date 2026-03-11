"""Command-line interface for biotrace_extractor."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from .extractor import SessionExtractor
from .io_utils import write_jsonl
from .schemas import ExtractorConfig

logger = logging.getLogger("biotrace_extractor")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extract-session",
        description="Extract biometric traces from <session_dir>/frames and events.json",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Session directory containing frames/ and events.json",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output JSONL path",
    )
    parser.add_argument(
        "--baseline-window-ms",
        type=int,
        default=10_000,
        help="Baseline window in milliseconds (default: 10000)",
    )
    parser.add_argument(
        "--blink-threshold",
        type=float,
        default=0.21,
        help="EAR threshold for blink detection (default: 0.21)",
    )
    parser.add_argument(
        "--blink-min-closed-frames",
        type=int,
        default=2,
        help="Consecutive closed frames to emit blink=1 (default: 2)",
    )
    parser.add_argument(
        "--rolling-window-ms",
        type=int,
        default=10_000,
        help="Rolling window for blink/quality summaries (default: 10000)",
    )
    parser.add_argument(
        "--blink-inhibition-threshold",
        type=float,
        default=0.35,
        help="Blink inhibition threshold relative to baseline (default: 0.35)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Log verbosity",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    try:
        extractor = SessionExtractor(
            ExtractorConfig(
                baseline_window_ms=args.baseline_window_ms,
                blink_threshold=args.blink_threshold,
                blink_min_closed_frames=args.blink_min_closed_frames,
                rolling_window_ms=args.rolling_window_ms,
                blink_inhibition_threshold=args.blink_inhibition_threshold,
            )
        )
        rows = extractor.extract(args.input)
        write_jsonl(rows, args.output)
    except Exception as exc:  # pragma: no cover - fatal path
        logger.error("Extraction failed: %s", exc)
        return 1

    logger.info("Extraction complete: %d rows -> %s", len(rows), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
