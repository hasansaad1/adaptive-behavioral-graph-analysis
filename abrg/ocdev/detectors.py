"""One-class detectors fit on train-benign only; return scores + fitted objects."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist


def leak_spearman(scores: list[float], cov: dict[str, list[float]]) -> dict[str, float]:
    out = {}
    for k, v in cov.items():
        if len(scores) < 3:
            out[k] = float("nan")
        else:
            r, _ = spearmanr(scores, v)
            out[k] = float(r)
    return out


def eval_block(
    scores: list[float],
    labels: list[int],
    cov: dict[str, list[float]],
    *,
    score_parts: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    auc = _auc_with_bootstrap(scores, labels)
    n0 = labels.count(0)
    n1 = labels.count(1)
    # assume scores ordered test_benign then test_malware when n matches
    tb = scores[:n0] if len(scores) == n0 + n1 else []
    tm = scores[n0:] if len(scores) == n0 + n1 else []
    return {
        "auc": auc,
        "direction_inverted": auc.get("direction") == "benign_higher_score",
        "leak_spearman": leak_spearman(scores, cov),
        "score_distributions": {
            "test_benign": _dist(tb) if tb else {},
            "test_malware": _dist(tm) if tm else {},
        },
    }


def fit_pca(X_tr: np.ndarray, n_components: int) -> tuple[PCA, dict[str, Any]]:
    n_comp = min(n_components, X_tr.shape[0] - 1, X_tr.shape[1])
    pca = PCA(n_components=n_comp, random_state=42)
    pca.fit(X_tr)
    meta = {
        "requested": n_components,
        "fitted": int(n_comp),
        "explained_variance_ratio": [float(v) for v in pca.explained_variance_ratio_],
        "explained_variance_sum": float(pca.explained_variance_ratio_.sum()),
    }
    return pca, meta


def fit_score_centroid_euclidean(X_tr: np.ndarray, X_te: np.ndarray) -> tuple[list[float], dict]:
    c = X_tr.mean(axis=0)
    scores = np.linalg.norm(X_te - c, axis=1).tolist()
    return scores, {"centroid": c, "kind": "centroid_euclidean"}


def fit_score_centroid_cosine(X_tr: np.ndarray, X_te: np.ndarray) -> tuple[list[float], dict]:
    c = X_tr.mean(axis=0)
    cn = np.linalg.norm(c) + 1e-12
    xn = np.linalg.norm(X_te, axis=1) + 1e-12
    cos = (X_te @ c) / (xn * cn)
    return (1.0 - cos).tolist(), {"centroid": c, "kind": "centroid_cosine"}


def fit_score_mahalanobis(X_tr: np.ndarray, X_te: np.ndarray) -> tuple[list[float], dict]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    lw = LedoitWolf().fit(Xtr)
    diff = Xte - lw.location_
    d2 = np.einsum("ij,jk,ik->i", diff, lw.precision_, diff)
    return d2.tolist(), {"scaler": scaler, "lw": lw, "kind": "mahalanobis"}


def fit_score_ocsvm(X_tr: np.ndarray, X_te: np.ndarray, *, seed: int) -> tuple[list[float], Any]:
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")),
        ]
    )
    pipe.fit(X_tr)
    scores = (-pipe.decision_function(X_te)).tolist()
    return scores, pipe


def fit_score_iforest(X_tr: np.ndarray, X_te: np.ndarray, *, seed: int) -> tuple[list[float], Any]:
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                IsolationForest(
                    n_estimators=200, contamination="auto", random_state=seed, n_jobs=-1
                ),
            ),
        ]
    )
    pipe.fit(X_tr)
    # IsolationForest score_samples via named step after transform
    Xte = pipe.named_steps["scaler"].transform(X_te)
    scores = (-pipe.named_steps["clf"].score_samples(Xte)).tolist()
    return scores, pipe


def fit_score_knn(X_tr: np.ndarray, X_te: np.ndarray, *, k: int) -> tuple[list[float], dict]:
    scaler = StandardScaler().fit(X_tr)
    Xtr = scaler.transform(X_tr)
    Xte = scaler.transform(X_te)
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean", n_jobs=-1)
    nn.fit(Xtr)
    dists, _ = nn.kneighbors(Xte)
    return dists.mean(axis=1).tolist(), {"scaler": scaler, "nn": nn, "k": k, "kind": "knn"}


def fit_score_lof(X_tr: np.ndarray, X_te: np.ndarray, *, k: int = 20) -> tuple[list[float], Any]:
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LocalOutlierFactor(n_neighbors=k, novelty=True, contamination="auto")),
        ]
    )
    pipe.fit(X_tr)
    Xte = pipe.named_steps["scaler"].transform(X_te)
    scores = (-pipe.named_steps["clf"].score_samples(Xte)).tolist()
    return scores, pipe


def score_with_fitted(fitted: Any, X_te: np.ndarray, kind: str) -> list[float]:
    if kind == "centroid_euclidean":
        c = fitted["centroid"]
        return np.linalg.norm(X_te - c, axis=1).tolist()
    if kind == "centroid_cosine":
        c = fitted["centroid"]
        cn = np.linalg.norm(c) + 1e-12
        xn = np.linalg.norm(X_te, axis=1) + 1e-12
        return (1.0 - (X_te @ c) / (xn * cn)).tolist()
    if kind == "mahalanobis":
        Xte = fitted["scaler"].transform(X_te)
        diff = Xte - fitted["lw"].location_
        return np.einsum("ij,jk,ik->i", diff, fitted["lw"].precision_, diff).tolist()
    if kind == "knn":
        Xte = fitted["scaler"].transform(X_te)
        dists, _ = fitted["nn"].kneighbors(Xte)
        return dists.mean(axis=1).tolist()
    if isinstance(fitted, Pipeline):
        name = fitted.named_steps["clf"].__class__.__name__
        if name == "OneClassSVM":
            return (-fitted.decision_function(X_te)).tolist()
        Xte = fitted.named_steps["scaler"].transform(X_te)
        return (-fitted.named_steps["clf"].score_samples(Xte)).tolist()
    raise ValueError(kind)
