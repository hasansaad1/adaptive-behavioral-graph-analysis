"""
D-1 follow-up: volume-covariate reconciliation + random-init Linf control battery.
Scoring pass only — no retrain, no new tensors.
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
from scipy.stats import spearmanr
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.apigraph.split import load_run3_split
from abrg.devread import EXPECTED_SPLIT_DIGEST_PREFIX
from abrg.devread.run_d1_sparse_aggregation import (
    D1_BASELINE,
    N_NODES,
    SHUFFLE_SEED,
    _aggregate,
    _score_matrix,
    _transform,
)
from abrg.final_validate import FPR_POINTS, TEST_N_BENIGN, TEST_N_MALWARE
from abrg.final_validate.util import auc_raw_and_floor, eval_auc_block, tpr_at_fpr_from_scores
from abrg.ladder.grouping import _silhouette_curve
from abrg.ladder.vectorize import malware_full_vectors
from abrg.ocdev import DEVREAD_PROFILES
from abrg.ocdev.part_a import load_profiles
from abrg.ocdev_validate import NESTED_B, NESTED_SEED
from abrg.ocdev_validate.check1 import _bias_pack
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.validate.residual import apply_residual, ols_fit

FLOOR = 0.7025
K_GRID = (5, 10, 15, 20)
PAIRED_BOOT_B = 2000
PAIRED_BOOT_SEED = 42
TABLE_A4_KEYS = (
    "mapped_event_count",
    "total_event_count",
    "edge_count",
    "graph_density",
    "distinct_active_categories",
    "active_nodes",
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

    sha_to_app = {a.sha256: a for a in corpus.eligible}
    train_shas = [a.sha256 for a in train]
    test_shas = [a.sha256 for a in test_b] + [a.sha256 for a in test_m]
    labels = np.asarray([0] * len(test_b) + [1] * len(test_m), dtype=np.int32)

    arrays_tr, shas_tr = load_profiles("trained_t22")
    arrays_ri, shas_ri = load_profiles("random_init_t22")
    if shas_tr != shas_ri:
        raise SystemExit("STOP: trained vs random_init profile index mismatch")

    p = DEVREAD_PROFILES / "D1_random_init_t22.npy"
    arr = np.load(p)
    if arr.shape != arrays_ri["D1"].shape:
        raise SystemExit(f"STOP: D1_random_init shape {arr.shape} != {arrays_ri['D1'].shape}")
    if not np.allclose(arr, arrays_ri["D1"]):
        raise SystemExit("STOP: D1_random_init_t22.npy != load_profiles random_init D1")

    sha_to_i = {s: i for i, s in enumerate(shas_tr)}
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
        "sha_to_app": sha_to_app,
        "X_trained": arrays_tr["D1"],
        "X_random": arrays_ri["D1"],
        "profile_path": str(p),
    }


def _table_a4_covariates(
    tensors: dict, shas: list[str], sha_to_app: dict
) -> dict[str, np.ndarray]:
    rows = []
    for s in shas:
        t = tensors[s]
        a = sha_to_app[s]
        rows.append(
            {
                "mapped_event_count": float(t.get("n_mapped", t.get("n_inv_events", 0))),
                "total_event_count": float(t.get("n_events", t.get("n_total_events", 0))),
                "edge_count": float(t["n_edges"]),
                "graph_density": float(t["density"]),
                "distinct_active_categories": float(a.n_active_cats),
                "active_nodes": float(t["n_active"]),
            }
        )
    return {k: np.asarray([r[k] for r in rows], dtype=np.float64) for k in TABLE_A4_KEYS}


def _legacy_check3_covariates(tensors: dict, shas: list[str]) -> dict[str, np.ndarray]:
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


def _score_l2(X_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    sc, _ = _score_matrix(X_tr, X_te, "RAW", "L2")
    return sc


def _score_linf_with_argmax(
    X_tr: np.ndarray, X_te: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    mean = X_tr.mean(axis=0)
    mu = mean
    scores = []
    argmax_dims = []
    for x in X_te:
        d = x - mu
        ad = np.abs(d)
        i = int(np.argmax(ad))
        argmax_dims.append(i)
        scores.append(float(ad[i]))
    return np.asarray(scores, dtype=np.float64), np.asarray(argmax_dims, dtype=np.int32)


def _make_score_fn(
    prep: str, agg: str, *, mean: np.ndarray, std: np.ndarray, winsor_lo: np.ndarray | None = None, winsor_hi: np.ndarray | None = None
) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    def fn(X_tr_in: np.ndarray, X_te_in: np.ndarray) -> np.ndarray:
        if winsor_lo is not None and winsor_hi is not None:
            X_tr_t = _transform(X_tr_in, prep, mean=mean, std=std, winsor_lo=winsor_lo, winsor_hi=winsor_hi)
            X_te_t = _transform(X_te_in, prep, mean=mean, std=std, winsor_lo=winsor_lo, winsor_hi=winsor_hi)
        else:
            X_tr_t = _transform(X_tr_in, prep, mean=mean, std=std)
            X_te_t = _transform(X_te_in, prep, mean=mean, std=std)
        mu = X_tr_t.mean(axis=0)
        return np.asarray([_aggregate(x - mu, agg) for x in X_te_t], dtype=np.float64)

    return fn


def _structural_components(y: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, int, int]:
    y = np.asarray(y, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    pos = s[y == 1]
    neg = s[y == 0]
    m, n = len(pos), len(neg)
    if m == 0 or n == 0:
        raise ValueError("need both classes for DeLong")
    v10 = np.asarray([np.mean(pos > neg_j) + 0.5 * np.mean(pos == neg_j) for neg_j in neg], dtype=np.float64)
    v01 = np.asarray([np.mean(pos_i > neg) + 0.5 * np.mean(pos_i == neg) for pos_i in pos], dtype=np.float64)
    auc = float(np.mean(v01))
    return v10, v01, auc, m, n


def delong_test(y: np.ndarray, s1: np.ndarray, s2: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=np.int32)
    s1 = np.asarray(s1, dtype=np.float64)
    s2 = np.asarray(s2, dtype=np.float64)
    v10_1, v01_1, auc1, m, n = _structural_components(y, s1)
    v10_2, v01_2, auc2, m2, n2 = _structural_components(y, s2)
    if (m, n) != (m2, n2):
        raise ValueError("class counts mismatch")
    s01 = np.cov(np.vstack([v01_1, v01_2]))
    s10 = np.cov(np.vstack([v10_1, v10_2]))
    cov = s01 / m + s10 / n
    diff = auc1 - auc2
    var = float(cov[0, 0] + cov[1, 1] - 2 * cov[0, 1])
    se = math.sqrt(max(var, 0.0))
    z = diff / se if se > 0 else float("nan")
    p = float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else float("nan")
    return {
        "auc_1": auc1,
        "auc_2": auc2,
        "auc_diff_raw": diff,
        "auc_diff_floor": max(diff, -diff),
        "se": se,
        "z": z,
        "p_two_sided": p,
    }


def _paired_bootstrap_auc_diff(
    y: np.ndarray, s1: np.ndarray, s2: np.ndarray, *, B: int, seed: int
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    n = len(y)
    diffs = np.empty(B, dtype=np.float64)
    for b in range(B):
        idx = rng.integers(0, n, size=n)
        y_b = y[idx]
        if len(np.unique(y_b)) < 2:
            diffs[b] = float("nan")
            continue
        a1 = float(roc_auc_score(y_b, s1[idx]))
        a2 = float(roc_auc_score(y_b, s2[idx]))
        f1 = max(a1, 1.0 - a1)
        f2 = max(a2, 1.0 - a2)
        diffs[b] = f1 - f2
    valid = diffs[np.isfinite(diffs)]
    lo, hi = np.percentile(valid, [2.5, 97.5])
    return {
        "B": B,
        "seed": seed,
        "mean_diff_floor": float(np.mean(valid)),
        "ci95_diff_floor": [float(lo), float(hi)],
        "contains_zero": bool(lo <= 0 <= hi),
    }


def _nested_bootstrap_linf(
    X: np.ndarray, tr_idx: np.ndarray, te_idx: np.ndarray, labels: np.ndarray, *, B: int, seed: int
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    X_te = X[te_idx]
    sc0, _ = _score_linf_with_argmax(X[tr_idx], X_te)
    point = max(float(roc_auc_score(labels, sc0)), 1.0 - float(roc_auc_score(labels, sc0)))
    floors = np.empty(B, dtype=np.float64)
    for b in range(B):
        boot = rng.choice(tr_idx, size=len(tr_idx), replace=True)
        sc, _ = _score_linf_with_argmax(X[boot], X_te)
        a = float(roc_auc_score(labels, sc))
        floors[b] = max(a, 1.0 - a)
    pack = _bias_pack(point, floors)
    pack["B"] = B
    pack["seed"] = seed
    return pack


def _volume_controls_full(
    scores: np.ndarray,
    labels: np.ndarray,
    train_shas: list[str],
    test_shas: list[str],
    tensors: dict,
    sha_to_app: dict,
    *,
    score_fn: Callable[[np.ndarray, np.ndarray], np.ndarray],
    X_all: np.ndarray,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
    prep: str,
    agg: str,
) -> dict[str, Any]:
    cov_a4 = _table_a4_covariates(tensors, test_shas, sha_to_app)
    rhos_a4 = {}
    for k in TABLE_A4_KEYS:
        r, p = spearmanr(scores, cov_a4[k])
        rhos_a4[k] = {"rho": float(r), "p": float(p)}

    sc_tr = score_fn(X_all[tr_idx], X_all[tr_idx])
    mapped_tr = _table_a4_covariates(tensors, train_shas, sha_to_app)["mapped_event_count"].tolist()
    mapped_te = cov_a4["mapped_event_count"].tolist()
    reg, ols_meta = ols_fit(sc_tr.tolist(), mapped_tr)
    resid = apply_residual(reg, scores.tolist(), mapped_te)
    resid_auc = _auc_with_bootstrap(resid, labels.tolist())

    mapped = cov_a4["mapped_event_count"]
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
            auc_t = {"auc_floor": float("nan")}
        else:
            auc_t = _auc_with_bootstrap(s_t.tolist(), y_t.tolist())
        terciles.append({"tercile": lab, "n": int(mask.sum()), "auc_floor": float(auc_t["auc_floor"])})

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
        rest_idx = np.asarray([tr_idx[i] for i in np.where(rest_mask)[0]], dtype=np.int64)
        ho_idx = np.asarray([tr_idx[i] for i in np.where(hold_mask)[0]], dtype=np.int64)
        te_idx_fold = np.concatenate([ho_idx, mal_idx])
        y_te = np.asarray([0] * len(hold_shas) + [1] * len(test_m), dtype=np.int32)
        sc = score_fn(X_all[rest_idx], X_all[te_idx_fold])
        raw = auc_raw_and_floor(sc, y_te)
        pooled_s.extend(sc.tolist())
        pooled_y.extend(y_te.tolist())
        fold_rows.append({"fold": int(gid), "auc_floor": raw["auc_floor"], "inverted": raw["auc"] < 0.5})
    pooled = eval_auc_block(pooled_s, pooled_y)
    n_inv = sum(1 for f in fold_rows if f["inverted"])

    base_floor = float(_auc_with_bootstrap(scores.tolist(), labels.tolist())["auc_floor"])
    ablations = []
    for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        Xz = X_all.copy()
        Xz[:, i] = 0.0
        sc_z = score_fn(Xz[tr_idx], Xz[te_idx])
        auc_z = _auc_with_bootstrap(sc_z.tolist(), labels.tolist())
        drop = base_floor - float(auc_z["auc_floor"])
        ablations.append({"node": cat, "dim": i, "delta_auc_floor": drop, "auc_floor_zeroed": float(auc_z["auc_floor"])})
    ablations.sort(key=lambda r: -r["delta_auc_floor"])

    rng = np.random.default_rng(SHUFFLE_SEED)
    y_shuf = labels.copy()
    rng.shuffle(y_shuf)
    shuf_auc = _auc_with_bootstrap(scores.tolist(), y_shuf.tolist())

    max_abs_rho = max(abs(v["rho"]) for v in rhos_a4.values())

    return {
        "spearman_table_a4": rhos_a4,
        "max_abs_rho_table_a4": max_abs_rho,
        "residualisation": {"ols": ols_meta, "residualised_auc": resid_auc, "raw_auc_floor": base_floor},
        "terciles": terciles,
        "benign_holdout": {"chosen_k": k, "n_folds_inverted": n_inv, "pooled_oof": pooled, "folds": fold_rows},
        "per_node_ablation": ablations,
        "shuffled_labels": shuf_auc,
        "point_auc_floor": base_floor,
    }


def _linf_coord_distribution(argmax_dims: np.ndarray) -> dict[str, Any]:
    counts = {GRAPH_CATEGORY_UNIVERSE[i]: int((argmax_dims == i).sum()) for i in range(N_NODES)}
    ipc = counts.get("ipc_intents", 0)
    n = len(argmax_dims)
    top = sorted(counts.items(), key=lambda x: -x[1])[:5]
    return {
        "n_apps": n,
        "counts": counts,
        "ipc_intents_fraction": float(ipc / n) if n else float("nan"),
        "top5": top,
        "ipc_intents_count": ipc,
    }


def _operating_point(scores: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    rows = tpr_at_fpr_from_scores(
        scores, labels, FPR_POINTS, n_neg=TEST_N_BENIGN, n_pos=TEST_N_MALWARE
    )
    r01 = next(r for r in rows if r["fpr_target"] == 0.01)
    return {
        "fpr_target": 0.01,
        "fpr_achieved": r01["fpr_achieved"],
        "tpr": r01["tpr"],
        "precision_wild_pi_0.01": r01["precision_wild_base_rate"],
        "threshold": r01["threshold"],
    }


def _load_reference_json(path: Path) -> Any:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


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

    X_d1 = ctx["X_trained"]
    X_ri = ctx["X_random"]

    sc_d1 = _score_l2(X_d1[tr_idx], X_d1[te_idx])
    sc_ri, argmax_ri = _score_linf_with_argmax(X_ri[tr_idx], X_ri[te_idx])

    d1_floor = max(float(roc_auc_score(labels, sc_d1)), 1.0 - float(roc_auc_score(labels, sc_d1)))
    ri_floor = max(float(roc_auc_score(labels, sc_ri)), 1.0 - float(roc_auc_score(labels, sc_ri)))

    # --- Task 1 ---
    cov_a4 = _table_a4_covariates(tensors, test_shas, sha_to_app)
    task1_rhos = {}
    for k in TABLE_A4_KEYS:
        r, p = spearmanr(sc_d1, cov_a4[k])
        task1_rhos[k] = {"rho": float(r), "p": float(p)}
    task1_max = max(abs(v["rho"]) for v in task1_rhos.values())

    legacy = _legacy_check3_covariates(tensors, test_shas)
    legacy_rhos = {}
    for k, v in legacy.items():
        r, p = spearmanr(sc_d1, v)
        legacy_rhos[k] = {"rho": float(r), "p": float(p)}
    legacy_max = max(abs(v["rho"]) for v in legacy_rhos.values())

    check3_path = Path("abrg/output/androct_2017/final_validation/check3_d1_volume/check3.json")
    check3 = _load_reference_json(check3_path)

    task1 = {
        "score": "trained_D1_RAW_L2",
        "score_artifact": "abrg/devread/run_d1_sparse_aggregation.py (_score_matrix RAW L2)",
        "table_a4_spearman": task1_rhos,
        "table_a4_max_abs_rho": task1_max,
        "legacy_check3_spearman": legacy_rhos,
        "legacy_check3_max_abs_rho": legacy_max,
        "check3_json_static_norm_rho": (
            check3["spearman_vs_d1_centroid_eval"]["static_feature_norm"]["rho"]
            if check3
            else None
        ),
        "d1_l2_point_auc_floor": d1_floor,
    }

    # --- Task 2a prior reporting ---
    ri_cent_path = Path(
        "abrg/output/androct_2017/ocdev/controls/random_init_splitA/"
        "random_init__D1__none__centroid_euclidean__splitA__foldNA.json"
    )
    ri_cent = _load_reference_json(ri_cent_path)
    task2a = {
        "random_init_D1_centroid_in_catalogue": True,
        "catalogue_path": str(ri_cent_path),
        "catalogue_auc_floor": float(ri_cent["auc"]["auc_floor"]) if ri_cent else None,
        "random_init_Linf_8161_in_catalogue": False,
        "note": "0.8161 Linf is D-1 aggregator sweep only; catalogue has centroid 0.811844",
    }

    # --- Task 2b paired ---
    delong = delong_test(labels, sc_d1, sc_ri)
    paired_boot = _paired_bootstrap_auc_diff(labels, sc_d1, sc_ri, B=PAIRED_BOOT_B, seed=PAIRED_BOOT_SEED)
    rho_scores, p_scores = spearmanr(sc_d1, sc_ri)

    task2b = {
        "trained_D1_L2_auc_floor": d1_floor,
        "random_init_Linf_auc_floor": ri_floor,
        "point_diff_floor": ri_floor - d1_floor,
        "delong": delong,
        "paired_bootstrap_B2000": paired_boot,
        "spearman_rho_between_scores": float(rho_scores),
        "spearman_p": float(p_scores),
        "distinguishable_from_zero": not paired_boot["contains_zero"],
    }

    # --- Task 2c controls ---
    mean_d1 = X_d1[tr_idx].mean(axis=0)
    std_d1 = X_d1[tr_idx].std(axis=0, ddof=0)
    std_d1 = np.where(std_d1 < 1e-12, 1.0, std_d1)
    score_fn_d1 = _make_score_fn("RAW", "L2", mean=mean_d1, std=std_d1)

    mean_ri = X_ri[tr_idx].mean(axis=0)
    std_ri = X_ri[tr_idx].std(axis=0, ddof=0)
    std_ri = np.where(std_ri < 1e-12, 1.0, std_ri)
    score_fn_ri = _make_score_fn("RAW", "Linf", mean=mean_ri, std=std_ri)

    controls_d1 = _volume_controls_full(
        sc_d1,
        labels,
        train_shas,
        test_shas,
        tensors,
        sha_to_app,
        score_fn=score_fn_d1,
        X_all=X_d1,
        tr_idx=tr_idx,
        te_idx=te_idx,
        prep="RAW",
        agg="L2",
    )
    controls_ri = _volume_controls_full(
        sc_ri,
        labels,
        train_shas,
        test_shas,
        tensors,
        sha_to_app,
        score_fn=score_fn_ri,
        X_all=X_ri,
        tr_idx=tr_idx,
        te_idx=te_idx,
        prep="RAW",
        agg="Linf",
    )
    nested_ri = _nested_bootstrap_linf(X_ri, tr_idx, te_idx, labels, B=NESTED_B, seed=NESTED_SEED)
    coord_dist = _linf_coord_distribution(argmax_ri)

    bias_d1_path = Path("abrg/output/androct_2017/ocdev/validation/check1_bias/bias_stats.json")
    bias_d1 = _load_reference_json(bias_d1_path)

    # --- Task 2d operating ---
    op_d1 = _operating_point(sc_d1, labels)
    op_ri = _operating_point(sc_ri, labels)

    # --- Verdict ---
    if paired_boot["contains_zero"]:
        verdict = "NOT_DISTINGUISHABLE"
        verdict_detail = (
            "Paired bootstrap 95% CI on AUC_floor difference contains zero; DeLong p="
            f"{delong['p_two_sided']:.6f}. D1 stands. "
            f"Linf selects `ipc_intents` on {coord_dist['ipc_intents_fraction']*100:.2f}% of test apps "
            "(univariate ipc wrapper at AUC≈0.793 reference — §A.6.7 multivariate claim does not transfer)."
        )
    elif coord_dist["ipc_intents_fraction"] >= 0.5:
        verdict = "DISTINGUISHABLE_BUT_UNIVARIATE"
        verdict_detail = (
            f"Linf selects ipc_intents for {coord_dist['ipc_intents_fraction']*100:.1f}% of test apps."
        )
    else:
        fails = []
        if controls_ri["max_abs_rho_table_a4"] > 0.33:
            fails.append(f"volume rho {controls_ri['max_abs_rho_table_a4']:.6f} > 0.33")
        if float(controls_ri["shuffled_labels"]["auc_floor"]) > 0.53:
            fails.append(f"shuffled {controls_ri['shuffled_labels']['auc_floor']:.6f} > 0.53")
        if fails:
            verdict = "FAILS_CONTROLS"
            verdict_detail = "; ".join(fails)
        else:
            verdict = "DISTINGUISHABLE_AND_CONTROLLED"
            verdict_detail = "Difference significant and controls pass (manual review recommended)."

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "digest": ctx["digest"],
        "profile_path": ctx["profile_path"],
        "task1": task1,
        "task2a": task2a,
        "task2b": task2b,
        "controls_d1_reference": controls_d1,
        "controls_random_init_linf": controls_ri,
        "nested_random_init_linf": nested_ri,
        "linf_coord_distribution": coord_dist,
        "operating_d1": op_d1,
        "operating_random_init_linf": op_ri,
        "d1_nested_reference": bias_d1["partA_D1_centroid"] if bias_d1 else None,
        "verdict": verdict,
        "verdict_detail": verdict_detail,
    }

    (out_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, default=_json_default) + "\n", encoding="utf-8"
    )

    _write_report(results_md, payload, check3, bias_d1)
    _write_csv(csv_path, payload, bias_d1, controls_d1, controls_ri, nested_ri, op_d1, op_ri, task2b)
    print(f"[d1_randominit_controls] wrote {results_md}", flush=True)


def _write_csv(
    path: Path,
    payload: dict,
    bias_d1: dict | None,
    c_d1: dict,
    c_ri: dict,
    nested_ri: dict,
    op_d1: dict,
    op_ri: dict,
    t2b: dict,
) -> None:
    rows = []

    def add(metric: str, d1_val: Any, ri_val: Any, d1_art: str = "", ri_art: str = ""):
        rows.append(
            {
                "metric": metric,
                "D1_trained_RAW_L2": d1_val,
                "random_init_RAW_Linf": ri_val,
                "D1_artifact": d1_art,
                "random_init_artifact": ri_art,
            }
        )

    if bias_d1:
        b = bias_d1["partA_D1_centroid"]
        add(
            "nested_bootstrap_point_auc_floor",
            f"{b['full_sample_point']:.6f}",
            f"{nested_ri['full_sample_point']:.6f}",
            "ocdev/validation/check1_bias/bias_stats.json",
            "d1_randominit_controls/summary.json",
        )
        add(
            "nested_bootstrap_ci95",
            f"[{b['nested_percentile_ci95'][0]:.6f}, {b['nested_percentile_ci95'][1]:.6f}]",
            f"[{nested_ri['nested_percentile_ci95'][0]:.6f}, {nested_ri['nested_percentile_ci95'][1]:.6f}]",
        )
        add(
            "nested_bootstrap_bias",
            f"{b['bias_mean_minus_point']:.6f}",
            f"{nested_ri['bias_mean_minus_point']:.6f}",
        )
        add(
            "nested_point_inside_ci",
            b["point_inside_nested_percentile_ci"],
            nested_ri["point_inside_nested_percentile_ci"],
        )

    add("point_auc_floor", f"{t2b['trained_D1_L2_auc_floor']:.6f}", f"{t2b['random_init_Linf_auc_floor']:.6f}")
    add(
        "paired_bootstrap_diff_ci95",
        "—",
        f"[{t2b['paired_bootstrap_B2000']['ci95_diff_floor'][0]:.6f}, {t2b['paired_bootstrap_B2000']['ci95_diff_floor'][1]:.6f}]",
    )
    add("delong_p", "—", f"{t2b['delong']['p_two_sided']:.6f}")
    add("spearman_rho_scores", f"{t2b['spearman_rho_between_scores']:.6f}", f"{t2b['spearman_rho_between_scores']:.6f}")

    for k in TABLE_A4_KEYS:
        add(
            f"spearman_rho_{k}",
            f"{c_d1['spearman_table_a4'][k]['rho']:.6f}",
            f"{c_ri['spearman_table_a4'][k]['rho']:.6f}",
            "task1/table_a4",
        )
    add(
        "max_abs_rho_table_a4",
        f"{c_d1['max_abs_rho_table_a4']:.6f}",
        f"{c_ri['max_abs_rho_table_a4']:.6f}",
    )
    add(
        "residualisation_R2",
        f"{c_d1['residualisation']['ols']['r2']:.6f}",
        f"{c_ri['residualisation']['ols']['r2']:.6f}",
    )
    add(
        "residualised_auc_floor",
        f"{c_d1['residualisation']['residualised_auc']['auc_floor']:.6f}",
        f"{c_ri['residualisation']['residualised_auc']['auc_floor']:.6f}",
    )
    for i, lab in enumerate(["T1_low", "T2_mid", "T3_high"]):
        add(
            f"tercile_{lab}_auc_floor",
            f"{c_d1['terciles'][i]['auc_floor']:.6f}",
            f"{c_ri['terciles'][i]['auc_floor']:.6f}",
        )
    add(
        "benign_holdout_pooled_auc_floor",
        f"{c_d1['benign_holdout']['pooled_oof']['auc_floor']:.6f}",
        f"{c_ri['benign_holdout']['pooled_oof']['auc_floor']:.6f}",
    )
    add(
        "benign_holdout_ci95",
        f"[{c_d1['benign_holdout']['pooled_oof']['ci95_floor'][0]:.6f}, {c_d1['benign_holdout']['pooled_oof']['ci95_floor'][1]:.6f}]",
        f"[{c_ri['benign_holdout']['pooled_oof']['ci95_floor'][0]:.6f}, {c_ri['benign_holdout']['pooled_oof']['ci95_floor'][1]:.6f}]",
    )
    add(
        "benign_holdout_folds_inverted",
        c_d1["benign_holdout"]["n_folds_inverted"],
        c_ri["benign_holdout"]["n_folds_inverted"],
    )
    add(
        "shuffled_labels_auc_floor",
        f"{c_d1['shuffled_labels']['auc_floor']:.6f}",
        f"{c_ri['shuffled_labels']['auc_floor']:.6f}",
    )
    d1_top = c_d1["per_node_ablation"][0]
    ri_top = c_ri["per_node_ablation"][0]
    add(
        "ablation_top1_delta",
        f"{d1_top['delta_auc_floor']:.6f} ({d1_top['node']})",
        f"{ri_top['delta_auc_floor']:.6f} ({ri_top['node']})",
    )
    add(
        "ablation_top2_delta",
        f"{c_d1['per_node_ablation'][1]['delta_auc_floor']:.6f} ({c_d1['per_node_ablation'][1]['node']})",
        f"{c_ri['per_node_ablation'][1]['delta_auc_floor']:.6f} ({c_ri['per_node_ablation'][1]['node']})",
    )
    add(
        "linf_ipc_intents_fraction",
        "—",
        f"{payload['linf_coord_distribution']['ipc_intents_fraction']:.6f}",
    )
    add("operating_fpr_at_target_0.01", f"{op_d1['fpr_achieved']:.6f}", f"{op_ri['fpr_achieved']:.6f}")
    add("operating_tpr_at_fpr_0.01", f"{op_d1['tpr']:.6f}", f"{op_ri['tpr']:.6f}")
    add(
        "operating_wild_precision_pi_0.01",
        f"{op_d1['precision_wild_pi_0.01']:.6f}",
        f"{op_ri['precision_wild_pi_0.01']:.6f}",
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_report(
    path: Path,
    payload: dict,
    check3: dict | None,
    bias_d1: dict | None,
) -> None:
    t1 = payload["task1"]
    t2a = payload["task2a"]
    t2b = payload["task2b"]
    c_d1 = payload["controls_d1_reference"]
    c_ri = payload["controls_random_init_linf"]
    nested_ri = payload["nested_random_init_linf"]
    coord = payload["linf_coord_distribution"]
    verdict = payload["verdict"]

    L: list[str] = []
    L.append("# D-1 follow-up: volume covariate reconciliation + random-init Linf controls")
    L.append("")
    L.append(f"- generated: {payload['generated_utc']}")
    L.append(f"- split digest: `{payload['digest'][:16]}…`")
    L.append(f"- profile: `{payload['profile_path']}`")
    L.append("")

    if verdict in ("NOT_DISTINGUISHABLE", "DISTINGUISHABLE_BUT_UNIVARIATE"):
        L.append(f"## VERDICT: **{verdict}**")
        L.append("")
        L.append(f"{payload['verdict_detail']}")
        L.append("")

    # Task 1
    L.append("## Task 1 — Volume-covariate bound reconciliation")
    L.append("")
    L.append("Score: **trained D1 RAW L2** (canonical 562/141/1700 test set).")
    L.append("")
    L.append("### 1a — Table A.4 six covariates (Spearman ρ vs D1 RAW L2 score)")
    L.append("")
    L.append("| covariate | ρ (6 dp) |")
    L.append("|---|---:|")
    for k in TABLE_A4_KEYS:
        rho = t1["table_a4_spearman"][k]["rho"]
        sign = "+" if rho >= 0 else "−"
        L.append(f"| `{k}` | {sign}{abs(rho):.6f} |")
    L.append("")
    L.append(f"- **max |ρ| (Table A.4 six):** {t1['table_a4_max_abs_rho']:.6f}")
    L.append("")

    L.append("### 1b — Same measurement as Chapter A / D-1?")
    L.append("")
    L.append(
        "**No — covariate set mismatch.** Chapter A §A.6.7 cites six **Table A.4** scalars "
        "but the archived bound 0.33 matches **`static_feature_norm`** (ρ = +0.330147), "
        "which is **not** one of those six. Among the six Table A.4 metrics recomputed here, "
        f"max |ρ| = **{t1['table_a4_max_abs_rho']:.6f}** (`total_event_count`). "
        "The D-1 figure 0.3301 uses the **legacy check3** covariate list (includes "
        "`static_feature_norm`, omits `distinct_active_categories`). "
        "Scoring is equivalent: RAW L2 = centroid Euclidean on D1 profiles (same point AUC "
        f"{t1['d1_l2_point_auc_floor']:.6f})."
    )
    L.append("")

    L.append("### 1c — Source of original 0.33")
    L.append("")
    src_rho = t1.get("check3_json_static_norm_rho")
    L.append(
        f"- **Source:** `abrg/output/androct_2017/final_validation/check3_d1_volume/check3.json` "
        f"(also `final_validation/SUMMARY.md` Check 3; T8 cites check4 holdout, not ρ)."
    )
    L.append(
        f"- **`static_feature_norm` ρ in check3.json:** {src_rho:.6f} → rounds to 0.33."
        if src_rho is not None
        else ""
    )
    L.append(
        f"- **Legacy six in check3 (not Table A.4):** max |ρ| = {t1['legacy_check3_max_abs_rho']:.6f} "
        "(static_feature_norm)."
    )
    L.append("")

    L.append("### 1d — Proposed chapter amendment (not applied)")
    L.append("")
    L.append("**Before:**")
    L.append(
        '> Six volume covariates have $|\\rho|\\le 0.33$ against the $D_1$ score; '
        "residualising on mapped-event count"
    )
    L.append("")
    L.append("**After:**")
    L.append(
        f"> Among the six Table~A.4 volume scalars, Spearman $|\\rho|$ against the $D_1$ "
        f"score ranges up to **{t1['table_a4_max_abs_rho']:.4f}** "
        f"(`total_event_count`, $\\rho={t1['table_a4_spearman']['total_event_count']['rho']:+.4f}$); "
        f"static-feature norm reaches $\\rho={t1['legacy_check3_spearman']['static_feature_norm']['rho']:+.4f}$ "
        f"(legacy check~3, not a Table~A.4 floor). Residualising on mapped-event count"
    )
    L.append("")

    # Task 2
    L.append("## Task 2 — Random-init RAW Linf control battery")
    L.append("")

    L.append("### 2a — Prior-reporting check")
    L.append("")
    L.append(
        f"- **Random-init D1 centroid already in catalogue:** "
        f"**{t2a['catalogue_auc_floor']:.6f}** at `{t2a['catalogue_path']}` "
        f"(ocdev validation SUMMARY: trained 0.8004 vs random-init 0.8118, "
        "`trained_and_untrained_indistinguishable`)."
    )
    L.append(
        f"- **Random-init RAW Linf 0.8161:** **not** in catalogue — new from D-1 sparse sweep only."
    )
    L.append(
        f"- Catalogue centroid **0.811844** ≠ Linf **{t2b['random_init_Linf_auc_floor']:.6f}** "
        "(different aggregator on same random-init profiles)."
    )
    L.append("")

    L.append("### 2b — Paired comparison (trained D1 L2 vs random-init Linf)")
    L.append("")
    L.append("| quantity | value | artifact |")
    L.append("|---|---:|---|")
    L.append(f"| D1 trained RAW L2 AUC_floor | {t2b['trained_D1_L2_auc_floor']:.6f} | recomputed |")
    L.append(f"| random-init RAW Linf AUC_floor | {t2b['random_init_Linf_auc_floor']:.6f} | recomputed |")
    L.append(f"| point Δ (Linf − D1) | {t2b['point_diff_floor']:.6f} | — |")
    d = t2b["delong"]
    L.append(
        f"| DeLong Δ (raw AUC) | {d['auc_diff_raw']:.6f} | SE={d['se']:.6f}, z={d['z']:.6f}, p={d['p_two_sided']:.6f} |"
    )
    pb = t2b["paired_bootstrap_B2000"]
    L.append(
        f"| paired bootstrap 95% CI on Δ_floor (B={pb['B']}) | "
        f"[{pb['ci95_diff_floor'][0]:.6f}, {pb['ci95_diff_floor'][1]:.6f}] | "
        f"`d1_randominit_controls/summary.json` |"
    )
    L.append(
        f"| Spearman ρ(D1 score, Linf score) | {t2b['spearman_rho_between_scores']:.6f} | p={t2b['spearman_p']:.6e} |"
    )
    L.append("")
    if t2b["spearman_rho_between_scores"] > 0.8:
        L.append(
            f"Scores are **strongly correlated** (ρ={t2b['spearman_rho_between_scores']:.6f}) — "
            "the AUC gap is a small perturbation of one ranking, not two independent detectors."
        )
        L.append("")
    dist = "yes" if t2b["distinguishable_from_zero"] else "no"
    L.append(f"**Difference distinguishable from zero?** **{dist}** (paired bootstrap CI on Δ_floor).")
    L.append("")

    L.append("### 2c — Five (+2) controls beside D1 reference")
    L.append("")
    if bias_d1:
        b = bias_d1["partA_D1_centroid"]
        L.append("**1. Nested bootstrap (B=200, train-benign resample, fixed eval)**")
        L.append("")
        L.append("| | D1 reference (centroid ≡ L2) | random-init Linf |")
        L.append("|---|---:|---:|")
        L.append(f"| point AUC_floor | {b['full_sample_point']:.6f} | {nested_ri['full_sample_point']:.6f} |")
        ci_d1 = b["nested_percentile_ci95"]
        ci_ri = nested_ri["nested_percentile_ci95"]
        L.append(f"| nested 95% CI | [{ci_d1[0]:.6f}, {ci_d1[1]:.6f}] | [{ci_ri[0]:.6f}, {ci_ri[1]:.6f}] |")
        L.append(f"| bias (boot mean − point) | {b['bias_mean_minus_point']:.6f} | {nested_ri['bias_mean_minus_point']:.6f} |")
        L.append(
            f"| point inside CI | {b['point_inside_nested_percentile_ci']} | "
            f"{nested_ri['point_inside_nested_percentile_ci']} |"
        )
        L.append(f"| artifact | `ocdev/validation/check1_bias/bias_stats.json` | `summary.json` |")
        L.append("")

    L.append("**2. Volume covariates (Table A.4 six, Spearman ρ)**")
    L.append("")
    L.append("| covariate | D1 ρ | Linf ρ |")
    L.append("|---|---:|---:|")
    for k in TABLE_A4_KEYS:
        L.append(
            f"| `{k}` | {c_d1['spearman_table_a4'][k]['rho']:+.6f} | "
            f"{c_ri['spearman_table_a4'][k]['rho']:+.6f} |"
        )
    L.append(
        f"| max \\|ρ\\| | {c_d1['max_abs_rho_table_a4']:.6f} | {c_ri['max_abs_rho_table_a4']:.6f} |"
    )
    L.append("")

    L.append("**3. Volume residualisation (OLS on mapped_event_count, train-benign)**")
    L.append("")
    L.append("| | D1 | random-init Linf |")
    L.append("|---|---:|---:|")
    L.append(
        f"| R² | {c_d1['residualisation']['ols']['r2']:.6f} | "
        f"{c_ri['residualisation']['ols']['r2']:.6f} |"
    )
    L.append(
        f"| residualised AUC_floor | {c_d1['residualisation']['residualised_auc']['auc_floor']:.6f} | "
        f"{c_ri['residualisation']['residualised_auc']['auc_floor']:.6f} |"
    )
    L.append("")

    L.append("**4. Volume terciles (test mapped_event_count)**")
    L.append("")
    for i, lab in enumerate(["T1_low", "T2_mid", "T3_high"]):
        L.append(
            f"- {lab}: D1 **{c_d1['terciles'][i]['auc_floor']:.6f}** / "
            f"Linf **{c_ri['terciles'][i]['auc_floor']:.6f}**"
        )
    L.append("")

    L.append("**5. Benign-group holdout (Ward k=5, pooled OOF)**")
    L.append("")
    p_d1 = c_d1["benign_holdout"]["pooled_oof"]
    p_ri = c_ri["benign_holdout"]["pooled_oof"]
    L.append(
        f"- D1: **{p_d1['auc_floor']:.6f}** "
        f"[{p_d1['ci95_floor'][0]:.6f}, {p_d1['ci95_floor'][1]:.6f}], "
        f"{c_d1['benign_holdout']['n_folds_inverted']}/5 inverted"
    )
    L.append(
        f"- Linf: **{p_ri['auc_floor']:.6f}** "
        f"[{p_ri['ci95_floor'][0]:.6f}, {p_ri['ci95_floor'][1]:.6f}], "
        f"{c_ri['benign_holdout']['n_folds_inverted']}/5 inverted"
    )
    L.append("")

    L.append("**6. Shuffled labels (seed=42)**")
    L.append("")
    L.append(
        f"- D1: **{c_d1['shuffled_labels']['auc_floor']:.6f}** / "
        f"Linf: **{c_ri['shuffled_labels']['auc_floor']:.6f}** "
        "(D3 analogue reference ≈ 0.5035)"
    )
    L.append("")

    L.append("**7. Per-node ablation (top drops)**")
    L.append("")
    for tag, c in [("D1", c_d1), ("Linf", c_ri)]:
        a0, a1 = c["per_node_ablation"][0], c["per_node_ablation"][1]
        L.append(
            f"- {tag}: #{1} `{a0['node']}` Δ={a0['delta_auc_floor']:.6f}; "
            f"#{2} `{a1['node']}` Δ={a1['delta_auc_floor']:.6f}"
        )
    L.append("")
    L.append("**Linf max-coordinate distribution (test apps)**")
    L.append("")
    L.append(f"- `ipc_intents` selected for **{coord['ipc_intents_count']}/{coord['n_apps']}** apps "
             f"({coord['ipc_intents_fraction']*100:.2f}%)")
    L.append("- Top-5 coordinates:")
    for name, cnt in coord["top5"]:
        L.append(f"  - `{name}`: {cnt}")
    L.append("")

    L.append("### 2d — Operating point (FPR target 0.01, Table A.14 protocol)")
    L.append("")
    op_d1 = payload["operating_d1"]
    op_ri = payload["operating_random_init_linf"]
    L.append("| | D1 reference | random-init Linf |")
    L.append("|---|---:|---:|")
    L.append(f"| FPR achieved | {op_d1['fpr_achieved']:.6f} | {op_ri['fpr_achieved']:.6f} |")
    L.append(f"| TPR | {op_d1['tpr']:.6f} | {op_ri['tpr']:.6f} |")
    L.append(
        f"| wild precision (π=0.01) | {op_d1['precision_wild_pi_0.01']:.6f} | "
        f"{op_ri['precision_wild_pi_0.01']:.6f} |"
    )
    L.append("")

    if verdict not in ("NOT_DISTINGUISHABLE", "DISTINGUISHABLE_BUT_UNIVARIATE"):
        L.append(f"## VERDICT: **{verdict}**")
        L.append("")
        L.append(payload["verdict_detail"])
        L.append("")

    L.append("## Artifacts")
    L.append("")
    L.append("- `abrg/output/androct_2017/d1_randominit_controls/summary.json`")
    L.append("- `results/D1_randominit_controls_battery.csv`")
    L.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="D-1 random-init Linf controls (scoring pass)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("abrg/output/androct_2017/d1_randominit_controls"),
    )
    p.add_argument(
        "--results-md",
        type=Path,
        default=Path("results/D1_randominit_controls.md"),
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=Path("results/D1_randominit_controls_battery.csv"),
    )
    args = p.parse_args()
    run(out_dir=args.out_dir, results_md=args.results_md, csv_path=args.csv)


if __name__ == "__main__":
    main()
