"""Orchestrate Part B then Part A (transitions experiment)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from abrg.apigraph.models_stage4 import ocpool, run_gae_dual, run_ocgin_plus
from abrg.transitions import REF, SEEDS, TRANSITIONS_OUTPUT_ROOT
from abrg.transitions.part_a import run_part_a
from abrg.transitions.part_b import run_part_b
from abrg.transitions.split import load_split_or_stop


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _mean_std(vals: list[float]) -> dict[str, Any]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(arr)) if len(arr) else float("nan"),
        "std": float(np.nanstd(arr, ddof=0)) if len(arr) else float("nan"),
        "values": [float(v) for v in vals],
    }


def _floor_of(cfg: dict, det: str) -> float:
    block = cfg[det]
    if det in ("ocsvm_rbf", "isolation_forest"):
        return float(block["auc_floor"]["mean"])
    return float(block["auc"]["auc_floor"])


def write_summary(
    *,
    out: Path,
    digest: str,
    part_b: dict[str, Any],
    part_a: dict[str, Any] | None,
    part_a_models: dict[str, Any] | None,
    part_b_inv: dict[str, Any] | None,
) -> None:
    lines: list[str] = []
    lines.append("# Transitions — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_sha_digest: `{digest}`")
    lines.append("- split: 562 / 141 / 1700 seed=42")
    lines.append("")

    # ---- Part B headline first ----
    lines.append("## Part B — one-class on proximity transition features (headline)")
    lines.append("")
    lines.append(f"- F4: {part_b['F4_definition']}")
    lines.append(f"- feature dims: {part_b['feature_dims']}")
    lines.append(
        f"- references: OCPool_mean={REF['OCPool_mean']} · "
        f"OCPool_resid={REF['OCPool_mean_residualized']} · GAE={REF['GAE']} · "
        f"adj_HGB={REF['supervised_adj_only_HGB']} · full_HGB={REF['supervised_full_HGB']} · "
        f"mapped_floor={REF['highest_size_floor_mapped']}"
    )
    lines.append("")
    lines.append(
        f"- n configs clearing mapped floor 0.7025: {part_b['n_clear_size_floor']}"
    )
    lines.append(
        f"- n configs clearing OCPool_mean 0.7765: {part_b['n_clear_ocpool']}"
    )
    best = part_b["best"]
    lines.append(
        f"- best: `{best['tag']}` :: `{best['detector']}` "
        f"auc_floor={best['auc_floor']:.4f} ({best['direction']}) "
        f"clears_size={best['clears_size_floor_0.7025']} "
        f"clears_ocpool={best['clears_OCPool_mean_0.7765']}"
    )
    lines.append("")

    # Compact table: feature x detector (no-PCA rows + best PCA per feature)
    lines.append("### AUC_floor by feature × detector (proximity tensors)")
    lines.append("")
    dets = [
        "ocsvm_rbf",
        "isolation_forest",
        "centroid_euclidean",
        "centroid_cosine",
        "mahalanobis_ledoit_wolf",
        "knn_k1",
        "knn_k5",
        "knn_k20",
    ]
    # base features only (no pca) for main table
    base_tags = [t for t in part_b["configs"] if "pca" not in t]
    lines.append("| feature | " + " | ".join(dets) + " |")
    lines.append("|---|" + "|".join(["---"] * len(dets)) + "|")
    for tag in sorted(base_tags):
        cfg = part_b["configs"][tag]
        feat = cfg["feature"]
        cells = [f"{_floor_of(cfg, d):.4f}" for d in dets]
        lines.append(f"| {feat} (d={cfg['dim']}) | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("### PCA variants (F1 / F3) — best detector per setting")
    lines.append("")
    lines.append("| tag | dim | explained_var_sum | best_detector | auc_floor | clears_0.7025 | clears_0.7765 |")
    lines.append("|---|---|---|---|---|---|---|")
    for tag, cfg in sorted(part_b["configs"].items()):
        if "pca" not in tag:
            continue
        floors = [(d, _floor_of(cfg, d)) for d in dets]
        d_best, f_best = max(floors, key=lambda x: x[1])
        ev = cfg.get("pca", {}).get("explained_variance_sum", float("nan"))
        lines.append(
            f"| {tag} | {cfg['dim']} | {ev:.4f} | {d_best} | {f_best:.4f} | "
            f"{f_best > REF['highest_size_floor_mapped']} | "
            f"{f_best > REF['OCPool_mean']} |"
        )
    lines.append("")

    lines.append("### Gate — configs clearing thresholds")
    lines.append("")
    clears_oc = [r for r in part_b["gate_rows"] if r["clears_OCPool_mean_0.7765"]]
    clears_sz = [r for r in part_b["gate_rows"] if r["clears_size_floor_0.7025"]]
    lines.append(f"clearing OCPool_mean 0.7765 (n={len(clears_oc)}):")
    for r in sorted(clears_oc, key=lambda x: -x["auc_floor"])[:30]:
        lines.append(
            f"- {r['tag']} :: {r['detector']}: {r['auc_floor']:.4f} ({r['direction']})"
        )
    if not clears_oc:
        lines.append("- (none)")
    lines.append("")
    lines.append(f"clearing mapped floor 0.7025 (n={len(clears_sz)}):")
    for r in sorted(clears_sz, key=lambda x: -x["auc_floor"])[:40]:
        lines.append(
            f"- {r['tag']} :: {r['detector']}: {r['auc_floor']:.4f} ({r['direction']})"
        )
    if not clears_sz:
        lines.append("- (none)")
    lines.append("")

    # ---- Part A ----
    lines.append("## Part A — 22-category invocation edges")
    lines.append("")
    if part_a is None:
        lines.append("not run")
        lines.append("")
    else:
        s = part_a["summary"]
        lines.append(f"- node_feat_dim: {s['node_feat_dim']} (asserted match run 3)")
        lines.append(
            "- multi-category: cartesian product of categorize_callee sets on both endpoints"
        )
        lines.append(
            f"- downstream variant: `{s['downstream_variant']}` "
            f"(self-loop increments corpus={s['no_self_loops']['n_self_loop_increments_corpus']}; "
            f"with_self_loops corpus increments={s['with_self_loops']['n_self_loop_increments_corpus']})"
        )
        lines.append("")
        lines.append("### Drop accounting (no_self_loops, corpus rates)")
        lines.append("")
        lines.append("| partition | caller_um | callee_um | either_um |")
        lines.append("|---|---|---|---|")
        for part in ("train_benign", "test_benign", "test_malware"):
            d = s["no_self_loops"]["drop"][part]
            lines.append(
                f"| {part} | {d['corpus_caller_unmapped_rate']:.4f} | "
                f"{d['corpus_callee_unmapped_rate']:.4f} | "
                f"{d['corpus_either_unmapped_rate']:.4f} |"
            )
        asym = s["no_self_loops"]["drop"]["asymmetry"]
        lines.append("")
        lines.append(
            f"- either_um |train_b − test_m| = "
            f"{asym['either_unmapped_train_benign_vs_test_malware']:.4f} "
            f"(warn>{asym['warn_threshold']}: {asym['asymmetric_train_vs_malware']})"
        )
        lines.append(
            f"- either_um |test_b − test_m| = "
            f"{asym['either_unmapped_test_benign_vs_test_malware']:.4f} "
            f"(warn>{asym['warn_threshold']}: {asym['asymmetric_testb_vs_malware']})"
        )
        lines.append("")
        lines.append("### Floors (no_self_loops)")
        lines.append("")
        lines.append("| metric | auc_floor | direction |")
        lines.append("|---|---|---|")
        for name, block in s["no_self_loops"]["floors"].items():
            lines.append(
                f"| {name} | {block['auc_floor']:.4f} | {block['direction']} |"
            )
        lines.append("")
        lines.append(
            "baselines: proximity edge 0.5267 · API-1000 0.5013 · "
            "V2 inv 0.7338 · V3 0.5070"
        )
        lines.append("")
        g = s["gate"]
        lines.append(f"### Gate: **{g['verdict']}**")
        lines.append(
            f"- edge={g['edge_count']:.4f} dens={g['density']:.4f} "
            f"moved={g['moved_ge_0.60']} drop_symmetric={g['drop_symmetric']}"
        )
        lines.append("")

        # with_self_loops floors briefly
        lines.append("### Floors (with_self_loops)")
        lines.append("")
        lines.append("| metric | auc_floor | direction |")
        lines.append("|---|---|---|")
        for name, block in s["with_self_loops"]["floors"].items():
            lines.append(
                f"| {name} | {block['auc_floor']:.4f} | {block['direction']} |"
            )
        lines.append("")

    if part_b_inv is not None:
        lines.append("## Part A follow-on — Part B battery on invocation adj")
        lines.append("")
        best_i = part_b_inv["best"]
        lines.append(
            f"- best: `{best_i['tag']}` :: `{best_i['detector']}` "
            f"auc_floor={best_i['auc_floor']:.4f} "
            f"clears_size={best_i['clears_size_floor_0.7025']} "
            f"clears_ocpool={best_i['clears_OCPool_mean_0.7765']}"
        )
        lines.append(
            f"- n clear size / ocpool: {part_b_inv['n_clear_size_floor']} / "
            f"{part_b_inv['n_clear_ocpool']}"
        )
        lines.append("")

    if part_a_models is not None:
        lines.append("## Part A follow-on — GAE / OCGIN_plus")
        lines.append("")
        lines.append(f"- highest_floor: {part_a_models['highest_floor']:.4f}")
        for pool, row in part_a_models["ocpool"].items():
            lines.append(
                f"- OCPool_{pool}: {row['auc']['auc_floor']:.4f} "
                f"clears={row['clears_highest_floor']}"
            )
        for tag, key in (("GAE", "gae"), ("OCGIN_plus", "ocgin_plus")):
            tr = part_a_models[key]["trained"]
            lines.append(
                f"- {tag} trained: {tr['auc_floor']['mean']:.4f} ± {tr['auc_floor']['std']:.4f} "
                f"clears_mean={tr['clears_highest_floor_mean']}"
            )
            rnd = part_a_models[key]["random_init"]
            lines.append(
                f"- {tag} random-init: {rnd['auc_floor']['mean']:.4f} ± {rnd['auc_floor']['std']:.4f}"
            )
        lines.append("")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[transitions] wrote {out / 'SUMMARY.md'}", flush=True)


def _run_gnn_stage(
    tensors: dict,
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    floors: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    highest = max(float(floors[k]["auc_floor"]) for k in floors)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"highest_floor": highest, "floors": floors}

    results["ocpool"] = {}
    for pool in ("add", "mean", "max"):
        row = ocpool(tensors, train_shas, test_b, test_m, pool)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest
        results["ocpool"][pool] = row

    gae_tr, gae_rd = [], []
    for seed in SEEDS:
        print(f"[transitions/A] GAE seed={seed}", flush=True)
        row = run_gae_dual(tensors, train_shas, test_b, test_m, seed=seed, trained=True)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest
        gae_tr.append(row)
        rrow = run_gae_dual(
            tensors, train_shas, test_b, test_m, seed=seed, trained=False, epochs=0
        )
        rrow["clears_highest_floor"] = float(rrow["auc"]["auc_floor"]) > highest
        gae_rd.append(rrow)
    results["gae"] = {
        "trained": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in gae_tr]),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in gae_tr])["mean"]
            )
            > highest,
            "per_seed": gae_tr,
        },
        "random_init": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in gae_rd]),
            "per_seed": gae_rd,
        },
    }

    oc_tr, oc_rd = [], []
    for seed in SEEDS:
        print(f"[transitions/A] OCGIN_plus seed={seed}", flush=True)
        row = run_ocgin_plus(tensors, train_shas, test_b, test_m, seed=seed, trained=True)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest
        oc_tr.append(row)
        rrow = run_ocgin_plus(
            tensors, train_shas, test_b, test_m, seed=seed, trained=False, epochs=0
        )
        rrow["clears_highest_floor"] = float(rrow["auc"]["auc_floor"]) > highest
        oc_rd.append(rrow)
    results["ocgin_plus"] = {
        "trained": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in oc_tr]),
            "n_collapse": int(sum(1 for r in oc_tr if r.get("collapse"))),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in oc_tr])["mean"]
            )
            > highest,
            "per_seed": oc_tr,
        },
        "random_init": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in oc_rd]),
            "n_collapse": int(sum(1 for r in oc_rd if r.get("collapse"))),
            "per_seed": oc_rd,
        },
    }
    _write_json(out_dir / "models_summary.json", results)
    return results


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Transitions: Part B then Part A")
    p.add_argument("--output-dir", type=Path, default=TRANSITIONS_OUTPUT_ROOT)
    p.add_argument("--skip-part-a", action="store_true")
    p.add_argument("--skip-part-b", action="store_true")
    args = p.parse_args(argv)

    out = args.output_dir
    part_b_dir = out / "partB_oneclass"
    part_a_dir = out / "partA_invocation"
    out.mkdir(parents=True, exist_ok=True)

    bundle = load_split_or_stop()
    train_shas = [a.sha256 for a in bundle.train]
    test_b = [a.sha256 for a in bundle.test_benign]
    test_m = [a.sha256 for a in bundle.test_malware]
    all_apps = bundle.train + bundle.test_benign + bundle.test_malware

    part_b = None
    if not args.skip_part_b:
        print("[transitions] === PART B (first) ===", flush=True)
        part_b = run_part_b(
            train_shas=train_shas,
            test_b=test_b,
            test_m=test_m,
            out_dir=part_b_dir,
            tag_prefix="prox",
        )
    else:
        part_b = json.loads((part_b_dir / "partB_summary.json").read_text(encoding="utf-8"))

    part_a_pack = None
    part_b_inv = None
    part_a_models = None
    if not args.skip_part_a:
        print("[transitions] === PART A ===", flush=True)
        part_a_pack = run_part_a(
            all_apps=all_apps,
            train_shas=train_shas,
            test_b=test_b,
            test_m=test_m,
            out_dir=part_a_dir,
        )
        if part_a_pack["gate"]["continue_to_models"]:
            print("[transitions] Part A PASS → Part B on invocation + GNN", flush=True)
            part_b_inv = run_part_b(
                train_shas=train_shas,
                test_b=test_b,
                test_m=test_m,
                out_dir=part_a_dir / "oneclass_on_invocation",
                tensors=part_a_pack["tensors_no_self"],
                tag_prefix="inv",
            )
            part_a_models = _run_gnn_stage(
                part_a_pack["tensors_no_self"],
                train_shas,
                test_b,
                test_m,
                part_a_pack["summary"]["no_self_loops"]["floors"],
                part_a_dir / "models",
            )
        else:
            print("[transitions] Part A STOP — no models", flush=True)

    write_summary(
        out=out,
        digest=bundle.sha_list_digest,
        part_b=part_b,
        part_a=part_a_pack,
        part_a_models=part_a_models,
        part_b_inv=part_b_inv,
    )
    _write_json(
        out / "run_meta.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "sha_list_digest": bundle.sha_list_digest,
            "part_a_gate": None if part_a_pack is None else part_a_pack["gate"],
        },
    )


if __name__ == "__main__":
    main()
