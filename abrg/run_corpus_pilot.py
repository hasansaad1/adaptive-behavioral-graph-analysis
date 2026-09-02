#!/usr/bin/env python3
"""
ABRG v0.2 corpus pilot: multi-window cumulative snapshots → GAE train/test.

Default: 60s processing windows, one cumulative graph snapshot per window per session.
Split by APP (all snapshots from held-out apps go to test — no leakage).

NOT malware detection — benign reconstruction baseline only.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
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
from abrg.config import DEFAULT_WINDOW_SEC, GAE_EPOCHS, GAE_HIDDEN_DIM, GAE_LR
from abrg.corpus import SessionGraphRecord, build_corpus_graphs
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.dataset_paths import current_sessions_dir, current_dataset_version
from abrg.windows import WindowMode

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS = current_sessions_dir()
DEFAULT_OUTPUT = REPO_ROOT / f"abrg/output/corpus_pilot_{current_dataset_version()}"
TEST_RATIO = 0.2
SPLIT_SEED = 42


def distribution_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "min": float("nan"), "median": float("nan"), "max": float("nan"), "mean": float("nan")}
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        "mean": statistics.mean(values),
    }


def snapshot_key(r: SessionGraphRecord) -> str:
    w = r.window_index if r.window_index is not None else 0
    return f"{r.session_id}::w{w}"


def record_to_tensors(
    rec: SessionGraphRecord,
    *,
    normalize: bool = True,
    edge_weight_channel: str = "w_cum",
    categories: list[str] | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    assert rec.graph is not None
    x, edge_index, edge_weight, _ = graph_to_tensors(
        rec.graph,
        normalize=normalize,
        edge_weight_channel=edge_weight_channel,
        categories=categories,
    )
    return x, edge_index, edge_weight


def split_train_test_by_app(
    records: list[SessionGraphRecord],
    test_ratio: float,
    seed: int,
) -> tuple[list[SessionGraphRecord], list[SessionGraphRecord], list[str], list[str]]:
    """Hold out entire apps — all their window snapshots stay in train or test."""
    eligible = [r for r in records if r.gae_eligible]
    apps = sorted({r.package for r in eligible})
    rng = random.Random(seed)
    shuffled = apps[:]
    rng.shuffle(shuffled)
    n_test_apps = max(1, round(len(shuffled) * test_ratio))
    test_apps = set(shuffled[:n_test_apps])
    train_apps = set(shuffled[n_test_apps:])
    train = [r for r in eligible if r.package in train_apps]
    test = [r for r in eligible if r.package in test_apps]
    return train, test, sorted(train_apps), sorted(test_apps)


def build_report(
    records: list[SessionGraphRecord],
    *,
    snapshots: bool,
    window_mode: str,
    window_sec: float,
) -> dict:
    session_ids = {r.session_id for r in records if not r.build_error}
    trainable = [r for r in records if r.trainable]
    excluded_sessions = len(session_ids) - len({r.session_id for r in trainable})
    gae_eligible = [r for r in records if r.gae_eligible]

    def dist(vals: list[int]) -> dict:
        if not vals:
            return {"min": 0, "median": 0, "max": 0, "mean": 0.0}
        return {
            "min": min(vals),
            "median": statistics.median(vals),
            "max": max(vals),
            "mean": round(statistics.mean(vals), 2),
        }

    windows_per_session: dict[str, int] = {}
    for r in records:
        if r.processing_windows_count is not None:
            windows_per_session[r.session_id] = r.processing_windows_count

    return {
        "total_sessions": len(session_ids),
        "total_snapshots": len(records),
        "snapshots_mode": snapshots,
        "window_mode": window_mode,
        "window_sec": window_sec,
        "build_errors": sum(1 for r in records if r.build_error),
        "trainable_snapshots": len(trainable),
        "sessions_with_trainable_snapshot": len({r.session_id for r in trainable}),
        "excluded_sessions_no_trainable_snapshot": excluded_sessions,
        "gae_eligible_snapshots": len(gae_eligible),
        "gae_eligible_apps": len({r.package for r in gae_eligible}),
        "snapshots_per_session_distribution": dist(list(windows_per_session.values())),
        "active_nodes_distribution_trainable": dist([r.n_active_nodes for r in trainable]),
        "edge_count_distribution_trainable": dist([r.n_edges for r in trainable]),
        "edge_count_distribution_gae_eligible": dist([r.n_edges for r in gae_eligible]),
    }


def serialize_record(
    r: SessionGraphRecord,
    recon_error: float | None = None,
    split: str | None = None,
) -> dict:
    out = {
        "snapshot_id": snapshot_key(r),
        "session_id": r.session_id,
        "package": r.package,
        "faithfulness": r.faithfulness,
        "window_index": r.window_index,
        "processing_windows_count": r.processing_windows_count,
        "events_kept": r.events_kept,
        "distinct_categories": r.distinct_categories,
        "n_active_nodes": r.n_active_nodes,
        "n_edges": r.n_edges,
        "active_nodes": r.active_nodes,
        "trainable": r.trainable,
        "gae_eligible": r.gae_eligible,
        "build_error": r.build_error,
    }
    if split is not None:
        out["split"] = split
    if recon_error is not None:
        out["reconstruction_error"] = recon_error
    return out


def count_ln2_failures(errors: list[float], tol: float = 1e-3) -> int:
    import math
    target = math.log(2)
    return sum(1 for e in errors if abs(e - target) < tol or abs(e - 0.693561) < tol)


def main() -> int:
    parser = argparse.ArgumentParser(description="ABRG v0.2 corpus pilot (multi-window snapshots)")
    parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--epochs", type=int, default=GAE_EPOCHS)
    parser.add_argument("--test-ratio", type=float, default=TEST_RATIO)
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    parser.add_argument(
        "--window-mode",
        choices=[m.value for m in WindowMode],
        default=WindowMode.TIME_SEC.value,
        help="Processing window mode (default: time_sec = multi-window)",
    )
    parser.add_argument("--window-sec", type=float, default=DEFAULT_WINDOW_SEC)
    parser.add_argument(
        "--snapshots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Emit one cumulative graph snapshot per processing window (default: on)",
    )
    parser.add_argument(
        "--whole-session",
        action="store_true",
        help="Shortcut: whole_session mode, one graph per app (legacy pilot)",
    )
    parser.add_argument(
        "--normalize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "v0.2.1 tensor feed: act fractions + transition probs (default). "
            "Use --no-normalize for pre-v0.2.1 A/B: log1p(act_count) + raw w_cum."
        ),
    )
    parser.add_argument(
        "--use-edge-weight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Feed edge_weight into GCNConv encoder (default: on).",
    )
    args = parser.parse_args()

    if args.whole_session:
        args.window_mode = WindowMode.WHOLE_SESSION.value
        args.snapshots = False

    window_mode = WindowMode(args.window_mode)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    seed_rng(args.seed)

    feature_mode = "v0.2.1_normalized" if args.normalize else "pre_v0.2.1_raw"
    mode_label = (
        f"multi-window snapshots ({args.window_sec}s)"
        if args.snapshots and window_mode == WindowMode.TIME_SEC
        else f"{window_mode.value}" + (" snapshots" if args.snapshots else ", final graph only")
    )
    print(f"=== A. BUILD: {mode_label}, zero static stub, features={feature_mode} ===")

    t0 = time.time()
    records = build_corpus_graphs(
        args.sessions.resolve(),
        window_mode=window_mode,
        window_sec=args.window_sec,
        snapshots=args.snapshots,
    )
    build_time = time.time() - t0
    build = build_report(
        records,
        snapshots=args.snapshots,
        window_mode=window_mode.value,
        window_sec=args.window_sec,
    )
    build["build_wall_sec"] = round(build_time, 2)
    print(json.dumps(build, indent=2))

    gae_eligible = [r for r in records if r.gae_eligible]
    if len(gae_eligible) < 2:
        print(f"STOP: only {len(gae_eligible)} GAE-eligible snapshots.", file=sys.stderr)
        return 1

    n_apps = build["gae_eligible_apps"]
    if n_apps < 15:
        print(
            f"\n*** WARNING: only {n_apps} apps with GAE-eligible snapshots (<15 apps). "
            f"{len(gae_eligible)} total snapshots. Generalization is INDICATIVE only. ***\n"
        )

    print("\n=== B. SPLIT: 80/20 by APP (all snapshots from test apps held out) ===")
    print(
        "Rationale: snapshots from the same app are correlated; split at app level "
        "so test snapshots are from apps the GAE never saw during training."
    )
    train_recs, test_recs, train_apps, test_apps = split_train_test_by_app(
        records, args.test_ratio, args.seed
    )
    print(f"  GAE-eligible snapshots: {len(gae_eligible)} from {n_apps} apps")
    print(f"  Train: {len(train_recs)} snapshots from {len(train_apps)} apps")
    print(f"  Test:  {len(test_recs)} snapshots from {len(test_apps)} apps")

    train_tensors = [record_to_tensors(r, normalize=args.normalize) for r in train_recs]
    train_pairs = [
        (x, ei, ew if args.use_edge_weight else None) for x, ei, ew in train_tensors
    ]

    print(f"\n=== C. TRAIN: GAE on {len(train_recs)} training snapshots ({feature_mode}) ===")
    print(f"  edge_weight_in_encoder={args.use_edge_weight}")
    t1 = time.time()
    model = build_gae(node_feature_dim(), GAE_HIDDEN_DIM)
    curve, final_train_mean = train_gae_multi(model, train_pairs, args.epochs, GAE_LR)
    train_time = time.time() - t1
    converged = len(curve) >= 2 and curve[-1] < curve[0] * 0.85
    print(f"  epochs={args.epochs}, hidden={GAE_HIDDEN_DIM}, lr={GAE_LR}, wall={train_time:.1f}s")
    print(f"  loss first epoch: {curve[0]:.6f}")
    print(f"  loss final epoch: {curve[-1]:.6f}")
    print(f"  converged (final < 85% of first): {converged}")

    def _score(x, ei, ew):
        return graph_reconstruction_error(
            model, x, ei, ew if args.use_edge_weight else None
        )

    print("\n=== D. TEST: held-out app snapshots ===")
    train_errors = [_score(x, ei, ew) for x, ei, ew in train_tensors]
    test_tensors = [record_to_tensors(r, normalize=args.normalize) for r in test_recs]
    test_errors = [_score(x, ei, ew) for x, ei, ew in test_tensors]

    train_stats = distribution_stats(train_errors)
    test_stats = distribution_stats(test_errors)
    print(f"  TRAIN error: min={train_stats['min']:.6f} med={train_stats['median']:.6f} max={train_stats['max']:.6f}")
    print(f"  TEST  error: min={test_stats['min']:.6f} med={test_stats['median']:.6f} max={test_stats['max']:.6f}")
    print(f"  TRAIN ln(2) failures: {count_ln2_failures(train_errors)}/{len(train_errors)}")
    print(f"  TEST  ln(2) failures: {count_ln2_failures(test_errors)}/{len(test_errors)}")

    ratio = test_stats["median"] / train_stats["median"] if train_stats["median"] else float("nan")
    ln2_frac = count_ln2_failures(train_errors + test_errors) / len(gae_eligible)
    if ratio < 2.0 and ln2_frac < 0.35:
        verdict = (
            "GAE reconstructs most multi-window benign snapshots and generalizes to "
            "held-out apps at comparable median error."
        )
    elif ln2_frac >= 0.35:
        verdict = (
            f"GAE training incomplete — {ln2_frac:.0%} of snapshots at ln(2) random-guess error; "
            "baseline not reliable yet."
        )
    else:
        verdict = "Held-out test error exceeds training range — generalization unclear."

    print(f"\n  Verdict: {verdict}")

    print("\n=== E. BASELINE: per-snapshot reconstruction error (all GAE-eligible) ===")
    per_graph: list[dict] = []
    all_errors: list[float] = []
    train_set = set(id(r) for r in train_recs)
    test_set = set(id(r) for r in test_recs)
    for r in gae_eligible:
        x, ei, ew = record_to_tensors(r, normalize=args.normalize)
        err = _score(x, ei, ew)
        all_errors.append(err)
        split = "train" if id(r) in train_set else "test" if id(r) in test_set else "unused"
        per_graph.append(serialize_record(r, recon_error=err, split=split))

    baseline_stats = distribution_stats(all_errors)
    print(json.dumps(baseline_stats, indent=2))

    model_path = args.output_dir / "gae_corpus_model.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "in_channels": node_feature_dim(),
            "hidden_channels": GAE_HIDDEN_DIM,
            "epochs": args.epochs,
            "lr": GAE_LR,
            "window_mode": window_mode.value,
            "window_sec": args.window_sec,
            "snapshots": args.snapshots,
        },
        model_path,
    )

    results = {
        "pilot": "abrg_v0.2_corpus_multiwindow",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pinned": {
            "window": f"{window_mode.value}_snapshots" if args.snapshots else window_mode.value,
            "window_sec": args.window_sec,
            "static": "zero_stub",
            "autoencoder": "GAE",
            "feature_mode": feature_mode,
            "normalize": args.normalize,
            "use_edge_weight": args.use_edge_weight,
            "weights": "transition_prob" if args.normalize else "raw_w_cum",
            "act_v": "fraction" if args.normalize else "log1p",
            "recon_loss": "adjacency_bce",
            "note": (
                "edge_weight fed to GCNConv" if args.use_edge_weight else "edge_weight ignored by encoder"
            ),
        },
        "build": build,
        "split": {
            "method": "random_80_20_app_level",
            "seed": args.seed,
            "test_ratio": args.test_ratio,
            "train_snapshots": len(train_recs),
            "test_snapshots": len(test_recs),
            "train_apps": train_apps,
            "test_apps": test_apps,
        },
        "training": {
            "epochs": args.epochs,
            "hidden_dim": GAE_HIDDEN_DIM,
            "lr": GAE_LR,
            "wall_sec": round(train_time, 2),
            "loss_curve": curve,
            "final_epoch_mean_loss": final_train_mean,
            "converged_heuristic": converged,
            "train_error_distribution": train_stats,
            "train_ln2_failure_count": count_ln2_failures(train_errors),
        },
        "test": {
            "error_distribution": test_stats,
            "train_vs_test_median_ratio": ratio,
            "test_ln2_failure_count": count_ln2_failures(test_errors),
            "generalization_verdict": verdict,
        },
        "baseline": baseline_stats,
        "per_snapshot": per_graph,
    }

    results_path = args.output_dir / "corpus_pilot_results.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    summary = f"""ABRG v0.2 corpus pilot — MULTI-WINDOW SNAPSHOTS
============================================================
Mode: {mode_label}
Features: {feature_mode}
Sessions: {build['total_sessions']} | Snapshots built: {build['total_snapshots']}
GAE-eligible snapshots: {len(gae_eligible)} from {n_apps} apps
Train: {len(train_recs)} snapshots / {len(train_apps)} apps
Test:  {len(test_recs)} snapshots / {len(test_apps)} apps

Build time: {build_time:.1f}s | Train time: {train_time:.1f}s
GAE loss {curve[0]:.4f} → {curve[-1]:.4f} ({args.epochs} epochs, converged={converged})
Train recon error: median={train_stats['median']:.6f} (ln2-fail={count_ln2_failures(train_errors)})
Test  recon error: median={test_stats['median']:.6f} (ln2-fail={count_ln2_failures(test_errors)})
Benign baseline (all eligible): median={baseline_stats['median']:.6f}

{verdict}

PILOT HONEST SUMMARY
--------------------
Multi-window cumulative snapshots ({args.window_sec}s) from {build['total_sessions']} sessions
produced {len(gae_eligible)} GAE-eligible snapshots from {n_apps} apps. NOT malware detection.
ln(2) failure rate: {ln2_frac:.0%} of snapshots at random-guess reconstruction error.

Saved: {results_path}
Model:  {model_path}
"""
    summary_path = args.output_dir / "corpus_pilot_summary.txt"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\nWrote {results_path}")
    print(f"Wrote {model_path}")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
