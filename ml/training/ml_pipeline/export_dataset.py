"""Dataset export CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from .dataset import export_training_dataset


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export per-second training dataset")
    parser.add_argument(
        "--database-url",
        type=str,
        default="postgresql+psycopg://biograph:biograph@localhost:5432/biograph",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    dataset = export_training_dataset(args.database_url, args.output)
    print(f"Exported dataset rows: {len(dataset)} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
