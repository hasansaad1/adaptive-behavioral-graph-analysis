"""Orchestrate OCGIN AndroCT 2017 experiment and write artifacts."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from abrg.androct.run_gae_run2 import floor_aucs
from abrg.ocgin import (
    BATCH_SIZE,
    EPOCHS,
    HIGHEST_SIZE_FLOOR_REF,
    LR,
    OCGIN_OUTPUT_ROOT,
    REF_ROWS,
    SEEDS,
    WEIGHT_DECAY,
)
from abrg.ocgin.baselines import ocpool_eval
from abrg.ocgin.data import load_ocgin_corpus, malware_train_split
from abrg.ocgin.models import Variant
from abrg.ocgin.score import full_method_eval
from abrg.ocgin.train import train_ocgin


def _mean_std(vals: list[float]) -> dict[str, float]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(arr)),
        "std": float(np.nanstd(arr, ddof=0)) if len(arr) else float("nan"),
        "values": [float(v) for v in vals],
    }


def _summarize_auc_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    floors = [r["auc"]["auc_floor"] for r in rows]
    raws = [r["auc"]["auc"] for r in rows]
    dirs = [r["auc"]["direction"] for r in rows]
    collapses = [bool(r.get("collapse")) for r in rows]
    return {
        "auc_floor": _mean_std(floors),
        "auc_raw": _mean_std(raws),
        "directions": dirs,
        "any_collapse": any(collapses),
        "n_collapse": int(sum(collapses)),
        "inverted_fraction": float(
            sum(1 for d in dirs if d == "benign_higher_score") / max(len(dirs), 1)
        ),
    }


def _run_ocgin_seeds(
    *,
    variant: Variant,
    tensors: dict,
    split: dict,
    seeds: tuple[int, ...],
    trained: bool,
    anomaly_is_malware: bool,
    device: torch.device,
    tag: str,
) -> dict[str, Any]:
    per_seed: list[dict[str, Any]] = []
    for seed in seeds:
        print(f"[ocgin] {tag} variant={variant} seed={seed} trained={trained}", flush=True)
        model, theta, losses = train_ocgin(
            variant=variant,
            tensors=tensors,
            train_apps=split["train"],
            seed=seed,
            epochs=EPOCHS if trained else 0,
            lr=LR,
            weight_decay=WEIGHT_DECAY,
            batch_size=BATCH_SIZE,
            device=device,
            trained=trained,
        )
        ev = full_method_eval(
            model,
            theta,
            tensors,
            split,
            batch_size=BATCH_SIZE,
            device=device,
            anomaly_is_malware=anomaly_is_malware,
        )
        ev["seed"] = seed
        ev["final_train_loss"] = losses[-1] if losses else float("nan")
        ev["variant"] = variant
        ev["trained"] = trained
        per_seed.append(ev)
    return {
        "tag": tag,
        "variant": variant,
        "trained": trained,
        "anomaly_is_malware": anomaly_is_malware,
        "per_seed": per_seed,
        "aggregate": _summarize_auc_rows(per_seed),
        "graph_embedding_dim": per_seed[0]["graph_embedding_dim"] if per_seed else None,
    }


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _fmt_ci(ci: list[float] | None) -> str:
    if not ci or len(ci) < 2:
        return "—"
    return f"[{ci[0]:.4f}, {ci[1]:.4f}]"


def write_summary(
    out: Path,
    *,
    results: dict[str, Any],
    floors: dict[str, Any],
    fingerprint: str,
) -> None:
    highest = max(floors[k]["auc_floor"] for k in floors if isinstance(floors[k], dict) and "auc_floor" in floors[k])
    lines: list[str] = [
        "# AndroCT 2017 — OCGIN",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- corpus fingerprint: `{fingerprint[:32]}…`",
        f"- split: train_benign=562 test_benign=141 test_malware=1700 (seed=42)",
        f"- graph embedding dim (OCGIN): {results['OCGIN_orig_A']['graph_embedding_dim']}",
        f"- edge weights: **not used** (GINConv has no edge_weight)",
        f"- highest size floor (recomputed): {highest:.6f}",
        f"- gate reference (mapped events ~0.703): {HIGHEST_SIZE_FLOOR_REF}",
        "",
        "## Size floors",
        "",
        "| metric | AUC_floor | direction | CI_floor |",
        "|---|---:|---|---|",
    ]
    for k, b in floors.items():
        if not isinstance(b, dict) or "auc_floor" not in b:
            continue
        lines.append(
            f"| {k} | {b['auc_floor']:.6f} | {b['direction']} | {_fmt_ci(b.get('ci95_floor'))} |"
        )

    lines += [
        "",
        "## Headline — Variant A (train benign; malware = anomaly)",
        "",
        "| method | AUC_floor mean±std | AUC raw mean±std | inverted frac | collapse | clears floor |",
        "|---|---:|---:|---:|---|---|",
    ]

    def row(name: str, block: dict[str, Any]) -> str:
        agg = block["aggregate"]
        af = agg["auc_floor"]
        ar = agg["auc_raw"]
        mean_af = af["mean"]
        clears = mean_af >= highest and not agg["any_collapse"]
        collapse = "COLLAPSE DETECTED" if agg["any_collapse"] else "no"
        return (
            f"| {name} | {af['mean']:.4f}±{af['std']:.4f} | {ar['mean']:.4f}±{ar['std']:.4f} | "
            f"{agg['inverted_fraction']:.2f} | {collapse} | {clears} |"
        )

    for key, label in (
        ("OCGIN_orig_A", "OCGIN_orig"),
        ("OCGIN_plus_A", "OCGIN_plus"),
        ("OCGIN_orig_rand_A", "RANDOM-INIT OCGIN_orig"),
        ("OCGIN_plus_rand_A", "RANDOM-INIT OCGIN_plus"),
        ("OCPool_add_A", "OCPool_add"),
        ("OCPool_mean_A", "OCPool_mean"),
        ("OCPool_max_A", "OCPool_max"),
    ):
        lines.append(row(label, results[key]))

    lines += [
        "",
        "### Reference rows (not re-run)",
        "",
        "| method | AUC_floor | inverted |",
        "|---|---:|---|",
    ]
    for k, v in REF_ROWS.items():
        lines.append(f"| {v['note']} | {v['auc_floor']:.3f} | {v['inverted']} |")

    lines += [
        "",
        "## Performance-flip diagnostic (raw AUC; Variant B = train malware / benign anomaly)",
        "",
        "| method | Variant A raw AUC mean | Variant B raw AUC mean | A+B |",
        "|---|---:|---:|---:|",
    ]
    for tag_a, tag_b, label in (
        ("OCGIN_orig_A", "OCGIN_orig_B", "OCGIN_orig"),
        ("OCGIN_plus_A", "OCGIN_plus_B", "OCGIN_plus"),
    ):
        a = results[tag_a]["aggregate"]["auc_raw"]["mean"]
        b = results[tag_b]["aggregate"]["auc_raw"]["mean"]
        lines.append(f"| {label} | {a:.4f} | {b:.4f} | {a + b:.4f} |")
    lines.append("")
    lines.append(
        "Variant B is a **diagnostic only**; it violates the benign-only training premise "
        "and is never proposed as a detector."
    )

    lines += [
        "",
        "## Per-seed AUC_floor (Variant A)",
        "",
        "| method | seed | AUC_floor | AUC raw | direction | collapse |",
        "|---|---:|---:|---:|---|---|",
    ]
    for key, label in (
        ("OCGIN_orig_A", "OCGIN_orig"),
        ("OCGIN_plus_A", "OCGIN_plus"),
        ("OCGIN_orig_rand_A", "RAND OCGIN_orig"),
        ("OCGIN_plus_rand_A", "RAND OCGIN_plus"),
    ):
        for r in results[key]["per_seed"]:
            lines.append(
                f"| {label} | {r['seed']} | {r['auc']['auc_floor']:.6f} | {r['auc']['auc']:.6f} | "
                f"{r['auc']['direction']} | {r['collapse']} |"
            )

    # OCPool single-seed
    lines += ["", "## OCPool (single fit, Variant A)", ""]
    lines.append("| method | AUC_floor | AUC raw | direction | clears floor |")
    lines.append("|---|---:|---:|---|---|")
    for key in ("OCPool_add_A", "OCPool_mean_A", "OCPool_max_A"):
        r = results[key]["per_seed"][0]
        clears = r["auc"]["auc_floor"] >= highest
        lines.append(
            f"| {results[key]['tag']} | {r['auc']['auc_floor']:.6f} | {r['auc']['auc']:.6f} | "
            f"{r['auc']['direction']} | {clears} |"
        )

    lines += [
        "",
        "## Leak Spearman ρ (Variant A, seed=42 OCGIN_orig)",
        "",
        "| metric | ρ |",
        "|---|---:|",
    ]
    leak = results["OCGIN_orig_A"]["per_seed"][0]["leak_spearman"]
    for k, v in leak.items():
        lines.append(f"| {k} | {v:.6f} |" if math.isfinite(v) else f"| {k} | nan |")

    lines += [
        "",
        "## Collapse diagnostics (OCGIN_orig seed=42, train)",
        "",
    ]
    d0 = results["OCGIN_orig_A"]["per_seed"][0]["collapse_diagnostics"]["train"]
    lines.append(f"- mean_var_across_dims: {d0['mean_var_across_dims']:.8e}")
    lines.append(f"- dist_to_theta mean±std: {d0['dist_to_theta_mean']:.6f} ± {d0['dist_to_theta_std']:.6f}")
    lines.append(f"- frac_within_1e-3_of_theta: {d0['frac_within_1e-3_of_theta']:.6f}")
    lines.append(f"- collapse_detected: {d0['collapse_detected']}")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> Path:
    out = OCGIN_OUTPUT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    (out / "per_seed").mkdir(exist_ok=True)
    (out / "collapse_diagnostics").mkdir(exist_ok=True)

    device = torch.device("cpu")
    corpus = load_ocgin_corpus()
    tensors = corpus.tensors
    split_a = corpus.split
    test_apps = split_a["test_benign"] + split_a["test_malware"]
    floors = floor_aucs(test_apps, tensors)
    _write_json(out / "floors.json", floors)

    results: dict[str, Any] = {}

    # Primary Variant A
    for variant in ("OCGIN_orig", "OCGIN_plus"):
        results[f"{variant}_A"] = _run_ocgin_seeds(
            variant=variant,  # type: ignore[arg-type]
            tensors=tensors,
            split=split_a,
            seeds=SEEDS,
            trained=True,
            anomaly_is_malware=True,
            device=device,
            tag=f"{variant}_A",
        )
        results[f"{variant}_rand_A"] = _run_ocgin_seeds(
            variant=variant,  # type: ignore[arg-type]
            tensors=tensors,
            split=split_a,
            seeds=SEEDS,
            trained=False,
            anomaly_is_malware=True,
            device=device,
            tag=f"{variant}_rand_A",
        )

    # OCPool
    for pool in ("add", "mean", "max"):
        print(f"[ocgin] OCPool_{pool}", flush=True)
        ev = ocpool_eval(tensors, split_a, pool=pool, anomaly_is_malware=True)
        results[f"OCPool_{pool}_A"] = {
            "tag": f"OCPool_{pool}",
            "per_seed": [ev],
            "aggregate": _summarize_auc_rows([ev]),
            "graph_embedding_dim": ev["graph_embedding_dim"],
        }

    # Flip diagnostic Variant B
    split_b = malware_train_split(corpus.bundle.eligible, n_train=len(split_a["train"]), seed=42)
    print(
        f"[ocgin] flip split_B train_malware={len(split_b['train'])} "
        f"test_benign={len(split_b['test_benign'])} test_malware={len(split_b['test_malware'])}",
        flush=True,
    )
    for variant in ("OCGIN_orig", "OCGIN_plus"):
        results[f"{variant}_B"] = _run_ocgin_seeds(
            variant=variant,  # type: ignore[arg-type]
            tensors=tensors,
            split=split_b,
            seeds=SEEDS,
            trained=True,
            anomaly_is_malware=False,
            device=device,
            tag=f"{variant}_B_flip",
        )

    # Persist per-seed + collapse
    for key, block in results.items():
        _write_json(out / "per_seed" / f"{key}.json", block)
        if block.get("per_seed") and "collapse_diagnostics" in block["per_seed"][0]:
            _write_json(
                out / "collapse_diagnostics" / f"{key}.json",
                {str(r["seed"]): r["collapse_diagnostics"] for r in block["per_seed"] if "seed" in r},
            )

    comparison = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "run": "ocgin",
        "corpus_fingerprint": corpus.fingerprint,
        "pins": {
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WEIGHT_DECAY,
            "hidden": 32,
            "n_layers": 4,
            "seeds": list(SEEDS),
            "batch_size": BATCH_SIZE,
            "edge_weight_in_gin": False,
            "gin_note": "GINConv does not accept edge_weight; w_cum unused",
        },
        "floors": {
            k: {"auc_floor": v["auc_floor"], "direction": v["direction"]}
            for k, v in floors.items()
            if isinstance(v, dict) and "auc_floor" in v
        },
        "highest_floor": max(
            v["auc_floor"] for v in floors.values() if isinstance(v, dict) and "auc_floor" in v
        ),
        "results": {
            k: {
                "aggregate": v["aggregate"],
                "graph_embedding_dim": v.get("graph_embedding_dim"),
                "per_seed_auc_floor": [
                    {
                        "seed": r.get("seed"),
                        "auc_floor": r["auc"]["auc_floor"],
                        "auc": r["auc"]["auc"],
                        "direction": r["auc"]["direction"],
                        "collapse": r.get("collapse", False),
                        "ci95_floor": r["auc"].get("ci95_floor"),
                    }
                    for r in v["per_seed"]
                ],
            }
            for k, v in results.items()
        },
        "references": REF_ROWS,
        "flip": {
            "OCGIN_orig": {
                "A_raw_mean": results["OCGIN_orig_A"]["aggregate"]["auc_raw"]["mean"],
                "B_raw_mean": results["OCGIN_orig_B"]["aggregate"]["auc_raw"]["mean"],
                "sum": results["OCGIN_orig_A"]["aggregate"]["auc_raw"]["mean"]
                + results["OCGIN_orig_B"]["aggregate"]["auc_raw"]["mean"],
            },
            "OCGIN_plus": {
                "A_raw_mean": results["OCGIN_plus_A"]["aggregate"]["auc_raw"]["mean"],
                "B_raw_mean": results["OCGIN_plus_B"]["aggregate"]["auc_raw"]["mean"],
                "sum": results["OCGIN_plus_A"]["aggregate"]["auc_raw"]["mean"]
                + results["OCGIN_plus_B"]["aggregate"]["auc_raw"]["mean"],
            },
        },
    }
    _write_json(out / "comparison.json", comparison)

    best_a = results["OCGIN_orig_A"]["aggregate"]["auc_floor"]["mean"]
    reproduce = {
        "kind": "androct_auc",
        "run_id": "androct_2017/ocgin",
        "axis": "OCGIN deep one-class graph-level AD (new objective family)",
        "cli_module": "abrg.ocgin",
        "profile": "ocgin_orig_mean_auc_floor",
        "expected": {
            "auc_floor": best_a,
            "direction": results["OCGIN_orig_A"]["per_seed"][0]["auc"]["direction"],
            "inverted": results["OCGIN_orig_A"]["per_seed"][0]["auc"]["direction"]
            == "benign_higher_score",
        },
        "atol_auc_floor": 0.05,
        "pins": comparison["pins"],
        "corpus_fingerprint": corpus.fingerprint,
    }
    _write_json(out / "reproduce_config.json", reproduce)

    write_summary(out, results=results, floors=floors, fingerprint=corpus.fingerprint)
    print(f"[ocgin] done → {out}", flush=True)
    return out


def main() -> None:
    run()


if __name__ == "__main__":
    main()
