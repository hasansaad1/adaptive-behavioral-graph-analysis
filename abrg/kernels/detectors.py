"""Stage-2 one-class detectors for embeddings and precomputed kernels."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.kernels import OCPOOL_MEAN_RAW, SIZE_FLOOR


def _rho(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    r, _ = spearmanr(xs, ys)
    return float(r)


def leak_spearman(scores: list[float], cov: dict[str, list[float]]) -> dict[str, float]:
    return {k: _rho(scores, v) for k, v in cov.items()}


def eval_row(
    scores: list[float],
    labels: list[int],
    cov: dict[str, list[float]],
) -> dict[str, Any]:
    auc = _auc_with_bootstrap(scores, labels)
    floor = float(auc["auc_floor"])
    return {
        "auc": auc,
        "leak_spearman": leak_spearman(scores, cov),
        "gate": {
            "clears_size_floor_0.7025": bool(floor > SIZE_FLOOR),
            "clears_OCPool_mean_0.7765": bool(floor > OCPOOL_MEAN_RAW),
            "is_result": bool(floor > SIZE_FLOOR),
        },
    }


# --- embedding-space detectors ---


def det_ocsvm_rbf(X_tr: np.ndarray, X_te: np.ndarray, *, seed: int) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    clf = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")
    clf.fit(scaler.transform(X_tr))
    return (-clf.decision_function(scaler.transform(X_te))).tolist()


def det_isolation_forest(X_tr: np.ndarray, X_te: np.ndarray, *, seed: int) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    clf = IsolationForest(
        n_estimators=200, contamination="auto", random_state=seed, n_jobs=1
    )
    clf.fit(scaler.transform(X_tr))
    return (-clf.score_samples(scaler.transform(X_te))).tolist()


def det_centroid_euclidean(X_tr: np.ndarray, X_te: np.ndarray) -> list[float]:
    c = X_tr.mean(axis=0, keepdims=True)
    return np.linalg.norm(X_te - c, axis=1).tolist()


def det_centroid_cosine(X_tr: np.ndarray, X_te: np.ndarray) -> list[float]:
    c = X_tr.mean(axis=0)
    cn = np.linalg.norm(c) + 1e-12
    xn = np.linalg.norm(X_te, axis=1) + 1e-12
    cos = (X_te @ c) / (xn * cn)
    return (1.0 - cos).tolist()


def det_knn(X_tr: np.ndarray, X_te: np.ndarray, *, k: int) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean", n_jobs=1)
    nn.fit(Xtr)
    dists, _ = nn.kneighbors(Xte)
    return dists.mean(axis=1).tolist()


def det_lof(X_tr: np.ndarray, X_te: np.ndarray, *, seed: int) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    # novelty=True → fit on train, score eval
    clf = LocalOutlierFactor(n_neighbors=20, novelty=True, contamination="auto")
    clf.fit(Xtr)
    return (-clf.score_samples(Xte)).tolist()


def run_embedding_detectors(
    X_tr: np.ndarray,
    X_tb: np.ndarray,
    X_tm: np.ndarray,
    cov: dict[str, list[float]],
    seeds: tuple[int, ...],
) -> dict[str, Any]:
    X_te = np.vstack([X_tb, X_tm])
    labels = [0] * len(X_tb) + [1] * len(X_tm)
    out: dict[str, Any] = {}

    for name, fn in (
        ("ocsvm_rbf", det_ocsvm_rbf),
        ("isolation_forest", det_isolation_forest),
        ("lof_novelty", det_lof),
    ):
        per = []
        for seed in seeds:
            scores = fn(X_tr, X_te, seed=seed)
            row = eval_row(scores, labels, cov)
            row["seed"] = seed
            per.append(row)
        floors = [r["auc"]["auc_floor"] for r in per]
        out[name] = {
            "stochastic": True,
            "seeds": list(seeds),
            "auc_floor_mean": float(np.mean(floors)),
            "auc_floor_std": float(np.std(floors)),
            "per_seed": per,
        }

    for name, scores in (
        ("centroid_euclidean", det_centroid_euclidean(X_tr, X_te)),
        ("centroid_cosine", det_centroid_cosine(X_tr, X_te)),
        ("knn_k1", det_knn(X_tr, X_te, k=1)),
        ("knn_k5", det_knn(X_tr, X_te, k=5)),
        ("knn_k20", det_knn(X_tr, X_te, k=20)),
    ):
        row = eval_row(scores, labels, cov)
        row["stochastic"] = False
        out[name] = row
    return out


# --- kernel detectors ---


def det_ocsvm_precomputed(K_tr: np.ndarray, K_et: np.ndarray) -> list[float]:
    clf = OneClassSVM(kernel="precomputed", nu=0.1)
    clf.fit(K_tr)
    return (-clf.decision_function(K_et)).tolist()


def _kernel_distances_to_train(K_et: np.ndarray, K_tr: np.ndarray) -> np.ndarray:
    """
    Squared distances in RKHS: ||φ(x)-φ(y)||^2 = Kxx + Kyy - 2 Kxy.
    For eval i vs train j: use K_et[i,j], diag of K_tr for train, and
    approximate K_ee[i,i] ≈ 1 if normalized else use max self-sim via train.
    When kernels are normalized, K_ii=1.
    """
    # assume normalized kernels → diag ≈ 1
    k_ee = np.ones(K_et.shape[0], dtype=np.float64)
    k_tt = np.diag(K_tr).astype(np.float64)
    # d2[i,j] = k_ee[i] + k_tt[j] - 2 K_et[i,j]
    d2 = k_ee[:, None] + k_tt[None, :] - 2.0 * K_et
    return np.maximum(d2, 0.0)


def det_knn_kernel(K_tr: np.ndarray, K_et: np.ndarray, *, k: int) -> list[float]:
    d2 = _kernel_distances_to_train(K_et, K_tr)
    # mean of k smallest distances to train
    part = np.partition(d2, kth=min(k, d2.shape[1] - 1), axis=1)[:, :k]
    return np.sqrt(part).mean(axis=1).tolist()


def run_kernel_detectors(
    K_tr: np.ndarray,
    K_et_b: np.ndarray,
    K_et_m: np.ndarray,
    cov: dict[str, list[float]],
) -> dict[str, Any]:
    K_et = np.vstack([K_et_b, K_et_m])
    labels = [0] * len(K_et_b) + [1] * len(K_et_m)
    out: dict[str, Any] = {}
    # OCSVM precomputed is deterministic given Gram
    row = eval_row(det_ocsvm_precomputed(K_tr, K_et), labels, cov)
    row["stochastic"] = False
    out["ocsvm_precomputed"] = row
    for k in (1, 5, 20):
        row = eval_row(det_knn_kernel(K_tr, K_et, k=k), labels, cov)
        row["stochastic"] = False
        out[f"knn_kernel_k{k}"] = row
    return out
