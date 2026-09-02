#!/usr/bin/env python3
"""
Negative control on benign test graphs — per-model corruption diagnostics.

Two models (normalized v0.2.1, raw pre-v0.2.1), same v2 app-level test split.
Three corruption types kept SEPARATE (never pooled):

  1. edge_shuffle          — destroy transition structure (exact degree preservation
                             when feasible; else out-degree-preserving rematch among
                             active nodes — sparse graphs often admit only one simple
                             digraph with a given degree sequence)
  2. impossible_edge       — inject edges never observed in the benign corpus
  3. weight_randomization  — same topology, shuffled edge weights

Per (model × corruption) cell:
  - median δ (IQR) where δᵢ = err(corruptedᵢ) − err(benignᵢ)
  - AUC (benign vs corrupted recon errors; higher = more abnormal)
  - paired win rate: fraction with δᵢ > 0
  - Wilcoxon signed-rank p on δ (optional significance)

Also reports one benign baseline median error per model.

IMPORTANT: when use_edge_weight=True (default for weighted models), edge_weight is
fed into GCNConv. Loss remains adjacency BCE. weight_randomization then becomes a
real probe of whether the encoder used habitual proportions / magnitudes.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch import Tensor

from abrg.autoencoder import build_gae, graph_reconstruction_error_deterministic
from abrg.config import DEFAULT_WINDOW_SEC, GAE_HIDDEN_DIM
from abrg.corpus import SessionGraphRecord, build_corpus_graphs
from abrg.dataset_paths import current_dataset_version, current_sessions_dir
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.run_corpus_pilot import SPLIT_SEED, TEST_RATIO, split_train_test_by_app
from abrg.windows import WindowMode

REPO_ROOT = Path(__file__).resolve().parents[1]
N_NODES = len(GRAPH_CATEGORY_UNIVERSE)


@dataclass(frozen=True)
class ScoredGraph:
    package: str
    session_id: str
    window: int
    benign_error: float
    corrupted_error: float

    @property
    def delta(self) -> float:
        return self.corrupted_error - self.benign_error


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else float("nan")


def _iqr(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    q1, q3 = statistics.quantiles(xs, n=4)[0], statistics.quantiles(xs, n=4)[2]
    return float(q3 - q1)


def _auc(benign: list[float], corrupted: list[float]) -> float:
    """ROC AUC with higher reconstr. error = more abnormal (label 1). Same n for both lists."""
    try:
        from sklearn.metrics import roc_auc_score
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("scikit-learn required for AUC: pip install scikit-learn") from exc
    y = [0] * len(benign) + [1] * len(corrupted)
    s = benign + corrupted
    if len(set(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, s))


def _wilcoxon_p(deltas: list[float]) -> float:
    nonzero = [d for d in deltas if d != 0.0]
    if len(nonzero) < 1:
        return float("nan")
    try:
        from scipy.stats import wilcoxon
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("scipy required for Wilcoxon: pip install scipy") from exc
    try:
        res = wilcoxon(nonzero, alternative="greater", zero_method="wilcox")
        return float(res.pvalue)
    except ValueError:
        return float("nan")


def summarize_cell(rows: list[ScoredGraph], *, n_test_pool: int, skipped_unchanged: int) -> dict:
    deltas = [r.delta for r in rows]
    benign = [r.benign_error for r in rows]
    corrupted = [r.corrupted_error for r in rows]
    win = sum(1 for d in deltas if d > 0)
    return {
        "n_eligible": len(rows),
        "n_test_pool": n_test_pool,
        "skipped_unchanged": skipped_unchanged,
        "n": len(rows),  # alias for n_eligible (compat)
        "benign_median": _median(benign),
        "corrupted_median": _median(corrupted),
        "median_delta": _median(deltas),
        "iqr_delta": _iqr(deltas),
        "auc": _auc(benign, corrupted),
        "auc_note": "AUC uses same n_eligible for benign and corrupted (not full test pool)",
        "win_rate": win / len(rows) if rows else float("nan"),
        "wins": win,
        "wilcoxon_p_greater": _wilcoxon_p(deltas),
    }


def corpus_observed_edges(records: list[SessionGraphRecord]) -> set[tuple[int, int]]:
    """Directed edges that appear at least once in the benign corpus (any eligible/trainable)."""
    cats = list(GRAPH_CATEGORY_UNIVERSE)
    cat_to_idx = {c: i for i, c in enumerate(cats)}
    observed: set[tuple[int, int]] = set()
    for r in records:
        if r.graph is None:
            continue
        for (u, v), e in r.graph.edges.items():
            if e.w_cum <= 0:
                continue
            if u in cat_to_idx and v in cat_to_idx:
                observed.add((cat_to_idx[u], cat_to_idx[v]))
    return observed


def impossible_pairs(observed: set[tuple[int, int]]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for i in range(N_NODES):
        for j in range(N_NODES):
            if i == j:
                continue
            if (i, j) not in observed:
                pairs.append((i, j))
    return pairs


def _clone_tensors(x: Tensor, edge_index: Tensor, edge_weight: Tensor) -> tuple[Tensor, Tensor, Tensor]:
    return x.clone(), edge_index.clone(), edge_weight.clone()


def _active_node_indices(x: Tensor, edge_index: Tensor) -> list[int]:
    """Nodes with nonzero activity feature or incident to an edge."""
    # act column: last-but-2 in feature layout (sess, rec after act) — use any nonzero feat row
    # Safer: union of edge endpoints + rows with any nonzero feature.
    active = set(edge_index[0].tolist()) | set(edge_index[1].tolist())
    for i in range(x.size(0)):
        if float(x[i].abs().sum()) > 0:
            active.add(i)
    return sorted(active)


def corrupt_edge_shuffle(
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Tensor,
    rng: random.Random,
    *,
    max_attempts: int = 128,
) -> tuple[Tensor, Tensor, Tensor, bool]:
    """
    Rewire edges to destroy transition structure while keeping |E|, weights multiset,
    and total activity (node features unchanged).

    Preferred: exact directed configuration-model rematching (preserves in+out degrees).
    Fallback (common on this sparse corpus, where the degree sequence often admits only
    one simple digraph): out-degree-preserving destination scramble among active nodes.
    That keeps how many transitions leave each category, but not in-degrees.
    """
    x, edge_index, edge_weight = _clone_tensors(x, edge_index, edge_weight)
    e = edge_index.size(1)
    if e < 1:
        return x, edge_index, edge_weight, False

    orig_src = edge_index[0].tolist()
    orig_dst = edge_index[1].tolist()
    orig_set = set(zip(orig_src, orig_dst))
    weights = edge_weight.tolist()
    active = _active_node_indices(x, edge_index)
    if len(active) < 2:
        return x, edge_index, edge_weight, False

    # --- attempt exact in+out degree preservation ---
    if e >= 2:
        for _ in range(max_attempts):
            out_stubs = orig_src[:]
            in_stubs = orig_dst[:]
            rng.shuffle(in_stubs)
            pairs = list(zip(out_stubs, in_stubs))
            if any(u == v for u, v in pairs):
                continue
            if len(set(pairs)) != e:
                continue
            if set(pairs) == orig_set:
                continue
            w = weights[:]
            rng.shuffle(w)
            src = [u for u, _ in pairs]
            dst = [v for _, v in pairs]
            return (
                x,
                torch.tensor([src, dst], dtype=torch.long),
                torch.tensor(w, dtype=torch.float32),
                True,
            )

    # --- fallback: out-degree-preserving destination scramble ---
    for _ in range(max_attempts):
        new_pairs: list[tuple[int, int]] = []
        ok = True
        used: set[tuple[int, int]] = set()
        for u in orig_src:
            candidates = [v for v in active if v != u]
            if not candidates:
                ok = False
                break
            rng.shuffle(candidates)
            chosen = None
            for v in candidates:
                if (u, v) not in used:
                    chosen = v
                    break
            if chosen is None:
                ok = False
                break
            used.add((u, chosen))
            new_pairs.append((u, chosen))
        if not ok:
            continue
        if set(new_pairs) == orig_set:
            continue
        w = weights[:]
        rng.shuffle(w)
        src = [u for u, _ in new_pairs]
        dst = [v for _, v in new_pairs]
        return (
            x,
            torch.tensor([src, dst], dtype=torch.long),
            torch.tensor(w, dtype=torch.float32),
            True,
        )
    return x, edge_index, edge_weight, False


def corrupt_impossible_edge(
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Tensor,
    rng: random.Random,
    pool: list[tuple[int, int]],
    *,
    n_inject: int | None = None,
) -> tuple[Tensor, Tensor, Tensor, bool]:
    """Add directed edges from the corpus-impossible pool (not already present)."""
    x, edge_index, edge_weight = _clone_tensors(x, edge_index, edge_weight)
    existing = {
        (int(edge_index[0, k]), int(edge_index[1, k]))
        for k in range(edge_index.size(1))
    }
    candidates = [p for p in pool if p not in existing]
    if not candidates:
        return x, edge_index, edge_weight, False

    e = edge_index.size(1)
    k = n_inject if n_inject is not None else max(1, (e + 3) // 4)
    k = min(k, len(candidates))
    chosen = rng.sample(candidates, k)

    if edge_weight.numel() > 0:
        w_fill = float(edge_weight.median().item())
        if w_fill <= 0:
            w_fill = 1.0
    else:
        w_fill = 1.0

    new_src = edge_index[0].tolist() + [u for u, _ in chosen]
    new_dst = edge_index[1].tolist() + [v for _, v in chosen]
    new_w = edge_weight.tolist() + [w_fill] * k
    return (
        x,
        torch.tensor([new_src, new_dst], dtype=torch.long),
        torch.tensor(new_w, dtype=torch.float32),
        True,
    )


def corrupt_weight_randomization(
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Tensor,
    rng: random.Random,
) -> tuple[Tensor, Tensor, Tensor, bool]:
    """Same topology; permute edge weights."""
    x, edge_index, edge_weight = _clone_tensors(x, edge_index, edge_weight)
    if edge_weight.numel() < 2:
        return x, edge_index, edge_weight, False
    weights = edge_weight.tolist()
    orig = weights[:]
    # retry until permutation differs (or give up)
    for _ in range(32):
        rng.shuffle(weights)
        if weights != orig:
            return x, edge_index, torch.tensor(weights, dtype=torch.float32), True
        weights = orig[:]
    return x, edge_index, edge_weight, False


def load_model(path: Path) -> tuple[torch.nn.Module, dict]:
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = build_gae(node_feature_dim(), GAE_HIDDEN_DIM)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt if isinstance(ckpt, dict) else {}


def score_arm(
    *,
    label: str,
    normalize: bool,
    model: torch.nn.Module,
    test_recs: list[SessionGraphRecord],
    impossible_pool: list[tuple[int, int]],
    seed: int,
    use_edge_weight: bool,
) -> dict:
    corruption_fns = {
        "edge_shuffle": lambda x, ei, ew, rng: corrupt_edge_shuffle(x, ei, ew, rng),
        "impossible_edge": lambda x, ei, ew, rng: corrupt_impossible_edge(
            x, ei, ew, rng, impossible_pool
        ),
        "weight_randomization": lambda x, ei, ew, rng: corrupt_weight_randomization(
            x, ei, ew, rng
        ),
    }

    n_test_pool = sum(
        1
        for r in test_recs
        if r.graph is not None
        and graph_to_tensors(r.graph, normalize=normalize)[1].numel() > 0
    )

    cells: dict[str, dict] = {}
    detail: dict[str, list[dict]] = {name: [] for name in corruption_fns}

    # Full-pool benign baseline (all test graphs with edges)
    benign_errors: list[float] = []
    for r in test_recs:
        assert r.graph is not None
        x, ei, ew, _ = graph_to_tensors(r.graph, normalize=normalize)
        if ei.numel() == 0:
            continue
        benign_errors.append(
            graph_reconstruction_error_deterministic(
                model, x, ei, ew if use_edge_weight else None
            )
        )

    for name, fn in corruption_fns.items():
        rows: list[ScoredGraph] = []
        skipped_unchanged = 0
        for r in test_recs:
            assert r.graph is not None
            x, ei, ew, _ = graph_to_tensors(r.graph, normalize=normalize)
            if ei.numel() == 0:
                continue
            benign_err = graph_reconstruction_error_deterministic(
                model, x, ei, ew if use_edge_weight else None
            )
            rng = random.Random(
                hash((seed, label, name, r.session_id, r.window_index)) % (2**32)
            )
            x_c, ei_c, ew_c, changed = fn(x, ei, ew, rng)
            if not changed or ei_c.numel() == 0:
                skipped_unchanged += 1
                continue
            corr_err = graph_reconstruction_error_deterministic(
                model, x_c, ei_c, ew_c if use_edge_weight else None
            )
            row = ScoredGraph(
                package=r.package,
                session_id=r.session_id,
                window=r.window_index if r.window_index is not None else 0,
                benign_error=benign_err,
                corrupted_error=corr_err,
            )
            rows.append(row)
            detail[name].append(
                {
                    "package": row.package,
                    "session_id": row.session_id,
                    "window": row.window,
                    "benign_error": row.benign_error,
                    "corrupted_error": row.corrupted_error,
                    "delta": row.delta,
                }
            )
        cells[name] = summarize_cell(
            rows, n_test_pool=n_test_pool, skipped_unchanged=skipped_unchanged
        )

    return {
        "label": label,
        "normalize": normalize,
        "gae_uses_edge_weight": use_edge_weight,
        "benign_baseline_median": _median(benign_errors),
        "benign_baseline_iqr": _iqr(benign_errors),
        "benign_n": len(benign_errors),
        "cells": cells,
        "per_graph": detail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Negative control: corruption vs benign AE scores")
    parser.add_argument("--sessions", type=Path, default=current_sessions_dir())
    parser.add_argument(
        "--use-edge-weight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass edge_weight into encoder when scoring (must match how the model was trained).",
    )
    parser.add_argument(
        "--norm-model",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--raw-model",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    parser.add_argument("--test-ratio", type=float, default=TEST_RATIO)
    parser.add_argument("--window-sec", type=float, default=DEFAULT_WINDOW_SEC)
    args = parser.parse_args()

    ver = current_dataset_version()
    if args.use_edge_weight:
        default_root = REPO_ROOT / f"abrg/output/norm_ab_{ver}_weighted"
        if args.output_dir is None:
            args.output_dir = REPO_ROOT / f"abrg/output/negative_control_{ver}_weighted"
    else:
        default_root = REPO_ROOT / f"abrg/output/norm_ab_{ver}"
        if args.output_dir is None:
            args.output_dir = REPO_ROOT / f"abrg/output/negative_control_{ver}"

    if args.norm_model is None:
        args.norm_model = default_root / "normalized_v021/gae_corpus_model.pt"
    if args.raw_model is None:
        args.raw_model = default_root / "raw_pre_v021/gae_corpus_model.pt"

    for p in (args.norm_model, args.raw_model):
        if not p.is_file():
            raise SystemExit(f"Missing model: {p}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Building corpus from {args.sessions} "
        f"(edge_weight_in_encoder={args.use_edge_weight}) ..."
    )
    records = build_corpus_graphs(
        args.sessions.resolve(),
        window_mode=WindowMode.TIME_SEC,
        window_sec=args.window_sec,
        snapshots=True,
    )
    train_recs, test_recs, train_apps, test_apps = split_train_test_by_app(
        records, args.test_ratio, args.seed
    )
    # Impossible edges: pairs never seen in the full benign corpus (all buildable graphs)
    observed = corpus_observed_edges(records)
    imposs = impossible_pairs(observed)
    print(
        f"Test: {len(test_recs)} snaps / {len(test_apps)} apps | "
        f"observed directed pairs={len(observed)} | impossible={len(imposs)} "
        f"(of {N_NODES * (N_NODES - 1)} possible)"
    )

    results = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": current_dataset_version(),
        "seed": args.seed,
        "use_edge_weight": args.use_edge_weight,
        "test_apps": test_apps,
        "test_snapshots": len(test_recs),
        "observed_directed_pairs": len(observed),
        "impossible_directed_pairs": len(imposs),
        "note": (
            "Eval uses deterministic recon_loss (all directed non-edges as negatives). "
            f"edge_weight_in_encoder={args.use_edge_weight}. "
            "Per-cell AUC uses n_eligible benign vs n_eligible corrupted (same support). "
            "Corruptions are never pooled."
        ),
        "models": {},
    }

    for label, path, normalize in (
        ("normalized_v021", args.norm_model, True),
        ("raw_pre_v021", args.raw_model, False),
    ):
        print(f"\n=== {label} ({path}) ===")
        model, ckpt = load_model(path)
        trained_with = ckpt.get("use_edge_weight") if isinstance(ckpt, dict) else None
        if trained_with is not None and bool(trained_with) != bool(args.use_edge_weight):
            print(
                f"  WARNING: checkpoint use_edge_weight={trained_with} "
                f"but scoring use_edge_weight={args.use_edge_weight}"
            )
        arm = score_arm(
            label=label,
            normalize=normalize,
            model=model,
            test_recs=test_recs,
            impossible_pool=imposs,
            seed=args.seed,
            use_edge_weight=args.use_edge_weight,
        )
        results["models"][label] = {
            k: v for k, v in arm.items() if k != "per_graph"
        }
        (args.output_dir / f"{label}_per_graph.json").write_text(
            json.dumps(arm["per_graph"], indent=2), encoding="utf-8"
        )
        print(
            f"  benign baseline median={arm['benign_baseline_median']:.4f} "
            f"(n={arm['benign_n']})"
        )
        for corr, cell in arm["cells"].items():
            print(
                f"  {corr:22s}  n={cell['n_eligible']}/{cell['n_test_pool']}  "
                f"medδ={cell['median_delta']:+.4f} "
                f"(IQR {cell['iqr_delta']:.4f})  AUC={cell['auc']:.3f}  "
                f"win={cell['wins']}/{cell['n_eligible']} ({cell['win_rate']:.1%})  "
                f"W p={cell['wilcoxon_p_greater']:.3g}  "
                f"skipped={cell.get('skipped_unchanged', 0)}"
            )

    out_json = args.output_dir / "negative_control_results.json"
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Compact table for thesis-style reading
    lines = [
        "Negative control — benign test corruptions (not pooled)",
        f"Dataset={current_dataset_version()} seed={args.seed} "
        f"test_snaps={len(test_recs)} apps={len(test_apps)} "
        f"edge_weight_in_encoder={args.use_edge_weight}",
        "",
        f"{'model':18s} {'corruption':22s} {'n':>7s} {'medδ':>8s} {'IQRδ':>8s} "
        f"{'AUC':>6s} {'win':>14s} {'W_p':>9s}",
        "-" * 100,
    ]
    for label, arm in results["models"].items():
        lines.append(
            f"{label:18s} {'BENIGN_BASELINE':22s} "
            f"{arm['benign_n']:7d} "
            f"{arm['benign_baseline_median']:8.4f} "
            f"{arm['benign_baseline_iqr']:8.4f} {'—':>6s} "
            f"{'—':>14s} {'—':>9s}"
        )
        for corr, cell in arm["cells"].items():
            win_s = f"{cell['wins']}/{cell['n_eligible']} ({cell['win_rate']:.0%})"
            lines.append(
                f"{label:18s} {corr:22s} "
                f"{cell['n_eligible']:7d} "
                f"{cell['median_delta']:+8.4f} {cell['iqr_delta']:8.4f} "
                f"{cell['auc']:6.3f} {win_s:>14s} {cell['wilcoxon_p_greater']:9.3g}"
            )
        lines.append("")
    lines.append(results["note"])
    summary = "\n".join(lines) + "\n"
    (args.output_dir / "negative_control_summary.txt").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
