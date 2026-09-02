"""OCPool shallow baseline (no edges, no training of a GNN)."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from sklearn.svm import OneClassSVM

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist
from abrg.ocgin.score import leak_spearman

PoolName = Literal["add", "mean", "max"]


def pool_node_features(x: np.ndarray, how: PoolName) -> np.ndarray:
    # x: [22, 10]
    if how == "add":
        return x.sum(axis=0)
    if how == "mean":
        return x.mean(axis=0)
    if how == "max":
        return x.max(axis=0)
    raise ValueError(how)


def ocpool_eval(
    tensors: dict[str, dict],
    split: dict[str, list],
    *,
    pool: PoolName,
    nu: float = 0.1,
    anomaly_is_malware: bool = True,
) -> dict[str, Any]:
    def mat(apps: list) -> np.ndarray:
        rows = []
        for a in apps:
            x = tensors[a.sha256]["x"].detach().cpu().numpy()
            rows.append(pool_node_features(x, pool))
        return np.asarray(rows, dtype=np.float64)

    X_tr = mat(split["train"])
    X_tb = mat(split["test_benign"])
    X_tm = mat(split["test_malware"])

    clf = OneClassSVM(kernel="rbf", nu=nu, gamma="scale")
    clf.fit(X_tr)
    # decision_function: larger = more normal; anomaly score = -decision
    sc_tr = -clf.decision_function(X_tr)
    sc_tb = -clf.decision_function(X_tb)
    sc_tm = -clf.decision_function(X_tm)

    if anomaly_is_malware:
        scores = sc_tb.tolist() + sc_tm.tolist()
        labels = [0] * len(sc_tb) + [1] * len(sc_tm)
    else:
        scores = sc_tm.tolist() + sc_tb.tolist()
        labels = [0] * len(sc_tm) + [1] * len(sc_tb)
    auc = _auc_with_bootstrap(scores, labels)
    test_apps = split["test_benign"] + split["test_malware"]
    leak_scores = sc_tb.tolist() + sc_tm.tolist()
    return {
        "method": f"OCPool_{pool}",
        "pool": pool,
        "auc": auc,
        "collapse": False,
        "score_distributions": {
            "train": _dist(sc_tr.tolist()),
            "test_benign": _dist(sc_tb.tolist()),
            "test_malware": _dist(sc_tm.tolist()),
        },
        "leak_spearman": leak_spearman(leak_scores, test_apps, tensors),
        "n_train": len(split["train"]),
        "n_test_benign": len(split["test_benign"]),
        "n_test_malware": len(split["test_malware"]),
        "graph_embedding_dim": int(X_tr.shape[1]),
    }
