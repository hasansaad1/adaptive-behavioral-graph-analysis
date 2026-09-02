"""One-class detectors + PCA (fit train-benign only)."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from scipy.stats import spearmanr
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from abrg.androct.run_gae_run2 import _auc_with_bootstrap


def _rho(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    r, _ = spearmanr(xs, ys)
    return float(r)


def leak_spearman(scores: list[float], cov: dict[str, list[float]]) -> dict[str, float]:
    return {k: _rho(scores, v) for k, v in cov.items()}


def fit_pca_train_only(
    X_train: np.ndarray, n_components: int
) -> tuple[PCA, dict[str, Any]]:
    """PCA fit on train-benign only. Assert n_components < n_samples and <= n_features."""
    n_comp = min(n_components, X_train.shape[0] - 1, X_train.shape[1])
    pca = PCA(n_components=n_comp, random_state=42)
    pca.fit(X_train)
    meta = {
        "requested": n_components,
        "fitted": int(n_comp),
        "explained_variance_ratio": [float(v) for v in pca.explained_variance_ratio_],
        "explained_variance_sum": float(pca.explained_variance_ratio_.sum()),
        "n_train": int(X_train.shape[0]),
        "n_features_in": int(X_train.shape[1]),
    }
    return pca, meta


def transform_pair(
    X_tr: np.ndarray, X_te: np.ndarray, pca: PCA | None
) -> tuple[np.ndarray, np.ndarray]:
    if pca is None:
        return X_tr, X_te
    return pca.transform(X_tr), pca.transform(X_te)


DetectorFn = Callable[..., dict[str, Any]]


def score_ocsvm(
    X_tr: np.ndarray, X_te: np.ndarray, *, seed: int
) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    # integrity: scaler fit on train only
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    clf = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")
    clf.fit(Xtr)
    return (-clf.decision_function(Xte)).tolist()


def score_isolation_forest(
    X_tr: np.ndarray, X_te: np.ndarray, *, seed: int
) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    clf = IsolationForest(
        n_estimators=200, contamination="auto", random_state=seed, n_jobs=-1
    )
    clf.fit(Xtr)
    return (-clf.score_samples(Xte)).tolist()


def score_centroid_euclidean(X_tr: np.ndarray, X_te: np.ndarray) -> list[float]:
    c = X_tr.mean(axis=0, keepdims=True)
    return np.linalg.norm(X_te - c, axis=1).tolist()


def score_centroid_cosine(X_tr: np.ndarray, X_te: np.ndarray) -> list[float]:
    c = X_tr.mean(axis=0)
    cn = np.linalg.norm(c) + 1e-12
    xn = np.linalg.norm(X_te, axis=1) + 1e-12
    cos = (X_te @ c) / (xn * cn)
    return (1.0 - cos).tolist()  # higher = farther from centroid


def score_mahalanobis(X_tr: np.ndarray, X_te: np.ndarray) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    lw = LedoitWolf().fit(Xtr)
    diff = Xte - lw.location_
    d2 = np.einsum("ij,jk,ik->i", diff, lw.precision_, diff)
    return d2.tolist()


def score_knn(X_tr: np.ndarray, X_te: np.ndarray, *, k: int) -> list[float]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean", n_jobs=-1)
    nn.fit(Xtr)
    dists, _ = nn.kneighbors(Xte)
    return dists.mean(axis=1).tolist()


def eval_scores(
    scores: list[float],
    labels: list[int],
    cov: dict[str, list[float]],
) -> dict[str, Any]:
    auc = _auc_with_bootstrap(scores, labels)
    return {
        "auc": auc,
        "leak_spearman": leak_spearman(scores, cov),
    }
