"""Batch-validate reproduce configs for runs marked pending in REPRODUCE_STATUS."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "abrg" / "output"


def pending_runs() -> list[Path]:
    out: list[Path] = []
    for cfg in sorted(OUTPUT_ROOT.rglob("reproduce_config.json")):
        if "nb_repro" in cfg.parts:
            continue
        run_dir = cfg.parent
        vr = run_dir / "validate_reproduce_report.json"
        if not vr.exists():
            out.append(run_dir)
            continue
        payload = json.loads(vr.read_text(encoding="utf-8"))
        if not all(r.get("ok") for r in payload.get("reports", [])):
            out.append(run_dir)
    return out


def main() -> int:
    runs = pending_runs()
    if not runs:
        print("No pending runs.")
        return 0
    print(f"Validating {len(runs)} pending runs …")
    failed: list[str] = []
    for run_dir in runs:
        rel = run_dir.relative_to(OUTPUT_ROOT)
        print(f"\n=== {rel} ===", flush=True)
        proc = subprocess.run(
            [sys.executable, "-m", "abrg.validate_reproduce", "--run-dir", str(run_dir), "--mode", "cli"],
            cwd=REPO_ROOT,
        )
        if proc.returncode != 0:
            failed.append(str(rel))
    subprocess.run([sys.executable, "-m", "abrg.backfill_reproduce"], cwd=REPO_ROOT, check=False)
    if failed:
        print("FAILED:", failed, file=sys.stderr)
        return 2
    print("All pending validates OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
