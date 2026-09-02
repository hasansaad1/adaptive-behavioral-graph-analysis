"""
D-1: Sparse aggregation on the D1 deviation profile (scoring pass only).

Loads persisted devread profiles; no GAE retrain. Emits artifacts under
abrg/output/androct_2017/d1_sparse_aggregation/ and results/D1_sparse_aggregation.md
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
from scipy.stats import spearmanr
from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.apigraph.split import load_run3_split
from abrg.devread import EXPECTED_SPLIT_DIGEST_PREFIX
from abrg.features import feature_vector_labels
from abrg.final_validate.util import auc_raw_and_floor, eval_auc_block
from abrg.ladder.grouping import _silhouette_curve
from abrg.ladder.vectorize import malware_full_vectors
from abrg.ocdev.detectors import fit_score_centroid_euclidean
from abrg.ocdev.part_a import load_profiles
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.validate.residual import apply_residual, ols_fit

FLOOR = 0.7025
D1_BASELINE = 0.8004
N_NODES = 22
ACT_V_FRAC_IDX = feature_vector_labels(normalize=True).index("act_v_frac")
K_GRID = (5, 10, 15, 20)
AGGREGATORS = (
    "L2",
    "L1",
    "Linf",
    "MAX",
    "TOPK_MEAN_2",
    "TOPK_MEAN_3",
    "TOPK_MEAN_5",
    "TRIMMED_L2",
    "WINSOR_L2",
)
PREPROCESS = ("RAW", "ZSTD")
PROFILE_TAGS = ("trained_t22", "random_init_t22")
SHUFFLE_SEED = 42


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _assert_inputs() -> dict[str, Any]:
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

    arrays, shas = load_profiles("trained_t22")
    X = arrays["D1"]
    if X.shape[1] != N_NODES:
        raise SystemExit(f"STOP: D1 dim {X.shape[1]} != {N_NODES}")

    train_shas = [a.sha256 for a in train]
    test_shas = [a.sha256 for a in test_b] + [a.sha256 for a in test_m]
    sha_to_i = {s: i for i, s in enumerate(shas)}

    for s in train_shas + test_shas:
        if s not in sha_to_i:
            raise SystemExit(f"STOP: sha {s[:12]} missing from profile index")

    labels = np.asarray([0] * len(test_b) + [1] * len(test_m), dtype=np.int32)
    tr_idx = np.asarray([sha_to_i[s] for s in train_shas], dtype=np.int64)
    te_idx = np.asarray([sha_to_i[s] for s in test_shas], dtype=np.int64)

    return {
        "digest": dig,
        "train_shas": train_shas,
        "test_shas": test_shas,
        "labels": labels,
        "tr_idx": tr_idx,
        "te_idx": te_idx,
        "tensors": corpus.tensors,
        "sha_to_i": sha_to_i,
    }


def _node_mapped_share(tensors: dict, train_shas: list[str]) -> np.ndarray:
    acc = np.zeros(N_NODES, dtype=np.float64)
    for s in train_shas:
        x = tensors[s]["x"]
        if hasattr(x, "numpy"):
            x = x.numpy()
        acc += np.asarray(x[:, ACT_V_FRAC_IDX], dtype=np.float64)
    return acc / max(len(train_shas), 1)


def _phase1(
    X_tr: np.ndarray,
    X_tb: np.ndarray,
    X_tm: np.ndarray,
    node_mapped_share: np.ndarray,
) -> dict[str, Any]:
    mean = X_tr.mean(axis=0)
    sd = X_tr.std(axis=0, ddof=0)
    sd_safe = np.where(sd < 1e-12, 1.0, sd)
    node_var = X_tr.var(axis=0)

    coord_rows = []
    for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        coord_rows.append(
            {
                "node": cat,
                "dim": i,
                "mean": float(mean[i]),
                "sd": float(sd[i]),
                "variance": float(node_var[i]),
                "mapped_share": float(node_mapped_share[i]),
            }
        )
    rho_sd_share, p_sd_share = spearmanr(sd.tolist(), node_mapped_share.tolist())

    pca = PCA(n_components=N_NODES)
    pca.fit(X_tr)
    ev = pca.explained_variance_
    evr = pca.explained_variance_ratio_
    cum = np.cumsum(evr)

    def n_for(th: float) -> int:
        return int(np.searchsorted(cum, th) + 1)

    n50, n90, n99 = n_for(0.50), n_for(0.90), n_for(0.99)
    mars = bool(n90 <= math.floor(N_NODES / 3))

    axes = []
    ratios = []
    for i in range(N_NODES):
        u = pca.components_[i]
        msq_b = float(np.mean((X_tb @ u) ** 2))
        msq_m = float(np.mean((X_tm @ u) ** 2))
        ratio = msq_m / msq_b if msq_b > 0 else float("nan")
        axes.append(
            {
                "pc": i,
                "eigenvalue": float(ev[i]),
                "var_ratio": float(evr[i]),
                "cum_var": float(cum[i]),
                "msq_benign": msq_b,
                "msq_malware": msq_m,
                "malware_benign_ratio": ratio,
            }
        )
        ratios.append(ratio)

    ratios_a = np.asarray(ratios, dtype=np.float64)
    third = N_NODES // 3
    sep_high = float(np.nanmean(np.abs(np.log(np.clip(ratios_a[:third], 1e-12, None)))))
    sep_low = float(np.nanmean(np.abs(np.log(np.clip(ratios_a[-third:], 1e-12, None)))))
    mean_abs_log = float(np.nanmean(np.abs(np.log(np.clip(ratios_a, 1e-12, None)))))

    if mean_abs_log < 0.05:
        verdict = "NO_SEPARATION"
        where = "nowhere"
    elif sep_low > sep_high * 1.15:
        verdict = "LOW_VARIANCE_SEPARATION"
        where = f"low-variance axes (sep_low={sep_low:.4f} > sep_high={sep_high:.4f})"
    elif sep_high > sep_low * 1.15:
        verdict = "HIGH_VARIANCE_SEPARATION"
        where = f"high-variance axes (sep_high={sep_high:.4f} > sep_low={sep_low:.4f})"
    else:
        verdict = "LOW_VARIANCE_SEPARATION" if sep_low >= sep_high else "HIGH_VARIANCE_SEPARATION"
        where = f"borderline ({verdict})"

    return {
        "coordinates": coord_rows,
        "sd_ratio_max_min": float(sd.max() / max(sd.min(), 1e-12)),
        "spearman_rho_sd_vs_mapped_share": float(rho_sd_share),
        "spearman_p_sd_vs_mapped_share": float(p_sd_share),
        "pca": {
            "eigenvalues": ev.tolist(),
            "explained_variance_ratio": evr.tolist(),
            "cumulative_variance": cum.tolist(),
            "n_components_50": n50,
            "n_components_90": n90,
            "n_components_99": n99,
            "mars_condition_90pct_under_third": mars,
            "axes": axes,
            "verdict": verdict,
            "separation_where": where,
            "sep_high_third": sep_high,
            "sep_low_third": sep_low,
        },
    }


def _transform(
    X: np.ndarray,
    prep: str,
    *,
    mean: np.ndarray | None = None,
    std: np.ndarray | None = None,
    winsor_lo: np.ndarray | None = None,
    winsor_hi: np.ndarray | None = None,
) -> np.ndarray:
    out = X.copy()
    if prep == "ZSTD" and mean is not None and std is not None:
        out = (out - mean) / std
    if winsor_lo is not None and winsor_hi is not None:
        out = np.clip(out, winsor_lo, winsor_hi)
    return out


def _aggregate(d: np.ndarray, agg: str) -> float:
    ad = np.abs(d)
    if agg == "L2":
        return float(np.linalg.norm(d, ord=2))
    if agg == "L1":
        return float(np.linalg.norm(d, ord=1))
    if agg in ("Linf", "MAX"):
        return float(np.max(ad))
    if agg.startswith("TOPK_MEAN_"):
        k = int(agg.rsplit("_", 1)[-1])
        k = min(k, len(d))
        idx = np.argpartition(ad, -k)[-k:]
        return float(np.mean(ad[idx]))
    if agg == "TRIMMED_L2":
        if len(d) <= 2:
            return float(np.linalg.norm(d, ord=2))
        i_min = int(np.argmin(d))
        i_max = int(np.argmax(d))
        mask = np.ones(len(d), dtype=bool)
        mask[i_min] = False
        if i_max != i_min:
            mask[i_max] = False
        return float(np.linalg.norm(d[mask], ord=2))
    if agg == "WINSOR_L2":
        return float(np.linalg.norm(d, ord=2))
    raise ValueError(agg)


def _score_matrix(
    X_tr_raw: np.ndarray,
    X_te_raw: np.ndarray,
    prep: str,
    agg: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    mean = X_tr_raw.mean(axis=0)
    std = X_tr_raw.std(axis=0, ddof=0)
    std = np.where(std < 1e-12, 1.0, std)
    winsor_lo = np.percentile(X_tr_raw, 5, axis=0)
    winsor_hi = np.percentile(X_tr_raw, 95, axis=0)

    if agg == "WINSOR_L2":
        X_tr = _transform(X_tr_raw, prep, mean=mean, std=std, winsor_lo=winsor_lo, winsor_hi=winsor_hi)
        X_te = _transform(X_te_raw, prep, mean=mean, std=std, winsor_lo=winsor_lo, winsor_hi=winsor_hi)
    else:
        X_tr = _transform(X_tr_raw, prep, mean=mean, std=std)
        X_te = _transform(X_te_raw, prep, mean=mean, std=std)

    mu = X_tr.mean(axis=0)
    scores = np.asarray([_aggregate(x - mu, agg) for x in X_te], dtype=np.float64)
    meta = {"prep": prep, "agg": agg, "mu_norm": float(np.linalg.norm(mu))}
    return scores, meta


def _eval_row(scores: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    block = _auc_with_bootstrap(scores.tolist(), labels.tolist())
    floor = float(block["auc_floor"])
    return {
        "auc": float(block["auc"]),
        "auc_floor": floor,
        "direction": block["direction"],
        "ci95": block.get("ci95"),
        "ci95_floor": block.get("ci95_floor"),
        "clears_floor": floor >= FLOOR,
        "delta_vs_d1_baseline": floor - D1_BASELINE,
    }


def _covariates(tensors: dict, shas: list[str]) -> dict[str, np.ndarray]:
    rows = []
    for s in shas:
        t = tensors[s]
        mapped = float(t.get("n_mapped", t.get("n_inv_events", 0)))
        total = float(t.get("n_events", t.get("n_total_events", 0)))
        static = t.get("static_global")
        if static is not None and hasattr(static, "norm"):
            sn = float(static.norm().item())
        else:
            sn = float(t.get("static_norm", 0.0) or 0.0)
        rows.append(
            {
                "mapped_events": mapped,
                "total_events": total,
                "active_nodes": float(t["n_active"]),
                "edge_count": float(t["n_edges"]),
                "density": float(t["density"]),
                "static_feature_norm": sn,
            }
        )
    keys = list(rows[0].keys())
    return {k: np.asarray([r[k] for r in rows], dtype=np.float64) for k in keys}


def _volume_controls(
    scores: np.ndarray,
    labels: np.ndarray,
    train_shas: list[str],
    test_shas: list[str],
    tensors: dict,
    *,
    score_fn_on_profiles: Callable[[np.ndarray, np.ndarray], np.ndarray],
    X_all: np.ndarray,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
) -> dict[str, Any]:
    cov = _covariates(tensors, test_shas)
    rhos = {}
    for k, v in cov.items():
        r, p = spearmanr(scores, v)
        rhos[k] = {"rho": float(r), "p": float(p)}

    sc_tr = score_fn_on_profiles(X_all[tr_idx], X_all[tr_idx])
    mapped_tr = _covariates(tensors, train_shas)["mapped_events"].tolist()
    mapped_te = cov["mapped_events"].tolist()
    reg, ols_meta = ols_fit(sc_tr.tolist(), mapped_tr)
    resid = apply_residual(reg, scores.tolist(), mapped_te)
    resid_auc = _auc_with_bootstrap(resid, labels.tolist())

    mapped = cov["mapped_events"]
    qs = np.quantile(mapped, [1 / 3, 2 / 3])
    terciles = []
    for t_i, (lo, hi, lab) in enumerate(
        [(-np.inf, qs[0], "T1_low"), (qs[0], qs[1], "T2_mid"), (qs[1], np.inf, "T3_high")]
    ):
        if t_i == 0:
            mask = mapped <= hi
        elif t_i == 2:
            mask = mapped > lo
        else:
            mask = (mapped > lo) & (mapped <= hi)
        y_t = labels[mask]
        s_t = scores[mask]
        if len(np.unique(y_t)) < 2:
            auc_t = {"auc_floor": float("nan"), "direction": "undefined"}
        else:
            auc_t = _auc_with_bootstrap(s_t.tolist(), y_t.tolist())
        terciles.append(
            {
                "tercile": lab,
                "n": int(mask.sum()),
                "auc_floor": float(auc_t["auc_floor"]),
                "direction": auc_t.get("direction"),
            }
        )

    # Ward holdout k=5 on full vectors (matches D1 check4)
    train_b = train_shas
    test_m = [s for s, y in zip(test_shas, labels) if y == 1]
    X_ben = malware_full_vectors(tensors, train_b, mode="full")
    X_ben = np.nan_to_num(X_ben, nan=0.0)
    Xs = StandardScaler().fit_transform(X_ben)
    sil = _silhouette_curve(Xs, K_GRID, method="ward")
    k = int(sil["chosen_k"])
    labels_cl = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Xs)
    mal_idx = te_idx[141:]

    fold_rows = []
    pooled_s: list[float] = []
    pooled_y: list[int] = []
    for gid in sorted(set(labels_cl.tolist())):
        hold_mask = labels_cl == gid
        rest_mask = ~hold_mask
        hold_shas = [train_b[i] for i in np.where(hold_mask)[0]]
        rest_shas = [train_b[i] for i in np.where(rest_mask)[0]]
        rest_idx = np.asarray([tr_idx[i] for i in np.where(rest_mask)[0]], dtype=np.int64)
        ho_idx = np.asarray([tr_idx[i] for i in np.where(hold_mask)[0]], dtype=np.int64)
        te_idx_fold = np.concatenate([ho_idx, mal_idx])
        y_te = np.asarray([0] * len(hold_shas) + [1] * len(test_m), dtype=np.int32)
        sc = score_fn_on_profiles(X_all[rest_idx], X_all[te_idx_fold])
        raw = auc_raw_and_floor(sc, y_te)
        pooled_s.extend(sc.tolist())
        pooled_y.extend(y_te.tolist())
        fold_rows.append(
            {
                "fold": int(gid),
                "auc_floor": raw["auc_floor"],
                "inverted": raw["auc"] < 0.5,
            }
        )
    pooled = eval_auc_block(pooled_s, pooled_y)
    n_inv = sum(1 for f in fold_rows if f["inverted"])

    # per-node ablation on deviation scoring
    base_floor = float(_auc_with_bootstrap(scores.tolist(), labels.tolist())["auc_floor"])
    ablations = []
    for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        Xz = X_all.copy()
        Xz[:, i] = 0.0
        sc_z = score_fn_on_profiles(Xz[tr_idx], Xz[te_idx])
        auc_z = _auc_with_bootstrap(sc_z.tolist(), labels.tolist())
        drop = base_floor - float(auc_z["auc_floor"])
        ablations.append({"node": cat, "dim": i, "delta_auc_floor": drop, "auc_floor_zeroed": float(auc_z["auc_floor"])})
    ablations.sort(key=lambda r: -r["delta_auc_floor"])

    # shuffled labels
    rng = np.random.default_rng(SHUFFLE_SEED)
    y_shuf = labels.copy()
    rng.shuffle(y_shuf)
    shuf_auc = _auc_with_bootstrap(scores.tolist(), y_shuf.tolist())

    max_abs_rho = max(abs(v["rho"]) for v in rhos.values() if np.isfinite(v["rho"]))

    return {
        "spearman_vs_score": rhos,
        "max_abs_rho": max_abs_rho,
        "passes_d1_rho_standard": max_abs_rho <= 0.33,
        "residualisation": {
            "ols": ols_meta,
            "residualised_auc": resid_auc,
            "raw_auc_floor": base_floor,
        },
        "terciles": terciles,
        "benign_holdout": {
            "chosen_k": k,
            "n_folds_inverted": n_inv,
            "pooled_oof": pooled,
            "folds": fold_rows,
        },
        "per_node_ablation": ablations,
        "shuffled_labels": shuf_auc,
    }


def _centroid_scores(X_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    sc, _ = fit_score_centroid_euclidean(X_tr, X_te)
    return np.asarray(sc, dtype=np.float64)


def run(*, out_dir: Path, results_md: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = _assert_inputs()
    labels = ctx["labels"]
    tr_idx = ctx["tr_idx"]
    te_idx = ctx["te_idx"]
    train_shas = ctx["train_shas"]
    test_shas = ctx["test_shas"]
    tensors = ctx["tensors"]

    # Phase 1 on trained profiles
    arrays_tr, _ = load_profiles("trained_t22")
    X = arrays_tr["D1"]
    X_tr = X[tr_idx]
    tb_idx = te_idx[:141]
    tm_idx = te_idx[141:]
    X_tb = X[tb_idx]
    X_tm = X[tm_idx]
    node_share = _node_mapped_share(tensors, train_shas)
    phase1 = _phase1(X_tr, X_tb, X_tm, node_share)

    rows: list[dict[str, Any]] = []

    for tag in PROFILE_TAGS:
        arrays, _ = load_profiles(tag)
        Xp = arrays["D1"]
        X_tr_p = Xp[tr_idx]
        X_te_p = Xp[te_idx]

        # Reference centroid row (RAW only, trained tag primary)
        if tag == "trained_t22":
            sc_cent = _centroid_scores(X_tr_p, X_te_p)
            ev = _eval_row(sc_cent, labels)
            rows.append(
                {
                    "profile_tag": tag,
                    "preprocess": "RAW",
                    "aggregator": "D1_CENTROID_EUCLIDEAN",
                    "reference": True,
                    **ev,
                }
            )

        for prep in PREPROCESS:
            for agg in AGGREGATORS:
                sc, _ = _score_matrix(X_tr_p, X_te_p, prep, agg)
                ev = _eval_row(sc, labels)
                rows.append(
                    {
                        "profile_tag": tag,
                        "preprocess": prep,
                        "aggregator": agg,
                        **ev,
                    }
                )

    # Best trained row by auc_floor (exclude reference duplicate L2 RAW if same)
    trained_rows = [r for r in rows if r["profile_tag"] == "trained_t22" and not r.get("reference")]
    best = max(trained_rows, key=lambda r: r["auc_floor"])

    # Phase 3 controls on best row
    arrays_tr, _ = load_profiles("trained_t22")
    X_all = arrays_tr["D1"]
    prep = best["preprocess"]
    agg = best["aggregator"]
    mean = X_all[tr_idx].mean(axis=0)
    std = X_all[tr_idx].std(axis=0, ddof=0)
    std = np.where(std < 1e-12, 1.0, std)
    winsor_lo = np.percentile(X_all[tr_idx], 5, axis=0)
    winsor_hi = np.percentile(X_all[tr_idx], 95, axis=0)

    def score_fn(X_tr_in: np.ndarray, X_te_in: np.ndarray) -> np.ndarray:
        if agg == "WINSOR_L2":
            X_tr_t = _transform(X_tr_in, prep, mean=mean, std=std, winsor_lo=winsor_lo, winsor_hi=winsor_hi)
            X_te_t = _transform(X_te_in, prep, mean=mean, std=std, winsor_lo=winsor_lo, winsor_hi=winsor_hi)
        else:
            X_tr_t = _transform(X_tr_in, prep, mean=mean, std=std)
            X_te_t = _transform(X_te_in, prep, mean=mean, std=std)
        mu = X_tr_t.mean(axis=0)
        return np.asarray([_aggregate(x - mu, agg) for x in X_te_t], dtype=np.float64)

    best_scores = score_fn(X_all[tr_idx], X_all[te_idx])
    phase3 = _volume_controls(
        best_scores,
        labels,
        train_shas,
        test_shas,
        tensors,
        score_fn_on_profiles=score_fn,
        X_all=X_all,
        tr_idx=tr_idx,
        te_idx=te_idx,
    )

    # Phase 4 summaries
    d1_row = next(r for r in rows if r.get("reference"))
    beats_d1_raw = best["auc_floor"] > D1_BASELINE
    passes_volume = (
        phase3["passes_d1_rho_standard"]
        and float(phase3["residualisation"]["residualised_auc"]["auc_floor"]) >= 0.79
    )

    zstd_deltas = []
    sparse_deltas = []
    dense_deltas = []
    sparse_aggs = {"Linf", "MAX", "TOPK_MEAN_2", "TOPK_MEAN_3", "TOPK_MEAN_5", "TRIMMED_L2"}
    dense_aggs = {"L2", "L1", "WINSOR_L2"}
    for tag in ("trained_t22",):
        for agg in AGGREGATORS:
            raw_r = next(r for r in rows if r["profile_tag"] == tag and r["preprocess"] == "RAW" and r["aggregator"] == agg)
            zstd_r = next(r for r in rows if r["profile_tag"] == tag and r["preprocess"] == "ZSTD" and r["aggregator"] == agg)
            zstd_deltas.append(zstd_r["auc_floor"] - raw_r["auc_floor"])
            if agg in sparse_aggs:
                dense_r = next(r for r in rows if r["profile_tag"] == tag and r["preprocess"] == "RAW" and r["aggregator"] == "L2")
                sparse_r = raw_r
                sparse_deltas.append(sparse_r["auc_floor"] - dense_r["auc_floor"])
        for agg in dense_aggs:
            if agg == "L2":
                continue
            l2_r = next(r for r in rows if r["profile_tag"] == tag and r["preprocess"] == "RAW" and r["aggregator"] == "L2")
            dense_r = next(r for r in rows if r["profile_tag"] == tag and r["preprocess"] == "RAW" and r["aggregator"] == agg)
            dense_deltas.append(dense_r["auc_floor"] - l2_r["auc_floor"])

    trained_best = max(
        [r for r in rows if r["profile_tag"] == "trained_t22" and not r.get("reference")],
        key=lambda r: r["auc_floor"],
    )
    random_best = max(
        [r for r in rows if r["profile_tag"] == "random_init_t22"],
        key=lambda r: r["auc_floor"],
    )
    random_beats_trained = random_best["auc_floor"] > trained_best["auc_floor"]

    phase4 = {
        "4a_beats_d1_after_controls": beats_d1_raw and passes_volume,
        "4a_beats_d1_raw_only": beats_d1_raw,
        "4a_best_row": best,
        "4a_d1_centroid_reference": d1_row,
        "4b_zstd_minus_raw_mean_delta": float(np.mean(zstd_deltas)),
        "4c_sparse_minus_l2_mean_delta": float(np.mean(sparse_deltas)),
        "4d_random_init_best": random_best,
        "4d_trained_best": trained_best,
        "4d_random_beats_trained": random_beats_trained,
        "4e_rho_sd_share": phase1["spearman_rho_sd_vs_mapped_share"],
        "4e_zstd_is_volume_norm": abs(phase1["spearman_rho_sd_vs_mapped_share"]) > 0.9,
    }

    # Persist artifacts
    summary = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "digest": ctx["digest"],
        "floor": FLOOR,
        "d1_baseline": D1_BASELINE,
        "phase1": phase1,
        "phase3_best_row": {"preprocess": prep, "aggregator": agg, **phase3},
        "phase4": phase4,
        "n_rows": len(rows),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=_json_default) + "\n")
    (out_dir / "phase1.json").write_text(json.dumps(phase1, indent=2, default=_json_default) + "\n")
    (out_dir / "phase3_controls.json").write_text(
        json.dumps(phase3, indent=2, default=_json_default) + "\n"
    )

    csv_path = out_dir / "matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "profile_tag",
            "preprocess",
            "aggregator",
            "auc",
            "auc_floor",
            "direction",
            "ci95_floor_lo",
            "ci95_floor_hi",
            "clears_floor",
            "delta_vs_d1_baseline",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            ci = r.get("ci95_floor") or [None, None]
            w.writerow(
                {
                    "profile_tag": r["profile_tag"],
                    "preprocess": r["preprocess"],
                    "aggregator": r["aggregator"],
                    "auc": f"{r['auc']:.10f}",
                    "auc_floor": f"{r['auc_floor']:.10f}",
                    "direction": r["direction"],
                    "ci95_floor_lo": f"{ci[0]:.10f}" if ci[0] is not None else "",
                    "ci95_floor_hi": f"{ci[1]:.10f}" if ci[1] is not None else "",
                    "clears_floor": r["clears_floor"],
                    "delta_vs_d1_baseline": f"{r['delta_vs_d1_baseline']:.10f}",
                }
            )

    _write_report(results_md, ctx, phase1, rows, best, phase3, phase4, out_dir)
    print(f"[D1-sparse] wrote {out_dir} and {results_md}", flush=True)


def _fmt(x: float | None, n: int = 4) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "nan"
    return f"{x:.{n}f}"


def _write_report(
    path: Path,
    ctx: dict,
    phase1: dict,
    rows: list[dict],
    best: dict,
    phase3: dict,
    phase4: dict,
    out_dir: Path,
) -> None:
    L: list[str] = []
    L.append("# D1 sparse aggregation (D-1 scoring pass)")
    L.append("")
    L.append(f"Artifacts: `{out_dir}/`")
    L.append("")

    L.append("## Input assertions")
    L.append(f"- Split digest: `{ctx['digest'][:16]}…` (prefix `6129eb13d6a4`)")
    L.append("- Counts: 562 train-benign / 141 test-benign / 1700 test-malware")
    L.append("- Profiles: `devread/artifacts/profiles/D1_{trained,random_init}_t22.npy` (22 coords)")
    L.append("- Baseline: D1 centroid Euclidean floor AUC **0.8004**")
    L.append("")

    L.append("## Phase 1 — variance structure (train-benign D1, trained)")
    L.append(f"- SD ratio max/min: **{phase1['sd_ratio_max_min']:.4f}**")
    L.append(
        f"- Spearman ρ(coordinate SD, mapped-event share): **{phase1['spearman_rho_sd_vs_mapped_share']:.4f}** "
        f"(p={phase1['spearman_p_sd_vs_mapped_share']:.2e})"
    )
    pca = phase1["pca"]
    L.append(
        f"- PCA: n90={pca['n_components_90']}/22; MaRS condition (n90 ≤ 7): **{pca['mars_condition_90pct_under_third']}**; "
        f"verdict **{pca['verdict']}** — {pca['separation_where']}"
    )
    L.append("")
    L.append("| node | mean | SD | mapped_share |")
    L.append("|------|------|-----|--------------|")
    for c in phase1["coordinates"]:
        L.append(
            f"| {c['node']} | {c['mean']:.6f} | {c['sd']:.6f} | {c['mapped_share']:.4f} |"
        )
    L.append("")
    L.append(f"Full Phase 1: `{out_dir}/phase1.json`")
    L.append("")

    L.append("## Phase 2 — aggregator sweep")
    L.append(f"Matrix: `{out_dir}/matrix.csv` ({len(rows)} rows)")
    L.append("")
    L.append("| tag | prep | aggregator | AUC_floor | direction | clears | Δ vs 0.8004 |")
    L.append("|-----|------|------------|-----------|-----------|--------|-------------|")
    for r in sorted(rows, key=lambda x: (-x["auc_floor"], x["profile_tag"], x["preprocess"], x["aggregator"])):
        L.append(
            f"| {r['profile_tag']} | {r['preprocess']} | {r['aggregator']} | "
            f"{r['auc_floor']:.4f} | {r['direction']} | {r['clears_floor']} | {r['delta_vs_d1_baseline']:+.4f} |"
        )
    L.append("")

    L.append("## Phase 3 — controls (best trained row)")
    L.append(f"- Best row: **{best['preprocess']} / {best['aggregator']}** — floor **{best['auc_floor']:.4f}**")
    L.append(f"- max |ρ| vs six covariates: **{phase3['max_abs_rho']:.4f}** (D1 standard: ≤0.33) → **{phase3['passes_d1_rho_standard']}**")
    resid = phase3["residualisation"]["residualised_auc"]
    L.append(
        f"- Residualised on mapped events: R²={phase3['residualisation']['ols']['r2']:.6f}; "
        f"floor **{resid['auc_floor']:.4f}** ({resid['direction']})"
    )
    L.append("- Volume terciles (test mapped events):")
    for t in phase3["terciles"]:
        L.append(f"  - {t['tercile']}: floor **{t['auc_floor']:.4f}** (n={t['n']})")
    bh = phase3["benign_holdout"]
    L.append(
        f"- Benign-group holdout (Ward k={bh['chosen_k']}): pooled OOF floor **{bh['pooled_oof']['auc_floor']:.4f}**; "
        f"folds inverted **{bh['n_folds_inverted']}/{bh['chosen_k']}**"
    )
    L.append(
        f"- Shuffled labels: floor **{phase3['shuffled_labels']['auc_floor']:.4f}** "
        f"({phase3['shuffled_labels']['direction']})"
    )
    L.append("- Top per-node ablation drops:")
    for a in phase3["per_node_ablation"][:5]:
        L.append(f"  - {a['node']}: Δ **{a['delta_auc_floor']:.4f}**")
    L.append("")

    L.append("## Phase 4 — interpretation")
    if phase4["4a_beats_d1_after_controls"]:
        L.append(
            f"4a. **Yes** — {best['preprocess']}/{best['aggregator']} beats 0.8004 with margin "
            f"{best['delta_vs_d1_baseline']:+.4f} and passes D1 volume controls."
        )
    elif phase4["4a_beats_d1_raw_only"]:
        L.append(
            f"4a. **Raw only** — best row {best['preprocess']}/{best['aggregator']} floor {best['auc_floor']:.4f} "
            f"({best['delta_vs_d1_baseline']:+.4f}) but fails D1-equivalent volume controls."
        )
    else:
        L.append(
            "4a. **No** — no aggregator beats D1 centroid 0.8004 after controls 2–5. "
            "Euclidean centroid remains the empirically right aggregator; §A.8.3 mechanism stands, remedy does not."
        )
    L.append(
        f"4b. ZSTD vs RAW mean Δ floor (trained, matched aggregators): **{phase4['4b_zstd_minus_raw_mean_delta']:+.4f}**"
    )
    L.append(
        f"4c. Sparse vs L2 mean Δ (RAW trained): **{phase4['4c_sparse_minus_l2_mean_delta']:+.4f}**"
    )
    L.append(
        f"4d. Random-init best: {phase4['4d_random_init_best']['aggregator']}/{phase4['4d_random_init_best']['preprocess']} "
        f"**{phase4['4d_random_init_best']['auc_floor']:.4f}** vs trained best "
        f"**{phase4['4d_trained_best']['auc_floor']:.4f}** — random beats trained: **{phase4['4d_random_beats_trained']}**"
    )
    if phase4["4e_zstd_is_volume_norm"]:
        L.append(
            f"4e. ρ(SD, mapped share)={phase4['4e_rho_sd_share']:.4f}: ZSTD gains are substantially volume "
            f"normalisation; honest residualised floor **{resid['auc_floor']:.4f}**."
        )
    L.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="D-1 sparse aggregation on D1 profiles")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path("abrg/output/androct_2017/d1_sparse_aggregation"),
    )
    ap.add_argument(
        "--results-md",
        type=Path,
        default=Path("results/D1_sparse_aggregation.md"),
    )
    args = ap.parse_args()
    run(out_dir=args.output_dir, results_md=args.results_md)


if __name__ == "__main__":
    main()
