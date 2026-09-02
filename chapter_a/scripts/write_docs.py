"""Stage 7–8 docs: README, GAPS, environment pins from reproduce_config.json files."""
from __future__ import annotations

import csv
import json
import platform
import sys
from collections import defaultdict
from pathlib import Path

from lib import ANDROCT, CHAPTER_A, REPO


def collect_library_versions() -> tuple[dict, list[str]]:
    found = defaultdict(set)
    missing = []
    disagreements = []
    for p in ANDROCT.rglob("reproduce_config.json"):
        js = json.loads(p.read_text())
        lib = js.get("library_versions") or js.get("libraries") or {}
        py = js.get("python")
        if py:
            lib = dict(lib)
            lib.setdefault("python", py)
        for k in ("numpy", "torch"):
            if k in js and k not in lib:
                lib[k] = js[k]
        if not lib:
            missing.append(str(p.relative_to(REPO)))
            continue
        for k, v in lib.items():
            found[k].add(str(v))
    pins = {}
    for k, vs in sorted(found.items()):
        if len(vs) > 1:
            disagreements.append(f"{k}: " + " | ".join(sorted(vs)))
            pins[k] = "DISAGREEMENT: " + " | ".join(sorted(vs))
        else:
            pins[k] = next(iter(vs))
    return pins, missing, disagreements


def write_environment():
    pins, missing, disagreements = collect_library_versions()
    req_lines = []
    yml_deps = ["python=" + pins.get("python", sys.version.split()[0])]
    for k, v in pins.items():
        if k in {"python", "platform", "embedding_impl"}:
            continue
        if v.startswith("DISAGREEMENT") or v.startswith("unavailable"):
            req_lines.append(f"# {k}: {v}")
            continue
        pkg = {"scikit-learn": "scikit-learn", "grakel": "grakel"}.get(k, k)
        req_lines.append(f"{pkg}=={v}")
        yml_deps.append(f"{pkg}=={v}")
    (CHAPTER_A / "requirements.txt").write_text("\n".join(req_lines) + "\n")
    yml = [
        "name: chapter_a",
        "channels:",
        "  - conda-forge",
        "dependencies:",
    ]
    for d in yml_deps:
        yml.append(f"  - {d}")
    yml.append("  - pip")
    yml.append("  - pip:")
    yml.append("    - -r requirements.txt")
    (CHAPTER_A / "environment.yml").write_text("\n".join(yml) + "\n")
    return pins, missing, disagreements


def write_readme():
    text = """# Chapter A — AndroCT 2017 reconstruction / one-class / supervision audit

This directory is a **read-only consolidation** of `abrg/output/androct_2017/`.
It does not re-run experiments and does not modify run outputs.

## Claims ↔ tables / figures

| Claim | Table / figure | MASTER row(s) |
|---|---|---|
| Eligible corpus n, mapped rate, medians | T1_corpus | (corpus_cache, not an AUC row) |
| Trivial floors across T22 / API-1000 / invocation | T2_floors, F6_granularity | method=`trivial_floor` |
| Seven families trained vs untrained vs size floor | T3_method_sweep, F2_trained_vs_untrained | family detectors |
| Rung 1 / rung 2 pooled OOF / random-group / rung 3 | T4_supervision_ladder, F1_ladder | ladder HGB; OCPool |
| M1/M2/M3 and WL ablations | T5_message_passing, F5_message_passing | supgnn; WL_* |
| D0–D5 one-class and supervised + raw control | T6_deviation_readout | ocdev/devread |
| TPR at FPR 0.001/0.01/0.05/0.10, wild precision | T7_operating_points, F3_roc_headlines | check2_operating |
| D1 per-node ablation | F4_d1_node_ablation | check3_d1_volume |
| What each headline survived | T8_validation | bias / nested / holdout / shuffle |
| Headline set | MASTER_RESULTS.csv `is_headline=True` | HEADLINE_JUSTIFICATION.txt |

## Reproduce (no experiment re-run)

```bash
.venv/bin/python chapter_a/scripts/verify_all.py
```

This rebuilds tables/figures/notebooks from saved artifacts, reloads every MASTER
AUC from its artifact, executes notebooks headlessly, and diffs regenerated
tables/figures against the copies under `chapter_a/`.

Wall time is recorded in `REPRODUCIBILITY.md`.

## Layout

```
chapter_a/
  MANIFEST.csv
  MASTER_RESULTS.csv
  tables/  T1–T8 .csv and .tex
  figures/ F1–F6 .pdf and .svg
  notebooks/ 01–06
  scripts/
  REPRODUCIBILITY.md
  GAPS.md
  environment.yml
  requirements.txt
```
"""
    (CHAPTER_A / "README.md").write_text(text)


def write_gaps(manifest_rows: list[dict], master_rows: list[dict], env_missing: list[str], env_disagree: list[str]):
    no_repro = [
        r for r in manifest_rows if str(r["has_SUMMARY"]) in {"True", "true"} and str(r["has_reproduce_md"]) in {"False", "false", ""}
    ]
    lines = [
        "# Chapter A gaps",
        "",
        "Register of what is not independently re-executed or not fully version-pinned.",
        "No numbers were regenerated to close a gap.",
        "",
        "## 16 experiment dirs with SUMMARY.md and no reproduce.md",
        "",
    ]
    for r in no_repro:
        trace = "traceable via MASTER artifact_path / JSON" if r["status"] not in {"aborted"} else "Split-B aborted; no checkpoints"
        lines.append(f"- `{r['experiment_dir']}` status={r['status']} — {trace}. {r.get('notes','')}")
    lines += [
        "",
        f"Count: {len(no_repro)}",
        "",
        "## Aborted / abandoned runs",
        "",
        "- `ocgtl` Split-B aborted; no checkpoints.",
        "- `glocalkd` nested bootstrap abandoned at B=20.",
        "- `invgraph` V2 complete_but_artifact (99.99% malware edge-drop).",
        "",
        "## reproduce_config.json missing library versions",
        "",
    ]
    if env_missing:
        for p in env_missing:
            lines.append(f"- `{p}`")
    else:
        lines.append("- (none)")
    lines += ["", "## Library version disagreements across runs", ""]
    if env_disagree:
        for d in env_disagree:
            lines.append(f"- {d}")
    else:
        lines.append("- (none)")
    untrace = [r for r in master_rows if r.get("trace_flag")]
    lines += ["", "## MASTER rows with missing / unresolvable artifact_path", ""]
    if untrace:
        for r in untrace:
            lines.append(f"- {r['experiment']} / {r['detector']} flag={r['trace_flag']} path={r['artifact_path']}")
    else:
        lines.append("- (none at inventory time; verify_all.py may add catalog-only rows)")
    lines += [
        "",
        "## Figures / tables whose source artifact is missing",
        "",
        "- Generated scripts fail rather than invent numbers. See REPRODUCIBILITY.md after verify_all.",
        "",
        "## GPU nondeterminism vs headlines",
        "",
        "- Headline rows (D1 centroid, OCPool raw/R2, S1 nested mean, D3 HGB, HGB full, mapped floor,",
        "  rung-2 pooled OOF, random-group control, D1 benign-holdout centroid) are sklearn/numpy",
        "  scores or stored JSON scalars. They do not depend on GPU nondeterminism given the artifacts.",
        "- T3 GNN families (OCGIN, GLocalKD, OCGTL, GAE recon) used torch; trained-vs-untrained means",
        "  are catalogued from saved JSONs and were not re-trained here.",
        "",
        "## AUC verification mode",
        "",
        "- `verify_all.py` reloads the stored `auc_floor` (or documented bootstrap mean) from each row's",
        "  JSON artifact and asserts 6 decimal-place agreement with MASTER_RESULTS.csv.",
        "- Per-app score vectors are not stored in most detector JSONs (`score_distributions` are",
        "  quantiles only). Independent `roc_auc_score` from raw scores was therefore not possible",
        "  for those rows without re-inferring models (forbidden here).",
        "",
        "## Chapter A toolchain not in experiment reproduce_config.json",
        "",
        "- matplotlib, pandas, nbformat/nbconvert used to build tables/figures/notebooks are recorded",
        "  in REPRODUCIBILITY.md at verify time; they are not pinned in experiment reproduce_config files.",
        "- kernels `reproduce_config.json` records karateclub and gensim as `unavailable_on_cpython_3.14`.",
        "",
    ]
    (CHAPTER_A / "GAPS.md").write_text("\n".join(lines) + "\n")


def write_docs(manifest_rows, master_rows):
    pins, missing, disagreements = write_environment()
    write_readme()
    write_gaps(manifest_rows, master_rows, missing, disagreements)
    meta = {
        "python_running": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pins_from_reproduce_config": pins,
        "configs_missing_library_versions": missing,
        "disagreements": disagreements,
    }
    (CHAPTER_A / "ENV_RUNTIME.json").write_text(json.dumps(meta, indent=2) + "\n")
    return pins, missing, disagreements
