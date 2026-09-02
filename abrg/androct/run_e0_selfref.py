"""
E0 — Self-reference windowed detection (Chapter A addition).

NO trained neural model. Reuses Run 6 Part 3 Arm B N=8 construction
(partition_mapped_indices, always-8 slots). Regenerates tensors via the
identical builder path when the Arm B snap cache was not persisted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier

from abrg.androct.categorize import _PRIORITY
from abrg.androct.graph_build import (
    assert_recency_unpopulated,
    assert_universe,
    partition_mapped_indices,
    update_graph_sequence,
)
from abrg.androct.paths import androct_run2_output_dir, androct_run6_output_dir
from abrg.androct.run2_corpus import load_corpus_cache, static_cache_dir, _static_path
from abrg.androct.run_gae_run2 import (
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    SEED,
    TEST_RATIO,
    _auc_with_bootstrap,
    _dist,
    split_apps,
)
from abrg.androct.run_gae_run3_5 import _stratified_split
from abrg.api_category_map import HOOK_API_TO_CATEGORY, categorize_callee
from abrg.apigraph.split import _sha_digest
from abrg.config import K_BURST
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.graph import build_initial_graph
from abrg.registry import DROPPED_CATEGORIES, GRAPH_CATEGORY_UNIVERSE
from abrg.static import StaticReport, zero_static_report

N_PARTS = 8
N_REF = 6
N_TEST = 2
N_NODES = 22
FLOOR_MAPPED = 0.7025
EXPECTED_DIGEST_PREFIX = "6129eb13d6a4"
SEQ_DIR = Path("abrg/output/androct_2017/apigraph/cache/sequences")
UNIVERSE = frozenset(GRAPH_CATEGORY_UNIVERSE)

assert len(GRAPH_CATEGORY_UNIVERSE) == N_NODES
assert node_feature_dim() == 10


def _stable_app_seed(app_id: str) -> int:
    """seed = 42 + hash(app_id) with a process-stable hash."""
    h = int(hashlib.sha256(app_id.encode("utf-8")).hexdigest()[:8], 16)
    return SEED + (h % (2**31 - 1))


@lru_cache(maxsize=500_000)
def _map_callee(callee: str) -> str | None:
    cls, _, meth = callee.rpartition(".")
    if not cls or not meth:
        return None
    simple = f"{cls.split('.')[-1]}.{meth}"
    exact = HOOK_API_TO_CATEGORY.get(simple)
    if exact and exact in UNIVERSE:
        return exact
    cats = categorize_callee(cls, meth) - DROPPED_CATEGORIES
    cats &= UNIVERSE
    if not cats:
        return None
    for pref in _PRIORITY:
        if pref in cats:
            return pref
    return sorted(cats)[0]


def _load_static(sha: str) -> StaticReport:
    sp = _static_path(static_cache_dir(androct_run2_output_dir()), sha)
    if not sp.is_file():
        return zero_static_report(sha)
    payload = torch.load(sp, map_location="cpu", weights_only=False)
    if payload.get("ok") and payload.get("report") is not None:
        return payload["report"]
    return zero_static_report(sha)


def _adj_matrix(edge_index: torch.Tensor, edge_weight: torch.Tensor) -> np.ndarray:
    A = np.zeros((N_NODES, N_NODES), dtype=np.float64)
    if edge_index.numel() == 0:
        return A
    src = edge_index[0].cpu().numpy()
    dst = edge_index[1].cpu().numpy()
    w = edge_weight.cpu().numpy().astype(np.float64)
    for i, j, ww in zip(src, dst, w):
        A[int(i), int(j)] = float(ww)
    return A


def _build_snapshots_for_app(
    sha: str,
    label: str,
    categories: list[str],
    static: StaticReport,
    *,
    n_events: int,
) -> list[dict[str, Any]]:
    """Identical to run6_part3._build_snapshots (always N=8, empty ranges padded)."""
    events = categories
    ranges = (
        partition_mapped_indices(max(len(events), 1), N_PARTS)
        if events
        else [(0, 0)] * N_PARTS
    )
    if not events:
        ranges = [(0, 0)] * N_PARTS
    snaps: list[dict[str, Any]] = []
    for snap_idx, (start, end) in enumerate(ranges):
        chunk = events[start:end] if events else []
        graph = build_initial_graph(static_report=static)
        assert_universe(graph)
        if chunk:
            update_graph_sequence(graph, chunk, k_burst=K_BURST)
        assert_recency_unpopulated(graph)
        x, ei, ew, _ = graph_to_tensors(
            graph, normalize=True, edge_weight_channel="w_cum"
        )
        n_edges = sum(1 for _ in graph.iter_edges())
        snaps.append(
            {
                "sha256": sha,
                "label": label,
                "snap_idx": snap_idx,
                "n_mapped_in_snap": len(chunk),
                "n_edges": n_edges,
                "n_active": len(graph.active_nodes()),
                "x": x.cpu(),
                "edge_index": ei.cpu(),
                "edge_weight": ew.cpu(),
                "A": torch.from_numpy(_adj_matrix(ei, ew)).float(),
                "n_mapped_app": len(events),
                "n_events_app": int(n_events),
            }
        )
    while len(snaps) < N_PARTS:
        snaps.append(
            {
                "sha256": sha,
                "label": label,
                "snap_idx": len(snaps),
                "n_mapped_in_snap": 0,
                "n_edges": 0,
                "n_active": 0,
                "x": torch.zeros(N_NODES, node_feature_dim()),
                "edge_index": torch.zeros(2, 0, dtype=torch.long),
                "edge_weight": torch.zeros(0),
                "A": torch.zeros(N_NODES, N_NODES),
                "n_mapped_app": len(events),
                "n_events_app": int(n_events),
            }
        )
    return snaps[:N_PARTS]


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    n = len(s)
    k = (n - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] * (c - k) + s[c] * (k - f))


def _d_node(X: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Per-node aggregated |X-R| on node features [22,10] → [22]."""
    return np.abs(X - R).sum(axis=1)


def _d_adj(A: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Per-node row-aggregated |A-R| on adjacency [22,22] → [22]."""
    return np.abs(A - R).sum(axis=1)


def _ref_test_indices(mode: str, sha: str) -> tuple[list[int], list[int]]:
    idxs = list(range(N_PARTS))
    if mode == "PREFIX":
        return idxs[:N_REF], idxs[N_REF:]
    if mode == "SCATTERED":
        rng = random.Random(_stable_app_seed(sha))
        ref = sorted(rng.sample(idxs, N_REF))
        test = [i for i in idxs if i not in ref]
        return ref, test
    raise ValueError(mode)


def _size_matched_apps(
    apps: list[Any],
    n_mapped: dict[str, int],
) -> tuple[list[Any], dict[str, Any]]:
    """
    Restrict to apps whose n_mapped lies in the overlapping central mass of
    the two class distributions: [max(p10_b, p10_m), min(p90_b, p90_m)].
    """
    benign = [a for a in apps if a.label == "benign"]
    malware = [a for a in apps if a.label == "malware"]
    vb = np.array([n_mapped[a.sha256] for a in benign], dtype=np.float64)
    vm = np.array([n_mapped[a.sha256] for a in malware], dtype=np.float64)
    p10_b, p90_b = float(np.percentile(vb, 10)), float(np.percentile(vb, 90))
    p10_m, p90_m = float(np.percentile(vm, 10)), float(np.percentile(vm, 90))
    lo = max(p10_b, p10_m)
    hi = min(p90_b, p90_m)
    meta = {
        "benign_p10": p10_b,
        "benign_p90": p90_b,
        "malware_p10": p10_m,
        "malware_p90": p90_m,
        "overlap_lo": lo,
        "overlap_hi": hi,
        "overlap_empty": lo > hi,
    }
    if lo > hi:
        # No overlapping central 80% — fall back to full range intersection
        lo = max(float(vb.min()), float(vm.min()))
        hi = min(float(vb.max()), float(vm.max()))
        meta["fallback_full_range"] = True
        meta["overlap_lo"] = lo
        meta["overlap_hi"] = hi
    kept = [a for a in apps if lo <= n_mapped[a.sha256] <= hi]
    meta["n_kept_benign"] = sum(1 for a in kept if a.label == "benign")
    meta["n_kept_malware"] = sum(1 for a in kept if a.label == "malware")
    return kept, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="E0 self-reference (Arm B N=8)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("abrg/output/androct_2017/selfref"),
    )
    parser.add_argument(
        "--results-md",
        type=Path,
        default=Path("results/E0_selfref_summary.md"),
    )
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args()
    out = args.output_dir
    win_dir = out / "windows"
    dev_dir = out / "deviations"
    out.mkdir(parents=True, exist_ok=True)
    win_dir.mkdir(parents=True, exist_ok=True)
    dev_dir.mkdir(parents=True, exist_ok=True)

    # ── Spine ────────────────────────────────────────────────
    bundle = load_corpus_cache(androct_run2_output_dir())
    digest = _sha_digest(bundle.split)
    if not digest.startswith(EXPECTED_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {digest[:12]} ≠ prefix {EXPECTED_DIGEST_PREFIX}"
        )
    split = bundle.split
    n_tr, n_tb, n_tm = len(split["train"]), len(split["test_benign"]), len(split["test_malware"])
    if (n_tr, n_tb, n_tm) != (562, 141, 1700):
        raise SystemExit(f"STOP: split counts {n_tr}/{n_tb}/{n_tm} ≠ 562/141/1700")
    print(f"[E0] digest={digest[:12]}… split={n_tr}/{n_tb}/{n_tm}", flush=True)

    train_shas = {a.sha256 for a in split["train"]}
    eligible = list(bundle.eligible)
    if len(eligible) != 2403:
        raise SystemExit(f"STOP: eligible={len(eligible)} ≠ 2403")

    # ── Phase 1: load or rebuild window tensors ──────────────
    cache_pt = win_dir / "armb_n8_windows.pt"
    manifest_csv = win_dir / "manifest.csv"
    part3 = json.loads(
        (androct_run6_output_dir() / "part3_armB" / "comparison.json").read_text()
    )
    ref_ws = part3["primary"]["window_size_dist"]
    ref_deg = part3["primary"]["degenerate_snapshots"]

    if cache_pt.is_file() and not args.force_rebuild:
        print(f"[E0] loading cached windows {cache_pt}", flush=True)
        payload = torch.load(cache_pt, map_location="cpu", weights_only=False)
        snap_cache: dict[str, list[dict[str, Any]]] = payload["snap_cache"]
        build_note = payload.get(
            "build_note",
            "loaded from cache (regenerated via Arm B Part 3 builder path)",
        )
    else:
        print(
            "[E0] Arm B snap tensors were not persisted; regenerating via identical "
            "run6_part3 builder + apigraph sequences (exact n_mapped) …",
            flush=True,
        )
        snap_cache = {}
        mism = 0
        for i, app in enumerate(eligible):
            seq_path = SEQ_DIR / f"{app.sha256.upper()}.json"
            callees = json.loads(seq_path.read_text())
            cats = [c for c in (_map_callee(x) for x in callees) if c is not None]
            if len(cats) != int(app.n_mapped):
                mism += 1
                if mism <= 3:
                    print(f"  MISMATCH {app.sha256[:12]} {app.n_mapped} vs {len(cats)}")
            static = _load_static(app.sha256)
            snap_cache[app.sha256] = _build_snapshots_for_app(
                app.sha256,
                app.label,
                cats,
                static,
                n_events=int(app.n_events),
            )
            if (i + 1) % 200 == 0:
                print(f"  … snaps {i+1}/{len(eligible)}", flush=True)
        if mism:
            raise SystemExit(f"STOP: n_mapped mismatches={mism}")
        build_note = (
            "Regenerated: Arm B Part 3 did not persist snap_cache; built with "
            "partition_mapped_indices N=8, update_graph_sequence k=5, w_cum, "
            "shares-not-counts, static from run2 cache, categories from apigraph "
            "sequences with categorize_soot_callee-equivalent map (2403/2403 exact)."
        )
        torch.save(
            {
                "snap_cache": snap_cache,
                "digest": digest,
                "build_note": build_note,
                "utc": datetime.now(timezone.utc).isoformat(),
            },
            cache_pt,
        )
        print(f"[E0] cached → {cache_pt}", flush=True)

    # Phase 1 asserts
    n_ben = sum(1 for a in eligible if a.label == "benign")
    n_mal = sum(1 for a in eligible if a.label == "malware")
    assert n_ben == 703 and n_mal == 1700, (n_ben, n_mal)

    win_sizes = {"benign": [], "malware": []}
    zero_edge = {"benign": 0, "malware": 0}
    n_snaps = {"benign": 0, "malware": 0}
    lt8_nonempty: list[dict[str, Any]] = []
    manifest_rows = []

    for app in eligible:
        snaps = snap_cache[app.sha256]
        if len(snaps) != 8:
            raise SystemExit(f"STOP: {app.sha256} has {len(snaps)} windows ≠ 8")
        x0 = snaps[0]["x"]
        if tuple(x0.shape) != (22, 10):
            raise SystemExit(f"STOP: x shape {tuple(x0.shape)} ≠ (22,10)")
        if tuple(snaps[0]["A"].shape) != (22, 22):
            raise SystemExit(f"STOP: A shape {tuple(snaps[0]['A'].shape)}")
        counts = [int(s["n_mapped_in_snap"]) for s in snaps]
        n_nonempty = sum(1 for c in counts if c > 0)
        if n_nonempty < 8:
            lt8_nonempty.append(
                {
                    "sha256": app.sha256,
                    "label": app.label,
                    "n_mapped": int(app.n_mapped),
                    "n_nonempty_windows": n_nonempty,
                    "per_window": counts,
                }
            )
        for s in snaps:
            win_sizes[app.label].append(float(s["n_mapped_in_snap"]))
            n_snaps[app.label] += 1
            if int(s["n_edges"]) == 0:
                zero_edge[app.label] += 1
        scattered_seed = _stable_app_seed(app.sha256)
        manifest_rows.append(
            {
                "app_id": app.sha256,
                "label": app.label,
                "n_mapped_total": int(app.n_mapped),
                "per_window_mapped": ";".join(str(c) for c in counts),
                "scattered_seed": scattered_seed,
                "n_nonempty_windows": n_nonempty,
                "retained_lt8": n_nonempty < 8,
            }
        )

    with manifest_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        w.writeheader()
        w.writerows(manifest_rows)

    phase1 = {
        "n_benign": n_ben,
        "n_malware": n_mal,
        "n_windows_per_app": 8,
        "node_feature_dim": 10,
        "adjacency": "22x22",
        "build_note": build_note,
        "window_mapped": {
            lab: {
                "n": len(win_sizes[lab]),
                "median": _pct(win_sizes[lab], 50),
                "p25": _pct(win_sizes[lab], 25),
                "p75": _pct(win_sizes[lab], 75),
                "iqr": _pct(win_sizes[lab], 75) - _pct(win_sizes[lab], 25),
                "min": float(min(win_sizes[lab])),
                "ref_median": ref_ws[lab]["median"],
                "ref_iqr": ref_ws[lab]["iqr"],
                "matches_phase0_median": abs(_pct(win_sizes[lab], 50) - ref_ws[lab]["median"])
                < 1e-6,
            }
            for lab in ("benign", "malware")
        },
        "zero_edge_fraction": {
            lab: {
                "n_zero": zero_edge[lab],
                "n_snaps": n_snaps[lab],
                "frac": zero_edge[lab] / n_snaps[lab],
                "ref_frac": ref_deg[lab]["frac_zero_edges"],
            }
            for lab in ("benign", "malware")
        },
        "lt8_nonempty": {
            "n_benign": sum(1 for r in lt8_nonempty if r["label"] == "benign"),
            "n_malware": sum(1 for r in lt8_nonempty if r["label"] == "malware"),
            "apps": lt8_nonempty,
            "decision": (
                "RETAINED — empty-range windows carry static features and zero edges "
                "(Arm B Part 3 always-8-slots policy). Included in every downstream table."
            ),
        },
        "artifacts": {
            "windows": str(cache_pt),
            "manifest": str(manifest_csv),
            "armb_comparison": "abrg/output/androct_2017/run6/part3_armB/comparison.json",
        },
    }
    print(
        f"[E0] Phase1 benign med={phase1['window_mapped']['benign']['median']} "
        f"zero={phase1['zero_edge_fraction']['benign']['frac']:.4f} "
        f"lt8={phase1['lt8_nonempty']['n_benign']}",
        flush=True,
    )

    # ── Phase 2: reference + deviation ───────────────────────
    # Persist d for PREFIX and SCATTERED × node / adj
    # Structure: deviations/{mode}/{space}/{sha}_test{idx}.npy + index.csv

    def compute_deviations(mode: str) -> dict[str, Any]:
        rows = []
        d_store: dict[str, dict[str, list[np.ndarray]]] = {
            "node": {},
            "adj": {},
        }
        for app in eligible:
            snaps = snap_cache[app.sha256]
            ref_i, test_i = _ref_test_indices(mode, app.sha256)
            Xs = [snaps[i]["x"].numpy().astype(np.float64) for i in ref_i]
            As = [snaps[i]["A"].numpy().astype(np.float64) for i in ref_i]
            R_x = np.mean(np.stack(Xs, axis=0), axis=0)
            R_a = np.mean(np.stack(As, axis=0), axis=0)
            d_nodes = []
            d_adjs = []
            for ti in test_i:
                X = snaps[ti]["x"].numpy().astype(np.float64)
                A = snaps[ti]["A"].numpy().astype(np.float64)
                dn = _d_node(X, R_x)
                da = _d_adj(A, R_a)
                d_nodes.append(dn)
                d_adjs.append(da)
                for space, d in (("node", dn), ("adj", da)):
                    scalar = float(np.linalg.norm(d))
                    rows.append(
                        {
                            "sha256": app.sha256,
                            "label": app.label,
                            "partition": (
                                "train"
                                if app.sha256 in train_shas
                                else (
                                    "test_benign"
                                    if app.label == "benign"
                                    else "test_malware"
                                )
                            ),
                            "split_mode": mode,
                            "space": space,
                            "test_snap_idx": ti,
                            "n_mapped_app": int(app.n_mapped),
                            "n_mapped_in_snap": int(snaps[ti]["n_mapped_in_snap"]),
                            "scalar_L2": scalar,
                            "ref_indices": ";".join(str(i) for i in ref_i),
                            "scattered_seed": _stable_app_seed(app.sha256)
                            if mode == "SCATTERED"
                            else "",
                        }
                    )
            d_store["node"][app.sha256] = d_nodes
            d_store["adj"][app.sha256] = d_adjs
        return {"rows": rows, "d_store": d_store}

    mode_data = {}
    all_row_records = []
    for mode in ("PREFIX", "SCATTERED"):
        print(f"[E0] Phase2 deviations {mode} …", flush=True)
        mode_data[mode] = compute_deviations(mode)
        all_row_records.extend(mode_data[mode]["rows"])
        # persist d vectors
        for space in ("node", "adj"):
            sp = dev_dir / mode / space
            sp.mkdir(parents=True, exist_ok=True)
            for sha, vecs in mode_data[mode]["d_store"][space].items():
                np.save(sp / f"{sha}.npy", np.stack(vecs, axis=0))  # [2, 22]

    # Fit mu_benign per (mode, space) on TRAIN-BENIGN test-window d's only
    mu_benign: dict[tuple[str, str], np.ndarray] = {}
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            mats = []
            for a in split["train"]:
                for d in mode_data[mode]["d_store"][space][a.sha256]:
                    mats.append(d)
            mu = np.mean(np.stack(mats, axis=0), axis=0)
            mu_benign[(mode, space)] = mu
            np.save(dev_dir / f"mu_benign_{mode}_{space}.npy", mu)

    # Attach centroid scores to rows
    for row in all_row_records:
        mode, space = row["split_mode"], row["space"]
        sha = row["sha256"]
        # find which test window
        snaps_d = mode_data[mode]["d_store"][space][sha]
        ref_i, test_i = _ref_test_indices(mode, sha)
        pos = test_i.index(row["test_snap_idx"])
        d = snaps_d[pos]
        mu = mu_benign[(mode, space)]
        row["centroid_L2"] = float(np.linalg.norm(d - mu))

    dev_csv = dev_dir / "window_scores.csv"
    with dev_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_row_records[0].keys()))
        w.writeheader()
        w.writerows(all_row_records)
    print(f"[E0] Phase2 → {dev_csv}", flush=True)

    # ── Phase 3 helpers ──────────────────────────────────────
    def window_scores_for(
        mode: str, space: str, score_type: str, apps: list
    ) -> dict[str, list[float]]:
        """sha → [score_test0, score_test1]"""
        out: dict[str, list[float]] = {}
        key = "scalar_L2" if score_type == "SCALAR" else "centroid_L2"
        by_sha: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for row in all_row_records:
            if row["split_mode"] != mode or row["space"] != space:
                continue
            by_sha[row["sha256"]].append((row["test_snap_idx"], row[key]))
        for a in apps:
            pairs = sorted(by_sha[a.sha256])
            out[a.sha256] = [p[1] for p in pairs]
        return out

    def train_benign_window_scores(mode: str, space: str, score_type: str) -> list[float]:
        ws = window_scores_for(mode, space, score_type, split["train"])
        vals = []
        for a in split["train"]:
            vals.extend(ws[a.sha256])
        return vals

    def app_verdict_scores(
        win_scores: dict[str, list[float]],
        verdict: str,
        tau: float | None,
    ) -> dict[str, float]:
        out = {}
        for sha, sc in win_scores.items():
            if verdict == "MEAN":
                out[sha] = float(np.mean(sc))
            elif verdict == "MAX":
                out[sha] = float(np.max(sc))
            elif verdict == "FRACTION":
                assert tau is not None
                out[sha] = float(np.mean([1.0 if s > tau else 0.0 for s in sc]))
            else:
                raise ValueError(verdict)
        return out

    def eval_auc(
        scores_by_sha: dict[str, float],
        test_benign: list,
        test_malware: list,
    ) -> dict[str, Any]:
        scores = [scores_by_sha[a.sha256] for a in test_benign] + [
            scores_by_sha[a.sha256] for a in test_malware
        ]
        labels = [0] * len(test_benign) + [1] * len(test_malware)
        return _auc_with_bootstrap(scores, labels)

    def run_matrix(
        test_benign: list,
        test_malware: list,
        *,
        tag: str,
    ) -> list[dict[str, Any]]:
        rows = []
        for mode in ("PREFIX", "SCATTERED"):
            for score_type in ("SCALAR", "CENTROID"):
                for space in ("node", "adj"):
                    tb_win = train_benign_window_scores(mode, space, score_type)
                    tau95 = _pct(tb_win, 95)
                    win_all = window_scores_for(
                        mode, space, score_type, test_benign + test_malware
                    )
                    for verdict in ("MEAN", "MAX", "FRACTION"):
                        tau = tau95 if verdict == "FRACTION" else None
                        app_sc = app_verdict_scores(win_all, verdict, tau)
                        auc = eval_auc(app_sc, test_benign, test_malware)
                        # volume coupling
                        sc_list = [app_sc[a.sha256] for a in test_benign + test_malware]
                        mapped = [
                            float(a.n_mapped) for a in test_benign + test_malware
                        ]
                        labs = [a.label for a in test_benign + test_malware]
                        rho_b = _rho(
                            [app_sc[a.sha256] for a in test_benign],
                            [float(a.n_mapped) for a in test_benign],
                        )
                        rho_m = _rho(
                            [app_sc[a.sha256] for a in test_malware],
                            [float(a.n_mapped) for a in test_malware],
                        )
                        rows.append(
                            {
                                "tag": tag,
                                "split_mode": mode,
                                "score_type": score_type,
                                "verdict": verdict,
                                "space": space,
                                "auc": auc["auc"],
                                "auc_floor": auc["auc_floor"],
                                "direction": auc["direction"],
                                "ci95_floor_lo": auc["ci95_floor"][0],
                                "ci95_floor_hi": auc["ci95_floor"][1],
                                "clears_floor": bool(auc["auc_floor"] >= FLOOR_MAPPED),
                                "tau95": tau95 if verdict == "FRACTION" else "",
                                "rho_benign": rho_b,
                                "rho_malware": rho_m,
                                "n_test_benign": len(test_benign),
                                "n_test_malware": len(test_malware),
                            }
                        )
        return rows

    print("[E0] Phase3 raw matrix …", flush=True)
    matrix_raw = run_matrix(split["test_benign"], split["test_malware"], tag="raw")

    # Size-matched
    scored = split["test_benign"] + split["test_malware"]
    n_mapped_map = {a.sha256: int(a.n_mapped) for a in eligible}
    matched, size_meta = _size_matched_apps(scored, n_mapped_map)
    matched_b = [a for a in matched if a.label == "benign"]
    matched_m = [a for a in matched if a.label == "malware"]
    print(
        f"[E0] Phase5 size-matched n_benign={len(matched_b)} n_malware={len(matched_m)} "
        f"overlap=[{size_meta['overlap_lo']:.1f}, {size_meta['overlap_hi']:.1f}]",
        flush=True,
    )
    if len(matched_b) < 20 or len(matched_m) < 20:
        print(
            f"[E0] WARN: size-matched n small ({len(matched_b)}/{len(matched_m)}); "
            "still reporting as primary control.",
            flush=True,
        )
    matrix_matched = run_matrix(matched_b, matched_m, tag="size_matched")

    matrix_csv = out / "matrix_24.csv"
    with matrix_csv.open("w", newline="", encoding="utf-8") as f:
        fields = list(matrix_raw[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(matrix_raw)
        w.writerows(matrix_matched)

    # Tau sweep for FRACTION (PREFIX, SCALAR, node as primary curve; emit all)
    tau_sweep_rows = []
    for mode in ("PREFIX", "SCATTERED"):
        for score_type in ("SCALAR", "CENTROID"):
            for space in ("node", "adj"):
                tb_win = train_benign_window_scores(mode, space, score_type)
                win_all = window_scores_for(
                    mode, space, score_type, split["test_benign"] + split["test_malware"]
                )
                for p in range(50, 100):
                    tau = _pct(tb_win, float(p))
                    app_sc = app_verdict_scores(win_all, "FRACTION", tau)
                    auc = eval_auc(app_sc, split["test_benign"], split["test_malware"])
                    tau_sweep_rows.append(
                        {
                            "split_mode": mode,
                            "score_type": score_type,
                            "space": space,
                            "tau_percentile": p,
                            "tau": tau,
                            "auc_floor": auc["auc_floor"],
                            "direction": auc["direction"],
                        }
                    )
    tau_csv = out / "tau_sweep.csv"
    with tau_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(tau_sweep_rows[0].keys()))
        w.writeheader()
        w.writerows(tau_sweep_rows)

    # ── Phase 4: supervised ceiling ──────────────────────────
    print("[E0] Phase4 HGB ceiling …", flush=True)
    ceiling_rows = []
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            # stratified both-class split on eligible
            strat = _stratified_split(eligible, seed=SEED, test_ratio=TEST_RATIO)
            train_apps = strat["train"]
            test_apps = strat["test_benign"] + strat["test_malware"]

            def app_vec(a) -> np.ndarray:
                vecs = mode_data[mode]["d_store"][space][a.sha256]
                return np.concatenate(vecs, axis=0)  # 44-dim

            X_tr = np.stack([app_vec(a) for a in train_apps])
            y_tr = np.array([1 if a.label == "malware" else 0 for a in train_apps])
            X_te = np.stack([app_vec(a) for a in test_apps])
            y_te = np.array([1 if a.label == "malware" else 0 for a in test_apps])
            X_tr = np.nan_to_num(X_tr, nan=0.0)
            X_te = np.nan_to_num(X_te, nan=0.0)
            clf = HistGradientBoostingClassifier(
                max_depth=6,
                learning_rate=0.08,
                max_iter=300,
                random_state=SEED,
                early_stopping=True,
                validation_fraction=0.1,
                n_iter_no_change=20,
            )
            clf.fit(X_tr, y_tr)
            scores = clf.predict_proba(X_te)[:, 1].tolist()
            auc = _auc_with_bootstrap(scores, y_te.tolist())
            ceiling_rows.append(
                {
                    "split_mode": mode,
                    "space": space,
                    "auc": auc["auc"],
                    "auc_floor": auc["auc_floor"],
                    "direction": auc["direction"],
                    "ci95_floor_lo": auc["ci95_floor"][0],
                    "ci95_floor_hi": auc["ci95_floor"][1],
                    "n_train": len(train_apps),
                    "n_test": len(test_apps),
                    "label": "DIAGNOSTIC CAPACITY CEILING — not a proposed detector",
                }
            )
    ceiling_csv = out / "phase4_ceiling.csv"
    with ceiling_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ceiling_rows[0].keys()))
        w.writeheader()
        w.writerows(ceiling_rows)

    # ── Phase 5 remaining controls ───────────────────────────
    # Within-trace density trend
    density_by_idx = {"benign": defaultdict(list), "malware": defaultdict(list)}
    for app in eligible:
        for s in snap_cache[app.sha256]:
            density_by_idx[app.label][int(s["snap_idx"])].append(
                float(s["n_mapped_in_snap"])
            )
    density_trend = {
        lab: {
            str(i): {
                "mean": float(np.mean(density_by_idx[lab][i])),
                "median": float(np.median(density_by_idx[lab][i])),
                "n": len(density_by_idx[lab][i]),
            }
            for i in range(N_PARTS)
        }
        for lab in ("benign", "malware")
    }

    # Shuffled labels
    print("[E0] Phase5 shuffled labels …", flush=True)
    shuffle_rows = []
    rng_shuf = np.random.default_rng(SEED)
    for mode in ("PREFIX", "SCATTERED"):
        for score_type in ("SCALAR", "CENTROID"):
            for space in ("node", "adj"):
                for verdict in ("MEAN", "MAX", "FRACTION"):
                    tb_win = train_benign_window_scores(mode, space, score_type)
                    tau95 = _pct(tb_win, 95)
                    win_all = window_scores_for(
                        mode,
                        space,
                        score_type,
                        split["test_benign"] + split["test_malware"],
                    )
                    app_sc = app_verdict_scores(
                        win_all, verdict, tau95 if verdict == "FRACTION" else None
                    )
                    scores = [app_sc[a.sha256] for a in split["test_benign"]] + [
                        app_sc[a.sha256] for a in split["test_malware"]
                    ]
                    labels = [0] * len(split["test_benign"]) + [1] * len(
                        split["test_malware"]
                    )
                    labels_shuf = list(labels)
                    rng_shuf.shuffle(labels_shuf)
                    auc = _auc_with_bootstrap(scores, labels_shuf)
                    shuffle_rows.append(
                        {
                            "split_mode": mode,
                            "score_type": score_type,
                            "verdict": verdict,
                            "space": space,
                            "auc_floor": auc["auc_floor"],
                            "direction": auc["direction"],
                        }
                    )
    # Also shuffle ceiling once per mode/space
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            strat = _stratified_split(eligible, seed=SEED, test_ratio=TEST_RATIO)
            train_apps = strat["train"]
            test_apps = strat["test_benign"] + strat["test_malware"]

            def app_vec(a) -> np.ndarray:
                return np.concatenate(
                    mode_data[mode]["d_store"][space][a.sha256], axis=0
                )

            X_tr = np.nan_to_num(np.stack([app_vec(a) for a in train_apps]))
            y_tr = np.array([1 if a.label == "malware" else 0 for a in train_apps])
            X_te = np.nan_to_num(np.stack([app_vec(a) for a in test_apps]))
            y_te = np.array([1 if a.label == "malware" else 0 for a in test_apps])
            y_tr_s = y_tr.copy()
            y_te_s = y_te.copy()
            rng_shuf.shuffle(y_tr_s)
            rng_shuf.shuffle(y_te_s)
            clf = HistGradientBoostingClassifier(
                max_depth=6,
                learning_rate=0.08,
                max_iter=300,
                random_state=SEED,
                early_stopping=True,
                validation_fraction=0.1,
                n_iter_no_change=20,
            )
            clf.fit(X_tr, y_tr_s)
            scores = clf.predict_proba(X_te)[:, 1].tolist()
            auc = _auc_with_bootstrap(scores, y_te_s.tolist())
            shuffle_rows.append(
                {
                    "split_mode": mode,
                    "score_type": "HGB_CEILING",
                    "verdict": "DIAGNOSTIC",
                    "space": space,
                    "auc_floor": auc["auc_floor"],
                    "direction": auc["direction"],
                }
            )

    shuffle_csv = out / "shuffled_labels.csv"
    with shuffle_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(shuffle_rows[0].keys()))
        w.writeheader()
        w.writerows(shuffle_rows)

    # PREFIX - SCATTERED delta
    def key_row(r):
        return (r["score_type"], r["verdict"], r["space"])

    raw_by = {
        (r["split_mode"],) + key_row(r): r for r in matrix_raw
    }
    delta_rows = []
    for score_type in ("SCALAR", "CENTROID"):
        for verdict in ("MEAN", "MAX", "FRACTION"):
            for space in ("node", "adj"):
                p = raw_by[("PREFIX", score_type, verdict, space)]
                s = raw_by[("SCATTERED", score_type, verdict, space)]
                delta_rows.append(
                    {
                        "score_type": score_type,
                        "verdict": verdict,
                        "space": space,
                        "auc_floor_prefix": p["auc_floor"],
                        "auc_floor_scattered": s["auc_floor"],
                        "delta_prefix_minus_scattered": p["auc_floor"] - s["auc_floor"],
                        "direction_prefix": p["direction"],
                        "direction_scattered": s["direction"],
                    }
                )
    for space in ("node", "adj"):
        p = next(r for r in ceiling_rows if r["split_mode"] == "PREFIX" and r["space"] == space)
        s = next(
            r for r in ceiling_rows if r["split_mode"] == "SCATTERED" and r["space"] == space
        )
        delta_rows.append(
            {
                "score_type": "HGB_CEILING",
                "verdict": "DIAGNOSTIC",
                "space": space,
                "auc_floor_prefix": p["auc_floor"],
                "auc_floor_scattered": s["auc_floor"],
                "delta_prefix_minus_scattered": p["auc_floor"] - s["auc_floor"],
                "direction_prefix": p["direction"],
                "direction_scattered": s["direction"],
            }
        )
    delta_csv = out / "prefix_scattered_delta.csv"
    with delta_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(delta_rows[0].keys()))
        w.writeheader()
        w.writerows(delta_rows)

    # Gates
    ceil_floors = [r["auc_floor"] for r in ceiling_rows]
    ceil_max = max(ceil_floors)
    ceil_min = min(ceil_floors)
    if ceil_max >= 0.85:
        gate = "PROCEED_E2_STRONG"
        gate_note = f"Phase 4 ceiling max={ceil_max:.4f} ≥ 0.85 — representation carries signal."
    elif ceil_max >= 0.70:
        gate = "PROCEED_E2_WEAK"
        gate_note = (
            f"Phase 4 ceiling max={ceil_max:.4f} in [0.70, 0.85) — weak; "
            "expect one-class arms near the floor."
        )
    else:
        gate = "STOP"
        gate_note = (
            f"Phase 4 ceiling max={ceil_max:.4f} < 0.70 — self-deviation carries no "
            "class information under full supervision. Write the negative."
        )
    deltas = [r["delta_prefix_minus_scattered"] for r in delta_rows]
    mean_abs_delta = float(np.mean(np.abs(deltas)))
    if mean_abs_delta < 0.02 and ceil_max < 0.70:
        gate = "STOP_ORDER_NULL"
        gate_note += (
            f" Additionally |PREFIX−SCATTERED| mean={mean_abs_delta:.4f}≈0 with low ceiling "
            "— window order carries nothing."
        )

    matched_clear = any(r["clears_floor"] for r in matrix_matched)
    raw_clear = any(r["clears_floor"] for r in matrix_raw)

    # Persist summary json
    summary = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "digest": digest,
        "phase1": phase1,
        "gate": gate,
        "gate_note": gate_note,
        "ceiling_max": ceil_max,
        "ceiling_min": ceil_min,
        "mean_abs_prefix_scattered_delta": mean_abs_delta,
        "raw_any_clears_floor": raw_clear,
        "size_matched_any_clears_floor": matched_clear,
        "size_matched_n": {"benign": len(matched_b), "malware": len(matched_m)},
        "size_matched_meta": size_meta,
        "fraction_granularity": "{0, 0.5, 1} with 2 test windows — do not change split ratio",
        "limitation_app_balanced_fixed_W": (
            "App-balanced fixed-W variant was not evaluated; recorded as limitation. "
            "E0 uses N=8 Arm B construction only."
        ),
        "artifacts": {
            "windows": str(cache_pt),
            "manifest": str(manifest_csv),
            "window_scores": str(dev_csv),
            "matrix": str(matrix_csv),
            "ceiling": str(ceiling_csv),
            "tau_sweep": str(tau_csv),
            "shuffle": str(shuffle_csv),
            "delta": str(delta_csv),
            "density_trend": str(out / "density_trend.json"),
        },
    }
    (out / "density_trend.json").write_text(json.dumps(density_trend, indent=2) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # ── Markdown report ──────────────────────────────────────
    def fmt(x, nd=4):
        if isinstance(x, float):
            if math.isnan(x):
                return "nan"
            return f"{x:.{nd}f}"
        return str(x)

    lines: list[str] = []
    L = lines.append
    L("# E0 — Self-reference windowed detection")
    L("")
    L("No trained neural model. Arm B N=8 tensors / identical builder path. "
      "Phase 4 is a **diagnostic capacity ceiling**, not a proposed detector.")
    L("")
    L("## Spine")
    L("")
    L(f"- Digest: `{digest[:12]}…` (asserted `{EXPECTED_DIGEST_PREFIX}`)")
    L(f"- Split: {n_tr} / {n_tb} / {n_tm}")
    L(f"- Construction: N=8 fixed count, Arm B Part 3 always-8-slots")
    L(f"- Limitation: app-balanced fixed-W not evaluated (PROXY_VALID rejected mass-weighted fixed-W)")
    L("")
    L("## Phase 1 — Load and verify")
    L("")
    L(f"- {build_note}")
    L(f"- Apps: {n_ben} benign / {n_mal} malware; 8 windows/app; x∈ℝ^{{22×10}}; A∈ℝ^{{22×22}}")
    L("")
    L("| class | median mapped/win | IQR | Phase0 ref median | zero-edge frac | Phase0 ref |")
    L("|---|---:|---:|---:|---:|---:|")
    for lab in ("benign", "malware"):
        w = phase1["window_mapped"][lab]
        z = phase1["zero_edge_fraction"][lab]
        L(
            f"| {lab} | {fmt(w['median'],1)} | {fmt(w['iqr'],1)} | {fmt(w['ref_median'],1)} | "
            f"{fmt(z['frac'])} | {fmt(z['ref_frac'])} |"
        )
    L("")
    L(f"- Apps with <8 mapped-nonempty windows: "
      f"**{phase1['lt8_nonempty']['n_benign']} benign**, "
      f"{phase1['lt8_nonempty']['n_malware']} malware.")
    L(f"- Decision: {phase1['lt8_nonempty']['decision']}")
    L(f"- Artifacts: `{cache_pt}`, `{manifest_csv}`")
    L("")
    L("## Phase 3 — Raw 24-row matrix")
    L("")
    L("FRACTION granularity with 2 test windows: **{0, 0.5, 1}** only.")
    L(f"Floor = mapped_event_count **{FLOOR_MAPPED}**. μ_benign fit on train-benign test windows only.")
    L("")
    L("| split | score | verdict | space | auc_floor | direction | CI95 floor | clears_floor | ρ_benign | ρ_malware |")
    L("|---|---|---|---|---:|---|---|---|---:|---:|")
    for r in matrix_raw:
        L(
            f"| {r['split_mode']} | {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor'])} | {r['direction']} | "
            f"[{fmt(r['ci95_floor_lo'])}, {fmt(r['ci95_floor_hi'])}] | "
            f"{r['clears_floor']} | {fmt(r['rho_benign'],3)} | {fmt(r['rho_malware'],3)} |"
        )
    L("")
    L(f"Artifact: `{matrix_csv}` (tag=raw)")
    L("")
    L("## Phase 5.1 — Size-matched matrix (PRIMARY control)")
    L("")
    L(f"Overlapping central mass of class n_mapped distributions on the test set: "
      f"[max(p10_b,p10_m), min(p90_b,p90_m)] = "
      f"[{fmt(size_meta['overlap_lo'],1)}, {fmt(size_meta['overlap_hi'],1)}] "
      f"(benign p10/p90={fmt(size_meta['benign_p10'],1)}/{fmt(size_meta['benign_p90'],1)}; "
      f"malware p10/p90={fmt(size_meta['malware_p10'],1)}/{fmt(size_meta['malware_p90'],1)}). "
      f"Kept n_benign={len(matched_b)}, n_malware={len(matched_m)}.")
    L("")
    L("| split | score | verdict | space | auc_floor | direction | CI95 floor | clears_floor | ρ_benign | ρ_malware |")
    L("|---|---|---|---|---:|---|---|---|---:|---:|")
    for r in matrix_matched:
        L(
            f"| {r['split_mode']} | {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor'])} | {r['direction']} | "
            f"[{fmt(r['ci95_floor_lo'])}, {fmt(r['ci95_floor_hi'])}] | "
            f"{r['clears_floor']} | {fmt(r['rho_benign'],3)} | {fmt(r['rho_malware'],3)} |"
        )
    L("")
    L(f"Any cell clears floor? raw={raw_clear}, size_matched={matched_clear}")
    L("")
    L("## Phase 4 — Supervised ceiling (DIAGNOSTIC ONLY)")
    L("")
    L("HistGradientBoosting on concatenated test-window d vectors (44-dim), "
      "stratified both-class split seed=42. **Not a proposed detector.**")
    L("")
    L("| split_mode | space | auc_floor | direction | CI95 floor |")
    L("|---|---|---:|---|---|")
    for r in ceiling_rows:
        L(
            f"| {r['split_mode']} | {r['space']} | {fmt(r['auc_floor'])} | {r['direction']} | "
            f"[{fmt(r['ci95_floor_lo'])}, {fmt(r['ci95_floor_hi'])}] |"
        )
    L("")
    L(f"Ceiling range: [{fmt(ceil_min)}, {fmt(ceil_max)}]. Artifact: `{ceiling_csv}`")
    L("")
    L("## Phase 5 — Controls")
    L("")
    L("### 1. Size-matched — see matrix above (primary).")
    L("")
    L("### 2. Floor")
    L(f"Every row flagged `clears_floor` vs {FLOOR_MAPPED} (see matrices).")
    L("")
    L("### 3. Volume coupling")
    L("Spearman ρ(app score, n_mapped) per class — columns in matrices above.")
    L("")
    L("### 4. Within-trace density trend")
    L("")
    L("| snap_idx | benign mean mapped | malware mean mapped |")
    L("|---:|---:|---:|")
    for i in range(N_PARTS):
        L(
            f"| {i} | {fmt(density_trend['benign'][str(i)]['mean'],2)} | "
            f"{fmt(density_trend['malware'][str(i)]['mean'],2)} |"
        )
    L("")
    L(f"Artifact: `{out / 'density_trend.json'}`")
    L("")
    L("### 5. Shuffled labels")
    L("")
    L("| split | score | verdict | space | auc_floor |")
    L("|---|---|---|---|---:|")
    for r in shuffle_rows:
        L(
            f"| {r['split_mode']} | {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor'])} |"
        )
    L("")
    shuf_mean = float(np.mean([r["auc_floor"] for r in shuffle_rows]))
    L(f"Mean shuffled auc_floor={fmt(shuf_mean)} (expect ~0.50). Artifact: `{shuffle_csv}`")
    L("")
    L("### 6. PREFIX − SCATTERED delta")
    L("")
    L("| score | verdict | space | auc_floor PREFIX | auc_floor SCATTERED | Δ |")
    L("|---|---|---|---:|---:|---:|")
    for r in delta_rows:
        L(
            f"| {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor_prefix'])} | {fmt(r['auc_floor_scattered'])} | "
            f"{fmt(r['delta_prefix_minus_scattered'])} |"
        )
    L("")
    L(f"Mean |Δ|={fmt(mean_abs_delta)}. Artifact: `{delta_csv}`")
    L("")
    L("## Tau sweep (FRACTION)")
    L("")
    L(f"Full curve 50th–99th percentile in `{tau_csv}`. Snapshot at 95th is the FRACTION row in the matrix.")
    L("")
    L("## Gate")
    L("")
    L(f"**{gate}** — {gate_note}")
    L("")
    L("---")
    L("")
    L(f"Generated {summary['utc']}. Summary JSON: `{out / 'summary.json'}`.")

    args.results_md.parent.mkdir(parents=True, exist_ok=True)
    args.results_md.write_text("\n".join(lines) + "\n")
    print(f"[E0] wrote {args.results_md}", flush=True)
    print(f"[E0] GATE={gate}", flush=True)
    print(gate_note, flush=True)


if __name__ == "__main__":
    main()
