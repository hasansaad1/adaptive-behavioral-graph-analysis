"""Backfill reproduce_config.json + reproduce.ipynb for all formal result dirs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from abrg.reproduce import emit_reproduce_artifacts, emit_reproduce_from_config, write_reproduce_notebook
from abrg.reproduce_kinds import config_for_androct, config_for_negative_control

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "abrg" / "output"

# AndroCT formal runs: (relative path, cli_module, profile, axis, cli_extra)
ANDROCT_RUNS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "androct_2017/arm_a_n1",
        "abrg.androct.run_gae",
        "arm_mean",
        "Arm A N=1 dynamic-only stochastic GAE",
        ["--arm", "arm_a_n1"],
    ),
    (
        "androct_2017/arm_b_n8",
        "abrg.androct.run_gae",
        "arm_mean",
        "Arm B N=8 dynamic-only stochastic GAE",
        ["--arm", "arm_b_n8"],
    ),
    (
        "androct_2017/run2",
        "abrg.androct.run_gae_run2",
        "gae_default",
        "Run 2 — static fusion + stochastic recon (from cache)",
        ["--from-cache"],
    ),
    (
        "androct_2017/run3",
        "abrg.androct.run_gae_run3",
        "gae_default",
        "Run 3 — deterministic full-adj weighted BCE",
        [],
    ),
    (
        "androct_2017/run3_5",
        "abrg.androct.run_gae_run3_5",
        "run3_5_hgb_full",
        "Run 3.5 — supervised HGB full (diagnostic)",
        [],
    ),
    (
        "androct_2017/run4",
        "abrg.androct.run_gae_run4",
        "run4_best",
        "Run 4 — dual recon alpha sweep",
        [],
    ),
    (
        "androct_2017/run5",
        "abrg.androct.run_gae_run5",
        "run5_best",
        "Run 5 — hidden bottleneck @ alpha=0.2",
        [],
    ),
    (
        "androct_2017/run8",
        "abrg.androct.run_gae_run8",
        "run8_best",
        "Run 8 — embedding-space scoring (no retrain)",
        [],
    ),
    (
        "androct_2017/run6/part1_ablation",
        "abrg.androct.run6_part1",
        "run6_part1_hgb",
        "Run 6 Part 1 — supervised node ablation HGB baseline",
        [],
    ),
    (
        "androct_2017/run6/part2_geometry",
        "abrg.androct.run6_part2",
        "run6_part2_centroid_raw",
        "Run 6 Part 2 — centroid Euclidean geometry",
        [],
    ),
    (
        "androct_2017/run6/part3_armB",
        "abrg.androct.run6_part3",
        "run6_part3_armB_mean",
        "Run 6 Part 3 — Arm B N=8 mean aggregation",
        [],
    ),
    (
        "androct_2017/run6/centroid_node_ablation",
        "abrg.androct.run6_centroid_oneclass",
        "run6_centroid_baseline",
        "Run 6 — centroid node ablation baseline",
        ["--task", "ablation"],
    ),
    (
        "androct_2017/run6/oneclass_baselines",
        "abrg.androct.run6_centroid_oneclass",
        "run6_oneclass_best",
        "Run 6 — one-class baselines best method",
        ["--task", "oneclass"],
    ),
    (
        "androct_2017/run6/ipc_scalar_probes",
        "abrg.androct.run6_ipc_whiten",
        "run6_ipc_act_v",
        "Run 6 — ipc_intents act_v_frac scalar probe",
        ["--task", "ipc"],
    ),
    (
        "androct_2017/run6/whiten_h8_a02",
        "abrg.androct.run6_ipc_whiten",
        "gae_default",
        "Run 6 — whitened dual-recon h=8 alpha=0.2",
        ["--task", "whiten"],
    ),
]

FRIDA_AXIS_HINTS: dict[str, str] = {
    "w35_h64_weighted": "window_sec 30→35 @ h64 weighted e300 (champion)",
    "w30_h64_weighted": "window_sec=30 h64 weighted e300",
    "norm_ab_v2": "normalization A/B unweighted",
    "norm_ab_v2_weighted": "normalization A/B weighted",
}


def _headline_metric(config: dict[str, Any]) -> str:
    kind = config.get("kind", "ratio")
    exp = config.get("expected") or {}
    if kind == "ratio":
        return f"ratio={exp.get('ratio', float('nan')):.4f}"
    if kind == "negative_control":
        return f"impossible_edge_auc={exp.get('impossible_edge_auc', float('nan')):.4f}"
    if kind == "androct_auc":
        return f"auc_floor={exp.get('auc_floor', float('nan')):.4f} dir={exp.get('direction')}"
    return str(exp)


def _emit_androct(rel: str, cli_module: str, profile: str, axis: str, cli_extra: list[str]) -> dict:
    run_dir = OUTPUT_ROOT / rel
    cfg = config_for_androct(
        run_dir,
        run_id=rel,
        axis=axis,
        cli_module=cli_module,
        profile=profile,
        cli_extra=cli_extra,
    )
    paths = emit_reproduce_from_config(run_dir, cfg)
    return {"run_id": rel, "kind": "androct_auc", "headline": _headline_metric(cfg), **paths}


def _emit_frida_ratio(run_dir: Path, run_id: str) -> dict:
    if (run_dir / "reproduce_config.json").exists() and (run_dir / "reproduce.ipynb").exists():
        cfg = json.loads((run_dir / "reproduce_config.json").read_text(encoding="utf-8"))
        if cfg.get("kind") in (None, "ratio"):
            if "kind" not in cfg:
                cfg["kind"] = "ratio"
                (run_dir / "reproduce_config.json").write_text(json.dumps(cfg, indent=2) + "\n")
            return {
                "run_id": run_id,
                "kind": "ratio",
                "headline": _headline_metric(cfg),
                "skipped": True,
            }
    axis = FRIDA_AXIS_HINTS.get(run_dir.name, run_dir.name)
    paths = emit_reproduce_artifacts(run_dir, axis=axis, run_id=run_id)
    cfg = json.loads((run_dir / "reproduce_config.json").read_text(encoding="utf-8"))
    cfg["kind"] = "ratio"
    (run_dir / "reproduce_config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    return {"run_id": run_id, "kind": "ratio", "headline": _headline_metric(cfg), **paths}


def _emit_norm_ab(name: str) -> dict:
    run_dir = OUTPUT_ROOT / name
    axis = FRIDA_AXIS_HINTS.get(name, name)
    paths = emit_reproduce_artifacts(run_dir, axis=axis, run_id=name)
    cfg_path = run_dir / "reproduce_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["atol_median"] = 0.03  # stochastic baseline; slightly wider than campaign default
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    write_reproduce_notebook(run_dir, cfg)
    return {"run_id": name, "kind": "ratio", "headline": _headline_metric(cfg), **paths}


def _emit_negative_control(name: str) -> dict:
    run_dir = OUTPUT_ROOT / name
    cfg = config_for_negative_control(run_dir, run_id=name, axis=f"negative control {name}")
    paths = emit_reproduce_from_config(run_dir, cfg)
    return {"run_id": name, "kind": "negative_control", "headline": _headline_metric(cfg), **paths}


def collect_frida_exp_runs() -> list[Path]:
    runs: list[Path] = []
    for p in sorted(OUTPUT_ROOT.rglob("comparison.json")):
        if "nb_repro" in p.parts:
            continue
        rel = p.parent.relative_to(OUTPUT_ROOT)
        parts = rel.parts
        if parts[0].startswith("exp_") or rel.as_posix() in ("norm_ab_v2", "norm_ab_v2_weighted"):
            runs.append(p.parent)
    return runs


def backfill_all(*, force_notebook: bool = False) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for rel, mod, profile, axis, extra in ANDROCT_RUNS:
        run_dir = OUTPUT_ROOT / rel
        if not (run_dir / "comparison.json").exists():
            records.append({"run_id": rel, "status": "missing_comparison"})
            continue
        rec = _emit_androct(rel, mod, profile, axis, extra)
        rec["status"] = "emitted"
        records.append(rec)

    for name in ("norm_ab_v2", "norm_ab_v2_weighted"):
        if (OUTPUT_ROOT / name / "comparison.json").exists():
            rec = _emit_norm_ab(name)
            rec["status"] = "emitted"
            records.append(rec)

    for name in ("negative_control_v2", "negative_control_v2_weighted"):
        nc_dir = OUTPUT_ROOT / name
        if (nc_dir / "negative_control_results.json").exists():
            rec = _emit_negative_control(name)
            rec["status"] = "emitted"
            records.append(rec)

    for run_dir in collect_frida_exp_runs():
        if run_dir.name in ("norm_ab_v2", "norm_ab_v2_weighted"):
            continue
        run_id = run_dir.relative_to(OUTPUT_ROOT).as_posix()
        rec = _emit_frida_ratio(run_dir, run_id)
        rec["status"] = "emitted" if not rec.get("skipped") else "skipped_existing"
        records.append(rec)

    desc_seed_dir = OUTPUT_ROOT / "desc_seed"
    if (desc_seed_dir / "reproduce_config.json").exists():
        records.append(
            {
                "run_id": "desc_seed",
                "kind": "desc_seed",
                "headline": "self_cross_auc=0.501 within_prior=0.952",
                "status": "emitted",
            }
        )

    return records


def write_status_md(records: list[dict[str, Any]]) -> Path:
    lines = [
        "# Reproduce status",
        "",
        "| run_id | kind | headline | notebook | config | validate |",
        "|---|---|---|---|---|---|",
    ]
    for rec in records:
        run_id = rec.get("run_id", "?")
        run_dir = OUTPUT_ROOT / run_id
        nb = (run_dir / "reproduce.ipynb").exists()
        cfg = (run_dir / "reproduce_config.json").exists()
        val = "unknown"
        vr = run_dir / "validate_reproduce_report.json"
        if vr.exists():
            payload = json.loads(vr.read_text(encoding="utf-8"))
            ok = all(r.get("ok") for r in payload.get("reports", []))
            val = "ok" if ok else "fail"
        elif rec.get("status") == "missing_comparison":
            val = "n/a"
        else:
            val = "pending"
        lines.append(
            f"| `{run_id}` | {rec.get('kind', '?')} | {rec.get('headline', '—')} | "
            f"{'yes' if nb else 'no'} | {'yes' if cfg else 'no'} | {val} |"
        )
    path = OUTPUT_ROOT / "REPRODUCE_STATUS.md"
    lines.extend(
        [
            "",
            "## Batch validate pending",
            "",
            "```bash",
            "cd REPO_ROOT",
            ".venv/bin/python -m abrg.batch_validate_reproduce",
            "```",
            "",
            "Long-running AndroCT retrains (run2/4/5, arms) may take hours; run overnight.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_index_notebook(records: list[dict[str, Any]]) -> Path:
    nb_path = REPO_ROOT / "notebooks" / "REPRODUCE_INDEX.ipynb"
    nb_path.parent.mkdir(parents=True, exist_ok=True)

    md = """# ABRG reproduce index

Per-run notebooks live beside frozen outputs under `abrg/output/`. Validate one run:

```bash
cd REPO_ROOT
.venv/bin/python -m abrg.validate_reproduce --run-dir abrg/output/<run_id>
```

Status table: `abrg/output/REPRODUCE_STATUS.md`
"""
    table_lines = ["\n| run_id | kind | validate |", "|---|---|---|"]
    for rec in records:
        run_id = rec.get("run_id", "?")
        run_dir = OUTPUT_ROOT / run_id
        val = "pending"
        vr = run_dir / "validate_reproduce_report.json"
        if vr.exists():
            payload = json.loads(vr.read_text(encoding="utf-8"))
            val = "ok" if all(r.get("ok") for r in payload.get("reports", [])) else "fail"
        table_lines.append(f"| `{run_id}` | {rec.get('kind', '?')} | {val} |")

    code = f"""from pathlib import Path
REPO_ROOT = Path.cwd().resolve()
if not (REPO_ROOT / "abrg").is_dir():
    REPO_ROOT = REPO_ROOT.parent
runs = {json.dumps([r.get("run_id") for r in records if r.get("run_id")], indent=2)}
for run_id in runs:
    nb = REPO_ROOT / "abrg" / "output" / run_id / "reproduce.ipynb"
    print(run_id, "OK" if nb.is_file() else "MISSING", nb)
"""

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": (md + "\n".join(table_lines)).splitlines(keepends=True),
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": code.splitlines(keepends=True),
            },
        ],
    }
    nb_path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    return nb_path


def main() -> int:
    records = backfill_all()
    status = write_status_md(records)
    index = write_index_notebook(records)
    print(f"Backfilled {len(records)} runs")
    print("Status:", status)
    print("Index:", index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
