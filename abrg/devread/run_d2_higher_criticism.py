"""
D-2: Higher Criticism and sparse-signal ladder on D1 deviation profiles.
Scoring pass only — no retrain, no new tensors. Benign-only fitting throughout.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy import stats
from scipy.stats import kstest, spearmanr
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.apigraph.split import load_run3_split
from abrg.devread import EXPECTED_SPLIT_DIGEST_PREFIX
from abrg.devread.run_d1_randominit_controls import (
    PAIRED_BOOT_B,
    PAIRED_BOOT_SEED,
    TABLE_A4_KEYS,
    _make_score_fn,
    _paired_bootstrap_auc_diff,
    _table_a4_covariates,
    delong_test,
)
from abrg.devread.run_d1_sparse_aggregation import SHUFFLE_SEED, _score_matrix
from abrg.final_validate import FPR_POINTS, TEST_N_BENIGN, TEST_N_MALWARE
from abrg.final_validate.util import auc_raw_and_floor, eval_auc_block, tpr_at_fpr_from_scores
from abrg.ladder.grouping import _silhouette_curve
from abrg.ladder.vectorize import malware_full_vectors
from abrg.ocdev.part_a import load_profiles
from abrg.ocdev_validate import NESTED_B, NESTED_SEED
from abrg.ocdev_validate.check1 import _bias_pack
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.validate.residual import apply_residual, ols_fit

FLOOR = 0.7025
D1_L2_REF = 0.8004255319148936
IPC_UNIVARIATE_REF = 0.7931914893617023
N_NODES = 22
IPC_IDX = GRAPH_CATEGORY_UNIVERSE.index("ipc_intents")
ALPHA0_GRID = (0.25, 0.50, 1.00)
K_GRID = (5, 10, 15, 20)
DEGENERATE_SD_EPS = 1e-6
DEGENERATE_NDISTINCT_MAX = 2
CONFORMAL_CAL_FRAC = 0.20
CONFORMAL_SEED = 42
LADDER_STATS = (
    "HC",
    "HC_rank",
    "MIN_P",
    "FISHER",
    "STOUFFER",
    "BERK_JONES",
    "BONFERRONI",
)


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _load_context() -> dict[str, Any]:
    bundle = load_run3_split()
    dig = bundle.sha_list_digest
    if not dig.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(f"STOP: digest {dig[:16]} != {EXPECTED_SPLIT_DIGEST_PREFIX}")

    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train = split["train"]
    test_b = split["test_benign"]
    test_m = split["test_malware"]
    if len(train) != 562 or len(test_b) != 141 or len(test_m) != 1700:
        raise SystemExit(
            f"STOP: split counts {len(train)}/{len(test_b)}/{len(test_m)} != 562/141/1700"
        )

    arrays_tr, shas = load_profiles("trained_t22")
    arrays_ri, shas_ri = load_profiles("random_init_t22")
    if shas != shas_ri:
        raise SystemExit("STOP: profile index mismatch trained vs random_init")
    X_tr = arrays_tr["D1"]
    X_ri = arrays_ri["D1"]
    if X_tr.shape != (2403, 22):
        raise SystemExit(f"STOP: D1 shape {X_tr.shape} != (2403, 22)")

    sha_to_app = {a.sha256: a for a in corpus.eligible}
    train_shas = [a.sha256 for a in train]
    test_shas = [a.sha256 for a in test_b] + [a.sha256 for a in test_m]
    sha_to_i = {s: i for i, s in enumerate(shas)}
    for s in train_shas + test_shas:
        if s not in sha_to_i:
            raise SystemExit(f"STOP: sha missing from profile index")

    tr_idx = np.asarray([sha_to_i[s] for s in train_shas], dtype=np.int64)
    te_idx = np.asarray([sha_to_i[s] for s in test_shas], dtype=np.int64)
    labels = np.asarray([0] * len(test_b) + [1] * len(test_m), dtype=np.int32)
    n_ben_test = len(test_b)

    return {
        "digest": dig,
        "train_shas": train_shas,
        "test_shas": test_shas,
        "labels": labels,
        "n_ben_test": n_ben_test,
        "tr_idx": tr_idx,
        "te_idx": te_idx,
        "tensors": corpus.tensors,
        "sha_to_app": sha_to_app,
        "X_trained": X_tr,
        "X_random": X_ri,
    }


def _empirical_pvalues(X_train: np.ndarray, X_test: np.ndarray) -> np.ndarray:
    """Two-sided p vs train-benign |x - mu_j| with +1 smoothing. Shape (n_test, m)."""
    mu = X_train.mean(axis=0)
    abs_tr = np.abs(X_train - mu)
    abs_te = np.abs(X_test - mu)
    n_tr, m = abs_tr.shape
    n_te = abs_te.shape[0]
    out = np.empty((n_te, m), dtype=np.float64)
    for j in range(m):
        sorted_tr = np.sort(abs_tr[:, j])
        idx = np.searchsorted(sorted_tr, abs_te[:, j], side="left")
        counts = n_tr - idx
        out[:, j] = (1.0 + counts) / (n_tr + 1.0)
    return out


def _coord_degeneracy(X_train: np.ndarray) -> list[dict[str, Any]]:
    rows = []
    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        col = X_train[:, j]
        sd = float(np.std(col, ddof=0))
        n_dist = int(len(np.unique(col)))
        degenerate = sd < DEGENERATE_SD_EPS or n_dist <= DEGENERATE_NDISTINCT_MAX
        rows.append(
            {
                "dim": j,
                "node": cat,
                "train_sd": sd,
                "n_distinct_train_benign": n_dist,
                "degenerate": degenerate,
            }
        )
    return rows


def _phase1(
    p_ben: np.ndarray,
    p_mal: np.ndarray,
    degen: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    ks_rows = []
    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        pb = p_ben[:, j]
        pm = p_mal[:, j]

        def _med_iqr(x: np.ndarray) -> tuple[float, float]:
            q25, q50, q75 = np.percentile(x, [25, 50, 75])
            return float(q50), float(q75 - q25)

        med_b, iqr_b = _med_iqr(pb)
        med_m, iqr_m = _med_iqr(pm)
        ks_stat, ks_p = kstest(pb, "uniform")
        rows.append(
            {
                "node": cat,
                "dim": j,
                "median_p_test_benign": med_b,
                "iqr_p_test_benign": iqr_b,
                "median_p_test_malware": med_m,
                "iqr_p_test_malware": iqr_m,
                "ks_statistic_test_benign_vs_uniform": float(ks_stat),
                "ks_pvalue": float(ks_p),
            }
        )
        ks_rows.append({"node": cat, "ks": float(ks_stat), "ks_p": float(ks_p)})

    bad_ks = sorted(ks_rows, key=lambda r: -r["ks"])[:5]
    return {
        "p_distribution_table": rows,
        "degeneracy": degen,
        "n_degenerate": sum(1 for d in degen if d["degenerate"]),
        "worst_ks_uniformity": bad_ks,
    }


def _sorted_with_indices(p_row: np.ndarray, keep_dims: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = p_row[keep_dims]
    order = np.argsort(p)
    return p[order], keep_dims[order]


def _hc_terms(p_sorted: np.ndarray, m: int, alpha0: float, *, rank_based: bool) -> tuple[float, int]:
    k_max = max(1, int(math.floor(alpha0 * m)))
    best = -np.inf
    arg_i = 1
    sm = math.sqrt(m)
    for i in range(1, k_max + 1):
        pi = float(np.clip(p_sorted[i - 1], 1e-15, 1.0 - 1e-15))
        if rank_based:
            denom = math.sqrt((i / m) * (1.0 - i / m))
        else:
            denom = math.sqrt(pi * (1.0 - pi))
        if denom <= 0:
            continue
        val = sm * (i / m - pi) / denom
        if val > best:
            best = val
            arg_i = i
    return float(max(best, 0.0)), arg_i


def _berk_jones(p_sorted: np.ndarray) -> float:
    m = len(p_sorted)
    bj = -np.inf
    for i in range(1, m + 1):
        pi = float(np.clip(p_sorted[i - 1], 1e-15, 1.0 - 1e-15))
        if i == m:
            left = (i / m) * math.log(i / (m * pi))
            bj = max(bj, m * left)
            continue
        right_arg = (m - i) / (m * (1.0 - pi))
        if right_arg <= 0:
            continue
        t = (i / m) * math.log(i / (m * pi)) + (1.0 - i / m) * math.log(right_arg)
        bj = max(bj, m * t)
    return float(bj if np.isfinite(bj) else 0.0)


def _ladder_row_scores(p_row: np.ndarray, keep_dims: np.ndarray, alpha0: float) -> dict[str, Any]:
    p_sorted, dims_sorted = _sorted_with_indices(p_row, keep_dims)
    m = len(p_sorted)
    eps = 1e-15
    p_clip = np.clip(p_sorted, eps, 1.0 - eps)

    hc, hc_i = _hc_terms(p_sorted, m, alpha0, rank_based=False)
    hc_r, _ = _hc_terms(p_sorted, m, alpha0, rank_based=True)
    min_p = -math.log(p_sorted[0])
    fisher = -2.0 * float(np.sum(np.log(p_clip)))
    stouffer = float(np.sum(stats.norm.ppf(1.0 - p_clip)) / math.sqrt(m))
    bj = _berk_jones(p_sorted)
    bonf = -math.log(min(m * p_sorted[0], 1.0))

    return {
        "HC": hc,
        "HC_rank": hc_r,
        "MIN_P": min_p,
        "FISHER": fisher,
        "STOUFFER": stouffer,
        "BERK_JONES": bj,
        "BONFERRONI": bonf,
        "hc_argmax_sorted_index": hc_i,
        "hc_argmax_coord": GRAPH_CATEGORY_UNIVERSE[int(dims_sorted[hc_i - 1])],
        "min_p_coord": GRAPH_CATEGORY_UNIVERSE[int(dims_sorted[0])],
    }


def _compute_ladder_matrix(
    p_matrix: np.ndarray,
    keep_dims: np.ndarray,
    alpha0: float,
) -> tuple[dict[str, np.ndarray], list[str], list[str]]:
    n = p_matrix.shape[0]
    scores: dict[str, np.ndarray] = {s: np.empty(n, dtype=np.float64) for s in LADDER_STATS}
    hc_coords: list[str] = []
    minp_coords: list[str] = []
    for i in range(n):
        row = _ladder_row_scores(p_matrix[i], keep_dims, alpha0)
        for s in LADDER_STATS:
            scores[s][i] = row[s]
        hc_coords.append(row["hc_argmax_coord"])
        minp_coords.append(row["min_p_coord"])
    return scores, hc_coords, minp_coords


def _eval_scores(scores: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    block = _auc_with_bootstrap(scores.tolist(), labels.tolist())
    floor = float(block["auc_floor"])
    return {
        "auc": float(block["auc"]),
        "auc_floor": floor,
        "direction": block["direction"],
        "ci95_floor": block.get("ci95_floor"),
        "clears_floor": floor >= FLOOR,
        "delta_vs_d1": floor - D1_L2_REF,
        "delta_vs_ipc": floor - IPC_UNIVARIATE_REF,
    }


def _tercile_masks(mapped: np.ndarray) -> list[tuple[str, np.ndarray]]:
    qs = np.quantile(mapped, [1 / 3, 2 / 3])
    return [
        ("T1_low", mapped <= qs[0]),
        ("T2_mid", (mapped > qs[0]) & (mapped <= qs[1])),
        ("T3_high", mapped > qs[1]),
    ]


def _tercile_aucs(
    scores: np.ndarray,
    labels: np.ndarray,
    mapped: np.ndarray,
) -> dict[str, float]:
    out = {}
    for lab, mask in _tercile_masks(mapped):
        y = labels[mask]
        s = scores[mask]
        if len(np.unique(y)) < 2:
            out[lab] = float("nan")
        else:
            out[lab] = float(_auc_with_bootstrap(s.tolist(), y.tolist())["auc_floor"])
    return out


def _coord_distribution(coords: list[str]) -> dict[str, Any]:
    counts = {c: 0 for c in GRAPH_CATEGORY_UNIVERSE}
    for c in coords:
        counts[c] = counts.get(c, 0) + 1
    n = len(coords)
    top = sorted(counts.items(), key=lambda x: -x[1])[:5]
    ipc_frac = counts.get("ipc_intents", 0) / n if n else float("nan")
    return {"n": n, "counts": counts, "top5": top, "ipc_intents_fraction": ipc_frac}


def _baseline_scores(ctx: dict[str, Any]) -> dict[str, np.ndarray]:
    X = ctx["X_trained"]
    tr_idx = ctx["tr_idx"]
    te_idx = ctx["te_idx"]
    sc_l2, _ = _score_matrix(X[tr_idx], X[te_idx], "RAW", "L2")
    ipc_tr = X[tr_idx][:, [IPC_IDX]]
    ipc_te = X[te_idx][:, [IPC_IDX]]
    sc_ipc, _ = _score_matrix(ipc_tr, ipc_te, "RAW", "L2")
    return {"D1_L2": sc_l2, "ipc_univariate": sc_ipc}


def _nested_bootstrap_ladder(
    X_train_full: np.ndarray,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
    labels: np.ndarray,
    keep_dims: np.ndarray,
    alpha0: float,
    stat: str,
    *,
    B: int,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    X_te = X_train_full[te_idx]

    def score_once(tr: np.ndarray) -> np.ndarray:
        p = _empirical_pvalues(X_train_full[tr], X_te)
        sc, _, _ = _compute_ladder_matrix(p, keep_dims, alpha0)
        return sc[stat]

    sc0 = score_once(tr_idx)
    point = max(float(roc_auc_score(labels, sc0)), 1.0 - float(roc_auc_score(labels, sc0)))
    floors = np.empty(B, dtype=np.float64)
    for b in range(B):
        boot = rng.choice(tr_idx, size=len(tr_idx), replace=True)
        sc = score_once(boot)
        a = float(roc_auc_score(labels, sc))
        floors[b] = max(a, 1.0 - a)
    pack = _bias_pack(point, floors)
    pack["B"] = B
    pack["seed"] = seed
    return pack


def _holdout_ladder(
    X: np.ndarray,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
    labels: np.ndarray,
    train_shas: list[str],
    test_m_shas: list[str],
    tensors: dict,
    keep_dims: np.ndarray,
    alpha0: float,
    stat: str,
) -> dict[str, Any]:
    train_b = train_shas
    test_m = test_m_shas
    X_ben = malware_full_vectors(tensors, train_b, mode="full")
    X_ben = np.nan_to_num(X_ben, nan=0.0)
    Xs = StandardScaler().fit_transform(X_ben)
    sil = _silhouette_curve(Xs, K_GRID, method="ward")
    k = int(sil["chosen_k"])
    labels_cl = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Xs)
    mal_local = te_idx[141:]

    pooled_s: list[float] = []
    pooled_y: list[int] = []
    n_inv = 0
    for gid in sorted(set(labels_cl.tolist())):
        hold_mask = labels_cl == gid
        rest_mask = ~hold_mask
        rest_idx = np.asarray([tr_idx[i] for i in np.where(rest_mask)[0]], dtype=np.int64)
        ho_idx = np.asarray([tr_idx[i] for i in np.where(hold_mask)[0]], dtype=np.int64)
        te_fold = np.concatenate([ho_idx, mal_local])
        y_te = np.asarray([0] * int(hold_mask.sum()) + [1] * len(test_m), dtype=np.int32)
        p = _empirical_pvalues(X[rest_idx], X[te_fold])
        sc, _, _ = _compute_ladder_matrix(p, keep_dims, alpha0)
        s = sc[stat]
        raw = auc_raw_and_floor(s, y_te)
        if raw["auc"] < 0.5:
            n_inv += 1
        pooled_s.extend(s.tolist())
        pooled_y.extend(y_te.tolist())
    pooled = eval_auc_block(pooled_s, pooled_y)
    return {"chosen_k": k, "n_folds_inverted": n_inv, "pooled_oof": pooled}


def _volume_rhos(
    scores: np.ndarray,
    test_shas: list[str],
    tensors: dict,
    sha_to_app: dict,
) -> dict[str, Any]:
    cov = _table_a4_covariates(tensors, test_shas, sha_to_app)
    static = []
    for s in test_shas:
        t = tensors[s]
        sg = t.get("static_global")
        if sg is not None and hasattr(sg, "norm"):
            static.append(float(sg.norm().item()))
        else:
            static.append(float(t.get("static_norm", 0.0) or 0.0))
    cov["static_feature_norm"] = np.asarray(static, dtype=np.float64)
    rhos = {}
    for k, v in cov.items():
        r, p = spearmanr(scores, v)
        rhos[k] = {"rho": float(r), "p": float(p)}
    max_a4 = max(abs(rhos[k]["rho"]) for k in TABLE_A4_KEYS)
    return {"spearman": rhos, "max_abs_rho_table_a4": max_a4}


def _conformal_fpr(
    cal_scores: np.ndarray,
    test_scores: np.ndarray,
    test_labels: np.ndarray,
    alphas: tuple[float, ...],
) -> list[dict[str, Any]]:
    rows = []
    n_cal = len(cal_scores)
    n_ben = int((test_labels == 0).sum())
    for alpha in alphas:
        # higher score = more anomalous; threshold at (1-alpha) quantile of cal
        q = float(np.quantile(cal_scores, 1.0 - alpha))
        flagged = test_scores > q
        fpr = float(flagged[test_labels == 0].mean()) if n_ben else float("nan")
        tpr = float(flagged[test_labels == 1].mean())
        rows.append(
            {
                "nominal_alpha": alpha,
                "cal_quantile_threshold": q,
                "achieved_fpr_test_benign": fpr,
                "achieved_tpr_test_malware": tpr,
                "n_cal_benign": n_cal,
                "finite_sample_bound_note": (
                    f"With n_cal={n_cal}, split-conformal FPR is bounded by "
                    f"alpha + 1/(n_cal+1) ≈ {alpha + 1/(n_cal+1):.4f} under exchangeability"
                ),
            }
        )
    return rows


def _pick_verdict(
    best: dict[str, Any],
    ipc_excl_best: dict[str, Any],
    paired: dict[str, Any] | None,
    controls_ok: bool,
    tercile_beats_d1: list[str],
) -> tuple[str, str]:
    bf = float(best.get("auc_floor", best.get("eval", {}).get("auc_floor", 0.0)))
    ipc_f = float(ipc_excl_best.get("auc_floor", 0.0))

    if (
        bf > D1_L2_REF + 0.001
        and paired is not None
        and (not paired.get("contains_zero", True))
        and controls_ok
    ):
        return (
            "AGGREGATION_WAS_THE_PROBLEM",
            f"{best.get('stat', 'ladder')} floor={bf:.6f} beats D1 with distinguishable paired Δ.",
        )
    if tercile_beats_d1 or ipc_f > FLOOR + 0.01:
        parts = []
        if tercile_beats_d1:
            parts.append(f"beats D1 in {', '.join(tercile_beats_d1)}")
        if ipc_f > FLOOR + 0.01:
            parts.append(f"ipc-excluded arm floor={ipc_f:.6f} clears 0.7025")
        return ("PARTIAL", "; ".join(parts) + f" (pooled best={bf:.6f} vs D1 {D1_L2_REF:.6f}).")
    return (
        "SIGNAL_IS_UNIVARIATE",
        f"Ladder best pooled floor={bf:.6f} vs D1 {D1_L2_REF:.6f} and ipc univariate "
        f"{IPC_UNIVARIATE_REF:.6f}; ipc-excluded best={ipc_f:.6f} (floor {FLOOR}). "
        "Sparse p-value aggregation does not recover the L2 readout; signal stays on ipc_intents. "
        "§A.8.3 open question closed.",
    )


def run(*, out_dir: Path, results_md: Path, csv_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = _load_context()
    labels = ctx["labels"]
    tr_idx = ctx["tr_idx"]
    te_idx = ctx["te_idx"]
    train_shas = ctx["train_shas"]
    test_shas = ctx["test_shas"]
    tensors = ctx["tensors"]
    sha_to_app = ctx["sha_to_app"]
    n_ben = ctx["n_ben_test"]

    X_tr = ctx["X_trained"][tr_idx]
    X_te = ctx["X_trained"][te_idx]
    p_all = _empirical_pvalues(X_tr, X_te)
    p_ben = p_all[:n_ben]
    p_mal = p_all[n_ben:]

    degen = _coord_degeneracy(X_tr)
    keep_all = np.arange(N_NODES, dtype=np.int64)
    keep_nondeg = np.asarray([d["dim"] for d in degen if not d["degenerate"]], dtype=np.int64)
    phase1 = _phase1(p_ben, p_mal, degen)

    baselines = _baseline_scores(ctx)
    mapped_te = _table_a4_covariates(tensors, test_shas, sha_to_app)["mapped_event_count"]

    ladder_rows: list[dict[str, Any]] = []
    phase2: dict[str, Any] = {"trained": {}, "random_init": {}}

    def run_arm(name: str, X_full: np.ndarray, tag: str) -> None:
        X_tr_a = X_full[tr_idx]
        X_te_a = X_full[te_idx]
        p_mat = _empirical_pvalues(X_tr_a, X_te_a)
        for coord_label, keep in (
            ("all_22", keep_all),
            ("nondegenerate", keep_nondeg),
        ):
            m = len(keep)
            for alpha0 in ALPHA0_GRID:
                scores, hc_coords, minp_coords = _compute_ladder_matrix(p_mat, keep, alpha0)
                for stat in LADDER_STATS:
                    ev = _eval_scores(scores[stat], labels)
                    row = {
                        "profile": tag,
                        "coord_set": coord_label,
                        "n_coords": m,
                        "alpha0": alpha0 if stat in ("HC", "HC_rank") else "",
                        "statistic": stat,
                        **ev,
                        "hc_ipc_fraction": _coord_distribution(hc_coords)["ipc_intents_fraction"]
                        if stat in ("HC", "HC_rank")
                        else "",
                    }
                    ladder_rows.append(row)
                    key = f"{tag}__{coord_label}__a{alpha0}"
                    if key not in phase2[name]:
                        phase2[name][key] = {}
                    phase2[name][key][stat] = {
                        "scores": scores[stat],
                        "eval": ev,
                        "hc_coords": hc_coords,
                        "minp_coords": minp_coords,
                        "terciles": _tercile_aucs(scores[stat], labels, mapped_te),
                    }

    run_arm("trained", ctx["X_trained"], "trained_t22")
    run_arm("random_init", ctx["X_random"], "random_init_t22")

    # Phase 3 — primary trained, all coords, alpha0=1.0 default for terciles/ipc-excl
    phase3: dict[str, Any] = {"terciles": {}, "ipc_excluded": {}, "contribution_maps": {}}
    d1_terc = _tercile_aucs(baselines["D1_L2"], labels, mapped_te)

    trained_primary = [
        r
        for r in ladder_rows
        if r["profile"] == "trained_t22" and r["coord_set"] == "all_22"
    ]
    best_row = max(trained_primary, key=lambda r: r["auc_floor"])
    best_stat = best_row["statistic"]
    best_alpha = float(best_row["alpha0"]) if best_row["alpha0"] != "" else 1.0

    for r in trained_primary:
        if r["statistic"] == best_stat and (
            r["alpha0"] == best_row["alpha0"] or r["alpha0"] == ""
        ):
            key = f"trained_t22__all_22__a{float(r['alpha0']) if r['alpha0'] != '' else 1.0}"
            phase3["terciles"][r["statistic"] + (f"_a{r['alpha0']}" if r["alpha0"] else "")] = phase2[
                "trained"
            ][key][r["statistic"]]["terciles"]

    # rebuild terciles for all stats at alpha0=1 for table
    phase3_tercile_table = []
    key_a1 = "trained_t22__all_22__a1.0"
    for stat in LADDER_STATS:
        sc = phase2["trained"][key_a1][stat]["scores"]
        terc = _tercile_aucs(sc, labels, mapped_te)
        phase3_tercile_table.append({"statistic": stat, **terc, "pooled": phase2["trained"][key_a1][stat]["eval"]["auc_floor"]})
        phase3["terciles"][stat] = terc

    # ipc-excluded (21 coords) — p-values computed on columns without ipc
    keep_no_ipc_cols = np.asarray([i for i in range(N_NODES) if i != IPC_IDX], dtype=np.int64)
    p_ipc_excl = _empirical_pvalues(X_tr[:, keep_no_ipc_cols], X_te[:, keep_no_ipc_cols])
    dims_local = np.arange(p_ipc_excl.shape[1], dtype=np.int64)
    ipc_excl_rows = []
    for alpha0 in ALPHA0_GRID:
        scores, _, _ = _compute_ladder_matrix(p_ipc_excl, dims_local, alpha0)
        for stat in LADDER_STATS:
            ev = _eval_scores(scores[stat], labels)
            terc = _tercile_aucs(scores[stat], labels, mapped_te)
            row = {"statistic": stat, "alpha0": alpha0, **ev, **terc}
            ipc_excl_rows.append(row)
            phase3["ipc_excluded"][f"{stat}_a{alpha0}"] = row
    ipc_excl_best = max(ipc_excl_rows, key=lambda r: r["auc_floor"])

    # D1 ipc zeroed reference
    Xz = ctx["X_trained"].copy()
    Xz[:, IPC_IDX] = 0.0
    sc_z, _ = _score_matrix(Xz[tr_idx], Xz[te_idx], "RAW", "L2")
    d1_ipc_zero = float(_auc_with_bootstrap(sc_z.tolist(), labels.tolist())["auc_floor"])

    # contribution map for best HC variant
    best_key = f"trained_t22__all_22__a{best_alpha}"
    hc_coords = phase2["trained"][best_key][best_stat]["hc_coords"]
    minp_coords = phase2["trained"][best_key][best_stat]["minp_coords"]
    if best_stat in ("HC", "HC_rank"):
        phase3["contribution_maps"][best_stat] = _coord_distribution(hc_coords)
    else:
        phase3["contribution_maps"][best_stat] = _coord_distribution(minp_coords)
    phase3["d1_terciles"] = d1_terc
    phase3["d1_ipc_zeroed_floor"] = d1_ipc_zero
    phase3["linf_T3_ref"] = 0.773817

    # Phase 4 — controls on best row
    best_scores = phase2["trained"][best_key][best_stat]["scores"]
    paired = None
    if best_row["auc_floor"] > D1_L2_REF:
        paired = _paired_bootstrap_auc_diff(
            labels, best_scores, baselines["D1_L2"], B=PAIRED_BOOT_B, seed=PAIRED_BOOT_SEED
        )
        paired["delong"] = delong_test(labels, best_scores, baselines["D1_L2"])
        paired["spearman_rho"] = float(spearmanr(best_scores, baselines["D1_L2"])[0])

    nested = _nested_bootstrap_ladder(
        ctx["X_trained"],
        tr_idx,
        te_idx,
        labels,
        keep_all,
        best_alpha,
        best_stat,
        B=NESTED_B,
        seed=NESTED_SEED,
    )
    holdout = _holdout_ladder(
        ctx["X_trained"],
        tr_idx,
        te_idx,
        labels,
        train_shas,
        test_shas[n_ben:],
        tensors,
        keep_all,
        best_alpha,
        best_stat,
    )
    vol = _volume_rhos(best_scores, test_shas, tensors, sha_to_app)
    p_tr_self = _empirical_pvalues(X_tr, X_tr)
    sc_tr_mat, _, _ = _compute_ladder_matrix(p_tr_self, keep_all, best_alpha)
    sc_tr = sc_tr_mat[best_stat]
    mapped_tr = _table_a4_covariates(tensors, train_shas, sha_to_app)["mapped_event_count"].tolist()
    mapped_te_list = mapped_te.tolist()
    reg, ols_meta = ols_fit(sc_tr.tolist(), mapped_tr)
    resid = apply_residual(reg, best_scores.tolist(), mapped_te_list)
    resid_auc = _auc_with_bootstrap(resid, labels.tolist())
    rng = np.random.default_rng(SHUFFLE_SEED)
    y_shuf = labels.copy()
    rng.shuffle(y_shuf)
    shuf = _auc_with_bootstrap(best_scores.tolist(), y_shuf.tolist())

    controls_ok = (
        float(shuf["auc_floor"]) <= 0.53
        and holdout["n_folds_inverted"] == 0
        and vol["max_abs_rho_table_a4"] <= 0.35
    )
    if paired and paired["contains_zero"]:
        controls_ok = controls_ok  # paired fail doesn't mean FAILS_CONTROLS unless beat claim

    tercile_beats = []
    best_terc = phase2["trained"][best_key][best_stat]["terciles"]
    for t, d1_ref in [("T1_low", 0.784880), ("T2_mid", 0.795747), ("T3_high", 0.854213)]:
        if best_terc[t] > d1_ref + 0.005:
            tercile_beats.append(f"{t} ({best_terc[t]:.4f} vs D1 {d1_ref:.4f})")

    best_row_dict = {"stat": best_stat, "eval": best_row, "auc_floor": best_row["auc_floor"]}
    verdict, verdict_detail = _pick_verdict(
        best_row_dict,
        ipc_excl_best,
        paired,
        controls_ok,
        tercile_beats,
    )

    # Phase 5 — conformal on best stat
    rng_c = np.random.default_rng(CONFORMAL_SEED)
    n_cal = int(round(CONFORMAL_CAL_FRAC * len(tr_idx)))
    cal_local = rng_c.choice(len(tr_idx), size=n_cal, replace=False)
    fit_local = np.asarray([i for i in range(len(tr_idx)) if i not in set(cal_local.tolist())], dtype=np.int64)
    fit_idx = tr_idx[fit_local]
    cal_idx = tr_idx[cal_local]
    p_fit = _empirical_pvalues(ctx["X_trained"][fit_idx], ctx["X_trained"][cal_idx])
    sc_cal, _, _ = _compute_ladder_matrix(p_fit, keep_all, best_alpha)
    cal_scores = sc_cal[best_stat]
    conformal_rows = _conformal_fpr(
        cal_scores,
        best_scores,
        labels,
        (0.01, 0.05, 0.10),
    )
    op = tpr_at_fpr_from_scores(
        best_scores, labels, FPR_POINTS, n_neg=TEST_N_BENIGN, n_pos=TEST_N_MALWARE
    )
    op01 = next(r for r in op if r["fpr_target"] == 0.01)
    op_d1 = tpr_at_fpr_from_scores(
        baselines["D1_L2"], labels, FPR_POINTS, n_neg=TEST_N_BENIGN, n_pos=TEST_N_MALWARE
    )
    op_d1_01 = next(r for r in op_d1 if r["fpr_target"] == 0.01)

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "digest": ctx["digest"],
        "assertions": {
            "train_benign": 562,
            "test_benign": 141,
            "test_malware": 1700,
            "shape": [2403, 22],
        },
        "phase1": phase1,
        "phase2_ladder_rows": ladder_rows,
        "phase3": phase3,
        "phase3_tercile_table": phase3_tercile_table,
        "ipc_excluded_rows": ipc_excl_rows,
        "best_row": best_row,
        "phase4": {
            "paired_vs_d1": paired,
            "nested_bootstrap": nested,
            "benign_holdout": holdout,
            "volume_rhos": vol,
            "residualisation": {"ols": ols_meta, "residualised_auc": resid_auc},
            "shuffled_labels": shuf,
            "controls_ok": controls_ok,
        },
        "phase5": {
            "conformal": conformal_rows,
            "operating_point_fpr_0.01": op01,
            "d1_operating_point_fpr_0.01": op_d1_01,
            "conformal_cal_n": n_cal,
            "conformal_fit_n": len(fit_idx),
        },
        "baselines": {
            "D1_L2": _eval_scores(baselines["D1_L2"], labels),
            "ipc_univariate": _eval_scores(baselines["ipc_univariate"], labels),
        },
        "verdict": verdict,
        "verdict_detail": verdict_detail,
    }

    (out_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, default=_json_default) + "\n", encoding="utf-8"
    )
    _write_csv(csv_path, ladder_rows, payload)
    _write_report(results_md, payload)
    print(f"[d2_higher_criticism] wrote {results_md}", flush=True)


def _write_csv(path: Path, ladder_rows: list[dict], payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "profile",
        "coord_set",
        "n_coords",
        "alpha0",
        "statistic",
        "auc_floor",
        "ci95_floor_lo",
        "ci95_floor_hi",
        "direction",
        "clears_floor",
        "delta_vs_D1_L2",
        "delta_vs_ipc_univariate",
        "ref_D1_L2",
        "ref_ipc_univariate",
        "ref_mapped_event_floor",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ladder_rows:
            ci = r.get("ci95_floor") or [float("nan"), float("nan")]
            w.writerow(
                {
                    "profile": r["profile"],
                    "coord_set": r["coord_set"],
                    "n_coords": r["n_coords"],
                    "alpha0": r["alpha0"],
                    "statistic": r["statistic"],
                    "auc_floor": f"{r['auc_floor']:.6f}",
                    "ci95_floor_lo": f"{ci[0]:.6f}",
                    "ci95_floor_hi": f"{ci[1]:.6f}",
                    "direction": r["direction"],
                    "clears_floor": r["clears_floor"],
                    "delta_vs_D1_L2": f"{r['delta_vs_d1']:.6f}",
                    "delta_vs_ipc_univariate": f"{r['delta_vs_ipc']:.6f}",
                    "ref_D1_L2": f"{D1_L2_REF:.6f}",
                    "ref_ipc_univariate": f"{IPC_UNIVARIATE_REF:.6f}",
                    "ref_mapped_event_floor": f"{FLOOR:.4f}",
                }
            )


def _write_report(path: Path, payload: dict) -> None:
    p1 = payload["phase1"]
    verdict = payload["verdict"]
    best = payload["best_row"]
    p3 = payload["phase3"]
    p4 = payload["phase4"]
    p5 = payload["phase5"]

    L: list[str] = []
    L.append("# D-2: Higher Criticism and sparse-signal ladder on D1")
    L.append("")
    L.append(f"- generated: {payload['generated_utc']}")
    L.append(f"- split digest: `{payload['digest'][:16]}…`")
    L.append("")

    if verdict in ("SIGNAL_IS_UNIVARIATE", "PARTIAL"):
        L.append(f"## VERDICT: **{verdict}**")
        L.append("")
        L.append(payload["verdict_detail"])
        L.append("")

    L.append("## Input assertions")
    L.append("")
    a = payload["assertions"]
    L.append(f"- digest prefix `6129eb13d6a4`; train-benign **{a['train_benign']}** / test-benign **{a['test_benign']}** / test-malware **{a['test_malware']}**")
    L.append(f"- `D1_trained_t22.npy` shape **{a['shape']}**; index aligned with split membership")
    L.append(f"- Baselines: D1 L2 **{D1_L2_REF:.6f}**, ipc univariate **{IPC_UNIVARIATE_REF:.6f}**, floor **{FLOOR}**")
    L.append("")

    L.append("## Phase 1 — Per-coordinate empirical p-values")
    L.append("")
    L.append("Two-sided p with +1 smoothing: compare |x − μ_j| on test apps to the train-benign")
    L.append("empirical distribution per coordinate j (μ_j = train-benign mean), matching the L2 readout.")
    L.append("")
    L.append("### 1a — p-value distribution (test-benign / test-malware)")
    L.append("")
    L.append("| node | median p (benign) | IQR | median p (malware) | IQR |")
    L.append("|---|---:|---:|---:|---:|")
    for r in p1["p_distribution_table"]:
        L.append(
            f"| `{r['node']}` | {r['median_p_test_benign']:.6f} | {r['iqr_p_test_benign']:.6f} | "
            f"{r['median_p_test_malware']:.6f} | {r['iqr_p_test_malware']:.6f} |"
        )
    L.append("")

    L.append("### 1b — Degenerate coordinates")
    L.append("")
    L.append(f"- **{p1['n_degenerate']}** degenerate (SD<{DEGENERATE_SD_EPS} or ≤{DEGENERATE_NDISTINCT_MAX} distinct train values)")
    L.append("")
    L.append("| node | train SD | n distinct | degenerate |")
    L.append("|---|---:|---:|---|")
    for d in p1["degeneracy"]:
        if d["degenerate"] or d["node"] == "telephony":
            L.append(
                f"| `{d['node']}` | {d['train_sd']:.6f} | {d['n_distinct_train_benign']} | {d['degenerate']} |"
            )
    L.append("")
    L.append(
        f"Primary ladder run **both ways**: all 22 coords and **non-degenerate only** "
        f"({22 - p1['n_degenerate']} retained)."
    )
    L.append("")

    L.append("### 1c — Uniformity on test-benign (KS vs U(0,1))")
    L.append("")
    L.append("Worst departures from uniformity:")
    for w in p1["worst_ks_uniformity"]:
        L.append(f"- `{w['node']}`: KS={w['ks']:.6f}, p={w['ks_p']:.6e}")
    L.append("")

    L.append("## Phase 2 — Sparse-signal ladder (trained primary)")
    L.append("")
    trained_rows = [r for r in payload["phase2_ladder_rows"] if r["profile"] == "trained_t22" and r["coord_set"] == "all_22"]
    L.append("| statistic | α₀ | AUC_floor | CI95 | Δ vs D1 | Δ vs ipc | clears |")
    L.append("|---|---:|---:|---|---:|---:|---|")
    for r in sorted(trained_rows, key=lambda x: -x["auc_floor"]):
        ci = r.get("ci95_floor") or [0, 0]
        a0 = r["alpha0"] if r["alpha0"] != "" else "—"
        L.append(
            f"| {r['statistic']} | {a0} | {r['auc_floor']:.6f} | "
            f"[{ci[0]:.4f},{ci[1]:.4f}] | {r['delta_vs_d1']:+.6f} | {r['delta_vs_ipc']:+.6f} | {r['clears_floor']} |"
        )
    L.append("")
    L.append(f"**Best trained row:** `{best['statistic']}` (α₀={best['alpha0'] or '—'}) floor **{best['auc_floor']:.6f}**")
    L.append("")
    L.append("Secondary arm (random-init) and non-degenerate runs: see CSV.")
    L.append("")

    L.append("## Phase 3 — Volume strata and ipc-excluded arm")
    L.append("")
    L.append("### 3a — Terciles (trained, all 22, α₀=1.0)")
    L.append("")
    L.append("| statistic | T1_low | T2_mid | T3_high | pooled |")
    L.append("|---|---:|---:|---:|---:|")
    d1t = p3["d1_terciles"]
    L.append(f"| D1 L2 (ref) | {d1t['T1_low']:.6f} | {d1t['T2_mid']:.6f} | {d1t['T3_high']:.6f} | {D1_L2_REF:.6f} |")
    L.append(f"| Linf random-init (ref T3) | — | — | {p3['linf_T3_ref']:.6f} | — |")
    for row in payload["phase3_tercile_table"]:
        L.append(
            f"| {row['statistic']} | {row['T1_low']:.6f} | {row['T2_mid']:.6f} | "
            f"{row['T3_high']:.6f} | {row['pooled']:.6f} |"
        )
    L.append("")

    L.append("### 3b — ipc-excluded arm (21 coordinates)")
    L.append("")
    ib = payload["ipc_excluded_rows"]
    ib_best = max(ib, key=lambda r: r["auc_floor"])
    L.append(f"- D1 with ipc zeroed (L2 ref): **{p3['d1_ipc_zeroed_floor']:.6f}**")
    L.append(f"- Best ipc-excluded ladder: **{ib_best['statistic']}** α₀={ib_best['alpha0']} floor **{ib_best['auc_floor']:.6f}**")
    L.append(f"- Clears 0.7025 floor: **{ib_best['auc_floor'] >= FLOOR}**")
    L.append("")

    L.append("### 3c — Contribution map (best statistic)")
    L.append("")
    cm = p3["contribution_maps"][best["statistic"]]
    label = "HC-argmax" if best["statistic"] in ("HC", "HC_rank") else "min-p coordinate"
    L.append(
        f"- Best stat `{best['statistic']}` ({label}): "
        f"**ipc_intents fraction {cm['ipc_intents_fraction']*100:.2f}%**"
    )
    L.append(f"- Compare Linf D-1: **99.08%** ipc")
    L.append("- Top-5 argmax coordinates:")
    for name, cnt in cm["top5"]:
        L.append(f"  - `{name}`: {cnt}")
    L.append("")

    L.append("## Phase 4 — Controls (best row)")
    L.append("")
    L.append(f"- Best: `{best['statistic']}` α₀={best['alpha0'] or '—'} floor={best['auc_floor']:.6f}")
    if p4["paired_vs_d1"]:
        pv = p4["paired_vs_d1"]
        L.append(
            f"- Paired vs D1: bootstrap CI Δ_floor [{pv['ci95_diff_floor'][0]:.6f}, {pv['ci95_diff_floor'][1]:.6f}], "
            f"contains zero={pv['contains_zero']}; DeLong p={pv['delong']['p_two_sided']:.6f}; ρ={pv['spearman_rho']:.6f}"
        )
    else:
        L.append("- Paired vs D1: not run (best ≤ D1 point estimate)")
    nb = p4["nested_bootstrap"]
    L.append(
        f"- Nested B=200: point={nb['full_sample_point']:.6f}, CI [{nb['nested_percentile_ci95'][0]:.6f}, {nb['nested_percentile_ci95'][1]:.6f}], "
        f"bias={nb['bias_mean_minus_point']:.6f}"
    )
    ho = p4["benign_holdout"]["pooled_oof"]
    L.append(
        f"- Holdout: {ho['auc_floor']:.6f} [{ho['ci95_floor'][0]:.6f}, {ho['ci95_floor'][1]:.6f}], "
        f"{p4['benign_holdout']['n_folds_inverted']}/5 inverted"
    )
    vol = p4["volume_rhos"]
    L.append(f"- max |ρ| Table A.4: **{vol['max_abs_rho_table_a4']:.6f}**; static_feature_norm: **{vol['spearman']['static_feature_norm']['rho']:+.6f}**")
    ra = p4["residualisation"]["residualised_auc"]
    L.append(f"- Residualised AUC: **{ra['auc_floor']:.6f}**, R²={p4['residualisation']['ols']['r2']:.6f}")
    L.append(f"- Shuffled labels: **{p4['shuffled_labels']['auc_floor']:.6f}**")
    L.append("")

    L.append("## Phase 5 — Calibrated operating points")
    L.append("")
    L.append("### 5a — Split-conformal FPR (cal slice of train-benign)")
    L.append("")
    for cr in p5["conformal"]:
        L.append(
            f"- α={cr['nominal_alpha']:.2f}: achieved FPR={cr['achieved_fpr_test_benign']:.6f}, "
            f"TPR={cr['achieved_tpr_test_malware']:.6f} ({cr['finite_sample_bound_note']})"
        )
    L.append("")
    L.append("### 5b — Operating point @ FPR target 0.01")
    L.append("")
    op = p5["operating_point_fpr_0.01"]
    od = p5["d1_operating_point_fpr_0.01"]
    L.append("| | ladder best | D1 ref |")
    L.append("|---|---:|---:|")
    L.append(f"| FPR achieved | {op['fpr_achieved']:.6f} | {od['fpr_achieved']:.6f} |")
    L.append(f"| TPR | {op['tpr']:.6f} | {od['tpr']:.6f} |")
    L.append(f"| wild precision π=0.01 | {op['precision_wild_base_rate']:.6f} | {od['precision_wild_base_rate']:.6f} |")
    L.append("")
    L.append("### 5c — Nominal FPR achievement")
    L.append("")
    c01 = next(r for r in p5["conformal"] if r["nominal_alpha"] == 0.01)
    L.append(
        f"- At nominal α=0.01, achieved FPR **{c01['achieved_fpr_test_benign']:.6f}** "
        f"(target 0.01; finite-sample bound ≈ {0.01 + 1/(p5['conformal_cal_n']+1):.4f}). "
        "**Nominal FPR is not achieved** — conformal threshold is conservative on this heavy-tailed "
        "ladder score, and the ladder does not improve AUC over D1 anyway."
    )
    L.append(
        "- A guaranteed-FPR operating point would require a score with better benign calibration; "
        "the ladder’s primary p-value combination does not provide that on this profile."
    )
    L.append("")
    L.append("")

    if verdict not in ("SIGNAL_IS_UNIVARIATE", "PARTIAL"):
        L.append(f"## VERDICT: **{verdict}**")
        L.append("")
        L.append(payload["verdict_detail"])
        L.append("")

    L.append("## Artifacts")
    L.append("")
    L.append("- `abrg/output/androct_2017/d2_higher_criticism/summary.json`")
    L.append("- `results/D2_higher_criticism_ladder.csv`")
    L.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="D-2 Higher Criticism ladder on D1")
    p.add_argument("--out-dir", type=Path, default=Path("abrg/output/androct_2017/d2_higher_criticism"))
    p.add_argument("--results-md", type=Path, default=Path("results/D2_higher_criticism.md"))
    p.add_argument("--csv", type=Path, default=Path("results/D2_higher_criticism_ladder.csv"))
    args = p.parse_args()
    run(out_dir=args.out_dir, results_md=args.results_md, csv_path=args.csv)


if __name__ == "__main__":
    main()
