"""CLI: parse/inventory AndroCT 2017 archives (no graph construction)."""

from __future__ import annotations

import argparse
from pathlib import Path

from abrg.androct.inventory import run_inventory
from abrg.androct.paths import androct_inventory_dir, androct_raw_dir


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help=f"Directory with verified tar.gz (default: {androct_raw_dir()})",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=f"Inventory output dir (default: {androct_inventory_dir()})",
    )
    args = p.parse_args(argv)
    run_inventory(raw_dir=args.raw_dir, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
