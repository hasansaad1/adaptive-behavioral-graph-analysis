"""Check 4 — D1 under genuine benign-group holdout (GAE weights fixed)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from abrg.final_validate.util import auc_raw_and_floor, eval_auc_block, score_dist, write_json
from abrg.ladder.grouping import _silhouette_curve
from abrg.ladder.vectorize import malware_full_vectors
from abrg.ocdev.detectors import fit_score_centroid_euclidean, fit_score_mahalanobis

K_GRID = (5, 10, 15, 20)


def run_check4(*, out: Path, split_bundle: Any, tensors: dict[str, dict]) -> dict[str, Any]:
    from abrg.ocdev.part_a import load_profiles

    out.mkdir(parents=True, exist_ok=True)
    train_b = [a.sha256 for a in split_bundle.train]
    test_m = [a.sha256 for a in split_bundle.test_malware]
    assert all(a.label == "benign" for a in split_bundle.train)

    print("[final_validate/C4] clustering 562 train-benign (Ward, k in {5,10,15,20}) …", flush=True)
    X_ben = malware_full_vectors(tensors, train_b, mode="full")
    X_ben = np.nan_to_num(X_ben, nan=0.0, posinf=0.0, neginf=0.0)
    Xs = StandardScaler().fit_transform(X_ben)
    sil = _silhouette_curve(Xs, K_GRID, method="ward")
    k = int(sil["chosen_k"])
    labels_cl = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Xs)
    sizes = {int(c): int((labels_cl == c).sum()) for c in sorted(set(labels_cl.tolist()))}

    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    D1 = arrays["D1"]
    mal_idx = np.asarray([sha_to_i[s] for s in test_m], dtype=np.int64)

    print(
        f"[final_validate/C4] GAE weights held fixed; centroid/Mahalanobis reference "
        f"recomputed per fold on D1 profiles. chosen_k={k}",
        flush=True,
    )

    def _holdout(det_name: str, fit_fn) -> dict[str, Any]:
        fold_rows = []
        pooled_s: list[float] = []
        pooled_y: list[int] = []
        for gid in sorted(sizes):
            hold_mask = labels_cl == gid
            rest_mask = ~hold_mask
            hold_shas = [train_b[i] for i in np.where(hold_mask)[0]]
            rest_shas = [train_b[i] for i in np.where(rest_mask)[0]]
            tr_idx = np.asarray([sha_to_i[s] for s in rest_shas], dtype=np.int64)
            ho_idx = np.asarray([sha_to_i[s] for s in hold_shas], dtype=np.int64)
            te_idx = np.concatenate([ho_idx, mal_idx])
            y_te = np.asarray([0] * len(hold_shas) + [1] * len(test_m), dtype=np.int32)
            sc, _ = fit_fn(D1[tr_idx], D1[te_idx])
            sc = np.asarray(sc, dtype=np.float64)
            raw = auc_raw_and_floor(sc, y_te)
            pooled_s.extend(sc.tolist())
            pooled_y.extend(y_te.tolist())
            fold_rows.append(
                {
                    "fold": int(gid),
                    "n_holdout_benign": len(hold_shas),
                    "n_malware": len(test_m),
                    "n_test": int(len(te_idx)),
                    "raw_auc": raw["auc"],
                    "auc_floor": raw["auc_floor"],
                    "direction": raw["direction"],
                    "inverted": raw["auc"] < 0.5,
                    "score_holdout_benign": score_dist(sc[: len(hold_shas)]),
                    "score_malware": score_dist(sc[len(hold_shas) :]),
                }
            )
        raws = np.asarray([f["raw_auc"] for f in fold_rows], dtype=np.float64)
        floors = np.asarray([f["auc_floor"] for f in fold_rows], dtype=np.float64)
        w = np.asarray([f["n_test"] for f in fold_rows], dtype=np.float64)
        pooled = eval_auc_block(pooled_s, pooled_y)
        return {
            "detector": det_name,
            "n_folds": len(fold_rows),
            "n_folds_raw_auc_lt_0.5": int(np.sum(raws < 0.5)),
            "mean_raw_auc": float(np.mean(raws)),
            "mean_auc_floor": float(np.mean(floors)),
            "weighted_mean_raw_auc": float(np.average(raws, weights=w)),
            "weighted_mean_auc_floor": float(np.average(floors, weights=w)),
            "pooled_oof_raw": pooled,
            "folds": fold_rows,
        }

    cent = _holdout("centroid_euclidean", fit_score_centroid_euclidean)
    maha = _holdout("mahalanobis", fit_score_mahalanobis)

    csv_path = out / "benign_holdout_per_fold.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "detector",
                "fold",
                "n_holdout_benign",
                "n_malware",
                "raw_auc",
                "auc_floor",
                "direction",
                "inverted",
            ]
        )
        for blk in (cent, maha):
            for row in blk["folds"]:
                w.writerow(
                    [
                        blk["detector"],
                        row["fold"],
                        row["n_holdout_benign"],
                        row["n_malware"],
                        f"{row['raw_auc']:.10f}",
                        f"{row['auc_floor']:.10f}",
                        row["direction"],
                        int(row["inverted"]),
                    ]
                )

    payload = {
        "gae_retrained_per_fold": False,
        "reference_recomputed_per_fold": True,
        "profiles": "devread/artifacts/profiles/D1_trained_t22.npy",
        "clustering": {
            "population": "train_benign_only_n=562",
            "malware_used_in_clustering": False,
            "features": "T22 full vectors (node+adj), StandardScaler fit on train-benign",
            "method": "Ward agglomerative",
            "k_grid": list(K_GRID),
            "silhouette": sil,
            "chosen_k": k,
            "cluster_sizes": sizes,
        },
        "centroid_euclidean": {k: v for k, v in cent.items() if k != "folds"} | {"folds": cent["folds"]},
        "mahalanobis": {k: v for k, v in maha.items() if k != "folds"} | {"folds": maha["folds"]},
    }
    write_json(out / "check4.json", payload)
    return payload
