"""Orchestrate API-level graph Stages 1–3; Stage 4 only if structural gate passes."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from abrg.androct.run_gae_run3_5 import _stratified_split
from abrg.apigraph import (
    APIGRAPH_OUTPUT_ROOT,
    BASELINE_22,
    SEED,
    STRUCTURAL_FLOOR_PASS,
    VOCAB_KS,
)
from abrg.apigraph.construct import (
    NODE_FEAT_DIM,
    STATIC_GLOBAL_DIM,
    build_graph_tensors,
    construction_stats,
)
from abrg.apigraph.extract import extract_sequences
from abrg.apigraph.floors import compute_floors, gate_decision
from abrg.apigraph.models_stage4 import (
    ocpool,
    run_gae_dual,
    run_ocgin_plus,
    supervised_probe,
)
from abrg.apigraph.split import load_run3_split
from abrg.apigraph.vocab import VOCAB_SOURCE_ASSERTION, build_vocabularies, coverage_table

SEEDS = (42, 43, 44, 45, 46)
REF_22_CEILING = 0.976  # Run 3.5 HGB diagnostic


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _mean_std(vals: list[float]) -> dict[str, float]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(arr)) if len(arr) else float("nan"),
        "std": float(np.nanstd(arr, ddof=0)) if len(arr) else float("nan"),
        "values": [float(v) for v in vals],
    }


def _build_tensors_for_k(
    *,
    K: int,
    vocab: list[str],
    sequences: dict[str, list[str]],
    by_sha: dict[str, Any],
    shas: list[str],
) -> dict[str, dict[str, Any]]:
    tensors: dict[str, dict[str, Any]] = {}
    for i, sha in enumerate(shas):
        tensors[sha] = build_graph_tensors(sequences[sha], vocab, app=by_sha[sha])
        if (i + 1) % 500 == 0:
            print(f"  … K={K} graphs {i+1}/{len(shas)}", flush=True)
    return tensors


def _pick_best_k(gate: dict[str, Any]) -> int | None:
    """Best K = argmax max(active_nodes_floor, edge_count_floor)."""
    best_k = None
    best_score = -1.0
    for k_str, row in gate["per_k"].items():
        score = max(float(row["active_nodes"]), float(row["edge_count"]))
        if score > best_score:
            best_score = score
            best_k = int(k_str)
    return best_k


def _run_stage4(
    *,
    K: int,
    tensors: dict[str, dict[str, Any]],
    split_bundle,
    sequences: dict[str, list[str]],
    vocab: list[str],
    floors: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    train_shas = [a.sha256 for a in split_bundle.train]
    test_b = [a.sha256 for a in split_bundle.test_benign]
    test_m = [a.sha256 for a in split_bundle.test_malware]

    highest_struct = max(
        float(floors["active_nodes"]["auc_floor"]),
        float(floors["edge_count"]["auc_floor"]),
        float(floors["graph_density"]["auc_floor"]),
    )
    highest_size = max(
        float(floors["in_vocab_event_count"]["auc_floor"]),
        float(floors["total_event_count"]["auc_floor"]),
        float(floors["oov_rate"]["auc_floor"]),
    )
    highest_floor = max(highest_struct, highest_size)

    results: dict[str, Any] = {
        "K": K,
        "selection_criterion": "argmax_K max(active_nodes_floor, edge_count_floor)",
        "highest_structure_floor": highest_struct,
        "highest_size_floor": highest_size,
        "highest_floor_any": highest_floor,
        "ref_22_supervised_ceiling": REF_22_CEILING,
    }

    # Supervised probe — stratified both-class (diagnostic)
    print("[apigraph] Stage4 supervised probe …", flush=True)
    eligible = list(split_bundle.eligible)
    strat = _stratified_split(eligible, seed=SEED, test_ratio=0.2)
    # ensure tensors exist for stratified apps
    need = [a.sha256 for a in strat["train"] + strat["test_benign"] + strat["test_malware"]]
    for sha in need:
        if sha not in tensors:
            tensors[sha] = build_graph_tensors(
                sequences[sha], vocab, app=split_bundle.by_sha[sha]
            )
    tr_b = [a.sha256 for a in strat["train"] if a.label == "benign"]
    tr_m = [a.sha256 for a in strat["train"] if a.label == "malware"]
    te_b = [a.sha256 for a in strat["test_benign"]]
    te_m = [a.sha256 for a in strat["test_malware"]]
    results["supervised_probe"] = supervised_probe(tensors, tr_b, tr_m, te_b, te_m)
    for name, block in results["supervised_probe"].items():
        clears = float(block["auc_floor"]) > highest_floor
        block["clears_highest_floor"] = clears

    # OCPool
    print("[apigraph] Stage4 OCPool …", flush=True)
    results["ocpool"] = {}
    for pool in ("add", "mean", "max"):
        row = ocpool(tensors, train_shas, test_b, test_m, pool)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest_floor
        results["ocpool"][pool] = row
        _write_json(out_dir / f"ocpool_{pool}.json", row)

    # GAE dual + random-init
    print("[apigraph] Stage4 GAE dual α=0.2 h=8 …", flush=True)
    gae_rows = []
    gae_rand = []
    for seed in SEEDS:
        print(f"  GAE seed={seed}", flush=True)
        row = run_gae_dual(
            tensors, train_shas, test_b, test_m, seed=seed, trained=True
        )
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest_floor
        gae_rows.append(row)
        _write_json(out_dir / f"gae_seed{seed}.json", row)
        print(f"  GAE-rand seed={seed}", flush=True)
        rrow = run_gae_dual(
            tensors, train_shas, test_b, test_m, seed=seed, trained=False, epochs=0
        )
        rrow["clears_highest_floor"] = float(rrow["auc"]["auc_floor"]) > highest_floor
        gae_rand.append(rrow)
        _write_json(out_dir / f"gae_rand_seed{seed}.json", rrow)

    results["gae_dual"] = {
        "pins": {"alpha": 0.2, "hidden": 8, "epochs": 300, "lr": 0.01, "wd": 0},
        "trained": {
            "per_seed": gae_rows,
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in gae_rows]),
            "auc_raw": _mean_std([r["auc"]["auc"] for r in gae_rows]),
            "directions": [r["auc"]["direction"] for r in gae_rows],
            "clears_highest_floor_any_seed": any(
                r["clears_highest_floor"] for r in gae_rows
            ),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in gae_rows])["mean"]
            )
            > highest_floor,
        },
        "random_init": {
            "per_seed": gae_rand,
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in gae_rand]),
            "auc_raw": _mean_std([r["auc"]["auc"] for r in gae_rand]),
            "directions": [r["auc"]["direction"] for r in gae_rand],
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in gae_rand])["mean"]
            )
            > highest_floor,
        },
    }

    # OCGIN_plus + random-init
    print("[apigraph] Stage4 OCGIN_plus …", flush=True)
    oc_rows = []
    oc_rand = []
    for seed in SEEDS:
        print(f"  OCGIN_plus seed={seed}", flush=True)
        row = run_ocgin_plus(
            tensors, train_shas, test_b, test_m, seed=seed, trained=True
        )
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest_floor
        oc_rows.append(row)
        _write_json(out_dir / f"ocgin_plus_seed{seed}.json", row)
        print(f"  OCGIN_plus-rand seed={seed}", flush=True)
        rrow = run_ocgin_plus(
            tensors, train_shas, test_b, test_m, seed=seed, trained=False, epochs=0
        )
        rrow["clears_highest_floor"] = float(rrow["auc"]["auc_floor"]) > highest_floor
        oc_rand.append(rrow)
        _write_json(out_dir / f"ocgin_plus_rand_seed{seed}.json", rrow)

    results["ocgin_plus"] = {
        "pins": {"hidden": 32, "layers": 4, "epochs": 300, "lr": 0.01, "wd": 0},
        "trained": {
            "per_seed": oc_rows,
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in oc_rows]),
            "auc_raw": _mean_std([r["auc"]["auc"] for r in oc_rows]),
            "directions": [r["auc"]["direction"] for r in oc_rows],
            "n_collapse": int(sum(1 for r in oc_rows if r.get("collapse"))),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in oc_rows])["mean"]
            )
            > highest_floor,
        },
        "random_init": {
            "per_seed": oc_rand,
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in oc_rand]),
            "auc_raw": _mean_std([r["auc"]["auc"] for r in oc_rand]),
            "directions": [r["auc"]["direction"] for r in oc_rand],
            "n_collapse": int(sum(1 for r in oc_rand if r.get("collapse"))),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in oc_rand])["mean"]
            )
            > highest_floor,
        },
    }

    _write_json(out_dir / "stage4_summary.json", results)
    return results


def _fmt_floor(block: dict[str, Any]) -> str:
    return (
        f"{block['auc_floor']:.4f} ({block['direction']}) "
        f"ci95=[{block['ci95_floor'][0]:.4f},{block['ci95_floor'][1]:.4f}]"
    )


def write_summary(
    *,
    out: Path,
    digest: str,
    freq: dict[str, Any],
    coverage: dict[str, Any],
    graph_stats: dict[str, Any],
    floors_by_k: dict[str, Any],
    gate: dict[str, Any],
    stage4: dict[str, Any] | None,
    node_feat_dim: int,
    static_dim: int,
) -> None:
    lines: list[str] = []
    lines.append("# API-level graph representation — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_sha_digest: `{digest}`")
    lines.append("- split: train_benign=562, test_benign=141, test_malware=1700, seed=42")
    lines.append(f"- node_feat_dim: {node_feat_dim}")
    lines.append(f"- static_global_dim: {static_dim}")
    lines.append(f"- vocab_integrity: {VOCAB_SOURCE_ASSERTION}")
    lines.append("")

    lines.append("## Stage 1 — vocabulary (train-benign only)")
    lines.append("")
    fd = freq.get("frequency_distribution", freq)
    lines.append(f"| stat | value |")
    lines.append(f"|---|---|")
    lines.append(f"| distinct_callees | {fd.get('n_distinct_callees')} |")
    lines.append(f"| total_call_events | {fd.get('total_call_events')} |")
    for k, v in (fd.get("document_frequency_thresholds") or {}).items():
        lines.append(f"| callees {k} of apps | {v} |")
    lines.append("")
    lines.append("### Coverage (fraction of call events in vocabulary)")
    lines.append("")
    lines.append("| K | train_benign | test_benign | test_malware |")
    lines.append("|---|---|---|---|")
    for k in sorted(coverage.keys(), key=int):
        row = coverage[k]
        lines.append(
            f"| {k} | {row['train_benign']['coverage_frac']:.4f} | "
            f"{row['test_benign']['coverage_frac']:.4f} | "
            f"{row['test_malware']['coverage_frac']:.4f} |"
        )
    lines.append("")
    lines.append("### OOV rate")
    lines.append("")
    lines.append("| K | train_benign | test_benign | test_malware |")
    lines.append("|---|---|---|---|")
    for k in sorted(coverage.keys(), key=int):
        row = coverage[k]
        lines.append(
            f"| {k} | {row['train_benign']['oov_frac']:.4f} | "
            f"{row['test_benign']['oov_frac']:.4f} | "
            f"{row['test_malware']['oov_frac']:.4f} |"
        )
    lines.append("")

    lines.append("## Stage 2 — graph construction stats")
    lines.append("")
    for k in sorted(graph_stats.keys(), key=int):
        lines.append(f"### K={k}")
        lines.append("")
        lines.append(
            "| partition | active_nodes med (IQR) | edges med (IQR) | "
            "frac edges≤2 | density med |"
        )
        lines.append("|---|---|---|---|---|")
        for part, st in graph_stats[k].items():
            an, ed, dens = st["active_nodes"], st["edges"], st["density"]
            lines.append(
                f"| {part} | {an['median']:.1f} ({an['iqr']:.1f}) | "
                f"{ed['median']:.1f} ({ed['iqr']:.1f}) | "
                f"{st['fraction_graphs_edges_le_2']:.4f} | {dens['median']:.6f} |"
            )
        lines.append("")

    lines.append("## Stage 3 — floors vs 22-node baselines")
    lines.append("")
    lines.append(
        f"| baseline_22 | active_nodes={BASELINE_22['active_nodes']} | "
        f"edge_count/density={BASELINE_22['edge_count']} | "
        f"mapped_event_count={BASELINE_22['mapped_event_count']} |"
    )
    lines.append("")
    lines.append(
        "| K | in_vocab_events | total_events | active_nodes | edge_count | "
        "density | oov_rate |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for k in sorted(floors_by_k.keys(), key=int):
        f = floors_by_k[k]
        lines.append(
            f"| {k} | {f['in_vocab_event_count']['auc_floor']:.4f} | "
            f"{f['total_event_count']['auc_floor']:.4f} | "
            f"{f['active_nodes']['auc_floor']:.4f} | "
            f"{f['edge_count']['auc_floor']:.4f} | "
            f"{f['graph_density']['auc_floor']:.4f} | "
            f"{f['oov_rate']['auc_floor']:.4f} |"
        )
    lines.append("")
    lines.append("### Floor directions / CI")
    lines.append("")
    for k in sorted(floors_by_k.keys(), key=int):
        lines.append(f"**K={k}**")
        for name, block in floors_by_k[k].items():
            lines.append(f"- {name}: {_fmt_floor(block)}")
        lines.append("")

    lines.append("## Gate")
    lines.append("")
    lines.append(f"- threshold: {gate['threshold']}")
    lines.append(f"- verdict: {gate['verdict']}")
    lines.append(f"- continue_to_stage4: {gate['continue_to_stage4']}")
    lines.append("")
    lines.append("| K | active_nodes | edge_count | structurally_moved |")
    lines.append("|---|---|---|---|")
    for k, row in sorted(gate["per_k"].items(), key=lambda kv: int(kv[0])):
        lines.append(
            f"| {k} | {row['active_nodes']:.4f} | {row['edge_count']:.4f} | "
            f"{row['structurally_moved']} |"
        )
    lines.append("")

    if stage4 is None:
        lines.append("## Stage 4 — models")
        lines.append("")
        lines.append("not run (gate STOP)")
        lines.append("")
    else:
        lines.append("## Stage 4 — models")
        lines.append("")
        lines.append(f"- selected_K: {stage4['K']}")
        lines.append(f"- selection_criterion: {stage4['selection_criterion']}")
        lines.append(f"- highest_structure_floor: {stage4['highest_structure_floor']:.4f}")
        lines.append(f"- highest_size_floor: {stage4['highest_size_floor']:.4f}")
        lines.append(f"- highest_floor_any: {stage4['highest_floor_any']:.4f}")
        lines.append(f"- ref_22_supervised_ceiling: {stage4['ref_22_supervised_ceiling']}")
        lines.append("")
        lines.append("### Supervised probe (diagnostic)")
        lines.append("")
        for name, block in stage4["supervised_probe"].items():
            lines.append(
                f"- {name}: auc_floor={block['auc_floor']:.4f} "
                f"({block['direction']}) clears_highest_floor={block['clears_highest_floor']}"
            )
        lines.append("")
        lines.append("### OCPool")
        lines.append("")
        for pool, row in stage4["ocpool"].items():
            a = row["auc"]
            lines.append(
                f"- OCPool_{pool}: auc_floor={a['auc_floor']:.4f} ({a['direction']}) "
                f"clears_highest_floor={row['clears_highest_floor']}"
            )
            leak = row["leak_spearman"]
            lines.append(
                f"  - spearman: inv={leak['in_vocab_events']:.3f} tot={leak['total_events']:.3f} "
                f"act={leak['active_nodes']:.3f} edg={leak['edge_count']:.3f} "
                f"dens={leak['density']:.3f} stat={leak['static_norm']:.3f}"
            )
        lines.append("")
        for tag, key in (("GAE dual trained", "gae_dual"), ("OCGIN_plus trained", "ocgin_plus")):
            block = stage4[key]["trained"]
            ms = block["auc_floor"]
            lines.append(f"### {tag}")
            lines.append("")
            lines.append(
                f"- auc_floor mean±std: {ms['mean']:.4f} ± {ms['std']:.4f} "
                f"values={ms['values']}"
            )
            lines.append(f"- directions: {block['directions']}")
            lines.append(
                f"- clears_highest_floor_mean: {block['clears_highest_floor_mean']}"
            )
            if "n_collapse" in block:
                lines.append(f"- n_collapse: {block['n_collapse']}")
            lines.append("")
            rand = stage4[key]["random_init"]
            rms = rand["auc_floor"]
            lines.append(f"### {tag.split()[0]} random-init")
            lines.append("")
            lines.append(
                f"- auc_floor mean±std: {rms['mean']:.4f} ± {rms['std']:.4f} "
                f"values={rms['values']}"
            )
            lines.append(f"- directions: {rand['directions']}")
            lines.append(
                f"- clears_highest_floor_mean: {rand['clears_highest_floor_mean']}"
            )
            lines.append("")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[apigraph] wrote {out / 'SUMMARY.md'}", flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="API-level graph representation experiment")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=APIGRAPH_OUTPUT_ROOT,
        help="Output root (default: abrg/output/androct_2017/apigraph)",
    )
    p.add_argument("--force-extract", action="store_true")
    p.add_argument(
        "--skip-stage4",
        action="store_true",
        help="Force skip Stage 4 even if gate passes",
    )
    args = p.parse_args(argv)

    out: Path = args.output_dir
    vocab_dir = out / "vocab"
    graphs_dir = out / "graphs"
    floors_dir = out / "floors"
    models_dir = out / "models"
    for d in (vocab_dir, graphs_dir, floors_dir, models_dir):
        d.mkdir(parents=True, exist_ok=True)

    print("[apigraph] Stage 0 — split assert", flush=True)
    bundle = load_run3_split()
    train_shas = [a.sha256 for a in bundle.train]
    test_b_shas = [a.sha256 for a in bundle.test_benign]
    test_m_shas = [a.sha256 for a in bundle.test_malware]
    all_apps = bundle.train + bundle.test_benign + bundle.test_malware

    print("[apigraph] Stage 1 — extract sequences", flush=True)
    sequences = extract_sequences(all_apps, force=args.force_extract)

    train_benign_seqs = {s: sequences[s] for s in train_shas}
    assert set(train_benign_seqs) == set(train_shas)
    assert len(train_benign_seqs) == 562
    # Integrity: no malware / test benign in ranking input
    for s in test_b_shas + test_m_shas:
        assert s not in train_benign_seqs or s in train_shas

    print("[apigraph] Stage 1 — TF-IDF vocabularies", flush=True)
    vocab_meta = build_vocabularies(
        train_benign_seqs, train_shas, ks=VOCAB_KS, out_dir=vocab_dir
    )
    partitions = {
        "train_benign": train_shas,
        "test_benign": test_b_shas,
        "test_malware": test_m_shas,
    }
    coverage = coverage_table(vocab_meta["vocabs"], sequences, partitions)
    _write_json(vocab_dir / "coverage.json", coverage)
    # CSV coverage
    with (vocab_dir / "coverage.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "K",
                "partition",
                "in_vocab_events",
                "total_events",
                "coverage_frac",
                "oov_frac",
            ]
        )
        for k, parts in coverage.items():
            for part, row in parts.items():
                w.writerow(
                    [
                        k,
                        part,
                        row["in_vocab_events"],
                        row["total_events"],
                        f"{row['coverage_frac']:.6f}",
                        f"{row['oov_frac']:.6f}",
                    ]
                )

    # OOV class gap prominence
    for k, parts in coverage.items():
        tb = parts["train_benign"]["coverage_frac"]
        tm = parts["test_malware"]["coverage_frac"]
        gap = tb - tm
        print(
            f"[apigraph] coverage K={k} train_b={tb:.4f} test_m={tm:.4f} gap={gap:.4f}",
            flush=True,
        )

    floors_by_k: dict[str, Any] = {}
    graph_stats: dict[str, Any] = {}
    tensors_by_k: dict[int, dict[str, dict[str, Any]]] = {}

    for K in VOCAB_KS:
        print(f"[apigraph] Stage 2 — construct K={K}", flush=True)
        vocab = vocab_meta["vocabs"][str(K)]
        tensors = _build_tensors_for_k(
            K=K,
            vocab=vocab,
            sequences=sequences,
            by_sha=bundle.by_sha,
            shas=train_shas + test_b_shas + test_m_shas,
        )
        tensors_by_k[K] = tensors
        stats = construction_stats(tensors, partitions)
        graph_stats[str(K)] = stats
        _write_json(graphs_dir / f"K{K}_stats.json", stats)
        # light meta (not full tensors)
        meta = {
            "K": K,
            "node_feat_dim": NODE_FEAT_DIM,
            "static_global_dim": STATIC_GLOBAL_DIM,
            "n_graphs": len(tensors),
        }
        _write_json(graphs_dir / f"K{K}_meta.json", meta)

        print(f"[apigraph] Stage 3 — floors K={K}", flush=True)
        floors = compute_floors(tensors, test_b_shas, test_m_shas)
        floors_by_k[str(K)] = floors
        _write_json(floors_dir / f"K{K}_floors.json", floors)

    gate = gate_decision(floors_by_k)
    _write_json(floors_dir / "gate.json", gate)
    print(f"[apigraph] GATE: {gate['verdict']}", flush=True)

    stage4 = None
    if gate["continue_to_stage4"] and not args.skip_stage4:
        best_k = _pick_best_k(gate)
        assert best_k is not None
        print(f"[apigraph] Stage 4 — models on K={best_k}", flush=True)
        stage4 = _run_stage4(
            K=best_k,
            tensors=tensors_by_k[best_k],
            split_bundle=bundle,
            sequences=sequences,
            vocab=vocab_meta["vocabs"][str(best_k)],
            floors=floors_by_k[str(best_k)],
            out_dir=models_dir / f"K{best_k}",
        )
    elif not gate["continue_to_stage4"]:
        print("[apigraph] Stage 4 skipped (structural gate STOP)", flush=True)

    write_summary(
        out=out,
        digest=bundle.sha_list_digest,
        freq=vocab_meta,
        coverage=coverage,
        graph_stats=graph_stats,
        floors_by_k=floors_by_k,
        gate=gate,
        stage4=stage4,
        node_feat_dim=NODE_FEAT_DIM,
        static_dim=STATIC_GLOBAL_DIM,
    )
    _write_json(
        out / "run_meta.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "sha_list_digest": bundle.sha_list_digest,
            "gate": gate,
            "stage4_ran": stage4 is not None,
            "node_feat_dim": NODE_FEAT_DIM,
            "static_global_dim": STATIC_GLOBAL_DIM,
        },
    )


if __name__ == "__main__":
    main()
