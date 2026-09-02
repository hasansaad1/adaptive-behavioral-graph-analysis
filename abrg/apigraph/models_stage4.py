"""Stage 4 models — only invoked if Stage 3 structural gate passes."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist
from abrg.autoencoder import (
    FeatureDecoder,
    build_gae,
    graph_reconstruction_error_dual,
    train_gae_multi_dual,
)
from abrg.ocgin.models import build_ocgin
from abrg.ocgin.score import collapse_diagnostics, score_distance_sq
from abrg.ocgin.train import embed_loader, init_theta, make_loader
from scipy.stats import spearmanr


def _rho(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    r, _ = spearmanr(xs, ys)
    return float(r)


def leak_vs_tensors(scores: list[float], shas: list[str], tensors: dict) -> dict[str, float]:
    return {
        "in_vocab_events": _rho(scores, [float(tensors[s]["n_inv_events"]) for s in shas]),
        "total_events": _rho(scores, [float(tensors[s]["n_total_events"]) for s in shas]),
        "active_nodes": _rho(scores, [float(tensors[s]["n_active"]) for s in shas]),
        "edge_count": _rho(scores, [float(tensors[s]["n_edges"]) for s in shas]),
        "density": _rho(scores, [float(tensors[s]["density"]) for s in shas]),
        "static_norm": _rho(
            scores, [float(tensors[s]["static_global"].norm().item()) for s in shas]
        ),
    }


def _flat(t: dict) -> np.ndarray:
    return np.concatenate(
        [t["x"].detach().cpu().numpy().reshape(-1), t["static_global"].detach().cpu().numpy()]
    )


def ocpool(tensors, train_shas, test_b, test_m, pool: str) -> dict[str, Any]:
    def pool_x(sha: str) -> np.ndarray:
        x = tensors[sha]["x"].detach().cpu().numpy()
        if pool == "add":
            v = x.sum(axis=0)
        elif pool == "mean":
            v = x.mean(axis=0)
        else:
            v = x.max(axis=0)
        return np.concatenate([v, tensors[sha]["static_global"].detach().cpu().numpy()])

    X_tr = np.stack([pool_x(s) for s in train_shas])
    X_tb = np.stack([pool_x(s) for s in test_b])
    X_tm = np.stack([pool_x(s) for s in test_m])
    clf = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale").fit(X_tr)
    sc_tb = (-clf.decision_function(X_tb)).tolist()
    sc_tm = (-clf.decision_function(X_tm)).tolist()
    scores = sc_tb + sc_tm
    labels = [0] * len(sc_tb) + [1] * len(sc_tm)
    auc = _auc_with_bootstrap(scores, labels)
    shas = test_b + test_m
    return {
        "method": f"OCPool_{pool}",
        "auc": auc,
        "leak_spearman": leak_vs_tensors(scores, shas, tensors),
        "score_distributions": {
            "test_benign": _dist(sc_tb),
            "test_malware": _dist(sc_tm),
        },
    }


def supervised_probe(tensors, train_shas_b, train_shas_m, test_b, test_m) -> dict[str, Any]:
    """Stratified both-class (diagnostic). Uses malware in train — not a method claim."""
    X_tr = np.stack([_flat(tensors[s]) for s in train_shas_b + train_shas_m])
    y_tr = np.array([0] * len(train_shas_b) + [1] * len(train_shas_m))
    X_te = np.stack([_flat(tensors[s]) for s in test_b + test_m])
    y_te = np.array([0] * len(test_b) + [1] * len(test_m))
    out = {}
    for name, clf in (
        (
            "logistic_regression",
            Pipeline(
                [
                    ("sc", StandardScaler()),
                    ("lr", LogisticRegression(max_iter=2000, solver="lbfgs")),
                ]
            ),
        ),
        ("hist_gradient_boosting", HistGradientBoostingClassifier(random_state=42)),
    ):
        clf.fit(X_tr, y_tr)
        if hasattr(clf, "predict_proba"):
            scores = clf.predict_proba(X_te)[:, 1].tolist()
        else:
            scores = clf.decision_function(X_te).tolist()
        out[name] = _auc_with_bootstrap(scores, y_te.tolist())
    return out


def run_gae_dual(
    tensors,
    train_shas,
    test_b,
    test_m,
    *,
    seed: int,
    epochs: int = 300,
    hidden: int = 8,
    alpha: float = 0.2,
    lr: float = 0.01,
    trained: bool = True,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    in_ch = int(tensors[train_shas[0]]["x"].size(1))
    model = build_gae(in_ch, hidden)
    feat_dec = FeatureDecoder(hidden, in_ch)
    train_graphs = [
        (tensors[s]["x"], tensors[s]["edge_index"], tensors[s]["edge_weight"])
        for s in train_shas
        if tensors[s]["edge_index"].numel() > 0
    ]
    if trained and train_graphs:
        train_gae_multi_dual(
            model, feat_dec, train_graphs, epochs, lr, alpha=alpha, weight_decay=0.0
        )

    def score(sha: str) -> float:
        t = tensors[sha]
        return float(
            graph_reconstruction_error_dual(
                model, feat_dec, t["x"], t["edge_index"], t["edge_weight"], alpha=alpha
            )
        )

    sc_tb = [score(s) for s in test_b]
    sc_tm = [score(s) for s in test_m]
    scores = sc_tb + sc_tm
    labels = [0] * len(sc_tb) + [1] * len(sc_tm)
    auc = _auc_with_bootstrap(scores, labels)
    return {
        "seed": seed,
        "trained": trained,
        "auc": auc,
        "leak_spearman": leak_vs_tensors(scores, test_b + test_m, tensors),
        "score_distributions": {
            "test_benign": _dist(sc_tb),
            "test_malware": _dist(sc_tm),
        },
    }


def run_ocgin_plus(
    tensors,
    train_shas,
    test_b,
    test_m,
    *,
    seed: int,
    epochs: int = 300,
    trained: bool = True,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    device = torch.device("cpu")
    in_ch = int(tensors[train_shas[0]]["x"].size(1))
    model = build_ocgin("OCGIN_plus", in_dim=in_ch, hidden=32, n_layers=4).to(device)

    # Adapt DataLoader from ocgin — use x/edge_index only
    class _App:
        def __init__(self, sha):
            self.sha256 = sha

    train_apps = [_App(s) for s in train_shas]
    # monkey: make_loader expects tensors[sha]
    init_loader = make_loader(tensors, train_apps, batch_size=32, shuffle=False)
    theta = init_theta(model, init_loader, device).to(device)
    theta.requires_grad_(False)

    if trained:
        opt = torch.optim.Adam(model.parameters(), lr=0.01)
        loader = make_loader(tensors, train_apps, batch_size=32, shuffle=True)
        model.train()
        for _ in range(epochs):
            for batch in loader:
                batch = batch.to(device)
                opt.zero_grad()
                z = model(batch.x, batch.edge_index, batch.batch)
                loss = ((z - theta) ** 2).sum(dim=-1).mean()
                loss.backward()
                opt.step()

    def emb_scores(shas: list[str]):
        apps = [_App(s) for s in shas]
        loader = make_loader(tensors, apps, batch_size=32, shuffle=False)
        emb = embed_loader(model, loader, device)
        return score_distance_sq(emb, theta.cpu()), emb

    sc_tb, emb_tb = emb_scores(test_b)
    sc_tm, emb_tm = emb_scores(test_m)
    sc_tr, emb_tr = emb_scores(train_shas)
    scores = sc_tb.tolist() + sc_tm.tolist()
    labels = [0] * len(sc_tb) + [1] * len(sc_tm)
    auc = _auc_with_bootstrap(scores, labels)
    diag = {
        "train": collapse_diagnostics(emb_tr, theta.cpu(), label="train"),
        "test_benign": collapse_diagnostics(emb_tb, theta.cpu(), label="test_benign"),
        "test_malware": collapse_diagnostics(emb_tm, theta.cpu(), label="test_malware"),
    }
    return {
        "seed": seed,
        "trained": trained,
        "auc": auc,
        "collapse": bool(diag["train"]["collapse_detected"]),
        "collapse_diagnostics": diag,
        "leak_spearman": leak_vs_tensors(scores, test_b + test_m, tensors),
        "score_distributions": {
            "test_benign": _dist(sc_tb.tolist()),
            "test_malware": _dist(sc_tm.tolist()),
        },
    }
