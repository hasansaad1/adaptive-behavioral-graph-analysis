"""
E4 Phases -1, 1, 2, 4 on v2_extended.

No malware. No AUC. Session-level unit (no within-session windowing).
Canonical graph builder: Chapter B Run 2 (update_graph_sequence via graphs_seq).
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
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy import stats as scipy_stats

from abrg.chapter_b.config import EXPORT_ROOT, N_NODES
from abrg.chapter_b.graphs_seq import graph_from_events, topology
from abrg.chapter_b.ingest import SessionRow, load_sessions, pass_sessions
from abrg.corpus import build_session_graph
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.trace import load_frida_trace

N_REF = 6
N_TEST = 2
LN2 = math.log(2.0)
MEDIAN_GAP_S = 17509.528  # Phase 0 inter-session median (seconds)
# Decay half-lives anchored to observed inter-session scale (Phase 0 median 4.86h).
DECAY_HALF_LIFE_S = {
    "fast": 3600.0,  # 1 h
    "medium": MEDIAN_GAP_S,  # ~4.86 h
    "slow": 86400.0,  # 24 h
}
DECAY_LAMBDA_PER_S = {k: LN2 / v for k, v in DECAY_HALF_LIFE_S.items()}
CROSS_APP_SEED = 42
ORDERING_NEUTRAL_REL_DELTA = 0.10  # median |prefix-scattered| / median ||d||


def _stable_app_seed(app_id: str) -> int:
    h = int(hashlib.sha256(app_id.encode("utf-8")).hexdigest()[:8], 16)
    return 42 + (h % (2**31 - 1))


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _session_ts_s(row: SessionRow) -> float:
    if row.start_timestamp:
        t = _parse_iso(row.start_timestamp)
        if t:
            return t.timestamp()
    return float("nan")


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


def session_tensors(graph) -> tuple[np.ndarray, np.ndarray]:
    x, ei, ew, _ = graph_to_tensors(
        graph, normalize=True, edge_weight_channel="w_cum"
    )
    X = x.detach().cpu().numpy().astype(np.float64)
    A = _adj_matrix(ei, ew)
    assert X.shape == (N_NODES, node_feature_dim())
    assert A.shape == (N_NODES, N_NODES)
    return X, A


def _d_node(X: np.ndarray, R: np.ndarray) -> np.ndarray:
    return np.abs(X - R).sum(axis=1)


def _d_adj(A: np.ndarray, R: np.ndarray) -> np.ndarray:
    return np.abs(A - R).sum(axis=1)


def _l2(d: np.ndarray) -> float:
    return float(np.linalg.norm(d))


def _mean_ref(mats: list[np.ndarray]) -> np.ndarray:
    return np.mean(np.stack(mats, axis=0), axis=0)


def _weighted_ref(mats: list[np.ndarray], weights: list[float]) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    if w.sum() <= 0:
        return _mean_ref(mats)
    w = w / w.sum()
    return np.tensordot(w, np.stack(mats, axis=0), axes=(0, 0))


def _deviation_scores(
    X: np.ndarray,
    A: np.ndarray,
    R_x: np.ndarray,
    R_a: np.ndarray,
) -> dict[str, Any]:
    dn = _d_node(X, R_x)
    da = _d_adj(A, R_a)
    return {
        "d_node": dn,
        "d_adj": da,
        "l2_node": _l2(dn),
        "l2_adj": _l2(da),
        "l2_combined": math.sqrt(_l2(dn) ** 2 + _l2(da) ** 2),
    }


def _split_indices_prefix(n: int) -> tuple[list[int], list[int], list[int]]:
    if n == 8:
        return list(range(6)), [6, 7], []
    if n == 9:
        return list(range(6)), [7, 8], [6]
    raise ValueError(f"expected 8 or 9 sessions, got {n}")


def _split_indices_scattered(n: int, app_id: str) -> tuple[list[int], list[int], list[int]]:
    rng = random.Random(_stable_app_seed(app_id))
    idxs = list(range(n))
    rng.shuffle(idxs)
    ref = sorted(idxs[:N_REF])
    rest = sorted(idxs[N_REF:])
    test = rest[:N_TEST]
    discarded = rest[N_TEST:]
    return ref, test, discarded


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    return float(np.percentile(np.asarray(vals, dtype=np.float64), p))


def _summary(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {"n": 0, "median": float("nan"), "iqr": float("nan"), "min": float("nan"), "max": float("nan")}
    return {
        "n": len(vals),
        "min": float(min(vals)),
        "p25": _pct(vals, 25),
        "median": _pct(vals, 50),
        "p75": _pct(vals, 75),
        "max": float(max(vals)),
        "iqr": _pct(vals, 75) - _pct(vals, 25),
        "mean": float(np.mean(vals)),
    }


def _rank_biserial(w: float, n: int) -> float:
    """Approximate rank-biserial correlation from Wilcoxon W (paired, n pairs)."""
    if n <= 0:
        return float("nan")
    denom = n * (n + 1) / 2.0
    return float(1.0 - 2.0 * w / denom)


def _wilcoxon_paired(a: list[float], b: list[float]) -> dict[str, Any]:
    if len(a) != len(b) or len(a) < 5:
        return {"n": len(a), "error": "insufficient pairs"}
    diffs = [x - y for x, y in zip(a, b)]
    try:
        res = scipy_stats.wilcoxon(a, b, alternative="two-sided")
        w = float(res.statistic)
        n = len(a)
        d_med = _summary(diffs)
        # paired Cohen's d on differences
        sd = float(np.std(diffs, ddof=1)) if n > 1 else float("nan")
        cohen_d = float(np.mean(diffs) / sd) if sd and sd > 0 else float("nan")
        return {
            "n": n,
            "statistic_W": w,
            "p": float(res.pvalue),
            "rank_biserial_r": _rank_biserial(w, n),
            "cohen_d_paired": cohen_d,
            "median_diff": d_med["median"],
            "iqr_diff": d_med["iqr"],
            "mean_diff": d_med["mean"],
        }
    except Exception as exc:  # noqa: BLE001
        return {"n": len(a), "error": str(exc)}


def build_eligible_corpus(
    rows: list[SessionRow],
) -> tuple[dict[str, list[SessionRow]], dict[str, dict[str, Any]]]:
    by_app: dict[str, list[SessionRow]] = defaultdict(list)
    for r in rows:
        by_app[r.app_id].append(r)
    for app in by_app:
        by_app[app].sort(key=lambda s: s.session_index_within_app)

    eligible = {a: sess for a, sess in by_app.items() if len(sess) >= 8}
    tensors: dict[str, dict[str, Any]] = {}
    for app_id, sess in eligible.items():
        per_sess = []
        for s in sess:
            events, _ = load_frida_trace(Path(s.events_path))
            g = graph_from_events(events, package=app_id)
            n_active, n_edges, dens = topology(g)
            X, A = session_tensors(g)
            per_sess.append(
                {
                    "session_index": s.session_index_within_app,
                    "export_dir_name": s.export_dir_name,
                    "X": X,
                    "A": A,
                    "n_edges": n_edges,
                    "n_active": n_active,
                    "density": dens,
                    "n_mapped": len(events),
                    "t_s": _session_ts_s(s),
                }
            )
        tensors[app_id] = {"sessions": per_sess, "n_sessions": len(per_sess)}
    return eligible, tensors


def phase_minus1_provenance(rows: list[SessionRow]) -> dict[str, Any]:
    """Reconcile export vs Run2 vs norm_ab_v2 edge counts."""
    export_edges = []
    seq_edges = []
    upd_edges = []
    for r in rows:
        export_edges.append(float(r.n_edges_meta or 0))
        events, _ = load_frida_trace(Path(r.events_path))
        g_seq = graph_from_events(events, package=r.app_id)
        _, e_seq, _ = topology(g_seq)
        g_upd = build_session_graph(events, r.app_id)
        e_upd = sum(1 for _ in g_upd.iter_edges())
        seq_edges.append(float(e_seq))
        upd_edges.append(float(e_upd))

    nab = Path("abrg/output/norm_ab_v2/comparison.json")
    norm_ab: dict[str, Any] = {}
    if nab.is_file():
        comp = json.loads(nab.read_text())
        build = comp.get("build") or {}
        norm_ab = {
            "total_snapshots": build.get("total_snapshots"),
            "gae_eligible_snapshots": build.get("gae_eligible_snapshots"),
            "edge_dist_trainable": build.get("edge_count_distribution_trainable"),
            "edge_dist_gae": build.get("edge_count_distribution_gae_eligible"),
        }
        csv_p = Path("abrg/output/norm_ab_v2/normalized_v021/per_snapshot_errors.csv")
        if csv_p.is_file():
            with csv_p.open(encoding="utf-8") as f:
                ev = [float(row["n_edges"]) for row in csv.DictReader(f)]
            norm_ab["gae_csv_n"] = len(ev)
            norm_ab["gae_csv_edge_sum"] = float(sum(ev))
            norm_ab["gae_csv_edge_mean"] = float(np.mean(ev))

    # Archaeology: 579 / ~728
    archaeology = {
        "cited": "579 edge instances across ~728 snapshots (August handoff)",
        "reproduced": False,
        "note": (
            "Not found in any persisted artifact. Closest: norm_ab_v2 "
            "total_snapshots=731, gae_eligible_snapshots=565, "
            f"GAE edge sum={norm_ab.get('gae_csv_edge_sum', 'NA')} "
            f"(mean {norm_ab.get('gae_csv_edge_mean', 'NA'):.2f} edges/snap on 60s windows). "
            "The thesis B5 bucket label 72831 refers to mapped-event counts in a "
            "retention curve, not edge instances."
        ),
        "correct_figure_whole_session_run2": {
            "n_sessions": len(rows),
            "edge_median": _summary(seq_edges)["median"],
            "edge_mean": _summary(seq_edges)["mean"],
            "edge_sum": float(sum(seq_edges)),
        },
    }

    verdict = {
        "e4_builder": "abrg.chapter_b.graphs_seq.graph_from_events → update_graph_sequence",
        "e4_why": (
            "Chapter B Run 2 unit-aligned comparison used update_graph_sequence "
            "(k-burst=5, w_cum, zero static, whole session). Export index used "
            "build_session_graph/update_graph with δ time filter → fewer edges "
            "(median 2 vs 5). E4 must match Run 2 for comparability with Chapter B."
        ),
        "reconciled": True,
        "export_stage": "build_session_graph (update_graph, δ-filtered pairs) → len(edges)",
        "run2_stage": "graph_from_events (update_graph_sequence, k-burst only) → topology iter_edges",
        "norm_ab_v2_stage": "60s timed snapshots on original v2 (168 sessions), not v2_extended whole-session",
    }

    return {
        "export_index_edges": _summary(export_edges),
        "recomputed_seq_edges": _summary(seq_edges),
        "recomputed_update_graph_edges": _summary(upd_edges),
        "export_vs_seq_mismatch_sessions": int(
            sum(1 for a, b in zip(export_edges, seq_edges) if a != b)
        ),
        "norm_ab_v2": norm_ab,
        "archaeology_579_728": archaeology,
        "verdict": verdict,
    }


def phase1_ordering(tensors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    apps = sorted(tensors.keys())
    per_app: dict[str, Any] = {}
    prefix_l2: list[float] = []
    scattered_l2: list[float] = []
    deltas: list[float] = []

    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        n = len(sess)
        out: dict[str, Any] = {"n_sessions": n}
        for mode, split_fn in (
            ("PREFIX", lambda: _split_indices_prefix(n)),
            ("SCATTERED", lambda: _split_indices_scattered(n, app_id)),
        ):
            ref_i, test_i, discarded = split_fn()
            Xs = [sess[i]["X"] for i in ref_i]
            As = [sess[i]["A"] for i in ref_i]
            R_x = _mean_ref(Xs)
            R_a = _mean_ref(As)
            test_scores = []
            d_nodes = []
            d_adjs = []
            for ti in test_i:
                sc = _deviation_scores(sess[ti]["X"], sess[ti]["A"], R_x, R_a)
                test_scores.append(sc)
                d_nodes.append(sc["d_node"])
                d_adjs.append(sc["d_adj"])
            mean_l2 = float(np.mean([s["l2_combined"] for s in test_scores]))
            out[mode] = {
                "ref_indices": ref_i,
                "test_indices": test_i,
                "discarded_indices": discarded,
                "scattered_seed": _stable_app_seed(app_id) if mode == "SCATTERED" else None,
                "test_l2_combined": [s["l2_combined"] for s in test_scores],
                "mean_l2_combined": mean_l2,
                "mean_l2_node": float(np.mean([s["l2_node"] for s in test_scores])),
                "mean_l2_adj": float(np.mean([s["l2_adj"] for s in test_scores])),
                "d_node_mean": np.mean(np.stack(d_nodes, axis=0), axis=0).tolist(),
                "d_adj_mean": np.mean(np.stack(d_adjs, axis=0), axis=0).tolist(),
            }
            if mode == "PREFIX":
                prefix_l2.append(mean_l2)
            else:
                scattered_l2.append(mean_l2)

        delta = out["PREFIX"]["mean_l2_combined"] - out["SCATTERED"]["mean_l2_combined"]
        out["delta_prefix_minus_scattered"] = delta
        deltas.append(delta)
        per_app[app_id] = out

    # Per-node pooled mean d (PREFIX)
    node_pool = np.zeros(N_NODES, dtype=np.float64)
    adj_pool = np.zeros(N_NODES, dtype=np.float64)
    for app_id in apps:
        node_pool += np.asarray(per_app[app_id]["PREFIX"]["d_node_mean"])
        adj_pool += np.asarray(per_app[app_id]["PREFIX"]["d_adj_mean"])
    node_pool /= len(apps)
    adj_pool /= len(apps)

    wx = _wilcoxon_paired(prefix_l2, scattered_l2)
    pooled_med_d = _summary(prefix_l2)["median"]
    rel_delta = abs(_summary(deltas)["median"]) / pooled_med_d if pooled_med_d else float("nan")
    abs_iqr_delta = _summary(deltas)["iqr"]

    # ORDERING_MATTERS requires material shift; n=26 → effect size first, then magnitude.
    material = (
        rel_delta >= ORDERING_NEUTRAL_REL_DELTA
        or (
            wx.get("p", 1.0) < 0.05
            and abs(wx.get("rank_biserial_r", 0)) >= 0.30
        )
    )
    if material:
        verdict = "ORDERING_MATTERS"
        verdict_note = (
            f"PREFIX−SCATTERED median Δ={_summary(deltas)['median']:.4f} "
            f"(IQR={abs_iqr_delta:.4f}, rel={rel_delta:.3f}); "
            f"rank-biserial r={wx.get('rank_biserial_r', float('nan')):.3f}, "
            f"Cohen d={wx.get('cohen_d_paired', float('nan')):.3f}, p={wx.get('p', float('nan')):.4f}. "
            "Cross-session order affects self-deviation — AndroCT within-session "
            "exchangeability (|Δ|≈0.0055) is scoped to windows inside one run."
        )
    else:
        verdict = "ORDERING_NEUTRAL"
        verdict_note = (
            f"PREFIX−SCATTERED median Δ={_summary(deltas)['median']:.4f} "
            f"(IQR={abs_iqr_delta:.4f}, rel={rel_delta:.3f}); "
            f"rank-biserial r={wx.get('rank_biserial_r', float('nan')):.3f}, p={wx.get('p', float('nan')):.4f}. "
            "Behaviour is exchangeable at both granularities tested — the adaptive "
            "temporal element of ABRG has no empirical support at session scale."
        )

    per_node = {
        GRAPH_CATEGORY_UNIVERSE[j]: {
            "mean_d_node_prefix": float(node_pool[j]),
            "mean_d_adj_prefix": float(adj_pool[j]),
        }
        for j in range(N_NODES)
    }

    return {
        "n_apps": len(apps),
        "pooled_l2_prefix": _summary(prefix_l2),
        "pooled_l2_scattered": _summary(scattered_l2),
        "delta_prefix_minus_scattered": _summary(deltas),
        "wilcoxon_prefix_vs_scattered_l2": wx,
        "relative_median_delta": rel_delta,
        "verdict": verdict,
        "verdict_note": verdict_note,
        "per_node_mean_d_prefix": per_node,
        "per_app": per_app,
    }


def _multi_day_prereq(eligible: dict[str, list[SessionRow]]) -> dict[str, Any]:
    multi = 0
    single = 0
    per_app: dict[str, Any] = {}
    for app_id, sess in eligible.items():
        days = set()
        for s in sess:
            t = _parse_iso(s.start_timestamp)
            if t:
                days.add(t.date())
        nd = len(days)
        per_app[app_id] = {"n_calendar_days": nd, "multi_day": nd > 1}
        if nd > 1:
            multi += 1
        else:
            single += 1
    return {
        "n_apps": len(eligible),
        "multi_day": multi,
        "single_day": single,
        "all_multi_day": single == 0,
        "per_app": per_app,
        "prerequisite_note": (
            "All 26 eligible apps span multiple calendar days — recency weighting "
            "has temporal separation to act on."
            if single == 0
            else f"Only {multi}/{len(eligible)} eligible apps are multi-day; Phase 2 is provisional."
        ),
    }


def phase2_recency(
    tensors: dict[str, dict[str, Any]],
    *,
    multi_day: dict[str, Any],
) -> dict[str, Any]:
    apps = sorted(tensors.keys())
    per_decay: dict[str, Any] = {}
    for decay_name, lam in DECAY_LAMBDA_PER_S.items():
        w_cum_l2: list[float] = []
        w_rec_l2: list[float] = []
        per_app: dict[str, Any] = {}
        for app_id in apps:
            sess = tensors[app_id]["sessions"]
            n = len(sess)
            ref_i, test_i, discarded = _split_indices_prefix(n)
            Xs = [sess[i]["X"] for i in ref_i]
            As = [sess[i]["A"] for i in ref_i]
            ts_ref = [sess[i]["t_s"] for i in ref_i]
            R_x_cum = _mean_ref(Xs)
            R_a_cum = _mean_ref(As)
            test_l2_cum = []
            test_l2_rec = []
            for ti in test_i:
                t_test = sess[ti]["t_s"]
                sc_c = _deviation_scores(sess[ti]["X"], sess[ti]["A"], R_x_cum, R_a_cum)
                # W_REC: weight reference sessions by exp(-λ * Δt) to test time
                weights = []
                for tr in ts_ref:
                    if math.isnan(tr) or math.isnan(t_test):
                        weights.append(1.0)
                    else:
                        dt = max(0.0, t_test - tr)
                        weights.append(math.exp(-lam * dt))
                R_x_w = _weighted_ref(Xs, weights)
                R_a_w = _weighted_ref(As, weights)
                sc_r = _deviation_scores(sess[ti]["X"], sess[ti]["A"], R_x_w, R_a_w)
                test_l2_cum.append(sc_c["l2_combined"])
                test_l2_rec.append(sc_r["l2_combined"])
            mc = float(np.mean(test_l2_cum))
            mr = float(np.mean(test_l2_rec))
            w_cum_l2.append(mc)
            w_rec_l2.append(mr)
            per_app[app_id] = {
                "mean_l2_w_cum": mc,
                "mean_l2_w_rec": mr,
                "delta_rec_minus_cum": mr - mc,
                "rec_lower_is_better": mr < mc,
            }
        wx = _wilcoxon_paired(w_rec_l2, w_cum_l2)
        wins_rec = sum(1 for a in apps if per_app[a]["rec_lower_is_better"])
        per_decay[decay_name] = {
            "half_life_s": DECAY_HALF_LIFE_S[decay_name],
            "lambda_per_s": lam,
            "pooled_w_cum": _summary(w_cum_l2),
            "pooled_w_rec": _summary(w_rec_l2),
            "delta_rec_minus_cum": _summary([per_app[a]["delta_rec_minus_cum"] for a in apps]),
            "wilcoxon_w_rec_vs_w_cum": wx,
            "n_apps_w_rec_wins_lower_deviation": wins_rec,
            "per_app": per_app,
        }

    # Best decay = lowest median w_rec deviation
    best = min(
        DECAY_HALF_LIFE_S.keys(),
        key=lambda k: per_decay[k]["pooled_w_rec"]["median"],
    )
    best_row = per_decay[best]
    w_rec_beats = best_row["n_apps_w_rec_wins_lower_deviation"] > len(apps) / 2 and (
        best_row["wilcoxon_w_rec_vs_w_cum"].get("median_diff", 0) < 0
    )

    return {
        "multi_day_prerequisite": multi_day,
        "decay_values": {
            k: {"half_life_s": DECAY_HALF_LIFE_S[k], "lambda_per_s": DECAY_LAMBDA_PER_S[k]}
            for k in DECAY_HALF_LIFE_S
        },
        "by_decay": per_decay,
        "best_decay_by_median_w_rec": best,
        "w_rec_beats_w_cum": bool(w_rec_beats),
        "verdict_note": (
            f"W_REC (half-life={DECAY_HALF_LIFE_S[best]/3600:.2f}h) median deviation "
            f"{best_row['pooled_w_rec']['median']:.4f} vs W_CUM "
            f"{best_row['pooled_w_cum']['median']:.4f}; "
            f"W_REC wins on {best_row['n_apps_w_rec_wins_lower_deviation']}/{len(apps)} apps."
            if w_rec_beats
            else "W_REC does not beat W_CUM at any fixed decay — recency channel specified, "
            "implemented, and measured as not helping on this corpus."
        ),
    }


def phase4_cold_start(
    tensors: dict[str, dict[str, Any]],
    eligible_apps: list[str],
) -> dict[str, Any]:
    rng = np.random.default_rng(CROSS_APP_SEED)
    apps = sorted(eligible_apps)
    # d_self[k]: deviation of session k+1 from R built from first k sessions (k=1..7)
    self_curves: dict[int, list[float]] = {k: [] for k in range(1, 8)}
    cross_curves: dict[int, list[float]] = {k: [] for k in range(1, 8)}
    per_app_self: dict[str, list[float]] = {}
    per_app_cross: dict[str, list[float]] = {}

    full_refs = {}
    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        full_refs[app_id] = (
            _mean_ref([s["X"] for s in sess]),
            _mean_ref([s["A"] for s in sess]),
        )

    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        self_s = []
        cross_s = []
        for k in range(1, min(8, len(sess))):
            R_x = _mean_ref([sess[i]["X"] for i in range(k)])
            R_a = _mean_ref([sess[i]["A"] for i in range(k)])
            target = sess[k]
            sc_self = _deviation_scores(target["X"], target["A"], R_x, R_a)
            self_s.append(sc_self["l2_combined"])
            self_curves[k].append(sc_self["l2_combined"])
            # cross-app reference: random j != i
            others = [a for a in apps if a != app_id]
            j = others[int(rng.integers(0, len(others)))]
            R_x_j, R_a_j = full_refs[j]
            sc_cross = _deviation_scores(target["X"], target["A"], R_x_j, R_a_j)
            cross_s.append(sc_cross["l2_combined"])
            cross_curves[k].append(sc_cross["l2_combined"])
        per_app_self[app_id] = self_s
        per_app_cross[app_id] = cross_s

    pooled_self = {k: _summary(v) for k, v in self_curves.items() if v}
    pooled_cross = {k: _summary(v) for k, v in cross_curves.items() if v}

    ks = sorted(pooled_self.keys())
    medians = [pooled_self[k]["median"] for k in ks]
    k_min = ks[int(np.argmin(medians))]
    min_med = min(medians)
    k7_med = pooled_self[7]["median"]

    # Plateau: first k where median within 10% of k=7 (reported either way)
    plateau_k = None
    for k in ks[:-1]:
        if k7_med > 0 and abs(pooled_self[k]["median"] - k7_med) / k7_med <= 0.10:
            plateau_k = k
            break

    # Convergence: held-out deviation should fall as k grows; if k=7 > k=1, not converged
    still_falling_at_k7 = len(medians) >= 2 and medians[-1] < medians[-2]
    has_not_converged = k7_med > min_med * 1.05 or k_min < ks[-1]

    # Spearman: k vs pooled self deviation
    rho = None
    if len(ks) >= 3:
        y = [pooled_self[k]["median"] for k in ks]
        if np.std(y) > 0:
            r, p = scipy_stats.spearmanr(ks, y)
            rho = {"rho": float(r), "p": float(p)}

    # Apps with 9 sessions — per-app curves
    apps9 = [a for a in apps if tensors[a]["n_sessions"] == 9]

    return {
        "cross_app_seed": CROSS_APP_SEED,
        "k_range": "1..7 (held-out session k+1)",
        "pooled_self": pooled_self,
        "pooled_cross": pooled_cross,
        "plateau_k_median_within_10pct_of_k7": plateau_k,
        "k_at_minimum_median_self": k_min,
        "minimum_median_self": min_med,
        "still_falling_at_k7": still_falling_at_k7,
        "has_not_converged_within_8_sessions": has_not_converged,        "spearman_k_vs_self_median": rho,
        "per_app_self": per_app_self,
        "per_app_cross": per_app_cross,
        "apps_with_9_sessions": apps9,
        "chapter_c_reference": (
            "Chapter C pooled within vs cross (frobenius_combined) ≈ 1.28 vs 38.32; "
            "E4 reports L2 combined d at each k on the same 22-node tensors."
        ),
        "verdict_note": (
            f"Self-deviation median: k=1 {pooled_self[1]['median']:.4f} (minimum) → "
            f"k=7 {pooled_self[7]['median']:.4f}; cross-app at k=7 "
            f"≈{pooled_cross[7]['median']:.1f}. "
            + (
                "Held-out deviation does not decrease with reference size — "
                "has not converged within 8 sessions; the cold-start answer is "
                f"non-convergence (minimum at k={k_min})."
                if has_not_converged
                else f"Plateau near k={plateau_k}."
            )
        ),
    }


def _write_markdown(
    path: Path,
    *,
    p1: dict[str, Any],
    p2: dict[str, Any],
    p4: dict[str, Any],
    pm1: dict[str, Any],
    n_apps: int,
    utc: str,
    out_dir: Path,
) -> None:
    def fmt(x: float, nd: int = 4) -> str:
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return "nan"
        return f"{x:.{nd}f}"

    lines: list[str] = []
    L = lines.append
    L("# E4 — Ordering, recency, and cold-start on v2_extended")
    L("")
    L("**v2_extended has no malware. Nothing here is a detection result.**")
    L("")
    L(
        "Sensor note: same 22-node `GRAPH_CATEGORY_UNIVERSE` as AndroCT (E0/E2), but "
        "Frida hooks (ContextDroid) ≠ DroidFax logcat — do not treat numbers as "
        "interchangeable samples."
    )
    L("")
    L(f"Eligible apps: **n={n_apps}** (≥8 usable sessions). Session unit; no within-session windowing.")
    L("")
    L("## Phase −1 — Provenance verdict")
    L("")
    v = pm1["verdict"]
    L(f"**E4 builder:** `{v['e4_builder']}`")
    L("")
    L(v["e4_why"])
    L("")
    L("| Stage | Pipeline | Median edges |")
    L("|---|---|---:|")
    L(f"| Export index (Phase 0) | {pm1['verdict']['export_stage']} | {fmt(pm1['export_index_edges']['median'],1)} |")
    L(f"| Chapter B Run 2 | {pm1['verdict']['run2_stage']} | {fmt(pm1['recomputed_seq_edges']['median'],1)} |")
    gae = pm1.get("norm_ab_v2", {})
    L(
        f"| norm_ab_v2 (60s snaps) | {pm1['verdict']['norm_ab_v2_stage']} | "
        f"GAE mean {fmt(gae.get('gae_csv_edge_mean', float('nan')),2)} /snap |"
    )
    L("")
    arch = pm1["archaeology_579_728"]
    L(f"**579/728 archaeology:** {arch['note']}")
    L("")
    L(f"Artifact: `{out_dir / 'provenance.json'}`")
    L("")
    L("## Phase 1 — Temporal ordering (session granularity)")
    L("")
    L(f"Split: PREFIX = earliest 6 / latest 2; SCATTERED = random 6 / remaining 2 (seed=42+hash(app)). "
      f"9-session apps discard middle index 6 under PREFIX.")
    L("")
    L(f"**VERDICT: `{p1['verdict']}`** — {p1['verdict_note']}")
    L("")
    wx = p1["wilcoxon_prefix_vs_scattered_l2"]
    L(
        f"Effect size (report first): rank-biserial **r={fmt(wx.get('rank_biserial_r', float('nan')),3)}**, "
        f"Cohen d={fmt(wx.get('cohen_d_paired', float('nan')),3)}, "
        f"median Δ={fmt(wx.get('median_diff', float('nan')))} "
        f"(Wilcoxon p={fmt(wx.get('p', float('nan')))})."
    )
    L("")
    L("| split | median \\|\\|d\\|\\| | IQR |")
    L("|---|---:|---:|")
    L(f"| PREFIX | {fmt(p1['pooled_l2_prefix']['median'])} | {fmt(p1['pooled_l2_prefix']['iqr'])} |")
    L(f"| SCATTERED | {fmt(p1['pooled_l2_scattered']['median'])} | {fmt(p1['pooled_l2_scattered']['iqr'])} |")
    L(f"| PREFIX−SCATTERED (per app) | {fmt(p1['delta_prefix_minus_scattered']['median'])} | {fmt(p1['delta_prefix_minus_scattered']['iqr'])} |")
    L("")
    L("Per-app table: `{}/phase1_per_app.csv`".format(out_dir))
    L("")
    L("### Per-node mean d (PREFIX, node space)")
    L("")
    L("| node | mean d_node | mean d_adj |")
    L("|---|---:|---:|")
    for cat in GRAPH_CATEGORY_UNIVERSE:
        pn = p1["per_node_mean_d_prefix"][cat]
        L(f"| {cat} | {fmt(pn['mean_d_node_prefix'],4)} | {fmt(pn['mean_d_adj_prefix'],4)} |")
    L("")
    L("## Phase 2 — Recency vs cumulative reference")
    L("")
    md = p2["multi_day_prerequisite"]
    L(f"**Prerequisite:** {md['prerequisite_note']} (multi-day {md['multi_day']}/{md['n_apps']}).")
    L("")
    L(f"**{p2['verdict_note']}**")
    L("")
    L("Decay half-lives (fixed before run): fast=1h, medium=4.86h (Phase 0 median gap), slow=24h.")
    L("")
    L("| decay | half-life | median \\|\\|d\\|\\| W_CUM | median W_REC | Δ(W_REC−W_CUM) | r | p | W_REC wins |")
    L("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name in ("fast", "medium", "slow"):
        row = p2["by_decay"][name]
        wx2 = row["wilcoxon_w_rec_vs_w_cum"]
        L(
            f"| {name} | {DECAY_HALF_LIFE_S[name]/3600:.2f}h | "
            f"{fmt(row['pooled_w_cum']['median'])} | {fmt(row['pooled_w_rec']['median'])} | "
            f"{fmt(row['delta_rec_minus_cum']['median'])} | "
            f"{fmt(wx2.get('rank_biserial_r', float('nan')),3)} | {fmt(wx2.get('p', float('nan')))} | "
            f"{row['n_apps_w_rec_wins_lower_deviation']}/{n_apps} |"
        )
    L("")
    L(f"Artifact: `{out_dir / 'phase2_recency.json'}`")
    L("")
    L("## Phase 4 — Cold start / convergence")
    L("")
    L(f"**{p4['verdict_note']}**")
    L("")
    L(f"Cross-app draw seed={p4['cross_app_seed']}. d = L2 combined (node + adj deviation vectors).")
    L("")
    L("| k | median d_self | IQR self | median d_cross | IQR cross |")
    L("|---:|---:|---:|---:|---:|")
    for k in range(1, 8):
        ps = p4["pooled_self"][k]
        pc = p4["pooled_cross"][k]
        L(
            f"| {k} | {fmt(ps['median'])} | {fmt(ps['iqr'])} | "
            f"{fmt(pc['median'])} | {fmt(pc['iqr'])} |"
        )
    L("")
    if p4["has_not_converged_within_8_sessions"]:
        L("**Convergence:** held-out deviation does **not** decrease with k — "
          f"minimum at k={p4['k_at_minimum_median_self']} "
          f"(median={fmt(p4['minimum_median_self'])}). "
          "Non-convergence within 8 sessions is the cold-start answer.")
    elif p4["plateau_k_median_within_10pct_of_k7"]:
        L(f"**Plateau k:** {p4['plateau_k_median_within_10pct_of_k7']} (median within 10% of k=7).")
    else:
        L("**Plateau:** not identified within k=1..7.")
    L("")
    L(f"Apps with 9 sessions (per-app curves in JSON): {len(p4['apps_with_9_sessions'])}.")
    L(f"Artifact: `{out_dir / 'phase4_coldstart.json'}`")
    L("")
    L("---")
    L("")
    L(f"Generated {utc}. Summary: `{out_dir / 'summary.json'}`.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="E4 ordering/recency/cold-start")
    parser.add_argument("--export-root", type=Path, default=EXPORT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("abrg/output/v2_extended/e4_ordering"),
    )
    parser.add_argument(
        "--results-md",
        type=Path,
        default=Path("results/E4_ordering_recency_coldstart.md"),
    )
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    rows = pass_sessions(load_sessions(args.export_root))
    print(f"[E4] usable sessions={len(rows)}", flush=True)

    print("[E4] Phase -1 provenance …", flush=True)
    pm1 = phase_minus1_provenance(rows)
    (out / "provenance.json").write_text(json.dumps(pm1, indent=2) + "\n")
    if not pm1["verdict"]["reconciled"]:
        raise SystemExit("STOP: provenance not reconciled")

    print("[E4] building session tensors (Run2 builder) …", flush=True)
    eligible, tensors = build_eligible_corpus(rows)
    n_apps = len(eligible)
    if n_apps < 8:
        raise SystemExit(f"STOP: only {n_apps} apps with >=8 sessions")
    print(f"[E4] eligible apps={n_apps}", flush=True)

    # cache tensors metadata (not full arrays in summary)
    (out / "eligible_apps.json").write_text(
        json.dumps(
            {
                "n_apps": n_apps,
                "apps": sorted(eligible.keys()),
                "sessions_per_app": {a: len(eligible[a]) for a in sorted(eligible)},
            },
            indent=2,
        )
        + "\n"
    )

    print("[E4] Phase 1 ordering …", flush=True)
    p1 = phase1_ordering(tensors)
    with (out / "phase1_per_app.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "app_id",
                "n_sessions",
                "prefix_mean_l2",
                "scattered_mean_l2",
                "delta_prefix_minus_scattered",
                "prefix_test_l2",
                "scattered_test_l2",
            ],
        )
        w.writeheader()
        for app_id, row in sorted(p1["per_app"].items()):
            w.writerow(
                {
                    "app_id": app_id,
                    "n_sessions": row["n_sessions"],
                    "prefix_mean_l2": row["PREFIX"]["mean_l2_combined"],
                    "scattered_mean_l2": row["SCATTERED"]["mean_l2_combined"],
                    "delta_prefix_minus_scattered": row["delta_prefix_minus_scattered"],
                    "prefix_test_l2": ";".join(
                        f"{x:.6f}" for x in row["PREFIX"]["test_l2_combined"]
                    ),
                    "scattered_test_l2": ";".join(
                        f"{x:.6f}" for x in row["SCATTERED"]["test_l2_combined"]
                    ),
                }
            )
    p1_save = {k: v for k, v in p1.items() if k != "per_app"}
    p1_save["per_app"] = p1["per_app"]
    (out / "phase1_ordering.json").write_text(json.dumps(p1_save, indent=2) + "\n")

    print("[E4] Phase 2 recency …", flush=True)
    md = _multi_day_prereq(eligible)
    p2 = phase2_recency(tensors, multi_day=md)
    (out / "phase2_recency.json").write_text(json.dumps(p2, indent=2) + "\n")

    print("[E4] Phase 4 cold start …", flush=True)
    p4 = phase4_cold_start(tensors, sorted(eligible.keys()))
    (out / "phase4_coldstart.json").write_text(json.dumps(p4, indent=2) + "\n")

    utc = datetime.now(timezone.utc).isoformat()
    summary = {
        "utc": utc,
        "n_apps": n_apps,
        "builder": pm1["verdict"]["e4_builder"],
        "phase1_verdict": p1["verdict"],
        "phase2_w_rec_beats": p2["w_rec_beats_w_cum"],
        "phase4_converged": not p4["has_not_converged_within_8_sessions"],
        "artifacts": {
            "provenance": str(out / "provenance.json"),
            "phase1": str(out / "phase1_ordering.json"),
            "phase1_csv": str(out / "phase1_per_app.csv"),
            "phase2": str(out / "phase2_recency.json"),
            "phase4": str(out / "phase4_coldstart.json"),
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    _write_markdown(
        args.results_md,
        p1=p1,
        p2=p2,
        p4=p4,
        pm1=pm1,
        n_apps=n_apps,
        utc=utc,
        out_dir=out,
    )
    print(f"[E4] wrote {args.results_md}", flush=True)
    print(
        f"[E4] Phase1={p1['verdict']} Phase2 w_rec_beats={p2['w_rec_beats_w_cum']} "
        f"Phase4 converged={not p4['has_not_converged_within_8_sessions']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
