"""Validate that a run's reproduce notebook / CLI regenerates matching metrics."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from abrg.reproduce import emit_reproduce_artifacts, emit_reproduce_from_config, write_reproduce_notebook
from abrg.reproduce_kinds import (
    cli_argv_from_config,
    compare_kind_metrics,
    extract_metrics_from_result,
    result_json_name,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_config(run_dir: Path) -> dict:
    cfg_path = run_dir / "reproduce_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"missing {cfg_path}; pass --axis to emit from comparison.json first"
        )
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def validate_via_cli(run_dir: Path, config: dict) -> dict:
    kind = config.get("kind", "ratio")
    repro_dir = run_dir / "nb_repro"
    if repro_dir.exists():
        shutil.rmtree(repro_dir)
    repro_dir.mkdir(parents=True)
    argv = [sys.executable, *cli_argv_from_config(config, repro_dir)]
    print("Running:", " ".join(argv))
    proc = subprocess.run(argv, cwd=REPO_ROOT)
    if proc.returncode != 0:
        return {"ok": False, "error": f"CLI exit {proc.returncode}", "argv": argv}

    result_name = result_json_name(kind)
    actual_data = json.loads((repro_dir / result_name).read_text(encoding="utf-8"))
    actual = extract_metrics_from_result(
        actual_data, kind=kind, profile=config.get("profile", "")
    )
    expected = config.get("expected")
    if expected is None:
        frozen = run_dir / result_name
        expected = extract_metrics_from_result(
            json.loads(frozen.read_text(encoding="utf-8")),
            kind=kind,
            profile=config.get("profile", ""),
        )
    report = compare_kind_metrics(expected, actual, kind=kind, config=config)
    report["mode"] = "cli"
    report["repro_dir"] = str(repro_dir)
    return report


def validate_via_notebook(run_dir: Path) -> dict:
    nb = run_dir / "reproduce.ipynb"
    if not nb.exists():
        return {"ok": False, "error": f"missing {nb}"}
    out_nb = run_dir / "reproduce.executed.ipynb"
    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        "--ExecutePreprocessor.timeout=7200",
        f"--output={out_nb.name}",
        str(nb),
    ]
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=run_dir)
    report_path = run_dir / "nb_validate_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["mode"] = "notebook"
        report["nbconvert_exit"] = proc.returncode
        report["ok"] = bool(report.get("ok")) and proc.returncode == 0
        return report
    return {
        "ok": False,
        "mode": "notebook",
        "error": "nb_validate_report.json not written",
        "nbconvert_exit": proc.returncode,
    }


def _has_frozen_result(run_dir: Path, kind: str) -> bool:
    if kind == "desc_seed":
        cfg = run_dir / "reproduce_config.json"
        if not cfg.exists():
            return False
        return "expected" in json.loads(cfg.read_text(encoding="utf-8"))
    return (run_dir / result_json_name(kind)).exists()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-run an ABRG experiment from reproduce_config / reproduce.ipynb "
        "and check frozen metrics match within tolerance."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to abrg/output/<campaign>/<run_id>/",
    )
    parser.add_argument(
        "--axis",
        type=str,
        default="",
        help="If reproduce_config.json missing, emit artifacts using this axis string",
    )
    parser.add_argument(
        "--mode",
        choices=("cli", "notebook", "both"),
        default="cli",
        help="cli=re-run module from config (default); notebook=nbconvert execute; both=cli then notebook",
    )
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()

    kind = "ratio"
    if (run_dir / "reproduce_config.json").exists():
        kind = json.loads((run_dir / "reproduce_config.json").read_text()).get("kind", "ratio")
    elif (run_dir / "negative_control_results.json").exists():
        kind = "negative_control"
    elif (run_dir / "comparison.json").exists():
        kind = "ratio"

    if not _has_frozen_result(run_dir, kind):
        if kind == "desc_seed":
            print(f"STOP: no expected block in {run_dir / 'reproduce_config.json'}", file=sys.stderr)
        else:
            print(f"STOP: no {result_json_name(kind)} in {run_dir}", file=sys.stderr)
        return 1

    if not (run_dir / "reproduce_config.json").exists():
        if not args.axis:
            print(
                "STOP: missing reproduce_config.json; re-run with --axis '...' "
                "or run abrg.backfill_reproduce",
                file=sys.stderr,
            )
            return 1
        paths = emit_reproduce_artifacts(run_dir, axis=args.axis)
        print("Emitted:", {k: str(v) for k, v in paths.items()})

    config = _load_config(run_dir)
    if not (run_dir / "reproduce.ipynb").exists():
        write_reproduce_notebook(run_dir, config)

    reports: list[dict] = []
    if args.mode in ("cli", "both"):
        reports.append(validate_via_cli(run_dir, config))
    if args.mode in ("notebook", "both"):
        reports.append(validate_via_notebook(run_dir))

    out = run_dir / "validate_reproduce_report.json"
    payload = {"run_dir": str(run_dir), "reports": reports}
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))

    ok = all(r.get("ok") for r in reports)
    print("VALIDATE:", "OK" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
