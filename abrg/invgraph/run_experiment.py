"""Orchestrate invgraph Stages 1–3; Stage 4 only if edge gate passes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from abrg.apigraph.models_stage4 import ocpool, run_gae_dual, run_ocgin_plus
from abrg.invgraph import (
    BASELINE_EDGE,
    B_DOCFREQ_VOCAB_CSV,
    INVGRAPH_OUTPUT_ROOT,
    SEEDS,
    V3_LOOKBACK,
)
from abrg.invgraph.construct import (
    NODE_FEAT_DIM,
    Variant,
    build_variant_tensors,
    construction_stats,
)
from abrg.invgraph.extract import (
    CALLER_DISCARD_SITES,
    ICC_DECISION,
    extract_invocation_pairs,
    load_b_docfreq_vocab,
)
from abrg.invgraph.floors import (
    check_v1_reproduces,
    compute_floors,
    gate_decision,
    pick_best_variant,
)
from abrg.invgraph.split import load_split_or_stop
from abrg.invgraph.stage1 import stage1_inventory

VARIANTS: tuple[Variant, ...] = (
    "V1_proximity",
    "V2_invocation",
    "V3_invocation_projected",
)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(o: Any) -> Any:
        if isinstance(o, frozenset):
            return sorted(list(o))
        if isinstance(o, set):
            return sorted(list(o))
        raise TypeError(type(o))

    path.write_text(json.dumps(obj, indent=2, default=_default) + "\n", encoding="utf-8")


def _mean_std(vals: list[float]) -> dict[str, float]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(arr)) if len(arr) else float("nan"),
        "std": float(np.nanstd(arr, ddof=0)) if len(arr) else float("nan"),
        "values": [float(v) for v in vals],
    }


def _strip_heavy(t: dict[str, Any]) -> dict[str, Any]:
    """Drop non-serialisable / heavy keys before any accidental dump."""
    out = {k: v for k, v in t.items() if k != "unique_edge_keys"}
    return out


def _build_all(
    pairs: dict[str, list[tuple[str, str]]],
    vocab: list[str],
    by_sha: dict[str, Any],
    shas: list[str],
    variant: Variant,
) -> dict[str, dict[str, Any]]:
    tensors: dict[str, dict[str, Any]] = {}
    for i, sha in enumerate(shas):
        tensors[sha] = build_variant_tensors(pairs[sha], vocab, app=by_sha[sha], variant=variant)
        if (i + 1) % 500 == 0:
            print(f"  … {variant} {i+1}/{len(shas)}", flush=True)
    return tensors


def _run_stage4(
    *,
    variant: str,
    tensors: dict[str, dict[str, Any]],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    floors: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    highest = max(float(floors[k]["auc_floor"]) for k in floors)
    results: dict[str, Any] = {
        "variant": variant,
        "highest_floor": highest,
        "floors": floors,
    }

    # OCPool control — edge-free; should match across variants if only edges differ
    print("[invgraph] Stage4 OCPool …", flush=True)
    results["ocpool"] = {}
    for pool in ("add", "mean", "max"):
        row = ocpool(tensors, train_shas, test_b, test_m, pool)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest
        results["ocpool"][pool] = row
        _write_json(out_dir / f"ocpool_{pool}.json", row)

    print("[invgraph] Stage4 GAE …", flush=True)
    gae_tr, gae_rand = [], []
    for seed in SEEDS:
        print(f"  GAE seed={seed}", flush=True)
        row = run_gae_dual(tensors, train_shas, test_b, test_m, seed=seed, trained=True)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest
        gae_tr.append(row)
        _write_json(out_dir / f"gae_seed{seed}.json", row)
        rrow = run_gae_dual(
            tensors, train_shas, test_b, test_m, seed=seed, trained=False, epochs=0
        )
        rrow["clears_highest_floor"] = float(rrow["auc"]["auc_floor"]) > highest
        gae_rand.append(rrow)
        _write_json(out_dir / f"gae_rand_seed{seed}.json", rrow)

    results["gae_dual"] = {
        "trained": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in gae_tr]),
            "directions": [r["auc"]["direction"] for r in gae_tr],
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in gae_tr])["mean"]
            )
            > highest,
            "leak_spearman_mean": {
                k: float(np.mean([r["leak_spearman"][k] for r in gae_tr]))
                for k in gae_tr[0]["leak_spearman"]
            },
            "per_seed": gae_tr,
        },
        "random_init": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in gae_rand]),
            "directions": [r["auc"]["direction"] for r in gae_rand],
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in gae_rand])["mean"]
            )
            > highest,
            "per_seed": gae_rand,
        },
    }

    print("[invgraph] Stage4 OCGIN_plus …", flush=True)
    oc_tr, oc_rand = [], []
    for seed in SEEDS:
        print(f"  OCGIN_plus seed={seed}", flush=True)
        row = run_ocgin_plus(tensors, train_shas, test_b, test_m, seed=seed, trained=True)
        row["clears_highest_floor"] = float(row["auc"]["auc_floor"]) > highest
        oc_tr.append(row)
        _write_json(out_dir / f"ocgin_plus_seed{seed}.json", row)
        rrow = run_ocgin_plus(
            tensors, train_shas, test_b, test_m, seed=seed, trained=False, epochs=0
        )
        rrow["clears_highest_floor"] = float(rrow["auc"]["auc_floor"]) > highest
        oc_rand.append(rrow)
        _write_json(out_dir / f"ocgin_plus_rand_seed{seed}.json", rrow)

    results["ocgin_plus"] = {
        "trained": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in oc_tr]),
            "directions": [r["auc"]["direction"] for r in oc_tr],
            "n_collapse": int(sum(1 for r in oc_tr if r.get("collapse"))),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in oc_tr])["mean"]
            )
            > highest,
            "leak_spearman_mean": {
                k: float(np.mean([r["leak_spearman"][k] for r in oc_tr]))
                for k in oc_tr[0]["leak_spearman"]
            },
            "per_seed": oc_tr,
        },
        "random_init": {
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in oc_rand]),
            "directions": [r["auc"]["direction"] for r in oc_rand],
            "n_collapse": int(sum(1 for r in oc_rand if r.get("collapse"))),
            "clears_highest_floor_mean": float(
                _mean_std([r["auc"]["auc_floor"] for r in oc_rand])["mean"]
            )
            > highest,
            "per_seed": oc_rand,
        },
    }
    _write_json(out_dir / "stage4_summary.json", results)
    return results


def write_summary(
    *,
    out: Path,
    digest: str,
    stage1: dict[str, Any],
    stats_by_v: dict[str, Any],
    floors_by_v: dict[str, Any],
    v1_check: dict[str, Any],
    gate: dict[str, Any],
    stage4: dict[str, Any] | None,
    ocpool_all_variants: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# Invocation-graph representation — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_sha_digest: `{digest}`")
    lines.append("- split: 562 / 141 / 1700 seed=42")
    lines.append(f"- node_feat_dim: {NODE_FEAT_DIM} (asserted 25)")
    lines.append("- vocab: B_docfreq K=1000 (reused verbatim from apigraph/vocab_control)")
    lines.append(f"- V3_lookback: {V3_LOOKBACK}")
    lines.append("")

    # Stage 5 table FIRST
    lines.append("## Stage 5 — edge definition × floors / OCPool / trained GNN")
    lines.append("")
    lines.append(
        "| edge definition | edge_count | density | active_nodes | "
        "OCPool_mean | best trained GNN |"
    )
    lines.append("|---|---|---|---|---|---|")
    for v in VARIANTS:
        f = floors_by_v[v]
        oc = ocpool_all_variants.get(v, {})
        oc_m = oc.get("mean", {}).get("auc", {}).get("auc_floor", float("nan"))
        gnn = "—"
        if stage4 and stage4.get("variant") == v:
            gae_m = stage4["gae_dual"]["trained"]["auc_floor"]["mean"]
            ocg_m = stage4["ocgin_plus"]["trained"]["auc_floor"]["mean"]
            best = max(gae_m, ocg_m)
            tag = "GAE" if gae_m >= ocg_m else "OCGIN_plus"
            gnn = f"{best:.4f} ({tag})"
        elif stage4 is None:
            gnn = "not run"
        lines.append(
            f"| {v} | {f['edge_count']['auc_floor']:.4f} | "
            f"{f['graph_density']['auc_floor']:.4f} | "
            f"{f['active_nodes']['auc_floor']:.4f} | "
            f"{oc_m if oc_m == oc_m else float('nan'):.4f} | {gnn} |"
        )
    lines.append("")
    lines.append(
        f"baselines: 22-node edge={BASELINE_EDGE['22node']} · "
        f"API-1000 edge={BASELINE_EDGE['api1000_tfidf']} · "
        f"B_docfreq edge={BASELINE_EDGE['B_docfreq']}"
    )
    lines.append("")

    lines.append("## Stage 1 — caller discard + ICC")
    lines.append("")
    lines.append(f"- icc_decision: {ICC_DECISION}")
    lines.append("- caller previously discarded at:")
    for s in CALLER_DISCARD_SITES:
        lines.append(f"  - `{s['path']}` :: `{s['symbol']}` — {s['detail']}")
    lines.append("")
    lines.append(
        f"| distinct callers | {stage1['n_distinct_callers']} | "
        f"callees | {stage1['n_distinct_callees']} | "
        f"pairs | {stage1['n_distinct_pairs']} |"
    )
    lines.append("")
    lines.append("| caller class | count | frac |")
    lines.append("|---|---|---|")
    for k, c in stage1["caller_class_counts"].items():
        lines.append(f"| {k} | {c} | {stage1['caller_class_frac'][k]:.4f} |")
    lines.append("")
    lines.append(
        f"- caller out-degree med (IQR): "
        f"{stage1['caller_out_degree']['median']:.1f} ({stage1['caller_out_degree']['iqr']:.1f})"
    )
    lines.append(
        f"- callee in-degree med (IQR): "
        f"{stage1['callee_in_degree']['median']:.1f} ({stage1['callee_in_degree']['iqr']:.1f})"
    )
    lines.append("")
    lines.append("### Top 30 library prefixes")
    lines.append("")
    lines.append("| prefix | count |")
    lines.append("|---|---|")
    for row in stage1["top30_library_prefixes"]:
        lines.append(f"| {row['prefix']} | {row['count']} |")
    lines.append("")

    lines.append("## Stage 2 — construction stats")
    lines.append("")
    for v in VARIANTS:
        st = stats_by_v[v]
        lines.append(f"### {v}")
        lines.append("")
        lines.append(f"- corpus_n_distinct_edges: {st['corpus_n_distinct_edges']}")
        lines.append(
            "| partition | edges med (IQR) | dens med | frac≤2 | "
            "out-deg med | in-deg med |"
        )
        lines.append("|---|---|---|---|---|---|")
        for part in ("train_benign", "test_benign", "test_malware"):
            p = st[part]
            lines.append(
                f"| {part} | {p['edges']['median']:.1f} ({p['edges']['iqr']:.1f}) | "
                f"{p['density']['median']:.6f} | {p['fraction_graphs_edges_le_2']:.4f} | "
                f"{p['mean_out_degree_active']['median']:.2f} | "
                f"{p['mean_in_degree_active']['median']:.2f} |"
            )
        if "drop_rate" in st.get("test_malware", {}):
            lines.append("")
            lines.append(
                "| partition | V2 drop_rate med |"
            )
            lines.append("|---|---|")
            for part in ("train_benign", "test_benign", "test_malware"):
                if "drop_rate" in st[part]:
                    lines.append(
                        f"| {part} | {st[part]['drop_rate']['median']:.4f} |"
                    )
        if "n_projected_edges" in st.get("test_malware", {}):
            lines.append("")
            lines.append("| partition | n_v2_style med | n_projected med |")
            lines.append("|---|---|---|")
            for part in ("train_benign", "test_benign", "test_malware"):
                lines.append(
                    f"| {part} | {st[part]['n_v2_style_edges']['median']:.1f} | "
                    f"{st[part]['n_projected_edges']['median']:.1f} |"
                )
        lines.append("")

    lines.append("## Stage 3 — floors")
    lines.append("")
    lines.append(
        "| variant | edge_count | density | active_nodes | in_vocab | total | oov |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        f = floors_by_v[v]
        lines.append(
            f"| {v} | {f['edge_count']['auc_floor']:.4f} | "
            f"{f['graph_density']['auc_floor']:.4f} | "
            f"{f['active_nodes']['auc_floor']:.4f} | "
            f"{f['in_vocab_events']['auc_floor']:.4f} | "
            f"{f['total_events']['auc_floor']:.4f} | "
            f"{f['oov_rate']['auc_floor']:.4f} |"
        )
    lines.append("")
    lines.append("### Directions / CI")
    lines.append("")
    for v in VARIANTS:
        lines.append(f"**{v}**")
        for name, block in floors_by_v[v].items():
            lines.append(
                f"- {name}: {block['auc_floor']:.4f} ({block['direction']}) "
                f"ci95=[{block['ci95_floor'][0]:.4f},{block['ci95_floor'][1]:.4f}]"
            )
        lines.append("")

    lines.append("## V1 control check")
    lines.append("")
    lines.append(f"- {v1_check['message']}")
    lines.append(
        f"- v1_edge_floor={v1_check['v1_edge_floor']:.4f} "
        f"target={v1_check['target']} tol={v1_check['tol']}"
    )
    lines.append("")

    lines.append("## Gate")
    lines.append("")
    lines.append(f"- verdict: **{gate['verdict']}**")
    lines.append(f"- continue_to_stage4: {gate['continue_to_stage4']}")
    lines.append(f"- threshold: {gate['threshold']}")
    for name, row in gate.get("per_variant_v2_v3", {}).items():
        lines.append(
            f"- {name}: edge={row['edge_count']:.4f} dens={row['graph_density']:.4f} "
            f"moved_ge_0.60={row['moved_ge_0.60']}"
        )
    lines.append("")

    lines.append("## OCPool across variants (edge-free control)")
    lines.append("")
    lines.append("| variant | add | mean | max |")
    lines.append("|---|---|---|---|")
    for v in VARIANTS:
        oc = ocpool_all_variants[v]
        lines.append(
            f"| {v} | {oc['add']['auc']['auc_floor']:.4f} | "
            f"{oc['mean']['auc']['auc_floor']:.4f} | "
            f"{oc['max']['auc']['auc_floor']:.4f} |"
        )
    lines.append("")

    if stage4 is None:
        lines.append("## Stage 4 — models")
        lines.append("")
        lines.append("not run (gate STOP)")
        lines.append("")
    else:
        lines.append(f"## Stage 4 — models on `{stage4['variant']}`")
        lines.append("")
        lines.append(f"- highest_floor: {stage4['highest_floor']:.4f}")
        for pool, row in stage4["ocpool"].items():
            lines.append(
                f"- OCPool_{pool}: {row['auc']['auc_floor']:.4f} "
                f"({row['auc']['direction']}) clears={row['clears_highest_floor']}"
            )
        for tag, key in (("GAE trained", "gae_dual"), ("OCGIN_plus trained", "ocgin_plus")):
            block = stage4[key]["trained"]
            ms = block["auc_floor"]
            lines.append(
                f"- {tag}: {ms['mean']:.4f} ± {ms['std']:.4f} "
                f"clears_mean={block['clears_highest_floor_mean']} "
                f"dirs={block['directions']}"
            )
            if "leak_spearman_mean" in block:
                lk = block["leak_spearman_mean"]
                lines.append(
                    f"  - spearman: inv={lk['in_vocab_events']:.3f} "
                    f"tot={lk['total_events']:.3f} act={lk['active_nodes']:.3f} "
                    f"edg={lk['edge_count']:.3f} dens={lk['density']:.3f} "
                    f"stat={lk['static_norm']:.3f}"
                )
            rand = stage4[key]["random_init"]
            rms = rand["auc_floor"]
            lines.append(
                f"- {tag.split()[0]} random-init: {rms['mean']:.4f} ± {rms['std']:.4f} "
                f"clears_mean={rand['clears_highest_floor_mean']}"
            )
        lines.append("")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[invgraph] wrote {out / 'SUMMARY.md'}", flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Invocation-graph edge-definition experiment")
    p.add_argument("--output-dir", type=Path, default=INVGRAPH_OUTPUT_ROOT)
    p.add_argument("--force-extract", action="store_true")
    p.add_argument("--skip-stage4", action="store_true")
    args = p.parse_args(argv)

    out: Path = args.output_dir
    stage1_dir = out / "stage1_edges"
    var_dir = out / "variants"
    floors_dir = out / "floors"
    models_dir = out / "models"
    for d in (stage1_dir, var_dir, floors_dir, models_dir):
        d.mkdir(parents=True, exist_ok=True)

    bundle = load_split_or_stop()
    train_shas = [a.sha256 for a in bundle.train]
    test_b = [a.sha256 for a in bundle.test_benign]
    test_m = [a.sha256 for a in bundle.test_malware]
    all_apps = bundle.train + bundle.test_benign + bundle.test_malware
    all_shas = train_shas + test_b + test_m
    partitions = {
        "train_benign": train_shas,
        "test_benign": test_b,
        "test_malware": test_m,
    }

    if not B_DOCFREQ_VOCAB_CSV.is_file():
        raise SystemExit(f"STOP: missing B_docfreq vocab at {B_DOCFREQ_VOCAB_CSV}")
    vocab = load_b_docfreq_vocab(B_DOCFREQ_VOCAB_CSV)
    assert NODE_FEAT_DIM == 25

    print("[invgraph] extract invocation pairs", flush=True)
    pairs = extract_invocation_pairs(all_apps, force=args.force_extract)

    print("[invgraph] Stage 1 inventory", flush=True)
    train_pairs = {s: pairs[s] for s in train_shas}
    stage1 = stage1_inventory(train_pairs, train_shas, out_dir=stage1_dir)
    _write_json(stage1_dir / "caller_discard_and_icc.json", {
        "caller_discard_sites": CALLER_DISCARD_SITES,
        "icc_decision": ICC_DECISION,
    })

    floors_by_v: dict[str, Any] = {}
    stats_by_v: dict[str, Any] = {}
    tensors_by_v: dict[str, dict[str, dict[str, Any]]] = {}

    for variant in VARIANTS:
        print(f"[invgraph] Stage 2 construct {variant}", flush=True)
        tensors = _build_all(pairs, vocab, bundle.by_sha, all_shas, variant)
        # assert node features identical across variants for a sample sha
        tensors_by_v[variant] = tensors
        stats = construction_stats(tensors, partitions)
        # serialisable stats only
        stats_ser = json.loads(json.dumps(stats, default=lambda o: list(o) if isinstance(o, (set, frozenset)) else o))
        stats_by_v[variant] = stats_ser
        _write_json(var_dir / f"{variant}_stats.json", stats_ser)

        print(f"[invgraph] Stage 3 floors {variant}", flush=True)
        floors = compute_floors(tensors, test_b, test_m)
        floors_by_v[variant] = floors
        _write_json(floors_dir / f"{variant}_floors.json", floors)
        print(
            f"  edge_count={floors['edge_count']['auc_floor']:.4f} "
            f"density={floors['graph_density']['auc_floor']:.4f}",
            flush=True,
        )

    # Feature identity check: V1 vs V2 x tensors must match
    sample = all_shas[0]
    x1 = tensors_by_v["V1_proximity"][sample]["x"]
    x2 = tensors_by_v["V2_invocation"][sample]["x"]
    x3 = tensors_by_v["V3_invocation_projected"][sample]["x"]
    if not (bool((x1 == x2).all()) and bool((x1 == x3).all())):
        raise SystemExit("STOP: node features differ across variants — axis broken")
    print("[invgraph] node-feature identity across variants: OK", flush=True)

    v1_check = check_v1_reproduces(floors_by_v["V1_proximity"])
    _write_json(floors_dir / "v1_control_check.json", v1_check)
    print(f"[invgraph] {v1_check['message']}", flush=True)
    if not v1_check["ok"]:
        write_summary(
            out=out,
            digest=bundle.sha_list_digest,
            stage1=stage1,
            stats_by_v=stats_by_v,
            floors_by_v=floors_by_v,
            v1_check=v1_check,
            gate={"verdict": "STOP — V1 control failed", "continue_to_stage4": False, "threshold": None, "per_variant_v2_v3": {}},
            stage4=None,
            ocpool_all_variants={},
        )
        raise SystemExit(v1_check["message"])

    gate = gate_decision(floors_by_v)
    _write_json(floors_dir / "gate.json", gate)
    print(f"[invgraph] GATE: {gate['verdict']}", flush=True)

    # OCPool on all variants (edge-free control) — always, cheap vs GAE
    print("[invgraph] OCPool all variants (control)", flush=True)
    ocpool_all: dict[str, Any] = {}
    for variant in VARIANTS:
        tensors = tensors_by_v[variant]
        ocpool_all[variant] = {
            pool: ocpool(tensors, train_shas, test_b, test_m, pool)
            for pool in ("add", "mean", "max")
        }
        _write_json(var_dir / f"{variant}_ocpool.json", ocpool_all[variant])

    stage4 = None
    if gate["continue_to_stage4"] and not args.skip_stage4:
        best = pick_best_variant(floors_by_v)
        print(f"[invgraph] Stage 4 on {best}", flush=True)
        stage4 = _run_stage4(
            variant=best,
            tensors=tensors_by_v[best],
            train_shas=train_shas,
            test_b=test_b,
            test_m=test_m,
            floors=floors_by_v[best],
            out_dir=models_dir / best,
        )
    else:
        print("[invgraph] Stage 4 skipped", flush=True)

    write_summary(
        out=out,
        digest=bundle.sha_list_digest,
        stage1=stage1,
        stats_by_v=stats_by_v,
        floors_by_v=floors_by_v,
        v1_check=v1_check,
        gate=gate,
        stage4=stage4,
        ocpool_all_variants=ocpool_all,
    )
    _write_json(
        out / "run_meta.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "sha_list_digest": bundle.sha_list_digest,
            "gate": gate,
            "v1_check": v1_check,
            "stage4_ran": stage4 is not None,
            "V3_lookback": V3_LOOKBACK,
            "node_feat_dim": NODE_FEAT_DIM,
        },
    )


if __name__ == "__main__":
    main()
