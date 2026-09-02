"""Orchestrate GLocalKD experiment on T22 + T1K."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from abrg.glocalkd import (
    BATCH_SIZE,
    EPOCHS,
    GLOCALKD_OUTPUT_ROOT,
    IMPLEMENTATION,
    LOSS_MODES,
    NESTED_B,
    NESTED_B_FULL,
    OCPOOL_MEAN_RAW,
    POOLINGS,
    REF_COMMIT,
    REF_ROWS,
    SCORE_VARIANTS,
    SEEDS,
    SIZE_FLOOR,
)
from abrg.glocalkd.bootstrap import nested_bootstrap
from abrg.glocalkd.data import covariates_for, make_loader
from abrg.glocalkd.degeneracy import diagnose
from abrg.glocalkd.explain import node_deviation_table
from abrg.glocalkd.score import eval_scores, score_graphs
from abrg.glocalkd.train import LossMode, train_glocalkd
from abrg.kernels.load import load_bundle


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _mean_std(vals: list[float]) -> dict[str, Any]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(arr)) if len(arr) else float("nan"),
        "std": float(np.nanstd(arr, ddof=0)) if len(arr) else float("nan"),
        "values": [float(v) for v in vals],
    }


def run_one(
    *,
    kind: str,
    tensors: dict[str, dict[str, Any]],
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    pooling: str,
    loss_mode: LossMode,
    seed: int,
    trained: bool,
    out_dir: Path,
    device: torch.device,
    tag: str,
    epochs: int = EPOCHS,
) -> dict[str, Any]:
    in_dim = int(tensors[train[0]]["x"].shape[1])
    eval_ids = test_b + test_m
    labels = [0] * len(test_b) + [1] * len(test_m)
    cov = covariates_for(tensors, eval_ids, kind=kind)

    t0 = time.perf_counter()
    from abrg.glocalkd.config import BRIEF

    brief = BRIEF
    if epochs != BRIEF.epochs:
        from dataclasses import replace

        brief = replace(brief, epochs=epochs)
    target, predictor, tot_c, node_c, graph_c = train_glocalkd(
        tensors=tensors,
        train_shas=train,
        in_dim=in_dim,
        pooling=pooling,  # type: ignore[arg-type]
        seed=seed,
        loss_mode=loss_mode,
        profile=brief,
        trained=trained,
        device=device,
    )
    train_time = time.perf_counter() - t0

    train_loader = make_loader(tensors, train, batch_size=BATCH_SIZE, shuffle=False)
    eval_loader = make_loader(tensors, eval_ids, batch_size=BATCH_SIZE, shuffle=False)
    deg = diagnose(
        target=target,
        predictor=predictor,
        train_loader=train_loader,
        loss_curve=tot_c if trained else [],
        device=device,
    )
    scored = score_graphs(
        target, predictor, eval_loader, device, shas_in_order=eval_ids
    )

    score_results: dict[str, Any] = {}
    for variant in SCORE_VARIANTS:
        row = eval_scores(scored[variant], labels, cov)
        if deg["DEGENERATE"] and trained:
            row["auc_suppressed"] = True
            row["note"] = "DEGENERATE — AUC not a result"
        score_results[variant] = row

    # node scores split
    node_tb = scored["per_graph_node_scores"][: len(test_b)]
    node_tm = scored["per_graph_node_scores"][len(test_b) :]

    payload = {
        "tag": tag,
        "kind": kind,
        "pooling": pooling,
        "loss_mode": loss_mode if trained else "untrained",
        "trained": trained,
        "seed": seed,
        "in_dim": in_dim,
        "train_wall_sec": train_time,
        "epochs": epochs if trained else 0,
        "degeneracy": {
            k: v
            for k, v in deg.items()
            if k != "loss" or True
        },
        "scores": score_results,
        "primary": score_results["s_graph"],
    }
    # shrink loss curve in degeneracy file separately
    deg_out = dict(deg)
    _write_json(out_dir / "degeneracy" / f"{tag}.json", deg_out)
    # store run without full curve duplication in scores file
    run_slim = dict(payload)
    if "degeneracy" in run_slim and "loss" in run_slim["degeneracy"]:
        run_slim["degeneracy"] = {
            **run_slim["degeneracy"],
            "loss": {
                k: v
                for k, v in run_slim["degeneracy"]["loss"].items()
                if k != "curve"
            },
        }
    _write_json(out_dir / "runs" / f"{tag}.json", run_slim)

    return {
        **payload,
        "node_scores_tb": node_tb,
        "node_scores_tm": node_tm,
        "loss_curve": tot_c,
    }


def write_summary(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    deg_flags: list[dict[str, Any]],
    winner: dict[str, Any] | None,
    ablation_rows: list[dict[str, Any]],
    explain: dict[str, Any] | None,
    nested: dict[str, Any] | None,
    digest: str,
) -> None:
    lines: list[str] = []
    lines.append("# GLocalKD — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_digest: `{digest[:16]}…` (562/141/1700)")
    lines.append(f"- implementation: {IMPLEMENTATION}")
    lines.append(f"- reference_commit: `{REF_COMMIT}`")
    lines.append(
        "- layer_spec: GCNConv(in→128)+ReLU → GCNConv(128→128)+ReLU → GCNConv(128→128); "
        "readout ∈ {mean, add, max}; loss L=L_node+L_graph (equal weight, reference)"
    )
    lines.append(f"- train: epochs={EPOCHS} lr=0.01 wd=0 Adam batch={BATCH_SIZE}")
    lines.append("")
    lines.append("## Degeneracy flags (first)")
    lines.append("")
    lines.append("| tag | DEGENERATE | target_const | pred_const | loss_collapsed | near_zero_frac |")
    lines.append("|---|---|---|---|---|---:|")
    for d in deg_flags:
        f = d["flags"]
        lines.append(
            f"| {d['tag']} | {d['DEGENERATE']} | {f['target_near_constant']} | "
            f"{f['predictor_near_constant']} | {f['loss_collapsed']} | "
            f"{d.get('frac_near_zero', float('nan')):.4f} |"
        )
    n_deg = sum(1 for d in deg_flags if d["DEGENERATE"])
    lines.append("")
    lines.append(f"- degenerate_runs: {n_deg} / {len(deg_flags)}")
    lines.append("")
    lines.append("## Reference rows (fixed)")
    lines.append("")
    lines.append(
        "| OCPool raw | OCPool R2 | R2 nested CI | centroid | rand GAE | GAE | OCGIN+ | "
        "WL_h3 | WL struct | mapped floor | HGB full | HGB adj |"
    )
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| {REF_ROWS['OCPool_mean_raw']} | {REF_ROWS['OCPool_mean_R2']} | "
        f"{REF_ROWS['OCPool_mean_R2_nested_CI']} | {REF_ROWS['input_centroid']} | "
        f"{REF_ROWS['random_init_GAE']} | {REF_ROWS['GAE']} | {REF_ROWS['OCGIN_plus']} | "
        f"{REF_ROWS['WL_h3_kernel']} | {REF_ROWS['WL_structure_only']} | "
        f"{REF_ROWS['size_floor_mapped_events']} | {REF_ROWS['supervised_HGB_full']} | "
        f"{REF_ROWS['supervised_HGB_adj_only']} |"
    )
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(
        f"(a) size floor **{SIZE_FLOOR}** · (b) OCPool_mean **{OCPOOL_MEAN_RAW}** · "
        "¬(a) ⇒ not a result. DEGENERATE ⇒ AUC suppressed."
    )
    lines.append("")
    lines.append("## Results grid (trained full loss)")
    lines.append("")
    lines.append(
        "| kind | pool | score | seed | auc | auc_floor | dir | ci95_floor | "
        "clears_(a) | clears_(b) | DEGENERATE | ρ_mapped | ρ_total | ρ_active | ρ_edges | ρ_dens | ρ_static |"
    )
    lines.append(
        "|---|---|---|---:|---:|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---:|"
    )
    for r in rows:
        if r.get("loss_mode") != "full" or not r.get("trained", True):
            continue
        sp = r.get("leak_spearman") or {}
        g = r["gate"]
        lines.append(
            f"| {r['kind']} | {r['pooling']} | {r['score_variant']} | {r['seed']} | "
            f"{r['auc']:.4f} | {r['auc_floor']:.4f} | {r['direction']} | {r['ci95_floor']} | "
            f"{g['clears_size_floor_0.7025']} | {g['clears_OCPool_mean_0.7765']} | "
            f"{r.get('DEGENERATE')} | "
            f"{sp.get('mapped_events', float('nan')):.3f} | "
            f"{sp.get('total_events', float('nan')):.3f} | "
            f"{sp.get('active_nodes', float('nan')):.3f} | "
            f"{sp.get('edge_count', float('nan')):.3f} | "
            f"{sp.get('density', float('nan')):.3f} | "
            f"{sp.get('static_norm', float('nan')):.3f} |"
        )

    lines.append("")
    lines.append("## Aggregate (full · s_graph · non-degenerate seeds)")
    lines.append("")
    lines.append("| kind | pool | auc_floor mean±std | n_seeds | clears_(a) any |")
    lines.append("|---|---|---:|---:|---|")
    from collections import defaultdict

    groups: dict[tuple, list[float]] = defaultdict(list)
    clears: dict[tuple, bool] = defaultdict(bool)
    for r in rows:
        if r.get("loss_mode") != "full" or r.get("score_variant") != "s_graph":
            continue
        if r.get("DEGENERATE"):
            continue
        key = (r["kind"], r["pooling"])
        groups[key].append(float(r["auc_floor"]))
        clears[key] = clears[key] or bool(r["gate"]["clears_size_floor_0.7025"])
    for key, vals in sorted(groups.items()):
        ms = _mean_std(vals)
        lines.append(
            f"| {key[0]} | {key[1]} | {ms['mean']:.4f}±{ms['std']:.4f} | {len(vals)} | {clears[key]} |"
        )

    lines.append("")
    lines.append("## Ablation / controls")
    lines.append("")
    lines.append(
        "| kind | pool | mode | score | seed | auc_floor | clears_(a) | DEGENERATE |"
    )
    lines.append("|---|---|---|---|---:|---:|---|---|")
    for r in ablation_rows:
        lines.append(
            f"| {r['kind']} | {r['pooling']} | {r['loss_mode']} | {r['score_variant']} | "
            f"{r['seed']} | {r['auc_floor']:.4f} | "
            f"{r['gate']['clears_size_floor_0.7025']} | {r.get('DEGENERATE')} |"
        )

    lines.append("")
    lines.append("## Winner")
    lines.append("")
    if winner:
        lines.append(
            f"- {winner['kind']} · pool={winner['pooling']} · mode={winner['loss_mode']} · "
            f"score={winner['score_variant']} · auc_floor={winner['auc_floor']:.4f} · "
            f"DEGENERATE={winner.get('DEGENERATE')}"
        )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Explainability (winner · top-20 |Δ|)")
    lines.append("")
    if explain and explain.get("top_k"):
        lines.append("| rank | node | mean_benign | mean_malware | Δ(m−b) |")
        lines.append("|---:|---|---:|---:|---:|")
        for i, row in enumerate(explain["top_k"], 1):
            lines.append(
                f"| {i} | {row['name']} | {row['mean_test_benign']:.6f} | "
                f"{row['mean_test_malware']:.6f} | {row['delta_malware_minus_benign']:.6f} |"
            )
        if explain.get("full_t22_table"):
            lines.append("")
            lines.append("### T22 full 22-node table")
            lines.append("")
            lines.append("| node | mean_benign | mean_malware | Δ(m−b) |")
            lines.append("|---|---:|---:|---:|")
            for row in explain["full_t22_table"]:
                lines.append(
                    f"| {row['name']} | {row['mean_test_benign']:.6f} | "
                    f"{row['mean_test_malware']:.6f} | {row['delta_malware_minus_benign']:.6f} |"
                )
    else:
        lines.append("- n/a")

    lines.append("")
    lines.append("## Nested bootstrap (winner)")
    lines.append("")
    if nested:
        lines.append(
            f"| B_ok | mean | std | percentile_ci95 | naive_ci95 | wall_sec |"
        )
        lines.append("|---:|---:|---:|---|---|---:|")
        lines.append(
            f"| {nested.get('B_ok')} | {nested.get('auc_floor_mean')} | "
            f"{nested.get('auc_floor_std')} | {nested.get('percentile_ci95')} | "
            f"{nested.get('naive_score_resample_ci95')} | {nested.get('wall_sec')} |"
        )
    else:
        lines.append("- n/a")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GLocalKD experiment")
    ap.add_argument("--out", type=Path, default=GLOCALKD_OUTPUT_ROOT)
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--skip-nested", action="store_true")
    ap.add_argument("--nested-B", type=int, default=None)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--kinds", default="T22,T1K")
    ap.add_argument("--quick", action="store_true", help="1 seed, mean pool only (debug)")
    args = ap.parse_args(argv)

    # allow epoch override via monkeypatch on train default through args
    import abrg.glocalkd.train as train_mod
    import abrg.glocalkd as pkg

    if args.epochs != EPOCHS:
        train_mod.EPOCHS = args.epochs  # type: ignore[attr-defined]
        pkg.EPOCHS = args.epochs

    out = args.out
    for sub in ("runs", "degeneracy", "ablation", "explain", "bootstrap"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device)
    t_all = time.perf_counter()
    bundle = load_bundle()
    train, test_b, test_m = bundle["train"], bundle["test_benign"], bundle["test_malware"]
    _write_json(
        out / "reproduce_config.json",
        {
            "split_digest": bundle["digest"],
            "implementation": IMPLEMENTATION,
            "reference_commit": REF_COMMIT,
            "seeds": list(SEEDS),
            "epochs": args.epochs,
            "lr": 0.01,
            "hidden": 128,
            "out_dim": 128,
            "n_layers": 3,
            "poolings": list(POOLINGS),
            "loss": "L_node + L_graph equal weight (reference)",
            "T22_x": [22, 10],
            "T1K_x": [1000, 25],
        },
    )

    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    poolings = ("mean",) if args.quick else POOLINGS
    seeds = (42,) if args.quick else SEEDS

    grid_rows: list[dict[str, Any]] = []
    ablation_rows: list[dict[str, Any]] = []
    deg_flags: list[dict[str, Any]] = []
    # keep node scores for explain from best non-deg run
    node_cache: dict[str, Any] = {}

    for kind in kinds:
        tensors = bundle["t22"] if kind == "T22" else bundle["t1k"]
        for pooling in poolings:
            # --- full trained ---
            for seed in seeds:
                tag = f"{kind}__pool-{pooling}__full__seed{seed}"
                print(f"[glocalkd] {tag}", flush=True)
                res = run_one(
                    kind=kind,
                    tensors=tensors,
                    train=train,
                    test_b=test_b,
                    test_m=test_m,
                    pooling=pooling,
                    loss_mode="full",
                    seed=seed,
                    trained=True,
                    out_dir=out,
                    device=device,
                    tag=tag,
                    epochs=args.epochs,
                )
                deg_flags.append(
                    {
                        "tag": tag,
                        "DEGENERATE": res["degeneracy"]["DEGENERATE"],
                        "flags": res["degeneracy"]["flags"],
                        "frac_near_zero": res["degeneracy"]["train_s_graph"][
                            "frac_score_below_1e-6"
                        ],
                    }
                )
                for variant in SCORE_VARIANTS:
                    sc = res["scores"][variant]
                    row = {
                        "kind": kind,
                        "pooling": pooling,
                        "loss_mode": "full",
                        "trained": True,
                        "score_variant": variant,
                        "seed": seed,
                        "auc": float(sc["auc"]["auc"]),
                        "auc_floor": float(sc["auc"]["auc_floor"]),
                        "direction": sc["auc"]["direction"],
                        "ci95_floor": sc["auc"]["ci95_floor"],
                        "gate": sc["gate"],
                        "leak_spearman": sc["leak_spearman"],
                        "DEGENERATE": res["degeneracy"]["DEGENERATE"],
                        "inverted": sc["inverted"],
                    }
                    grid_rows.append(row)
                node_cache[tag] = {
                    "tb": res["node_scores_tb"],
                    "tm": res["node_scores_tm"],
                    "meta": {
                        "kind": kind,
                        "pooling": pooling,
                        "loss_mode": "full",
                        "seed": seed,
                        "auc_floor": float(res["scores"]["s_graph"]["auc"]["auc_floor"]),
                        "DEGENERATE": res["degeneracy"]["DEGENERATE"],
                    },
                }

            # --- controls: untrained + node_only + graph_only ---
            for mode, trained_flag in (
                ("untrained", False),
                ("node_only", True),
                ("graph_only", True),
            ):
                for seed in seeds:
                    tag = f"{kind}__pool-{pooling}__{mode}__seed{seed}"
                    print(f"[glocalkd] {tag}", flush=True)
                    lm: LossMode = "full" if mode == "untrained" else mode  # type: ignore[assignment]
                    res = run_one(
                        kind=kind,
                        tensors=tensors,
                        train=train,
                        test_b=test_b,
                        test_m=test_m,
                        pooling=pooling,
                        loss_mode=lm,
                        seed=seed,
                        trained=trained_flag,
                        out_dir=out,
                        device=device,
                        tag=tag,
                        epochs=args.epochs,
                    )
                    # move to ablation folder copy
                    src = out / "runs" / f"{tag}.json"
                    if src.is_file():
                        (out / "ablation" / f"{tag}.json").write_text(
                            src.read_text(encoding="utf-8"), encoding="utf-8"
                        )
                    deg_flags.append(
                        {
                            "tag": tag,
                            "DEGENERATE": res["degeneracy"]["DEGENERATE"],
                            "flags": res["degeneracy"]["flags"],
                            "frac_near_zero": res["degeneracy"]["train_s_graph"][
                                "frac_score_below_1e-6"
                            ],
                        }
                    )
                    for variant in SCORE_VARIANTS:
                        sc = res["scores"][variant]
                        ablation_rows.append(
                            {
                                "kind": kind,
                                "pooling": pooling,
                                "loss_mode": mode,
                                "score_variant": variant,
                                "seed": seed,
                                "auc_floor": float(sc["auc"]["auc_floor"]),
                                "auc": float(sc["auc"]["auc"]),
                                "gate": sc["gate"],
                                "DEGENERATE": res["degeneracy"]["DEGENERATE"],
                                "ci95_floor": sc["auc"]["ci95_floor"],
                                "direction": sc["auc"]["direction"],
                                "leak_spearman": sc["leak_spearman"],
                            }
                        )

    # winner among non-degenerate full s_graph
    cand = [
        r
        for r in grid_rows
        if r["loss_mode"] == "full"
        and r["score_variant"] == "s_graph"
        and not r.get("DEGENERATE")
    ]
    if not cand:
        cand = [r for r in grid_rows if r["loss_mode"] == "full" and r["score_variant"] == "s_graph"]
    winner = max(cand, key=lambda r: float(r["auc_floor"])) if cand else None
    _write_json(out / "runs" / "winner.json", winner)

    explain = None
    nested = None
    if winner is not None:
        # find matching node cache (same kind/pool/seed)
        match_tag = (
            f"{winner['kind']}__pool-{winner['pooling']}__full__seed{winner['seed']}"
        )
        if match_tag in node_cache:
            nc = node_cache[match_tag]
            explain = node_deviation_table(
                node_scores_benign=nc["tb"],
                node_scores_malware=nc["tm"],
                kind=winner["kind"],
            )
            _write_json(out / "explain" / "winner_nodes.json", explain)

        if not args.skip_nested:
            print("[glocalkd] nested bootstrap", flush=True)
            tensors = bundle["t22"] if winner["kind"] == "T22" else bundle["t1k"]
            in_dim = int(tensors[train[0]]["x"].shape[1])
            B = args.nested_B or NESTED_B
            nested = nested_bootstrap(
                tensors=tensors,
                train=train,
                test_b=test_b,
                test_m=test_m,
                in_dim=in_dim,
                pooling=winner["pooling"],
                loss_mode="full",
                score_variant=winner["score_variant"],
                naive_ci=list(winner.get("ci95_floor") or [float("nan"), float("nan")]),
                B=B,
                epochs=args.epochs,
                seed=int(winner["seed"]),
                device=device,
            )
            # if fast enough and B==100, note; optionally bump
            if (
                B == NESTED_B
                and nested.get("wall_sec", 1e9) < 600
                and nested.get("B_ok", 0) == B
            ):
                print("[glocalkd] nested B=100 fast enough → extending to B=200", flush=True)
                nested = nested_bootstrap(
                    tensors=tensors,
                    train=train,
                    test_b=test_b,
                    test_m=test_m,
                    in_dim=in_dim,
                    pooling=winner["pooling"],
                    loss_mode="full",
                    score_variant=winner["score_variant"],
                    naive_ci=list(winner.get("ci95_floor") or [float("nan"), float("nan")]),
                    B=NESTED_B_FULL,
                    epochs=args.epochs,
                    seed=int(winner["seed"]),
                    device=device,
                )
            _write_json(out / "bootstrap" / "winner_nested.json", nested)

    write_summary(
        out / "SUMMARY.md",
        rows=grid_rows,
        deg_flags=deg_flags,
        winner=winner,
        ablation_rows=ablation_rows,
        explain=explain,
        nested=nested,
        digest=bundle["digest"],
    )
    _write_json(
        out / "runs" / "grid_rows.json",
        {
            "rows": grid_rows,
            "ablation_rows": ablation_rows,
            "winner": winner,
            "wall_sec": time.perf_counter() - t_all,
        },
    )
    print(
        f"[glocalkd] done in {time.perf_counter() - t_all:.1f}s → {out / 'SUMMARY.md'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
