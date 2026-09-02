"""Reproduce every Chapter A (§A.5/A.6) reported number from frozen artifacts.

Two layers
----------
1. **Number verify (required, fast):** reload every MASTER_RESULTS.csv row and every
   EXTRA_NUMBERS.csv entry from its artifact path; assert 6-dp agreement.
2. **CLI re-run (optional, slow):** GAE-family runs already have
   ``abrg/output/androct_2017/*/reproduce.ipynb`` validated via
   ``python -m abrg.validate_reproduce``. Module CLIs are listed in
   ``CLI_RERUN_REGISTRY`` for operators who set ``REPRODUCE_RERUN=1``.

Entry points
------------
::

    .venv/bin/python -m abrg.reproduce_chapter_a_numbers emit
    .venv/bin/python -m abrg.reproduce_chapter_a_numbers verify
    jupyter nbconvert --execute chapter_a/reproduce/00_all_numbers.ipynb
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAPTER_A = REPO_ROOT / "chapter_a"
REPRO_ROOT = CHAPTER_A / "reproduce"
MASTER = CHAPTER_A / "MASTER_RESULTS.csv"
EXTRA = CHAPTER_A / "EXTRA_NUMBERS.csv"
SCRIPTS = CHAPTER_A / "scripts"

# Experiment → optional full retrain CLI (operator must have data + time).
CLI_RERUN_REGISTRY: dict[str, dict[str, Any]] = {
    "apigraph": {"cli_module": "abrg.apigraph", "out_flag": "--output-dir"},
    "ladder": {"cli_module": "abrg.ladder", "out_flag": "--out"},
    "ocdev": {"cli_module": "abrg.ocdev", "out_flag": "--out"},
    "devread": {"cli_module": "abrg.devread", "out_flag": "--out"},
    "ocgin": {"cli_module": "abrg.ocgin", "out_flag": None, "note": "hardcoded output root"},
    "ocgtl": {"cli_module": "abrg.ocgtl", "out_flag": "--out"},
    "glocalkd": {"cli_module": "abrg.glocalkd", "out_flag": "--out"},
    "kernels": {"cli_module": "abrg.kernels", "out_flag": "--out"},
    "supgnn": {"cli_module": "abrg.supgnn", "out_flag": "--out"},
    "transitions": {"cli_module": "abrg.transitions", "out_flag": "--output-dir"},
    "invgraph": {"cli_module": "abrg.invgraph", "out_flag": "--output-dir"},
    "selfref": {"cli_module": "abrg.androct.run_e0_selfref", "out_flag": "--output-dir"},
    "selfref_e2": {
        "cli_module": "abrg.androct.run_e2_variance_aware",
        "out_flag": "--output-dir",
    },
    "final_validate": {"cli_module": "abrg.final_validate", "out_flag": "--out"},
    "validation": {"cli_module": "abrg.validate", "out_flag": "--out"},
    "run3": {"cli_module": "abrg.androct.run_gae_run3", "harness": "androct_auc"},
    "run8": {"cli_module": "abrg.androct.run_gae_run8", "harness": "androct_auc"},
}


def _ensure_scripts_path() -> None:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))


def load_master_rows() -> list[dict[str, str]]:
    with MASTER.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_extra_rows() -> list[dict[str, str]]:
    if not EXTRA.exists():
        return []
    with EXTRA.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_nested(data: Any, dotted: str) -> Any:
    cur = data
    for part in dotted.split("."):
        if part.endswith("]") and "[" in part:
            key, idx = part[:-1].split("[")
            if key:
                cur = cur[key]
            cur = cur[int(idx)]
        else:
            cur = cur[part]
    return cur


def verify_extra_row(row: dict[str, str]) -> dict[str, Any]:
    from lib import abs_artifact, load_json

    path = row["artifact_path"]
    p = abs_artifact(path)
    expected = float(row["expected_value"])
    rec: dict[str, Any] = {
        "id": row["id"],
        "section": row.get("section", ""),
        "artifact_path": path,
        "json_path": row.get("json_path", ""),
        "expected": expected,
    }
    if not p.exists():
        rec["ok"] = False
        rec["error"] = "missing artifact"
        return rec
    if p.suffix == ".csv":
        with p.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        match_col = row.get("csv_match_column") or ""
        match_val = row.get("csv_match_value") or ""
        value_col = row.get("csv_value_column") or row.get("json_path") or ""
        hit = None
        for r in rows:
            if match_col and str(r.get(match_col, "")) != match_val:
                continue
            hit = r
            break
        if hit is None and rows and not match_col:
            hit = rows[0]
        if hit is None or value_col not in hit:
            rec["ok"] = False
            rec["error"] = "csv row/column not found"
            return rec
        actual = float(hit[value_col])
    else:
        data = load_json(p)
        try:
            actual = float(get_nested(data, row["json_path"]))
        except (KeyError, TypeError, IndexError, ValueError) as e:
            rec["ok"] = False
            rec["error"] = f"json_path failed: {e}"
            return rec
    rec["actual"] = actual
    rec["ok"] = round(actual, 6) == round(expected, 6)
    if not rec["ok"]:
        rec["error"] = f"mismatch expected={expected} actual={actual}"
    return rec


def verify_all_numbers() -> dict[str, Any]:
    _ensure_scripts_path()
    from auc_from_artifact import verify_master_rows

    master = verify_master_rows(load_master_rows())
    extras = [verify_extra_row(r) for r in load_extra_rows()]
    extra_ok = [e for e in extras if e.get("ok")]
    extra_fail = [e for e in extras if not e.get("ok")]
    report = {
        "master": {
            "n": len(master["verified"]) + len(master["failed"]) + len(master["untraceable"]),
            "verified": len(master["verified"]),
            "failed": len(master["failed"]),
            "untraceable": len(master["untraceable"]),
            "failed_rows": master["failed"],
            "untraceable_rows": master["untraceable"],
        },
        "extra": {
            "n": len(extras),
            "verified": len(extra_ok),
            "failed": len(extra_fail),
            "failed_rows": extra_fail,
        },
        "cli_rerun_registry": CLI_RERUN_REGISTRY,
        "gae_harness_hint": (
            "python -m abrg.batch_validate_reproduce  # GAE-family androct_auc notebooks"
        ),
    }
    report["ok"] = (
        report["master"]["failed"] == 0
        and report["master"]["untraceable"] == 0
        and report["extra"]["failed"] == 0
    )
    return report


def _nb_cell(source: str, cell_type: str = "code") -> dict[str, Any]:
    import uuid

    lines = source if source.endswith("\n") else source + "\n"
    cell: dict[str, Any] = {
        "cell_type": cell_type,
        "metadata": {},
        "source": lines.splitlines(keepends=True),
        "id": uuid.uuid4().hex[:8],
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _write_notebook(path: Path, cells: list[dict[str, Any]]) -> None:
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": cells,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")


def emit_all_notebooks() -> dict[str, Any]:
    """Write chapter_a/reproduce/ tree: index + per-experiment verify notebooks."""
    rows = load_master_rows()
    by_exp: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_exp[r["experiment"]].append(r)

    REPRO_ROOT.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []

    # Master all-numbers notebook
    all_nb = REPRO_ROOT / "00_all_numbers.ipynb"
    _write_notebook(
        all_nb,
        [
            _nb_cell(
                "# Chapter A — reproduce all reported numbers\n\n"
                "Reloads every `MASTER_RESULTS.csv` AUC and every `EXTRA_NUMBERS.csv` "
                "scalar from frozen artifacts (6 decimal places). "
                "Does **not** retrain by default.\n\n"
                "Optional full CLI re-runs: GAE family via "
                "`python -m abrg.validate_reproduce --run-dir …`; "
                "other modules via `CLI_RERUN_REGISTRY` / `REPRODUCE_RERUN=1`.\n",
                "markdown",
            ),
            _nb_cell(
                "from __future__ import annotations\n"
                "import json, sys\n"
                "from pathlib import Path\n"
                "CWD = Path.cwd().resolve()\n"
                "REPO = CWD if (CWD / 'abrg').is_dir() else CWD.parent\n"
                "sys.path.insert(0, str(REPO))\n"
                "from abrg.reproduce_chapter_a_numbers import verify_all_numbers\n"
                "report = verify_all_numbers()\n"
                "out = REPO / 'chapter_a' / 'reproduce' / 'verify_all_numbers_report.json'\n"
                "out.write_text(json.dumps(report, indent=2) + '\\n')\n"
                "print(json.dumps({k: report[k] for k in ('ok','master','extra')}, indent=2))\n"
                "assert report['ok'], 'number verify failed — see verify_all_numbers_report.json'\n"
                "print('ALL CHAPTER A NUMBERS OK')\n"
            ),
        ],
    )
    index_rows.append(
        {
            "experiment": "_ALL_",
            "notebook": "chapter_a/reproduce/00_all_numbers.ipynb",
            "n_master_rows": len(rows),
            "mode": "artifact_verify",
        }
    )

    for exp, erows in sorted(by_exp.items()):
        exp_dir = REPRO_ROOT / "by_experiment" / exp
        exp_dir.mkdir(parents=True, exist_ok=True)
        cfg = {
            "kind": "androct_master_verify",
            "experiment": exp,
            "n_rows": len(erows),
            "cli_rerun": CLI_RERUN_REGISTRY.get(exp),
            "rows": [
                {
                    "detector": r["detector"],
                    "method": r["method"],
                    "representation": r["representation"],
                    "split": r["split"],
                    "auc_floor": r["auc_floor"],
                    "raw_auc": r["raw_auc"],
                    "artifact_path": r["artifact_path"],
                    "is_headline": r.get("is_headline"),
                }
                for r in erows
            ],
        }
        (exp_dir / "reproduce_config.json").write_text(
            json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
        )
        nb_path = exp_dir / "reproduce_numbers.ipynb"
        _write_notebook(
            nb_path,
            [
                _nb_cell(
                    f"# Reproduce numbers: `{exp}`\n\n"
                    f"Verifies {len(erows)} MASTER row(s) for this experiment "
                    "by reloading frozen artifacts.\n",
                    "markdown",
                ),
                _nb_cell(
                    "from __future__ import annotations\n"
                    "import json, sys\n"
                    "from pathlib import Path\n"
                    "CWD = Path.cwd().resolve()\n"
                    "REPO = CWD if (CWD / 'abrg').is_dir() else CWD.parent\n"
                    "sys.path.insert(0, str(REPO))\n"
                    "sys.path.insert(0, str(REPO / 'chapter_a' / 'scripts'))\n"
                    "from auc_from_artifact import extract_auc, close6, as_float\n"
                    f"EXP = {exp!r}\n"
                    "CFG = json.loads((REPO / 'chapter_a' / 'reproduce' / 'by_experiment' / EXP / 'reproduce_config.json').read_text())\n"
                    "failed = []\n"
                    "for r in CFG['rows']:\n"
                    "    row = dict(r)\n"
                    "    row['experiment'] = EXP\n"
                    "    art, mode = extract_auc(row)\n"
                    "    master = as_float(row['auc_floor'])\n"
                    "    if row['detector'] == 'HGB_mean_raw_auc':\n"
                    "        master = as_float(row['raw_auc'])\n"
                    "    ok = art is not None and close6(master, art)\n"
                    "    print(f\"{row['detector']:40s} master={master} art={art} mode={mode} ok={ok}\")\n"
                    "    if not ok:\n"
                    "        failed.append({'detector': row['detector'], 'master': master, 'art': art, 'mode': mode})\n"
                    "assert not failed, failed\n"
                    "print('OK', EXP)\n"
                ),
            ],
        )
        # Also drop a pointer into the androct run dir when it exists
        dir_aliases = {
            "final_validate": "final_validation",
            "ocdev_validate": "ocdev",
        }
        androct_name = dir_aliases.get(exp, exp)
        androct = REPO_ROOT / "abrg" / "output" / "androct_2017" / androct_name
        if androct.is_dir():
            pointer = {
                "chapter_a_numbers_notebook": str(
                    nb_path.relative_to(REPO_ROOT)
                ),
                "chapter_a_numbers_config": str(
                    (exp_dir / "reproduce_config.json").relative_to(REPO_ROOT)
                ),
                "gae_cli_reproduce": (
                    "reproduce.ipynb"
                    if (androct / "reproduce.ipynb").exists()
                    else None
                ),
                "cli_rerun": CLI_RERUN_REGISTRY.get(exp),
            }
            (androct / "CHAPTER_A_REPRODUCE.json").write_text(
                json.dumps(pointer, indent=2) + "\n", encoding="utf-8"
            )
        # self-ref dirs are EXTRA-only; still pointer them
        for self_dir in ("selfref", "selfref_e2"):
            sd = REPO_ROOT / "abrg" / "output" / "androct_2017" / self_dir
            if sd.is_dir() and not (sd / "CHAPTER_A_REPRODUCE.json").exists():
                (sd / "CHAPTER_A_REPRODUCE.json").write_text(
                    json.dumps(
                        {
                            "chapter_a_numbers_notebook": "chapter_a/reproduce/01_extra_numbers.ipynb",
                            "extra_csv": "chapter_a/EXTRA_NUMBERS.csv",
                            "cli_rerun": CLI_RERUN_REGISTRY.get(self_dir),
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
        index_rows.append(
            {
                "experiment": exp,
                "notebook": str(nb_path.relative_to(REPO_ROOT)),
                "n_master_rows": len(erows),
                "mode": "artifact_verify",
                "cli_rerun": CLI_RERUN_REGISTRY.get(exp),
            }
        )

    # EXTRA numbers notebook
    extras = load_extra_rows()
    if extras:
        extra_nb = REPRO_ROOT / "01_extra_numbers.ipynb"
        _write_notebook(
            extra_nb,
            [
                _nb_cell(
                    "# Chapter A — EXTRA numbers (self-ref, D-followups, …)\n\n"
                    "Scalars cited in §A.6 that are not MASTER AUC rows.\n",
                    "markdown",
                ),
                _nb_cell(
                    "from __future__ import annotations\n"
                    "import json, sys\n"
                    "from pathlib import Path\n"
                    "CWD = Path.cwd().resolve()\n"
                    "REPO = CWD if (CWD / 'abrg').is_dir() else CWD.parent\n"
                    "sys.path.insert(0, str(REPO))\n"
                    "from abrg.reproduce_chapter_a_numbers import load_extra_rows, verify_extra_row\n"
                    "failed = []\n"
                    "for r in load_extra_rows():\n"
                    "    rec = verify_extra_row(r)\n"
                    "    print(rec)\n"
                    "    if not rec.get('ok'):\n"
                    "        failed.append(rec)\n"
                    "assert not failed, failed\n"
                    "print('EXTRA OK')\n"
                ),
            ],
        )
        index_rows.append(
            {
                "experiment": "_EXTRA_",
                "notebook": str(extra_nb.relative_to(REPO_ROOT)),
                "n_master_rows": len(extras),
                "mode": "artifact_verify",
            }
        )

    index = {
        "description": (
            "Chapter A number reproduction index. "
            "Primary gate: artifact reload. Secondary: GAE harness / module CLI."
        ),
        "entries": index_rows,
        "how_to": {
            "verify_all": ".venv/bin/python -m abrg.reproduce_chapter_a_numbers verify",
            "emit": ".venv/bin/python -m abrg.reproduce_chapter_a_numbers emit",
            "notebook": "jupyter nbconvert --to notebook --execute chapter_a/reproduce/00_all_numbers.ipynb",
            "gae_cli_rerun": ".venv/bin/python -m abrg.batch_validate_reproduce",
        },
    }
    (REPRO_ROOT / "INDEX.json").write_text(json.dumps(index, indent=2) + "\n")
    lines = [
        "# Chapter A number reproduction",
        "",
        "Every §A.5/A.6 number that lives in `MASTER_RESULTS.csv` or "
        "`EXTRA_NUMBERS.csv` can be re-checked from frozen artifacts.",
        "",
        "## Fast path (required)",
        "",
        "```bash",
        ".venv/bin/python -m abrg.reproduce_chapter_a_numbers verify",
        "# or execute chapter_a/reproduce/00_all_numbers.ipynb",
        "```",
        "",
        "## Per-experiment notebooks",
        "",
        "| experiment | notebook | n rows |",
        "|---|---|---|",
    ]
    for e in index_rows:
        if e["experiment"].startswith("_"):
            continue
        lines.append(
            f"| `{e['experiment']}` | `{e['notebook']}` | {e['n_master_rows']} |"
        )
    lines += [
        "",
        "## Full CLI re-run (optional / expensive)",
        "",
        "- GAE family (`run2`–`run8`, arms, `run6/*`): "
        "`python -m abrg.validate_reproduce --run-dir abrg/output/androct_2017/<run>`",
        "- Other modules: see `CLI_RERUN_REGISTRY` in `abrg/reproduce_chapter_a_numbers.py` "
        "and each experiment's `CHAPTER_A_REPRODUCE.json`.",
        "",
    ]
    (REPRO_ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index


def build_extra_numbers_csv() -> Path:
    """Freeze EXTRA_NUMBERS.csv from known §A.6 non-MASTER artifacts."""
    _ensure_scripts_path()
    from lib import load_json

    rows: list[dict[str, str]] = []

    def add(
        id_: str,
        section: str,
        artifact: str,
        json_path: str,
        *,
        expected: float | None = None,
        **csv_kw: str,
    ) -> None:
        p = REPO_ROOT / artifact
        if not p.exists():
            return
        if expected is None:
            if p.suffix == ".csv":
                return
            expected = float(get_nested(load_json(p), json_path))
        rows.append(
            {
                "id": id_,
                "section": section,
                "artifact_path": artifact,
                "json_path": json_path,
                "expected_value": f"{expected:.10g}",
                "csv_match_column": csv_kw.get("csv_match_column", ""),
                "csv_match_value": csv_kw.get("csv_match_value", ""),
                "csv_value_column": csv_kw.get("csv_value_column", ""),
            }
        )

    # Self-ref E0 / E2 headlines
    add(
        "e2_best_raw",
        "A.6.8",
        "abrg/output/androct_2017/selfref_e2/summary.json",
        "headline.e2_best_raw",
    )
    add(
        "e0_best_raw_from_e2",
        "A.6.8",
        "abrg/output/androct_2017/selfref_e2/summary.json",
        "headline.e0_best_raw",
    )
    add(
        "e2_best_size_matched",
        "A.6.8",
        "abrg/output/androct_2017/selfref_e2/summary.json",
        "headline.e2_best_size_matched",
    )
    add(
        "e0_best_size_matched_from_e2",
        "A.6.8",
        "abrg/output/androct_2017/selfref_e2/summary.json",
        "headline.e0_best_size_matched",
    )
    add(
        "e2_shuffle_mean",
        "A.6.8",
        "abrg/output/androct_2017/selfref_e2/summary.json",
        "shuffle_mean_auc_floor",
    )
    add(
        "e0_ceiling_max",
        "A.6.8",
        "abrg/output/androct_2017/selfref/summary.json",
        "ceiling_max",
    )
    add(
        "e0_ceiling_min",
        "A.6.8",
        "abrg/output/androct_2017/selfref/summary.json",
        "ceiling_min",
    )

    # Cell A / observability
    add(
        "d1_point_auc_floor",
        "A.6.7",
        "results/cell_a_volume_battery.json",
        "d1_reference.point_auc_floor",
    )
    add(
        "cell_a_point_auc_floor",
        "A.6.7",
        "results/cell_a_volume_battery.json",
        "cell_a.point_auc_floor",
    )
    add(
        "obs_androct_effective_universe",
        "A.6.7",
        "results/observability_audit_summary.json",
        "androct_effective_universe",
    )
    add(
        "obs_v2_effective_universe",
        "A.6.7",
        "results/observability_audit_summary.json",
        "v2_effective_universe",
    )
    add(
        "obs_d1_l2_restricted",
        "A.6.7",
        "results/observability_audit_summary.json",
        "d1_l2_restricted",
    )
    add(
        "obs_d2_fisher_floor",
        "A.6.7",
        "results/observability_audit_summary.json",
        "d2_restricted.fisher_floor",
    )

    # GAE / reconstruction headlines (not all in MASTER)
    gae_headlines = [
        ("run2", "auc.auc_floor"),
        ("run3", "auc.auc_floor"),
        ("run3_5", "modes.full.models.hist_gradient_boosting.auc.auc_floor"),
        ("run4", "best_auc_floor"),
        ("run8", "best_scorer.auc_floor"),
        ("arm_a_n1", "auc_by_aggregation.mean.auc.auc_floor"),
        ("arm_b_n8", "auc_by_aggregation.mean.auc.auc_floor"),
    ]
    for run_id, jpath in gae_headlines:
        art = f"abrg/output/androct_2017/{run_id}/comparison.json"
        add(f"gae_{run_id}_auc_floor", "A.6.2", art, jpath)

    # run5 best hidden floor
    run5 = REPO_ROOT / "abrg/output/androct_2017/run5/comparison.json"
    if run5.exists():
        d = load_json(run5)
        best_h, best_floor = None, -1.0
        for h, block in (d.get("by_hidden") or {}).items():
            floor = float(block["auc"]["auc_floor"])
            if floor > best_floor:
                best_floor, best_h = floor, h
        if best_h is not None:
            add(
                "gae_run5_best_auc_floor",
                "A.6.2",
                "abrg/output/androct_2017/run5/comparison.json",
                f"by_hidden.{best_h}.auc.auc_floor",
                expected=best_floor,
            )

    d3 = REPO_ROOT / "results" / "D3_factorial_2x2.csv"
    if d3.exists():
        with d3.open(newline="", encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f)):
                # try common column names
                val_col = next(
                    (
                        c
                        for c in ("auc_floor", "AUC_floor", "auc", "value")
                        if c in r
                    ),
                    None,
                )
                if val_col is None:
                    continue
                key_bits = [
                    r.get(k, "")
                    for k in ("cell", "condition", "reference", "localisation", "name")
                    if r.get(k)
                ]
                mid = "_".join(key_bits) or f"row{i}"
                rows.append(
                    {
                        "id": f"d3_factorial_{mid}",
                        "section": "A.6.7",
                        "artifact_path": "results/D3_factorial_2x2.csv",
                        "json_path": "",
                        "expected_value": f"{float(r[val_col]):.10g}",
                        "csv_match_column": next(
                            (k for k in ("cell", "condition", "name") if k in r),
                            "",
                        ),
                        "csv_match_value": r.get(
                            next(
                                (k for k in ("cell", "condition", "name") if k in r),
                                "",
                            ),
                            "",
                        ),
                        "csv_value_column": val_col,
                    }
                )

    fields = [
        "id",
        "section",
        "artifact_path",
        "json_path",
        "expected_value",
        "csv_match_column",
        "csv_match_value",
        "csv_value_column",
    ]
    with EXTRA.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return EXTRA


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=("emit", "verify", "build-extra", "all"),
        help="emit notebooks | verify numbers | rebuild EXTRA_NUMBERS.csv | all",
    )
    args = p.parse_args(argv)
    if args.command in {"build-extra", "all"}:
        path = build_extra_numbers_csv()
        print(f"wrote {path} ({sum(1 for _ in path.open()) - 1} rows)")
    if args.command in {"emit", "all"}:
        index = emit_all_notebooks()
        print(f"wrote {REPRO_ROOT} ({len(index['entries'])} index entries)")
    if args.command in {"verify", "all"}:
        report = verify_all_numbers()
        out = REPRO_ROOT / "verify_all_numbers_report.json"
        REPRO_ROOT.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            f"master verified={report['master']['verified']} "
            f"failed={report['master']['failed']} "
            f"untraceable={report['master']['untraceable']}"
        )
        print(
            f"extra verified={report['extra']['verified']} "
            f"failed={report['extra']['failed']}"
        )
        print(f"report → {out}")
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
