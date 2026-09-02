"""Scoring, collapse diagnostics, Spearman leak, size floors."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from scipy.stats import spearmanr
from torch import Tensor

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist, floor_aucs
from abrg.ocgin import COLLAPSE_VAR_THRESHOLD, NEAR_THETA_EPS
from abrg.ocgin.models import OCGIN
from abrg.ocgin.train import embed_loader, make_loader


def score_distance_sq(emb: Tensor, theta: Tensor) -> np.ndarray:
    d = emb - theta.unsqueeze(0)
    return (d ** 2).sum(dim=-1).detach().cpu().numpy()


def collapse_diagnostics(emb: Tensor, theta: Tensor, *, label: str) -> dict[str, Any]:
    if emb.numel() == 0:
        return {"label": label, "n": 0}
    var_per_dim = emb.var(dim=0, unbiased=False).cpu().numpy()
    mean_var = float(var_per_dim.mean())
    dist = torch.norm(emb - theta.unsqueeze(0), dim=-1).cpu().numpy()
    frac_near = float((dist < NEAR_THETA_EPS).mean())
    collapse = mean_var < COLLAPSE_VAR_THRESHOLD
    return {
        "label": label,
        "n": int(emb.size(0)),
        "var_per_dim": var_per_dim.tolist(),
        "mean_var_across_dims": mean_var,
        "dist_to_theta_mean": float(dist.mean()),
        "dist_to_theta_std": float(dist.std()),
        "frac_within_1e-3_of_theta": frac_near,
        "collapse_detected": collapse,
    }


def leak_spearman(scores: list[float], apps: list, tensors: dict[str, dict]) -> dict[str, float]:
    def rho(xs: list[float], ys: list[float]) -> float:
        if len(xs) < 3:
            return float("nan")
        r, _ = spearmanr(xs, ys)
        return float(r)

    return {
        "mapped_event_count": rho(scores, [float(a.n_mapped) for a in apps]),
        "total_event_count": rho(scores, [float(getattr(a, "n_events", 0)) for a in apps]),
        "active_nodes": rho(scores, [float(tensors[a.sha256]["n_active"]) for a in apps]),
        "edge_count": rho(scores, [float(tensors[a.sha256]["n_edges"]) for a in apps]),
        "graph_density": rho(scores, [float(tensors[a.sha256]["density"]) for a in apps]),
        "static_feature_norm": rho(
            scores, [float(getattr(a, "static_norm", tensors[a.sha256].get("static_slice_norm", 0.0))) for a in apps]
        ),
    }


def evaluate_scores(
    scores_benign: np.ndarray,
    scores_malware: np.ndarray,
    *,
    anomaly_is_malware: bool = True,
) -> dict[str, Any]:
    """
    Higher score = more anomalous.
    Variant A: malware is anomaly (labels 0=benign, 1=malware).
    Variant B: benign is anomaly (labels 0=malware, 1=benign) — diagnostic only.
    """
    if anomaly_is_malware:
        scores = scores_benign.tolist() + scores_malware.tolist()
        labels = [0] * len(scores_benign) + [1] * len(scores_malware)
    else:
        scores = scores_malware.tolist() + scores_benign.tolist()
        labels = [0] * len(scores_malware) + [1] * len(scores_benign)
    auc_block = _auc_with_bootstrap(scores, labels)
    return auc_block


def score_partition(
    model: OCGIN,
    theta: Tensor,
    tensors: dict[str, dict],
    apps: list,
    *,
    batch_size: int,
    device: torch.device,
) -> tuple[np.ndarray, Tensor]:
    loader = make_loader(tensors, apps, batch_size=batch_size, shuffle=False)
    emb = embed_loader(model, loader, device)
    return score_distance_sq(emb, theta.to(emb.device)), emb


def full_method_eval(
    model: OCGIN,
    theta: Tensor,
    tensors: dict[str, dict],
    split: dict[str, list],
    *,
    batch_size: int,
    device: torch.device,
    anomaly_is_malware: bool = True,
) -> dict[str, Any]:
    model.eval()
    sc_tr, emb_tr = score_partition(
        model, theta, tensors, split["train"], batch_size=batch_size, device=device
    )
    sc_tb, emb_tb = score_partition(
        model, theta, tensors, split["test_benign"], batch_size=batch_size, device=device
    )
    sc_tm, emb_tm = score_partition(
        model, theta, tensors, split["test_malware"], batch_size=batch_size, device=device
    )

    diag = {
        "train": collapse_diagnostics(emb_tr, theta, label="train"),
        "test_benign": collapse_diagnostics(emb_tb, theta, label="test_benign"),
        "test_malware": collapse_diagnostics(emb_tm, theta, label="test_malware"),
    }
    collapse = bool(diag["train"]["collapse_detected"])

    auc = evaluate_scores(sc_tb, sc_tm, anomaly_is_malware=anomaly_is_malware)
    test_apps = split["test_benign"] + split["test_malware"]
    if anomaly_is_malware:
        test_scores = sc_tb.tolist() + sc_tm.tolist()
    else:
        # scores stay distance-to-theta; AUC uses remapped labels above
        test_scores = sc_tb.tolist() + sc_tm.tolist()

    leak = leak_spearman(test_scores, test_apps, tensors)
    return {
        "auc": auc,
        "collapse": collapse,
        "collapse_diagnostics": diag,
        "score_distributions": {
            "train": _dist(sc_tr.tolist()),
            "test_benign": _dist(sc_tb.tolist()),
            "test_malware": _dist(sc_tm.tolist()),
        },
        "leak_spearman": leak,
        "n_train": len(split["train"]),
        "n_test_benign": len(split["test_benign"]),
        "n_test_malware": len(split["test_malware"]),
        "graph_embedding_dim": model.graph_embedding_dim,
    }
