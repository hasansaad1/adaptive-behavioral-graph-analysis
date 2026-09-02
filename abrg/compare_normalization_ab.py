#!/usr/bin/env python3
"""
A/B: same v2 corpus, same split/seed/GAE hyperparams — only tensor feed differs.

  A) --normalize     (v0.2.1): act_v fraction + transition-prob edge_weight
  B) --no-normalize  (pre):    act_v log1p + raw w_cum edge_weight

By default edge_weight is fed into GCNConv message passing (encoder only).
Loss remains adjacency BCE (recon_loss). Use --no-edge-weight to reproduce the
legacy A/B where weights were computed but ignored.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch

from abrg.autoencoder import (
    build_gae,
    graph_reconstruction_error,
    seed_rng,
    train_gae_multi,
)
from abrg.config import (
    DEFAULT_WINDOW_SEC,
    DELTA_SEC,
    GAE_EPOCHS,
    GAE_HIDDEN_DIM,
    GAE_LR,
    K_BURST,
    LAMBDA_REC,
)
from abrg.corpus import build_corpus_graphs
from abrg.dataset_paths import REPO_ROOT, current_dataset_version, current_sessions_dir
from abrg.features import categories_active_in_corpus, node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.run_corpus_pilot import (
    SPLIT_SEED,
    TEST_RATIO,
    build_report,
    count_ln2_failures,
    distribution_stats,
    record_to_tensors,
    split_train_test_by_app,
)
from abrg.windows import WindowMode

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_arm(
    *,
    label: str,
    normalize: bool,
    train_recs,
    test_recs,
    gae_eligible,
    epochs: int,
    seed: int,
    out_dir: Path,
    use_edge_weight: bool,
    hidden: int,
    lr: float,
    weight_decay: float = 0.0,
    edge_weight_channel: str = "w_cum",
    categories: list[str] | None = None,
) -> dict:
    seed_rng(seed)
    tensor_kw = dict(edge_weight_channel=edge_weight_channel, categories=categories)
    train_tensors = [
        record_to_tensors(r, normalize=normalize, **tensor_kw) for r in train_recs
    ]
    if use_edge_weight:
        train_pairs = [(x, ei, ew) for x, ei, ew in train_tensors]
    else:
        train_pairs = [(x, ei, None) for x, ei, _ in train_tensors]

    t0 = time.time()
    model = build_gae(node_feature_dim(), hidden)
    curve, final_train_mean = train_gae_multi(
        model, train_pairs, epochs, lr, weight_decay=weight_decay
    )
    train_sec = time.time() - t0

    def _err(x, ei, ew):
        return graph_reconstruction_error(model, x, ei, ew if use_edge_weight else None)

    train_errors = [_err(x, ei, ew) for x, ei, ew in train_tensors]
    test_tensors = [
        record_to_tensors(r, normalize=normalize, **tensor_kw) for r in test_recs
    ]
    test_errors = [_err(x, ei, ew) for x, ei, ew in test_tensors]

    train_stats = distribution_stats(train_errors)
    test_stats = distribution_stats(test_errors)
    ratio = (
        test_stats["median"] / train_stats["median"] if train_stats["median"] else float("nan")
    )

    rows = []
    train_ids = {id(r) for r in train_recs}
    for r in gae_eligible:
        x, ei, ew = record_to_tensors(r, normalize=normalize, **tensor_kw)
        err = _err(x, ei, ew)
        split = "train" if id(r) in train_ids else "test"
        rows.append(
            {
                "package": r.package,
                "session_id": r.session_id,
                "window": r.window_index if r.window_index is not None else 0,
                "split": split,
                "n_active_nodes": r.n_active_nodes,
                "n_edges": r.n_edges,
                "events_kept": r.events_kept,
                "reconstruction_error": err,
            }
        )

    arm_dir = out_dir / label
    arm_dir.mkdir(parents=True, exist_ok=True)
    n_nodes = len(categories) if categories is not None else len(GRAPH_CATEGORY_UNIVERSE)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "normalize": normalize,
            "label": label,
            "seed": seed,
            "epochs": epochs,
            "lr": lr,
            "weight_decay": weight_decay,
            "use_edge_weight": use_edge_weight,
            "edge_weight_channel": edge_weight_channel,
            "categories": categories,
            "n_nodes": n_nodes,
            "in_channels": node_feature_dim(),
            "hidden_channels": hidden,
        },
        arm_dir / "gae_corpus_model.pt",
    )
    with (arm_dir / "per_snapshot_errors.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    with (arm_dir / "training_curve.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "loss"])
        for i, loss in enumerate(curve, start=1):
            writer.writerow([i, loss])

    result = {
        "label": label,
        "normalize": normalize,
        "use_edge_weight": use_edge_weight,
        "act_v": "fraction" if normalize else "log1p",
        "edge_weight_tensor": (
            f"transition_prob_{edge_weight_channel}"
            if normalize
            else f"raw_{edge_weight_channel}"
        ),
        "edge_weight_channel": edge_weight_channel,
        "edge_weight_in_encoder": use_edge_weight,
        "n_nodes": n_nodes,
        "dropped_never_active": categories is not None
        and len(categories) < len(GRAPH_CATEGORY_UNIVERSE),
        "train_wall_sec": round(train_sec, 2),
        "loss_first": curve[0] if curve else float("nan"),
        "loss_final": curve[-1] if curve else float("nan"),
        "final_epoch_mean_loss": final_train_mean,
        "converged_heuristic": len(curve) >= 2 and curve[-1] < curve[0] * 0.85,
        "train_error": train_stats,
        "test_error": test_stats,
        "train_vs_test_median_ratio": ratio,
        "train_ln2_failures": count_ln2_failures(train_errors),
        "test_ln2_failures": count_ln2_failures(test_errors),
    }
    (arm_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B normalize vs raw features on same corpus")
    parser.add_argument("--sessions", type=Path, default=current_sessions_dir())
    parser.add_argument(
        "--use-edge-weight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Feed edge_weight into GCNConv (default: on).",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=GAE_EPOCHS)
    parser.add_argument("--hidden", type=int, default=GAE_HIDDEN_DIM)
    parser.add_argument("--lr", type=float, default=GAE_LR)
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=0.0,
        help="Adam L2 weight_decay (default: 0).",
    )
    parser.add_argument(
        "--k-burst",
        type=int,
        default=K_BURST,
        help=f"Edge-formation burst look-ahead k (default: {K_BURST}).",
    )
    parser.add_argument(
        "--delta-sec",
        type=float,
        default=DELTA_SEC,
        help=f"Edge-formation time tolerance δ seconds (default: {DELTA_SEC}).",
    )
    parser.add_argument(
        "--lambda-rec",
        type=float,
        default=LAMBDA_REC,
        help=f"Recency decay λ per second (default: {LAMBDA_REC}).",
    )
    parser.add_argument(
        "--edge-weight-channel",
        choices=["w_cum", "w_rec"],
        default="w_cum",
        help="Encoder edge-weight channel (default: w_cum).",
    )
    parser.add_argument(
        "--snapshots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Cumulative multi-window snapshots (default: on).",
    )
    parser.add_argument(
        "--drop-never-active-nodes",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Temporary probe: drop GRAPH_CATEGORY_UNIVERSE nodes that never appear "
            "(act_count=0) in any corpus graph from the GAE tensor (default: off)."
        ),
    )
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    parser.add_argument("--test-ratio", type=float, default=TEST_RATIO)
    parser.add_argument("--window-sec", type=float, default=DEFAULT_WINDOW_SEC)
    parser.add_argument(
        "--axis",
        type=str,
        default="",
        help="Experimental axis label for reproduce_config.json / reproduce.ipynb",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Run id for reproduce artifacts (default: output-dir name)",
    )
    args = parser.parse_args()

    if args.output_dir is None:
        if args.use_edge_weight:
            args.output_dir = (
                REPO_ROOT / f"abrg/output/norm_ab_{current_dataset_version()}_weighted"
            )
        else:
            args.output_dir = REPO_ROOT / f"abrg/output/norm_ab_{current_dataset_version()}"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Building corpus once from {args.sessions} "
        f"(dataset={current_dataset_version()}, window={args.window_sec}s, "
        f"edge_weight_in_encoder={args.use_edge_weight})..."
    )
    t0 = time.time()
    records = build_corpus_graphs(
        args.sessions.resolve(),
        window_mode=WindowMode.TIME_SEC,
        window_sec=args.window_sec,
        snapshots=args.snapshots,
        k_burst=args.k_burst,
        delta_sec=args.delta_sec,
        lambda_rec=args.lambda_rec,
    )
    build = build_report(
        records,
        snapshots=args.snapshots,
        window_mode=WindowMode.TIME_SEC.value,
        window_sec=args.window_sec,
    )
    build["build_wall_sec"] = round(time.time() - t0, 2)
    print(json.dumps(build, indent=2))

    train_recs, test_recs, train_apps, test_apps = split_train_test_by_app(
        records, args.test_ratio, args.seed
    )
    gae_eligible = [r for r in records if r.gae_eligible]

    dropped_nodes: list[str] = []
    categories: list[str] | None = None
    if args.drop_never_active_nodes:
        categories = categories_active_in_corpus(records)
        dropped_nodes = [c for c in GRAPH_CATEGORY_UNIVERSE if c not in categories]
        print(
            f"drop-never-active-nodes: keeping {len(categories)}/{len(GRAPH_CATEGORY_UNIVERSE)} "
            f"nodes; dropped={dropped_nodes}"
        )
    print(
        f"Split seed={args.seed}: train {len(train_recs)} snaps / {len(train_apps)} apps | "
        f"test {len(test_recs)} snaps / {len(test_apps)} apps"
    )

    print("\n=== ARM A: v0.2.1 normalized ===")
    arm_a = _run_arm(
        label="normalized_v021",
        normalize=True,
        train_recs=train_recs,
        test_recs=test_recs,
        gae_eligible=gae_eligible,
        epochs=args.epochs,
        seed=args.seed,
        out_dir=args.output_dir,
        use_edge_weight=args.use_edge_weight,
        hidden=args.hidden,
        lr=args.lr,
        weight_decay=args.weight_decay,
        edge_weight_channel=args.edge_weight_channel,
        categories=categories,
    )
    print(
        f"  loss {arm_a['loss_first']:.4f} → {arm_a['loss_final']:.4f} | "
        f"train med={arm_a['train_error']['median']:.4f} | "
        f"test med={arm_a['test_error']['median']:.4f}"
    )

    print("\n=== ARM B: pre-v0.2.1 raw (no normalize) ===")
    arm_b = _run_arm(
        label="raw_pre_v021",
        normalize=False,
        train_recs=train_recs,
        test_recs=test_recs,
        gae_eligible=gae_eligible,
        epochs=args.epochs,
        seed=args.seed,
        out_dir=args.output_dir,
        use_edge_weight=args.use_edge_weight,
        hidden=args.hidden,
        lr=args.lr,
        weight_decay=args.weight_decay,
        edge_weight_channel=args.edge_weight_channel,
        categories=categories,
    )
    print(
        f"  loss {arm_b['loss_first']:.4f} → {arm_b['loss_final']:.4f} | "
        f"train med={arm_b['train_error']['median']:.4f} | "
        f"test med={arm_b['test_error']['median']:.4f}"
    )

    comparison = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": current_dataset_version(),
        "sessions_dir": str(Path(args.sessions).resolve().relative_to(REPO_ROOT)) if str(Path(args.sessions).resolve()).startswith(str(REPO_ROOT)) else str(Path(args.sessions).resolve()), Path(__file__).resolve().parents[1]),
        "pinned": {
            "window_sec": args.window_sec,
            "epochs": args.epochs,
            "hidden": args.hidden,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "k_burst": args.k_burst,
            "delta_sec": args.delta_sec,
            "lambda_rec": args.lambda_rec,
            "edge_weight_channel": args.edge_weight_channel,
            "snapshots": args.snapshots,
            "drop_never_active_nodes": args.drop_never_active_nodes,
            "n_nodes": len(categories) if categories is not None else len(GRAPH_CATEGORY_UNIVERSE),
            "kept_categories": categories,
            "dropped_categories": dropped_nodes,
            "seed": args.seed,
            "test_ratio": args.test_ratio,
            "static": "zero_stub",
            "gae_uses_edge_weight": args.use_edge_weight,
            "recon_loss": "adjacency_bce",
        },
        "build": build,
        "split": {
            "train_snapshots": len(train_recs),
            "test_snapshots": len(test_recs),
            "train_apps": train_apps,
            "test_apps": test_apps,
        },
        "normalized_v021": arm_a,
        "raw_pre_v021": arm_b,
        "delta_test_median_normalized_minus_raw": (
            arm_a["test_error"]["median"] - arm_b["test_error"]["median"]
        ),
        "delta_train_median_normalized_minus_raw": (
            arm_a["train_error"]["median"] - arm_b["train_error"]["median"]
        ),
    }
    out_json = args.output_dir / "comparison.json"
    out_json.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    weight_note = (
        "Encoder feeds edge_weight into GCNConv; recon_loss stays adjacency BCE."
        if args.use_edge_weight
        else "Encoder ignores edge_weight (legacy A/B)."
    )
    summary = f"""ABRG normalization A/B — same corpus / split / seed
============================================================
Dataset: {current_dataset_version()} | window={args.window_sec}s | seed={args.seed}
edge_weight_in_encoder={args.use_edge_weight}
Train: {len(train_recs)} snaps / {len(train_apps)} apps
Test:  {len(test_recs)} snaps / {len(test_apps)} apps

                 train_med   test_med   ratio   loss_final
normalized_v021  {arm_a['train_error']['median']:9.4f}  {arm_a['test_error']['median']:8.4f}  {arm_a['train_vs_test_median_ratio']:5.3f}  {arm_a['loss_final']:10.4f}
raw_pre_v021     {arm_b['train_error']['median']:9.4f}  {arm_b['test_error']['median']:8.4f}  {arm_b['train_vs_test_median_ratio']:5.3f}  {arm_b['loss_final']:10.4f}

Δ test median (norm − raw):  {comparison['delta_test_median_normalized_minus_raw']:+.4f}
Δ train median (norm − raw): {comparison['delta_train_median_normalized_minus_raw']:+.4f}

{weight_note}
Saved: {out_json}
"""
    (args.output_dir / "comparison_summary.txt").write_text(summary, encoding="utf-8")
    print("\n" + summary)

    from abrg.reproduce import emit_reproduce_artifacts

    axis = args.axis or (
        f"window_sec={args.window_sec} epochs={args.epochs} "
        f"hidden={args.hidden} lr={args.lr} weight_decay={args.weight_decay} "
        f"edge_weight={args.use_edge_weight}"
    )
    paths = emit_reproduce_artifacts(
        args.output_dir,
        axis=axis,
        run_id=args.run_id or args.output_dir.name,
        cli_module="abrg.compare_normalization_ab",
    )
    print(
        "Reproduce artifacts:",
        f"{paths['reproduce_config'].name}, {paths['reproduce_notebook'].name}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
