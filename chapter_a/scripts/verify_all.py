"""Stage 6 — verify MASTER AUCs against artifacts, execute notebooks, diff tables/figures.

Does not re-train. Does not rewrite experiment outputs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from auc_from_artifact import extract_auc, verify_master_rows
from lib import CHAPTER_A, REPO

MASTER = CHAPTER_A / "MASTER_RESULTS.csv"


def verify_master(rows: list[dict]) -> dict:
    return verify_master_rows(rows)


def execute_notebooks() -> tuple[list[str], list[str]]:
    from nbconvert.preprocessors import ExecutePreprocessor
    import nbformat

    ok, bad = [], []
    for p in sorted((CHAPTER_A / "notebooks").glob("*.ipynb")):
        nb = nbformat.read(p.open(), as_version=4)
        ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
        try:
            ep.preprocess(nb, {"metadata": {"path": str(REPO)}})
            ok.append(p.name)
        except Exception as e:
            bad.append(f"{p.name}: {e}")
    return ok, bad


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def diff_outputs(before: dict[str, str]) -> list[str]:
    fails = []
    for rel, old in before.items():
        p = REPO / rel
        if not p.exists():
            fails.append(f"missing after regen: {rel}")
            continue
        new = file_sha(p)
        if new != old:
            fails.append(f"diff: {rel}")
    return fails


def snapshot_outputs() -> dict[str, str]:
    out = {}
    for folder in (CHAPTER_A / "tables", CHAPTER_A / "figures"):
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix in {".csv", ".tex", ".svg"}:
                out[str(p.relative_to(REPO))] = file_sha(p)
    return out


def main():
    os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
    t0 = time.time()
    sys.path.insert(0, str(CHAPTER_A / "scripts"))
    from inventory import build_manifest
    from build_master import build_master
    from make_tables import make_tables
    from make_figures import make_figures
    from make_notebooks import make_notebooks
    from write_docs import write_docs

    man = build_manifest()
    master_rows = build_master()
    make_tables()
    make_figures()
    make_notebooks()
    write_docs(man, master_rows)

    snap = snapshot_outputs()
    # regenerate and diff
    make_tables()
    make_figures()
    diffs = diff_outputs(snap)

    with MASTER.open() as f:
        rows = list(csv.DictReader(f))
    vr = verify_master(rows)

    # Also run the dedicated Chapter A number gate (MASTER + EXTRA).
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from abrg.reproduce_chapter_a_numbers import verify_all_numbers

    numbers_report = verify_all_numbers()
    (CHAPTER_A / "reproduce" / "verify_all_numbers_report.json").write_text(
        json.dumps(numbers_report, indent=2) + "\n", encoding="utf-8"
    )

    nb_ok, nb_bad = execute_notebooks()

    elapsed = time.time() - t0
    lib_versions = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    try:
        import numpy
        import sklearn
        import torch
        import matplotlib
        import pandas

        lib_versions.update(
            {
                "numpy": numpy.__version__,
                "sklearn": sklearn.__version__,
                "torch": torch.__version__,
                "matplotlib": matplotlib.__version__,
                "pandas": pandas.__version__,
            }
        )
    except ImportError as e:
        lib_versions["import_error"] = str(e)

    report = [
        "# Chapter A reproducibility",
        "",
        f"- wall_time_sec: {elapsed:.1f}",
        f"- python: {sys.version.split()[0]}",
        f"- platform: {platform.platform()}",
        f"- machine: {platform.machine()}",
        f"- library_versions: `{json.dumps(lib_versions)}`",
        f"- MASTER rows: {len(rows)}",
        f"- verified (artifact AUC matches MASTER to 6 dp): {len(vr['verified'])}",
        f"- failed: {len(vr['failed'])}",
        f"- untraceable / missing artifact: {len(vr['untraceable'])}",
        f"- notebooks executed: {len(nb_ok)}",
        f"- notebooks failed: {len(nb_bad)}",
        f"- table/figure diffs after regen: {len(diffs)}",
        f"- EXTRA number verify: {numbers_report['extra']['verified']}/{numbers_report['extra']['n']} "
        f"(ok={numbers_report['ok']})",
        "",
        "## Failed AUC reloads",
        "",
    ]
    if vr["failed"]:
        for r in vr["failed"]:
            report.append(
                f"- {r['experiment']} / {r['detector']} / {r['method']} / {r['split']}: {r.get('error')}"
            )
    else:
        report.append("- (none)")
    report += ["", "## Untraceable rows", ""]
    if vr["untraceable"]:
        for r in vr["untraceable"]:
            report.append(f"- {r['experiment']} / {r['detector']} mode={r['mode']} path={r['artifact_path']}")
    else:
        report.append("- (none)")
    report += ["", "## Notebook failures", ""]
    if nb_bad:
        for x in nb_bad:
            report.append(f"- {x}")
    else:
        report.append("- (none)")
    report += ["", "## Regen diffs", ""]
    if diffs:
        for x in diffs:
            report.append(f"- {x}")
    else:
        report.append("- (none)")
    report += [
        "",
        "## Exit",
        "",
        "Non-zero if any AUC failure, notebook failure, or regen diff.",
        "",
    ]
    (CHAPTER_A / "REPRODUCIBILITY.md").write_text("\n".join(report) + "\n")
    (CHAPTER_A / "verify_report.json").write_text(
        json.dumps(
            {
                "n_verified": len(vr["verified"]),
                "n_failed": len(vr["failed"]),
                "n_untraceable": len(vr["untraceable"]),
                "failed": vr["failed"],
                "untraceable": vr["untraceable"],
                "notebooks_ok": nb_ok,
                "notebooks_bad": nb_bad,
                "diffs": diffs,
                "wall_time_sec": elapsed,
                "library_versions": lib_versions,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print("\n".join(report))
    rc = 0 if (
        not vr["failed"]
        and not nb_bad
        and not diffs
        and numbers_report.get("ok")
    ) else 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
