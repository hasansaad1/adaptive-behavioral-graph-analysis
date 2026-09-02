"""Check 3 — Split-B pooled vs weighted divergence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.ocdev import LADDER_ASSIGNMENTS_PATH, LADDER_HOLDOUT_PATH
from abrg.ocdev.detectors import fit_score_mahalanobis
from abrg.ocdev.part_a import load_profiles
from abrg.ocdev_validate.util import score_dist_block, write_json

BEST_SPLITB = ("D4", "mahalanobis")  # weighted 0.8083 in ocdev SUMMARY
EPS = 1e-12


def _auc_floor(scores: np.ndarray, labels: np.ndarray) -> float:
    a = float(roc_auc_score(labels, scores))
    return max(a, 1.0 - a)


def run_check3(*, out: Path, split_bundle: Any, tensors: dict[str, dict]) -> dict[str, Any]:
    fset, det = BEST_SPLITB
    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    X = arrays[fset]

    assignments = {
        str(k): int(v)
        for k, v in json.loads(LADDER_ASSIGNMENTS_PATH.read_text())["ward"]["assignments"].items()
    }
    ladder = json.loads(LADDER_HOLDOUT_PATH.read_text())
    groups: dict[int, list[str]] = {}
    for sha, gid in assignments.items():
        groups.setdefault(int(gid), []).append(sha)
    meta = {int(f["group_id"]): int(f["n_malware_holdout"]) for f in ladder["folds"]}
    if sorted(groups) != sorted(meta):
        raise SystemExit("STOP: split-B fold ids != ladder")

    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train_b = [a.sha256 for a in split["train"]]
    test_ben = [a.sha256 for a in split["test_benign"]]
    if any(a.label != "benign" for a in split["train"]):
        raise SystemExit("STOP: non-benign in fit()")

    tr_idx = np.asarray([sha_to_i[s] for s in train_b], dtype=np.int64)
    # one fit — train benign is fixed across folds
    sc_tr, fitted = fit_score_mahalanobis(X[tr_idx], X[tr_idx])
    sc_tr = np.asarray(sc_tr, dtype=np.float64)
    mu, sd = float(sc_tr.mean()), float(sc_tr.std(ddof=1) if sc_tr.size > 1 else 0.0)

    from abrg.ocdev.detectors import score_with_fitted

    fold_rows = []
    pooled_s: list[float] = []
    pooled_y: list[int] = []
    pooled_z: list[float] = []
    unique_mal_s: list[float] = []
    unique_mal_y: list[int] = []
    unique_mal_z: list[float] = []
    tb_idx = np.asarray([sha_to_i[s] for s in test_ben], dtype=np.int64)
    sc_tb = np.asarray(score_with_fitted(fitted, X[tb_idx], "mahalanobis"), dtype=np.float64)
    z_tb = (sc_tb - mu) / (sd + EPS)

    mapped = {
        s: float(tensors[s].get("n_mapped", tensors[s].get("n_inv_events", 0)))
        for s in test_ben + [a.sha256 for a in split["test_malware"]]
    }

    for gid in sorted(groups):
        hold = groups[gid]
        te_idx_m = np.asarray([sha_to_i[s] for s in hold], dtype=np.int64)
        sc_m = np.asarray(score_with_fitted(fitted, X[te_idx_m], "mahalanobis"), dtype=np.float64)
        z_m = (sc_m - mu) / (sd + EPS)
        sc_te = np.concatenate([sc_tb, sc_m])
        z_te = np.concatenate([z_tb, z_m])
        y_te = np.asarray([0] * len(test_ben) + [1] * len(hold), dtype=np.int32)
        af = _auc_floor(sc_te, y_te)
        af_z = _auc_floor(z_te, y_te)
        floor_scores = np.asarray([mapped[s] for s in test_ben + hold], dtype=np.float64)
        trivial = _auc_floor(floor_scores, y_te)
        fold_rows.append(
            {
                "fold": gid,
                "n_test": int(len(test_ben) + len(hold)),
                "n_benign": int(len(test_ben)),
                "n_malware": int(len(hold)),
                "auc_floor": af,
                "auc_floor_zscored": af_z,
                "trivial_floor_mapped_event_count": trivial,
                "score_test_benign": score_dist_block(sc_tb),
                "score_test_malware": score_dist_block(sc_m),
                "score_all_test": score_dist_block(sc_te),
            }
        )
        pooled_s.extend(sc_te.tolist())
        pooled_y.extend(y_te.tolist())
        pooled_z.extend(z_te.tolist())
        unique_mal_s.extend(sc_m.tolist())
        unique_mal_y.extend([1] * len(hold))
        unique_mal_z.extend(z_m.tolist())

    fold_aucs = np.asarray([r["auc_floor"] for r in fold_rows], dtype=np.float64)
    weights = np.asarray([r["n_test"] for r in fold_rows], dtype=np.float64)
    weighted = float(np.average(fold_aucs, weights=weights))
    pooled = _auc_with_bootstrap(pooled_s, pooled_y)
    pooled_z_auc = _auc_with_bootstrap(pooled_z, pooled_y)

    # de-duplicated: 141 test benign once + 1700 malware once (detector identical across folds)
    uniq_s = np.concatenate([sc_tb, np.asarray(unique_mal_s)])
    uniq_y = np.concatenate([np.zeros(len(test_ben), dtype=np.int32), np.ones(len(unique_mal_y), dtype=np.int32)])
    uniq_z = np.concatenate([z_tb, np.asarray(unique_mal_z)])
    uniq = _auc_with_bootstrap(uniq_s.tolist(), uniq_y.tolist())
    uniq_z_auc = _auc_with_bootstrap(uniq_z.tolist(), uniq_y.tolist())

    # range overlap: do fold malware score ranges overlap the (shared) benign range?
    bmin, bmax = float(sc_tb.min()), float(sc_tb.max())
    overlap_rows = []
    for r in fold_rows:
        mm, mx = r["score_test_malware"]["min"], r["score_test_malware"]["max"]
        overlap_rows.append(
            {
                "fold": r["fold"],
                "malware_range": [mm, mx],
                "benign_range": [bmin, bmax],
                "ranges_overlap": not (mx < bmin or mm > bmax),
            }
        )

    med_all = np.asarray([r["score_all_test"]["median"] for r in fold_rows])
    med_m = np.asarray([r["score_test_malware"]["median"] for r in fold_rows])
    med_b = np.asarray([r["score_test_benign"]["median"] for r in fold_rows])
    within_var = np.asarray(
        [r["score_all_test"]["std"] ** 2 for r in fold_rows], dtype=np.float64
    )
    var_between_median = float(np.var(med_all, ddof=1))
    var_within_mean = float(np.mean(within_var))
    ratio = var_between_median / var_within_mean if var_within_mean else float("nan")

    n_mal = np.asarray([r["n_malware"] for r in fold_rows], dtype=np.float64)
    triv = np.asarray([r["trivial_floor_mapped_event_count"] for r in fold_rows], dtype=np.float64)
    rho_n, p_n = spearmanr(fold_aucs, n_mal)
    rho_f, p_f = spearmanr(fold_aucs, triv)

    delta_raw = abs(float(pooled["auc_floor"]) - weighted)
    delta_z = abs(float(pooled_z_auc["auc_floor"]) - weighted)
    scale_confirmed = bool(delta_z < delta_raw - 1e-6)

    n_benign_pooled = int(sum(r["n_benign"] for r in fold_rows))
    payload = {
        "config": {"feature_set": fset, "detector": det, "train_benign_fixed_across_folds": True},
        "n_folds": len(fold_rows),
        "n_test_benign_unique": len(test_ben),
        "n_benign_rows_in_pooled": n_benign_pooled,
        "benign_replication_factor": n_benign_pooled / max(len(test_ben), 1),
        "n_malware_unique": int(sum(r["n_malware"] for r in fold_rows)),
        "train_benign_score": score_dist_block(sc_tr),
        "zscore": {"mean_train_benign": mu, "sd_train_benign": sd, "eps": EPS},
        "weighted_mean_auc_floor": weighted,
        "mean_auc_floor": float(np.mean(fold_aucs)),
        "std_auc_floor": float(np.std(fold_aucs, ddof=1)),
        "pooled_oof_raw": pooled,
        "pooled_oof_zscored": pooled_z_auc,
        "deduplicated_pooled_raw": uniq,
        "deduplicated_pooled_zscored": uniq_z_auc,
        "scale_hypothesis": {
            "abs_weighted_minus_raw_pooled": delta_raw,
            "abs_weighted_minus_z_pooled": delta_z,
            "z_moves_toward_weighted": scale_confirmed,
        },
        "between_vs_within": {
            "var_fold_median_all": var_between_median,
            "var_fold_median_malware": float(np.var(med_m, ddof=1)),
            "var_fold_median_benign": float(np.var(med_b, ddof=1)),
            "mean_within_fold_variance": var_within_mean,
            "ratio_between_median_over_mean_within": ratio,
            "benign_medians_identical_across_folds": bool(np.allclose(med_b, med_b[0])),
        },
        "range_overlap": overlap_rows,
        "spearman": {
            "auc_vs_n_malware": {"rho": float(rho_n), "pvalue": float(p_n)},
            "auc_vs_trivial_floor": {"rho": float(rho_f), "pvalue": float(p_f)},
        },
        "folds": fold_rows,
        "thesis_carries": {
            "figure": "weighted_mean_auc_floor",
            "value": weighted,
            "optimistic_vs_global_ranking": True,
            "global_ranking_deduplicated_pooled": float(uniq["auc_floor"]),
            "reason": (
                "scale hypothesis not confirmed: z-scored pooled equals raw pooled "
                f"({pooled['auc_floor']:.4f}); train-benign fit is identical across folds "
                "so per-fold detectors share one affine scale and AUC is rank-based. "
                f"fold n_malware ranges {int(n_mal.min())}–{int(n_mal.max())}; "
                f"Spearman AUC vs n_malware ρ={float(rho_n):.3f}. "
                "weighted mean of per-fold AUCs is the Split-B protocol figure and is "
                f"optimistic relative to the single global ranking "
                f"(deduplicated pooled {uniq['auc_floor']:.4f})"
            ),
        },
    }
    write_json(out / "check3.json", payload)
    return payload
