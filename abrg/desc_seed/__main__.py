"""CLI: recompute desc_seed metrics and optionally validate against reproduce_config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from abrg.desc_seed.metrics import recompute_all_metrics
from abrg.desc_seed.validate import validate_run_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = REPO_ROOT / "abrg" / "output" / "desc_seed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=DEFAULT_RUN_DIR,
        help="Path to abrg/output/desc_seed",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write recomputed metrics JSON here",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Compare to reproduce_config.json expected block",
    )
    args = parser.parse_args()

    if args.validate:
        report = validate_run_dir(args.run_dir)
        out_path = args.output or (args.run_dir / "nb_validate_report.json")
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 2

    metrics = recompute_all_metrics(args.run_dir)
    out_path = args.output or (args.run_dir / "scoring_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
